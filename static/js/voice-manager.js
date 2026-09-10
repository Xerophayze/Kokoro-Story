// Voice Manager - Handles voice library and selection

let voiceData = null;
// Make availableVoices globally accessible for main.js
window.availableVoices = null;
window.customVoiceMap = window.customVoiceMap || {};
window.availablePocketTtsVoices = null;
let chatterboxVoices = [];
const CHATTERBOX_ALLOWED_EXTENSIONS = ['.wav', '.mp3', '.m4a', '.flac', '.ogg'];
const chatterboxPreviewController = createChatterboxPreviewController();
window.chatterboxPreviewController = chatterboxPreviewController;

const audioPreviewCache = {};
let currentPreviewAudio = null;
let currentPreviewItem = null;
let samplesReady = false;
let lastFailedSamples = [];
let customVoices = [];
let qwenVoicePreview = null;

const generateSamplesBtnId = 'generate-voice-samples-btn';
const regenerateSamplesBtnId = 'regenerate-voice-samples-btn';
const sampleStatusId = 'voice-sample-status';

const VOICES_UPDATED_EVENT = window.VOICES_UPDATED_EVENT || 'voices:updated';
window.VOICES_UPDATED_EVENT = VOICES_UPDATED_EVENT;
const CHATTERBOX_VOICES_EVENT = window.CHATTERBOX_VOICES_EVENT || 'chatterboxVoices:updated';
window.CHATTERBOX_VOICES_EVENT = CHATTERBOX_VOICES_EVENT;
window.addEventListener(CHATTERBOX_VOICES_EVENT, event => {
    if (!Array.isArray(event?.detail?.voices)) return;
    chatterboxVoices = event.detail.voices;
    renderChatterboxVoiceList();
    updateGlobalPreviewSelections();
});

// Load voices on page load
document.addEventListener('DOMContentLoaded', () => {
    loadVoices();
    loadPocketTtsVoices();
    loadCustomVoices();
    setupCustomVoiceModal();
    loadChatterboxVoices();
    setupChatterboxVoiceSection();
    setupVoiceListControls();
    initEditVoiceModal();
    setupVoicesAccordion();
    setupQwenVoiceCreation();
    setupOmniVoiceCreation();
    setupVoiceCreationEngineToggle();
});

function setupVoicesAccordion() {
    const sections = document.querySelectorAll('.voices-section');
    sections.forEach(section => {
        const header = section.querySelector('.voices-section-header');
        const toggle = section.querySelector('.voices-section-toggle');
        if (!header || !toggle) return;
        header.addEventListener('click', event => {
            if (event.target.closest('button')) {
                return;
            }
            section.classList.toggle('collapsed');
            toggle.textContent = section.classList.contains('collapsed') ? '▶' : '▼';
        });
    });
}

async function loadPocketTtsVoices() {
    try {
        const response = await fetch('/api/pocket-tts/voices');
        const data = await response.json();
        if (data.success) {
            window.availablePocketTtsVoices = data.voices || [];
        } else {
            window.availablePocketTtsVoices = [];
        }
    } catch (error) {
        console.error('Error loading Pocket TTS voices:', error);
        window.availablePocketTtsVoices = [];
    } finally {
        emitVoicesUpdated();
    }
}

function getSelectionSet(scope) {
    return scope === 'archived' ? selectedArchivedVoiceIds : selectedVoiceIds;
}

function getSelectedCount(scope) {
    return getSelectionSet(scope).size;
}

function updateBatchToolbar(scope) {
    const isArchive = scope === 'archived';
    const count = getSelectedCount(scope);
    const countLabel = document.getElementById(isArchive ? 'voice-archive-selected-count' : 'voice-selected-count');
    if (countLabel) {
        countLabel.textContent = `${count} selected`;
    }
    const exportBtn = document.getElementById(isArchive ? 'voice-archive-export-btn' : 'voice-batch-export-btn');
    const transcribeBtn = isArchive ? null : document.getElementById('voice-batch-transcribe-btn');
    const archiveBtn = document.getElementById(isArchive ? 'voice-archive-restore-btn' : 'voice-batch-archive-btn');
    const deleteBtn = document.getElementById(isArchive ? 'voice-archive-delete-btn' : 'voice-batch-delete-btn');
    [exportBtn, archiveBtn, deleteBtn].forEach(btn => {
        if (btn) btn.disabled = count === 0;
    });
    if (transcribeBtn) {
        const missingCount = Array.from(getSelectionSet(scope)).filter(id => {
            const voice = chatterboxVoices.find(entry => entry.id === id);
            return voice && !voice.transcript_available && !voice.missing_file;
        }).length;
        transcribeBtn.disabled = missingCount === 0;
        transcribeBtn.textContent = missingCount
            ? `Generate Transcripts (${missingCount})`
            : 'Generate Transcripts';
    }
    const selectAll = document.getElementById(isArchive ? 'voice-archive-select-all' : 'voice-select-all');
    if (selectAll) {
        const totalRows = getVoiceRowCheckboxes(scope).length;
        selectAll.checked = totalRows > 0 && count === totalRows;
        selectAll.indeterminate = count > 0 && count < totalRows;
    }
}

function updateSelectAllState(scope, totalRows) {
    const selection = getSelectionSet(scope);
    const selectAll = document.getElementById(scope === 'archived' ? 'voice-archive-select-all' : 'voice-select-all');
    if (!selectAll) return;
    const count = selection.size;
    selectAll.checked = totalRows > 0 && count === totalRows;
    selectAll.indeterminate = count > 0 && count < totalRows;
}

function updateRowSelection(row, checked) {
    if (!row) return;
    const voiceId = row.dataset.voiceId;
    if (!voiceId) return;
    const scope = row.dataset.archived === 'true' ? 'archived' : 'active';
    const selection = getSelectionSet(scope);
    if (checked) {
        selection.add(voiceId);
    } else {
        selection.delete(voiceId);
    }
    updateBatchToolbar(scope);
}

function getVoiceRowCheckboxes(scope) {
    const container = scope === 'archived'
        ? document.getElementById('chatterbox-voice-archive-list')
        : document.getElementById('chatterbox-voice-list');
    if (!container) return [];
    return Array.from(container.querySelectorAll('input.voice-select-checkbox'));
}

function syncSelectionSets() {
    const activeIds = new Set(allVoices.filter(entry => !entry.archived).map(entry => entry.id));
    const archivedIds = new Set(allVoices.filter(entry => entry.archived).map(entry => entry.id));
    selectedVoiceIds.forEach(id => {
        if (!activeIds.has(id)) selectedVoiceIds.delete(id);
    });
    selectedArchivedVoiceIds.forEach(id => {
        if (!archivedIds.has(id)) selectedArchivedVoiceIds.delete(id);
    });
}

async function applyArchiveState(voiceIds, archived) {
    if (!voiceIds.length) return;
    const response = await fetch('/api/chatterbox-voices/archive', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice_ids: voiceIds, archived })
    });
    const data = await response.json();
    if (!data.success) {
        throw new Error(data.error || 'Archive update failed');
    }
}

async function deleteVoicesBatch(voiceIds) {
    if (!voiceIds.length) return;
    const response = await fetch('/api/chatterbox-voices/batch-delete', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice_ids: voiceIds })
    });
    const data = await response.json();
    if (!data.success) {
        throw new Error(data.error || 'Delete failed');
    }
}

async function exportVoicesBatch(voiceIds) {
    if (!voiceIds.length) return;
    const response = await fetch('/api/chatterbox-voices/export', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ voice_ids: voiceIds })
    });
    if (!response.ok) {
        const data = await response.json().catch(() => ({}));
        throw new Error(data.error || 'Export failed');
    }
    const blob = await response.blob();
    const disposition = response.headers.get('Content-Disposition') || '';
    const filenameMatch = disposition.match(/filename="?([^";]+)"?/i);
    const filename = filenameMatch ? filenameMatch[1] : (blob.type === 'application/zip' ? 'voice_samples.zip' : 'voice_sample.wav');
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
}

function setupQwenVoiceCreation() {
    const generateBtn = document.getElementById('qwen-voice-generate-btn');
    const saveBtn = document.getElementById('qwen-voice-save-btn');
    if (generateBtn) {
        generateBtn.addEventListener('click', generateQwenVoicePreview);
    }
    if (saveBtn) {
        saveBtn.addEventListener('click', saveQwenVoicePrompt);
    }
    const refreshAvailability = () => {
        const engine = getActiveVoiceCreationDesignEngine();
        const config = window.getVoiceDesignEngineConfig?.(engine) || {};
        const available = window.voiceDesignEngineAvailable?.(engine) === true;
        const known = window.voiceDesignEngineAvailabilityKnown?.(engine) === true;
        const status = document.getElementById('qwen-voice-status');
        if (!available && status) {
            status.textContent = known
                ? (config.installMessage || 'Install the selected voice-design engine under Settings → Engine Settings.')
                : `Checking ${config.label || 'voice-design engine'} availability…`;
        } else if (available && status?.textContent?.startsWith('Install ')) {
            status.textContent = '';
        }
        window.refreshQwenVoiceDesignControls?.();
        if (available) loadQwenVoiceLanguages(engine);
    };
    window.addEventListener('qwenVoiceDesignAvailabilityChanged', refreshAvailability);
    window.addEventListener('breezeVoiceDesignAvailabilityChanged', refreshAvailability);
    window.addEventListener('voiceCreationEngineChanged', refreshAvailability);
    refreshAvailability();
}

function getActiveVoiceCreationDesignEngine() {
    const active = document.querySelector('#voice-creation-engine-toggle [data-voice-engine].active')?.dataset?.voiceEngine;
    return active === 'breeze' ? 'breeze' : 'qwen3';
}

async function loadQwenVoiceLanguages(engine = getActiveVoiceCreationDesignEngine()) {
    const select = document.getElementById('qwen-voice-language');
    if (!select) return;
    if (engine === 'breeze') {
        const previous = select.value;
        select.innerHTML = '<option value="English">English</option><option value="Chinese">Chinese</option>';
        select.value = ['English', 'Chinese'].includes(previous) ? previous : 'English';
        return;
    }
    try {
        const response = await fetch('/api/qwen3/metadata');
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to load Qwen3 metadata');
        }
        const previous = select.value;
        select.innerHTML = '<option value="Auto">Auto</option>';
        (data.languages || []).forEach(language => {
            const option = document.createElement('option');
            option.value = language;
            option.textContent = language;
            select.appendChild(option);
        });
        if (previous) {
            select.value = previous;
        }
    } catch (error) {
        console.warn('Unable to load Qwen3 metadata', error);
    }
}

