// Settings Management

const geminiPresetState = {
    list: [],
    editingId: null,
    isPersisting: false,
};

document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    setupSettingsListeners();
});

function normalizeGeminiPreset(preset, fallbackIndex = 0) {
    if (!preset || typeof preset !== 'object') {
        return null;
    }
    const title = (preset.title || '').trim();
    const prompt = (preset.prompt || '').trim();
    if (!title || !prompt) {
        return null;
    }
    let id = (preset.id || '').trim();
    if (!id) {
        id = typeof crypto !== 'undefined' && crypto.randomUUID
            ? crypto.randomUUID()
            : `preset-${Date.now()}-${fallbackIndex}`;
    }
    return { id, title, prompt };
}

function sanitizeGeminiPreset(preset) {
    if (!preset) return null;
    return {
        id: preset.id,
        title: preset.title,
        prompt: preset.prompt,
    };
}

async function persistGeminiPresets(feedbackMessage) {
    if (geminiPresetState.isPersisting) {
        return;
    }
    geminiPresetState.isPersisting = true;
    const payload = geminiPresetState.list
        .map(sanitizeGeminiPreset)
        .filter(Boolean);
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ gemini_prompt_presets: payload }),
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to save presets');
        }
        window.dispatchEvent(new CustomEvent('geminiPresets:changed', {
            detail: {
                presets: payload
            }
        }));
        if (feedbackMessage) {
            updateGeminiPresetHint(feedbackMessage, 'success');
        }
    } catch (error) {
        console.error('Failed to persist Gemini presets', error);
        updateGeminiPresetHint('Preset list updated locally but failed to save. Try again.', 'warning');
    } finally {
        geminiPresetState.isPersisting = false;
    }
}

function setGeminiPresetState(presets = []) {
    const normalized = [];
    if (Array.isArray(presets)) {
        presets.forEach((preset, index) => {
            const normalizedPreset = normalizeGeminiPreset(preset, index);
            if (normalizedPreset) {
                normalized.push(normalizedPreset);
            }
        });
    }
    geminiPresetState.list = normalized;
    geminiPresetState.editingId = null;
    renderGeminiPresetList();
    resetGeminiPresetForm(true);
    updateGeminiPresetHint('Fill both fields to create a new preset, or select Edit on an existing preset.');
}

function renderGeminiPresetList() {
    const listEl = document.getElementById('gemini-preset-list');
    if (!listEl) return;
    listEl.innerHTML = '';
    if (!geminiPresetState.list.length) {
        const empty = document.createElement('div');
        empty.className = 'gemini-preset-empty';
        empty.textContent = listEl.dataset.emptyText || 'No prompt presets yet.';
        listEl.appendChild(empty);
        return;
    }

    geminiPresetState.list.forEach(preset => {
        const item = document.createElement('div');
        item.className = 'gemini-preset-item';
        item.title = preset.prompt;
        item.dataset.id = preset.id;

        const meta = document.createElement('div');
        meta.className = 'gemini-preset-meta';
        const titleEl = document.createElement('div');
        titleEl.className = 'gemini-preset-title';
        titleEl.textContent = preset.title;
        meta.appendChild(titleEl);

        const actions = document.createElement('div');
        actions.className = 'gemini-preset-actions';
        const editBtn = document.createElement('button');
        editBtn.type = 'button';
        editBtn.className = 'btn btn-secondary btn-xs';
        editBtn.dataset.action = 'edit';
        editBtn.dataset.id = preset.id;
        editBtn.textContent = 'Edit';
        const deleteBtn = document.createElement('button');
        deleteBtn.type = 'button';
        deleteBtn.className = 'btn btn-ghost btn-xs';
        deleteBtn.dataset.action = 'delete';
        deleteBtn.dataset.id = preset.id;
        deleteBtn.textContent = 'Delete';
        actions.appendChild(editBtn);
        actions.appendChild(deleteBtn);

        item.appendChild(meta);
        item.appendChild(actions);
        listEl.appendChild(item);
    });
}

function getGeminiPresetTitleInput() {
    return document.getElementById('gemini-preset-title');
}

function getGeminiPresetTextInput() {
    return document.getElementById('gemini-preset-text');
}

function getGeminiPresetHintEl() {
    return document.getElementById('gemini-preset-form-hint');
}

