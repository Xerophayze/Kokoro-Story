from __future__ import annotations

from pathlib import Path

import app as app_module
from scripts import install_engine as engine_manager
from src.engines.omnivoice_clone_engine import _check_omnivoice_available


ROOT = Path(__file__).resolve().parents[1]


def test_core_requirements_exclude_optional_tts_runtimes():
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").lower()
    for optional_package in (
        "kokoro", "chatterbox-tts", "voxcpm", "qwen-tts", "pocket-tts",
        "kittentts", "edge-tts", "torch", "funasr",
    ):
        assert optional_package not in requirements
    assert (ROOT / "requirements-engines" / "qwen3.txt").is_file()
    assert (ROOT / "scripts" / "install_engine.py").is_file()


def test_chatterbox_uses_an_isolated_runtime():
    manager = (ROOT / "scripts" / "install_engine.py").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements-engines" / "chatterbox_turbo_local.txt").read_text(
        encoding="utf-8"
    )
    adapter = (ROOT / "src" / "engines" / "chatterbox_turbo_local_engine.py").read_text(
        encoding="utf-8"
    )

    assert 'engine_dir = ROOT / "engines" / "chatterbox"' in manager
    assert '"chatterbox_turbo_local": "chatterbox_turbo_local.txt"' not in manager
    assert "transformers==4.57.3" not in requirements
    assert "CHATTERBOX_READY_MARKER" in adapter
    assert (ROOT / "engines" / "chatterbox" / "chatterbox_worker.py").is_file()


def test_setup_scripts_use_core_only_install_and_first_run_marker():
    windows = (ROOT / "setup.bat").read_text(encoding="utf-8")
    unix = (ROOT / "setup.sh").read_text(encoding="utf-8")

    assert 'set "CORE_ONLY=1"' in windows
    assert 'type nul > ".first_run_pending"' in windows
    assert 'CORE_ONLY=1' in unix
    assert 'touch .first_run_pending' in unix
    assert "Optional TTS engines are installed from Settings" in windows
    assert "Optional TTS engines are installed from Settings" in unix


def test_engine_catalog_reports_install_and_configuration_actions(monkeypatch):
    config = dict(app_module.DEFAULT_CONFIG)
    config.update({
        "azure_speech_key": "",
        "azure_speech_region": "",
        "localai_tts_model": "local-model",
    })
    real_available = app_module.isolated_engine_available
    monkeypatch.setattr(
        app_module,
        "isolated_engine_available",
        lambda engine: False if engine == "kokoro" else real_available(engine),
    )
    catalog = {entry["id"]: entry for entry in app_module._engine_setup_catalog(config)}

    assert catalog["kokoro"]["action"] == "install"
    assert catalog["kokoro"]["install_target"] == "kokoro"
    assert catalog["kokoro"]["uninstall_target"] is None
    assert catalog["azure_speech"]["action"] == "configure"
    assert catalog["localai_tts"]["ready"] is True


def test_ready_local_engine_reports_safe_uninstall(monkeypatch):
    real_available = app_module.isolated_engine_available
    monkeypatch.setattr(
        app_module,
        "isolated_engine_available",
        lambda engine: True if engine == "kokoro" else real_available(engine),
    )
    catalog = {entry["id"]: entry for entry in app_module._engine_setup_catalog(dict(app_module.DEFAULT_CONFIG))}

    assert catalog["kokoro"]["uninstall_target"] == "kokoro"
    assert "Shared TTS dependencies" in catalog["kokoro"]["uninstall_warning"]
    assert catalog["azure_speech"]["uninstall_target"] is None


def test_isolated_engine_removal_preserves_adapter(tmp_path, monkeypatch):
    monkeypatch.setattr(engine_manager, "ROOT", tmp_path)
    engine_dir = tmp_path / "engines" / "omnivoice"
    (engine_dir / ".venv").mkdir(parents=True)
    (engine_dir / ".venv" / "runtime.bin").write_bytes(b"runtime")
    (engine_dir / "omnivoice_worker.py").write_text("# adapter", encoding="utf-8")
    (engine_dir / "requirements.txt").write_text("omnivoice", encoding="utf-8")
    (engine_dir / ".omnivoice_ready").touch()

    engine_manager.remove_isolated_runtime("omnivoice")

    assert (engine_dir / "omnivoice_worker.py").is_file()
    assert (engine_dir / "requirements.txt").is_file()
    assert not (engine_dir / ".venv").exists()
    assert not (engine_dir / ".omnivoice_ready").exists()


