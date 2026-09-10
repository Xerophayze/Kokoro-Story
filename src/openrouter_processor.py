"""OpenRouter LLM integration using its OpenAI-compatible HTTP API."""

from __future__ import annotations

import re
import json
import logging
import math
import time
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Any, List, Optional

import requests
from src.structured_output import validate_schema, parse_structured_response


DEFAULT_OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
DEFAULT_OPENROUTER_MODEL = "openrouter/auto"


class OpenRouterProcessorError(RuntimeError):
    """Raised when OpenRouter model discovery or generation fails."""

    def __init__(self, message, *, status_code=None, provider_name=None,
                 provider_code=None, retry_after=None):
        super().__init__(message)
        self.status_code = status_code
        self.provider_name = provider_name
        self.provider_code = provider_code
        self.retry_after = retry_after
        self.attempts = 1
        self.retries_exhausted = False


def _safe_error_text(value, api_key=""):
    text = str(value or "")
    if api_key:
        text = text.replace(api_key, "[redacted]")
    text = re.sub(r'(?i)Bearer\s+[^\s,;"\}]+', 'Bearer [redacted]', text)
    text = re.sub(r'\b(?:sk-[A-Za-z0-9_-]+|AIza[A-Za-z0-9_-]+)\b', '[redacted]', text)
    text = re.sub(r'(?i)((?:api[_-]?key|token|authorization)\s*[=:]\s*)[^\s,;]+',
                  r'\1[redacted]', text)
    return re.sub(r'\s+', ' ', text).strip()[:800]


def _retry_after_seconds(value):
    try:
        seconds = float(value)
    except (ValueError, TypeError):
        try:
            when = parsedate_to_datetime(str(value))
            if when.tzinfo is None:
                when = when.replace(tzinfo=timezone.utc)
            seconds = (when - datetime.now(timezone.utc)).total_seconds()
        except (ValueError, TypeError, OverflowError):
            return None
    return max(0.0, seconds) if math.isfinite(seconds) else None


def _unique_models(models: List[Optional[str]]) -> List[str]:
    cleaned = {str(model).strip() for model in models if model and str(model).strip()}
    return sorted(cleaned, key=str.casefold)


