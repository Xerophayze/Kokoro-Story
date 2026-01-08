const MIN_CHATTERBOX_PROMPT_SECONDS = 5;

function preloadGenerationControls() {
    fetch('/api/settings')
        .then(resp => resp.json())
        .then(data => {
            if (!data?.success || !data.settings) return;
            const settings = data.settings;
            runtimeSettings = settings;
            setAvailableGeminiPresets(settings.gemini_prompt_presets || []);
            const formatSelect = document.getElementById('job-output-format');
            const bitrateSelect = document.getElementById('job-output-bitrate');
            if (formatSelect && settings.output_format) {
                formatSelect.value = settings.output_format;
                handleOutputFormatChange(formatSelect.value);
                refreshGlobalChatterboxPreviewButton();
}
            if (bitrateSelect && settings.output_bitrate_kbps) {
                bitrateSelect.value = String(settings.output_bitrate_kbps);
            }
            applyEngineDefaults(settings);
        })
        .catch(err => {
            console.error('Failed to preload output controls', err);
        });
}

function handleChatterboxVoicesUpdated(event) {
    const voices = Array.isArray(event?.detail?.voices) ? event.detail.voices : [];
    availableChatterboxVoices = voices;
    populateReferenceSelects();
    refreshGlobalChatterboxPreviewButton();
}

function handleOutputFormatChange(value) {
    const bitrateSelect = document.getElementById('job-output-bitrate');
    if (!bitrateSelect) return;
    const isMp3 = value === 'mp3';
    bitrateSelect.disabled = !isMp3;
    bitrateSelect.parentElement?.classList.toggle('disabled', !isMp3);
}

function applyEngineDefaults(settings) {
    const engineSelect = document.getElementById('job-tts-engine');
    const defaultEngine = (settings.tts_engine || 'kokoro').toLowerCase();
    if (engineSelect) {
        engineSelect.value = defaultEngine;
    }
    hydrateTurboLocalJobFields(settings);
    hydrateTurboReplicateJobFields(settings);
    updateEngineUI(defaultEngine);
}

function updateJobEngineOptionVisibility(engineName) {
    const jobTurboLocal = document.getElementById('job-chatterbox-turbo-local-options');
    const jobTurboReplicate = document.getElementById('job-chatterbox-turbo-replicate-options');
    if (jobTurboLocal) {
        jobTurboLocal.style.display = engineName === 'chatterbox_turbo_local' ? 'grid' : 'none';
    }
    if (jobTurboReplicate) {
        jobTurboReplicate.style.display = engineName === 'chatterbox_turbo_replicate' ? 'grid' : 'none';
    }
}

function updateEngineUI(engineName) {
    updateJobEngineOptionVisibility(engineName);
    const kokoroCard = document.getElementById('kokoro-default-voice-card');
    const turboCard = document.getElementById('chatterbox-turbo-voice-card');
    const isTurbo = engineName === 'chatterbox_turbo_local' || engineName === 'chatterbox_turbo_replicate';
    if (kokoroCard) {
        kokoroCard.style.display = isTurbo ? 'none' : 'block';
    }
    if (turboCard) {
        turboCard.style.display = isTurbo ? 'block' : 'none';
    }
    updateAssignmentModes(engineName);
    if (isTurbo) {
        fetchReferencePrompts();
    }
}

function hydrateTurboLocalJobFields(settings) {
    const promptInput = document.getElementById('job-turbo-local-prompt');
    const tempInput = document.getElementById('job-turbo-local-temperature');
    const topPInput = document.getElementById('job-turbo-local-top-p');
    const topKInput = document.getElementById('job-turbo-local-top-k');
    const repPenaltyInput = document.getElementById('job-turbo-local-rep-penalty');
    const cfgInput = document.getElementById('job-turbo-local-cfg-weight');
    const exaggerationInput = document.getElementById('job-turbo-local-exaggeration');
    const normCheck = document.getElementById('job-turbo-local-norm');
    const promptNormCheck = document.getElementById('job-turbo-local-prompt-norm');

    if (promptInput) {
        promptInput.placeholder = settings.chatterbox_turbo_local_default_prompt || promptInput.placeholder;
    }
    if (tempInput) {
        tempInput.value = settings.chatterbox_turbo_local_temperature ?? 0.8;
    }
    if (topPInput) {
        topPInput.value = settings.chatterbox_turbo_local_top_p ?? 0.95;
    }
    if (topKInput) {
        topKInput.value = settings.chatterbox_turbo_local_top_k ?? 1000;
    }
    if (repPenaltyInput) {
        repPenaltyInput.value = settings.chatterbox_turbo_local_repetition_penalty ?? 1.2;
    }
    if (cfgInput) {
        cfgInput.value = settings.chatterbox_turbo_local_cfg_weight ?? 0.0;
    }
    if (exaggerationInput) {
        exaggerationInput.value = settings.chatterbox_turbo_local_exaggeration ?? 0.0;
    }
    if (normCheck) {
        normCheck.checked = settings.chatterbox_turbo_local_norm_loudness !== false;
    }
    if (promptNormCheck) {
        promptNormCheck.checked = settings.chatterbox_turbo_local_prompt_norm_loudness !== false;
    }
}

function hydrateTurboReplicateJobFields(settings) {
    const modelInput = document.getElementById('job-turbo-replicate-model');
    const voiceInput = document.getElementById('job-turbo-replicate-voice');
    const tempInput = document.getElementById('job-turbo-replicate-temperature');
    const topPInput = document.getElementById('job-turbo-replicate-top-p');
    const topKInput = document.getElementById('job-turbo-replicate-top-k');
    const repPenaltyInput = document.getElementById('job-turbo-replicate-rep-penalty');
    const seedInput = document.getElementById('job-turbo-replicate-seed');

    if (modelInput) {
        modelInput.placeholder = settings.chatterbox_turbo_replicate_model || modelInput.placeholder;
    }
    if (voiceInput) {
        voiceInput.placeholder = settings.chatterbox_turbo_replicate_voice || voiceInput.placeholder;
    }
    if (tempInput) {
        tempInput.value = settings.chatterbox_turbo_replicate_temperature ?? 0.8;
    }
    if (topPInput) {
        topPInput.value = settings.chatterbox_turbo_replicate_top_p ?? 0.95;
    }
    if (topKInput) {
        topKInput.value = settings.chatterbox_turbo_replicate_top_k ?? 1000;
    }
    if (repPenaltyInput) {
        repPenaltyInput.value = settings.chatterbox_turbo_replicate_repetition_penalty ?? 1.2;
    }
    if (seedInput) {
        const seed = settings.chatterbox_turbo_replicate_seed;
        seedInput.value = seed === null || seed === undefined ? '' : seed;
    }
}

function isTurboEngine(engineName) {
    const value = (engineName || '').toLowerCase();
    return value === 'chatterbox_turbo_local' || value === 'chatterbox_turbo_replicate';
}

function updateEngineUI(engineName) {
    updateJobEngineOptionVisibility(engineName);
    const kokoroCard = document.getElementById('kokoro-default-voice-card');
    const turboCard = document.getElementById('chatterbox-turbo-voice-card');
    const isTurbo = isTurboEngine(engineName);
    if (kokoroCard) {
        kokoroCard.style.display = isTurbo ? 'none' : 'block';
    }
    if (turboCard) {
        turboCard.style.display = isTurbo ? 'block' : 'none';
    }
    updateAssignmentModes(engineName);
    if (isTurbo) {
        fetchReferencePrompts();
    }
}

function updateAssignmentModes(engineName) {
    const isTurbo = isTurboEngine(engineName);
    document.querySelectorAll('#inline-voice-assignment-list .voice-assignment-row').forEach(row => {
        const kokoroControl = row.querySelector('[data-role="kokoro-control"]');
        const turboControl = row.querySelector('[data-role="turbo-control"]');
        const kokoroPanel = row.querySelector('[data-role="kokoro-panel"]');
        if (kokoroControl) {
            kokoroControl.style.display = isTurbo ? 'none' : 'flex';
        }
        if (turboControl) {
            turboControl.style.display = isTurbo ? 'flex' : 'none';
        }
        if (kokoroPanel) {
            kokoroPanel.style.display = isTurbo ? 'none' : 'flex';
        }
    });
}

