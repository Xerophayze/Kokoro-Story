from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

import pytest

import app as app_module
from src.gemini_processor import GeminiProcessorError


PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def isolate_llm_profile_usage(monkeypatch, tmp_path):
    monkeypatch.setattr(
        app_module,
        "LLM_PROFILE_USAGE_FILE",
        tmp_path / "llm_profile_usage.json",
    )


def test_profile_chain_supports_multiple_models_and_api_keys_for_one_provider():
    profiles = app_module._resolve_llm_profile_chain({
        "llm_provider": "openrouter",
        "openrouter_model": "model/primary",
        "openrouter_api_key": "primary-key",
        "llm_backup_profiles": [
            {
                "id": "fast-backup",
                "name": "Fast Backup",
                "provider": "openrouter",
                "model": "model/fast",
                "api_key": "fast-key",
            },
            {
                "id": "quality-backup",
                "name": "Quality Backup",
                "provider": "openrouter",
                "model": "model/quality",
                "api_key": "quality-key",
            },
        ],
    })

    assert [(profile["provider"], profile["model"]) for profile in profiles] == [
        ("openrouter", "model/primary"),
        ("openrouter", "model/fast"),
        ("openrouter", "model/quality"),
    ]
    assert profiles[1]["api_key"] == "fast-key"
    assert profiles[2]["api_key"] == "quality-key"
    assert profiles[1]["daily_request_limit"] == 18


def test_retryable_primary_failure_uses_profile_model_and_key(monkeypatch):
    attempts = []

    def fake_run(prompt, config, provider, model_override=None, api_key_override=None, **_kwargs):
        attempts.append((provider, model_override, api_key_override))
        if len(attempts) == 1:
            raise GeminiProcessorError("Gemini API error: 429 RESOURCE_EXHAUSTED")
        return "prepared text"

    monkeypatch.setattr(app_module, "_run_llm_prompt_for_provider", fake_run)
    text, profile, failures = app_module._run_llm_prompt_with_failover(
        "prompt",
        {
            "llm_provider": "gemini",
            "gemini_model": "gemini-primary",
            "llm_backup_profiles": [{
                "id": "router-backup",
                "name": "Router Backup",
                "provider": "openrouter",
                "model": "vendor/backup",
                "api_key": "backup-key",
            }],
        },
    )

    assert text == "prepared text"
    assert profile == {
        "id": "router-backup",
        "name": "Router Backup",
        "provider": "openrouter",
        "model": "vendor/backup",
        "daily_request_limit": 18,
    }
    assert attempts == [
        ("gemini", "gemini-primary", ""),
        ("openrouter", "vendor/backup", "backup-key"),
    ]
    assert failures[0]["profile_id"] == "primary"
    assert "api_key" not in profile
    assert "api_key" not in failures[0]


def test_configuration_failure_does_not_silently_switch_profile(monkeypatch):
    attempts = []

    def fake_run(prompt, config, provider, model_override=None, api_key_override=None, **_kwargs):
        attempts.append(provider)
        raise GeminiProcessorError("Gemini API key not configured")

    monkeypatch.setattr(app_module, "_run_llm_prompt_for_provider", fake_run)

    with pytest.raises(GeminiProcessorError, match="not configured"):
        app_module._run_llm_prompt_with_failover(
            "prompt",
            {
                "llm_provider": "gemini",
                "llm_backup_profiles": [{
                    "provider": "openrouter",
                    "model": "vendor/backup",
                    "api_key": "backup-key",
                }],
            },
        )

    assert attempts == ["gemini"]


def test_preferred_profile_skips_earlier_failures_for_remaining_sections(monkeypatch):
    attempts = []

    def fake_run(prompt, config, provider, model_override=None, api_key_override=None, **_kwargs):
        attempts.append((provider, model_override))
        return "next section"

    monkeypatch.setattr(app_module, "_run_llm_prompt_for_provider", fake_run)
    text, profile, failures = app_module._run_llm_prompt_with_failover(
        "prompt",
        {
            "llm_provider": "gemini",
            "llm_backup_profiles": [
                {"id": "router-a", "provider": "openrouter", "model": "model/a"},
                {"id": "router-b", "provider": "openrouter", "model": "model/b"},
            ],
        },
        preferred_profile="router-a",
    )

    assert text == "next section"
    assert profile["id"] == "router-a"
    assert failures == []
    assert attempts == [("openrouter", "model/a")]


