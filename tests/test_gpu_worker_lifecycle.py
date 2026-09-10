import io
import json
import sys
import threading
from types import SimpleNamespace

import pytest

import app as app_module
from engines import isolated_engine_worker as worker
from src.engines import isolated_proxy as proxy_module


def test_narration_waits_for_casting_then_releases_workers(monkeypatch):
    stopped = []
    qwen, breeze = object(), object()
    import src.process_lifecycle as lifecycle
    monkeypatch.setattr(lifecycle, "stop_owned_worker", stopped.append)
    monkeypatch.setattr(app_module, "qwen3_voice_design_process", qwen)
    monkeypatch.setattr(app_module, "breeze_voice_design_process", breeze)
    monkeypatch.setattr(app_module, "qwen3_voice_design_log_handle", io.StringIO())
    monkeypatch.setattr(app_module, "breeze_voice_design_log_handle", io.StringIO())
    monkeypatch.setattr(app_module, "qwen3_voice_design_model", object())
    monkeypatch.setattr(app_module, "qwen3_voice_design_signature", "old")
    lock = threading.RLock()
    monkeypatch.setattr(app_module, "gpu_generation_lifecycle_lock", lock)
    entered, finished = threading.Event(), threading.Event()
    def narration(_job):
        assert stopped == [qwen, breeze]
        assert app_module.qwen3_voice_design_model is None
        entered.set()
    monkeypatch.setattr(app_module, "_process_audio_job", narration)
    def run():
        app_module.process_audio_job({"job_id": "test", "config": {"tts_engine": "breeze_tts_2"}})
        finished.set()
    with lock:
        thread = threading.Thread(target=run)
        thread.start()
        assert not entered.wait(0.1)
        assert stopped == []
    thread.join(timeout=5)
    assert finished.is_set()
    assert app_module.qwen3_voice_design_process is None
    assert app_module.breeze_voice_design_process is None


def test_cloud_job_does_not_release_another_jobs_gpu(monkeypatch):
    monkeypatch.setattr(app_module, "_release_voice_design_memory", lambda: pytest.fail("GPU cleanup for cloud job"))
    monkeypatch.setattr(app_module, "_process_audio_job", lambda _job: "done")
    assert app_module.process_audio_job({"config": {"tts_engine": "edge_tts"}}) == "done"


def test_persistent_worker_reuses_model_for_two_chapters(monkeypatch, tmp_path):
    counts = {"loads": 0, "batches": 0, "cleanups": 0}
    class Engine:
        def __init__(self, **_kwargs):
            counts["loads"] += 1
        def generate_batch(self, **_kwargs):
            counts["batches"] += 1
            return []
        def cleanup(self):
            counts["cleanups"] += 1
    job = tmp_path / "job.json"
    job.write_text(json.dumps({"engine": "breeze_tts_2", "operation": "batch", "output_dir": str(tmp_path)}))
    request = json.dumps({"job_file": str(job)}) + "\n"
    monkeypatch.setattr(worker, "engine_class", lambda _name: Engine)
    monkeypatch.setattr(worker.sys, "stdin", io.StringIO(request * 2))
    events = []
    monkeypatch.setattr(worker, "emit", events.append)
    assert worker.serve("breeze_tts_2") == 0
    assert counts == {"loads": 1, "batches": 2, "cleanups": 1}
    assert len([e for e in events if e["event"] == "complete"]) == 2


def test_proxy_reuses_process_and_stops_on_callback_cancellation(monkeypatch, tmp_path):
    # A real subprocess exercises the pipe protocol without loading any models.
    script = tmp_path / "worker.py"
    script.write_text('''import sys, json
for line in sys.stdin:
    request = json.loads(line)
    with open(request["job_file"], encoding="utf-8") as handle:
        job = json.load(handle)
    print('TTS_STORY_EVENT ' + json.dumps({"event":"progress"}), flush=True)
    print('TTS_STORY_EVENT ' + json.dumps({"event":"complete", "files":[]}), flush=True)
''')
    monkeypatch.setattr(proxy_module, "WORKER", script)
    monkeypatch.setattr(proxy_module, "isolated_engine_available", lambda _name: True)
    monkeypatch.setattr(proxy_module, "engine_python", lambda _name: sys.executable)
    proxy = proxy_module.IsolatedEngineProxy("breeze_tts_2")
    try:
        assert proxy.generate_batch([], {}, tmp_path) == []
        process = proxy._process
        assert proxy.generate_batch([], {}, tmp_path) == []
        assert proxy._process is process
        def cancel():
            raise RuntimeError("paused")
        with pytest.raises(RuntimeError, match="paused"):
            proxy.generate_batch([], {}, tmp_path, progress_cb=cancel)
        assert proxy._process is None
        assert process.poll() is not None
        proxy.generate_batch([], {}, tmp_path)
        replacement = proxy._process
        assert replacement is not process
    finally:
        proxy.cleanup()
    assert replacement.poll() is not None