function populateReferenceDropdown(selectEl, placeholderText = 'Use preset voice') {
    if (!selectEl) return;
    const previousValue = selectEl.value;
    selectEl.innerHTML = '';
    if (placeholderText) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = placeholderText;
        selectEl.appendChild(option);
    }
    // Sort voices alphabetically by name
    const sortedVoices = [...availableChatterboxVoices].sort((a, b) =>
        (a.name || '').toLowerCase().localeCompare((b.name || '').toLowerCase())
    );
    sortedVoices.forEach(entry => {
        const option = document.createElement('option');
        const promptPath = (entry?.prompt_path || entry?.file_name || '').trim();
        option.value = promptPath;
        const durationLabel = entry?.duration_seconds ? ` · ${entry.duration_seconds.toFixed(2)}s` : '';
        option.textContent = `${entry?.name || promptPath}${durationLabel}`;
        option.dataset.durationSeconds = entry?.duration_seconds ?? '';
        selectEl.appendChild(option);
    });
    if (previousValue) {
        selectEl.value = previousValue;
    }
}

function populatePresetSelect(selectEl, selectedValue, placeholderText = 'Select a saved voice') {
    if (!selectEl) return;
    const previousValue = selectedValue || selectEl.value;
    selectEl.innerHTML = '';
    if (placeholderText) {
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = placeholderText;
        selectEl.appendChild(placeholder);
    }
    // Sort voices alphabetically by name
    const sortedVoices = [...availableChatterboxVoices].sort((a, b) =>
        (a.name || '').toLowerCase().localeCompare((b.name || '').toLowerCase())
    );
    sortedVoices.forEach(entry => {
        const pathValue = (entry?.prompt_path || entry?.file_name || '').trim();
        if (!pathValue) {
            return;
        }
        const option = document.createElement('option');
        option.value = pathValue;
        option.textContent = entry?.name || pathValue;
        if (entry.missing_file) {
            option.disabled = true;
            option.textContent = `${option.textContent} (missing file)`;
        }
        selectEl.appendChild(option);
    });
    if (previousValue) {
        selectEl.value = previousValue;
    }
}

function populateReferenceSelects() {
    populateReferenceDropdown(
        document.getElementById('chatterbox-reference-select'),
        'Select saved Chatterbox voice'
    );
    document.querySelectorAll('#inline-voice-assignment-list [data-role="turbo-control"] .reference-select')
        .forEach(select => {
            populateReferenceDropdown(select, 'Inherit from global selection');
    });
}

async function handleReferenceUpload(event) {
    const files = event.target.files;
    if (!files || !files.length) {
        return;
    }
    const file = files[0];
    const formData = new FormData();
    formData.append('file', file);
    try {
        const response = await fetch('/api/voice-prompts/upload', {
            method: 'POST',
            body: formData,
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Upload failed');
        }
        showNotification('Reference prompt uploaded.', 'success');
        await fetchReferencePrompts();
    } catch (error) {
        console.error('Prompt upload failed', error);
        showNotification(error.message || 'Failed to upload prompt', 'error');
    } finally {
        event.target.value = '';
    }
}

function handleReferenceSelectChange(event) {
    const selected = event.target.value;
    const promptInput = document.getElementById('job-turbo-local-prompt');
    if (promptInput !== null) {
        promptInput.value = selected;
    }
    refreshGlobalChatterboxPreviewButton();
}

async function fetchReferencePrompts() {
    try {
        const response = await fetch('/api/voice-prompts');
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Unable to load reference prompts');
        }
        window.availableReferencePrompts = data.prompts || [];
    } catch (error) {
        console.error('Failed to fetch reference prompts', error);
        window.availableReferencePrompts = [];
    } finally {
        populateReferenceSelects();
        refreshGlobalChatterboxPreviewButton();
    }
}

function findChatterboxVoiceByPath(pathValue) {
    if (!pathValue) return null;
    const normalized = pathValue.trim();
    if (!normalized) return null;
    return availableChatterboxVoices.find(entry => {
        const promptPath = (entry?.prompt_path || '').trim();
        const fileName = (entry?.file_name || '').trim();
        return promptPath === normalized || fileName === normalized;
    }) || null;
}

function refreshGlobalChatterboxPreviewButton() {
    const select = document.getElementById('chatterbox-reference-select');
    const button = document.getElementById('global-chatterbox-preview-btn');
    if (!button) return;
    const hasSelection = !!(select?.value?.trim());
    if (!hasSelection) {
        button.disabled = true;
        button.classList.remove('is-playing', 'is-loading');
        button.textContent = button.dataset.labelPlay || 'Play';
    } else {
        button.disabled = false;
    }
}
window.refreshGlobalChatterboxPreviewButton = refreshGlobalChatterboxPreviewButton;

function getSelectedJobEngine() {
    const select = document.getElementById('job-tts-engine');
    if (!select) return null;
    const value = (select.value || '').trim().toLowerCase();
    return value || null;
}

function getGlobalReferenceSelection() {
    const select = document.getElementById('chatterbox-reference-select');
    if (select && select.value) {
        return select.value.trim();
    }
    const promptInput = document.getElementById('job-turbo-local-prompt');
    return (promptInput?.value || '').trim();
}

function collectEngineOverrides(engineName) {
    if (!engineName) return null;
    switch (engineName) {
        case 'chatterbox':
            return collectChatterboxOverrides();
        case 'chatterbox_turbo_local':
            return collectTurboLocalOverrides();
        case 'chatterbox_turbo_replicate':
            return collectTurboReplicateOverrides();
        default:
            return null;
    }
}

function collectTurboLocalOverrides() {
    const options = {};
    const prompt = document.getElementById('job-turbo-local-prompt')?.value.trim();
    if (prompt) {
        options.default_prompt = prompt;
    }
    const temperature = readNumericInput('job-turbo-local-temperature');
    if (temperature !== null) {
        options.temperature = temperature;
    }
    const topP = readNumericInput('job-turbo-local-top-p');
    if (topP !== null) {
        options.top_p = topP;
    }
    const topK = readNumericInput('job-turbo-local-top-k', true);
    if (topK !== null) {
        options.top_k = topK;
    }
    const repPenalty = readNumericInput('job-turbo-local-rep-penalty');
    if (repPenalty !== null) {
        options.repetition_penalty = repPenalty;
    }
    const cfgWeight = readNumericInput('job-turbo-local-cfg-weight');
    if (cfgWeight !== null) {
        options.cfg_weight = cfgWeight;
    }
    const exaggeration = readNumericInput('job-turbo-local-exaggeration');
    if (exaggeration !== null) {
        options.exaggeration = exaggeration;
    }
    const normCheckbox = document.getElementById('job-turbo-local-norm');
    if (normCheckbox) {
        options.norm_loudness = normCheckbox.checked;
    }
    const promptNormCheckbox = document.getElementById('job-turbo-local-prompt-norm');
    if (promptNormCheckbox) {
        options.prompt_norm_loudness = promptNormCheckbox.checked;
    }
    return Object.keys(options).length ? options : null;
}

function collectTurboReplicateOverrides() {
    const options = {};
    const model = document.getElementById('job-turbo-replicate-model')?.value.trim();
    if (model) {
        options.model = model;
    }
    const voice = document.getElementById('job-turbo-replicate-voice')?.value.trim();
    if (voice) {
        options.voice = voice;
    }
    const temperature = readNumericInput('job-turbo-replicate-temperature');
    if (temperature !== null) {
        options.temperature = temperature;
    }
    const topP = readNumericInput('job-turbo-replicate-top-p');
    if (topP !== null) {
        options.top_p = topP;
    }
    const topK = readNumericInput('job-turbo-replicate-top-k', true);
    if (topK !== null) {
        options.top_k = topK;
    }
    const repPenalty = readNumericInput('job-turbo-replicate-rep-penalty');
    if (repPenalty !== null) {
        options.repetition_penalty = repPenalty;
    }
    const seedValue = document.getElementById('job-turbo-replicate-seed')?.value.trim();
    if (seedValue) {
        const parsedSeed = parseInt(seedValue, 10);
        if (Number.isFinite(parsedSeed) && parsedSeed >= 0) {
            options.seed = parsedSeed;
        }
    }
    return Object.keys(options).length ? options : null;
}