function updateGeminiPresetHint(message, tone = 'muted') {
    const hintEl = getGeminiPresetHintEl();
    if (!hintEl) return;
    hintEl.textContent = message;
    hintEl.dataset.tone = tone;
}

function resetGeminiPresetForm(skipHintUpdate = false) {
    const titleInput = getGeminiPresetTitleInput();
    const textInput = getGeminiPresetTextInput();
    if (titleInput) titleInput.value = '';
    if (textInput) textInput.value = '';
    geminiPresetState.editingId = null;
    if (!skipHintUpdate) {
        updateGeminiPresetHint('Fill both fields to create a new preset, or select Edit on an existing preset.');
    } else {
        const hintEl = getGeminiPresetHintEl();
        if (hintEl) {
            hintEl.dataset.tone = 'muted';
        }
    }
}

async function handleGeminiPresetSave() {
    const titleInput = getGeminiPresetTitleInput();
    const textInput = getGeminiPresetTextInput();
    if (!titleInput || !textInput) return;
    const title = titleInput.value.trim();
    const prompt = textInput.value.trim();
    if (!title || !prompt) {
        updateGeminiPresetHint('Both title and prompt are required.', 'warning');
        return;
    }

    if (geminiPresetState.editingId) {
        const idx = geminiPresetState.list.findIndex(preset => preset.id === geminiPresetState.editingId);
        if (idx !== -1) {
            geminiPresetState.list[idx] = {
                ...geminiPresetState.list[idx],
                title,
                prompt,
            };
        }
        renderGeminiPresetList();
        await persistGeminiPresets(`Updated preset "${title}".`);
    } else {
        const newPreset = {
            id: typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `preset-${Date.now()}`,
            title,
            prompt,
        };
        geminiPresetState.list.push(newPreset);
        renderGeminiPresetList();
        await persistGeminiPresets(`Added preset "${title}".`);
    }

    geminiPresetState.editingId = null;
    resetGeminiPresetForm(true);
}

async function handleGeminiPresetListClick(event) {
    const action = event.target?.dataset?.action;
    const presetId = event.target?.dataset?.id;
    if (!action || !presetId) return;
    if (action === 'edit') {
        const preset = geminiPresetState.list.find(entry => entry.id === presetId);
        if (!preset) return;
        const titleInput = getGeminiPresetTitleInput();
        const textInput = getGeminiPresetTextInput();
        if (titleInput) titleInput.value = preset.title;
        if (textInput) textInput.value = preset.prompt;
        geminiPresetState.editingId = presetId;
        updateGeminiPresetHint(`Editing preset "${preset.title}". Save to apply changes or Clear to cancel.`, 'info');
    } else if (action === 'delete') {
        const index = geminiPresetState.list.findIndex(entry => entry.id === presetId);
        if (index === -1) return;
        const [removed] = geminiPresetState.list.splice(index, 1);
        if (geminiPresetState.editingId === presetId) {
            geminiPresetState.editingId = null;
            resetGeminiPresetForm(true);
        }
        renderGeminiPresetList();
        await persistGeminiPresets(`Deleted preset "${removed.title}".`);
    }
}

function handleGeminiPresetReset() {
    resetGeminiPresetForm();
    updateGeminiPresetHint('Cleared preset form.', 'info');
}

function toggleEngineSettingsSections(engineName) {
    // With the new tabbed UI, we auto-switch to the relevant engine tab when the default engine changes
    const engineTabMap = {
        'kokoro': 'kokoro',
        'kokoro_replicate': 'kokoro',
        'chatterbox_turbo_local': 'chatterbox-local',
        'chatterbox_turbo_replicate': 'chatterbox-replicate',
        'voxcpm_local': 'voxcpm',
        'qwen3_custom': 'qwen3',
        'qwen3_clone': 'qwen3'
    };
    
    const targetTab = engineTabMap[engineName];
    if (targetTab) {
        const tabBtn = document.querySelector(`.engine-tab-btn[data-engine-tab="${targetTab}"]`);
        if (tabBtn) {
            tabBtn.click();
        }
    }
}

