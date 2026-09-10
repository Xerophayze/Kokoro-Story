from pathlib import Path
from types import SimpleNamespace

import app as app_module
from src.job_timing import JobTiming


def test_timing_does_not_replay_prior_chunks_or_count_pause_time():
    now = [100.0]
    first = JobTiming(clock=lambda: now[0])
    now[0] += 10
    first.complete()
    now[0] += 20
    first.complete()
    saved = first.snapshot()
    now[0] += 3600  # pause
    resumed = JobTiming(saved, 2, clock=lambda: now[0])
    assert resumed.snapshot()["chunk_times"] == [10, 20]
    assert resumed.snapshot()["total_seconds"] == 30
    assert resumed.snapshot()["session_chunk_count"] == 0
    now[0] += 5
    resumed.complete()
    assert resumed.eta(10) == 50
    final = resumed.snapshot(finished=True)
    assert final["chunk_times"] == [10, 20, 5]
    assert final["total_seconds"] == 35
    assert final["chunk_count"] == 3
    again = JobTiming(final, 3, clock=lambda: now[0])
    now[0] += 7
    again.complete()
    assert again.snapshot()["chunk_times"] == [10, 20, 5, 7]
    assert again.snapshot()["total_seconds"] == 42


def test_two_resumes_preserve_files_order_and_metadata_across_chapters(monkeypatch, tmp_path):
    job_id = "resume-integrity"
    rendered = []
    manifests = []
    sections = [{"title": "Title", "content": "a|b"},
                {"title": "Chapter 1", "content": "c|d|e|f"}]
    class Engine:
        sample_rate = 24000
        device = "test"
        def generate_batch(self, segments, voice_config, output_dir, speed=1,
                           progress_cb=None, chunk_cb=None):
            files = []
            order = 0
            for si, segment in enumerate(segments):
                for ci, text in enumerate(segment["chunks"]):
                    path = Path(output_dir) / f"chunk_{order:06d}.wav"
                    path.write_bytes(text.encode())
                    rendered.append(text)
                    if len(rendered) in {3, 5}:
                        app_module.pause_flags[job_id] = True
                    progress_cb()
                    chunk_cb(ci, {"segment_index": si, "chunk_index": ci, "order_index": order}, str(path))
                    files.append(str(path))
                    order += 1
            return files
    monkeypatch.setattr(app_module, "OUTPUT_DIR", tmp_path)
    monkeypatch.setattr(app_module, "jobs", {})
    monkeypatch.setattr(app_module, "pause_flags", {})
    monkeypatch.setattr(app_module, "cancel_flags", {})
    monkeypatch.setattr(app_module, "cancel_events", {})
    monkeypatch.setattr(app_module, "_persist_job_state", lambda *a, **k: None)
    monkeypatch.setattr(app_module, "_create_text_processor_for_engine", lambda *a: SimpleNamespace(
        process_text=lambda text: [{"speaker": "narrator", "chunks": text.split("|")}]))
    monkeypatch.setattr(app_module, "split_text_into_book_sections", lambda *a: {"sections": sections})
    monkeypatch.setattr(app_module, "get_tts_engine", lambda *a, **k: Engine())
    def merge(_id, entry, manifest):
        manifests.append(manifest)
        entry["status"] = "completed"
    monkeypatch.setattr(app_module, "_merge_review_job", merge)
    config = {**app_module.DEFAULT_CONFIG, "tts_engine": "breeze_tts_2"}
    data = {"job_id": job_id, "text": "test", "config": config, "voice_assignments": {},
            "total_chunks": 6, "review_mode": True, "split_by_chapter": True,
            "generate_full_story": True}
    entry = {"status": "processing", "total_chunks": 6, "config_snapshot": config}
    app_module.jobs[job_id] = entry
    preserved = {}
    for expected in [3, 5, 6]:
        data["resume_from_chunk_index"] = entry.get("resume_from_chunk_index", 0)
        entry["status"] = "processing"
        app_module._process_audio_job(data)
        assert entry["processed_chunks"] == expected
        assert len(entry["chunks"]) == expected
        for path, content in preserved.items():
            assert Path(path).read_bytes() == content
        preserved = {c["file_path"]: Path(c["file_path"]).read_bytes() for c in entry["chunks"]}
        assert len(preserved) == expected
    assert rendered == list("abcdef")
    assert entry["status"] == "completed"
    assert [c["text"] for c in entry["chunks"]] == list("abcdef")
    assert len(set(c["id"] for c in entry["chunks"])) == 6
    assert len(manifests[-1]["all_full_story_chunks"]) == 6
