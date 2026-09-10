from __future__ import annotations

from pathlib import Path

from src.library_metadata import can_reuse_active_review_job


PROJECT_ROOT = Path(__file__).resolve().parents[1]
APP_SOURCE = PROJECT_ROOT / "app.py"
LIBRARY_SCRIPT = PROJECT_ROOT / "static" / "js" / "library.js"
INDEX_TEMPLATE = PROJECT_ROOT / "templates" / "index.html"


def test_active_library_review_job_is_reused_without_losing_regen_tasks(tmp_path):
    job_dir = tmp_path / "audio" / "job-123"
    job = {
        "review_mode": True,
        "job_dir": str(job_dir),
        "chunks": [{"id": "chunk-1"}],
        "regen_tasks": {
            "chunk-1": {"status": "running"},
            "chunk-2": {"status": "queued"},
        },
    }

    assert can_reuse_active_review_job(job, job_dir)
    assert job["regen_tasks"]["chunk-1"]["status"] == "running"
    assert job["regen_tasks"]["chunk-2"]["status"] == "queued"


def test_incomplete_or_different_review_jobs_are_not_reused(tmp_path):
    job_dir = tmp_path / "audio" / "job-123"

    assert not can_reuse_active_review_job(None, job_dir)
    assert not can_reuse_active_review_job({"review_mode": False, "chunks": [{}]}, job_dir)
    assert not can_reuse_active_review_job(
        {"review_mode": True, "job_dir": job_dir, "chunks": []},
        job_dir,
    )
    assert not can_reuse_active_review_job(
        {
            "review_mode": True,
            "job_dir": job_dir,
            "chunks": [{"id": "one"}],
            "regen_tasks": {"one": {"status": "completed"}},
        },
        job_dir,
    )
    assert not can_reuse_active_review_job(
        {
            "review_mode": True,
            "job_dir": job_dir,
            "chunks": [{"id": "one"}],
            "regen_tasks": {"one": {"status": "queued"}},
        },
        tmp_path / "audio" / "different-job",
    )


def test_restore_route_reuses_existing_state_before_reinitializing_job():
    source = APP_SOURCE.read_text(encoding="utf-8")
    route_start = source.index("def restore_library_item_to_review(job_id):")
    route_end = source.index(
        "@app.route('/api/library/<job_id>/chunks'",
        route_start,
    )
    route = source[route_start:route_end]

    reuse_check = route.index("can_reuse_active_review_job(existing_job, job_dir)")
    replacement = route.index("jobs[job_id] = {")
    assert reuse_check < replacement
    assert '"already_restored": True' in route
    assert '"has_active_regen": _has_active_regen_tasks(existing_job)' in route


def test_bulk_regeneration_restores_once_and_preserves_speaker_task_state():
    source = LIBRARY_SCRIPT.read_text(encoding="utf-8")
    start = source.index("function wireBatchRebuildEvents")
    end = source.index("function wireChapterRebuildEvents", start)
    batch_handler = source[start:end]

    assert batch_handler.count("requestLibraryReviewRestore(jobId)") == 1
    assert "{ skipRestore: true }" in batch_handler
    assert "if (!queued)" in batch_handler


def test_library_watcher_does_not_guess_completion_or_expire_slow_qwen_jobs():
    source = LIBRARY_SCRIPT.read_text(encoding="utf-8")

    assert "status || 'completed'" not in source
    assert "LIBRARY_CHUNK_MAX_ATTEMPTS" not in source
    assert "initialRegeneratedAt" in source
    assert "chunk.regenerated_at !== entry.initialRegeneratedAt" in source
    assert "LIBRARY_CHUNK_MAX_ERROR_BACKOFF_MS" in source


def test_recompile_button_is_wired_and_uses_server_regen_state():
    source = LIBRARY_SCRIPT.read_text(encoding="utf-8")

    assert "recompileBtn.addEventListener('click', recompileLibraryAudio)" in source
    assert "async function recompileLibraryAudio()" in source
    assert "reviewPayload.review?.has_active_regen" in source
    assert "fetch(`/api/jobs/${jobId}/review/finish`" in source


def test_bulk_regeneration_displays_server_backed_progress_and_eta():
    source = LIBRARY_SCRIPT.read_text(encoding="utf-8")

    assert 'id="library-regen-progress"' in source
    assert "function startLibraryBulkRegenWatcher" in source
    assert "function pollLibraryBulkRegenStatus" in source
    assert "payload.regen_tasks || {}" in source
    assert "task.started_at && task.completed_at" in source
    assert "About ${formatLibraryRegenDuration(averageSeconds * remaining)} remaining" in source
    assert "${counts.completed} updated" in source
    assert "${counts.running} rendering" in source
    assert "${counts.queued} queued" in source
    assert "${counts.failed} failed" in source