async function generateQwenVoicePreview() {
    const engine = getActiveVoiceCreationDesignEngine();
    const engineConfig = window.getVoiceDesignEngineConfig?.(engine) || {};
    const textInput = document.getElementById('qwen-voice-text');
    const instructInput = document.getElementById('qwen-voice-instruct');
    const languageSelect = document.getElementById('qwen-voice-language');
    const previewAudio = document.getElementById('qwen-voice-preview');
    const status = document.getElementById('qwen-voice-status');
    const saveBtn = document.getElementById('qwen-voice-save-btn');
    const generateBtn = document.getElementById('qwen-voice-generate-btn');
    const text = textInput?.value.trim() || '';
    const instruct = instructInput?.value.trim() || '';
    const language = languageSelect?.value || 'Auto';

    if (window.voiceDesignEngineAvailable?.(engine) !== true) {
        showToast(engineConfig.installMessage || 'Install the selected voice-design engine to generate voices.', 'warning');
        return;
    }

    if (!text) {
        showToast('Enter sample text for the preview.', 'warning');
        return;
    }

    if (status) {
        status.textContent = 'Generating preview...';
    }
    if (generateBtn) {
        generateBtn.disabled = true;
    }
    if (saveBtn) {
        saveBtn.disabled = true;
    }
    qwenVoicePreview = null;

    try {
        const response = await fetch(engineConfig.previewUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, instruct, language }),
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to enqueue preview');
        }
        const result = await pollQwenVoiceTask(data.job_id, status, 'Generating preview...', engineConfig.taskUrl);
        qwenVoicePreview = {
            audio_base64: result.audio_base64,
            mime_type: result.mime_type || 'audio/wav',
            engine,
            result,
        };
        if (previewAudio && result.audio_base64) {
            previewAudio.src = `data:${qwenVoicePreview.mime_type};base64,${result.audio_base64}`;
            previewAudio.load();
        }
        if (saveBtn) {
            saveBtn.disabled = false;
        }
        if (status) {
            status.textContent = 'Preview ready. Save when you like it.';
        }
    } catch (error) {
        console.error('Failed to generate voice-design preview', error);
        showToast(error.message || 'Preview failed', 'error');
        if (status) {
            status.textContent = 'Preview failed.';
        }
    } finally {
        if (generateBtn) {
            generateBtn.disabled = window.voiceDesignEngineAvailable?.(engine) !== true;
        }
    }
}

async function saveQwenVoicePrompt() {
    const engine = qwenVoicePreview?.engine || getActiveVoiceCreationDesignEngine();
    const engineConfig = window.getVoiceDesignEngineConfig?.(engine) || {};
    const nameInput = document.getElementById('qwen-voice-name');
    const genderSelect = document.getElementById('qwen-voice-gender');
    const languageSelect = document.getElementById('qwen-voice-language');
    const descriptionInput = document.getElementById('qwen-voice-description');
    const textInput = document.getElementById('qwen-voice-text');
    const instructInput = document.getElementById('qwen-voice-instruct');
    const status = document.getElementById('qwen-voice-status');
    const saveBtn = document.getElementById('qwen-voice-save-btn');

    const name = nameInput?.value.trim() || '';
    const gender = genderSelect?.value || null;
    const language = languageSelect?.value || 'Auto';
    const description = descriptionInput?.value.trim() || '';
    const text = textInput?.value.trim() || '';
    const instruct = instructInput?.value.trim() || '';

    if (!name) {
        showToast('Add a name before saving the voice prompt.', 'warning');
        return;
    }
    if (!text) {
        showToast('Sample text is required to save this voice.', 'warning');
        return;
    }
    if (!qwenVoicePreview?.audio_base64) {
        showToast('Generate a preview before saving.', 'warning');
        return;
    }

    if (status) {
        status.textContent = 'Saving voice prompt...';
    }
    if (saveBtn) {
        saveBtn.disabled = true;
    }

    try {
        const previewResult = qwenVoicePreview.result || {};
        const response = await fetch(engineConfig.saveUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                gender,
                language,
                description,
                text,
                instruct,
                audio_base64: qwenVoicePreview.audio_base64,
                engine,
                model: previewResult.model,
                seed: previewResult.seed,
                sampling_parameters: previewResult.sampling_parameters,
                wav_sha256: previewResult.wav_sha256,
            }),
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to enqueue save');
        }
        await pollQwenVoiceTask(data.job_id, status, 'Saving voice prompt...', engineConfig.taskUrl);
        showToast(`${engineConfig.label || 'Voice'} prompt saved.`, 'success');
        if (status) {
            status.textContent = 'Saved to Voice Prompts.';
        }
        if (nameInput) nameInput.value = '';
        if (descriptionInput) descriptionInput.value = '';
        qwenVoicePreview = null;
        if (saveBtn) {
            saveBtn.disabled = true;
        }
        await loadChatterboxVoices();
    } catch (error) {
        console.error('Failed to save voice prompt', error);
        showToast(error.message || 'Save failed', 'error');
        if (status) {
            status.textContent = 'Save failed.';
        }
        if (saveBtn) {
            saveBtn.disabled = false;
        }
    }
}

async function pollQwenVoiceTask(taskId, statusEl, message, taskUrl = '/api/qwen3/voice-design/tasks') {
    if (!taskId) {
        throw new Error('Missing task id for queued request.');
    }
    const start = Date.now();
    const timeoutMs = 10 * 60 * 1000;
    while (Date.now() - start < timeoutMs) {
        if (statusEl && message) {
            statusEl.textContent = message;
        }
        const taskEndpoint = typeof taskUrl === 'function'
            ? taskUrl(taskId)
            : `${String(taskUrl).replace(/\/$/, '')}/${encodeURIComponent(taskId)}`;
        const response = await fetch(taskEndpoint);
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to fetch task status');
        }
        if (data.status === 'completed') {
            return data.result || {};
        }
        if (data.status === 'failed') {
            throw new Error(data.error || 'Queued task failed');
        }
        await new Promise(resolve => setTimeout(resolve, 1500));
    }
    throw new Error('Timed out waiting for the queued task.');
}

// Load available voices from API
async function loadVoices() {
    try {
        const response = await fetch('/api/voices');
        const data = await response.json();
        
        if (data.success) {
            voiceData = data.voices;
            window.availableVoices = data.voices; // Make globally accessible
            updateCustomVoiceMap(data.voices);
            samplesReady = data.samples_ready;
            updateSampleStatus(data);
            displayVoiceLibrary(data.voices);
            emitVoicesUpdated();
        } else {
            displaySampleError(data.error || 'Unable to load voices');
        }
    } catch (error) {
        console.error('Error loading voices:', error);
        displaySampleError('Error loading voices');
    }
}

// ---------------------------------------------------------------------------
// Chatterbox voice management

async function loadChatterboxVoices() {
    try {
        const response = await fetch('/api/chatterbox-voices');
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Unable to load Chatterbox voices');
        }
        chatterboxVoices = Array.isArray(data.voices) ? data.voices : [];
        renderChatterboxVoiceList();
        updateGlobalPreviewSelections();
        emitChatterboxVoicesUpdated();
    } catch (error) {
        console.error('Failed to load Chatterbox voices', error);
        showToast(error.message || 'Failed to load Chatterbox voices', 'error');
    }
}

function setupChatterboxVoiceSection() {
    const form = document.getElementById('chatterbox-voice-form');
    const list = document.getElementById('chatterbox-voice-list');
    if (form) {
        form.addEventListener('submit', async event => {
            event.preventDefault();
            const nameInput = document.getElementById('chatterbox-voice-name');
            const fileInput = document.getElementById('chatterbox-voice-file');
            const transcriptInput = document.getElementById('chatterbox-voice-transcript');
            const name = nameInput?.value.trim();
            const file = fileInput?.files?.[0];
            if (!name) {
                showToast('A friendly voice name is required.', 'warning');
                return;
            }
            if (!file) {
                showToast('Select an audio file to upload.', 'warning');
                return;
            }
            const formData = new FormData();
            formData.append('name', name);
            formData.append('file', file);
            formData.append('transcript', transcriptInput?.value?.trim() || '');
            try {
                const response = await fetch('/api/chatterbox-voices', {
                    method: 'POST',
                    body: formData,
                });
                const data = await response.json();
                if (!data.success) {
                    throw new Error(data.error || 'Failed to save voice');
                }
                showToast('Chatterbox voice saved.', 'success');
                form.reset();
                fileInput.value = '';
                await loadChatterboxVoices();
            } catch (error) {
                console.error('Failed to save Chatterbox voice', error);
                showToast(error.message || 'Failed to save voice', 'error');
            }
        });
    }
    initChatterboxDropzone();
    if (list) {
        list.addEventListener('click', event => {
            const actionButton = event.target.closest('[data-action]');
            if (!actionButton) return;
            const card = event.target.closest('.chatterbox-voice-card');
            if (!card) return;
            const voiceId = card.dataset.voiceId;
            if (!voiceId) return;
            const action = actionButton.dataset.action;
            if (action === 'rename') {
                renameChatterboxVoice(voiceId);
            } else if (action === 'delete') {
                deleteChatterboxVoice(voiceId);
            } else if (action === 'copy') {
                copyChatterboxVoicePath(voiceId);
            } else if (action === 'preview') {
                toggleChatterboxVoicePreview(voiceId, actionButton);
            }
        });
    }
}

function initChatterboxDropzone() {
    const dropzone = document.getElementById('chatterbox-dropzone');
    const fileInput = document.getElementById('chatterbox-dropzone-input');
    const statusContainer = document.getElementById('chatterbox-dropzone-status');
    if (!dropzone || !fileInput || !statusContainer) {
        return;
    }
    const browseBtn = dropzone.querySelector('button');
    if (browseBtn) {
        browseBtn.addEventListener('click', () => {
            if (dropzone.classList.contains('is-uploading')) return;
            fileInput.click();
        });
    }
    fileInput.addEventListener('change', event => {
        const files = Array.from(event.target.files || []);
        if (files.length) {
            bulkUploadChatterboxVoices(files, dropzone, statusContainer, fileInput);
        }
        event.target.value = '';
    });
    ['dragenter', 'dragover'].forEach(eventName => {
        dropzone.addEventListener(eventName, event => {
            event.preventDefault();
            event.stopPropagation();
            if (dropzone.classList.contains('is-uploading')) return;
            dropzone.classList.add('is-dragging');
        });
    });
    ['dragleave', 'dragend'].forEach(eventName => {
        dropzone.addEventListener(eventName, event => {
            event.preventDefault();
            event.stopPropagation();
            dropzone.classList.remove('is-dragging');
        });
    });
    dropzone.addEventListener('drop', event => {
        event.preventDefault();
        event.stopPropagation();
        dropzone.classList.remove('is-dragging');
        if (dropzone.classList.contains('is-uploading')) return;
        const files = Array.from(event.dataTransfer?.files || []);
        if (files.length) {
            bulkUploadChatterboxVoices(files, dropzone, statusContainer, fileInput);
        }
    });
}

function updateGlobalPreviewSelections() {
    if (typeof populateReferenceSelects === 'function') {
        try {
            populateReferenceSelects();
        } catch (error) {
            console.warn('populateReferenceSelects failed', error);
        }
    }

    if (typeof window.rebuildTurboPreviewMenus === 'function') {
        try {
            window.rebuildTurboPreviewMenus();
        } catch (error) {
            console.warn('rebuildTurboPreviewMenus failed', error);
        }
    }

    const globalSelect = document.getElementById('chatterbox-reference-select');
    const globalButton = document.getElementById('global-chatterbox-preview-btn');
    if (globalButton) {
        const hasSelection = (globalSelect?.value || '').trim().length > 0;
        if (!hasSelection) {
            globalButton.disabled = true;
            globalButton.classList.remove('is-playing', 'is-loading');
            globalButton.textContent = globalButton.dataset.labelPlay || 'Play';
        } else {
            globalButton.disabled = false;
        }
    }
}