class OpenRouterProcessor:
    """List user-available OpenRouter models and submit chat completions."""

    def __init__(
        self,
        api_key: str,
        model_name: str,
        base_url: str = DEFAULT_OPENROUTER_BASE_URL,
        timeout: int = 120,
        temperature: Optional[float] = None,
        top_p: Optional[float] = None,
        top_k: Optional[int] = None,
        repetition_penalty: Optional[float] = None,
        max_tokens: Optional[int] = None,
        disable_reasoning: bool = False,
        max_attempts: int = 3,
        before_retry=None,
    ) -> None:
        self.api_key = (api_key or "").strip()
        self.model_name = (model_name or "").strip()
        self.base_url = self.normalize_base_url(base_url)
        self.timeout = max(10, int(timeout or 120))
        self.temperature = temperature
        self.top_p = top_p
        self.top_k = top_k
        self.repetition_penalty = repetition_penalty
        self.max_tokens = max_tokens
        self.disable_reasoning = disable_reasoning
        self.max_attempts = min(5, max(1, int(max_attempts)))
        self.before_retry = before_retry
        self.last_attempts = []
        self.last_finish_reason = None
        self.last_usage = {}
        self.last_response_id = None
        self.last_response_text = None

        if not self.api_key:
            raise OpenRouterProcessorError("OpenRouter API key is required")
        if not self.model_name:
            raise OpenRouterProcessorError("OpenRouter model is required")
        if not self.base_url:
            raise OpenRouterProcessorError("OpenRouter base URL is required")

    @staticmethod
    def normalize_base_url(base_url: str) -> str:
        base = (base_url or DEFAULT_OPENROUTER_BASE_URL).strip().rstrip("/")
        if base and not re.search(r"/(?:api/)?v1$", base, re.IGNORECASE):
            base = f"{base}/api/v1"
        return base

    @staticmethod
    def _headers(api_key: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {api_key.strip()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-OpenRouter-Title": "TTS-Story",
        }

    @staticmethod
    def _response_error(response: Any, action: str, api_key="") -> OpenRouterProcessorError:
        detail = ""
        provider = provider_code = None
        status = response.status_code
        metadata = {}
        try:
            payload = response.json()
            raw_error = payload.get("error") if isinstance(payload, dict) else None
            if isinstance(raw_error, dict):
                detail = str(raw_error.get("message") or "").strip()
                code = raw_error.get("code")
                if str(code).isdigit() and 400 <= int(code) <= 599:
                    status = int(code)
                metadata = raw_error.get("metadata") or {}
                if not isinstance(metadata, dict):
                    metadata = {}
                provider = metadata.get("provider_name")
                provider_code = metadata.get("provider_code") or metadata.get("error_type")
                raw = metadata.get("raw")
                if isinstance(raw, str):
                    try:
                        raw = json.loads(raw)
                    except (ValueError, TypeError):
                        pass
                if isinstance(raw, dict):
                    nested = raw.get("error")
                    raw = nested if isinstance(nested, dict) else raw
                    provider_code = provider_code or raw.get("code") or raw.get("type")
                    raw = raw.get("message") or raw.get("detail") or ""
                if isinstance(raw, str) and raw.strip():
                    detail += ": " + raw
            elif raw_error:
                detail = str(raw_error).strip()
            if not detail and isinstance(payload, dict):
                detail = str(payload.get("message") or "").strip()
        except Exception:
            raw_text = str(getattr(response, "text", "") or "").strip()
            if not re.search(r"<(?:!doctype|html|head|body)\b", raw_text, re.IGNORECASE):
                detail = re.sub(r"\s+", " ", raw_text)[:500]
        detail = _safe_error_text(detail, api_key)
        provider = _safe_error_text(provider, api_key) or None
        provider_code = _safe_error_text(provider_code, api_key) or None
        headers = getattr(response, 'headers', {}) or {}
        retry_after = _retry_after_seconds(headers.get('Retry-After'))
        if retry_after is None and isinstance(metadata.get('headers'), dict):
            retry_after = _retry_after_seconds(metadata['headers'].get('Retry-After'))
        suffix = f": {detail}" if detail else ""
        if provider:
            suffix += f" [provider: {provider}]"
        if provider_code:
            suffix += f" [upstream code: {provider_code}]"
        if retry_after is not None:
            suffix += f" [Retry-After: {retry_after:.0f}s]"
        return OpenRouterProcessorError(
            f"OpenRouter {action} failed (HTTP {status}){suffix}",
            status_code=status, provider_name=provider,
            provider_code=provider_code, retry_after=retry_after,
        )

    @classmethod
    def list_available_models(
        cls,
        api_key: str,
        base_url: str = DEFAULT_OPENROUTER_BASE_URL,
        timeout: int = 30,
        current_model: str = DEFAULT_OPENROUTER_MODEL,
    ) -> List[str]:
        api_key = (api_key or "").strip()
        if not api_key:
            raise OpenRouterProcessorError("OpenRouter API key is required")

        try:
            response = requests.get(
                f"{cls.normalize_base_url(base_url)}/models/user",
                headers=cls._headers(api_key),
                timeout=min(max(10, int(timeout or 30)), 60),
            )
        except Exception as exc:
            raise OpenRouterProcessorError(
                "OpenRouter model API request failed: " + _safe_error_text(exc, api_key)
            ) from None
        if response.status_code >= 400:
            raise cls._response_error(response, "model discovery", api_key)

        try:
            payload = response.json() if response.content else {}
        except Exception as exc:
            raise OpenRouterProcessorError(
                "OpenRouter model API returned invalid JSON"
            ) from exc

        entries = payload.get("data", []) if isinstance(payload, dict) else []
        model_ids: List[Optional[str]] = []
        for entry in entries if isinstance(entries, list) else []:
            if isinstance(entry, str):
                model_ids.append(entry)
                continue
            if not isinstance(entry, dict):
                continue
            architecture = entry.get("architecture") or {}
            output_modalities = architecture.get("output_modalities") or []
            if output_modalities and "text" not in output_modalities:
                continue
            model_ids.append(entry.get("id") or entry.get("canonical_slug"))

        discovered = _unique_models(model_ids)
        if not discovered:
            raise OpenRouterProcessorError(
                "No text-output models are available for this OpenRouter API key"
            )
        return _unique_models([*discovered, current_model])

    @staticmethod
    def _extract_content(payload: Any) -> str:
        choices = payload.get("choices") if isinstance(payload, dict) else None
        if not isinstance(choices, list) or not choices:
            return ""
        first = choices[0] if isinstance(choices[0], dict) else {}
        message = first.get("message") if isinstance(first, dict) else {}
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts = []
            for item in content:
                if isinstance(item, str):
                    parts.append(item)
                elif isinstance(item, dict) and item.get("text"):
                    parts.append(str(item["text"]))
            return "".join(parts).strip()
        return ""

    def generate_text(self, prompt: str, *, response_schema=None,
                      response_schema_name=None, response_schema_strict=True) -> str:
        if not (prompt or "").strip():
            raise OpenRouterProcessorError("Prompt must not be empty")

        payload: dict[str, Any] = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}],
            "stream": False,
        }
        self.last_usage = {}
        self.last_response_id = None
        self.last_response_text = None
        self.last_attempts = []
        self.last_finish_reason = None
        if response_schema is not None:
            payload["response_format"] = validate_schema(
                response_schema, response_schema_name, response_schema_strict)
            payload["provider"] = {"require_parameters": True}
        if self.temperature is not None:
            payload["temperature"] = float(self.temperature)
        if self.top_p is not None:
            payload["top_p"] = float(self.top_p)
        if self.top_k is not None and int(self.top_k) > 0:
            payload["top_k"] = int(self.top_k)
        if self.repetition_penalty is not None:
            payload["repetition_penalty"] = float(self.repetition_penalty)
        if self.max_tokens is not None and int(self.max_tokens) > 0:
            payload["max_tokens"] = int(self.max_tokens)
        if self.disable_reasoning:
            payload["reasoning"] = {"effort": "none"}

        waited = 0.0
        for attempt in range(1, self.max_attempts + 1):
            try:
                response = requests.post(
                    f"{self.base_url}/chat/completions", json=payload,
                    headers=self._headers(self.api_key), timeout=self.timeout)
            except Exception as exc:
                # A read timeout may still be billed upstream. Do not silently
                # multiply uncertain requests; let the caller decide how to proceed.
                error = OpenRouterProcessorError(
                    "OpenRouter generation request failed: " + _safe_error_text(exc, self.api_key))
                error.attempts = attempt
                self.last_attempts.append({'attempt':attempt, 'http_status':None,
                                           'error':str(error), 'usage':{}})
                raise error from None
            try:
                result = response.json()
            except Exception:
                if response.status_code < 400:
                    raise OpenRouterProcessorError("OpenRouter generation returned invalid JSON") from None
                result = {}
            if not isinstance(result, dict):
                raise OpenRouterProcessorError("OpenRouter generation returned invalid JSON object")
            self.last_usage = result.get('usage') or {}
            self.last_response_id = result.get('id')
            failure = response.status_code >= 400 or bool(result.get('error'))
            record = {'attempt': attempt, 'http_status': response.status_code,
                      'response_id': self.last_response_id, 'usage': self.last_usage}
            if not failure:
                self.last_attempts.append(record)
                break
            error = self._response_error(response, 'generation', self.api_key)
            error.attempts = attempt
            record['error'] = str(error)
            record['provider'] = error.provider_name
            self.last_attempts.append(record)
            transient = error.status_code in (429, 502, 503, 504)
            # Never replay partially generated content or permanent quota errors.
            permanent = re.search(r'(?i)insufficient.?quota|quota.?exceeded|daily.?limit|insufficient.?credits',
                                  str(error))
            delay = max(min(5.0 * 2 ** (attempt - 1), 30.0), error.retry_after or 0)
            if (not transient or permanent or self._extract_content(result)):
                raise error
            if attempt >= self.max_attempts or waited + delay > 60:
                # If Retry-After exceeds our total wait budget, stop instead of
                # retrying early. Preserve it for the UI/manual retry decision.
                error.retries_exhausted = True
                raise error
            if self.before_retry is not None:
                self.before_retry()  # Reserve each retry against profile daily cap.
            record['retry_delay_seconds'] = delay
            logging.getLogger(__name__).warning(
                'OpenRouter retry %s/%s in %.1fs: %s', attempt + 1, self.max_attempts, delay, error)
            time.sleep(delay)
            waited += delay
        content = self._extract_content(result)
        self.last_response_text = content
        self.last_usage = result.get("usage") or {}
        self.last_response_id = result.get("id")
        choices = result.get('choices') or []
        self.last_finish_reason = (choices[0].get('finish_reason')
                                   if isinstance(choices, list) and choices and isinstance(choices[0], dict)
                                   else None)
        if self.last_finish_reason == 'length' and response_schema is not None:
            raise OpenRouterProcessorError(
                'OpenRouter output reached the token limit; response may be truncated. '
                'Increase the output token budget before retrying.')
        if not content:
            raise OpenRouterProcessorError(
                "OpenRouter response did not contain any text"
            )
        if response_schema is not None:
            parse_structured_response(content, response_schema)
        return content