def test_bulk_regeneration_uses_one_aggregate_watcher_and_cleans_it_up():
    source = LIBRARY_SCRIPT.read_text(encoding="utf-8")
    batch_start = source.index("function wireBatchRebuildEvents")
    batch_end = source.index("function wireChapterRebuildEvents", batch_start)
    batch_handler = source[batch_start:batch_end]
    close_start = source.index("function closeChunkReviewModal")
    close_end = source.index("function renderChunkReviewModal", close_start)
    close_handler = source[close_start:close_end]

    assert "startLibraryBulkRegenWatcher(jobId, queuedChunkIds)" in batch_handler
    assert "startLibraryChunkRegenWatcher(jobId" not in batch_handler
    assert "stopLibraryBulkRegenWatcher()" in close_handler


def test_library_progress_assets_have_fresh_cache_versions():
    template = INDEX_TEMPLATE.read_text(encoding="utf-8")

    assert "/static/css/style.css?v=41" in template
    assert "/static/js/library.js?v=48" in template


def test_full_story_pill_loads_combined_audio_and_busts_rebuild_cache():
    source = LIBRARY_SCRIPT.read_text(encoding="utf-8")

    assert 'data-full-story-src="${item.full_story?.output_file || \'\'}"' in source
    assert "reviewAllButton.getAttribute('data-full-story-src')" in source
    assert source.count("`${fullStorySrc}${separator}v=${Date.now()}`") == 2
    assert "title: 'Full Story'" in source


def test_recompile_exposes_and_renders_live_post_process_progress():
    app_source = APP_SOURCE.read_text(encoding="utf-8")
    library_source = LIBRARY_SCRIPT.read_text(encoding="utf-8")

    assert '"post_process_percent": int(job_entry.get("post_process_percent") or 0)' in app_source
    assert '"post_process_label": job_entry.get("post_process_label")' in app_source
    assert "function startLibraryRecompileProgressWatcher" in library_source
    assert "function pollLibraryRecompileProgress" in library_source
    assert "function renderLibraryRecompileProgress" in library_source
    assert "review.post_process_percent || 0" in library_source


def test_recompile_merges_generated_outputs_into_existing_metadata():
    source = APP_SOURCE.read_text(encoding="utf-8")
    merge_start = source.index("def _merge_review_job")
    merge_end = source.index("@app.route('/api/jobs/<job_id>/review/finish'", merge_start)
    merge_source = source[merge_start:merge_end]

    assert "metadata = load_job_metadata(job_dir) or {}" in merge_source
    assert "merge_generated_library_metadata(" in merge_source
    assert '"word_replacements": (' in merge_source


def test_queue_sort_tolerates_missing_created_timestamp():
    source = APP_SOURCE.read_text(encoding="utf-8")
    route_start = source.index("def get_queue():")
    route_end = source.index("@app.route('/api/extract-document'", route_start)
    route = source[route_start:route_end]

    assert 'job_info.get("created_at")' in route
    assert 'or job_info.get("updated_at")' in route
    assert "all_jobs.sort(key=lambda x: x.get(\"created_at\") or \"\"" in route


def test_library_restore_supplies_a_creation_timestamp():
    source = APP_SOURCE.read_text(encoding="utf-8")
    route_start = source.index("def restore_library_item_to_review(job_id):")
    route_end = source.index("@app.route('/api/library/<job_id>/chunks'", route_start)
    route = source[route_start:route_end]

    assert '"created_at": (' in route
    assert 'metadata.get("created_at")' in route
    assert 'chunks_meta.get("created_at")' in route
    assert "job_dir.stat().st_ctime" in route


def test_library_delete_releases_audio_retries_and_verifies_before_success():
    app_source = APP_SOURCE.read_text(encoding="utf-8")
    library_source = LIBRARY_SCRIPT.read_text(encoding="utf-8")
    route_start = app_source.index("def delete_library_item(job_id):")
    route_end = app_source.index("@app.route('/api/library/clear'", route_start)
    route = app_source[route_start:route_end]

    audio_delete = route.index("remove_directory_with_retries(job_dir)")
    memory_delete = route.index("jobs.pop(job_id, None)")
    assert audio_delete < memory_delete
    assert 'conn.execute("DELETE FROM jobs WHERE job_id=?"' in route
    assert '"retryable": True' in route
    assert "function releaseLibraryItemAudio(jobId)" in library_source
    assert "await new Promise(resolve => setTimeout(resolve, 200))" in library_source