function createChatterboxPreviewController() {
    let currentAudio = null;
    let currentVoiceId = null;
    let currentTrigger = null;

    function resetTrigger(trigger) {
        if (!trigger) return;
        trigger.classList.remove('is-playing', 'is-loading');
        trigger.textContent = trigger.dataset.labelPlay || 'Play';
        trigger.disabled = trigger.dataset.disabled === 'true';
    }

    function applyPlayingState(trigger) {
        if (!trigger) return;
        trigger.classList.remove('is-loading');
        trigger.classList.add('is-playing');
        trigger.textContent = trigger.dataset.labelStop || 'Stop';
    }

    function applyLoadingState(trigger) {
        if (!trigger) return;
        trigger.dataset.disabled = trigger.disabled ? 'true' : 'false';
        trigger.disabled = true;
        trigger.classList.add('is-loading');
        trigger.textContent = 'Loading…';
    }

    function stopPlayback() {
        if (currentAudio) {
            currentAudio.pause();
            currentAudio.currentTime = 0;
            currentAudio = null;
        }
        if (currentTrigger) {
            resetTrigger(currentTrigger);
            currentTrigger = null;
        }
        currentVoiceId = null;
    }

    async function toggleById(voiceId, trigger) {
        if (!voiceId) return;
        if (voiceId === currentVoiceId) {
            stopPlayback();
            return;
        }
        stopPlayback();
        currentVoiceId = voiceId;
        currentTrigger = trigger || null;
        if (currentTrigger) {
            applyLoadingState(currentTrigger);
        }
        const previewUrl = `/api/chatterbox-voices/${voiceId}/preview?_=${Date.now()}`;
        const audio = new Audio(previewUrl);
        currentAudio = audio;

        audio.addEventListener('ended', () => {
            stopPlayback();
        });
        audio.addEventListener('error', () => {
            showToast('Unable to play preview audio.', 'error');
            stopPlayback();
        });

        try {
            await audio.play();
            if (currentTrigger) {
                currentTrigger.disabled = false;
                applyPlayingState(currentTrigger);
            }
        } catch (error) {
            console.error('Failed to play chatterbox preview', error);
            showToast('Unable to play preview audio.', 'error');
            stopPlayback();
        }
    }

    return {
        toggleById,
        stop: stopPlayback,
        getCurrentVoiceId() {
            return currentVoiceId;
        },
    };
}

function appendDropzoneStatus(container, message, type = 'info') {
    if (!container) return null;
    const row = document.createElement('div');
    row.className = `dropzone-status-row ${type}`;
    row.textContent = message;
    container.prepend(row);
    while (container.childElementCount > 10) {
        container.removeChild(container.lastElementChild);
    }
    return row;
}

function normalizeVoiceNameFromFile(filename = '') {
    const stem = filename.replace(/\.[^/.]+$/, '');
    const cleaned = stem.replace(/[_\s-]+/g, ' ').trim();
    if (cleaned) {
        return cleaned.length > 64 ? cleaned.slice(0, 64) : cleaned;
    }
    return stem || 'Untitled Voice';
}

function getFileExtension(filename = '') {
    const lastDot = filename.lastIndexOf('.');
    if (lastDot === -1) return '';
    return filename.slice(lastDot).toLowerCase();
}

async function bulkUploadChatterboxVoices(files, dropzone, statusContainer, fileInput) {
    if (!files.length) {
        appendDropzoneStatus(statusContainer, 'No files detected.', 'info');
        return;
    }
    dropzone.classList.add('is-uploading');
    let createdAny = false;
    try {
        for (const file of files) {
            const extension = getFileExtension(file.name);
            if (!CHATTERBOX_ALLOWED_EXTENSIONS.includes(extension)) {
                appendDropzoneStatus(
                    statusContainer,
                    `${file.name}: Unsupported file type (${extension || 'unknown'}).`,
                    'error'
                );
                continue;
            }
            const pendingRow = appendDropzoneStatus(
                statusContainer,
                `Uploading ${file.name}…`,
                'info'
            );
            const friendlyName = normalizeVoiceNameFromFile(file.name);
            const formData = new FormData();
            formData.append('name', friendlyName);
            formData.append('file', file);
            try {
                const response = await fetch('/api/chatterbox-voices', {
                    method: 'POST',
                    body: formData,
                });
                const data = await response.json();
                if (!data.success) {
                    throw new Error(data.error || 'Failed to save voice.');
                }
                pendingRow.textContent = `Saved ${file.name} (${friendlyName}).`;
                pendingRow.classList.remove('info');
                pendingRow.classList.add('success');
                createdAny = true;
            } catch (error) {
                pendingRow.textContent = `${file.name}: ${error.message}`;
                pendingRow.classList.remove('info');
                pendingRow.classList.add('error');
            }
        }
        if (createdAny) {
            await loadChatterboxVoices();
        }
    } finally {
        dropzone.classList.remove('is-uploading');
        if (fileInput) {
            fileInput.value = '';
        }
    }
}

// Voice list state
let externalVoices = [];
let allVoices = []; // Combined local + external
let voiceListSortKey = 'name';
let voiceListSortDir = 'asc';
const selectedVoiceIds = new Set();
const selectedArchivedVoiceIds = new Set();

// Locale code to human-readable language name mapping (voice-manager specific)
const VM_LOCALE_NAMES = {
    'af-ZA': 'Afrikaans',
    'am-ET': 'Amharic',
    'ar-AE': 'Arabic (UAE)',
    'ar-BH': 'Arabic (Bahrain)',
    'ar-DZ': 'Arabic (Algeria)',
    'ar-EG': 'Arabic (Egypt)',
    'ar-IQ': 'Arabic (Iraq)',
    'ar-JO': 'Arabic (Jordan)',
    'ar-KW': 'Arabic (Kuwait)',
    'ar-LB': 'Arabic (Lebanon)',
    'ar-LY': 'Arabic (Libya)',
    'ar-MA': 'Arabic (Morocco)',
    'ar-OM': 'Arabic (Oman)',
    'ar-QA': 'Arabic (Qatar)',
    'ar-SA': 'Arabic (Saudi)',
    'ar-SY': 'Arabic (Syria)',
    'ar-TN': 'Arabic (Tunisia)',
    'ar-YE': 'Arabic (Yemen)',
    'az-AZ': 'Azerbaijani',
    'bg-BG': 'Bulgarian',
    'bn-BD': 'Bengali (Bangladesh)',
    'bn-IN': 'Bengali (India)',
    'bs-BA': 'Bosnian',
    'ca-ES': 'Catalan',
    'cs-CZ': 'Czech',
    'cy-GB': 'Welsh',
    'da-DK': 'Danish',
    'de-AT': 'German (Austria)',
    'de-CH': 'German (Swiss)',
    'de-DE': 'German',
    'el-GR': 'Greek',
    'en-AU': 'English (Australia)',
    'en-CA': 'English (Canada)',
    'en-GB': 'English (UK)',
    'en-HK': 'English (Hong Kong)',
    'en-IE': 'English (Ireland)',
    'en-IN': 'English (India)',
    'en-KE': 'English (Kenya)',
    'en-NG': 'English (Nigeria)',
    'en-NZ': 'English (New Zealand)',
    'en-PH': 'English (Philippines)',
    'en-SG': 'English (Singapore)',
    'en-TZ': 'English (Tanzania)',
    'en-US': 'English (US)',
    'en-ZA': 'English (South Africa)',
    'es-AR': 'Spanish (Argentina)',
    'es-BO': 'Spanish (Bolivia)',
    'es-CL': 'Spanish (Chile)',
    'es-CO': 'Spanish (Colombia)',
    'es-CR': 'Spanish (Costa Rica)',
    'es-CU': 'Spanish (Cuba)',
    'es-DO': 'Spanish (Dominican Rep.)',
    'es-EC': 'Spanish (Ecuador)',
    'es-ES': 'Spanish (Spain)',
    'es-GQ': 'Spanish (Eq. Guinea)',
    'es-GT': 'Spanish (Guatemala)',
    'es-HN': 'Spanish (Honduras)',
    'es-MX': 'Spanish (Mexico)',
    'es-NI': 'Spanish (Nicaragua)',
    'es-PA': 'Spanish (Panama)',
    'es-PE': 'Spanish (Peru)',
    'es-PR': 'Spanish (Puerto Rico)',
    'es-PY': 'Spanish (Paraguay)',
    'es-SV': 'Spanish (El Salvador)',
    'es-US': 'Spanish (US)',
    'es-UY': 'Spanish (Uruguay)',
    'es-VE': 'Spanish (Venezuela)',
    'et-EE': 'Estonian',
    'eu-ES': 'Basque',
    'fa-IR': 'Persian',
    'fi-FI': 'Finnish',
    'fil-PH': 'Filipino',
    'fr-BE': 'French (Belgium)',
    'fr-CA': 'French (Canada)',
    'fr-CH': 'French (Swiss)',
    'fr-FR': 'French',
    'ga-IE': 'Irish',
    'gl-ES': 'Galician',
    'gu-IN': 'Gujarati',
    'he-IL': 'Hebrew',
    'hi-IN': 'Hindi',
    'hr-HR': 'Croatian',
    'hu-HU': 'Hungarian',
    'hy-AM': 'Armenian',
    'id-ID': 'Indonesian',
    'is-IS': 'Icelandic',
    'it-IT': 'Italian',
    'ja-JP': 'Japanese',
    'jv-ID': 'Javanese',
    'ka-GE': 'Georgian',
    'kk-KZ': 'Kazakh',
    'km-KH': 'Khmer',
    'kn-IN': 'Kannada',
    'ko-KR': 'Korean',
    'lo-LA': 'Lao',
    'lt-LT': 'Lithuanian',
    'lv-LV': 'Latvian',
    'mk-MK': 'Macedonian',
    'ml-IN': 'Malayalam',
    'mn-MN': 'Mongolian',
    'mr-IN': 'Marathi',
    'ms-MY': 'Malay',
    'mt-MT': 'Maltese',
    'my-MM': 'Burmese',
    'nb-NO': 'Norwegian',
    'ne-NP': 'Nepali',
    'nl-BE': 'Dutch (Belgium)',
    'nl-NL': 'Dutch',
    'pl-PL': 'Polish',
    'ps-AF': 'Pashto',
    'pt-BR': 'Portuguese (Brazil)',
    'pt-PT': 'Portuguese',
    'ro-RO': 'Romanian',
    'ru-RU': 'Russian',
    'si-LK': 'Sinhala',
    'sk-SK': 'Slovak',
    'sl-SI': 'Slovenian',
    'so-SO': 'Somali',
    'sq-AL': 'Albanian',
    'sr-RS': 'Serbian',
    'su-ID': 'Sundanese',
    'sv-SE': 'Swedish',
    'sw-KE': 'Swahili (Kenya)',
    'sw-TZ': 'Swahili (Tanzania)',
    'ta-IN': 'Tamil (India)',
    'ta-LK': 'Tamil (Sri Lanka)',
    'ta-MY': 'Tamil (Malaysia)',
    'ta-SG': 'Tamil (Singapore)',
    'te-IN': 'Telugu',
    'th-TH': 'Thai',
    'tr-TR': 'Turkish',
    'uk-UA': 'Ukrainian',
    'ur-IN': 'Urdu (India)',
    'ur-PK': 'Urdu (Pakistan)',
    'uz-UZ': 'Uzbek',
    'vi-VN': 'Vietnamese',
    'wuu-CN': 'Wu Chinese',
    'yue-CN': 'Cantonese',
    'zh-CN': 'Chinese (Mandarin)',
    'zh-HK': 'Chinese (Hong Kong)',
    'zh-TW': 'Chinese (Taiwan)',
    'zu-ZA': 'Zulu',
};