// Setup event listeners
function setupSettingsListeners() {
    // Speed slider
    const speedSlider = document.getElementById('speed');
    const speedValue = document.getElementById('speed-value');
    speedSlider.addEventListener('input', (e) => {
        speedValue.textContent = e.target.value + 'x';
    });
    
    // Save settings
    document.getElementById('save-settings-btn').addEventListener('click', saveSettings);
    
    // Reset settings
    document.getElementById('reset-settings-btn').addEventListener('click', resetSettings);

    const fetchGeminiModelsBtn = document.getElementById('fetch-gemini-models-btn');
    if (fetchGeminiModelsBtn) {
        fetchGeminiModelsBtn.addEventListener('click', () => fetchGeminiModels(fetchGeminiModelsBtn));
    }

    const ttsEngineSelect = document.getElementById('settings-tts-engine');
    if (ttsEngineSelect) {
        ttsEngineSelect.addEventListener('change', (event) => {
            const engineName = (event.target.value || '').toLowerCase();
            toggleEngineSettingsSections(engineName);
        });
    }

    const defaultFormatSelect = document.getElementById('settings-output-format');
    if (defaultFormatSelect) {
        defaultFormatSelect.addEventListener('change', () => {
            updateSettingsBitrateState();
        });
    }

    const presetSaveBtn = document.getElementById('save-gemini-preset-btn');
    if (presetSaveBtn) {
        presetSaveBtn.addEventListener('click', handleGeminiPresetSave);
    }
    const presetResetBtn = document.getElementById('reset-gemini-preset-btn');
    if (presetResetBtn) {
        presetResetBtn.addEventListener('click', handleGeminiPresetReset);
    }
    const presetList = document.getElementById('gemini-preset-list');
    if (presetList) {
        presetList.addEventListener('click', handleGeminiPresetListClick);
    }

    // Settings accordion collapse/expand
    setupSettingsAccordion();
    
    // Engine sub-tabs within Engine Settings
    setupEngineTabSwitching();
}

// Settings accordion toggle
function setupSettingsAccordion() {
    const headers = document.querySelectorAll('.settings-group-header[data-toggle="settings-group"]');
    headers.forEach(header => {
        header.addEventListener('click', () => {
            const group = header.closest('.settings-group');
            if (group) {
                group.classList.toggle('collapsed');
            }
        });
    });
}

// Engine tab switching within Engine Settings group
function setupEngineTabSwitching() {
    const tabButtons = document.querySelectorAll('.engine-tab-btn[data-engine-tab]');
    tabButtons.forEach(btn => {
        btn.addEventListener('click', () => {
            const targetTab = btn.dataset.engineTab;
            
            // Update button states
            tabButtons.forEach(b => b.classList.remove('active'));
            btn.classList.add('active');
            
            // Update panel visibility
            const panels = document.querySelectorAll('.engine-panel');
            panels.forEach(panel => {
                panel.classList.remove('active');
            });
            
            const targetPanel = document.getElementById(`engine-panel-${targetTab}`);
            if (targetPanel) {
                targetPanel.classList.add('active');
            }
        });
    });
}

function updateSettingsBitrateState() {
    const formatSelect = document.getElementById('settings-output-format');
    const bitrateSelect = document.getElementById('settings-output-bitrate');
    if (!formatSelect || !bitrateSelect) return;
    const isMp3 = (formatSelect.value || '').toLowerCase() === 'mp3';
    bitrateSelect.disabled = !isMp3;
    bitrateSelect.parentElement?.classList.toggle('disabled', !isMp3);
}

async function fetchGeminiModels(buttonEl) {
    const apiKeyInput = document.getElementById('gemini-api-key');
    const statusEl = document.getElementById('gemini-models-status');
    const modelsSelect = document.getElementById('gemini-model');

    if (!apiKeyInput || !modelsSelect) return;

    const apiKey = apiKeyInput.value.trim();
    if (!apiKey) {
        if (statusEl) {
            statusEl.textContent = 'Enter your Gemini API key first, then try again.';
        }
        return;
    }

    const originalLabel = buttonEl ? buttonEl.textContent : '';
    if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.textContent = 'Fetching models...';
    }
    if (statusEl) {
        statusEl.textContent = 'Contacting Gemini to list available models...';
    }

    try {
        const response = await fetch('/api/gemini/models', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ api_key: apiKey })
        });

        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Unable to fetch models');
        }

        const models = data.models || [];
        if (!models.length) {
            throw new Error('No models were returned. Verify your API key.');
        }

        const previousValue = modelsSelect.value;
        modelsSelect.innerHTML = '';
        models.forEach(modelName => {
            const option = document.createElement('option');
            option.value = modelName;
            option.textContent = modelName;
            modelsSelect.appendChild(option);
        });

        if (models.includes(previousValue)) {
            modelsSelect.value = previousValue;
        }

        if (statusEl) {
            statusEl.textContent = `Loaded ${models.length} models from Gemini.`;
        }
    } catch (error) {
        console.error('Failed to fetch Gemini models:', error);
        if (statusEl) {
            statusEl.textContent = error.message || 'Unable to fetch models. Check the console for details.';
        }
    } finally {
        if (buttonEl) {
            buttonEl.disabled = false;
            buttonEl.textContent = originalLabel || 'Fetch Available Models';
        }
    }
}

