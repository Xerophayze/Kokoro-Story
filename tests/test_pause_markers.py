from __future__ import annotations

import wave
from pathlib import Path

import pytest

import app as app_module
from src.pause_markers import pause_seconds_for_text, sanitize_display_title, write_silence_wav
from src.text_processor import TextProcessor


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_three_star_groups_become_ordered_standalone_chunks():
    chunks = TextProcessor(chunk_size=100).chunk_text(
        "First sentence.\n\n***\n\nSecond sentence.\n******\nThird sentence."
    )

    assert chunks == [
        "First sentence.",
        "***",
        "Second sentence.",
        "******",
        "Third sentence.",
    ]


def test_inline_pause_markers_after_periods_become_ordered_chunks():
    chunks = TextProcessor(chunk_size=100).chunk_text(
        "The man could not see.*** Then he heard a sound.****** Afterward, he ran."
    )

    assert chunks == [
        "The man could not see.",
        "***",
        "Then he heard a sound.",
        "******",
        "Afterward, he ran.",
    ]


def test_inline_pause_marker_inside_speaker_tag_is_preserved():
    segments = TextProcessor(chunk_size=100).process_text(
        "[narrator]Chapter 1.****** The man could not see.*** He waited.[/narrator]"
    )

    assert [chunk for segment in segments for chunk in segment["chunks"]] == [
        "Chapter 1.",
        "******",
        "The man could not see.",
        "***",
        "He waited.",
    ]


def test_pause_marker_attached_to_tagged_heading_is_preserved():
    segments = TextProcessor(chunk_size=100).process_text(
        "[narrator]SOLAR BOND******[/narrator]\n"
        "[narrator]Written by Eric Thorup using AI***[/narrator]"
    )

    assert [chunk for segment in segments for chunk in segment["chunks"]] == [
        "SOLAR BOND",
        "******",
        "Written by Eric Thorup using AI",
        "***",
    ]


def test_invalid_attached_star_count_is_not_treated_as_pause():
    segments = TextProcessor(chunk_size=100).process_text(
        "[narrator]A heading****[/narrator]"
    )

    assert [chunk for segment in segments for chunk in segment["chunks"]] == [
        "A heading****",
    ]


def test_pause_marker_between_speaker_tags_is_not_discarded():
    segments = TextProcessor(chunk_size=100).process_text(
        "[narrator]First sentence.[/narrator]\n***\n"
        "[alice]Second sentence.[/alice]"
    )

    assert [chunk for segment in segments for chunk in segment["chunks"]] == [
        "First sentence.",
        "***",
        "Second sentence.",
    ]


def test_pause_marker_duration_uses_default_values():
    assert pause_seconds_for_text("***") == 0.25
    assert pause_seconds_for_text("******") == 0.5
    assert pause_seconds_for_text("*********") == 0.75
    assert pause_seconds_for_text("**") is None
    assert pause_seconds_for_text("This is *** emphasis.") is None


def test_pause_marker_duration_uses_independent_configured_values():
    assert pause_seconds_for_text("***", 0.4, 1.25) == pytest.approx(0.4)
    assert pause_seconds_for_text("******", 0.4, 1.25) == pytest.approx(1.25)
    assert pause_seconds_for_text("*********", 0.4, 1.25) == pytest.approx(1.65)
    assert pause_seconds_for_text("************", 0.4, 1.25) == pytest.approx(2.5)
    assert pause_seconds_for_text("***", 0, 0) == 0


def test_markdown_style_closing_asterisks_are_not_pause_markers():
    chunks = TextProcessor(chunk_size=100).chunk_text("This is important***")

    assert chunks == ["This is important***"]


def test_display_title_removes_only_trailing_recognized_pause_groups():
    assert sanitize_display_title("Chapter 1.******") == "Chapter 1."
    assert sanitize_display_title("The Preface.  ***  ") == "The Preface."
    assert sanitize_display_title("Stars *** inside a title") == "Stars *** inside a title"
    assert sanitize_display_title("Chapter 1.**") == "Chapter 1.**"


def test_silence_wav_has_requested_duration(tmp_path):
    destination = write_silence_wav(tmp_path / "pause.wav", 1.0, sample_rate=16000)

    with wave.open(str(destination), "rb") as wav_file:
        assert wav_file.getframerate() == 16000
        assert wav_file.getnchannels() == 1
        assert wav_file.getnframes() / wav_file.getframerate() == pytest.approx(1.0)