function getLanguageDisplayName(localeCode) {
    if (!localeCode) return '—';
    return VM_LOCALE_NAMES[localeCode] || localeCode;
}

function renderChatterboxVoiceList() {
    const container = document.getElementById('chatterbox-voice-list');
    const archiveContainer = document.getElementById('chatterbox-voice-archive-list');
    if (!container) return;
    
    // Build set of local file names to detect duplicates
    const localFileNames = new Set(
        chatterboxVoices.map(v => v.file_name).filter(Boolean)
    );
    
    // Filter out external voices that have been downloaded (exist in local list)
    const filteredExternalVoices = externalVoices.filter(v => {
        const fileName = `${v.short_name}.mp3`;
        return !localFileNames.has(fileName);
    });
    
    // Combine local and external voices
    allVoices = [
        ...chatterboxVoices.map(v => ({ ...v, source: 'local' })),
        ...filteredExternalVoices.map(v => ({ ...v, source: 'external' }))
    ];
    
    const activeVoices = allVoices.filter(entry => !entry.archived);
    const archivedVoices = allVoices.filter(entry => entry.archived);

    // Apply filters
    const filteredVoices = applyVoiceFilters(activeVoices);
    const filteredArchived = applyVoiceFilters(archivedVoices);

    // Apply sorting
    const sortedVoices = sortVoices(filteredVoices, voiceListSortKey, voiceListSortDir);
    const sortedArchived = sortVoices(filteredArchived, voiceListSortKey, voiceListSortDir);

    // Update stats
    updateVoiceListStats(filteredVoices.length, activeVoices.length);
    
    // Update language filter options
    updateLanguageFilterOptions(allVoices);
    
    renderVoiceRows(container, sortedVoices, { archived: false });
    if (archiveContainer) {
        renderVoiceRows(archiveContainer, sortedArchived, { archived: true });
    }
    syncSelectionSets();
    updateBatchToolbar('active');
    updateBatchToolbar('archived');
}

function renderVoiceRows(container, rows, { archived }) {
    if (!container) return;
    if (!rows.length) {
        container.innerHTML = `<tr><td colspan="7" class="help-text">${archived ? 'No archived voices.' : 'No voices match your filters.'}</td></tr>`;
        return;
    }
    container.innerHTML = '';
    rows.forEach(entry => {
        const row = document.createElement('tr');
        row.dataset.voiceId = entry.id;
        row.dataset.source = entry.source;
        row.dataset.archived = archived ? 'true' : 'false';

        const isExternal = entry.source === 'external';
        const isDownloaded = isExternal ? entry.is_downloaded : true;
        const genderBadge = entry.gender
            ? `<span class="badge badge-${entry.gender.toLowerCase()}">${entry.gender}</span>`
            : '<span class="badge">—</span>';
        const sourceBadge = isExternal
            ? (isDownloaded ? '<span class="badge badge-downloaded">Downloaded</span>' : '<span class="badge badge-external">External</span>')
            : '<span class="badge badge-local">Local</span>';
        const transcriptBadge = isExternal ? '' : (entry.transcript_available
            ? '<span class="badge badge-downloaded">Transcript ready</span>'
            : '<span class="badge badge-danger">Transcript required for LocalAI</span>');
        const durationText = entry.duration_seconds ? `${entry.duration_seconds.toFixed(1)}s` : '—';
        const languageText = getLanguageDisplayName(entry.language);
        const selectionSet = archived ? selectedArchivedVoiceIds : selectedVoiceIds;
        const isSelected = selectionSet.has(entry.id);
        const archiveAction = archived ? 'unarchive' : 'archive';
        const archiveLabel = archived ? 'Unarchive' : 'Archive';

        row.innerHTML = `
            <td class="select-col">
                <input type="checkbox" class="voice-select-checkbox" data-role="voice-select" ${isSelected ? 'checked' : ''}>
            </td>
            <td class="voice-name-cell">
                ${escapeHtml(entry.name || 'Untitled Voice')}
                ${entry.missing_file ? '<span class="badge badge-danger">Missing</span>' : ''}
                ${transcriptBadge}
            </td>
            <td>${genderBadge}</td>
            <td>${escapeHtml(languageText)}</td>
            <td>${durationText}</td>
            <td>${sourceBadge}</td>
            <td class="voice-actions">
                ${isExternal && !isDownloaded ? `
                    <button type="button" class="btn-ghost btn-download" data-action="download" data-voice-id="${entry.short_name}">Download</button>
                ` : `
                    <button type="button" class="btn-ghost chatterbox-preview-btn"
                        data-action="preview"
                        data-label-play="Play"
                        data-label-stop="Stop">
                        Play
                    </button>
                `}
                <button type="button" class="btn-ghost" data-action="export" ${!isDownloaded ? 'disabled' : ''}>Export</button>
                <button type="button" class="btn-ghost" data-action="${archiveAction}">${archiveLabel}</button>
                ${!isExternal ? `
                    ${!entry.transcript_available && !entry.missing_file ? `
                        <button type="button" class="btn-ghost" data-action="transcribe">Generate Transcript</button>
                    ` : ''}
                    <button type="button" class="btn-ghost" data-action="edit-meta">Edit</button>
                ` : ''}
                <button type="button" class="btn-danger" data-action="delete">Delete</button>
            </td>
        `;
        container.appendChild(row);
    });
}

function applyVoiceFilters(voices) {
    const searchInput = document.getElementById('voice-search-input');
    const sourceFilter = document.getElementById('voice-filter-source');
    const genderFilter = document.getElementById('voice-filter-gender');
    const languageFilter = document.getElementById('voice-filter-language');
    
    const searchTerm = (searchInput?.value || '').toLowerCase().trim();
    const sourceValue = sourceFilter?.value || 'all';
    const genderValue = genderFilter?.value || 'all';
    const languageValue = languageFilter?.value || 'all';
    
    return voices.filter(v => {
        // Search filter
        if (searchTerm) {
            const nameMatch = (v.name || '').toLowerCase().includes(searchTerm);
            const langMatch = (v.language || '').toLowerCase().includes(searchTerm);
            const fileMatch = (v.file_name || '').toLowerCase().includes(searchTerm);
            if (!nameMatch && !langMatch && !fileMatch) return false;
        }
        
        // Source filter
        if (sourceValue !== 'all' && v.source !== sourceValue) return false;
        
        // Gender filter
        if (genderValue !== 'all' && v.gender !== genderValue) return false;
        
        // Language filter
        if (languageValue !== 'all' && v.language !== languageValue) return false;
        
        return true;
    });
}

function sortVoices(voices, key, dir) {
    return [...voices].sort((a, b) => {
        let aVal = a[key] ?? '';
        let bVal = b[key] ?? '';
        
        if (key === 'duration') {
            aVal = a.duration_seconds ?? 0;
            bVal = b.duration_seconds ?? 0;
        }
        
        if (typeof aVal === 'string') {
            aVal = aVal.toLowerCase();
            bVal = bVal.toLowerCase();
        }
        
        if (aVal < bVal) return dir === 'asc' ? -1 : 1;
        if (aVal > bVal) return dir === 'asc' ? 1 : -1;
        return 0;
    });
}

function updateVoiceListStats(filtered, total) {
    const statsEl = document.getElementById('voice-count-display');
    if (statsEl) {
        if (filtered === total) {
            statsEl.textContent = `${total} voice${total !== 1 ? 's' : ''}`;
        } else {
            statsEl.textContent = `${filtered} of ${total} voices`;
        }
    }
}

function updateLanguageFilterOptions(voices) {
    const select = document.getElementById('voice-filter-language');
    if (!select) return;
    
    const currentValue = select.value;
    const languages = new Set();
    voices.forEach(v => {
        if (v.language) languages.add(v.language);
    });
    
    // Sort by display name, not locale code
    const sortedLangs = [...languages].sort((a, b) => 
        getLanguageDisplayName(a).localeCompare(getLanguageDisplayName(b))
    );
    select.innerHTML = '<option value="all">All Languages</option>';
    sortedLangs.forEach(lang => {
        const opt = document.createElement('option');
        opt.value = lang;
        opt.textContent = getLanguageDisplayName(lang);
        select.appendChild(opt);
    });
    
    // Restore selection if still valid
    if (currentValue && languages.has(currentValue)) {
        select.value = currentValue;
    }
}