function readNumericInput(elementId, integerOnly = false) {
    const raw = document.getElementById(elementId)?.value;
    if (raw === undefined || raw === null || raw === '') {
        return null;
    }
    const parsed = integerOnly ? parseInt(raw, 10) : parseFloat(raw);
    if (!Number.isFinite(parsed)) {
        return null;
    }
    return parsed;
}

// Main application logic

let currentJobId = null;
let currentStats = null;
let analyzeDebounceTimer = null;
let lastAnalyzedText = '';
let analyzeInFlight = false;
let analyzeRerunRequested = false;
const ANALYZE_DEBOUNCE_MS = 800;
const VOICES_EVENT_NAME = window.VOICES_UPDATED_EVENT || 'voices:updated';
const DEFAULT_FX_STATE = Object.freeze({
    pitch: 0,
    speed: 1,
    sampleText: ''
});
const voiceFxState = {};
let currentFxPreviewAudio = null;
let queuePollInFlight = false;
let runtimeSettings = null;
let availableChatterboxVoices = [];
let availableGeminiPromptPresets = [];

window.customVoiceMap = window.customVoiceMap || {};
window.addEventListener(VOICES_EVENT_NAME, handleVoicesUpdated);
const CHATTERBOX_VOICES_EVENT_NAME = window.CHATTERBOX_VOICES_EVENT || 'chatterboxVoices:updated';
window.CHATTERBOX_VOICES_EVENT = CHATTERBOX_VOICES_EVENT_NAME;
window.addEventListener(CHATTERBOX_VOICES_EVENT_NAME, handleChatterboxVoicesUpdated);
window.addEventListener('geminiPresets:changed', event => {
    setAvailableGeminiPresets(event?.detail?.presets || []);
});

function setAvailableGeminiPresets(presets = []) {
    const normalized = [];
    if (Array.isArray(presets)) {
        presets.forEach(preset => {
            const title = (preset?.title || '').trim();
            const prompt = (preset?.prompt || '').trim();
            let id = (preset?.id || '').trim();
            if (!title || !prompt) {
                return;
            }
            if (!id) {
                id = typeof crypto !== 'undefined' && crypto.randomUUID
                    ? crypto.randomUUID()
                    : `preset-${Date.now()}-${normalized.length}`;
            }
            normalized.push({ id, title, prompt });
        });
    }
    availableGeminiPromptPresets = normalized;
    populateGeminiPresetDropdown();
}

function populateGeminiPresetDropdown(selectedId) {
    const select = document.getElementById('gemini-preset-select');
    if (!select) return;
    const previousValue = selectedId !== undefined ? selectedId : select.value;
    select.innerHTML = '';
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = 'Use default prompt';
    select.appendChild(defaultOption);
    availableGeminiPromptPresets.forEach(preset => {
        const option = document.createElement('option');
        option.value = preset.id;
        option.textContent = preset.title;
        option.title = preset.prompt;
        select.appendChild(option);
    });
    if (previousValue) {
        select.value = previousValue;
        if (select.value !== previousValue) {
            select.value = '';
        }
    }
}

function handleVoicesUpdated(event) {
    const detail = event?.detail || {};
    if (detail.voices) {
        window.availableVoices = detail.voices;
    }
    if (detail.customVoiceMap) {
        window.customVoiceMap = detail.customVoiceMap;
    }
    populateDefaultVoiceSelect();
    populateVoiceSelects();
    initDefaultVoiceFxPanel();
}

function getFxStateKey(speaker) {
    if (!speaker) return 'default';
    return speaker;
}

function getFxState(speaker) {
    const key = getFxStateKey(speaker);
    if (!voiceFxState[key]) {
        voiceFxState[key] = {
            pitch: DEFAULT_FX_STATE.pitch,
            speed: DEFAULT_FX_STATE.speed,
            sampleText: DEFAULT_FX_STATE.sampleText
        };
    }
    return voiceFxState[key];
}

function getFxPayload(speaker) {
    const state = getFxState(speaker);
    const payload = {};
    const pitch = Number(state.pitch) || 0;
    if (Math.abs(pitch) > 0.01) {
        payload.pitch = pitch;
    }
    return Object.keys(payload).length ? payload : null;
}

function createAssignment(voiceName, langCode, speakerKey) {
    const state = getFxState(speakerKey);
    const assignment = {
        voice: voiceName,
        lang_code: langCode
    };
    const fxPayload = getFxPayload(speakerKey);
    if (fxPayload) {
        assignment.fx = fxPayload;
    }
    const speedValue = Number(state.speed) || 1;
    if (Math.abs(speedValue - 1) > 0.01) {
        assignment.speed = Number(speedValue.toFixed(2));
    }
    return assignment;
}

function getSharedPreviewText() {
    const shared = document.getElementById('global-voice-preview-text');
    const value = shared?.value?.trim();
    if (value) return value;
    return 'This is a quick preview line.';
}

function buildDefaultSampleText(speaker) {
    if (!speaker || speaker === 'default') {
        return 'This is a quick preview for the default narrator.';
    }
    return `This is a quick preview line for ${speaker}.`;
}

function renderFxPanel(container, speaker, options = {}) {
    if (!container) return;
    const state = getFxState(speaker);
    const wrapClass = container.classList.contains('voice-fx-inline')
        ? 'fx-inline-layout'
        : 'fx-panel-layout';
    const previewSlot = options.previewTargetId
        ? document.getElementById(options.previewTargetId)
        : null;
    const useSharedPreview = options.useSharedPreview === true;
    const showHeaderTitle = options.showHeader !== false;
    const title = options.title || 'Voice FX';
    const headerMarkup = showHeaderTitle
        ? `<div class="fx-header"><h4>${title}</h4></div>`
        : '';
    const sharedActionsMarkup = useSharedPreview
        ? `
            <div class="fx-field fx-inline fx-actions">
                <button type="button" class="btn btn-sm" data-role="fx-preview-btn">Quick Test</button>
                <span class="fx-status" data-role="fx-status"></span>
            </div>
        `
        : '';
    const previewMarkup = !useSharedPreview
        ? `
            <div class="fx-field fx-preview">
                <textarea data-role="fx-sample-text" rows="2" placeholder="Preview text">${state.sampleText || buildDefaultSampleText(speaker)}</textarea>
                <div class="fx-preview-actions">
                    <button type="button" class="btn btn-sm" data-role="fx-preview-btn">Quick Test</button>
                    <span class="fx-status" data-role="fx-status"></span>
                </div>
            </div>
        `
        : '';
    container.innerHTML = `
        <div class="${wrapClass}">
            ${headerMarkup}
            <div class="fx-fields">
                <div class="fx-field fx-inline fx-slider">
                    <label>Pitch</label>
                    <div class="slider-group">
                        <input type="range" min="-6" max="6" step="0.1" value="${state.pitch}" data-role="fx-pitch">
                        <span class="slider-value" data-role="fx-pitch-value">${state.pitch.toFixed(1)} st</span>
                    </div>
                </div>
                <div class="fx-field fx-inline fx-slider">
                    <label>Speed</label>
                    <div class="slider-group">
                        <input type="range" min="0.5" max="2.0" step="0.05" value="${state.speed}" data-role="fx-speed">
                        <span class="slider-value" data-role="fx-speed-value">${state.speed.toFixed(2)}x</span>
                    </div>
                </div>
                ${sharedActionsMarkup}
            </div>
        </div>
    `;
    if (!useSharedPreview) {
        if (previewSlot) {
            previewSlot.innerHTML = previewMarkup;
        } else if (previewMarkup) {
            container.insertAdjacentHTML('beforeend', previewMarkup);
        }
    }
    container.classList.remove('fx-disabled');

    const pitchInput = container.querySelector('[data-role="fx-pitch"]');
    const pitchValue = container.querySelector('[data-role="fx-pitch-value"]');
    const speedInput = container.querySelector('[data-role="fx-speed"]');
    const speedValue = container.querySelector('[data-role="fx-speed-value"]');
    const previewRoot = useSharedPreview ? container : (previewSlot || container);
    const previewBtn = previewRoot.querySelector('[data-role="fx-preview-btn"]');
    const sampleInput = useSharedPreview
        ? document.getElementById('global-voice-preview-text')
        : previewRoot.querySelector('[data-role="fx-sample-text"]');

    if (pitchInput && pitchValue) {
        pitchInput.addEventListener('input', event => {
            state.pitch = parseFloat(event.target.value) || 0;
            pitchValue.textContent = `${state.pitch.toFixed(1)} st`;
        });
    }
    if (speedInput && speedValue) {
        speedInput.addEventListener('input', event => {
            state.speed = parseFloat(event.target.value) || 1;
            speedValue.textContent = `${state.speed.toFixed(2)}x`;
        });
    }
    if (!useSharedPreview && sampleInput) {
        sampleInput.addEventListener('input', event => {
            state.sampleText = event.target.value;
        });
    }
    if (previewBtn) {
        previewBtn.addEventListener('click', () => handleFxPreview(speaker, container));
    }
}

