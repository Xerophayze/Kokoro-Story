import ctypes as ct
from types import SimpleNamespace

import numpy as np
import pytest
import soundfile as sf

from src.engines import breeze_q8 as q8
from src.engines import breeze_tts_2_engine as adapter


def test_native_request_preserves_direction_transcript_and_reference(monkeypatch, tmp_path):
    reference = tmp_path / 'voice.wav'
    sf.write(reference, np.full((1600, 2), 0.25, dtype=np.float32), 16000)
    seen = []
    runtime = q8.Q8Runtime.__new__(q8.Q8Runtime)
    runtime.context = 123
    runtime.sample_rate = 24000
    def generate(context, pointer, callback, user):
        req = ct.cast(pointer, ct.POINTER(q8.Request)).contents
        assert context == 123
        seen.append((req.text, req.instruction, req.ref_text, req.ref_audio_len, req.seed))
        assert req.split_chars == -1
        assert np.allclose(np.ctypeslib.as_array(req.ref_audio, shape=(req.ref_audio_len,))[20:-20], 0.25, atol=.002)
        samples = (ct.c_float * 3)(0.1, 0.2, 0.3)
        assert callback(samples, 3, None) == 0
        samples[0] = 9  # callback must copy the transient buffer
        return 0
    runtime.lib = SimpleNamespace(breeze_generate=generate)
    audio = runtime.generate('Hello.', 'Speak gently.', str(reference), 'Exact words.', 4, 0, 1500)
    assert seen == [(b'Hello.', b'Speak gently.', b'Exact words.', 2400, 0)]
    assert np.allclose(audio, [.1, .2, .3])


@pytest.mark.parametrize('result', [0, 1])
def test_native_failure_or_empty_audio_is_not_saved_as_success(result):
    runtime = q8.Q8Runtime.__new__(q8.Q8Runtime)
    runtime.context, runtime.sample_rate = 123, 24000
    runtime.lib = SimpleNamespace(breeze_generate=lambda *a: result, breeze_last_error=lambda: b'native failed')
    with pytest.raises(RuntimeError, match='native failed|no audio'):
        runtime.generate('Hello.', 'Calm.', None, '', 1, 42, 1500)


def test_q8_batch_and_preview_share_runtime_without_pytorch(monkeypatch, tmp_path):
    marker = tmp_path / '.license_accepted'
    marker.touch()
    monkeypatch.setattr(adapter, 'LICENSE_MARKER', marker)
    monkeypatch.setattr(adapter, 'BREEZE_TTS_2_AVAILABLE', False)
    monkeypatch.setattr(adapter, 'torch', None)
    calls, closed = [], []
    class Runtime:
        sample_rate = 24000
        def __init__(self, **kwargs): pass
        def generate(self, *args):
            calls.append(args)
            return np.zeros(2400, dtype=np.float32)
        def close(self): closed.append(True)
    monkeypatch.setattr(q8, 'Q8Runtime', Runtime)
    engine = adapter.BreezeTTS2Engine(runtime='q8', seed=19)
    engine.generate_audio('Preview.', voice_design_prompt='FEMALE, warm alto.', seed=31)
    paths = engine.generate_batch(
        [{'speaker': 'lea', 'chunks': ['Hello.'], 'delivery_instruction': 'Speak urgently.'}],
        {}, tmp_path / 'chunks',
    )
    assert len(paths) == 1
    assert calls[0][1] == 'FEMALE, warm alto.'
    assert calls[0][5] == 31
    assert calls[1][1] == 'Speak urgently.'
    engine.cleanup()
    assert closed == [True]


def test_runtime_setting_is_preserved_and_changes_engine_cache_key():
    import app
    normalized = app._normalize_breeze_tts_2_options({'breeze_tts_2_runtime': 'q8'})
    assert normalized == {'breeze_tts_2_runtime': 'q8'}
    original = app._engine_signature('breeze_tts_2', {'breeze_tts_2_runtime': 'pytorch'})
    assert original != app._engine_signature('breeze_tts_2', normalized)
    assert app._normalize_breeze_tts_2_options({'breeze_tts_2_runtime': ['bad']}) == {'breeze_tts_2_runtime': 'pytorch'}


def test_runtime_availability_requires_model_library_and_marker(monkeypatch, tmp_path):
    from src.engines import isolated_proxy as proxy
    monkeypatch.setattr(proxy, 'isolated_engine_available', lambda _: True)
    monkeypatch.setattr(proxy, 'engine_root', lambda _: tmp_path)
    assert not proxy.breeze_runtime_available('q8')
    (tmp_path / '.q8_ready').touch()
    (tmp_path / 'models').mkdir()
    (tmp_path / 'models/breeze-tts-2-q8_0.gguf').touch()
    assert not proxy.breeze_runtime_available('q8')
    (tmp_path / 'q8/bin').mkdir(parents=True)
    (tmp_path / 'q8/bin/breeze.dll').touch()
    assert proxy.breeze_runtime_available('q8')
    assert not proxy.breeze_runtime_available('pytorch')


def test_q8_download_validates_checksum_and_reuses_file(monkeypatch, tmp_path):
    import hashlib
    import requests
    from scripts import install_breeze_q8 as installer
    content = b'GGUF-test-fixture'
    monkeypatch.setattr(installer, 'MODEL_SIZE', len(content))
    monkeypatch.setattr(installer, 'MODEL_SHA256', hashlib.sha256(content).hexdigest())
    calls = []
    class Response:
        status_code = 200
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_content(self, size): return iter([content[:4], content[4:]])
    def get(*args, **kwargs):
        calls.append(kwargs)
        return Response()
    monkeypatch.setattr(requests, 'get', get)
    installer.download_model(tmp_path)
    installer.download_model(tmp_path)
    assert (tmp_path / installer.MODEL_NAME).read_bytes() == content
    assert len(calls) == 1
    assert calls[0]['timeout'] == (20, 60)


def test_q8_download_rejects_wrong_checksum(monkeypatch, tmp_path):
    import requests
    from scripts import install_breeze_q8 as installer
    monkeypatch.setattr(installer, 'MODEL_SIZE', 4)
    monkeypatch.setattr(installer, 'MODEL_SHA256', '0' * 64)
    class Response:
        status_code = 200
        headers = {}
        def __enter__(self): return self
        def __exit__(self, *args): pass
        def raise_for_status(self): pass
        def iter_content(self, size): return iter([b'nope'])
    monkeypatch.setattr(requests, 'get', lambda *args, **kwargs: Response())
    with pytest.raises(RuntimeError, match='checksum'):
        installer.download_model(tmp_path)
    assert not (tmp_path / installer.MODEL_NAME).exists()
