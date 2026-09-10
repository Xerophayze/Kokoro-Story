import io
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import numpy as np
import pytest
import requests
import soundfile as sf

from src.engines.breeze_api_engine import BreezeAPIEngine, BreezeAPIError
from src.engines.base import VoiceAssignment


def wav():
    out = io.BytesIO()
    sf.write(out, np.zeros(24000 * 3), 24000, format="WAV")
    return out.getvalue()


def response(payload=None, status=200):
    return SimpleNamespace(status_code=status, content=wav(), headers={}, json=lambda: payload)


def test_synthesis_uses_hosted_contract_and_directions():
    request = Mock(return_value=response())
    engine = BreezeAPIEngine("test-key", request_func=request)
    items = engine._work_items([{"speaker": "alice", "chunks": ["Hello."],
                                 "emotion": "Speak warmly."}],
                               {"alice": {"voice": "voc_alice", "lang_code": "en"}})
    result = engine._synthesize(items[0]["text"], items[0]["assignment"])
    assert result.startswith(b"RIFF")
    args, kwargs = request.call_args
    assert args == ("POST", "https://api.breeze.blue/v1/text-to-speech/voc_alice")
    assert kwargs["headers"]["xi-api-key"] == "test-key"
    assert kwargs["json"] == {"text": "Hello.", "model_id": "breeze-tts-2",
                              "instructions": "Speak warmly.", "language_code": "en",
                              "voice_settings": {"guidance_scale": 4.0}}
    assert kwargs["allow_redirects"] is False


def test_batch_voices_and_resume_file_offsets(tmp_path):
    request = Mock(return_value=response())
    engine = BreezeAPIEngine("test-key", request_func=request)
    result = engine.generate_batch(
        [{"speaker": "a", "chunks": ["One."]}, {"speaker": "b", "chunks": ["Two."]}],
        {"a": {"voice": "voc_a"}, "b": {"voice": "voc_b"}}, tmp_path, start_index=7)
    assert len(result) == 2
    assert "000007" in result[0] and "000008" in result[1]
    assert [call.args[1].rsplit("/", 1)[1] for call in request.call_args_list] == ["voc_a", "voc_b"]


@pytest.mark.parametrize("status", [401, 402, 403, 422])
def test_permanent_errors_are_not_retried(status):
    request = Mock(return_value=response(status=status))
    engine = BreezeAPIEngine("test-key", request_func=request)
    with pytest.raises(BreezeAPIError):
        engine.request("POST", "/test", retry=True)
    assert request.call_count == 1


def test_transient_retry_and_no_ambiguous_timeout_retry():
    request = Mock(side_effect=[response(status=429), response()])
    sleep = Mock()
    engine = BreezeAPIEngine("test-key", request_func=request, sleep_func=sleep)
    engine.request("POST", "/test", retry=True)
    assert request.call_count == 2 and sleep.call_count == 1
    request.side_effect = requests.Timeout("private details")
    request.reset_mock()
    with pytest.raises(BreezeAPIError, match="history"):
        engine.request("POST", "/test", retry=True)
    assert request.call_count == 1


def test_clone_and_save_are_separate_no_transcript_needed(tmp_path):
    sample = tmp_path / "sample.wav"
    sample.write_bytes(wav())
    request = Mock(side_effect=[response({"generated_voice_id": "gvi_test"}), response({"voice_id": "voc_test"})])
    engine = BreezeAPIEngine("test-key", request_func=request)
    assert engine.clone_preview(sample, "Alice", "en")["generated_voice_id"] == "gvi_test"
    assert request.call_count == 1
    engine.save_preview("gvi_test", "Alice", "en")
    assert request.call_args.kwargs["json"] == {"voice_name": "Alice", "language_code": "en"}
    assert request.call_args_list[0].kwargs['timeout'] == (180, 180)