function resolveVoiceSelection(speaker) {
    if (speaker === 'default' || !speaker) {
        return document.getElementById('default-voice-select')?.value || '';
    }
    const selector = document.querySelector(`#inline-voice-assignment-list .voice-select[data-speaker="${speaker}"]`);
    return selector?.value || '';
}

async function handleFxPreview(speaker, container) {
    if (!container) return;
    const voiceName = resolveVoiceSelection(speaker);
    const statusEl = container.querySelector('[data-role="fx-status"]');
    const previewBtn = container.querySelector('[data-role="fx-preview-btn"]');
    if (!voiceName) {
        if (statusEl) statusEl.textContent = 'Select a voice first.';
        return;
    }
    const langCode = getLangCodeForVoice(voiceName);
    const state = getFxState(speaker);
    const sampleText = speaker === 'default'
        ? (state.sampleText || '').trim() || buildDefaultSampleText(speaker)
        : getSharedPreviewText();
    const payload = {
        voice: voiceName,
        lang_code: langCode,
        text: sampleText,
    };
    const fxPayload = getFxPayload(speaker);
    if (fxPayload) {
        payload.fx = fxPayload;
    }
    const panelSpeed = Number(state.speed) || NaN;
    const globalSpeed = parseFloat(document.getElementById('speed')?.value) || 1.0;
    let previewSpeed = Number.isFinite(panelSpeed) ? panelSpeed : globalSpeed;
    previewSpeed = Math.max(0.5, Math.min(previewSpeed, 2.0));
    payload.speed = previewSpeed;

    const selectedEngine = getSelectedJobEngine() || runtimeSettings?.tts_engine;
    if (selectedEngine) {
        payload.tts_engine = selectedEngine;
        const overrides = collectEngineOverrides(selectedEngine);
        if (overrides) {
            payload.engine_options = overrides;
        }
    }

    try {
        if (previewBtn) previewBtn.disabled = true;
        if (statusEl) statusEl.textContent = 'Rendering preview…';

        const response = await fetch('/api/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        const data = await response.json();
        if (!data.success || !data.audio_base64) {
            throw new Error(data.error || 'Preview failed');
        }
        if (currentFxPreviewAudio) {
            currentFxPreviewAudio.pause();
            currentFxPreviewAudio = null;
        }
        const mime = data.mime_type || 'audio/wav';
        currentFxPreviewAudio = new Audio(`data:${mime};base64,${data.audio_base64}`);
        currentFxPreviewAudio.play().then(() => {
            if (statusEl) statusEl.textContent = 'Playing preview…';
        }).catch(err => {
            console.error('Preview playback failed', err);
            if (statusEl) statusEl.textContent = 'Unable to play preview.';
        });
        if (currentFxPreviewAudio) {
            currentFxPreviewAudio.onended = () => {
                if (statusEl) statusEl.textContent = '';
                currentFxPreviewAudio = null;
            };
        }
    } catch (error) {
        console.error('Preview failed:', error);
        if (statusEl) statusEl.textContent = error.message || 'Preview failed';
    } finally {
        if (previewBtn) previewBtn.disabled = false;
    }
}

function initDefaultVoiceFxPanel() {
    const container = document.getElementById('default-voice-fx-panel');
    if (!container) return;
    renderFxPanel(container, 'default', {
        title: 'Default Voice FX',
        showHeader: false,
        previewTargetId: 'default-voice-preview-slot',
    });
}

function refreshChapterHint() {
    const chapterHint = document.getElementById('chapter-detection-hint');
    const chapterCheckbox = document.getElementById('split-chapters-checkbox');
    syncFullStoryOption(chapterCheckbox);
    if (!chapterHint || !chapterCheckbox) {
        return;
    }

    if (!currentStats || !currentStats.chapter_detection) {
        chapterHint.textContent = chapterCheckbox.checked
            ? 'Chapter splitting enabled. Awaiting analysis to determine chapters.'
            : 'Chapters not analyzed yet.';
        return;
    }

    const { detected, count } = currentStats.chapter_detection;
    if (!detected) {
        chapterHint.textContent = chapterCheckbox.checked
            ? 'Splitting enabled, but no chapter headings were detected. The whole story will be one file.'
            : 'No chapters detected. Add headings like "Chapter 1" to enable per-chapter outputs.';
        return;
    }

    if (chapterCheckbox.checked) {
        chapterHint.textContent = `Splitting enabled: ${count} chapter${count === 1 ? '' : 's'} will become individual audio files.`;
    } else {
        chapterHint.textContent = `Detected ${count} chapter${count === 1 ? '' : 's'}. Enable the checkbox to create separate audio files.`;
    }
}

function getSelectedGeminiPromptOverride() {
    const select = document.getElementById('gemini-preset-select');
    if (!select) return '';
    const selectedId = select.value;
    if (!selectedId) return '';
    const preset = availableGeminiPromptPresets.find(entry => entry.id === selectedId);
    return preset?.prompt || '';
}

async function processWithGemini(buttonEl) {
    const inputEl = document.getElementById('input-text');
    if (!inputEl) return;

    const text = inputEl.value;
    if (!text.trim()) {
        alert('Please enter some text first');
        return;
    }

    const splitByChapter = document.getElementById('split-chapters-checkbox')?.checked ?? false;
    const promptOverride = getSelectedGeminiPromptOverride();
    updateGeminiProgress({ visible: true, label: 'Preparing Gemini request…', count: '', fill: 5 });

    const originalLabel = buttonEl ? buttonEl.textContent : '';
    if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.textContent = 'Processing with Gemini...';
    }

    showNotification(
        splitByChapter
            ? 'Splitting content by chapter and sending to Gemini...'
            : 'Sending entire text to Gemini...',
        'info'
    );

    try {
        if (splitByChapter) {
            updateGeminiProgress({
                visible: true,
                label: 'Building chapter list for Gemini…',
                count: '',
                fill: 15
            });

            const sectionsResponse = await fetch('/api/gemini/sections', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text,
                    prefer_chapters: true
                })
            });

            const sectionsData = await sectionsResponse.json();
            if (!sectionsData.success) {
                throw new Error(sectionsData.error || 'Unable to build Gemini chapters');
            }

            const sections = sectionsData.sections || [];
            if (!sections.length) {
                throw new Error('No chapters were generated for Gemini processing.');
            }

            const outputs = [];
            const knownSpeakers = new Set();
            if (currentStats?.speakers?.length) {
                currentStats.speakers.forEach(name => {
                    if (typeof name === 'string' && name.trim()) {
                        knownSpeakers.add(name.trim().toLowerCase());
                    }
                });
            }

            for (let i = 0; i < sections.length; i++) {
                const section = sections[i];
                const currentIndex = i + 1;
                updateGeminiProgress({
                    visible: true,
                    label: `Processing chapter ${currentIndex} of ${sections.length}…`,
                    count: `${currentIndex} / ${sections.length}`,
                    fill: Math.round((currentIndex / sections.length) * 100)
                });

                const payload = {
                    content: section.content || ''
                };
                if (promptOverride) {
                    payload.prompt_override = promptOverride;
                }
                if (knownSpeakers.size > 0) {
                    payload.known_speakers = Array.from(knownSpeakers);
                }

                const sectionResponse = await fetch('/api/gemini/process-section', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify(payload)
                });

                const sectionData = await sectionResponse.json();
                if (!sectionData.success) {
                    throw new Error(sectionData.error || `Gemini failed on chapter ${currentIndex}`);
                }

                if (Array.isArray(sectionData.speakers)) {
                    sectionData.speakers.forEach(speaker => {
                        if (typeof speaker === 'string' && speaker.trim()) {
                            knownSpeakers.add(speaker.trim().toLowerCase());
                        }
                    });
                }
                outputs.push(sectionData.result_text || '');
            }

            updateGeminiProgress({
                visible: true,
                label: 'Combining Gemini output…',
                count: `${sections.length} / ${sections.length}`,
                fill: 100
            });

            inputEl.value = outputs.join('\n\n').trim();
        } else {
            updateGeminiProgress({ visible: true, label: 'Contacting Gemini…', count: '', fill: 20 });

            const response = await fetch('/api/gemini/process-full', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({
                    text,
                    prompt_override: promptOverride || undefined
                })
            });

            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Gemini processing failed');
            }

            const processedText = (data.result_text || '').trim();
            if (!processedText) {
                throw new Error('Gemini returned an empty response.');
            }

            updateGeminiProgress({
                visible: true,
                label: 'Gemini response received…',
                count: '',
                fill: 100
            });

            inputEl.value = processedText;
        }

        lastAnalyzedText = '';
        showNotification('Gemini processing complete! Text updated.', 'success');
        await analyzeText({ auto: true });
    } catch (error) {
        console.error('Gemini processing failed:', error);
        alert(error.message || 'Failed to process with Gemini');
    } finally {
        if (buttonEl) {
            buttonEl.disabled = false;
            buttonEl.textContent = originalLabel || 'Prep Text with Gemini';
        }
        updateGeminiProgress({ visible: false });
    }
}

