"""BreezeBlue hosted TTS with consented, production-scoped sample uploads."""
from dataclasses import replace
from urllib.parse import quote
import re
import logging
import time

import requests

logger = logging.getLogger(__name__)

from .openai_tts_engine import OpenAITTSEngine
from .cloud_audio import apply_wav_effects
from ..audio_effects import VoiceFXSettings


class BreezeAPIError(RuntimeError):
    def __init__(self, message, status_code=None):
        super().__init__(message)
        self.status_code = status_code


class BreezeAPIEngine(OpenAITTSEngine):
    name = "breeze_api"

    def __init__(self, api_key="", *, model_id="breeze-tts-2", default_voice="",
                 instructions="", timeout=180, max_parallel=1, max_retries=2,
                 guidance_scale=4, productions=None, production_progress=None, **kwargs):
        if not str(api_key).strip():
            raise BreezeAPIError("Configure the Breeze API key in Settings → Breeze API.")
        super().__init__(api_key, base_url="https://api.breeze.blue/v1",
                         model_id=model_id, default_voice=default_voice,
                         voice_required=False, instructions=instructions, timeout=timeout,
                         max_parallel=max_parallel, max_retries=max_retries, **kwargs)
        self.guidance_scale = self._clamp(guidance_scale, 1, 10, 4)
        self.productions = productions
        self.production_progress = production_progress or (lambda *_: None)

    @property
    def headers(self):
        return {"xi-api-key": self.api_key, "Accept": "application/json"}

    def request(self, method, path, *, retry=False, **kwargs):
        # Do not retry uncertain writes/timeouts: a paid request may already exist.
        timeout = kwargs.pop("timeout", (10, self.timeout))
        accepted = kwargs.pop("accepted_statuses", (200,))
        started = time.time()
        speech = method == 'POST' and path.startswith('/text-to-speech/')
        for attempt in range(self.max_retries + 1):
            try:
                response = self._request(method, self.root_url + path, headers=self.headers,
                                         timeout=timeout, allow_redirects=False, **kwargs)
            except requests.RequestException as exc:
                if (speech and retry and isinstance(exc, (requests.ConnectionError, requests.Timeout))
                        and not isinstance(exc, requests.exceptions.SSLError)):
                    # A disconnected POST has no reliable receipt. History can
                    # identify possible accepted work, but absence isn't proof.
                    delay = min(30, 5 * (2 ** attempt))
                    logger.warning('Breeze speech connection lost (%s); checking history before any retry', type(exc).__name__)
                    self._sleep(delay)
                    self._check_disconnected_speech(path, kwargs.get('json') or {}, started)
                    if attempt < self.max_retries:
                        logger.warning('No matching Breeze history entry found. Retrying speech %s/%s; duplicate billing remains possible.', attempt + 1, self.max_retries)
                        continue
                    raise BreezeAPIError('Breeze speech connection failed after the configured retries. No matching recent history was found, but server acceptance cannot be ruled out. Check Breeze history before resuming.') from exc
                if path == '/voice-previews/clone':
                    raise BreezeAPIError('Breeze voice-sample upload failed or timed out before its result was confirmed. '
                                         'Open Manage production voices to recover the interrupted upload before resuming. '
                                         'Check Breeze account history; automatic retries are blocked to prevent duplicates.') from exc
                raise BreezeAPIError("Breeze API connection failed or timed out. Check account history before retrying a paid operation.") from exc
            if response.status_code in accepted:
                return response
            if retry and response.status_code in (429, 503) and attempt < self.max_retries:
                try:
                    delay = float(response.headers.get("Retry-After", 2 ** attempt))
                except (TypeError, ValueError):
                    delay = 2 ** attempt
                self._sleep(max(0, min(delay, 120)))
                continue
            raise BreezeAPIError(f"Breeze API request failed (HTTP {response.status_code}). Check API access, credits, voice permissions and plan concurrency.", response.status_code)

    def _check_disconnected_speech(self, path, payload, started):
        """Read-only, conservative reconciliation; never adopt ambiguous audio."""
        voice = path.rsplit('/', 1)[-1]
        try:
            data = self.request('GET', '/history', timeout=(5, 30), params={
                'voice_id': voice, 'model_id': payload.get('model_id'),
                'search': str(payload.get('text', ''))[:128], 'page_size': 100,
                'sort_direction': 'desc'}).json()
        except (BreezeAPIError, ValueError) as exc:
            raise BreezeAPIError('Breeze history could not be checked after the disconnect. Automatic speech retry stopped to avoid duplicate charges.') from exc
        if not isinstance(data, dict) or not isinstance(data.get('history'), list):
            raise BreezeAPIError('Breeze returned an unreadable history response; automatic speech retry stopped.')
        records = data['history']
        for record in records:
            if not isinstance(record, dict):
                raise BreezeAPIError('Breeze returned an unreadable history entry; automatic speech retry stopped.')
            if record.get('text') != payload.get('text') or record.get('voice_id') != voice:
                continue
            stamp = record.get('date_unix')
            # Timestamps have second precision; allow modest server clock skew.
            if isinstance(stamp, (int, float)) and stamp < started - 30:
                continue
            history_id = str(record.get('history_item_id') or '')
            safe_id = history_id if re.fullmatch(r'[A-Za-z0-9_-]+', history_id) else '(unavailable)'
            raise BreezeAPIError(f'Breeze history contains a possible matching speech request ({safe_id}). Automatic retry stopped to avoid duplicates. Review its status/audio on Breeze before resuming.')
        if len(records) >= 100 or data.get('has_more'):
            raise BreezeAPIError('Breeze history search is incomplete; automatic speech retry stopped to avoid duplicates.')

    def catalog(self):
        # Catalog reads should not inherit long paid-generation timeouts/retries.
        models = self.request("GET", "/models", timeout=(5, 15)).json()
        voices = []
        for page in range(1, 101):
            data = self.request("GET", "/voices", timeout=(5, 15),
                                params={"voice_type": "personal", "page": page, "page_size": 100}).json()
            for item in data.get("voices", []):
                voices.append({**item, "short_name": item["voice_id"],
                               "display_name": item.get("name", item["voice_id"]),
                               "locale": item.get("language_code", ""),
                               "locale_name": item.get("language_code", "")})
            if not data.get("has_more"):
                break
        else:
            raise BreezeAPIError("Personal voice catalog exceeds 10,000 entries; enter a voice ID manually.")
        personal_count = len(voices)
        # The public catalog contains thousands of voices. Never download it all
        # just to configure an account; saved personal voices always come first.
        data = self.request("GET", "/voices", timeout=(5, 15),
                            params={"voice_type": "default", "page_size": 100}).json()
        seen = {v["voice_id"] for v in voices}
        for item in data.get("voices", []):
            if item["voice_id"] not in seen:
                voices.append({**item, "short_name": item["voice_id"],
                               "display_name": item.get("name", item["voice_id"]),
                               "locale": item.get("language_code", ""),
                               "locale_name": item.get("language_code", "")})
        return {"models": models, "voices": voices, "personal_count": personal_count,
                "public_count": len(voices) - personal_count,
                "public_has_more": bool(data.get("has_more"))}

    def _work_items(self, segments, voice_config):
        items = super()._work_items(segments, voice_config)
        for item in items:
            segment = segments[item["segment_index"]]
            direction = segment.get("delivery_instruction") or segment.get("emotion") or ""
            item['delivery_instruction'] = direction
            item['emotion'] = segment.get('emotion')
            item["assignment"] = replace(item["assignment"], extra={
                **item["assignment"].extra, "delivery_instruction": direction})
        return items

    @staticmethod
    def _notify(item, path, progress_cb, chunk_cb):
        if callable(progress_cb):
            progress_cb()
        if callable(chunk_cb):
            chunk_cb(item['order_index'], {key: item.get(key) for key in (
                'speaker', 'text', 'segment_index', 'chunk_index', 'order_index',
                'delivery_instruction', 'emotion')}, path)

    def _synthesize(self, text, assignment, *, fallback_speed=1.0):
        if not str(text or '').strip() or '[direction]' in text.lower():
            raise BreezeAPIError('Empty text or unparsed direction tags reached Breeze API; refusing generation.')
        extra = assignment.extra or {}
        if extra.get('breeze_production_id'):
            if self.productions is None:
                raise BreezeAPIError('Production voice storage is unavailable.')
            self.production_progress(extra['breeze_production_id'], 'Preparing production voice')
            voice_id = self.productions.resolve_voice(self, extra, self.production_progress)
            assignment = replace(assignment, voice=voice_id)
            self.production_progress(extra['breeze_production_id'], 'Synthesizing audio with production voices')
        voice = str(assignment.voice or self.default_voice).strip()
        if not voice or not re.fullmatch(r"[A-Za-z0-9_-]+", voice):
            raise BreezeAPIError("Select a local sample for a production, or a saved Breeze voice ID.")
        if "[direction]" in text.lower():
            raise BreezeAPIError("Unparsed direction tags reached Breeze API; refusing to speak instructions.")
        extra = assignment.extra or {}
        payload = {"text": text, "model_id": self.model_id,
                   "instructions": extra.get("delivery_instruction") or extra.get("instructions") or self.instructions,
                   "voice_settings": {"guidance_scale": self.guidance_scale}}
        language = str(assignment.lang_code or "").strip()
        if re.fullmatch(r"[a-zA-Z]{2}", language):
            payload["language_code"] = language.lower()
        response = self.request("POST", "/text-to-speech/" + quote(voice, safe=""),
                                retry=True, params={"output_format": "wav", "delivery": "sync"}, json=payload)
        wav = self._audio_converter(bytes(response.content), input_format="wav", sample_rate=24000, channels=1)
        fx = VoiceFXSettings.from_payload(assignment.fx_payload)
        speed = assignment.speed_override if assignment.speed_override is not None else fallback_speed
        fx = VoiceFXSettings(pitch_semitones=fx.pitch_semitones if fx else 0,
                             tone=fx.tone if fx else "neutral",
                             speed=fx.speed if fx else self._clamp(speed, 0.25, 4, 1))
        return apply_wav_effects(wav, fx)

    def clone_preview(self, path, name, language):
        if path.suffix.lower() not in (".wav", ".mp3") or path.stat().st_size > 5_000_000:
            raise BreezeAPIError("Choose a WAV/MP3 sample no larger than 5 MB.")
        from pydub import AudioSegment
        if len(AudioSegment.from_file(path)) < 3000:
            raise BreezeAPIError("Breeze requires at least 3 seconds of reference audio.")
        with path.open("rb") as stream:
            return self.request("POST", "/voice-previews/clone",
                                # requests uses the connect timeout during socket writes too.
                                # Give multipart audio uploads the full generation allowance.
                                timeout=(max(180, self.timeout), max(180, self.timeout)),
                                data={"name": name[:80], "language_code": language},
                                files={"files": (path.name, stream, "audio/wav" if path.suffix.lower() == ".wav" else "audio/mpeg")}).json()

    def save_preview(self, preview_id, name, language):
        return self.request("POST", "/voice-previews/" + quote(preview_id, safe="") + "/save",
                            json={"voice_name": name[:80], "language_code": language}).json()

    def delete_voice(self, voice_id):
        if not re.fullmatch(r'[A-Za-z0-9_-]+', str(voice_id)):
            raise BreezeAPIError('Invalid saved voice ID.')
        # A previously deleted tracked voice is already cleaned up.
        self.request('DELETE', '/voices/' + quote(voice_id, safe=''),
                     accepted_statuses=(200, 204, 404), timeout=(5, 30))