def test_omnivoice_install_state_is_checked_live(tmp_path):
    engine_dir = tmp_path / "omnivoice"
    worker = engine_dir / "omnivoice_worker.py"
    python = engine_dir / ".venv" / "Scripts" / "python.exe"
    python.parent.mkdir(parents=True)
    worker.write_text("# worker", encoding="utf-8")
    python.touch()

    available, reason = _check_omnivoice_available(engine_dir)
    assert available is False
    assert "installation marker" in reason

    (engine_dir / ".omnivoice_ready").touch()
    available, reason = _check_omnivoice_available(engine_dir)
    assert available is True
    assert reason == ""

    (engine_dir / ".omnivoice_ready").unlink()
    available, _ = _check_omnivoice_available(engine_dir)
    assert available is False


def test_omnivoice_worker_supports_numpy_and_torch_audio():
    worker = (ROOT / "engines" / "omnivoice" / "omnivoice_worker.py").read_text(
        encoding="utf-8"
    )
    assert "torch.is_tensor(audio)" in worker
    assert "np.array(audio, copy=True)" in worker
    assert "np.concatenate([silence, processed, silence], axis=-1)" in worker


def test_engine_first_run_notice_is_once_per_engine_and_resets_after_install(tmp_path, monkeypatch):
    state_file = tmp_path / "engine-first-run.json"
    monkeypatch.setattr(app_module, "ENGINE_FIRST_RUN_NOTICE_FILE", state_file)

    assert app_module._consume_engine_first_run_notice("pocket_tts") is True
    assert app_module._consume_engine_first_run_notice("pocket_tts") is False
    assert app_module._consume_engine_first_run_notice("pocket_tts_preset") is True

    app_module._reset_engine_first_run_notice("pocket_tts")

    assert app_module._consume_engine_first_run_notice("pocket_tts") is True
    assert app_module._consume_engine_first_run_notice("pocket_tts_preset") is True


def test_onboarding_marker_is_dismissed(tmp_path, monkeypatch):
    marker = tmp_path / ".first_run_pending"
    marker.touch()
    monkeypatch.setattr(app_module, "FIRST_RUN_MARKER", marker)
    client = app_module.app.test_client()

    assert client.get("/api/onboarding").get_json()["show_welcome"] is True
    assert client.post("/api/onboarding").get_json()["show_welcome"] is False
    assert not marker.exists()


def test_engine_install_endpoint_is_local_only_by_default():
    client = app_module.app.test_client()
    response = client.post(
        "/api/engines/install",
        json={"engine": "kokoro"},
        environ_base={"REMOTE_ADDR": "192.0.2.20"},
    )
    assert response.status_code == 403

    response = client.post(
        "/api/engines/uninstall",
        json={"engine": "kokoro"},
        environ_base={"REMOTE_ADDR": "192.0.2.20"},
    )
    assert response.status_code == 403


def test_remote_engine_management_requires_matching_admin_token(monkeypatch):
    config = dict(app_module.DEFAULT_CONFIG)
    config.update({
        "remote_engine_management_enabled": True,
        "remote_engine_management_token": "correct-private-token",
    })
    monkeypatch.setattr(app_module, "load_config", lambda: dict(config))

    with app_module.app.test_request_context(
        "/api/engines/uninstall",
        method="POST",
        environ_base={"REMOTE_ADDR": "192.0.2.20"},
    ):
        assert app_module._engine_management_request_allowed() is False

    with app_module.app.test_request_context(
        "/api/engines/uninstall",
        method="POST",
        headers={"X-TTS-Story-Admin-Token": "correct-private-token"},
        environ_base={"REMOTE_ADDR": "192.0.2.20"},
    ):
        assert app_module._engine_management_request_allowed() is True


def test_settings_api_never_returns_remote_admin_token(monkeypatch):
    config = dict(app_module.DEFAULT_CONFIG)
    config["remote_engine_management_token"] = "do-not-return-this"
    monkeypatch.setattr(app_module, "load_config", lambda: dict(config))
    response = app_module.app.test_client().get("/api/settings")
    assert response.status_code == 200
    assert response.get_json()["settings"]["remote_engine_management_token"] == ""

def test_frontend_has_engine_manager_and_first_run_welcome():
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "static" / "js" / "settings.js").read_text(encoding="utf-8")

    assert 'id="first-run-welcome-overlay"' in template
    assert 'id="engine-first-run-overlay"' in template
    assert 'id="engine-first-run-ok"' in template
    assert 'id="local-engine-tabs-label"' in template
    assert 'id="remote-engine-tabs-label"' in template
    assert template.index('data-engine-tab="omnivoice"') < template.index('id="remote-engine-tabs-label"')
    assert template.index('id="remote-engine-tabs-label"') < template.index('data-engine-tab="azure-speech"')
    assert '/static/js/settings.js?v=' in template
    assert "async function loadEngineSetupStatus()" in javascript
    assert "async function startEngineInstall(" in javascript
    assert "async function startEngineUninstall(" in javascript
    assert "/api/engines/uninstall" in javascript
    assert "uninstall_warning" in javascript
    assert "function filterEngineSelectors()" in javascript
    assert "engine-status-ready" in javascript
    assert "engine-status-missing" in javascript
    assert "await loadEngineSetupStatus();" in javascript
    assert "installedEntries.every(entry => entry.ready)" in javascript
    assert "async function restoreActiveEngineManagementJob()" in javascript
    assert "fetch('/api/engines/jobs')" in javascript
    assert "setEngineManagementBusy(activeJob, true)" in javascript
    assert "async function restartTtsStoryBackend(button)" in javascript
    assert "/api/system/restart" in javascript
    assert 'id="remote-engine-management-enabled"' in template
    assert 'id="remote-engine-management-token"' in template
    assert "X-TTS-Story-Admin-Token" in javascript
    assert "instance_id !== previousInstance" in javascript
    main_javascript = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    assert "function showEngineFirstRunNotice(engineName)" in main_javascript
    assert "if (data.first_run_notice)" in main_javascript