function updateGeminiProgress({ visible, label, count, fill }) {
    const container = document.getElementById('gemini-progress');
    const textEl = document.getElementById('gemini-progress-text');
    const countEl = document.getElementById('gemini-progress-count');
    const fillEl = document.getElementById('gemini-progress-fill');

    if (!container || !textEl || !countEl || !fillEl) return;

    if (visible) {
        container.style.display = 'block';
        if (label) textEl.textContent = label;
        if (count) countEl.textContent = count;
        if (typeof fill === 'number') fillEl.style.width = `${Math.min(Math.max(fill, 0), 100)}%`;
    } else {
        container.style.display = 'none';
        fillEl.style.width = '0%';
        countEl.textContent = '';
    }
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadHealthStatus();
    setupEventListeners();
    preloadGenerationControls();
    initDefaultVoiceFxPanel();
    if (typeof loadLibraryItems === 'function') {
        loadLibraryItems();
    }
    initAutoAnalyze();
    const chapterCheckbox = document.getElementById('split-chapters-checkbox');
    syncFullStoryOption(chapterCheckbox, true);
});

function initAutoAnalyze() {
    const input = document.getElementById('input-text');
    if (!input) return;

    input.addEventListener('input', () => {
        if (analyzeDebounceTimer) {
            clearTimeout(analyzeDebounceTimer);
        }

        analyzeDebounceTimer = setTimeout(async () => {
            const text = input.value;
            if (!text.trim()) {
                currentStats = null;
                lastAnalyzedText = '';
                hideAnalysis();
                return;
            }

            if (text.trim() === lastAnalyzedText) {
                return;
            }

            const success = await analyzeText({ auto: true });
            if (success) {
                lastAnalyzedText = text.trim();
            }
        }, ANALYZE_DEBOUNCE_MS);
    });
}

function hideAnalysis() {
    const statsSection = document.getElementById('stats-section');
    const inlineAssignments = document.getElementById('inline-voice-assignments');
    const chapterInfo = document.getElementById('chapter-detection-info');
    if (statsSection) {
        statsSection.style.display = 'none';
    }
    if (inlineAssignments) {
        inlineAssignments.style.display = 'none';
    }
    if (chapterInfo) {
        chapterInfo.style.display = 'none';
    }
    currentStats = null;
    refreshChapterHint();
}

// Tab switching
function initTabs() {
    const tabButtons = document.querySelectorAll('.tab-button');
    const tabContents = document.querySelectorAll('.tab-content');
    
    tabButtons.forEach(button => {
        button.addEventListener('click', () => {
            const tabName = button.dataset.tab;
            
            // Update buttons
            tabButtons.forEach(btn => btn.classList.remove('active'));
            button.classList.add('active');
            
            // Update content
            tabContents.forEach(content => {
                content.classList.remove('active');
            });
            document.getElementById(`${tabName}-tab`).classList.add('active');
        });
    });
}

// Setup event listeners
function setupEventListeners() {
    const analyzeBtn = document.getElementById('analyze-btn');
    const generateBtn = document.getElementById('generate-btn');
    const geminiBtn = document.getElementById('gemini-process-btn');
    const downloadBtn = document.getElementById('download-btn');
    const newGenerationBtn = document.getElementById('new-generation-btn');
    const resetAssignmentsBtn = document.getElementById('reset-assignments-btn');
    const cancelBtn = document.getElementById('cancel-btn');
    const chapterCheckbox = document.getElementById('split-chapters-checkbox');
    const fullStoryCheckbox = document.getElementById('full-story-checkbox');

    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', analyzeText);
    }
    if (generateBtn) {
        generateBtn.addEventListener('click', generateAudio);
    }
    if (geminiBtn) {
        geminiBtn.addEventListener('click', () => processWithGemini(geminiBtn));
    }
    if (downloadBtn) {
        downloadBtn.addEventListener('click', downloadAudio);
    }
    if (newGenerationBtn) {
        newGenerationBtn.addEventListener('click', resetGeneration);
    }
    if (resetAssignmentsBtn) {
        resetAssignmentsBtn.addEventListener('click', resetVoiceAssignments);
    }
    if (cancelBtn) {
        cancelBtn.addEventListener('click', cancelGeneration);
    }
    if (chapterCheckbox) {
        chapterCheckbox.addEventListener('change', event => {
            refreshChapterHint();
            syncFullStoryOption(event.currentTarget);
        });
    }

    if (fullStoryCheckbox) {
        fullStoryCheckbox.addEventListener('change', () => {
            if (!chapterCheckbox?.checked) {
                fullStoryCheckbox.checked = false;
            }
        });
    }

    const outputFormatSelect = document.getElementById('job-output-format');
    if (outputFormatSelect) {
        outputFormatSelect.addEventListener('change', event => {
            handleOutputFormatChange(event.target.value);
        });
        handleOutputFormatChange(outputFormatSelect.value);
    }

    const jobEngineSelect = document.getElementById('job-tts-engine');
    if (jobEngineSelect) {
        jobEngineSelect.addEventListener('change', event => {
            const engineName = (event.target.value || '').toLowerCase();
            updateEngineUI(engineName);
            updateModeIndicator(engineName);
            const currentText = document.getElementById('input-text')?.value?.trim();
            if (currentText && lastAnalyzedText && currentText === lastAnalyzedText) {
                analyzeText({ auto: true });
            }
        });
    }

    const referenceUploadInput = document.getElementById('reference-prompt-upload-input');
    if (referenceUploadInput) {
        referenceUploadInput.addEventListener('change', handleReferenceUpload);
    }
    const globalReferenceSelect = document.getElementById('chatterbox-reference-select');
    if (globalReferenceSelect) {
        globalReferenceSelect.addEventListener('change', handleReferenceSelectChange);
    }
    refreshGlobalChatterboxPreviewButton();
    const globalPreviewBtn = document.getElementById('global-chatterbox-preview-btn');
    if (globalPreviewBtn) {
        globalPreviewBtn.addEventListener('click', event => {
            const select = document.getElementById('chatterbox-reference-select');
            const selection = select?.value?.trim();
            if (!selection) {
                showNotification('Select a reference voice first.', 'warning');
                return;
            }
            const voiceEntry = findChatterboxVoiceByPath(selection);
            if (!voiceEntry || !voiceEntry.id) {
                showNotification('Unable to resolve that reference voice.', 'warning');
                return;
            }
            if (!window.chatterboxPreviewController) {
                showNotification('Preview controls are still loading. Try again shortly.', 'warning');
                return;
            }
            window.chatterboxPreviewController.toggleById(voiceEntry.id, event.currentTarget);
        });
    }
}