def test_upload_timeout_is_specific_and_never_retried(tmp_path):
    sample = tmp_path / 'sample.wav'
    sample.write_bytes(wav())
    request = Mock(side_effect=requests.ConnectionError('write timed out'))
    engine = BreezeAPIEngine('test-key', timeout=240, request_func=request)
    with pytest.raises(BreezeAPIError, match='voice-sample upload'):
        engine.clone_preview(sample, 'Alice', 'en')
    assert request.call_count == 1
    assert request.call_args.kwargs['timeout'] == (240, 240)


def test_disconnected_speech_checks_history_before_retry():
    request = Mock(side_effect=[requests.ConnectionError('remote closed'),
        response({'history': []}), response()])
    sleep = Mock()
    engine = BreezeAPIEngine('test-key', request_func=request, sleep_func=sleep)
    engine.request('POST', '/text-to-speech/voc_a', retry=True,
                   json={'text': 'Hello.', 'model_id': 'breeze-tts-2'})
    assert [call.args[0] for call in request.call_args_list] == ['POST', 'GET', 'POST']
    assert request.call_args_list[1].args[1].endswith('/history')
    assert request.call_args_list[2].kwargs['json']['text'] == 'Hello.'
    sleep.assert_called_once_with(5)


@pytest.mark.parametrize('history', [
    {'history': [{'text': 'Hello.', 'voice_id': 'voc_a', 'history_item_id': 'h_accepted'}]},
    {'unexpected': []},
    {'history': [], 'has_more': True},
])
def test_uncertain_history_never_retries_speech(history):
    request = Mock(side_effect=[requests.ConnectionError('remote closed'), response(history)])
    engine = BreezeAPIEngine('test-key', request_func=request, sleep_func=Mock())
    with pytest.raises(BreezeAPIError, match='retry stopped'):
        engine.request('POST', '/text-to-speech/voc_a', retry=True, json={'text': 'Hello.'})
    assert request.call_count == 2


def test_zero_retries_and_exhaustion_are_bounded():
    for retries in (0, 2):
        request = Mock(side_effect=sum(([requests.Timeout('lost'), response({'history': []})]
                                      for _ in range(retries + 1)), []))
        engine = BreezeAPIEngine('test-key', max_retries=retries,
                                request_func=request, sleep_func=Mock())
        with pytest.raises(BreezeAPIError, match='configured retries'):
            engine.request('POST', '/text-to-speech/voc_a', retry=True, json={'text': 'Hello.'})
        assert request.call_count == 2 * (retries + 1)


def test_history_connection_failure_does_not_retry_paid_request():
    request = Mock(side_effect=requests.ConnectionError('lost'))
    engine = BreezeAPIEngine('test-key', request_func=request, sleep_func=Mock())
    with pytest.raises(BreezeAPIError, match='history could not be checked'):
        engine.request('POST', '/text-to-speech/voc_a', retry=True, json={'text': 'Hello.'})
    assert request.call_count == 2


def test_invalid_voice_and_raw_direction_rejected():
    engine = BreezeAPIEngine("test-key", request_func=Mock())
    with pytest.raises(BreezeAPIError):
        engine._synthesize("Hello", VoiceAssignment(voice="sample.wav"))
    with pytest.raises(BreezeAPIError):
        engine._synthesize("[direction]Quiet[/direction]Hello", VoiceAssignment(voice="voc_test"))


def test_catalog_pagination():
    request = Mock(side_effect=[response([{"model_id": "breeze-tts-2"}]),
                               response({"voices": [{"voice_id": "voc_a", "name": "Alice"}], "has_more": True}),
                               response({"voices": [{"voice_id": "voc_b", "name": "Bob"}], "has_more": False}),
                               response({"voices": [{"voice_id": "voc_public", "name": "Public"}], "has_more": True, "total": 8632})])
    data = BreezeAPIEngine("test-key", request_func=request).catalog()
    assert [v["short_name"] for v in data["voices"]] == ["voc_a", "voc_b", "voc_public"]
    assert data["personal_count"] == 2
    assert data["public_has_more"] is True
    assert request.call_count == 4  # Never fetch all 8,632 public voices.
    assert request.call_args_list[1].kwargs["params"]["voice_type"] == "personal"
    assert request.call_args.kwargs["params"]["voice_type"] == "default"
    assert all(c.kwargs["timeout"] == (5, 15) for c in request.call_args_list)