// Load settings from API
async function loadSettings() {
    try {
        const response = await fetch('/api/settings');
        const data = await response.json();
        
        if (data.success) {
            applySettings(data.settings);
        }
    } catch (error) {
        console.error('Error loading settings:', error);
    }
}

function setElementValue(id, value, fallback = '') {
    const el = document.getElementById(id);
    if (!el) return;
    el.value = value ?? fallback ?? '';
}

function setElementText(id, text, fallback = '') {
    const el = document.getElementById(id);
    if (!el) return;
    el.textContent = text ?? fallback ?? '';
}

function setCheckboxValue(id, checked, fallback = false) {
    const el = document.getElementById(id);
    if (!el) return;
    el.checked = checked ?? fallback;
}

// Apply settings to UI
function applySettings(settings) {
    // Kokoro Replicate API Key
    if (settings.replicate_api_key) {
        setElementValue('kokoro-replicate-api-key', settings.replicate_api_key);
    }
    
    // Chunk size
    setElementValue('chunk-size', settings.chunk_size ?? 500, 500);
    
    // Speed
    const speed = settings.speed || 1.0;
    setElementValue('speed', speed, 1.0);
    setElementText('speed-value', speed + 'x', '1.0x');
    
    // Default output format / bitrate
    const defaultFormat = (settings.output_format || 'mp3').toLowerCase();
    setElementValue('settings-output-format', defaultFormat, 'mp3');
    const defaultBitrateValue = settings.output_bitrate_kbps ?? 128;
    setElementValue('settings-output-bitrate', String(defaultBitrateValue), '128');
    updateSettingsBitrateState();
    
    // Crossfade
    setElementValue('crossfade', settings.crossfade_duration ?? 0.1, 0.1);
    
    // Silence controls
    setElementValue('intro-silence', settings.intro_silence_ms ?? 0, 0);
    setElementValue('inter-silence', settings.inter_chunk_silence_ms ?? 0, 0);

    // Parallel processing
    setElementValue('parallel-chunks', settings.parallel_chunks ?? 3, 3);

    // VRAM cleanup setting
    const cleanupVramCheckbox = document.getElementById('cleanup-vram-after-job');
    if (cleanupVramCheckbox) {
        cleanupVramCheckbox.checked = settings.cleanup_vram_after_job ?? false;
    }

    // Gemini settings
    setElementValue('gemini-api-key', settings.gemini_api_key || '');
    const geminiModelSelect = document.getElementById('gemini-model');
    const savedGeminiModel = settings.gemini_model || 'gemini-1.5-flash';

    if (geminiModelSelect && savedGeminiModel) {
        const hasOption = Array.from(geminiModelSelect.options).some(option => option.value === savedGeminiModel);
        if (!hasOption) {
            const customOption = document.createElement('option');
            customOption.value = savedGeminiModel;
            customOption.textContent = savedGeminiModel;
            geminiModelSelect.appendChild(customOption);
        }
        geminiModelSelect.value = savedGeminiModel;
    }
    setElementValue('gemini-prompt', settings.gemini_prompt || '');
    setGeminiPresetState(settings.gemini_prompt_presets || []);

    // Engine + Chatterbox settings
    const ttsEngineSelect = document.getElementById('settings-tts-engine');
    const preferredEngine = (settings.tts_engine || 'kokoro').toLowerCase();
    if (ttsEngineSelect) {
        ttsEngineSelect.value = preferredEngine;
    }
    toggleEngineSettingsSections(preferredEngine);

    // Chatterbox Local settings
    const localDeviceInput = document.getElementById('chatterbox-turbo-local-device');
    if (localDeviceInput) {
        localDeviceInput.value = settings.chatterbox_turbo_local_device || 'auto';
    }
    const localPromptInput = document.getElementById('chatterbox-turbo-local-prompt');
    if (localPromptInput) {
        localPromptInput.value = settings.chatterbox_turbo_local_default_prompt || '';
    }
    const localTemp = document.getElementById('chatterbox-turbo-local-temperature');
    if (localTemp) {
        localTemp.value = settings.chatterbox_turbo_local_temperature ?? 0.8;
    }
    const localTopP = document.getElementById('chatterbox-turbo-local-top-p');
    if (localTopP) {
        localTopP.value = settings.chatterbox_turbo_local_top_p ?? 0.95;
    }
    const localTopK = document.getElementById('chatterbox-turbo-local-top-k');
    if (localTopK) {
        localTopK.value = settings.chatterbox_turbo_local_top_k ?? 1000;
    }
    const localRepPenalty = document.getElementById('chatterbox-turbo-local-rep-penalty');
    if (localRepPenalty) {
        localRepPenalty.value = settings.chatterbox_turbo_local_repetition_penalty ?? 1.2;
    }
    const localCfg = document.getElementById('chatterbox-turbo-local-cfg-weight');
    if (localCfg) {
        localCfg.value = settings.chatterbox_turbo_local_cfg_weight ?? 0.0;
    }
    const localExaggeration = document.getElementById('chatterbox-turbo-local-exaggeration');
    if (localExaggeration) {
        localExaggeration.value = settings.chatterbox_turbo_local_exaggeration ?? 0.0;
    }
    const localNorm = document.getElementById('chatterbox-turbo-local-norm');
    if (localNorm) {
        localNorm.checked = settings.chatterbox_turbo_local_norm_loudness !== false;
    }
    const localPromptNorm = document.getElementById('chatterbox-turbo-local-prompt-norm');
    if (localPromptNorm) {
        localPromptNorm.checked = settings.chatterbox_turbo_local_prompt_norm_loudness !== false;
    }
    const localChunkSize = document.getElementById('chatterbox-turbo-local-chunk-size');
    if (localChunkSize) {
        localChunkSize.value = settings.chatterbox_turbo_local_chunk_size ?? 450;
    }

    // VoxCPM Local settings
    const voxcpmModel = document.getElementById('voxcpm-local-model-id');
    if (voxcpmModel) {
        voxcpmModel.value = settings.voxcpm_local_model_id || 'openbmb/VoxCPM1.5';
    }
    const voxcpmDevice = document.getElementById('voxcpm-local-device');
    if (voxcpmDevice) {
        voxcpmDevice.value = settings.voxcpm_local_device || 'auto';
    }
    const voxcpmPrompt = document.getElementById('voxcpm-local-prompt');
    if (voxcpmPrompt) {
        voxcpmPrompt.value = settings.voxcpm_local_default_prompt || '';
    }
    const voxcpmPromptText = document.getElementById('voxcpm-local-prompt-text');
    if (voxcpmPromptText) {
        voxcpmPromptText.value = settings.voxcpm_local_default_prompt_text || '';
    }
    const voxcpmCfg = document.getElementById('voxcpm-local-cfg');
    if (voxcpmCfg) {
        voxcpmCfg.value = settings.voxcpm_local_cfg_value ?? 2.5;
    }
    const voxcpmSteps = document.getElementById('voxcpm-local-steps');
    if (voxcpmSteps) {
        voxcpmSteps.value = settings.voxcpm_local_inference_timesteps ?? 20;
    }
    const voxcpmNormalize = document.getElementById('voxcpm-local-normalize');
    if (voxcpmNormalize) {
        voxcpmNormalize.checked = settings.voxcpm_local_normalize !== false;
    }
    const voxcpmDenoise = document.getElementById('voxcpm-local-denoise');
    if (voxcpmDenoise) {
        voxcpmDenoise.checked = settings.voxcpm_local_denoise === true;
    }

    // Qwen3 CustomVoice settings
    const qwen3Model = document.getElementById('qwen3-custom-model-id');
    if (qwen3Model) {
        qwen3Model.value = settings.qwen3_custom_model_id || 'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice';
    }
    const qwen3Device = document.getElementById('qwen3-custom-device');
    if (qwen3Device) {
        qwen3Device.value = settings.qwen3_custom_device || 'auto';
    }
    const qwen3Dtype = document.getElementById('qwen3-custom-dtype');
    if (qwen3Dtype) {
        qwen3Dtype.value = settings.qwen3_custom_dtype || 'bfloat16';
    }
    const qwen3Attn = document.getElementById('qwen3-custom-attn');
    if (qwen3Attn) {
        qwen3Attn.value = settings.qwen3_custom_attn_implementation || 'flash_attention_2';
    }
    const qwen3Language = document.getElementById('qwen3-custom-language');
    if (qwen3Language) {
        qwen3Language.value = settings.qwen3_custom_default_language || 'Auto';
    }
    const qwen3Instruct = document.getElementById('qwen3-custom-instruct');
    if (qwen3Instruct) {
        qwen3Instruct.value = settings.qwen3_custom_default_instruct || '';
    }

    // Qwen3 Voice Clone settings
    const qwen3CloneModel = document.getElementById('qwen3-clone-model-id');
    if (qwen3CloneModel) {
        qwen3CloneModel.value = settings.qwen3_clone_model_id || 'Qwen/Qwen3-TTS-12Hz-1.7B-Base';
    }
    const qwen3CloneDevice = document.getElementById('qwen3-clone-device');
    if (qwen3CloneDevice) {
        qwen3CloneDevice.value = settings.qwen3_clone_device || 'auto';
    }
    const qwen3CloneDtype = document.getElementById('qwen3-clone-dtype');
    if (qwen3CloneDtype) {
        qwen3CloneDtype.value = settings.qwen3_clone_dtype || 'bfloat16';
    }
    const qwen3CloneAttn = document.getElementById('qwen3-clone-attn');
    if (qwen3CloneAttn) {
        qwen3CloneAttn.value = settings.qwen3_clone_attn_implementation || 'flash_attention_2';
    }
    const qwen3CloneLanguage = document.getElementById('qwen3-clone-language');
    if (qwen3CloneLanguage) {
        qwen3CloneLanguage.value = settings.qwen3_clone_default_language || 'Auto';
    }
    const qwen3ClonePrompt = document.getElementById('qwen3-clone-prompt');
    if (qwen3ClonePrompt) {
        qwen3ClonePrompt.value = settings.qwen3_clone_default_prompt || '';
    }
    const qwen3ClonePromptText = document.getElementById('qwen3-clone-prompt-text');
    if (qwen3ClonePromptText) {
        qwen3ClonePromptText.value = settings.qwen3_clone_default_prompt_text || '';
    }

    // Chatterbox Replicate settings (uses shared replicate_api_key)
    const turboModelInput = document.getElementById('chatterbox-turbo-replicate-model');
    if (turboModelInput) {
        turboModelInput.value = settings.chatterbox_turbo_replicate_model || '';
    }
    const turboVoiceInput = document.getElementById('chatterbox-turbo-replicate-voice');
    if (turboVoiceInput) {
        turboVoiceInput.value = settings.chatterbox_turbo_replicate_voice || '';
    }
    const turboTempInput = document.getElementById('chatterbox-turbo-replicate-temperature');
    if (turboTempInput) {
        turboTempInput.value = settings.chatterbox_turbo_replicate_temperature ?? 0.8;
    }
    const turboTopPInput = document.getElementById('chatterbox-turbo-replicate-top-p');
    if (turboTopPInput) {
        turboTopPInput.value = settings.chatterbox_turbo_replicate_top_p ?? 0.95;
    }
    const turboTopKInput = document.getElementById('chatterbox-turbo-replicate-top-k');
    if (turboTopKInput) {
        turboTopKInput.value = settings.chatterbox_turbo_replicate_top_k ?? 1000;
    }
    const turboRepPenaltyInput = document.getElementById('chatterbox-turbo-replicate-rep-penalty');
    if (turboRepPenaltyInput) {
        turboRepPenaltyInput.value = settings.chatterbox_turbo_replicate_repetition_penalty ?? 1.2;
    }
    const turboSeedInput = document.getElementById('chatterbox-turbo-replicate-seed');
    if (turboSeedInput) {
        turboSeedInput.value =
            settings.chatterbox_turbo_replicate_seed === null ||
            settings.chatterbox_turbo_replicate_seed === undefined
                ? ''
                : settings.chatterbox_turbo_replicate_seed;
    }
}

