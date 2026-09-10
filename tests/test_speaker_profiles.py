from __future__ import annotations

import re
from pathlib import Path

import app as app_module
import pytest
from app import (
    _build_qwen_voice_design_instruction,
    build_profile_voice_design_prompt,
    build_speaker_profile_excerpts,
    compose_gemini_speaker_profile_prompt,
    parse_gemini_speaker_table,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_profile_excerpts_are_bounded_and_grouped_by_exact_speaker():
    text = (
        "[narrator]The storm surrounded the old house.[/narrator]\n"
        "[alice-female]We should leave now.[/alice-female]\n"
        "[narrator]Alice watched the windows shake.[/narrator]"
    )

    result = build_speaker_profile_excerpts(
        text,
        ["narrator", "alice-female"],
        max_chars_per_speaker=30,
        max_total_chars=500,
    )

    assert "Speaker: narrator" in result
    assert "Speaker: alice-female" in result
    assert "We should leave now." in result
    assert len(result) < 500


def test_profile_prompt_enforces_complete_voice_table():
    prompt = compose_gemini_speaker_profile_prompt(
        "Analyze the characters.",
        ["narrator", "alice-female"],
        processed_text="Speaker: alice-female\nExcerpts: Hello.",
    )

    assert "Create one row for every exact speaker ID" in prompt
    assert "Character Name | Full Description | Voice Type | Voice Design Prompt" in prompt
    assert "ADULT FEMALE/MALE VOICE" in prompt
    assert "75-150 characters" in prompt
    assert "Do not mention audiobooks" in prompt
    assert "never include negative wording" in prompt
    assert "do not return blank cells" in prompt


def test_profile_parser_accepts_markdown_table_and_skips_headers():
    response = """
| Character Name | Full Description | Voice Profile |
| :--- | :--- | :--- |
| narrator | A measured adult storyteller with restrained dramatic warmth. | Warm, steady baritone |
| alice-female | A determined young woman whose urgency remains articulate. | Clear, urgent alto |
"""

    profiles = parse_gemini_speaker_table(response)

    assert set(profiles) == {"narrator", "alice-female"}
    assert profiles["alice-female"]["voice"] == "Clear, urgent alto"


def test_profile_parser_accepts_json_field_variations():
    response = """```json
[
  {
    "speaker": "alice-female",
    "profile": "A thoughtful young woman with a careful delivery.",
    "voice_type": "Soft, reflective alto"
  }
]
```"""

    profiles = parse_gemini_speaker_table(response)

    assert profiles["alice-female"] == {
        "name": "alice-female",
        "description": "A thoughtful young woman with a careful delivery.",
        "voice": "Soft, reflective alto",
    }


def test_profile_parser_preserves_dedicated_voice_design_prompt():
    response = """
| Character Name | Full Description | Voice Type | Voice Design Prompt |
| --- | --- | --- | --- |
| alice-female | A cautious investigator with quiet resolve. | Warm focused alto | Adult female voice, early thirties, warm alto. Measured pace, neutral English accent, restrained intensity for audiobook dialogue. |
"""

    profile = parse_gemini_speaker_table(response)["alice-female"]

    assert profile["voice"] == "Warm focused alto"
    assert profile["voice_design_prompt"].startswith("Adult female voice")


def test_qwen_instruction_uses_voice_fields_not_narrative_profile():
    instruction, language = _build_qwen_voice_design_instruction({
        "gender": "Female",
        "required_gender": True,
        "voice_type": "Warm, focused alto with measured pacing",
        "description": "A ruthless antagonist who manipulates everyone around her.",
        "language": "Auto",
    })

    assert instruction.startswith("ADULT FEMALE VOICE")
    assert "Warm, focused alto" in instruction
    assert "ruthless antagonist" not in instruction
    assert language == "English"


def test_qwen_instruction_removes_conflicting_negative_phrases():
    instruction, _ = _build_qwen_voice_design_instruction({
        "gender": "Male",
        "required_gender": True,
        "voice_design_prompt": "Mature baritone, never childlike, not theatrical, calm pace",
    })

    assert instruction.startswith("ADULT MALE VOICE")
    assert "never childlike" not in instruction.lower()
    assert "not theatrical" not in instruction.lower()


def test_qwen_instruction_blocks_missing_explicit_gender():
    with pytest.raises(ValueError, match="explicit Male, Female, or Neutral"):
        _build_qwen_voice_design_instruction({
            "required_gender": True,
            "voice_type": "Warm alto",
        })


def test_legacy_profile_gets_voice_design_prompt_without_using_biography():
    prompt = build_profile_voice_design_prompt({
        "name": "alice-female",
        "description": "A ruthless antagonist whose secret must never be revealed.",
        "voice": "Warm focused alto",
    })

    assert prompt.startswith("ADULT FEMALE VOICE")
    assert "Warm focused alto" in prompt
    assert "English" in prompt
    assert "ruthless antagonist" not in prompt
    assert "never" not in prompt.lower()
    assert "audiobook" not in prompt.lower()
    assert len(prompt) <= 150


def test_supplied_voice_design_prompt_is_compacted_and_drops_use_case():
    prompt = build_profile_voice_design_prompt({
        "name": "alice-female",
        "voice": "Warm focused alto",
        "voice_design_prompt": (
            "Adult female voice, early thirties, warm focused alto. Measured pace, neutral English accent, "
            "restrained intensity with expressive controlled delivery for audiobook dialogue."
        ),
    })
    instruction, _ = _build_qwen_voice_design_instruction({
        "gender": "Female",
        "required_gender": True,
        "voice_type": "Warm focused alto",
        "voice_design_prompt": prompt,
    })

    assert prompt.startswith("ADULT FEMALE VOICE")
    assert instruction.startswith("ADULT FEMALE VOICE")
    assert "audiobook" not in prompt.lower()
    assert "audiobook" not in instruction.lower()
    assert len(instruction) <= 150


def test_child_voice_prompt_never_receives_an_adult_prefix():
    original = {
        "name": "mira-female",
        "voice": "Child-like (7-8 years), light and sweet timbre",
        "voice_design_prompt": (
            "ADULT FEMALE VOICE. child-like (7-8 years), light and sweet timbre, "
            "inquisitive pace, standard American accent, innocent and curious emotional."
        ),
    }

    prompt = build_profile_voice_design_prompt(original)
    instruction, _ = _build_qwen_voice_design_instruction({
        "gender": "Female",
        "required_gender": True,
        "voice_type": original["voice"],
        "voice_design_prompt": prompt,
    })

    assert prompt.startswith("FEMALE CHILD VOICE")
    assert instruction.startswith("FEMALE CHILD VOICE")
    assert "ADULT" not in prompt
    assert "ADULT" not in instruction
    assert "age 7-8" in prompt.lower()
    assert "curious delivery" in prompt.lower()


@pytest.mark.parametrize(
    ("voice_type", "expected_prefix"),
    [
        ("15-year-old clear mezzo", "TEENAGE FEMALE VOICE"),
        ("young adult warm alto", "YOUNG ADULT FEMALE VOICE"),
        ("middle-aged smoky alto", "MIDDLE-AGED FEMALE VOICE"),
        ("elderly gentle alto", "ELDERLY FEMALE VOICE"),
    ],
)
def test_voice_prompt_uses_age_appropriate_prefixes(voice_type, expected_prefix):
    prompt = build_profile_voice_design_prompt({"name": "alice-female", "voice": voice_type})

    assert prompt.startswith(expected_prefix)


def test_all_voice_design_candidates_use_the_standard_inflection_passage():
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert "VOICE_DESIGN_STANDARD_PREVIEW_TEXT" in javascript
    assert "With this line of text, you will always know exactly where I stand" in javascript
    assert "return VOICE_DESIGN_STANDARD_PREVIEW_TEXT" in javascript
    assert 'data-role="speaker-voice-preview-text" rows="2" readonly' in javascript


def test_profile_parser_rejects_blank_profile_cells():
    response = "| alice-female |  | Soft alto |"

    assert parse_gemini_speaker_table(response) == {}


def test_generate_page_offers_profile_retry_without_reprocessing_text():
    template = (PROJECT_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert 'id="build-speaker-profiles-btn"' in template
    assert "await fetchSpeakerProfiles();" in javascript
    assert "buildProfilesBtn.disabled = !hasDetectedSpeakers" in javascript


def test_speaker_properties_offers_single_profile_generation():
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert 'data-role="speaker-build-profile"' in javascript
    assert "async function buildSingleSpeakerProfile(speaker)" in javascript
    assert "speakers: [speaker]" in javascript
    assert "processed_text: processedText" in javascript
    assert "updateSpeakerProfileEntry(speaker" in javascript
    assert 'data-role="speaker-voice-design-prompt"' in javascript
    assert "generateAndSaveVoiceCandidates" in javascript
    assert "voice_type: voiceType" in javascript
    assert "language: 'English'" in javascript
    assert "const instruct = description" not in javascript
    assert "function buildLocalVoiceDesignPrompt" in javascript
    assert "voice_design_prompt: buildLocalVoiceDesignPrompt(name, voice" in javascript


def test_main_bundle_cache_key_includes_latest_speaker_voice_routing_release():
    template = (PROJECT_ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    assert '/static/js/main.js?v=68' in template


def test_qwen_voice_generation_controls_require_optional_engine_installation(monkeypatch):
    template = (PROJECT_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    voice_manager = (PROJECT_ROOT / "static" / "js" / "voice-manager.js").read_text(encoding="utf-8")

    assert 'id="generate-voices-btn" class="btn btn-secondary btn-sm" disabled' in template
    assert 'id="qwen-voice-generate-btn" disabled' in template
    assert 'data-role="speaker-generate-voice" disabled' in javascript
    assert 'id="voice-creation-open-engine-settings"' in template
    assert 'data-role="open-voice-design-settings"' in javascript
    assert "qwen3_voice_design_available" in javascript
    assert "window.voiceDesignEngineAvailable?.(engine) !== true" in voice_manager

    monkeypatch.setattr(app_module, "isolated_engine_available", lambda _engine: False)
    client = app_module.app.test_client()
    health = client.get("/api/health").get_json()
    preview = client.post("/api/qwen3/voice-design/preview", json={"text": "Test"})

    assert health["qwen3_voice_design_available"] is False
    assert preview.status_code == 400
    assert "Settings" in preview.get_json()["error"]


def test_voice_sample_assignments_survive_compatible_engine_switches():
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert "TTS_STORY_VOICE_REFERENCE_PREFIX = 'tts-story://voice-prompts/'" in javascript
    assert "function captureCompatibleVoiceSamples()" in javascript
    assert "captureCompatibleVoiceSamples();" in javascript
    assert "function restoreCompatibleLocalAIVoiceSample(selectElement)" in javascript
    assert "restoreCompatibleLocalAIVoiceSample(select);" in javascript
    assert "Object.entries(turboSelectionState).forEach(([speaker, reference])" in javascript


def test_breeze_generated_sample_is_synced_into_speaker_properties():
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert "function syncSpeakerReferenceAssignment(speaker, promptValue = '')" in javascript
    assert "findSpeakerProfile(speaker).profile?.selected_voice_path" in javascript
    assert "populateReferenceDropdown(select, 'Select Voice Sample...', engineName)" in javascript
    assert "syncSpeakerReferenceAssignment(speaker, promptValue);" in javascript
    assert "syncSpeakerReferenceAssignment(speaker);" in javascript


def test_reference_sample_engines_never_expose_the_kokoro_voice_catalog():
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    stylesheet = (PROJECT_ROOT / "static" / "css" / "style.css").read_text(encoding="utf-8")
    template = (PROJECT_ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    assert "const usesReferenceSamples = isPromptEngine(engineName);" in javascript
    assert "kokoroControl.hidden = !showCatalogControl;" in javascript
    assert "turboControl.hidden = !showReferenceControl;" in javascript
    assert "select.innerHTML = '<option value=\"\">Voice samples are listed below</option>';" in javascript
    assert ".assignment-selection-group [data-role][hidden]" in stylesheet
    assert "/static/css/style.css?v=41" in template
    assert "/static/js/main.js?v=68" in template


def test_generated_voice_refresh_updates_available_voices_library():
    main = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    manager = (PROJECT_ROOT / "static" / "js" / "voice-manager.js").read_text(encoding="utf-8")
    template = (PROJECT_ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    assert "window.dispatchEvent(new CustomEvent(CHATTERBOX_VOICES_EVENT_NAME" in main
    assert "window.addEventListener(CHATTERBOX_VOICES_EVENT" in manager
    assert "chatterboxVoices = event.detail.voices" in manager
    assert '/static/js/voice-manager.js?v=18' in template


def test_voice_candidate_count_defaults_to_one_and_is_configurable():
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert 'data-role="speaker-voice-candidate-count"' in javascript
    assert 'min="1" max="10" step="1"' in javascript
    assert "profile?.voice_candidate_count, 10) || 1" in javascript
    assert "candidates.length === 1" in javascript


def test_bulk_generation_exposes_and_applies_candidate_count():
    template = (PROJECT_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert 'id="speaker-batch-candidate-count"' in template
    assert "Candidates per speaker" in template
    assert "voice_candidate_count: batchCandidateCount" in javascript
    assert "voice_design_engine: batchDesignEngine" in javascript


def test_project_schema_persists_casting_and_engine_state():
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    required_fragments = (
        "project_schema_version: 2",
        "bulk_voice_candidate_count:",
        "bulk_voice_prefix:",
        "assignments: getVoiceAssignments()",
        "turbo_selections: buildTurboSelectionMap()",
        "qwen_inline_languages: collectPerSpeakerControlValues",
        "qwen_inline_instructs: collectPerSpeakerControlValues",
        "word_replacements:",
        "fx_state:",
        "azure_voice_options:",
        "ready_state:",
        "speaker_profiles:",
        "voice_design_candidate_groups: serializeVoiceDesignCandidateGroups()",
        "restoreVoiceDesignCandidateGroups(project.voice_design_candidate_groups",
    )
    for fragment in required_fragments:
        assert fragment in javascript


def test_bulk_voice_generation_supports_qwen3_and_breeze():
    template = (PROJECT_ROOT / "templates" / "index.html").read_text(encoding="utf-8")
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert 'id="speaker-batch-design-engine"' in template
    assert '<option value="breeze" data-voice-design-option>Breeze TTS 2</option>' in template
    assert 'id="batch-engine-omnivoice-btn"' not in template
    assert "'/api/qwen3/voice-design/preview'" in javascript
    assert "'/api/qwen3/voice-design/save'" in javascript
    assert "'/api/breeze/voice-design/preview'" in javascript
    assert "'/api/breeze/voice-design/save'" in javascript
    assert "createVoiceDesignCandidateSeed()" in javascript
    assert "batchVoiceEngine" not in javascript


def test_qwen_candidates_are_seeded_and_cleanup_is_not_reapplied():
    source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    worker_source = (PROJECT_ROOT / "engines" / "qwen3_voice_design_worker.py").read_text(encoding="utf-8")
    cleanup_source = source.split("def _apply_voice_design_cleanup", 1)[1].split(
        "def _clean_voice_design_instruction", 1
    )[0]

    assert "with torch.random.fork_rng" in worker_source
    assert '"seed": seed' in source
    assert '"cleanup_applied": True' in source
    assert 'if not payload.get("cleanup_applied")' in source
    assert '"gain"' not in cleanup_source


def test_speaker_voice_sample_selector_is_filterable():
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert 'class="voice-sample-filter"' in javascript
    assert "selectEl.dataset.filterQuery" in javascript
    assert "entry?.voice_design?.instruction" in javascript
    assert "!entry?.archived || promptPath === previousValue" in javascript


def test_approved_candidate_updates_profile_and_dropdown_state():
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert "selected_voice_id: data.voice?.id || candidateId" in javascript
    assert "selected_voice_path: promptValue" in javascript
    assert "turboSelectionState[speaker] = promptValue" in javascript
    assert "Selected Voice:" in javascript


def test_candidate_approval_marks_selected_and_archives_rejected(monkeypatch):
    entries = [
        {
            "id": "candidate-a",
            "name": "Alice - Candidate A",
            "file_name": "alice_a.wav",
            "voice_design": {"candidate_group_id": "group-1", "approval_status": "pending"},
        },
        {
            "id": "candidate-b",
            "name": "Alice - Candidate B",
            "file_name": "alice_b.wav",
            "voice_design": {"candidate_group_id": "group-1", "approval_status": "pending"},
        },
    ]
    saved = {}
    monkeypatch.setattr(app_module, "_load_chatterbox_voice_entries", lambda: entries)
    monkeypatch.setattr(app_module, "_save_chatterbox_voice_entries", lambda value: saved.setdefault("entries", value))

    response = app_module.app.test_client().post(
        "/api/qwen3/voice-design/candidates/approve",
        json={"selected_id": "candidate-b", "candidate_group_id": "group-1"},
    )

    assert response.status_code == 200
    assert response.get_json()["voice"]["id"] == "candidate-b"
    by_id = {entry["id"]: entry for entry in saved["entries"]}
    assert by_id["candidate-b"]["voice_design"]["approval_status"] == "approved"
    assert by_id["candidate-b"]["archived"] is False
    assert by_id["candidate-a"]["voice_design"]["approval_status"] == "rejected"
    assert by_id["candidate-a"]["archived"] is True


def test_candidate_approval_supports_legacy_entries_without_group_metadata(monkeypatch):
    entries = [
        {"id": "legacy-a", "name": "Alice - Candidate A", "file_name": "alice_a.wav"},
        {"id": "legacy-b", "name": "Alice - Candidate B", "file_name": "alice_b.wav"},
    ]
    saved = {}
    monkeypatch.setattr(app_module, "_load_chatterbox_voice_entries", lambda: entries)
    monkeypatch.setattr(app_module, "_save_chatterbox_voice_entries", lambda value: saved.setdefault("entries", value))

    response = app_module.app.test_client().post(
        "/api/qwen3/voice-design/candidates/approve",
        json={
            "selected_id": "legacy-a",
            "candidate_group_id": "restored-group",
            "candidate_ids": ["legacy-a", "legacy-b"],
        },
    )

    assert response.status_code == 200
    by_id = {entry["id"]: entry for entry in saved["entries"]}
    assert by_id["legacy-a"]["voice_design"]["approval_status"] == "approved"
    assert by_id["legacy-a"]["archived"] is False
    assert by_id["legacy-b"]["voice_design"]["approval_status"] == "rejected"
    assert by_id["legacy-b"]["archived"] is True


def test_voice_design_frontend_detects_stale_backend_and_non_json_errors():
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert "qwen3_voice_design_api_version" in (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")
    assert "requireQwenVoiceDesignBackend()" in javascript
    assert "The updated voice-design backend is not running" in javascript
    assert "candidate_ids: groupCandidates.map" in javascript
    assert "VOICE_DESIGN_BACKEND_RESTART_REQUIRED" in javascript
    assert "new AbortController()" in javascript


def test_voice_design_preview_text_is_padded_to_a_ten_second_target():
    padded = app_module._ensure_voice_design_preview_length("A short line.")

    assert len(padded.split()) >= app_module.MIN_VOICE_DESIGN_PREVIEW_WORDS
    assert app_module.MIN_VOICE_DESIGN_PREVIEW_SECONDS == 10.0
    assert app_module.MIN_VOICE_DESIGN_PREVIEW_WORDS == 40


def test_standard_voice_preview_is_long_enough_for_batch_casting():
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    match = re.search(r"VOICE_DESIGN_STANDARD_PREVIEW_TEXT = '([^']+)'", javascript)

    assert match is not None
    assert len(match.group(1).split()) >= app_module.MIN_VOICE_DESIGN_PREVIEW_WORDS


def test_batch_voice_generation_clears_stale_candidates_and_reports_failures():
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")

    assert "delete speakerVoiceDesignCandidates[speakerKey]" in javascript
    assert "const failures = resume && Array.isArray(bulkVoiceGenerationState.failures)" in javascript
    assert "failures.push({ speaker, error: result.error })" in javascript
    assert "Promise.allSettled(candidates" in javascript


def test_voice_design_casting_uses_conservative_sampling(monkeypatch):
    captured = {}

    def fake_worker(payload):
        captured.update(payload["generation_kwargs"])
        app_module.sf.write(payload["output_path"], [0.0] * (24_000 * 11), 24_000)
        return {"sample_rate": 24_000, "elapsed_seconds": 0.1}

    monkeypatch.setattr(app_module, "_run_isolated_qwen_voice_design", fake_worker)
    monkeypatch.setattr(app_module, "_apply_voice_design_cleanup", lambda audio, _rate: audio)

    result = app_module._generate_voice_design_preview(
        {
            "name": "sima-kade-female",
            "gender": "Female",
            "voice_type": "Forceful, analytical alto",
            "text": "This is a sufficiently long preview passage for a casting voice sample.",
            "seed": 1234,
        },
        {},
    )

    assert captured["temperature"] == 0.6
    assert captured["top_p"] == 0.9
    assert captured["top_k"] == 40
    assert captured["subtalker_temperature"] == 0.6
    assert captured["subtalker_top_p"] == 0.9
    assert captured["subtalker_top_k"] == 40
    assert result["sampling_parameters"] == app_module.VOICE_DESIGN_CASTING_GENERATION


def test_voice_design_casting_caps_runaway_codec_generation():
    assert app_module.MAX_VOICE_DESIGN_PREVIEW_TOKENS == 768
    assert app_module.VOICE_DESIGN_CASTING_GENERATION["max_new_tokens"] == 768
    assert app_module.MAX_VOICE_DESIGN_PREVIEW_SECONDS == 45.0


def test_voice_design_preview_retries_with_a_new_seed(monkeypatch):
    calls = []
    cleanup_calls = []
    task_id = "voice-retry-test"

    def fake_generate(payload, _config):
        calls.append(payload["seed"])
        if len(calls) == 1:
            raise RuntimeError("missed ending token")
        return {"audio_base64": "d2F2", "seed": payload["seed"]}

    monkeypatch.setattr(app_module, "_generate_voice_design_preview", fake_generate)
    monkeypatch.setattr(
        app_module,
        "_cleanup_qwen_voice_design_generation",
        lambda **kwargs: cleanup_calls.append(kwargs),
    )
    monkeypatch.setattr(app_module, "_persist_job_state", lambda *args, **kwargs: None)
    app_module.jobs[task_id] = {
        "status": "processing",
        "job_type": "qwen3_voice_design_preview",
    }
    try:
        app_module.process_qwen3_voice_design_preview_task({
            "job_id": task_id,
            "payload": {"seed": 100},
            "config": {},
        })
        assert calls == [100, 101]
        assert app_module.jobs[task_id]["status"] == "completed"
        assert app_module.jobs[task_id]["result"]["attempts"] == 2
        assert any(call.get("force_cuda") for call in cleanup_calls)
    finally:
        app_module.jobs.pop(task_id, None)


def test_voice_design_cleanup_collects_python_objects_without_unloading_model(monkeypatch):
    collected = []
    original_model = app_module.qwen3_voice_design_model
    sentinel_model = object()
    app_module.qwen3_voice_design_model = sentinel_model
    monkeypatch.setattr(app_module.gc, "collect", lambda: collected.append(True))
    try:
        app_module._cleanup_qwen_voice_design_generation()
        assert collected == [True]
        assert app_module.qwen3_voice_design_model is sentinel_model
    finally:
        app_module.qwen3_voice_design_model = original_model


def test_bulk_voice_generation_persists_resumable_project_checkpoint():
    javascript = (PROJECT_ROOT / "static" / "js" / "main.js").read_text(encoding="utf-8")
    template = (PROJECT_ROOT / "templates" / "index.html").read_text(encoding="utf-8")

    assert "bulk_voice_generation_state:" in javascript
    assert "hasResumableBulkVoiceGeneration" in javascript
    assert "persistBulkVoiceGenerationState" in javascript
    assert "Pause requested. The current speaker will finish" in javascript
    assert 'id="speaker-batch-start-over-btn"' in template


def test_single_profile_request_sends_only_the_selected_speakers_excerpt(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        app_module,
        "load_config",
        lambda: {
            "llm_provider": "local",
            "gemini_speaker_profile_prompt": "Analyze this speaker.",
        },
    )

    def fake_run(prompt, _config):
        captured["prompt"] = prompt
        return (
            "| Character Name | Full Description | Voice Profile |\n"
            "| --- | --- | --- |\n"
            "| alice-female | A decisive investigator who speaks with calm urgency. | Clear, focused alto |",
            {"id": "primary", "name": "Primary", "provider": "local", "model": "test-model"},
            [],
        )

    monkeypatch.setattr(app_module, "_run_llm_prompt_with_failover", fake_run)
    response = app_module.app.test_client().post(
        "/api/gemini/speaker-profiles",
        json={
            "speakers": ["alice-female"],
            "processed_text": (
                "[alice-female]We leave before sunrise.[/alice-female]\n"
                "[bob-male]I will stay here.[/bob-male]"
            ),
        },
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert set(payload["profiles"]) == {"alice-female"}
    assert payload["profiles"]["alice-female"]["voice_design_prompt"].startswith("ADULT FEMALE VOICE")
    assert "We leave before sunrise." in captured["prompt"]
    assert "I will stay here." not in captured["prompt"]