def test_audio_job_filters_pause_markers_before_calling_any_tts_engine():
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    start = source.index("def generate_chunks(")
    end = source.index("def _prebuild_subprocess_engine_all_chapters", start)
    generation = source[start:end]

    assert "pause_seconds_for_text(" in generation
    assert 'config.get("pause_marker_three_seconds", 0.25)' in generation
    assert 'config.get("pause_marker_six_seconds", 0.5)' in generation
    assert '"segments": render_segments' in generation
    assert "write_silence_wav(" in generation
    assert "commit_pauses_before" in generation


def _install_review_chunk_job(monkeypatch, tmp_path, job_id: str, text: str) -> Path:
    job_dir = tmp_path / job_id
    target = job_dir / "chunks" / "chunk.wav"
    monkeypatch.setattr(app_module, "OUTPUT_DIR", tmp_path)
    with app_module.queue_lock:
        app_module.jobs[job_id] = {
            "review_mode": True,
            "job_dir": str(job_dir),
            "chunks": [{
                "id": "chunk-1",
                "speaker": "narrator",
                "text": text,
                "relative_file": "chunks/chunk.wav",
                "voice_assignment": {},
            }],
            "config_snapshot": {
                "tts_engine": "omnivoice_clone",
                "speed": 1.0,
                "sample_rate": 24000,
            },
            "voice_assignments": {},
            "word_replacements": [],
        }
    return target


def test_pause_only_chunk_regeneration_does_not_call_tts(monkeypatch, tmp_path):
    job_id = "pause-only-regen"
    target = _install_review_chunk_job(monkeypatch, tmp_path, job_id, "***")
    monkeypatch.setattr(
        app_module,
        "get_tts_engine",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("TTS must not render silence")),
    )
    monkeypatch.setattr(app_module, "_persist_chunks_metadata", lambda *args, **kwargs: True)

    try:
        app_module._perform_chunk_regeneration(job_id, "chunk-1", "***")
    finally:
        with app_module.queue_lock:
            app_module.jobs.pop(job_id, None)

    with wave.open(str(target), "rb") as wav_file:
        duration = wav_file.getnframes() / wav_file.getframerate()
    assert duration == pytest.approx(0.25, abs=0.01)


def test_pause_only_chunk_regeneration_uses_saved_marker_duration(monkeypatch, tmp_path):
    job_id = "configured-pause-only-regen"
    target = _install_review_chunk_job(monkeypatch, tmp_path, job_id, "******")
    with app_module.queue_lock:
        app_module.jobs[job_id]["config_snapshot"].update({
            "pause_marker_three_seconds": 0.4,
            "pause_marker_six_seconds": 1.2,
        })
    monkeypatch.setattr(
        app_module,
        "get_tts_engine",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("TTS must not render silence")),
    )
    monkeypatch.setattr(app_module, "_persist_chunks_metadata", lambda *args, **kwargs: True)

    try:
        app_module._perform_chunk_regeneration(job_id, "chunk-1", "******")
    finally:
        with app_module.queue_lock:
            app_module.jobs.pop(job_id, None)

    with wave.open(str(target), "rb") as wav_file:
        duration = wav_file.getnframes() / wav_file.getframerate()
    assert duration == pytest.approx(1.2, abs=0.01)


def test_attached_pause_regeneration_separates_speech_and_silence(monkeypatch, tmp_path):
    job_id = "attached-pause-regen"
    target = _install_review_chunk_job(monkeypatch, tmp_path, job_id, "SOLAR BOND******")
    captured_chunks = []

    class FakeEngine:
        def generate_batch(self, *, segments, output_dir, **kwargs):
            captured_chunks.extend(segments[0]["chunks"])
            spoken = Path(output_dir) / "spoken.wav"
            write_silence_wav(spoken, 0.1, sample_rate=24000)
            return [str(spoken)]

    monkeypatch.setattr(app_module, "get_tts_engine", lambda *args, **kwargs: FakeEngine())
    monkeypatch.setattr(app_module, "_persist_chunks_metadata", lambda *args, **kwargs: True)

    try:
        app_module._perform_chunk_regeneration(
            job_id,
            "chunk-1",
            "SOLAR BOND******",
        )
    finally:
        with app_module.queue_lock:
            app_module.jobs.pop(job_id, None)

    assert captured_chunks == ["SOLAR BOND"]
    with wave.open(str(target), "rb") as wav_file:
        duration = wav_file.getnframes() / wav_file.getframerate()
    assert duration == pytest.approx(0.6, abs=0.02)
