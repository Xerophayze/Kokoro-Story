from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_cloud_jobs_have_a_separate_bounded_dispatch_path():
    source = read("app.py")

    assert 'cloud_job_executor = ThreadPoolExecutor(max_workers=4' in source
    assert '"edge_tts",' in source
    assert '"azure_speech",' in source
    assert '"elevenlabs",' in source
    assert '"openai_tts",' in source
    assert "def _cloud_job_limit" in source
    assert 'cloud_tts_concurrent_jobs", 2' in source
    assert 'cloud_job_executor.submit(_run_queued_job, job_data, cloud_slot=True)' in source
    assert '"current_jobs": sorted(current_job_ids)' in source


def test_resume_keeps_prior_files_and_offsets_new_cloud_chunk_names():
    source = read("app.py")

    assert "resume_prefix_files" in source
    assert 'engine_kwargs["start_index"] = 0' in source
    assert 'render_dir = output_dir / f".tts-render-{uuid.uuid4().hex}"' in source
    assert "return resume_prefix_files + list(audio_files or [])" in source
    assert 'if increment == 0 and pause_flags.get(job_id, False):' in source
    assert source.index("register_chunk(", source.index("def chunk_cb(")) < source.index(
        "update_progress(0)", source.index("def chunk_cb(")
    )
    assert "job_entry['status'] = 'interrupted' if processed_chunks > 0 else 'failed'" in source
    assert 'resumable_statuses.add("failed")' in source


def test_chunk_checkpoint_write_failure_does_not_abort_audio_generation():
    source = read("app.py")
    start = source.index("def _persist_chunks_metadata")
    end = source.index("def _load_chunks_metadata", start)
    checkpoint_writer = source[start:end]

    assert "write_json_atomic(chunks_meta_path, chunks_meta)" in checkpoint_writer
    assert "except OSError as exc:" in checkpoint_writer
    assert "generation will continue" in checkpoint_writer
    assert "return False" in checkpoint_writer


def test_cloud_concurrency_and_edge_retry_controls_are_persisted_in_settings():
    template = read("templates/index.html")
    settings = read("static/js/settings.js")

    for element_id in (
        "cloud-tts-concurrent-jobs",
        "azure-speech-max-parallel",
        "edge-tts-max-parallel",
        "edge-tts-max-retries",
    ):
        assert f'id="{element_id}"' in template
        assert element_id in settings


def test_cloud_provider_controls_are_grouped_with_their_engines():
    template = read("templates/index.html")
    settings = read("static/js/settings.js")
    app = read("app.py")

    assert 'data-engine-tab="cloud-concurrency"' not in template
    assert 'data-engine-tab="api-keys"' not in template
    assert 'data-engine-tab="kokoro-replicate"' in template

    kokoro_start = template.index('id="engine-panel-kokoro-replicate"')
    azure_start = template.index('id="engine-panel-azure-speech"', kokoro_start)
    kokoro_panel = template[kokoro_start:azure_start]
    assert 'id="kokoro-replicate-api-key"' in kokoro_panel
    assert 'id="kokoro-replicate-max-parallel"' in kokoro_panel

    chatterbox_start = template.index('id="engine-panel-chatterbox-replicate"')
    voxcpm_start = template.index('id="engine-panel-voxcpm"', chatterbox_start)
    chatterbox_panel = template[chatterbox_start:voxcpm_start]
    assert 'id="chatterbox-replicate-api-key"' in chatterbox_panel
    assert 'id="chatterbox-replicate-max-parallel"' in chatterbox_panel

    assert "settings.replicate_max_parallel ?? settings.parallel_chunks" in settings
    assert '"kokoro_replicate": "replicate_max_parallel"' in app
    assert '"edge_tts": "edge_tts_max_parallel"' in app