def test_engine_management_jobs_are_discoverable_after_refresh(monkeypatch):
    job_id = "active-engine-job"
    monkeypatch.setattr(app_module, "ENGINE_INSTALL_JOBS", {
        job_id: {
            "id": job_id,
            "engine": "pocket_tts",
            "action": "install",
            "status": "running",
            "output": "Downloading runtime...",
            "started_at": "2026-08-17T18:00:00",
            "log_path": "private/path.log",
        }
    })

    response = app_module.app.test_client().get("/api/engines/jobs")
    assert response.status_code == 200
    payload = response.get_json()
    assert payload["jobs"][0]["id"] == job_id
    assert payload["jobs"][0]["status"] == "running"
    assert payload["jobs"][0]["output"] == "Downloading runtime..."
    assert "log_path" not in payload["jobs"][0]


def test_run_scripts_supervise_backend_restarts():
    windows = (ROOT / "run.bat").read_text(encoding="utf-8")
    unix = (ROOT / "run.sh").read_text(encoding="utf-8")

    assert 'set "TTS_STORY_RESTARTABLE=1"' in windows
    assert 'if "!SERVER_EXIT_CODE!"=="75"' in windows
    assert "export TTS_STORY_RESTARTABLE=1" in unix
    assert 'if [ "$SERVER_EXIT_CODE" -eq 75 ]' in unix


def test_backend_restart_endpoint_requires_local_supervised_launch(monkeypatch):
    client = app_module.app.test_client()
    remote = client.post(
        "/api/system/restart",
        environ_base={"REMOTE_ADDR": "192.0.2.20"},
    )
    assert remote.status_code == 403

    monkeypatch.delenv("TTS_STORY_RESTARTABLE", raising=False)
    local = client.post("/api/system/restart")
    assert local.status_code == 409
    assert "run.bat or run.sh" in local.get_json()["error"]

    status = client.get("/api/system/status")
    assert status.status_code == 200
    assert status.get_json()["instance_id"] == app_module.SERVER_INSTANCE_ID


def test_backend_restart_endpoint_schedules_supervisor_exit(monkeypatch):
    scheduled = []

    class FakeTimer:
        def __init__(self, interval, callback):
            self.interval = interval
            self.callback = callback

        def start(self):
            scheduled.append((self.interval, self.callback))

    monkeypatch.setenv("TTS_STORY_RESTARTABLE", "1")
    monkeypatch.setattr(app_module.threading, "Timer", FakeTimer)
    monkeypatch.setattr(app_module, "ENGINE_INSTALL_JOBS", {})
    monkeypatch.setattr(app_module, "current_job_ids", set())
    monkeypatch.setattr(app_module, "current_job_id", None)

    response = app_module.app.test_client().post("/api/system/restart")
    assert response.status_code == 202
    assert response.get_json()["instance_id"] == app_module.SERVER_INSTANCE_ID
    assert scheduled == [(0.5, app_module._exit_for_supervised_restart)]


def test_pocket_tts_exposes_gated_model_authentication_controls(monkeypatch):
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    javascript = (ROOT / "static" / "js" / "settings.js").read_text(encoding="utf-8")
    proxy = (ROOT / "src" / "engines" / "isolated_proxy.py").read_text(encoding="utf-8")

    assert 'id="pocket-tts-huggingface-token"' in template
    assert 'id="pocket-tts-verify-huggingface-btn"' in template
    assert "https://huggingface.co/kyutai/pocket-tts" in template
    assert "https://huggingface.co/settings/tokens" in template
    assert "/api/pocket-tts/huggingface-access" in javascript
    assert "huggingface_token" in app_module.SECRET_CONFIG_KEYS
    assert 'environment={"HF_TOKEN"' in Path(ROOT / "app.py").read_text(encoding="utf-8")
    assert "process_environment.update(self.environment)" in proxy

    monkeypatch.setattr(app_module, "load_config", lambda: {"huggingface_token": ""})
    response = app_module.app.test_client().post(
        "/api/pocket-tts/huggingface-access",
        json={"token": ""},
    )
    assert response.status_code == 400