function setupVoiceListControls() {
    // Search input
    const searchInput = document.getElementById('voice-search-input');
    if (searchInput) {
        let debounceTimer;
        searchInput.addEventListener('input', () => {
            clearTimeout(debounceTimer);
            debounceTimer = setTimeout(() => renderChatterboxVoiceList(), 200);
        });
    }
    
    // Filter selects
    ['voice-filter-source', 'voice-filter-gender', 'voice-filter-language'].forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener('change', () => renderChatterboxVoiceList());
        }
    });
    
    // Sort headers
    const table = document.getElementById('chatterbox-voice-table');
    if (table) {
        table.querySelectorAll('th.sortable').forEach(th => {
            th.addEventListener('click', () => {
                const sortKey = th.dataset.sort;
                if (voiceListSortKey === sortKey) {
                    voiceListSortDir = voiceListSortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    voiceListSortKey = sortKey;
                    voiceListSortDir = 'asc';
                }
                
                // Update sort indicators
                table.querySelectorAll('th.sortable').forEach(h => {
                    h.classList.remove('sort-asc', 'sort-desc');
                });
                th.classList.add(voiceListSortDir === 'asc' ? 'sort-asc' : 'sort-desc');
                
                renderChatterboxVoiceList();
            });
        });
    }
    const archiveTable = document.getElementById('chatterbox-voice-archive-table');
    if (archiveTable) {
        archiveTable.querySelectorAll('th.sortable').forEach(th => {
            th.addEventListener('click', () => {
                const sortKey = th.dataset.sort;
                if (voiceListSortKey === sortKey) {
                    voiceListSortDir = voiceListSortDir === 'asc' ? 'desc' : 'asc';
                } else {
                    voiceListSortKey = sortKey;
                    voiceListSortDir = 'asc';
                }
                archiveTable.querySelectorAll('th.sortable').forEach(h => {
                    h.classList.remove('sort-asc', 'sort-desc');
                });
                th.classList.add(voiceListSortDir === 'asc' ? 'sort-asc' : 'sort-desc');
                renderChatterboxVoiceList();
            });
        });
    }
    
    // Load external voices button
    const loadExternalBtn = document.getElementById('load-external-voices-btn');
    if (loadExternalBtn) {
        loadExternalBtn.addEventListener('click', loadExternalVoices);
    }

    const selectAllActive = document.getElementById('voice-select-all');
    if (selectAllActive) {
        selectAllActive.addEventListener('change', event => {
            const checked = event.target.checked;
            getVoiceRowCheckboxes('active').forEach(checkbox => {
                checkbox.checked = checked;
                updateRowSelection(checkbox.closest('tr'), checked);
            });
        });
    }

    const selectAllArchived = document.getElementById('voice-archive-select-all');
    if (selectAllArchived) {
        selectAllArchived.addEventListener('change', event => {
            const checked = event.target.checked;
            getVoiceRowCheckboxes('archived').forEach(checkbox => {
                checkbox.checked = checked;
                updateRowSelection(checkbox.closest('tr'), checked);
            });
        });
    }

    const batchExportBtn = document.getElementById('voice-batch-export-btn');
    if (batchExportBtn) {
        batchExportBtn.addEventListener('click', () => handleBatchExport('active'));
    }
    const batchArchiveBtn = document.getElementById('voice-batch-archive-btn');
    if (batchArchiveBtn) {
        batchArchiveBtn.addEventListener('click', () => handleBatchArchive('active'));
    }
    const batchTranscribeBtn = document.getElementById('voice-batch-transcribe-btn');
    if (batchTranscribeBtn) {
        batchTranscribeBtn.addEventListener('click', () => handleBatchTranscription(batchTranscribeBtn));
    }
    const batchDeleteBtn = document.getElementById('voice-batch-delete-btn');
    if (batchDeleteBtn) {
        batchDeleteBtn.addEventListener('click', () => handleBatchDelete('active'));
    }

    const archiveExportBtn = document.getElementById('voice-archive-export-btn');
    if (archiveExportBtn) {
        archiveExportBtn.addEventListener('click', () => handleBatchExport('archived'));
    }
    const archiveRestoreBtn = document.getElementById('voice-archive-restore-btn');
    if (archiveRestoreBtn) {
        archiveRestoreBtn.addEventListener('click', () => handleBatchArchive('archived'));
    }
    const archiveDeleteBtn = document.getElementById('voice-archive-delete-btn');
    if (archiveDeleteBtn) {
        archiveDeleteBtn.addEventListener('click', () => handleBatchDelete('archived'));
    }
    
    // Table row actions (delegated)
    const tbody = document.getElementById('chatterbox-voice-list');
    if (tbody) {
        tbody.addEventListener('click', handleVoiceTableAction);
        tbody.addEventListener('change', event => {
            const target = event.target;
            if (!(target instanceof HTMLInputElement)) return;
            if (!target.classList.contains('voice-select-checkbox')) return;
            updateRowSelection(target.closest('tr'), target.checked);
        });
    }
    const archiveBody = document.getElementById('chatterbox-voice-archive-list');
    if (archiveBody) {
        archiveBody.addEventListener('click', handleVoiceTableAction);
        archiveBody.addEventListener('change', event => {
            const target = event.target;
            if (!(target instanceof HTMLInputElement)) return;
            if (!target.classList.contains('voice-select-checkbox')) return;
            updateRowSelection(target.closest('tr'), target.checked);
        });
    }
}

async function loadExternalVoices() {
    const btn = document.getElementById('load-external-voices-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Loading...';
    }
    
    try {
        const response = await fetch('/api/external-voices');
        const data = await response.json();
        if (data.success) {
            externalVoices = data.voices || [];
            showToast(`Loaded ${externalVoices.length} external voices`, 'success');
            renderChatterboxVoiceList();
        } else {
            throw new Error(data.error || 'Failed to load external voices');
        }
    } catch (error) {
        console.error('Failed to load external voices:', error);
        showToast(error.message || 'Failed to load external voices', 'error');
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Load External Voices';
        }
    }
}

async function handleVoiceTableAction(event) {
    const btn = event.target.closest('[data-action]');
    if (!btn) return;
    
    const action = btn.dataset.action;
    const row = btn.closest('tr');
    const voiceId = row?.dataset.voiceId;
    const source = row?.dataset.source;
    
    if (action === 'preview') {
        if (source === 'external') {
            const shortName = voiceId.replace('external:', '');
            previewExternalVoice(shortName, btn);
        } else {
            toggleChatterboxVoicePreview(voiceId, btn);
        }
    } else if (action === 'download') {
        const shortName = btn.dataset.voiceId;
        await downloadExternalVoice(shortName, btn);
    } else if (action === 'export') {
        await handleRowExport(voiceId);
    } else if (action === 'archive') {
        await handleRowArchive(voiceId, true);
    } else if (action === 'unarchive') {
        await handleRowArchive(voiceId, false);
    } else if (action === 'delete') {
        await handleRowDelete(voiceId);
    } else if (action === 'edit-meta') {
        await editVoiceMetadata(voiceId);
    } else if (action === 'transcribe') {
        await generateVoiceTranscript(voiceId, btn);
    }
}

async function requestVoiceTranscript(voiceId) {
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 180000);
    let response;
    try {
        response = await fetch(`/api/chatterbox-voices/${encodeURIComponent(voiceId)}/transcribe`, {
            method: 'POST',
            signal: controller.signal,
        });
    } catch (error) {
        const wrapped = new Error(
            error?.name === 'AbortError'
                ? 'Transcription timed out after three minutes.'
                : 'The transcription service could not be reached.'
        );
        wrapped.fatal = true;
        throw wrapped;
    } finally {
        clearTimeout(timeoutId);
    }
    const data = await response.json().catch(() => ({}));
    if (!response.ok || !data.success) {
        const error = new Error(
            (response.status === 404 || response.status === 405)
                ? 'The transcription service is not loaded. Restart the TTS-Story backend and refresh this page.'
                : (data.error || 'Unable to generate the transcript.')
        );
        error.fatal = response.status === 404 || response.status === 405 || response.status >= 500;
        throw error;
    }
    return data;
}

async function generateVoiceTranscript(voiceId, button) {
    if (!voiceId) return;
    const originalLabel = button?.textContent || 'Generate Transcript';
    if (button) {
        button.disabled = true;
        button.textContent = 'Transcribing…';
    }
    try {
        const data = await requestVoiceTranscript(voiceId);
        await loadChatterboxVoices();
        showToast(`Transcript generated: ${data.transcript}`, 'success');
    } catch (error) {
        console.error('Voice transcription failed', error);
        showToast(error.message || 'Voice transcription failed', 'error');
        if (button) {
            button.disabled = false;
            button.textContent = originalLabel;
        }
    }
}

async function handleBatchTranscription(button) {
    const voiceIds = Array.from(selectedVoiceIds).filter(id => {
        const voice = chatterboxVoices.find(entry => entry.id === id);
        return voice && !voice.transcript_available && !voice.missing_file;
    });
    if (!voiceIds.length) return;
    const originalLabel = button?.textContent || 'Generate Transcripts';
    if (button) button.disabled = true;
    let completed = 0;
    const failures = [];
    let fatalError = null;
    for (const voiceId of voiceIds) {
        if (button) button.textContent = `Transcribing ${completed + 1} of ${voiceIds.length}…`;
        try {
            await requestVoiceTranscript(voiceId);
            completed += 1;
        } catch (error) {
            const voice = chatterboxVoices.find(entry => entry.id === voiceId);
            failures.push(`${voice?.name || voiceId}: ${error.message}`);
            if (error.fatal) {
                fatalError = error;
                break;
            }
        }
    }
    await loadChatterboxVoices();
    if (fatalError) {
        console.error('Voice transcript batch stopped', failures);
        showToast(fatalError.message, 'error');
    } else if (failures.length) {
        console.error('Some voice transcripts failed', failures);
        showToast(`Generated ${completed} transcript(s); ${failures.length} failed.`, 'warning');
    } else {
        showToast(`Generated ${completed} transcript${completed === 1 ? '' : 's'}.`, 'success');
    }
    if (button && !document.body.contains(button)) return;
    if (button) button.textContent = originalLabel;
    updateBatchToolbar('active');
}

async function handleBatchExport(scope) {
    const voiceIds = Array.from(getSelectionSet(scope));
    if (!voiceIds.length) return;
    try {
        await exportVoicesBatch(voiceIds);
    } catch (error) {
        console.error('Batch export failed', error);
        showToast(error.message || 'Export failed', 'error');
    }
}

async function handleBatchArchive(scope) {
    const voiceIds = Array.from(getSelectionSet(scope));
    if (!voiceIds.length) return;
    const archived = scope === 'active';
    try {
        await applyArchiveState(voiceIds, archived);
        voiceIds.forEach(id => getSelectionSet(scope).delete(id));
        await loadChatterboxVoices();
        renderChatterboxVoiceList();
        showToast(archived ? 'Voices archived.' : 'Voices restored.', 'success');
    } catch (error) {
        console.error('Archive update failed', error);
        showToast(error.message || 'Archive update failed', 'error');
    }
}

async function handleBatchDelete(scope) {
    const voiceIds = Array.from(getSelectionSet(scope));
    if (!voiceIds.length) return;
    const confirmed = confirm(`Delete ${voiceIds.length} voice sample${voiceIds.length === 1 ? '' : 's'}? This cannot be undone.`);
    if (!confirmed) return;
    try {
        await deleteVoicesBatch(voiceIds);
        voiceIds.forEach(id => getSelectionSet(scope).delete(id));
        await loadChatterboxVoices();
        renderChatterboxVoiceList();
        showToast('Voices deleted.', 'success');
    } catch (error) {
        console.error('Batch delete failed', error);
        showToast(error.message || 'Delete failed', 'error');
    }
}

async function handleRowExport(voiceId) {
    if (!voiceId) return;
    try {
        await exportVoicesBatch([voiceId]);
    } catch (error) {
        console.error('Export failed', error);
        showToast(error.message || 'Export failed', 'error');
    }
}

async function handleRowArchive(voiceId, archived) {
    if (!voiceId) return;
    try {
        await applyArchiveState([voiceId], archived);
        selectedVoiceIds.delete(voiceId);
        selectedArchivedVoiceIds.delete(voiceId);
        await loadChatterboxVoices();
        renderChatterboxVoiceList();
        showToast(archived ? 'Voice archived.' : 'Voice restored.', 'success');
    } catch (error) {
        console.error('Archive update failed', error);
        showToast(error.message || 'Archive update failed', 'error');
    }
}

async function handleRowDelete(voiceId) {
    if (!voiceId) return;
    const confirmed = confirm('Delete this voice sample? This cannot be undone.');
    if (!confirmed) return;
    try {
        await deleteVoicesBatch([voiceId]);
        selectedVoiceIds.delete(voiceId);
        selectedArchivedVoiceIds.delete(voiceId);
        await loadChatterboxVoices();
        renderChatterboxVoiceList();
        showToast('Voice deleted.', 'success');
    } catch (error) {
        console.error('Delete failed', error);
        showToast(error.message || 'Delete failed', 'error');
    }
}

async function downloadExternalVoice(shortName, btn) {
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Downloading...';
    }
    
    try {
        const response = await fetch(`/api/external-voices/${shortName}/download`, {
            method: 'POST'
        });
        const data = await response.json();
        if (data.success) {
            showToast(`Downloaded ${shortName}`, 'success');
            await loadChatterboxVoices(); // Refresh local voices
            renderChatterboxVoiceList();
        } else {
            throw new Error(data.error || 'Download failed');
        }
    } catch (error) {
        console.error('Download failed:', error);
        showToast(error.message || 'Download failed', 'error');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Download';
        }
    }
}