def test_catalog_does_not_wait_through_generation_retries():
    request = Mock(return_value=response(status=429))
    sleep = Mock()
    with pytest.raises(BreezeAPIError, match="429"):
        BreezeAPIEngine("test-key", request_func=request, sleep_func=sleep).catalog()
    assert request.call_count == 1
    sleep.assert_not_called()


def test_secret_is_registered_and_ui_is_separate():
    from scripts.check_repo_safety import SECRET_CONFIG_KEYS
    assert "breeze_api_key" in SECRET_CONFIG_KEYS
    root = Path(__file__).resolve().parents[1]
    template = (root / "templates/index.html").read_text(encoding="utf-8")
    assert template.count('<option value="breeze_api">') == 3
    assert 'id="engine-panel-breeze-api"' in template


def test_backend_factory_catalog_and_secret_masking(monkeypatch):
    import app as application
    config = {**application.DEFAULT_CONFIG, "breeze_api_key": "test-key"}
    engine = application._create_engine("breeze_api", config)
    assert isinstance(engine, BreezeAPIEngine)
    assert "test-key" not in application._engine_signature("breeze_api", config)
    assert "breeze_api_key" in application.SECRET_CONFIG_KEYS
    monkeypatch.setattr(application, "load_config", lambda: config)
    monkeypatch.setattr(BreezeAPIEngine, "catalog", lambda self: {"models": [], "voices": []})
    with application.app.test_client() as client:
        result = client.get('/api/breeze-api/catalog')
    assert result.status_code == 200 and result.json["success"]


def test_backend_upload_consent_traversal_and_approval(monkeypatch, tmp_path):
    import app as application
    root = tmp_path / "voices"
    root.mkdir()
    (root / "test.wav").write_bytes(wav())
    (tmp_path / "outside.wav").write_bytes(wav())
    monkeypatch.setattr(application, "VOICE_PROMPT_DIR", root)
    fake = Mock()
    fake.clone_preview.return_value = {"generated_voice_id": "gvi_test"}
    fake.save_preview.return_value = {"voice_id": "voc_test"}
    fake.request.return_value = response()
    monkeypatch.setattr(application, "_create_engine", lambda *args: fake)
    monkeypatch.setattr(application, "load_config", lambda: {})
    with application.app.test_client() as client:
        assert client.post('/api/breeze-api/clone', json={"file_name": "test.wav"}).status_code == 400
        assert client.post('/api/breeze-api/clone', json={"file_name": "../outside.wav", "consent": True}).status_code == 400
        assert not fake.clone_preview.called
        result = client.post('/api/breeze-api/clone', json={"file_name": "test.wav", "consent": True})
        assert result.json["generated_voice_id"] == "gvi_test"
        assert not fake.save_preview.called
        audio = client.get('/api/breeze-api/preview/gvi_test')
        assert audio.status_code == 200 and audio.data.startswith(b"RIFF")
        saved = client.post('/api/breeze-api/save-voice', json={"preview_id": "gvi_test", "name": "Alice", "language": "en"})
        assert saved.json["voice_id"] == "voc_test"


def test_directed_text_processor_keeps_instruction_out_of_speech():
    import app as application
    processor = application._create_text_processor_for_engine("breeze_api", 500, {})
    segments = processor.process_text('[direction]Speak gently.[/direction]\n[alice]Hello there.[/alice]')
    # Same parser contract as the local directed engine; no model invocation.
    assert "direction" not in str([s.get("chunks") for s in segments])
    assert any(s.get("emotion") == "Speak gently." for s in segments)