// Save settings
async function saveSettings() {
    const defaultFormatSelect = document.getElementById('settings-output-format');
    const defaultBitrateSelect = document.getElementById('settings-output-bitrate');
    const defaultFormat = defaultFormatSelect ? defaultFormatSelect.value : 'mp3';
    const defaultBitrate = defaultBitrateSelect ? parseInt(defaultBitrateSelect.value, 10) || 128 : 128;

    const kokoroReplicateKeyEl = document.getElementById('kokoro-replicate-api-key');
    const settings = {
        replicate_api_key: kokoroReplicateKeyEl ? kokoroReplicateKeyEl.value : '',
        chunk_size: parseInt(document.getElementById('chunk-size').value),
        speed: parseFloat(document.getElementById('speed').value),
        output_format: defaultFormat,
        crossfade_duration: parseFloat(document.getElementById('crossfade').value),
        intro_silence_ms: parseInt(document.getElementById('intro-silence').value, 10) || 0,
        inter_chunk_silence_ms: parseInt(document.getElementById('inter-silence').value, 10) || 0,
        parallel_chunks: Math.min(25, Math.max(1, parseInt(document.getElementById('parallel-chunks')?.value, 10) || 3)),
        cleanup_vram_after_job: document.getElementById('cleanup-vram-after-job')?.checked ?? false,
        gemini_api_key: document.getElementById('gemini-api-key').value,
        gemini_model: document.getElementById('gemini-model').value,
        gemini_prompt: document.getElementById('gemini-prompt').value,
        gemini_prompt_presets: geminiPresetState.list.map(preset => ({ ...preset })),
        tts_engine: document.getElementById('settings-tts-engine').value,
        chatterbox_turbo_local_device: document.getElementById('chatterbox-turbo-local-device').value,
        chatterbox_turbo_local_default_prompt: document.getElementById('chatterbox-turbo-local-prompt').value,
        chatterbox_turbo_local_temperature: parseFloat(document.getElementById('chatterbox-turbo-local-temperature').value) || 0.8,
        chatterbox_turbo_local_top_p: parseFloat(document.getElementById('chatterbox-turbo-local-top-p').value) || 0.95,
        chatterbox_turbo_local_top_k: parseInt(document.getElementById('chatterbox-turbo-local-top-k').value, 10) || 1000,
        chatterbox_turbo_local_repetition_penalty: parseFloat(document.getElementById('chatterbox-turbo-local-rep-penalty').value) || 1.2,
        chatterbox_turbo_local_cfg_weight: parseFloat(document.getElementById('chatterbox-turbo-local-cfg-weight').value) || 0,
        chatterbox_turbo_local_exaggeration: parseFloat(document.getElementById('chatterbox-turbo-local-exaggeration').value) || 0,
        chatterbox_turbo_local_norm_loudness: document.getElementById('chatterbox-turbo-local-norm').checked,
        chatterbox_turbo_local_prompt_norm_loudness: document.getElementById('chatterbox-turbo-local-prompt-norm').checked,
        chatterbox_turbo_local_chunk_size: parseInt(document.getElementById('chatterbox-turbo-local-chunk-size').value, 10) || 450,
        voxcpm_local_model_id: document.getElementById('voxcpm-local-model-id').value,
        voxcpm_local_device: document.getElementById('voxcpm-local-device').value,
        voxcpm_local_default_prompt: document.getElementById('voxcpm-local-prompt').value,
        voxcpm_local_default_prompt_text: document.getElementById('voxcpm-local-prompt-text').value,
        voxcpm_local_cfg_value: parseFloat(document.getElementById('voxcpm-local-cfg').value) || 2.0,
        voxcpm_local_inference_timesteps: parseInt(document.getElementById('voxcpm-local-steps').value, 10) || 10,
        voxcpm_local_normalize: document.getElementById('voxcpm-local-normalize').checked,
        voxcpm_local_denoise: document.getElementById('voxcpm-local-denoise').checked,
        qwen3_custom_model_id: document.getElementById('qwen3-custom-model-id').value,
        qwen3_custom_device: document.getElementById('qwen3-custom-device').value,
        qwen3_custom_dtype: document.getElementById('qwen3-custom-dtype').value,
        qwen3_custom_attn_implementation: document.getElementById('qwen3-custom-attn').value,
        qwen3_custom_default_language: document.getElementById('qwen3-custom-language').value,
        qwen3_custom_default_instruct: document.getElementById('qwen3-custom-instruct').value,
        qwen3_clone_model_id: document.getElementById('qwen3-clone-model-id').value,
        qwen3_clone_device: document.getElementById('qwen3-clone-device').value,
        qwen3_clone_dtype: document.getElementById('qwen3-clone-dtype').value,
        qwen3_clone_attn_implementation: document.getElementById('qwen3-clone-attn').value,
        qwen3_clone_default_language: document.getElementById('qwen3-clone-language').value,
        qwen3_clone_default_prompt: document.getElementById('qwen3-clone-prompt').value,
        qwen3_clone_default_prompt_text: document.getElementById('qwen3-clone-prompt-text').value,
        chatterbox_turbo_replicate_model: document.getElementById('chatterbox-turbo-replicate-model').value,
        chatterbox_turbo_replicate_voice: document.getElementById('chatterbox-turbo-replicate-voice').value,
        chatterbox_turbo_replicate_temperature: parseFloat(document.getElementById('chatterbox-turbo-replicate-temperature').value) || 0.8,
        chatterbox_turbo_replicate_top_p: parseFloat(document.getElementById('chatterbox-turbo-replicate-top-p').value) || 0.95,
        chatterbox_turbo_replicate_top_k: parseInt(document.getElementById('chatterbox-turbo-replicate-top-k').value, 10) || 1000,
        chatterbox_turbo_replicate_repetition_penalty: parseFloat(document.getElementById('chatterbox-turbo-replicate-rep-penalty').value) || 1.2,
        chatterbox_turbo_replicate_seed: (() => {
            const raw = document.getElementById('chatterbox-turbo-replicate-seed').value.trim();
            if (!raw) return null;
            const parsed = parseInt(raw, 10);
            return Number.isFinite(parsed) ? parsed : null;
        })(),
        output_bitrate_kbps: defaultBitrate
    };
    
    const saveBtn = document.getElementById('save-settings-btn');
    saveBtn.disabled = true;
    saveBtn.textContent = 'Saving...';
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(settings)
        });
        
        const data = await response.json();
        
        if (data.success) {
            alert('Settings saved successfully!');
            // Refresh status bar - loadHealthStatus is defined in main.js
            if (typeof loadHealthStatus === 'function') {
                loadHealthStatus();
            } else {
                console.warn('loadHealthStatus not available, reloading page');
                location.reload();
            }
        } else {
            alert('Error saving settings: ' + data.error);
        }
    } catch (error) {
        console.error('Error saving settings:', error);
        alert('Failed to save settings');
    } finally {
        saveBtn.disabled = false;
        saveBtn.textContent = 'Save Settings';
    }
}