async function previewExternalVoice(shortName, btn) {
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Loading...';
    }
    
    try {
        const audio = new Audio(`/api/external-voices/${shortName}/preview`);
        audio.addEventListener('ended', () => {
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Play';
            }
        });
        audio.addEventListener('error', () => {
            showToast('Failed to play preview', 'error');
            if (btn) {
                btn.disabled = false;
                btn.textContent = 'Play';
            }
        });
        await audio.play();
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Stop';
        }
    } catch (error) {
        console.error('Preview failed:', error);
        showToast('Failed to play preview', 'error');
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'Play';
        }
    }
}

async function editVoiceMetadata(voiceId) {
    const entry = chatterboxVoices.find(v => v.id === voiceId);
    if (!entry) return;
    
    openEditVoiceModal(entry);
}

function openEditVoiceModal(entry) {
    const overlay = document.getElementById('edit-voice-modal-overlay');
    const modal = document.getElementById('edit-voice-modal');
    const idInput = document.getElementById('edit-voice-id');
    const nameInput = document.getElementById('edit-voice-name');
    const genderSelect = document.getElementById('edit-voice-gender');
    const languageSelect = document.getElementById('edit-voice-language');
    const transcriptInput = document.getElementById('edit-voice-transcript');
    
    if (!overlay || !modal) return;
    
    // Populate language dropdown with all available locales
    languageSelect.innerHTML = '<option value="">— Not specified —</option>';
    Object.entries(VM_LOCALE_NAMES).sort((a, b) => a[1].localeCompare(b[1])).forEach(([code, name]) => {
        const opt = document.createElement('option');
        opt.value = code;
        opt.textContent = name;
        languageSelect.appendChild(opt);
    });
    
    // Fill in current values
    idInput.value = entry.id || '';
    nameInput.value = entry.name || '';
    genderSelect.value = entry.gender || '';
    languageSelect.value = entry.language || '';
    if (transcriptInput) transcriptInput.value = entry.transcript || '';
    
    // Show modal
    overlay.classList.remove('hidden');
    modal.classList.remove('hidden');
    nameInput.focus();
}

function closeEditVoiceModal() {
    const overlay = document.getElementById('edit-voice-modal-overlay');
    const modal = document.getElementById('edit-voice-modal');
    if (overlay) overlay.classList.add('hidden');
    if (modal) modal.classList.add('hidden');
}

async function saveEditVoiceModal() {
    const idInput = document.getElementById('edit-voice-id');
    const nameInput = document.getElementById('edit-voice-name');
    const genderSelect = document.getElementById('edit-voice-gender');
    const languageSelect = document.getElementById('edit-voice-language');
    const transcriptInput = document.getElementById('edit-voice-transcript');
    
    const voiceId = idInput.value;
    const name = nameInput.value.trim();
    const gender = genderSelect.value || null;
    const language = languageSelect.value || null;
    const transcript = transcriptInput?.value?.trim() || '';
    
    if (!voiceId) return;
    
    try {
        const response = await fetch(`/api/chatterbox-voices/${voiceId}/update`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ name, gender, language, transcript })
        });
        const data = await response.json();
        if (data.success) {
            showToast('Voice updated', 'success');
            closeEditVoiceModal();
            await loadChatterboxVoices();
        } else {
            throw new Error(data.error || 'Update failed');
        }
    } catch (error) {
        console.error('Update failed:', error);
        showToast(error.message || 'Update failed', 'error');
    }
}

function initEditVoiceModal() {
    const overlay = document.getElementById('edit-voice-modal-overlay');
    const closeBtn = document.getElementById('edit-voice-close');
    const cancelBtn = document.getElementById('edit-voice-cancel');
    const saveBtn = document.getElementById('edit-voice-save');
    
    if (overlay) overlay.addEventListener('click', closeEditVoiceModal);
    if (closeBtn) closeBtn.addEventListener('click', closeEditVoiceModal);
    if (cancelBtn) cancelBtn.addEventListener('click', closeEditVoiceModal);
    if (saveBtn) saveBtn.addEventListener('click', saveEditVoiceModal);
    
    // Handle Enter key in form
    const form = document.getElementById('edit-voice-form');
    if (form) {
        form.addEventListener('keydown', (e) => {
            if (e.key === 'Enter') {
                e.preventDefault();
                saveEditVoiceModal();
            }
        });
    }
}

function summarizeFileSize(bytes) {
    if (typeof bytes !== 'number' || Number.isNaN(bytes)) return '';
    if (bytes < 1024) {
        return `${bytes} B`;
    }
    const units = ['KB', 'MB', 'GB'];
    let value = bytes / 1024;
    let unitIndex = 0;
    while (value >= 1024 && unitIndex < units.length - 1) {
        value /= 1024;
        unitIndex += 1;
    }
    return `${value.toFixed(1)} ${units[unitIndex]}`;
}

function escapeHtml(value = '') {
    const div = document.createElement('div');
    div.textContent = value;
    return div.innerHTML;
}

async function renameChatterboxVoice(voiceId) {
    const entry = chatterboxVoices.find(item => item.id === voiceId);
    if (!entry) return;
    const nextName = prompt('Rename voice', entry.name || '');
    if (!nextName) {
        return;
    }
    const trimmed = nextName.trim();
    if (!trimmed || trimmed === entry.name) {
        return;
    }
    try {
        const response = await fetch(`/api/chatterbox-voices/${voiceId}`, {
            method: 'PUT',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ name: trimmed }),
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to rename voice');
        }
        showToast('Voice renamed.', 'success');
        await loadChatterboxVoices();
    } catch (error) {
        console.error('Failed to rename voice', error);
        showToast(error.message || 'Failed to rename voice', 'error');
    }
}