def test_high_demand_retries_current_profile_before_advancing(monkeypatch):
    attempts = []

    def fake_run(prompt, config, provider, model_override=None, api_key_override=None, **_kwargs):
        attempts.append((provider, model_override))
        raise GeminiProcessorError("Gemini API error: 503 model overloaded due to high demand")

    monkeypatch.setattr(app_module, "_run_llm_prompt_for_provider", fake_run)

    with pytest.raises(app_module.LLMProfileRetryError) as raised:
        app_module._run_llm_prompt_with_failover(
            "prompt",
            {
                "llm_provider": "gemini",
                "gemini_model": "gemini-primary",
                "llm_backup_profiles": [{
                    "id": "gemini-backup",
                    "provider": "gemini",
                    "model": "gemini-backup",
                    "api_key": "backup-key",
                }],
            },
            defer_transient_failover=True,
        )

    assert attempts == [("gemini", "gemini-primary")]
    assert raised.value.current_profile["id"] == "primary"
    assert raised.value.next_profile["id"] == "gemini-backup"


def test_explicit_quota_exhaustion_advances_without_same_profile_retry(monkeypatch):
    attempts = []

    def fake_run(prompt, config, provider, model_override=None, api_key_override=None, **_kwargs):
        attempts.append((provider, model_override))
        if model_override == "gemini-primary":
            raise GeminiProcessorError("429 RESOURCE_EXHAUSTED: quota exceeded; please try again later")
        return "prepared by backup"

    monkeypatch.setattr(app_module, "_run_llm_prompt_for_provider", fake_run)
    text, profile, failures = app_module._run_llm_prompt_with_failover(
        "prompt",
        {
            "llm_provider": "gemini",
            "gemini_model": "gemini-primary",
            "llm_backup_profiles": [{
                "id": "gemini-backup",
                "provider": "gemini",
                "model": "gemini-backup",
                "api_key": "backup-key",
                "daily_request_limit": 0,
            }],
        },
        defer_transient_failover=True,
    )

    assert text == "prepared by backup"
    assert profile["id"] == "gemini-backup"
    assert attempts == [("gemini", "gemini-primary"), ("gemini", "gemini-backup")]
    assert failures[0]["failure_kind"] == "advance_profile"


def test_explicit_quota_exhaustion_without_backup_is_not_retried(monkeypatch):
    def fake_run(*_args, **_kwargs):
        raise GeminiProcessorError("429 RESOURCE_EXHAUSTED: quota exceeded")

    monkeypatch.setattr(app_module, "_run_llm_prompt_for_provider", fake_run)

    with pytest.raises(app_module.LLMProviderChainError) as raised:
        app_module._run_llm_prompt_with_failover(
            "prompt",
            {"llm_provider": "gemini", "gemini_model": "gemini-primary"},
            defer_transient_failover=True,
        )

    assert raised.value.retryable is False


def test_daily_profile_limit_skips_to_next_backup_and_stores_no_key(monkeypatch, tmp_path):
    usage_file = tmp_path / "llm_profile_usage.json"
    monkeypatch.setattr(app_module, "LLM_PROFILE_USAGE_FILE", usage_file)
    attempts = []

    def fake_run(prompt, config, provider, model_override=None, api_key_override=None, **_kwargs):
        attempts.append((model_override, api_key_override))
        if model_override == "gemini-primary":
            raise GeminiProcessorError("429 RESOURCE_EXHAUSTED: quota exceeded")
        return f"prepared by {model_override}"

    monkeypatch.setattr(app_module, "_run_llm_prompt_for_provider", fake_run)
    config = {
        "llm_provider": "gemini",
        "gemini_model": "gemini-primary",
        "llm_backup_profiles": [
            {
                "id": "limited-key",
                "name": "Limited Key",
                "provider": "gemini",
                "model": "gemini-limited",
                "api_key": "limited-secret",
                "daily_request_limit": 1,
            },
            {
                "id": "unlimited-key",
                "name": "Unlimited Key",
                "provider": "gemini",
                "model": "gemini-unlimited",
                "api_key": "unlimited-secret",
                "daily_request_limit": 0,
            },
        ],
    }

    first_text, first_profile, _ = app_module._run_llm_prompt_with_failover("one", config)
    second_text, second_profile, second_failures = app_module._run_llm_prompt_with_failover("two", config)

    assert first_text == "prepared by gemini-limited"
    assert first_profile["id"] == "limited-key"
    assert second_text == "prepared by gemini-unlimited"
    assert second_profile["id"] == "unlimited-key"
    assert any(item.get("failure_kind") == "daily_limit" for item in second_failures)
    usage_text = usage_file.read_text(encoding="utf-8")
    assert "limited-secret" not in usage_text
    assert "unlimited-secret" not in usage_text
    assert attempts == [
        ("gemini-primary", ""),
        ("gemini-limited", "limited-secret"),
        ("gemini-primary", ""),
        ("gemini-unlimited", "unlimited-secret"),
    ]


