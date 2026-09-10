from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import numpy as np

import app as app_module
from scripts import install_engine
from src.engines import breeze_tts_2_engine as breeze_module
from src.engines.breeze_tts_2_engine import BreezeTTS2Engine
from src.engines.isolated_proxy import ENGINE_DIRS, SAMPLE_RATES
from src.text_processor import TextProcessor


ROOT = Path(__file__).resolve().parents[1]


def test_breeze_is_isolated_and_uses_official_pins():
    assert install_engine.ISOLATED_ENGINES["breeze_tts_2"] == "breeze_tts_2.txt"
    assert ENGINE_DIRS["breeze_tts_2"] == "breeze_tts_2"
    assert SAMPLE_RATES["breeze_tts_2"] == 24000
    requirements = (ROOT / "requirements-engines" / "breeze_tts_2.txt").read_text(
        encoding="utf-8"
    )
    assert "qwen-tts==0.1.1" in requirements
    assert "transformers==4.57.3" in requirements


def test_breeze_catalog_requires_install_and_license(monkeypatch):
    real_available = app_module.isolated_engine_available
    monkeypatch.setattr(
        app_module,
        "isolated_engine_available",
        lambda engine: False if engine == "breeze_tts_2" else real_available(engine),
    )
    catalog = {
        entry["id"]: entry
        for entry in app_module._engine_setup_catalog(dict(app_module.DEFAULT_CONFIG))
    }
    assert catalog["breeze_tts_2"]["install_target"] == "breeze_tts_2"
    assert catalog["breeze_tts_2"]["settings_tab"] == "breeze-tts-2"
    assert catalog["breeze_tts_2"]["action"] == "install"


def test_breeze_install_endpoint_rejects_missing_license_acceptance():
    response = app_module.app.test_client().post(
        "/api/engines/install",
        json={"engine": "breeze_tts_2"},
    )
    assert response.status_code == 400
    assert "Non-Commercial License" in response.get_json()["error"]


def test_direction_tag_is_attached_to_following_speaker_and_chunk():
    processor = TextProcessor(
        chunk_strategy="characters",
        char_soft_limit=120,
        char_hard_limit=180,
    )
    processed = processor.process_text(
        "[direction]Speak slowly with restrained fear.[/direction]"
        "[mara-female]There is someone beyond the gate.[/mara-female]"
    )
    assert processed[0]["speaker"] == "mara-female"
    assert processed[0]["emotion"] == "Speak slowly with restrained fear."
    assert processed[0]["delivery_instruction"] == "Speak slowly with restrained fear."
    assert processed[0]["chunks"] == ["There is someone beyond the gate."]


def test_legacy_emotion_tag_remains_direction_compatible():
    segment = TextProcessor().process_text(
        "[emotion]calm and reassuring[/emotion][narrator]It is safe now.[/narrator]"
    )[0]
    assert segment["emotion"] == "calm and reassuring"
    assert segment["delivery_instruction"] == "calm and reassuring"


def test_breeze_reads_voice_library_transcript_key(tmp_path):
    voice = tmp_path / "voice.wav"
    voice.write_bytes(b"RIFF-test-audio")
    stat = voice.stat()
    key = hashlib.md5(f"{voice.name}:{stat.st_size}:{stat.st_mtime}".encode()).hexdigest()[:16]
    engine = BreezeTTS2Engine.__new__(BreezeTTS2Engine)
    engine._transcripts = {key: "Exact reference words."}
    assert engine._transcript_for(voice) == "Exact reference words."


def test_breeze_frontend_and_help_expose_license_and_controls():
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    settings = (ROOT / "static" / "js" / "settings.js").read_text(encoding="utf-8")
    main = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    manifest = json.loads((ROOT / "docs" / "help" / "manifest.json").read_text(encoding="utf-8"))

    assert 'value="breeze_tts_2"' in template
    assert 'id="engine-panel-breeze-tts-2"' in template
    assert 'id="breeze-tts-2-license-accept"' in template
    assert "license_accepted: licenseAccepted" in settings
    assert "voice_design_prompt: profile?.voice_design_prompt" in main
    assert any(entry.get("id") == "engine-breeze-tts-2" for entry in manifest["articles"])
    assert (ROOT / "docs" / "help" / "engines" / "breeze-tts-2.md").is_file()