async function deleteChatterboxVoice(voiceId) {
    const entry = chatterboxVoices.find(item => item.id === voiceId);
    if (!entry) return;
    const confirmed = confirm(`Delete Chatterbox voice "${entry.name}"? This cannot be undone.`);
    if (!confirmed) return;
    try {
        const response = await fetch(`/api/chatterbox-voices/${voiceId}`, {
            method: 'DELETE',
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to delete voice');
        }
        showToast('Voice deleted.', 'success');
        await loadChatterboxVoices();
    } catch (error) {
        console.error('Failed to delete voice', error);
        showToast(error.message || 'Failed to delete voice', 'error');
    }
}

async function copyChatterboxVoicePath(voiceId) {
    const entry = chatterboxVoices.find(item => item.id === voiceId);
    if (!entry) return;
    const path = entry.prompt_path || entry.file_name;
    if (!path) {
        showToast('Voice file path unavailable.', 'warning');
        return;
    }
    try {
        await navigator.clipboard.writeText(path);
        showToast('Path copied to clipboard.', 'success');
    } catch (error) {
        console.error('Clipboard copy failed', error);
        showToast('Unable to copy path. Copy it manually from the list.', 'warning');
    }
}

function toggleChatterboxVoicePreview(voiceId, triggerButton) {
    if (!voiceId) return;
    if (!window.chatterboxPreviewController) {
        showToast('Preview controls are still loading. Try again shortly.', 'warning');
        return;
    }
    window.chatterboxPreviewController.toggleById(voiceId, triggerButton);
}

function emitVoicesUpdated() {
    const detail = {
        voices: voiceData,
        samplesReady,
        customVoiceMap: window.customVoiceMap,
        pocketTtsVoices: window.availablePocketTtsVoices,
    };
    window.dispatchEvent(new CustomEvent(VOICES_UPDATED_EVENT, { detail }));
}

function emitChatterboxVoicesUpdated() {
    const detail = {
        voices: chatterboxVoices,
    };
    window.dispatchEvent(new CustomEvent(CHATTERBOX_VOICES_EVENT, { detail }));
}

function updateCustomVoiceMap(voices) {
    const map = {};
    if (voices && typeof voices === 'object') {
        Object.values(voices).forEach(config => {
            if (!config) return;
            const langCode = config.lang_code;
            (config.custom_voices || []).forEach(entry => {
                if (!entry || !entry.code) return;
                map[entry.code] = {
                    ...entry,
                    lang_code: entry.lang_code || langCode,
                };
            });
        });
    }
    window.customVoiceMap = map;
}

async function loadCustomVoices() {
    try {
        const response = await fetch('/api/custom-voices');
        const data = await response.json();
        if (data.success) {
            customVoices = data.voices || [];
            renderCustomVoices();
        } else {
            showToast(data.error || 'Unable to load custom voices', 'error');
        }
    } catch (error) {
        console.error('Failed to load custom voices', error);
        showToast('Failed to load custom voices', 'error');
    }
}

function renderCustomVoices() {
    const container = document.getElementById('custom-voices-list');
    if (!container) return;

    if (!customVoices.length) {
        container.innerHTML = '<p class="help-text">You haven’t created any blends yet. Click “New Custom Voice” to get started.</p>';
        return;
    }

    container.innerHTML = '';
    customVoices.forEach(entry => {
        const card = document.createElement('div');
        card.className = 'custom-voice-card';
        card.dataset.voiceCode = entry.code;
        card.innerHTML = `
            <div class="custom-voice-title">
                <div>
                    <strong>${entry.name}</strong>
                </div>
                <span class="voice-badge">Lang ${entry.lang_code?.toUpperCase() ?? ''}</span>
            </div>
            <div class="custom-voice-components">
                ${renderComponentList(entry.components)}
            </div>
            <div class="custom-voice-meta">
                <span class="badge-muted">${entry.code}</span>
                ${entry.updated_at ? `<span>Updated ${new Date(entry.updated_at).toLocaleString()}</span>` : ''}
            </div>
            <div class="custom-voice-actions">
                <button class="btn-ghost" data-action="edit">Edit</button>
                <button class="btn-danger" data-action="delete">Delete</button>
            </div>
        `;

        card.querySelector('[data-action="edit"]').addEventListener('click', () => openCustomVoiceModal(entry));
        card.querySelector('[data-action="delete"]').addEventListener('click', () => deleteCustomVoice(entry));
        container.appendChild(card);
    });
}

function renderComponentList(components = []) {
    if (!components.length) {
        return '<em>No components defined.</em>';
    }
    return components.map(comp => {
        const weight = Number(comp.weight ?? 1).toFixed(2).replace(/\.00$/, '');
        return `<div>${comp.voice} <span class="badge-muted">x${weight}</span></div>`;
    }).join('');
}

function setupCustomVoiceModal() {
    const overlay = document.getElementById('custom-voice-modal-overlay');
    const modal = document.getElementById('custom-voice-modal');
    const openBtn = document.getElementById('create-custom-voice-btn');
    const closeBtn = document.getElementById('custom-voice-modal-close');
    const cancelBtn = document.getElementById('custom-voice-cancel');
    const saveBtn = document.getElementById('custom-voice-save');
    const addComponentBtn = document.getElementById('add-component-btn');

    if (!overlay || !modal) return;

    function closeModal() {
        overlay.classList.add('hidden');
        modal.classList.add('hidden');
        modal.dataset.editCode = '';
        document.getElementById('custom-voice-form').reset();
        const rows = document.getElementById('custom-voice-components');
        rows.innerHTML = '';
    }

    function openModal(entry = null) {
        overlay.classList.remove('hidden');
        modal.classList.remove('hidden');
        const title = document.getElementById('custom-voice-modal-title');
        const nameInput = document.getElementById('custom-voice-name');
        const langSelect = document.getElementById('custom-voice-lang');
        const notesInput = document.getElementById('custom-voice-notes');
        const rows = document.getElementById('custom-voice-components');

        rows.innerHTML = '';
        if (entry) {
            modal.dataset.editCode = entry.code;
            title.textContent = 'Edit Custom Voice';
            nameInput.value = entry.name || '';
            langSelect.value = entry.lang_code || 'a';
            notesInput.value = entry.notes || '';
            (entry.components || []).forEach(component => addComponentRow(component));
        } else {
            modal.dataset.editCode = '';
            title.textContent = 'Create Custom Voice';
            nameInput.value = '';
            langSelect.value = 'a';
            notesInput.value = '';
            addComponentRow();
        }
    }

    function addComponentRow(component = null) {
        const rows = document.getElementById('custom-voice-components');
        const row = document.createElement('div');
        row.className = 'component-row';
        const voiceSelect = buildVoiceSelect(component?.voice, document.getElementById('custom-voice-lang').value);
        voiceSelect.classList.add('component-voice-select');
        const weightInput = document.createElement('input');
        weightInput.type = 'number';
        weightInput.min = '0.1';
        weightInput.step = '0.1';
        weightInput.value = component?.weight ?? 1;
        weightInput.classList.add('component-weight-input');
        const removeBtn = document.createElement('button');
        removeBtn.type = 'button';
        removeBtn.className = 'remove-component';
        removeBtn.innerHTML = '&times;';
        removeBtn.addEventListener('click', () => {
            if (rows.children.length > 1) {
                row.remove();
            } else {
                showToast('Need at least one component.', 'warning');
            }
        });
        row.appendChild(voiceSelect);
        row.appendChild(weightInput);
        row.appendChild(removeBtn);
        rows.appendChild(row);
    }

    function buildVoiceSelect(selectedVoice = '', langCode = 'a') {
        const select = document.createElement('select');
        const voices = getVoicesForLang(langCode);
        voices.forEach(voice => {
            const option = document.createElement('option');
            option.value = voice;
            option.textContent = voice;
            if (voice === selectedVoice) {
                option.selected = true;
            }
            select.appendChild(option);
        });
        return select;
    }

    function getVoicesForLang(langCode = 'a') {
        if (!window.availableVoices) return [];
        const entry = Object.values(window.availableVoices).find(cfg => cfg.lang_code === langCode);
        return entry ? entry.voices : [];
    }

    openBtn?.addEventListener('click', () => openModal());
    closeBtn?.addEventListener('click', closeModal);
    cancelBtn?.addEventListener('click', closeModal);
    overlay?.addEventListener('click', event => {
        if (event.target === overlay) closeModal();
    });
    addComponentBtn?.addEventListener('click', () => addComponentRow());

    document.getElementById('custom-voice-lang')?.addEventListener('change', event => {
        const rows = document.querySelectorAll('.component-row select');
        rows.forEach(select => {
            const value = select.value;
            const newSelect = buildVoiceSelect(value, event.target.value);
            newSelect.className = select.className;
            select.replaceWith(newSelect);
        });
    });

    saveBtn?.addEventListener('click', async () => {
        const form = document.getElementById('custom-voice-form');
        const name = document.getElementById('custom-voice-name').value.trim();
        const lang = document.getElementById('custom-voice-lang').value;
        const notes = document.getElementById('custom-voice-notes').value.trim();
        const components = Array.from(document.querySelectorAll('.component-row')).map(row => ({
            voice: row.querySelector('select').value,
            weight: parseFloat(row.querySelector('.component-weight-input').value || 1),
        }));

        if (!name) {
            showToast('Name is required.', 'warning');
            return;
        }
        if (!components.length) {
            showToast('Add at least one component.', 'warning');
            return;
        }

        const payload = { name, lang_code: lang, notes, components };
        const isEdit = Boolean(modal.dataset.editCode);
        const url = isEdit ? `/api/custom-voices/${modal.dataset.editCode}` : '/api/custom-voices';
        const method = isEdit ? 'PUT' : 'POST';

        try {
            const response = await fetch(url, {
                method,
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload),
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Failed to save custom voice');
            }
            showToast(isEdit ? 'Custom voice updated.' : 'Custom voice created!', 'success');
            closeModal();
            await loadCustomVoices();
            await loadVoices();
        } catch (error) {
            console.error('Failed to save custom voice', error);
            showToast(error.message || 'Failed to save custom voice.', 'error');
        }
    });

    function openCustomVoiceModal(entry) {
        openModal(entry);
    }

    function deleteCustomVoice(entry) {
        if (!entry) return;
        if (!confirm(`Delete custom voice "${entry.name}"? This cannot be undone.`)) {
            return;
        }
        fetch(`/api/custom-voices/${entry.code}`, {
            method: 'DELETE',
        })
            .then(res => res.json())
            .then(data => {
                if (!data.success) {
                    throw new Error(data.error || 'Failed to delete custom voice');
                }
                showToast('Custom voice deleted.', 'success');
                loadCustomVoices();
                loadVoices();
            })
            .catch(err => {
                console.error('Delete custom voice failed', err);
                showToast(err.message || 'Failed to delete custom voice', 'error');
            });
    }

    window.openCustomVoiceModal = openCustomVoiceModal;
    window.deleteCustomVoice = deleteCustomVoice;
    window.addComponentRow = addComponentRow;
}

function summarizeVoiceList(list, max = 5) {
    if (!Array.isArray(list) || list.length === 0) {
        return 'None';
    }
    const uniqueVoices = [...new Set(list)];
    const shown = uniqueVoices.slice(0, max);
    const remainder = uniqueVoices.length - shown.length;
    return remainder > 0
        ? `${shown.join(', ')} +${remainder} more`
        : shown.join(', ');
}

function updateSampleStatus(data) {
    const statusContainer = document.getElementById(sampleStatusId);
    const buttonContainer = document.getElementById('voice-sample-controls');

    if (!statusContainer || !buttonContainer) {
        return;
    }

    const failedList = Array.isArray(data.failed)
        ? data.failed
        : lastFailedSamples;
    if (Array.isArray(data.failed)) {
        lastFailedSamples = data.failed;
    }

    const missingList = Array.isArray(data.missing_samples) ? data.missing_samples : [];
    const missingCount = missingList.length;
    const failedCount = failedList.length;
    const totalVoices = data.total_unique_voices || 0;
    const generatedCount = data.sample_count || 0;

    let summaryMessage = '';
    let statusClass = 'info';
    const detailMessages = [];

    if (missingCount === 0 && failedCount === 0 && generatedCount > 0) {
        summaryMessage = `All ${generatedCount} voice previews are ready.`;
        statusClass = 'success';
        buttonContainer.style.display = 'none';
    } else {
        const missingSummary = missingCount > 0
            ? `${missingCount} of ${totalVoices} voices still need previews`
            : 'Some voices are ready to preview';
        summaryMessage = missingSummary;

        if (missingCount > 0) {
            detailMessages.push(`Missing previews: ${summarizeVoiceList(missingList)}`);
        }

        if (failedCount > 0) {
            const failedNames = failedList
                .map(item => (typeof item === 'string' ? item : item.voice))
                .filter(Boolean);
            detailMessages.push(`Failed to generate: ${summarizeVoiceList(failedNames)}`);
            statusClass = 'warning';
        } else if (missingCount > 0) {
            statusClass = 'warning';
        } else {
            statusClass = 'info';
        }

        buttonContainer.style.display = 'flex';
    }

    statusContainer.className = `sample-status ${statusClass}`.trim();
    statusContainer.innerHTML = `
        <div>${summaryMessage}</div>
        ${detailMessages.length ? `<div class="sample-status-details">${detailMessages.join('<br>')}</div>` : ''}
    `;
}

function displaySampleError(message) {
    const statusContainer = document.getElementById(sampleStatusId);
    const buttonContainer = document.getElementById('voice-sample-controls');
    if (statusContainer) {
        statusContainer.textContent = message;
        statusContainer.className = 'sample-status error';
    }
    if (buttonContainer) {
        buttonContainer.style.display = 'flex';
    }
}

// Display voice library
function displayVoiceLibrary(voices) {
    const container = document.getElementById('voice-library');
    container.innerHTML = '';
    
    const languageNames = {
        'american_english': '🇺🇸 American English',
        'british_english': '🇬🇧 British English',
        'spanish': '🇪🇸 Spanish',
        'french': '🇫🇷 French',
        'hindi': '🇮🇳 Hindi',
        'japanese': '🇯🇵 Japanese',
        'chinese': '🇨🇳 Chinese',
        'brazilian_portuguese': '🇧🇷 Brazilian Portuguese',
    };
    
    for (const [key, config] of Object.entries(voices)) {
        const category = document.createElement('div');
        category.className = 'voice-category';
        
        const title = document.createElement('h3');
        title.textContent = languageNames[key] || key;
        category.appendChild(title);
        
        const list = document.createElement('ul');
        list.className = 'voice-list';
        
        config.voices.forEach(voice => {
            const item = document.createElement('li');
            item.className = 'voice-item';
            item.dataset.voice = voice;
            item.dataset.langCode = config.lang_code;
            
            const samplePath = (config.samples && config.samples[voice]) || null;
            if (samplePath) {
                item.classList.add('has-preview');
                item.dataset.samplePath = samplePath;
            }
            
            const friendlyName = voice.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
            
            const info = document.createElement('div');
            info.className = 'voice-info';
            info.innerHTML = `
                <span class="voice-name">${friendlyName}</span>
                <span class="voice-code">${voice}</span>
            `;
            item.appendChild(info);
            
            const status = document.createElement('div');
            status.className = 'voice-status';
            status.textContent = samplePath ? 'Preview ready' : 'Preview unavailable';
            if (!samplePath) {
                status.classList.add('muted');
            }
            item.appendChild(status);
            
            item.addEventListener('click', () => {
                playVoicePreview(voice, config.lang_code, samplePath, item);
            });
            
            list.appendChild(item);
        });
        
        category.appendChild(list);
        container.appendChild(category);
    }
}

async function generateSamples(overwrite = false) {
    const button = document.getElementById(generateSamplesBtnId);
    const regenButton = document.getElementById(regenerateSamplesBtnId);
    const statusContainer = document.getElementById(sampleStatusId);

    if (!button || !statusContainer) {
        return;
    }

    button.disabled = true;
    button.textContent = overwrite ? 'Regenerating samples…' : 'Generating samples…';
    if (regenButton) {
        regenButton.disabled = true;
    }
    statusContainer.textContent = 'Generating preview samples, please wait…';
    statusContainer.className = 'sample-status info';

    try {
        const response = await fetch('/api/voices/samples', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ overwrite })
        });

        const data = await response.json();

        if (data.success) {
            samplesReady = data.samples_ready;
            lastFailedSamples = Array.isArray(data.failed) ? data.failed : [];
            if (data.voices) {
                voiceData = data.voices;
                window.availableVoices = data.voices;
                updateCustomVoiceMap(data.voices);
                updateSampleStatus(data);
                displayVoiceLibrary(data.voices);
                emitVoicesUpdated();
            } else {
                await loadVoices();
            }
            const failedCount = data.failed ? data.failed.length : 0;
            const generatedCount = data.generated ? data.generated.length : 0;
            if (failedCount > 0) {
                showToast(`${generatedCount} previews generated, ${failedCount} failed. Check status for details.`, 'info');
            } else {
                showToast('Voice previews generated successfully!', 'success');
            }
        } else {
            throw new Error(data.error || 'Unknown error');
        }
    } catch (error) {
        console.error('Error generating voice samples:', error);
        showToast('Failed to generate voice samples: ' + error.message, 'error');
        displaySampleError('Failed to generate voice samples. Please check the server logs.');
    } finally {
        const refreshedButton = document.getElementById(generateSamplesBtnId);
        const refreshedRegenButton = document.getElementById(regenerateSamplesBtnId);
        if (refreshedButton) {
            refreshedButton.disabled = false;
            refreshedButton.textContent = 'Generate Voice Previews';
        }
        if (refreshedRegenButton) {
            refreshedRegenButton.disabled = false;
        }
    }
}