function syncFullStoryOption(chapterCheckbox, force = false) {
    const optionContainer = document.getElementById('full-story-option');
    const fullStoryCheckbox = document.getElementById('full-story-checkbox');
    if (!optionContainer || !chapterCheckbox) {
        return;
    }
    const shouldShow = !!chapterCheckbox.checked;
    if (!force && optionContainer.dataset.visible === String(shouldShow)) {
        return;
    }
    optionContainer.style.display = shouldShow ? 'block' : 'none';
    optionContainer.dataset.visible = String(shouldShow);
    if (!shouldShow && fullStoryCheckbox) {
        fullStoryCheckbox.checked = false;
    }
}

// Engine display name mapping
const engineDisplayNames = {
    'kokoro': 'Kokoro · Local GPU',
    'kokoro_replicate': 'Kokoro · Replicate',
    'chatterbox_turbo_local': 'Chatterbox · Local GPU',
    'chatterbox_turbo_replicate': 'Chatterbox · Replicate'
};

// Update mode indicator based on engine name (called when dropdown changes)
function updateModeIndicator(engineName) {
    const modeEl = document.getElementById('current-mode');
    if (!modeEl) return;
    
    const normalizedEngine = (engineName || 'kokoro').toLowerCase();
    const isLocal = normalizedEngine === 'kokoro' || normalizedEngine === 'chatterbox_turbo_local';
    
    modeEl.textContent = engineDisplayNames[normalizedEngine] || normalizedEngine;
    modeEl.style.color = isLocal ? '#10b981' : '#f59e0b';
}

// Load health status
async function loadHealthStatus() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        
        if (data.success) {
            const engineName = data.tts_engine || 'kokoro';
            updateModeIndicator(engineName);
            document.getElementById('cuda-status').textContent = 
                data.cuda_available ? 'Available' : 'Not Available';
        }
    } catch (error) {
        console.error('Error loading health status:', error);
    }
}

// Analyze text
async function analyzeText(options = {}) {
    const { auto = false } = options;
    if (auto && analyzeInFlight) {
        analyzeRerunRequested = true;
        return false;
    }
    const text = document.getElementById('input-text').value;
    
    if (!text.trim()) {
        alert('Please enter some text first');
        return false;
    }
    
    if (!auto) {
        showNotification('Analyzing text...', 'info');
    }
    
    analyzeInFlight = true;
    analyzeRerunRequested = false;
    try {
        const payload = { text };
        const selectedEngine = getSelectedJobEngine() || runtimeSettings?.tts_engine;
        if (selectedEngine) {
            payload.tts_engine = selectedEngine;
        }
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if (data.success) {
            currentStats = data.statistics;
            displayStatistics(data.statistics);
            updateVoiceAssignments(data.statistics.speakers);
            lastAnalyzedText = text.trim();
            if (!auto) {
                showNotification('Analysis complete', 'success');
            }
            return true;
        } else {
            alert('Error: ' + data.error);
            return false;
        }
    } catch (error) {
        console.error('Error analyzing text:', error);
        if (!auto) {
            alert('Failed to analyze text');
        }
        return false;
    }
    finally {
        const shouldRerun = analyzeRerunRequested;
        analyzeRerunRequested = false;
        analyzeInFlight = false;
        if (shouldRerun) {
            analyzeText({ auto: true });
        }
    }
}

// Display statistics
function displayStatistics(stats) {
    document.getElementById('stat-speakers').textContent = stats.speaker_count;
    document.getElementById('stat-chunks').textContent = stats.total_chunks;
    document.getElementById('stat-words').textContent = stats.word_count;
    
    const duration = Math.floor(stats.estimated_duration);
    const minutes = Math.floor(duration / 60);
    const seconds = duration % 60;
    document.getElementById('stat-duration').textContent = 
        `${minutes}:${seconds.toString().padStart(2, '0')}`;
    
    // Display speakers
    const speakersList = document.getElementById('speakers-list');
    const chapterInfo = document.getElementById('chapter-detection-info');
    const chapterHint = document.getElementById('chapter-detection-hint');
    const chapterCheckbox = document.getElementById('split-chapters-checkbox');
    if (chapterInfo && stats.chapter_detection) {
        const { detected, count, titles } = stats.chapter_detection;
        if (detected) {
            chapterInfo.style.display = 'block';
            const titleList = titles && titles.length ? ` (<em>${titles.slice(0, 5).join(', ')}${titles.length > 5 ? ', …' : ''}</em>)` : '';
            chapterInfo.innerHTML = `📚 Chapters detected: <strong>${count}</strong>${titleList}`;
            if (chapterCheckbox && !chapterCheckbox.dataset.userToggled) {
                chapterCheckbox.disabled = false;
                chapterCheckbox.classList.remove('disabled');
            }
        } else {
            chapterInfo.style.display = 'block';
            chapterInfo.innerHTML = '📚 No chapter headings detected.';
        }
    }
    refreshChapterHint();

    if (stats.has_speaker_tags) {
        speakersList.innerHTML = '<p><strong>Detected Speakers:</strong></p>';
        stats.speakers.forEach(speaker => {
            const tag = document.createElement('span');
            tag.className = 'speaker-tag';
            tag.textContent = speaker;
            speakersList.appendChild(tag);
        });
        
        // Show inline voice assignments
        displayInlineVoiceAssignments(stats.speakers);
    } else {
        speakersList.innerHTML = '<p><em>No speaker tags detected. Using single voice.</em></p>';
        document.getElementById('inline-voice-assignments').style.display = 'none';
    }
    
    document.getElementById('stats-section').style.display = 'block';
}

// Display inline voice assignments in Generate tab
function displayInlineVoiceAssignments(speakers) {
    const container = document.getElementById('inline-voice-assignment-list');
    container.innerHTML = '';
    
    speakers.forEach(speaker => {
        const row = document.createElement('div');
        row.className = 'voice-assignment-row';
        row.dataset.speaker = speaker;
        row.innerHTML = `
            <div class="assignment-header">
                <span class="speaker-label">${speaker}</span>
            </div>
            <div class="assignment-body compact-assignment">
                <div class="assignment-selection-group">
                    <div class="assignment-select voice-select-inline" data-role="kokoro-control">
                        <label>${speaker}</label>
                        <select class="voice-select" data-speaker="${speaker}">
                            <option value="">Select Voice...</option>
                        </select>
                    </div>
                    <div class="assignment-select turbo-inline-control" data-role="turbo-control">
                        <label>Chatterbox Voice Prompt</label>
                        <select class="reference-select" data-speaker="${speaker}">
                            <option value="">Inherit from global selection</option>
                        </select>
                    </div>
                </div>
                <div class="voice-fx-inline voice-inline-card" data-speaker="${speaker}" data-role="kokoro-panel"></div>
            </div>
        `;
        container.appendChild(row);
        const fxContainer = row.querySelector('.voice-fx-inline');
        if (fxContainer) {
            renderFxPanel(fxContainer, speaker, {
                title: `${speaker} FX`,
                showHeader: false,
                useSharedPreview: true
            });
        }
    });
    
    if (window.availableVoices) {
        populateVoiceSelects();
    } else {
        const checkVoices = setInterval(() => {
            if (window.availableVoices) {
                clearInterval(checkVoices);
                populateVoiceSelects();
            }
        }, 100);
    }
    
    document.getElementById('inline-voice-assignments').style.display = 'block';
    populateReferenceSelects();
    updateAssignmentModes(getSelectedJobEngine() || runtimeSettings?.tts_engine || 'kokoro');
}