def test_daily_limit_day_changes_at_midnight_pacific():
    before_midnight = datetime(2026, 8, 8, 6, 59, tzinfo=timezone.utc)
    at_midnight = datetime(2026, 8, 8, 7, 0, tzinfo=timezone.utc)

    assert app_module._llm_usage_day_key(before_midnight) == "2026-08-07"
    assert app_module._llm_usage_day_key(at_midnight) == "2026-08-08"


def test_process_section_exposes_safe_retry_and_next_profile_metadata(monkeypatch):
    monkeypatch.setattr(
        app_module,
        "load_config",
        lambda: {"llm_provider": "local", "gemini_prompt": "Prepare faithfully."},
    )
    current = {
        "id": "busy-profile",
        "name": "Busy Profile",
        "provider": "gemini",
        "model": "gemini-test",
        "api_key": "never-return-this-key",
        "daily_request_limit": 18,
    }
    next_profile = {
        "id": "next-profile",
        "name": "Next Profile",
        "provider": "openrouter",
        "model": "router-test",
        "api_key": "never-return-this-key-either",
        "daily_request_limit": 18,
    }

    def fake_run(*_args, **_kwargs):
        raise app_module.LLMProfileRetryError(
            "503 overloaded due to high demand",
            current_profile=current,
            next_profile=next_profile,
            failures=[],
        )

    monkeypatch.setattr(app_module, "_run_llm_prompt_with_failover", fake_run)
    response = app_module.app.test_client().post(
        "/api/gemini/process-section",
        json={"content": "A short section."},
    )

    assert response.status_code == 503
    payload = response.get_json()
    assert payload["retryable"] is True
    assert payload["retry_profile"]["id"] == "busy-profile"
    assert payload["next_profile"]["id"] == "next-profile"
    assert "api_key" not in payload["retry_profile"]
    assert "api_key" not in payload["next_profile"]


def test_job_snapshot_redacts_backup_profile_api_keys():
    snapshot = app_module._redact_config_secrets({
        "openrouter_api_key": "primary-secret",
        "llm_backup_profiles": [{
            "id": "router-backup",
            "provider": "openrouter",
            "model": "model/backup",
            "api_key": "backup-secret",
        }],
    })

    assert snapshot["openrouter_api_key"] == ""
    assert snapshot["llm_backup_profiles"][0]["api_key"] == ""


def test_frontend_builds_dynamic_profiles_and_resumes_active_profile():
    main_source = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    settings_source = (PROJECT_ROOT / "static" / "js" / "settings.js").read_text(encoding="utf-8")
    template = (PROJECT_ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    assert "active_profile: activeProfile || ''" in main_source
    assert "payload.preferred_profile = activeProfile" in main_source
    assert "llm_backup_profiles" in settings_source
    assert "data-profile-field=\"model\"" in settings_source
    assert "data-profile-field=\"api_key\"" in settings_source
    assert "data-profile-field=\"daily_request_limit\"" in settings_source
    assert "sectionData.next_profile" in main_source
    assert "payload.preferred_profile = nextProfile.id" in main_source
    assert 'id="llm-backup-profile-count"' in template
    assert 'id="llm-backup-profiles-list"' in template