// Reset settings to defaults
async function resetSettings() {
    if (!confirm('Reset all settings to defaults?')) {
        return;
    }
    
    const defaults = {
        mode: 'local',
        replicate_api_key: '',
        chunk_size: 500,
        speed: 1.0,
        output_format: 'mp3',
        crossfade_duration: 0.1,
        intro_silence_ms: 0,
        inter_chunk_silence_ms: 0,
        parallel_chunks: 3,
        cleanup_vram_after_job: false,
        gemini_api_key: '',
        gemini_model: 'gemini-1.5-flash',
        gemini_prompt: '',
        gemini_prompt_presets: [],
        tts_engine: 'kokoro',
        voxcpm_local_model_id: 'openbmb/VoxCPM1.5',
        voxcpm_local_device: 'auto',
        voxcpm_local_default_prompt: '',
        voxcpm_local_default_prompt_text: '',
        voxcpm_local_cfg_value: 2.5,
        voxcpm_local_inference_timesteps: 20,
        voxcpm_local_normalize: true,
        voxcpm_local_denoise: false,
        qwen3_custom_model_id: 'Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice',
        qwen3_custom_device: 'auto',
        qwen3_custom_dtype: 'bfloat16',
        qwen3_custom_attn_implementation: 'flash_attention_2',
        qwen3_custom_default_language: 'Auto',
        qwen3_custom_default_instruct: '',
        qwen3_clone_model_id: 'Qwen/Qwen3-TTS-12Hz-1.7B-Base',
        qwen3_clone_device: 'auto',
        qwen3_clone_dtype: 'bfloat16',
        qwen3_clone_attn_implementation: 'flash_attention_2',
        qwen3_clone_default_language: 'Auto',
        qwen3_clone_default_prompt: '',
        qwen3_clone_default_prompt_text: ''
    };
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(defaults)
        });
        
        const data = await response.json();
        
        if (data.success) {
            applySettings(defaults);
            alert('Settings reset to defaults');
            loadHealthStatus();
        }
    } catch (error) {
        console.error('Error resetting settings:', error);
        alert('Failed to reset settings');
    }
}