def test_breeze_voice_design_is_available_across_casting_surfaces():
    template = (ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    main = (ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    manager = (ROOT / "static" / "js" / "voice-manager.js").read_text(encoding="utf-8")
    backend = (ROOT / "app.py").read_text(encoding="utf-8")

    assert 'id="speaker-batch-design-engine"' in template
    assert 'id="voice-creation-breeze-btn"' in template
    assert 'data-role="speaker-voice-design-engine"' in main
    assert "generateAndSaveVoiceCandidates(speaker, displayName, statusEl, engineOverride" in main
    assert "engineConfig.previewUrl" in manager
    assert "engineConfig.saveUrl" in manager
    assert "'/api/breeze/voice-design/preview'" in backend
    assert "'/api/breeze/voice-design/save'" in backend
    assert "breeze_voice_design_available" in backend


def test_breeze_casting_uses_candidate_seed_without_reloading_worker(monkeypatch):
    captured = {}

    def fake_worker(request):
        captured.update(request)
        sample_rate = 24000
        duration = 12
        timeline = np.arange(sample_rate * duration, dtype=np.float32) / sample_rate
        audio = 0.05 * np.sin(2 * np.pi * 220 * timeline)
        app_module.sf.write(request["output_path"], audio, sample_rate)
        return {"sample_rate": sample_rate, "elapsed_seconds": 0.1}

    monkeypatch.setattr(app_module, "_run_isolated_breeze_voice_design", fake_worker)
    monkeypatch.setattr(app_module, "_apply_voice_design_cleanup", lambda audio, _rate: audio)
    result = app_module._generate_breeze_voice_design_preview(
        {
            "text": "This preview has enough expressive language to demonstrate a complete and consistent voice.",
            "gender": "Female",
            "required_gender": True,
            "voice_type": "warm alto, thoughtful pace, clear standard American accent",
            "voice_design_prompt": "warm alto, thoughtful pace, clear standard American accent",
            "language": "English",
            "seed": 987654,
        },
        {"breeze_tts_2_seed": 42},
    )

    assert captured["seed"] == 987654
    assert captured["constructor"]["seed"] == 42
    assert captured["instruct"].startswith("ADULT FEMALE VOICE.")
    assert result["engine"] == "breeze_tts_2_voice_design"
    assert result["duration_seconds"] >= 10


def test_breeze_loader_falls_back_when_flash_attention_is_absent(monkeypatch, tmp_path):
    captured = {}
    config = SimpleNamespace(text_encoder_config=SimpleNamespace(
        preferred_attn_implementation="flash_attention_2",
        _attn_implementation="flash_attention_2",
    ))

    class FakeConfigClass:
        @staticmethod
        def from_pretrained(_path):
            return config

    class FakeModel:
        config_class = FakeConfigClass

        @classmethod
        def from_pretrained(cls, _path, **kwargs):
            captured.update(kwargs)
            return cls()

        def to(self, _device):
            return self

        def eval(self):
            return self

    class FakeTokenizer:
        @staticmethod
        def from_pretrained(path, **kwargs):
            return (str(path), kwargs)

    model_path = tmp_path / "model"
    (model_path / "audio_tokenizer").mkdir(parents=True)
    monkeypatch.setattr(breeze_module.importlib.util, "find_spec", lambda _name: None)
    monkeypatch.setattr(breeze_module, "BreezeForConditionalGeneration", FakeModel)
    monkeypatch.setattr(breeze_module, "AutoTokenizer", FakeTokenizer)
    monkeypatch.setattr(breeze_module, "Qwen3TTSTokenizer", FakeTokenizer)
    monkeypatch.setattr(breeze_module, "torch", SimpleNamespace(bfloat16="bf16"))

    engine = BreezeTTS2Engine.__new__(BreezeTTS2Engine)
    engine.device = "cuda:0"
    engine._load_runtime(model_path)

    assert config.text_encoder_config.preferred_attn_implementation == "eager"
    assert config.text_encoder_config._attn_implementation == "eager"
    assert captured["attn_implementation"] == "eager"