function showToast(message, type) {
    if (window.showNotification) {
        window.showNotification(message, type);
    } else {
        alert(message);
    }
}

// Play voice preview using generated samples
function playVoicePreview(voice, langCode, samplePath, listItem) {
    if (!samplePath) {
        alert(`Preview not available for ${voice}. Click "Generate Voice Previews" to create samples.`);
        return;
    }

    if (currentPreviewAudio) {
        currentPreviewAudio.pause();
        currentPreviewAudio.currentTime = 0;
        if (currentPreviewItem) {
            currentPreviewItem.classList.remove('playing');
        }
    }

    if (!audioPreviewCache[voice]) {
        audioPreviewCache[voice] = new Audio(samplePath);
    }

    const audio = audioPreviewCache[voice];
    currentPreviewAudio = audio;
    currentPreviewItem = listItem;

    audio.currentTime = 0;
    audio.play().then(() => {
        listItem.classList.add('playing');
    }).catch(err => {
        console.error('Error playing preview:', err);
        alert('Unable to play preview. See console for details.');
    });

    audio.onended = () => {
        listItem.classList.remove('playing');
        currentPreviewAudio = null;
        currentPreviewItem = null;
    };
}

// Get voice info
function getVoiceInfo(voiceName) {
    if (!voiceData) return null;
    
    for (const [key, config] of Object.entries(voiceData)) {
        if (config.voices.includes(voiceName)) {
            return {
                language: key,
                lang_code: config.lang_code,
                voice: voiceName
            };
        }
    }
    
    return null;
}

// ---------------------------------------------------------------------------
// Voice Creation engine toggle (Qwen3 / Breeze / OmniVoice)

function setupVoiceCreationEngineToggle() {
    const qwen3Btn = document.getElementById('voice-creation-qwen3-btn');
    const breezeBtn = document.getElementById('voice-creation-breeze-btn');
    const omniBtn = document.getElementById('voice-creation-omnivoice-btn');
    const qwen3Fields = document.getElementById('voice-creation-qwen3-fields');
    const omniFields = document.getElementById('voice-creation-omnivoice-fields');
    if (!qwen3Btn || !breezeBtn || !omniBtn) return;

    const activate = engine => {
        qwen3Btn.classList.toggle('active', engine === 'qwen3');
        breezeBtn.classList.toggle('active', engine === 'breeze');
        omniBtn.classList.toggle('active', engine === 'omnivoice');
        if (qwen3Fields) qwen3Fields.style.display = engine === 'omnivoice' ? 'none' : '';
        if (omniFields) omniFields.style.display = engine === 'omnivoice' ? '' : 'none';
        if (engine !== 'omnivoice') {
            qwenVoicePreview = null;
            const preview = document.getElementById('qwen-voice-preview');
            if (preview) {
                preview.removeAttribute('src');
                preview.load();
            }
            const save = document.getElementById('qwen-voice-save-btn');
            if (save) save.disabled = true;
            loadQwenVoiceLanguages(engine);
        }
        window.dispatchEvent(new CustomEvent('voiceCreationEngineChanged', { detail: { engine } }));
        window.refreshQwenVoiceDesignControls?.();
    };

    qwen3Btn.addEventListener('click', () => activate('qwen3'));
    breezeBtn.addEventListener('click', () => activate('breeze'));
    omniBtn.addEventListener('click', () => activate('omnivoice'));

    document.getElementById('voice-creation-open-engine-settings')?.addEventListener('click', () => {
        const engine = getActiveVoiceCreationDesignEngine();
        if (engine === 'breeze') window.openBreezeEngineSettings?.();
        else window.openQwenEngineSettings?.();
    });
}

// ---------------------------------------------------------------------------
// OmniVoice voice creation (voice design)

let omniVoicePreview = null;

function getOmniVoiceInstruct() {
    const selected = document.querySelectorAll('#omnivoice-vc-instruct-tags .omnivoice-tag.active');
    return Array.from(selected).map(b => b.dataset.instruct).join(', ');
}

function setupOmniVoiceCreation() {
    const generateBtn = document.getElementById('omnivoice-vc-generate-btn');
    const saveBtn = document.getElementById('omnivoice-vc-save-btn');
    const tagContainer = document.getElementById('omnivoice-vc-instruct-tags');
    const instructPreview = document.getElementById('omnivoice-vc-instruct-preview');

    if (tagContainer) {
        tagContainer.addEventListener('click', event => {
            const tag = event.target.closest('.omnivoice-tag');
            if (!tag) return;
            const isActive = tag.classList.contains('active');
            // Find the category group (all tags between two group-labels)
            const siblings = Array.from(tagContainer.querySelectorAll('.omnivoice-tag'));
            const labels = Array.from(tagContainer.querySelectorAll('.omnivoice-tag-group-label'));
            // Determine which group this tag belongs to
            let groupStart = 0;
            let groupEnd = siblings.length;
            const tagIndex = siblings.indexOf(tag);
            // Walk DOM children to find the label boundaries
            const children = Array.from(tagContainer.children);
            let currentGroup = [];
            let groups = [];
            children.forEach(child => {
                if (child.classList.contains('omnivoice-tag-group-label')) {
                    if (currentGroup.length) groups.push(currentGroup);
                    currentGroup = [];
                } else if (child.classList.contains('omnivoice-tag')) {
                    currentGroup.push(child);
                }
            });
            if (currentGroup.length) groups.push(currentGroup);
            // Deselect all tags in the same group, then toggle this one
            for (const group of groups) {
                if (group.includes(tag)) {
                    group.forEach(t => t.classList.remove('active'));
                    break;
                }
            }
            if (!isActive) tag.classList.add('active');
            const instruct = getOmniVoiceInstruct();
            if (instructPreview) {
                instructPreview.textContent = instruct
                    ? `Instruct: "${instruct}"`
                    : 'No tags selected — select at least one above.';
            }
        });
    }
    if (generateBtn) {
        generateBtn.addEventListener('click', generateOmniVoicePreview);
    }
    if (saveBtn) {
        saveBtn.addEventListener('click', saveOmniVoicePrompt);
    }
}

async function pollOmniVoiceTask(taskId, statusEl, message) {
    if (!taskId) {
        throw new Error('Missing task id for queued request.');
    }
    const start = Date.now();
    const timeoutMs = 10 * 60 * 1000;
    while (Date.now() - start < timeoutMs) {
        if (statusEl && message) {
            statusEl.textContent = message;
        }
        const response = await fetch(`/api/omnivoice/voice-design/tasks/${taskId}`);
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to fetch task status');
        }
        if (data.status === 'completed') {
            return data.result || {};
        }
        if (data.status === 'failed') {
            throw new Error(data.error || 'Queued task failed');
        }
        await new Promise(resolve => setTimeout(resolve, 1500));
    }
    throw new Error('Timed out waiting for the queued task.');
}

async function generateOmniVoicePreview() {
    const textInput = document.getElementById('omnivoice-vc-text');
    const previewAudio = document.getElementById('omnivoice-vc-preview');
    const status = document.getElementById('omnivoice-vc-status');
    const saveBtn = document.getElementById('omnivoice-vc-save-btn');
    const generateBtn = document.getElementById('omnivoice-vc-generate-btn');
    const text = textInput?.value.trim() || '';
    const instruct = getOmniVoiceInstruct();

    if (!text) {
        showToast('Enter sample text for the preview.', 'warning');
        return;
    }
    if (!instruct) {
        showToast('Select at least one voice tag (e.g. female, low pitch, british accent).', 'warning');
        return;
    }

    if (status) status.textContent = 'Generating preview...';
    if (generateBtn) generateBtn.disabled = true;
    if (saveBtn) saveBtn.disabled = true;
    omniVoicePreview = null;

    try {
        const response = await fetch('/api/omnivoice/voice-design/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text, instruct }),
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to enqueue preview');
        }
        const result = await pollOmniVoiceTask(data.job_id, status, 'Generating preview...');
        omniVoicePreview = {
            audio_base64: result.audio_base64,
            mime_type: result.mime_type || 'audio/wav',
        };
        if (previewAudio && result.audio_base64) {
            previewAudio.src = `data:${omniVoicePreview.mime_type};base64,${result.audio_base64}`;
            previewAudio.load();
        }
        if (saveBtn) saveBtn.disabled = false;
        if (status) status.textContent = 'Preview ready. Save when you like it.';
    } catch (error) {
        console.error('Failed to generate OmniVoice preview', error);
        showToast(error.message || 'Preview failed', 'error');
        if (status) status.textContent = 'Preview failed.';
    } finally {
        if (generateBtn) generateBtn.disabled = false;
    }
}

async function saveOmniVoicePrompt() {
    const nameInput = document.getElementById('omnivoice-vc-name');
    const genderSelect = document.getElementById('omnivoice-vc-gender');
    const descriptionInput = document.getElementById('omnivoice-vc-description');
    const textInput = document.getElementById('omnivoice-vc-text');
    const status = document.getElementById('omnivoice-vc-status');
    const saveBtn = document.getElementById('omnivoice-vc-save-btn');

    const name = nameInput?.value.trim() || '';
    const gender = genderSelect?.value || null;
    const description = descriptionInput?.value.trim() || '';
    const text = textInput?.value.trim() || '';
    const instruct = getOmniVoiceInstruct();

    if (!name) {
        showToast('Add a name before saving the voice prompt.', 'warning');
        return;
    }
    if (!text) {
        showToast('Sample text is required to save this voice.', 'warning');
        return;
    }
    if (!omniVoicePreview?.audio_base64) {
        showToast('Generate a preview before saving.', 'warning');
        return;
    }

    if (status) status.textContent = 'Saving voice prompt...';
    if (saveBtn) saveBtn.disabled = true;

    try {
        const response = await fetch('/api/omnivoice/voice-design/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                name,
                gender,
                description,
                text,
                instruct,
                audio_base64: omniVoicePreview.audio_base64,
            }),
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to enqueue save');
        }
        await pollOmniVoiceTask(data.job_id, status, 'Saving voice prompt...');
        showToast('OmniVoice prompt saved.', 'success');
        if (status) status.textContent = 'Saved to Voice Prompts.';
        if (nameInput) nameInput.value = '';
        if (descriptionInput) descriptionInput.value = '';
        omniVoicePreview = null;
        if (saveBtn) saveBtn.disabled = true;
        await loadChatterboxVoices();
    } catch (error) {
        console.error('Failed to save OmniVoice prompt', error);
        showToast(error.message || 'Save failed', 'error');
        if (status) status.textContent = 'Save failed.';
        if (saveBtn) saveBtn.disabled = false;
    }
}