// Populate voice select dropdowns
function populateVoiceSelects() {
    if (!window.availableVoices) return;
    
    const selects = document.querySelectorAll('#inline-voice-assignment-list .voice-select');
    selects.forEach(select => {
        const previousValue = select.value;
        select.innerHTML = '<option value="">Select Voice...</option>';
        appendVoiceOptions(select);
        restoreSelectValue(select, previousValue);
    });
}

// Generate audio
async function generateAudio() {
    const text = document.getElementById('input-text').value;
    
    if (!text.trim()) {
        alert('Please enter some text first');
        return;
    }
    
    if (text.trim() !== lastAnalyzedText || !currentStats) {
        const analysisSuccess = await analyzeText({ auto: true });
        if (!analysisSuccess) {
            alert('Unable to analyze text for generation');
            return;
        }
        lastAnalyzedText = text.trim();
    }
    
    // Get voice assignments
    let voiceAssignments = getVoiceAssignments();
    
    // If no voice assignments, use default voice for all speakers
    if (Object.keys(voiceAssignments).length === 0) {
        const defaultVoice = document.getElementById('default-voice-select').value;
        if (!defaultVoice) {
            alert('Please assign voices to speakers or select a default voice');
            return;
        }
        
        const langCode = getLangCodeForVoice(defaultVoice);
        if (currentStats.speakers && currentStats.speakers.length > 0) {
            currentStats.speakers.forEach(speaker => {
                voiceAssignments[speaker] = createAssignment(defaultVoice, langCode, speaker);
            });
        } else {
            voiceAssignments['default'] = createAssignment(defaultVoice, langCode, 'default');
        }
    }
    
    console.log('Voice assignments for generation:', voiceAssignments);
    
    const splitByChapter = document.getElementById('split-chapters-checkbox')?.checked || false;
    const generateFullStory = splitByChapter && (document.getElementById('full-story-checkbox')?.checked || false);
    const outputFormat = document.getElementById('job-output-format')?.value || undefined;
    const outputBitrate = document.getElementById('job-output-bitrate')?.value || undefined;

    const selectedEngine = getSelectedJobEngine() || runtimeSettings?.tts_engine;
    const payload = {
        text,
        split_by_chapter: splitByChapter,
        generate_full_story: generateFullStory,
        voice_assignments: voiceAssignments,
        review_mode: true  // Always enabled - chunk review happens in library
    };
    if (selectedEngine) {
        payload.tts_engine = selectedEngine;
        const overrides = collectEngineOverrides(selectedEngine);
        if (overrides) {
            payload.engine_options = overrides;
        }
    }
    if (outputFormat) {
        payload.output_format = outputFormat;
    }
    if (outputFormat === 'mp3' && outputBitrate) {
        payload.output_bitrate_kbps = parseInt(outputBitrate, 10);
    }
    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success notification
            showNotification(`Job queued! Position: ${data.queue_position}`, 'success');
            
            // Update queue indicator
            updateQueueIndicator();
            
        } else {
            alert('Error: ' + data.error);
        }
    } catch (error) {
        console.error('Error generating audio:', error);
        alert('Failed to generate audio');
    }
}

// Show notification
function showNotification(message, type = 'info') {
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.textContent = message;
    document.body.appendChild(notification);
    
    setTimeout(() => {
        notification.classList.add('show');
    }, 10);
    
    setTimeout(() => {
        notification.classList.remove('show');
        setTimeout(() => notification.remove(), 300);
    }, 3000);
}

// Update queue indicator
async function updateQueueIndicator() {
    if (queuePollInFlight) {
        return;
    }
    queuePollInFlight = true;
    try {
        const response = await fetch('/api/queue');
        const data = await response.json();
        
        if (data.success) {
            const indicator = document.getElementById('queue-indicator');
            const queueSize = data.queue_size;
            const processingJobs = data.jobs.filter(j => j.status === 'processing').length;
            if (typeof updateLatestAudioFromQueue === 'function') {
                updateLatestAudioFromQueue(data.jobs);
            }
            
            if (queueSize > 0 || processingJobs > 0) {
                indicator.style.display = 'inline-block';
                indicator.textContent = `${processingJobs} processing, ${queueSize} queued`;
            } else {
                indicator.style.display = 'none';
            }
        }
    } catch (error) {
        console.error('Error updating queue indicator:', error);
    } finally {
        queuePollInFlight = false;
    }
}

// Start periodic queue indicator updates
setInterval(updateQueueIndicator, 2000);
updateQueueIndicator();

// These functions previously handled inline job progress; in queue mode we
// only need a lightweight hook to update the latest-audio player.

function updateLatestAudioFromQueue(jobs) {
    if (!Array.isArray(jobs) || jobs.length === 0) {
        const container = document.getElementById('latest-audio-container');
        if (container) {
            container.style.display = 'none';
        }
        return;
    }

    // Jobs are already sorted newest-first in /api/queue
    const latestCompleted = jobs.find(j => j.status === 'completed' && j.output_file);
    const container = document.getElementById('latest-audio-container');
    const player = document.getElementById('latest-audio-player');
    const label = document.getElementById('latest-audio-label');

    if (!latestCompleted || !container || !player || !label) {
        if (container) {
            container.style.display = 'none';
        }
        return;
    }

    container.style.display = 'block';
    label.textContent = `Most recently completed job (${latestCompleted.job_id})`;
    
    if (player.src !== window.location.origin + latestCompleted.output_file) {
        player.src = latestCompleted.output_file;
        player.load();
    }
}

// These functions are kept for backward compatibility but not used in queue mode
function downloadAudio() {
    if (!currentJobId) {
        alert('No audio to download');
        return;
    }
    window.location.href = `/api/download/${currentJobId}`;
}

function resetGeneration() {
    // Not used in queue mode
}

function displayResult(outputFile) {
    // Not used in queue mode - check Job Queue tab instead
    console.log('Job completed:', outputFile);
}

function pollJobStatus(jobId) {
    // Not used in queue mode - Job Queue tab handles monitoring
}

function simulateProgressWithEstimate(estimatedSeconds) {
    // Not used in queue mode
}

function resetVoiceAssignments() {
    const inputText = document.getElementById('input-text')?.value || '';
    const shouldProceed = inputText.trim()
        ? confirm('Reset all speaker assignments and FX settings? You can re-run Analyze Text afterwards.')
        : true;
    if (!shouldProceed) {
        return;
    }

    Object.keys(voiceFxState).forEach(key => {
        if (!voiceFxState[key]) {
            voiceFxState[key] = {
                pitch: DEFAULT_FX_STATE.pitch,
                speed: DEFAULT_FX_STATE.speed,
                sampleText: DEFAULT_FX_STATE.sampleText
            };
        } else {
            // Ensure legacy objects get any new defaults
            voiceFxState[key] = {
                pitch: Number.isFinite(voiceFxState[key].pitch) ? voiceFxState[key].pitch : DEFAULT_FX_STATE.pitch,
                speed: Number.isFinite(voiceFxState[key].speed) ? voiceFxState[key].speed : DEFAULT_FX_STATE.speed,
                sampleText: voiceFxState[key].sampleText ?? DEFAULT_FX_STATE.sampleText
            };
        }
    });

    const inlineAssignments = document.getElementById('inline-voice-assignments');
    if (inlineAssignments) {
        inlineAssignments.style.display = 'none';
    }
    const assignmentList = document.getElementById('inline-voice-assignment-list');
    if (assignmentList) {
        assignmentList.innerHTML = '';
    }
    const speakersList = document.getElementById('speakers-list');
    if (speakersList) {
        speakersList.innerHTML = '<p><em>No speaker tags detected. Run Analyze Text to rebuild assignments.</em></p>';
    }
    const statsSection = document.getElementById('stats-section');
    if (statsSection) {
        statsSection.style.display = 'none';
    }

    currentStats = null;
    lastAnalyzedText = '';
    initDefaultVoiceFxPanel();
    showNotification('Assignments reset. Run Analyze Text again when you\'re ready.', 'info');
}

// Populate default voice selector
function populateDefaultVoiceSelect() {
    const select = document.getElementById('default-voice-select');
    if (!select || !window.availableVoices) {
        return;
    }

    const previousValue = select.value;
    select.innerHTML = '<option value="">Select Default Voice...</option>';
    appendVoiceOptions(select);
    restoreSelectValue(select, previousValue);
}

function appendVoiceOptions(selectElement) {
    Object.values(window.availableVoices).forEach(voiceConfig => {
        if (!voiceConfig) return;
        const baseOptgroup = document.createElement('optgroup');
        baseOptgroup.label = voiceConfig.language || 'Voices';
        
        voiceConfig.voices.forEach(voiceName => {
            const option = document.createElement('option');
            option.value = voiceName;
            option.textContent = voiceName;
            baseOptgroup.appendChild(option);
        });
        
        selectElement.appendChild(baseOptgroup);
        
        const customVoices = voiceConfig.custom_voices || [];
        if (customVoices.length) {
            const customGroup = document.createElement('optgroup');
            customGroup.label = `${voiceConfig.language || 'Voices'} — Custom Blends`;
            
            customVoices.forEach(entry => {
                const option = document.createElement('option');
                option.value = entry.code;
                option.textContent = entry.name || entry.code;
                option.dataset.customVoice = 'true';
                customGroup.appendChild(option);
            });
            
            selectElement.appendChild(customGroup);
        }
    });
}

function restoreSelectValue(selectElement, previousValue) {
    if (!previousValue) {
        return;
    }
    const options = Array.from(selectElement.options);
    const match = options.find(option => option.value === previousValue);
    if (match) {
        selectElement.value = previousValue;
    }
}

// Helper function to get lang_code for a voice
function getLangCodeForVoice(voiceName) {
    if (!voiceName) {
        return 'a';
    }

    if (window.customVoiceMap && window.customVoiceMap[voiceName]) {
        return window.customVoiceMap[voiceName].lang_code || 'a';
    }

    if (!window.availableVoices) return 'a';
    
    for (const [key, voiceConfig] of Object.entries(window.availableVoices)) {
        if (voiceConfig.voices.includes(voiceName)) {
            return voiceConfig.lang_code;
        }
    }
    return 'a'; // Default to American English
}

// Get voice assignments from UI (from inline assignments in Generate tab)
function buildTurboSelectionMap() {
    const map = {};
    document.querySelectorAll('#inline-voice-assignment-list .voice-assignment-row').forEach(row => {
        const speaker = row.dataset.speaker;
        if (!speaker) return;
        const reference = row.querySelector('.reference-select')?.value.trim();
        map[speaker] = {
            reference: reference || ''
        };
    });
    return map;
}

function applyTurboSelections(assignments, turboSelections, globalReference) {
    Object.entries(assignments).forEach(([speakerKey, assignment]) => {
        const selection = turboSelections[speakerKey] || {};
        const resolvedReference = selection.reference || globalReference || '';
        if (!assignment.audio_prompt_path && resolvedReference) {
            assignment.audio_prompt_path = resolvedReference;
        }
    });
}

function buildTurboAssignment(speakerKey, referencePath) {
    const assignment = {};
    if (referencePath) {
        assignment.audio_prompt_path = referencePath;
    }
    const fxPayload = getFxPayload(speakerKey);
    if (fxPayload) {
        assignment.fx = fxPayload;
    }
    const state = getFxState(speakerKey);
    const speedValue = Number(state?.speed) || 1;
    if (Math.abs(speedValue - 1) > 0.01) {
        assignment.speed = Number(speedValue.toFixed(2));
    }
    return Object.keys(assignment).length ? assignment : null;
}

function getVoiceAssignments() {
    const assignments = {};
    const selects = document.querySelectorAll('#inline-voice-assignment-list .voice-select');
    const engineName = getSelectedJobEngine() || runtimeSettings?.tts_engine || 'kokoro';
    const turboEnabled = isTurboEngine(engineName);
    const turboSelections = turboEnabled ? buildTurboSelectionMap() : {};
    const globalReference = turboEnabled ? getGlobalReferenceSelection() : '';

    selects.forEach(select => {
        const speaker = select.dataset.speaker;
        const voiceName = select.value;
        
        if (voiceName && window.availableVoices) {
            const langCode = getLangCodeForVoice(voiceName);
            assignments[speaker] = createAssignment(voiceName, langCode, speaker);
        }
    });

    if (turboEnabled) {
        if (Object.keys(assignments).length) {
            applyTurboSelections(assignments, turboSelections, globalReference);
        } else {
            const targets = (currentStats?.speakers && currentStats.speakers.length)
                ? currentStats.speakers
                : ['default'];
            targets.forEach(speakerKey => {
                const selection = turboSelections[speakerKey] || {};
                const resolvedReference = selection.reference || globalReference || '';
                const turboAssignment = buildTurboAssignment(speakerKey, resolvedReference);
                if (turboAssignment) {
                    assignments[speakerKey] = turboAssignment;
                }
            });
        }
    }
    
    return assignments;
}

// Update voice assignments UI
function updateVoiceAssignments(speakers) {
    const container = document.getElementById('voice-assignments');
    if (!container) {
        return;
    }
    
    if (!speakers || speakers.length === 0) {
        container.innerHTML = '<p><em>No speakers detected. Analyze text first.</em></p>';
        return;
    }
    
    container.innerHTML = '';
    
    speakers.forEach(speaker => {
        const assignment = createVoiceAssignment(speaker);
        container.appendChild(assignment);
    });
}

// Create voice assignment element
function createVoiceAssignment(speaker) {
    const div = document.createElement('div');
    div.className = 'voice-assignment';
    div.dataset.speaker = speaker;
    
    div.innerHTML = `
        <h3>${speaker}</h3>
        <div class="voice-selector">
            <div style="flex: 1;">
                <label>Language</label>
                <select class="lang-select">
                    <option value="a">American English</option>
                    <option value="b">British English</option>
                    <option value="f">French</option>
                    <option value="h">Hindi</option>
                    <option value="i">Italian</option>
                    <option value="j">Japanese</option>
                    <option value="z">Chinese</option>
                </select>
            </div>
            <div style="flex: 1;">
                <label>Voice</label>
                <select class="voice-select">
                    <option value="af_heart">af_heart</option>
                    <option value="af_bella">af_bella</option>
                    <option value="af_nicole">af_nicole</option>
                    <option value="af_sarah">af_sarah</option>
                    <option value="af_sky">af_sky</option>
                    <option value="am_adam">am_adam</option>
                    <option value="am_michael">am_michael</option>
                    <option value="bf_emma">bf_emma</option>
                    <option value="bf_isabella">bf_isabella</option>
                    <option value="bm_george">bm_george</option>
                    <option value="bm_lewis">bm_lewis</option>
                </select>
            </div>
        </div>
    `;
    
    return div;
}

// Cancel generation (not used in queue mode - use Job Queue tab instead)
async function cancelGeneration() {
    // Redirect to queue tab
    showNotification('Please use the Job Queue tab to cancel jobs', 'info');
}
