const chunkPendingTextEdits = new Map();
const chunkVoiceOverrides = new Map();
window.customVoiceMap = window.customVoiceMap || {};
let availableVoicesCache = window.availableVoices || null;
let customVoiceMapCache = window.customVoiceMap || {};
let availableChatterboxVoicesCache = Array.isArray(window.availableChatterboxVoices)
    ? window.availableChatterboxVoices
    : [];
const REVIEW_VOICES_EVENT_NAME = window.VOICES_UPDATED_EVENT || 'voices:updated';
window.VOICES_UPDATED_EVENT = REVIEW_VOICES_EVENT_NAME;
const REVIEW_CHATTERBOX_EVENT_NAME = window.CHATTERBOX_VOICES_EVENT || 'chatterboxVoices:updated';
window.CHATTERBOX_VOICES_EVENT = REVIEW_CHATTERBOX_EVENT_NAME;

// Shared timing helpers — used by both queue job details and library metrics modal
function fmtDuration(secs) {
    if (secs == null) return 'N/A';
    const rounded = Math.round(secs);
    if (rounded < 60) return `${rounded}s`;
    const m = Math.floor(rounded / 60);
    const s = rounded % 60;
    return s > 0 ? `${m}m ${s}s` : `${m}m`;
}

function buildChunkChart(chunkTimes, chunkCount, totalSeconds) {
    let times = Array.isArray(chunkTimes) && chunkTimes.length > 0 ? chunkTimes : null;
    let estimated = false;
    if (!times && chunkCount > 0 && totalSeconds > 0) {
        const avg = totalSeconds / chunkCount;
        times = Array.from({length: chunkCount}, () => avg);
        estimated = true;
    }
    if (!times || times.length === 0) return '';

    const MAX_POINTS = 60;
    const rawN = times.length;
    const bucketSize = rawN <= MAX_POINTS ? 1 : Math.ceil(rawN / MAX_POINTS);
    const downsampled = [];
    for (let b = 0; b < rawN; b += bucketSize) {
        const slice = times.slice(b, b + bucketSize);
        const avg = slice.reduce((s, v) => s + v, 0) / slice.length;
        downsampled.push({
            avg,
            min: Math.min(...slice),
            max: Math.max(...slice),
            startChunk: b + 1,
            endChunk: Math.min(b + bucketSize, rawN),
        });
    }
    const isDownsampled = bucketSize > 1;
    const n = downsampled.length;

    const W = 480, H = 90, padL = 38, padR = 10, padT = 8, padB = 24;
    function fmtT(t) { return t >= 60 ? `${Math.floor(t/60)}m${Math.round(t%60)>0?Math.round(t%60)+'s':''}` : `${Math.round(t)}s`; }

    const allMax = downsampled.map(d => d.max);
    const globalMax = Math.max(...allMax);
    const yMin = 0;
    const yMax = globalMax * 1.1 || 1;
    const range = yMax - yMin;

    function xPos(i) { return padL + (n === 1 ? (W - padL - padR) / 2 : i * (W - padL - padR) / (n - 1)); }
    function yPos(t) { return padT + (1 - (t - yMin) / range) * (H - padT - padB); }

    let rangeBand = '';
    if (isDownsampled) {
        const topPts = downsampled.map((d, i) => `${xPos(i).toFixed(1)},${yPos(d.max).toFixed(1)}`).join(' ');
        const botPts = downsampled.slice().reverse().map((d, i) => `${xPos(n - 1 - i).toFixed(1)},${yPos(d.min).toFixed(1)}`).join(' ');
        rangeBand = `<polygon points="${topPts} ${botPts}" fill="rgba(126,184,247,0.10)" stroke="none"/>`;
    }

    const pts = downsampled.map((d, i) => `${xPos(i).toFixed(1)},${yPos(d.avg).toFixed(1)}`).join(' ');
    const areaD = `M${xPos(0).toFixed(1)},${(H - padB).toFixed(1)} ` +
        downsampled.map((d, i) => `L${xPos(i).toFixed(1)},${yPos(d.avg).toFixed(1)}`).join(' ') +
        ` L${xPos(n-1).toFixed(1)},${(H - padB).toFixed(1)} Z`;

    const dots = !isDownsampled
        ? downsampled.map((d, i) => `<circle cx="${xPos(i).toFixed(1)}" cy="${yPos(d.avg).toFixed(1)}" r="3.5" fill="var(--accent,#7eb8f7)" stroke="rgba(15,18,32,0.8)" stroke-width="1.5"><title>Chunk ${d.startChunk}: ${fmtT(d.avg)}</title></circle>`).join('')
        : downsampled.map((d, i) => `<circle cx="${xPos(i).toFixed(1)}" cy="${yPos(d.avg).toFixed(1)}" r="2" fill="var(--accent,#7eb8f7)" opacity="0.7"><title>Chunks ${d.startChunk}–${d.endChunk}: avg ${fmtT(d.avg)}, min ${fmtT(d.min)}, max ${fmtT(d.max)}</title></circle>`).join('');

    const MAX_XLABELS = 8;
    const xLabelStep = Math.max(1, Math.ceil(n / MAX_XLABELS));
    const xLabels = downsampled.map((d, i) => {
        if (i % xLabelStep !== 0 && i !== n - 1) return '';
        return `<text x="${xPos(i).toFixed(1)}" y="${H - 4}" text-anchor="middle" font-size="9" fill="rgba(180,190,210,0.6)">${d.startChunk}</text>`;
    }).join('');

    const yLabelMax = `<text x="${padL - 4}" y="${(padT + 4).toFixed(1)}" text-anchor="end" font-size="9" fill="rgba(180,190,210,0.6)">${fmtT(yMax)}</text>`;
    const yLabelMid = `<text x="${padL - 4}" y="${((padT + H - padB) / 2 + 3).toFixed(1)}" text-anchor="end" font-size="9" fill="rgba(180,190,210,0.6)">${fmtT(yMax / 2)}</text>`;
    const yLabelMin2 = `<text x="${padL - 4}" y="${(H - padB).toFixed(1)}" text-anchor="end" font-size="9" fill="rgba(180,190,210,0.6)">0s</text>`;

    const midY = ((padT + H - padB) / 2).toFixed(1);
    const grid = `<line x1="${padL}" y1="${midY}" x2="${W - padR}" y2="${midY}" stroke="rgba(99,102,241,0.12)" stroke-dasharray="3,3"/>`;

    const downsampleNote = isDownsampled
        ? `<div class="chunk-chart-estimated">averaged over ${bucketSize}-chunk windows · shaded band = min/max range</div>`
        : (estimated ? `<div class="chunk-chart-estimated">* estimated (equal distribution)</div>` : '');

    return `<div class="chunk-chart">
        <div class="chunk-chart-title">Chunk Duration Over Time</div>
        <svg viewBox="0 0 ${W} ${H}" width="100%" style="display:block;overflow:visible">
            <defs>
                <linearGradient id="cg" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0%" stop-color="var(--accent,#7eb8f7)" stop-opacity="0.25"/>
                    <stop offset="100%" stop-color="var(--accent,#7eb8f7)" stop-opacity="0.02"/>
                </linearGradient>
            </defs>
            ${grid}
            ${rangeBand}
            <path d="${areaD}" fill="url(#cg)"/>
            <polyline points="${pts}" fill="none" stroke="var(--accent,#7eb8f7)" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
            ${dots}
            ${xLabels}
            ${yLabelMax}
            ${yLabelMid}
            ${yLabelMin2}
        </svg>
        ${downsampleNote}
    </div>`;
}

// Job Queue Management

const QUEUE_REFRESH_INTERVAL_MS = 3000;
let queueRefreshTimer = null;
let queueTabButton = null;
const openReviewPanels = new Set();
const reviewPanelContentCache = new Map();
const chunkPanelLoadingJobs = new Set();
const completedJobIds = new Set();
const reviewPanelScrollPositions = new Map();
let activeVoiceSelects = 0;
const reviewPanelEditorState = new Map();
const activeEditingChunks = new Map();
const jobChunkMaps = new Map();
let activeChunkAudio = null;
let activeChunkId = null;
let activeChunkButton = null;
const chunkRegenWatchers = new Map();

const CHUNK_REFRESH_POLL_INTERVAL_MS = 2000;
const CHUNK_REFRESH_MAX_ATTEMPTS = 30;

function cacheBustUrl(url, token = '') {
    if (!url) {
        return '';
    }
    const trimmedToken = (token || '').toString().trim();
    const cacheToken = trimmedToken || Date.now().toString();
    const separator = url.includes('?') ? '&' : '?';
    return `${url}${separator}cb=${encodeURIComponent(cacheToken)}`;
}

document.addEventListener('DOMContentLoaded', () => {
    queueTabButton = document.querySelector('.tab-button[data-tab="queue"]');
    initQueue();

    ensureJobDetailModalHandlers();

    if (queueTabButton) {
        queueTabButton.addEventListener('click', () => {
            loadQueue();
            startQueueAutoRefresh();
        });
    }

function getChunkTextForJob(jobId, chunkId) {
    const textarea = document.querySelector(`textarea[data-chunk-text="${chunkId}"]`);
    if (textarea) {
        return textarea.value.trim();
    }
    const chunk = getChunkMetadata(jobId, chunkId);
    return (chunk?.text || '').trim();
}

async function regenerateEntireJob(jobId, button) {
    if (!jobId) return;
    const entry = jobChunkMaps.get(jobId);
    if (!entry) {
        alert('Chunk metadata unavailable. Refresh the panel and try again.');
        return;
    }
    if (!confirm('Re-render all chunks with current text and voice selections?')) {
        return;
    }
    button.disabled = true;
    const originalLabel = button.textContent;
    button.textContent = 'Queuing regen…';
    try {
        const chunkEntries = [];
        entry.chunks.forEach((chunk, chunkId) => {
            const textValue = getChunkTextForJob(jobId, chunkId);
            if (!textValue) {
                throw new Error(`Chunk ${chunkId} text is empty. Update it before regenerating.`);
            }
            const voicePayload = getVoicePayloadForChunk(jobId, chunkId);
            const entryPayload = {
                chunk_id: chunkId,
                text: textValue,
            };
            if (voicePayload && Object.keys(voicePayload).length > 0) {
                entryPayload.voice = voicePayload;
            }
            chunkEntries.push(entryPayload);
        });
        const response = await fetch(`/api/jobs/${jobId}/review/regen-all`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chunks: chunkEntries }),
        });
        const payload = await response.json();
        if (!payload.success) {
            throw new Error(payload.error || 'Failed to queue job regeneration');
        }
        showReviewToast(`Queued regeneration for ${payload.queued_chunks || chunkEntries.length} chunks.`);
        renderReviewPanel(jobId, { silent: true });
    } catch (error) {
        alert(error.message || 'Failed to queue job regeneration.');
    } finally {
        button.disabled = false;
        button.textContent = originalLabel || 'Regenerate entire job';
    }
}

    document.querySelectorAll('.tab-button').forEach(btn => {
        if (btn.dataset.tab !== 'queue') {
            btn.addEventListener('click', stopQueueAutoRefresh);
        }
    });

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            stopQueueAutoRefresh();
        } else if (isQueueTabActive()) {
            startQueueAutoRefresh();
            loadQueue();
        }
    });

    if (isQueueTabActive()) {
        startQueueAutoRefresh();
    }
});

function cachePendingTextEdits(jobId, remove = false) {
    if (!jobId) {
        return;
    }
    const panel = document.getElementById(`review-panel-${jobId}`);
    if (!panel) {
        return;
    }
    panel.querySelectorAll('textarea[data-chunk-text]').forEach(textarea => {
        const chunkId = textarea.dataset.chunkText;
        if (!chunkId) return;
        if (remove) {
            chunkPendingTextEdits.delete(chunkId);
        } else {
            chunkPendingTextEdits.set(chunkId, textarea.value);
        }
    });
}

document.addEventListener('click', handleQueueActionClick);
document.addEventListener('change', handleChunkVoiceSelectChange);
document.addEventListener('focusin', handleVoiceSelectFocus, true);
document.addEventListener('focusout', handleVoiceSelectBlur, true);
window.addEventListener(REVIEW_VOICES_EVENT_NAME, handleGlobalVoicesUpdated, { passive: true });
window.addEventListener(REVIEW_CHATTERBOX_EVENT_NAME, handleGlobalVoicesUpdated, { passive: true });

function handleGlobalVoicesUpdated(event) {
    if (!event) {
        return;
    }
    if (event.type === REVIEW_VOICES_EVENT_NAME) {
        const detail = event.detail || {};
        if (detail.voices) {
            availableVoicesCache = detail.voices;
        }
        if (detail.customVoiceMap) {
            customVoiceMapCache = detail.customVoiceMap;
        }
    } else if (event.type === REVIEW_CHATTERBOX_EVENT_NAME) {
        const voices = event.detail?.voices;
        availableChatterboxVoicesCache = Array.isArray(voices) ? voices : [];
    }
    openReviewPanels.forEach(jobId => {
        renderReviewPanel(jobId, { silent: true });
    });
}

const TURBO_ENGINES = new Set([
    'chatterbox_turbo_local',
    'chatterbox_turbo_replicate',
    'voxcpm_local',
    'qwen3_clone',
    'omnivoice_clone',
    'dots_tts',
    'audio8_tts',
    'breeze_tts_2',
    'breeze_api'
]);
const CHATTERBOX_ENGINES = new Set(['chatterbox', ...TURBO_ENGINES]);

function normalizeEngineName(engine) {
    return (engine || '').toLowerCase();
}

function isQueueReferenceEngine(engine) {
    return TURBO_ENGINES.has(normalizeEngineName(engine));
}

function isChatterboxEngine(engine) {
    return CHATTERBOX_ENGINES.has(normalizeEngineName(engine));
}

function chunkVoiceOverrideKey(jobId, chunkId) {
    return `${jobId || ''}::${chunkId || ''}`;
}

function getChunkVoiceOverride(jobId, chunkId) {
    return chunkVoiceOverrides.get(chunkVoiceOverrideKey(jobId, chunkId)) || null;
}

function setChunkVoiceOverride(jobId, chunkId, payload) {
    if (!jobId || !chunkId) {
        return;
    }
    const key = chunkVoiceOverrideKey(jobId, chunkId);
    if (payload && Object.keys(payload).length > 0) {
        chunkVoiceOverrides.set(key, payload);
    } else {
        chunkVoiceOverrides.delete(key);
    }
}

function clearVoiceOverridesForJob(jobId) {
    const prefix = `${jobId || ''}::`;
    Array.from(chunkVoiceOverrides.keys()).forEach(key => {
        if (key.startsWith(prefix)) {
            chunkVoiceOverrides.delete(key);
        }
    });
}

function pruneVoiceOverrides(activeJobIds = []) {
    const jobSet = new Set(
        Array.isArray(activeJobIds)
            ? activeJobIds.filter(Boolean)
            : Array.from(activeJobIds || []).filter(Boolean),
    );
    if (jobSet.size === 0) {
        chunkVoiceOverrides.clear();
        return;
    }
    Array.from(chunkVoiceOverrides.keys()).forEach(key => {
        const jobId = key.split('::', 1)[0];
        if (!jobSet.has(jobId)) {
            chunkVoiceOverrides.delete(key);
        }
    });
}

function chunkRegenWatcherKey(jobId, chunkId) {
    return `${jobId || ''}::${chunkId || ''}`;
}

function clearChunkRegenWatcher(jobId, chunkId) {
    const key = chunkRegenWatcherKey(jobId, chunkId);
    const entry = chunkRegenWatchers.get(key);
    if (entry?.timer) {
        clearTimeout(entry.timer);
    }
    chunkRegenWatchers.delete(key);
}

function clearChunkRegenWatchersForJob(jobId) {
    const prefix = `${jobId || ''}::`;
    Array.from(chunkRegenWatchers.keys()).forEach(key => {
        if (!jobId || key.startsWith(prefix)) {
            const entry = chunkRegenWatchers.get(key);
            if (entry?.timer) {
                clearTimeout(entry.timer);
            }
            chunkRegenWatchers.delete(key);
        }
    });
}

function syncChunkRegenWatchersFromPayload(jobId, payload = {}) {
    const regenTasks = payload.regen_tasks || {};
    const activeChunkIds = new Set();
    Object.entries(regenTasks).forEach(([chunkId, task]) => {
        const status = (task || {}).status;
        if (status === 'queued' || status === 'running') {
            activeChunkIds.add(chunkId);
            startChunkRegenWatcher(jobId, chunkId);
        } else {
            clearChunkRegenWatcher(jobId, chunkId);
        }
    });
    const prefix = `${jobId || ''}::`;
    Array.from(chunkRegenWatchers.keys()).forEach(key => {
        if (!key.startsWith(prefix)) {
            return;
        }
        const chunkId = key.slice(prefix.length);
        if (chunkId && !activeChunkIds.has(chunkId)) {
            clearChunkRegenWatcher(jobId, chunkId);
        }
    });
}

async function fetchJobChunkPayload(jobId) {
    const response = await fetch(`/api/jobs/${jobId}/chunks`);
    const payload = await response.json();
    if (!payload.success) {
        throw new Error(payload.error || 'Failed to load chunk metadata');
    }
    return payload;
}

function applyChunkPayloadToPanel(jobId, payload, chunkId = null) {
    if (!payload) {
        return;
    }
    cachePanelEditorState(jobId);
    cacheJobChunkMap(jobId, payload);
    reviewPanelContentCache.set(jobId, payload);
    replaceReviewPanelHeader(jobId, payload);
    if (chunkId) {
        const chunk = (payload.chunks || []).find(item => item?.id === chunkId);
        if (chunk) {
            const regenState = (payload.regen_tasks || {})[chunkId];
            const engine = (payload.review?.engine || '').toLowerCase();
            replaceChunkRow(jobId, chunk, regenState, engine);
        }
    }
    restorePanelEditorState(jobId);
    syncChunkRegenWatchersFromPayload(jobId, payload);
    syncActiveChunkControls();
}

function replaceReviewPanelHeader(jobId, payload) {
    const panel = document.getElementById(`review-panel-${jobId}`);
    if (!panel) {
        return;
    }
    const headerEl = panel.querySelector('.review-panel-header');
    if (!headerEl) {
        return;
    }
    const template = document.createElement('div');
    template.innerHTML = renderReviewPanelHeader(jobId, payload).trim();
    const newHeader = template.firstElementChild;
    if (newHeader) {
        headerEl.replaceWith(newHeader);
    }
}

function replaceChunkRow(jobId, chunk, regenState, engine) {
    if (!chunk?.id) {
        return;
    }
    const panel = document.getElementById(`review-panel-${jobId}`);
    if (!panel) {
        return;
    }
    const row = panel.querySelector(`.chunk-row[data-chunk-id="${chunk.id}"]`);
    if (!row) {
        return;
    }
    const wrapper = document.createElement('div');
    wrapper.innerHTML = renderChunkRow(jobId, chunk, regenState, engine).trim();
    const nextRow = wrapper.firstElementChild;
    if (nextRow) {
        row.replaceWith(nextRow);
    }
}

function startChunkRegenWatcher(jobId, chunkId) {
    if (!jobId || !chunkId) {
        return;
    }
    if (!openReviewPanels.has(jobId)) {
        return;
    }
    const watcherKey = chunkRegenWatcherKey(jobId, chunkId);
    // Don't start a new watcher if one already exists
    if (chunkRegenWatchers.has(watcherKey)) {
        return;
    }
    const entry = { attempts: 0, timer: null };
    chunkRegenWatchers.set(watcherKey, entry);
    pollChunkRegenStatus(jobId, chunkId, entry);
}

async function pollChunkRegenStatus(jobId, chunkId, entry) {
    const watcherKey = chunkRegenWatcherKey(jobId, chunkId);
    if (!chunkRegenWatchers.has(watcherKey)) {
        return;
    }
    if (!openReviewPanels.has(jobId)) {
        clearChunkRegenWatcher(jobId, chunkId);
        return;
    }
    entry.attempts += 1;
    try {
        const payload = await fetchJobChunkPayload(jobId);
        applyChunkPayloadToPanel(jobId, payload, chunkId);
        const status = payload?.regen_tasks?.[chunkId]?.status;
        const isComplete = !status || status === 'completed' || status === 'failed';
        if (isComplete || entry.attempts >= CHUNK_REFRESH_MAX_ATTEMPTS) {
            clearChunkRegenWatcher(jobId, chunkId);
            return;
        }
    } catch (error) {
        console.error(`Failed to refresh chunk ${chunkId} regen status`, error);
        if (entry.attempts >= CHUNK_REFRESH_MAX_ATTEMPTS) {
            clearChunkRegenWatcher(jobId, chunkId);
            return;
        }
    }
    entry.timer = setTimeout(() => pollChunkRegenStatus(jobId, chunkId, entry), CHUNK_REFRESH_POLL_INTERVAL_MS);
}

function cloneVoiceAssignment(assignment) {
    if (!assignment || typeof assignment !== 'object') {
        return {};
    }
    try {
        return JSON.parse(JSON.stringify(assignment));
    } catch (error) {
        console.warn('Failed to clone voice assignment', error);
        return { ...assignment };
    }
}

function cacheJobChunkMap(jobId, payload) {
    const chunkMap = new Map();
    (payload.chunks || []).forEach(chunk => {
        if (chunk?.id) {
            chunkMap.set(chunk.id, chunk);
        }
    });
    jobChunkMaps.set(jobId, {
        engine: normalizeEngineName(payload.review?.engine),
        chunks: chunkMap,
    });
}

function getChunkMetadata(jobId, chunkId) {
    const entry = jobChunkMaps.get(jobId);
    if (!entry) return null;
    return entry.chunks.get(chunkId) || null;
}

function resolveLangCodeForVoice(voiceName) {
    if (!voiceName) {
        return 'a';
    }
    const customEntry = customVoiceMapCache?.[voiceName];
    if (customEntry?.lang_code) {
        return customEntry.lang_code;
    }
    const voices = availableVoicesCache;
    if (!voices || typeof voices !== 'object') {
        return 'a';
    }
    for (const config of Object.values(voices)) {
        if (!config) continue;
        if (Array.isArray(config.voices) && config.voices.includes(voiceName)) {
            return config.lang_code || 'a';
        }
        const customVoices = config.custom_voices || [];
        const match = customVoices.find(entry => entry?.code === voiceName);
        if (match?.lang_code) {
            return match.lang_code;
        }
    }
    return 'a';
}

function resolveChatterboxVoiceName(promptPath) {
    if (!promptPath) return '';
    const normalized = promptPath.trim();
    if (!normalized) return '';
    const entry = availableChatterboxVoicesCache.find(item => {
        const path = (item?.prompt_path || item?.file_name || '').trim();
        return path === normalized;
    });
    if (!entry) {
        const basename = normalized.split(/[\\/]/).pop();
        return basename || normalized;
    }
    return entry.name || entry.prompt_path || entry.file_name || normalized;
}

function escapeHtml(value = '') {
    const div = document.createElement('div');
    div.textContent = value;
    return div.innerHTML;
}

function getKokoroVoiceSelection(jobId, chunk) {
    const override = getChunkVoiceOverride(jobId, chunk.id);
    if (override?.voice) {
        return override.voice;
    }
    const assignment = chunk.voice_assignment || {};
    if (assignment.voice) {
        return assignment.voice;
    }
    return '';
}

function getChatterboxPromptSelection(jobId, chunk) {
    const override = getChunkVoiceOverride(jobId, chunk.id);
    if (override?.audio_prompt_path) {
        return override.audio_prompt_path;
    }
    const assignment = chunk.voice_assignment || {};
    if (assignment.audio_prompt_path) {
        return assignment.audio_prompt_path;
    }
    return '';
}

function buildKokoroVoiceOptions(selectedVoice) {
    if (!availableVoicesCache) {
        return '<option value="">Voices loading…</option>';
    }
    let html = '';
    Object.entries(availableVoicesCache).forEach(([key, config]) => {
        if (!config) {
            return;
        }
        const label = config.language || key || 'Voices';
        html += `<optgroup label="${escapeHtml(label)}">`;
        (config.voices || []).forEach(voiceName => {
            if (!voiceName) return;
            const selected = voiceName === selectedVoice ? 'selected' : '';
            html += `<option value="${escapeHtml(voiceName)}" ${selected}>${escapeHtml(voiceName)}</option>`;
        });
        const customVoices = config.custom_voices || [];
        customVoices.forEach(entry => {
            if (!entry?.code) return;
            const selected = entry.code === selectedVoice ? 'selected' : '';
            const title = entry.name || entry.code;
            html += `<option value="${escapeHtml(entry.code)}" ${selected}>${escapeHtml(title)}</option>`;
        });
        html += '</optgroup>';
    });
    return html;
}

function buildChatterboxVoiceOptions(selectedPrompt) {
    const productionOption = selectedPrompt && /breeze_productions[\\/]/.test(selectedPrompt)
        ? `<option value="${escapeHtml(selectedPrompt)}" selected>Production sample (current)</option>` : '';
    if (!availableChatterboxVoicesCache.length) {
        return productionOption || '<option value="">No saved Chatterbox voices</option>';
    }
    // Sort voices alphabetically by name
    const sortedVoices = [...availableChatterboxVoicesCache].sort((a, b) =>
        (a.name || '').toLowerCase().localeCompare((b.name || '').toLowerCase())
    );
    return productionOption + sortedVoices
        .map(entry => {
            const promptPath = (entry?.prompt_path || entry?.file_name || '').trim();
            if (!promptPath) {
                return '';
            }
            const selected = promptPath === selectedPrompt ? 'selected' : '';
            const durationLabel = entry?.duration_seconds ? ` · ${entry.duration_seconds.toFixed(2)}s` : '';
            const label = `${entry?.name || promptPath}${durationLabel}`;
            return `<option value="${escapeHtml(promptPath)}" ${selected}>${escapeHtml(label)}</option>`;
        })
        .join('');
}

function getChunkVoiceLabel(jobId, chunk, engine) {
    const normalizedEngine = normalizeEngineName(engine);
    if (isChatterboxEngine(normalizedEngine)) {
        const promptPath = getChatterboxPromptSelection(jobId, chunk);
        if (promptPath) {
            return resolveChatterboxVoiceName(promptPath);
        }
        const overrideVoice = getChunkVoiceOverride(jobId, chunk.id)?.voice;
        if (overrideVoice) {
            return overrideVoice;
        }
        const assignmentVoice = chunk.voice_assignment?.voice;
        if (assignmentVoice) {
            return assignmentVoice;
        }
    } else {
        const voiceName = getKokoroVoiceSelection(jobId, chunk);
        if (voiceName) {
            return voiceName;
        }
    }
    return chunk.voice || 'Job default';
}

function renderChunkVoiceLabel(jobId, chunk, engine) {
    const label = getChunkVoiceLabel(jobId, chunk, engine);
    if (!label) {
        return '';
    }
    return `<span class="chunk-tag info" data-chunk-voice-label="${chunk.id}">${escapeHtml(label)}</span>`;
}

function renderKokoroVoiceControl(jobId, chunk, engine) {
    const selected = getKokoroVoiceSelection(jobId, chunk);
    const placeholder = chunk.voice ? `Use ${chunk.voice}` : 'Use job default';
    const disabled = !availableVoicesCache;
    const optionMarkup = availableVoicesCache ? buildKokoroVoiceOptions(selected) : '<option value="">Voices loading…</option>';
    return `
        <div class="chunk-row-voice">
            <label for="chunk-voice-${chunk.id}">Voice override</label>
            <select id="chunk-voice-${chunk.id}"
                    class="chunk-voice-select"
                    data-chunk-voice-select="true"
                    data-job-id="${jobId}"
                    data-chunk-id="${chunk.id}"
                    data-engine="${engine}"
                    ${disabled ? 'disabled' : ''}>
                <option value="">${escapeHtml(placeholder)}</option>
                ${optionMarkup}
            </select>
        </div>
    `;
}

function renderChatterboxVoiceControl(jobId, chunk, engine) {
    const selectedPrompt = getChatterboxPromptSelection(jobId, chunk);
    const placeholder = selectedPrompt
        ? `Use ${resolveChatterboxVoiceName(selectedPrompt)}`
        : 'Use job default prompt';
    const hasVoices = availableChatterboxVoicesCache.length > 0;
    const optionMarkup = hasVoices
        ? buildChatterboxVoiceOptions(selectedPrompt)
        : '<option value="">No saved voices available</option>';
    const labelText = isQueueReferenceEngine(engine) ? 'Voice sample' : 'Chatterbox voice prompt';
    return `
        <div class="chunk-row-voice">
            <label for="chunk-voice-${chunk.id}">${labelText}</label>
            <select id="chunk-voice-${chunk.id}"
                    class="chunk-voice-select"
                    data-chunk-voice-select="true"
                    data-job-id="${jobId}"
                    data-chunk-id="${chunk.id}"
                    data-engine="${engine}"
                    ${hasVoices ? '' : 'disabled'}>
                <option value="">${escapeHtml(placeholder)}</option>
                ${optionMarkup}
            </select>
        </div>
    `;
}

function renderChunkVoiceControl(jobId, chunk, engine) {
    const normalizedEngine = normalizeEngineName(engine);
    if (!chunk?.id || !normalizedEngine) {
        return '';
    }
    if (isChatterboxEngine(normalizedEngine)) {
        return renderChatterboxVoiceControl(jobId, chunk, normalizedEngine);
    }
    return renderKokoroVoiceControl(jobId, chunk, normalizedEngine);
}

function updateChunkVoiceLabelDisplay(chunkId, label) {
    const el = document.querySelector(`[data-chunk-voice-label="${chunkId}"]`);
    if (el) {
        el.textContent = label || 'Job default';
    }
}

function handleChunkVoiceSelectChange(event) {
    const select = event.target.closest('[data-chunk-voice-select="true"]');
    if (!select) {
        return;
    }
    const jobId = select.dataset.jobId;
    const chunkId = select.dataset.chunkId;
    const engine = normalizeEngineName(select.dataset.engine);
    if (!jobId || !chunkId) {
        return;
    }

    const payload = buildPayloadFromVoiceSelect(select);
    setChunkVoiceOverride(jobId, chunkId, payload);
    const label = payload
        ? isChatterboxEngine(engine)
            ? resolveChatterboxVoiceName(payload.audio_prompt_path)
            : payload.voice
        : getChunkVoiceLabel(jobId, getChunkMetadata(jobId, chunkId) || {}, engine);
    updateChunkVoiceLabelDisplay(chunkId, label);
    stopQueueAutoRefresh();
}

function buildPayloadFromVoiceSelect(select) {
    if (!select) {
        return null;
    }
    const engine = normalizeEngineName(select.dataset.engine);
    const rawValue = (select.value || '').trim();
    if (!rawValue) {
        return null;
    }
    if (isChatterboxEngine(engine)) {
        return { audio_prompt_path: rawValue };
    }
    return {
        voice: rawValue,
        lang_code: resolveLangCodeForVoice(rawValue),
    };
}

function handleVoiceSelectFocus(event) {
    const select = event.target?.closest?.('[data-chunk-voice-select="true"]');
    if (!select) {
        return;
    }
    activeVoiceSelects += 1;
    stopQueueAutoRefresh();
}

function handleVoiceSelectBlur(event) {
    const select = event.target?.closest?.('[data-chunk-voice-select="true"]');
    if (!select) {
        return;
    }
    activeVoiceSelects = Math.max(0, activeVoiceSelects - 1);
    resumeQueueAutoRefreshIfIdle();
}

function resumeQueueAutoRefreshIfIdle() {
    if (activeEditingChunks.size === 0 && activeVoiceSelects === 0 && isQueueTabActive()) {
        startQueueAutoRefresh();
    }
}

function initQueue() {
    const refreshBtn = document.getElementById('refresh-queue-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadQueue);
    }

    const clearQueueBtn = document.getElementById('clear-queue-btn');
    if (clearQueueBtn) {
        clearQueueBtn.addEventListener('click', async () => {
            if (!confirm('Clear all jobs from the queue? Jobs that are currently processing will be skipped. This cannot be undone.')) {
                return;
            }
            clearQueueBtn.disabled = true;
            clearQueueBtn.textContent = 'Clearing…';
            try {
                const response = await fetch('/api/jobs/clear-all', { method: 'DELETE' });
                const data = await response.json();
                if (data.success) {
                    const parts = [`Removed ${data.removed} job${data.removed !== 1 ? 's' : ''}`];
                    if (data.skipped > 0) parts.push(`${data.skipped} skipped (processing)`);
                    if (data.errors > 0) parts.push(`${data.errors} failed`);
                    alert(parts.join(', ') + '.');
                } else {
                    alert('Failed to clear queue: ' + (data.error || 'Unknown error'));
                }
            } catch (err) {
                alert('Failed to clear queue: ' + (err.message || 'Network error'));
            } finally {
                clearQueueBtn.disabled = false;
                clearQueueBtn.textContent = 'Clear Queue';
                loadQueue();
            }
        });
    }

    loadQueue();
}

function isQueueTabActive() {
    const queueTab = document.getElementById('queue-tab');
    return queueTab && queueTab.classList.contains('active');
}

function startQueueAutoRefresh() {
    if (activeEditingChunks.size > 0 || activeVoiceSelects > 0) {
        return;
    }
    if (queueRefreshTimer) {
        return;
    }
    queueRefreshTimer = setInterval(loadQueue, QUEUE_REFRESH_INTERVAL_MS);
}

function stopQueueAutoRefresh() {
    if (queueRefreshTimer) {
        clearInterval(queueRefreshTimer);
        queueRefreshTimer = null;
    }
}

async function loadQueue() {
    try {
        const response = await fetch('/api/queue');
        const data = await response.json();

        if (data.success) {
            displayQueue(data);
        } else {
            console.error('Error loading queue:', data.error);
        }
    } catch (error) {
        console.error('Error loading queue:', error);
    }
}

function displayQueue(data) {
    const container = document.getElementById('queue-list');
    if (!container) return;

    if (!data.jobs || data.jobs.length === 0) {
        container.innerHTML = '<p><em>No jobs in queue</em></p>';
        return;
    }

    let hasNewCompletion = false;
    data.jobs.forEach(job => {
        if (job.status === 'completed' && !completedJobIds.has(job.job_id)) {
            completedJobIds.add(job.job_id);
            hasNewCompletion = true;
        }
    });
    if (hasNewCompletion) {
        document.dispatchEvent(new CustomEvent('library:refresh'));
    }

    let html = `
        <div style="margin-bottom: 15px;">
            <strong>Queue Size:</strong> ${data.queue_size} pending |
            <strong>Current Jobs:</strong> ${Array.isArray(data.current_jobs) && data.current_jobs.length
                ? data.current_jobs.join(', ')
                : (data.current_job || 'None')}
        </div>
        <table class="queue-table">
            <thead>
                <tr>
                    <th>Status</th>
                    <th>Job ID</th>
                    <th>Progress</th>
                    <th>Text Preview</th>
                    <th>Created</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
    `;

    data.jobs.forEach(job => {
        const statusClass = getStatusClass(job.status);
        const statusIcon = getStatusIcon(job.status);
        const createdTime = job.created_at ? new Date(job.created_at).toLocaleString() : '';
        const currentJobs = Array.isArray(data.current_jobs) ? data.current_jobs : [data.current_job];
        const isCurrentJob = currentJobs.includes(job.job_id);
        const canPause = job.status === 'queued' || job.status === 'processing';
        const canResume = job.status === 'paused'
            || job.status === 'interrupted'
            || (job.status === 'failed' && (Number(job.processed_chunks || 0) > 0 || job.engine === 'breeze_api'));
        const canDelete = job.status !== 'processing' && job.status !== 'pausing';

        html += `
            <tr class="${isCurrentJob ? 'current-job' : ''}">
                <td><span class="status-badge ${statusClass}">${statusIcon} ${job.status}</span></td>
                <td><code>${job.job_id.substring(0, 8)}</code></td>
                <td>${renderJobProgress(job)}</td>
                <td class="text-preview">${job.text_preview || 'N/A'}</td>
                <td>${createdTime}</td>
                <td>
                    <button class="btn-small btn-secondary" onclick="openJobDetailsModal('${job.job_id}')">Details</button>
                    ${canPause ?
                        `<button class="btn-small btn-warning" onclick="pauseQueueJob('${job.job_id}')">Pause</button>` :
                        ''}
                    ${canResume ?
                        `<button class="btn-small btn-primary" onclick="resumeQueueJob('${job.job_id}')">Resume</button>` :
                        ''}
                    ${job.status === 'completed' ?
                        `<button class="btn-small btn-primary" onclick="downloadJobAudio('${job.job_id}')">Download</button>` :
                        ''}
                    ${(job.status === 'queued' || job.status === 'processing') ?
                        `<button class="btn-small btn-danger" onclick="cancelQueueJob('${job.job_id}')">Cancel</button>` :
                        ''}
                    ${canDelete ?
                        `<button class="btn-small btn-outline" onclick="deleteQueueJob('${job.job_id}')">Remove</button>` :
                        ''}
                    ${job.status === 'failed' ?
                        `<span class="error-text" title="${job.error || 'Unknown error'}">Failed</span>` :
                        ''}
                </td>
            </tr>
        `;
    });

    html += `
            </tbody>
        </table>
    `;

    container.innerHTML = html;
}

function getStatusClass(status) {
    switch (status) {
        case 'queued':
            return 'status-queued';
        case 'processing':
            return 'status-processing';
        case 'pausing':
            return 'status-pausing';
        case 'paused':
            return 'status-paused';
        case 'completed':
            return 'status-completed';
        case 'interrupted':
            return 'status-interrupted';
        case 'failed':
            return 'status-failed';
        case 'cancelled':
            return 'status-cancelled';
        default:
            return '';
    }
}

function getStatusIcon(status) {
    switch (status) {
        case 'queued':
            return '';
        case 'processing':
            return '';
        case 'pausing':
            return '';
        case 'paused':
            return '';
        case 'completed':
            return '';
        case 'interrupted':
            return '';
        case 'failed':
            return '';
        case 'cancelled':
            return '';
        default:
            return '';
    }
}

function ensureJobDetailModalHandlers() {
    const overlay = document.getElementById('job-detail-modal-overlay');
    const closeBtn = document.getElementById('job-detail-modal-close');
    const footerBtn = document.getElementById('job-detail-modal-close-btn');
    if (overlay && !overlay.dataset.bound) {
        overlay.addEventListener('click', (event) => {
            if (event.target === overlay) {
                closeJobDetailModal();
            }
        });
        overlay.dataset.bound = 'true';
    }
    if (closeBtn && !closeBtn.dataset.bound) {
        closeBtn.addEventListener('click', closeJobDetailModal);
        closeBtn.dataset.bound = 'true';
    }
    if (footerBtn && !footerBtn.dataset.bound) {
        footerBtn.addEventListener('click', closeJobDetailModal);
        footerBtn.dataset.bound = 'true';
    }
}

function closeJobDetailModal() {
    const overlay = document.getElementById('job-detail-modal-overlay');
    const modal = document.getElementById('job-detail-modal');
    if (overlay) overlay.classList.add('hidden');
    if (modal) modal.classList.add('hidden');
}

async function openJobDetailsModal(jobId) {
    if (!jobId) return;
    const overlay = document.getElementById('job-detail-modal-overlay');
    const modal = document.getElementById('job-detail-modal');
    const body = document.getElementById('job-detail-modal-body');
    if (overlay) overlay.classList.remove('hidden');
    if (modal) modal.classList.remove('hidden');
    if (body) body.innerHTML = '<div class="chunk-review-loading">Loading job details...</div>';
    try {
        const response = await fetch(`/api/jobs/${jobId}/details`);
        const payload = await response.json();
        if (!payload.success) {
            throw new Error(payload.error || 'Failed to load job details');
        }
        const job = payload.job || {};
        const speakers = Array.isArray(job.speakers) ? job.speakers : [];
        const speakerList = speakers.length ? speakers.map(s => `<span class="speaker-tag">${s}</span>`).join('') : '<span class="speaker-tag">default</span>';
        const text = (job.text || '').trim();
        const resumeFrom = (job.status !== 'completed' && Number.isFinite(Number(job.resume_from_chunk_index)) && Number(job.resume_from_chunk_index) > 0)
            ? Number(job.resume_from_chunk_index) + 1
            : null;
        const resumeLine = resumeFrom ? `<div><strong>Resume from:</strong> chunk ${resumeFrom}</div>` : '';

        // Timing metrics
        const tm = job.timing_metrics || {};
        function fmtTime(iso) {
            if (!iso) return 'N/A';
            return new Date(iso).toLocaleString();
        }
        const isLive = ['processing', 'pausing'].includes(job.status);
        const startedAt = fmtTime(job.started_at || tm.started_at);
        const completedAt = (job.completed_at || tm.completed_at)
            ? fmtTime(job.completed_at || tm.completed_at)
            : (isLive ? '<span style="color:var(--accent,#7eb8f7);font-style:italic">In progress…</span>' : 'N/A');
        const totalTimeLabel = 'Active Time (all runs)';
        const totalTime = fmtDuration(tm.total_seconds);
        const avgChunk = tm.avg_chunk_seconds != null ? fmtDuration(tm.avg_chunk_seconds) : 'N/A';
        const minChunk = tm.min_chunk_seconds != null ? fmtDuration(tm.min_chunk_seconds) : 'N/A';
        const maxChunk = tm.max_chunk_seconds != null ? fmtDuration(tm.max_chunk_seconds) : 'N/A';
        const chunkCount = job.total_chunks != null ? job.total_chunks : (tm.chunk_count != null ? tm.chunk_count : 'N/A');
        const processedChunks = job.processed_chunks != null ? job.processed_chunks : 'N/A';
        const liveBadge = isLive ? '<span style="margin-left:8px;font-size:0.7rem;padding:2px 7px;border-radius:10px;background:rgba(126,184,247,0.15);color:var(--accent,#7eb8f7);vertical-align:middle">live</span>' : '';

        const hasTimingData = tm.total_seconds != null;

        const chunkChart = hasTimingData
            ? buildChunkChart(tm.chunk_times, tm.chunk_count || chunkCount, tm.total_seconds)
            : '';

        const timingSection = hasTimingData ? `
            <div class="job-detail-timing">
                <h4 style="margin:0 0 10px 0; font-size:0.95rem; color:var(--accent, #7eb8f7);">Timing${liveBadge}</h4>
                <div class="job-detail-timing-grid">
                    <div class="timing-row"><span class="timing-label">Started</span><span class="timing-value">${startedAt}</span></div>
                    <div class="timing-row"><span class="timing-label">Completed</span><span class="timing-value">${completedAt}</span></div>
                    <div class="timing-row timing-highlight"><span class="timing-label">${totalTimeLabel}</span><span class="timing-value">${totalTime}</span></div>
                    <div class="timing-row"><span class="timing-label">Chunks</span><span class="timing-value">${processedChunks} / ${chunkCount}</span></div>
                    <div class="timing-row timing-highlight"><span class="timing-label">Avg Chunk Time</span><span class="timing-value">${avgChunk}</span></div>
                    <div class="timing-row"><span class="timing-label">Fastest Chunk</span><span class="timing-value">${minChunk}</span></div>
                    <div class="timing-row"><span class="timing-label">Slowest Chunk</span><span class="timing-value">${maxChunk}</span></div>
                </div>
                ${chunkChart}
            </div>` : (job.started_at ? `
            <div class="job-detail-timing">
                <h4 style="margin:0 0 10px 0; font-size:0.95rem; color:var(--accent, #7eb8f7);">Timing</h4>
                <div class="job-detail-timing-grid">
                    <div class="timing-row"><span class="timing-label">Started</span><span class="timing-value">${startedAt}</span></div>
                    <div class="timing-row"><span class="timing-label">Chunks</span><span class="timing-value">${processedChunks} / ${chunkCount}</span></div>
                </div>
            </div>` : '');

        if (body) {
            body.innerHTML = `
                <div class="job-detail-grid">
                    <div>
                        <strong>Engine:</strong> ${job.engine || 'Unknown'}
                    </div>
                    <div>
                        <strong>Status:</strong> ${job.status || 'Unknown'}
                    </div>
                    <div>
                        <strong>Created:</strong> ${job.created_at ? new Date(job.created_at).toLocaleString() : 'N/A'}
                    </div>
                    ${resumeLine}
                    <div class="job-detail-speakers">
                        <strong>Speakers:</strong>
                        <div class="speaker-tags-wrap">${speakerList}</div>
                    </div>
                </div>
                ${timingSection}
                <div class="job-detail-text">
                    <label>Job Text</label>
                    <textarea readonly rows="10">${text}</textarea>
                </div>
            `;
        }
    } catch (error) {
        if (body) body.innerHTML = '<div class="chunk-review-empty">Failed to load job details.</div>';
        alert(error.message || 'Failed to load job details');
    }
}

async function pauseQueueJob(jobId) {
    if (!jobId) return;
    try {
        const response = await fetch(`/api/jobs/${jobId}/pause`, { method: 'POST' });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to pause job');
        }
        loadQueue();
    } catch (error) {
        alert(error.message || 'Failed to pause job');
    }
}

async function resumeQueueJob(jobId) {
    if (!jobId) return;
    try {
        const response = await fetch(`/api/jobs/${jobId}/resume`, { method: 'POST' });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to resume job');
        }
        loadQueue();
    } catch (error) {
        alert(error.message || 'Failed to resume job');
    }
}

async function deleteQueueJob(jobId) {
    if (!jobId) return;
    if (!confirm('Remove this job from the queue? (Audio files will be kept)')) {
        return;
    }
    try {
        const response = await fetch(`/api/jobs/${jobId}/delete`, { method: 'DELETE' });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to delete job');
        }
        completedJobIds.delete(jobId);
        loadQueue();
        document.dispatchEvent(new CustomEvent('library:refresh'));
    } catch (error) {
        alert(error.message || 'Failed to delete job');
    }
}

function renderJobProgress(job) {
    const total = job.total_chunks || 0;
    const processed = Math.min(job.processed_chunks || 0, total || Infinity);
    const percent = total > 0 ? Math.round((processed / total) * 100) : (job.status === 'completed' ? 100 : 0);
    const chunkLabel = total ? `${processed} / ${total} chunk${total === 1 ? '' : 's'}` : 'Estimating…';
    const etaLabel = formatEta(job.eta_seconds, job.status);
    const chapterLabel = job.chapter_mode
        ? `${job.chapter_count || '?'} chapter${(job.chapter_count || 0) === 1 ? '' : 's'} (per chapter merge)`
        : 'Single output file';
    const postTotal = Number(job.post_process_total || 0);
    const postDone = Math.min(Number(job.post_process_done || 0), postTotal || Infinity);
    const postPercent = Number.isFinite(Number(job.post_process_percent))
        ? Math.max(0, Math.min(Math.round(Number(job.post_process_percent)), 100))
        : (postTotal > 0 ? Math.round((postDone / postTotal) * 100) : 0);
    const isFinishing = job.status === 'processing'
        && total > 0
        && processed >= total
        && (job.eta_seconds === 0 || job.eta_seconds === null || typeof job.eta_seconds !== 'number');
    const showPost = (postTotal > 0 && (job.post_process_active || postDone > 0)) || isFinishing;
    const postLabel = postTotal > 0
        ? `Post-processing ${postDone} / ${postTotal}`
        : 'Post-processing…';
    const postFillClass = postTotal > 0 ? 'progress-bar-fill' : 'progress-bar-fill indeterminate';
    const interruptedChip = job.status === 'interrupted'
        ? '<span class="review-chip warning">Interrupted</span>'
        : '';
    const resumeHint = job.status === 'interrupted' && Number.isFinite(Number(job.resume_from_chunk_index))
        ? `<span class="review-chip muted">Resume from chunk ${Number(job.resume_from_chunk_index) + 1}</span>`
        : '';

    return `
        <div class="queue-progress">
            ${job.status === 'processing' && job.breeze_voice_status ? `<div>${escapeHtml(job.breeze_voice_status)}</div>` : ''}
            <div class="queue-progress-header">
                <span>${chunkLabel}</span>
                <span>${etaLabel}</span>
            </div>
            <div class="progress-bar">
                <div class="progress-bar-fill" style="width: ${Math.min(Math.max(percent, 0), 100)}%;"></div>
            </div>
            <div class="queue-progress-footer">
                <span>${chapterLabel}</span>
                <span>${job.status === 'completed' ? 'Done' : job.status}</span>
            </div>
            ${interruptedChip || resumeHint ? `
                <div class="queue-progress-footer">
                    <span>${interruptedChip}</span>
                    <span>${resumeHint}</span>
                </div>
            ` : ''}
            ${showPost ? `
                <div class="queue-post-progress">
                    <div class="queue-progress-header">
                        <span>${postLabel}</span>
                        <span>${postPercent}%</span>
                    </div>
                    <div class="progress-bar">
                        <div class="${postFillClass}" style="width: ${Math.min(Math.max(postPercent, 0), 100)}%;"></div>
                    </div>
                </div>
            ` : ''}
        </div>
    `;
}

function formatEta(seconds, status) {
    if (status === 'completed') {
        return 'Done';
    }
    if (seconds === 0) {
        return 'Finishing up…';
    }
    if (typeof seconds !== 'number' || seconds < 0 || Number.isNaN(seconds)) {
        return 'Calculating…';
    }

    const minutes = Math.floor(seconds / 60);
    const secs = Math.max(seconds % 60, 0);
    if (minutes > 0) {
        return `ETA ${minutes}m ${secs.toFixed(0)}s`;
    }
    return `ETA ${secs.toFixed(0)}s`;
}

async function cancelQueueJob(jobId) {
    if (!confirm('Are you sure you want to cancel this job?')) {
        return;
    }

    try {
        const response = await fetch(`/api/cancel/${jobId}`, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            loadQueue();
        } else {
            alert('Failed to cancel job: ' + data.error);
        }
    } catch (error) {
        console.error('Error cancelling job:', error);
        alert('Error cancelling job');
    }
}

function downloadJobAudio(jobId) {
    window.location.href = `/api/download/${jobId}`;
}

function renderReviewCell(job) {
    if (!job.review_mode) {
        return '<span class="review-chip muted">N/A</span>';
    }

    const hasActiveRegen = Boolean(job.review_has_active_regen);
    const isOpen = openReviewPanels.has(job.job_id);
    const reviewState = (() => {
        switch (job.status) {
            case 'processing':
                return 'Live chunks';
            case 'waiting_review':
                return 'Waiting for finish';
            case 'completed':
                return 'Completed';
            default:
                return job.status;
        }
    })();

    return `
        <div class="review-cell">
            <div class="review-status-line">
                <span class="review-chip ${job.status === 'waiting_review' ? 'accent' : 'muted'}">
                    ${reviewState}
                </span>
                ${hasActiveRegen ? '<span class="review-chip warning">Regen running</span>' : ''}
            </div>
            <div class="review-buttons">
                <button class="btn-small btn-secondary"
                        data-action="toggle-review"
                        data-job-id="${job.job_id}">
                    ${isOpen ? 'Hide review' : 'Review chunks'}
                </button>
                ${job.status === 'waiting_review' ? `
                    <button class="btn-small btn-primary"
                            data-action="finish-review"
                            data-job-id="${job.job_id}"
                            ${hasActiveRegen ? 'disabled title="Wait for regenerations to finish"' : ''}>
                        Finish review
                    </button>` : ''}
            </div>
        </div>
    `;
}

function handleQueueActionClick(event) {
    const actionButton = event.target.closest('[data-action]');
    if (!actionButton) {
        return;
    }

    const action = actionButton.dataset.action;
    const jobId = actionButton.dataset.jobId;
    const chunkId = actionButton.dataset.chunkId;

    switch (action) {
        case 'toggle-review':
            toggleReviewPanel(jobId);
            break;
        case 'finish-review':
            finishReviewJob(jobId, actionButton);
            break;
        case 'chunk-play':
            handleChunkPlayback(actionButton);
            break;
        case 'chunk-edit':
            toggleChunkEditing(actionButton);
            break;
        case 'chunk-regenerate':
            triggerChunkRegeneration(jobId, chunkId, actionButton);
            break;
        case 'refresh-chunks':
            renderReviewPanel(jobId);
            break;
        case 'regen-job':
            regenerateEntireJob(jobId, actionButton);
            break;
        default:
            break;
    }
}

function toggleReviewPanel(jobId) {
    if (!jobId) return;

    const row = document.querySelector(`.review-panel-row[data-review-row="${jobId}"]`);
    const panel = document.getElementById(`review-panel-${jobId}`);
    if (!row || !panel) {
        openReviewPanels.delete(jobId);
        return;
    }

    const isOpening = !openReviewPanels.has(jobId);
    if (isOpening) {
        openReviewPanels.add(jobId);
        row.classList.add('open');
        panel.classList.add('open');
        renderReviewPanel(jobId);
    } else {
        openReviewPanels.delete(jobId);
        reviewPanelScrollPositions.delete(jobId);
        clearPanelEditorState(jobId);
        clearEditingStateForJob(jobId);
        jobChunkMaps.delete(jobId);
        row.classList.remove('open');
        panel.classList.remove('open');
        panel.innerHTML = '<div class="review-panel-collapsed">Review panel collapsed</div>';
    }

    updateReviewToggleButtons(jobId);
}

function setRefreshButtonState(jobId, isLoading) {
    document.querySelectorAll(`[data-action="refresh-chunks"][data-job-id="${jobId}"]`).forEach(button => {
        button.disabled = isLoading;
        button.textContent = isLoading ? 'Refreshing…' : 'Refresh chunks';
    });
}

function updateRefreshButtonsForOpenPanels() {
    openReviewPanels.forEach(jobId => {
        setRefreshButtonState(jobId, chunkPanelLoadingJobs.has(jobId));
    });
}

function cacheOpenPanelScrollPositions() {
    openReviewPanels.forEach(jobId => {
        const body = document.querySelector(`#review-panel-${jobId} .review-panel-body`);
        if (body) {
            reviewPanelScrollPositions.set(jobId, body.scrollTop);
        }
    });
}

function restoreOpenPanelScrollPositions() {
    openReviewPanels.forEach(jobId => {
        restorePanelScroll(jobId);
    });
}

function hookOpenPanelScrollTracking() {
    openReviewPanels.forEach(jobId => {
        attachPanelScrollTracking(jobId);
    });
}

function restorePanelScroll(jobId) {
    const scrollTop = reviewPanelScrollPositions.get(jobId);
    if (scrollTop == null) {
        return;
    }
    const body = document.querySelector(`#review-panel-${jobId} .review-panel-body`);
    if (body) {
        body.scrollTop = scrollTop;
    }
}

function attachPanelScrollTracking(jobId) {
    const body = document.querySelector(`#review-panel-${jobId} .review-panel-body`);
    if (!body || body.dataset.scrollTrackingAttached === 'true') {
        return;
    }
    const handler = () => {
        reviewPanelScrollPositions.set(jobId, body.scrollTop);
    };
    body.addEventListener('scroll', handler, { passive: true });
    body.dataset.scrollTrackingAttached = 'true';
}

function afterPanelRender(jobId) {
    restorePanelScroll(jobId);
    attachPanelScrollTracking(jobId);
    restorePanelEditorState(jobId);
    syncActiveChunkControls();
}

async function renderReviewPanel(jobId, options = {}) {
    const panel = document.getElementById(`review-panel-${jobId}`);
    if (!panel) {
        openReviewPanels.delete(jobId);
        return;
    }

    if (chunkPanelLoadingJobs.has(jobId)) {
        return;
    }

    cachePanelEditorState(jobId);

    const { silent = false } = options;
    chunkPanelLoadingJobs.add(jobId);
    setRefreshButtonState(jobId, true);
    if (!silent) {
        panel.innerHTML = '<div class="review-panel-loading">Loading chunk data…</div>';
    }

    try {
        const response = await fetch(`/api/jobs/${jobId}/chunks`);
        const payload = await response.json();
        if (!payload.success) {
            throw new Error(payload.error || 'Failed to load chunk metadata');
        }
        cacheJobChunkMap(jobId, payload);
        reviewPanelContentCache.set(jobId, payload);
        const latestPanel = document.getElementById(`review-panel-${jobId}`);
        if (latestPanel) {
            latestPanel.innerHTML = renderChunkTable(jobId, payload);
            afterPanelRender(jobId);
            syncChunkRegenWatchersFromPayload(jobId, payload);
        }
    } catch (error) {
        console.error('Failed to load chunk data', error);
        const latestPanel = document.getElementById(`review-panel-${jobId}`);
        if (latestPanel) {
            latestPanel.innerHTML = `<div class="review-panel-error">${error.message || 'Failed to load chunk metadata'}</div>`;
        }
    } finally {
        chunkPanelLoadingJobs.delete(jobId);
        setRefreshButtonState(jobId, false);
    }
}

function renderChunkTable(jobId, payload) {
    const chunks = payload.chunks || [];
    const regenTasks = payload.regen_tasks || {};
    const reviewInfo = payload.review || {};
    const hasChunks = chunks.length > 0;
    const canFinish = reviewInfo.status === 'waiting_review' && !reviewInfo.has_active_regen;
    const engine = (reviewInfo.engine || '').toLowerCase();

    const header = renderReviewPanelHeader(jobId, payload, { hasChunks, canFinish });

    const body = hasChunks
        ? `
            <div class="review-panel-body">
                <div class="chunk-table">
                    ${chunks.map(chunk => renderChunkRow(jobId, chunk, regenTasks[chunk.id], engine)).join('')}
                </div>
            </div>
        `
        : `
            <div class="review-panel-empty">
                No chunks available yet. Keep this panel open to watch them appear in real time.
            </div>
        `;

    return `
        ${header}
        ${body}
    `;
}

function renderReviewPanelHeader(jobId, payload, overrides = {}) {
    const chunks = payload.chunks || [];
    const reviewInfo = payload.review || {};
    const hasChunks = overrides.hasChunks != null ? overrides.hasChunks : chunks.length > 0;
    const canFinishOverride = overrides.canFinish;
    const canFinish =
        typeof canFinishOverride === 'boolean'
            ? canFinishOverride
            : reviewInfo.status === 'waiting_review' && !reviewInfo.has_active_regen;
    const isRefreshing = chunkPanelLoadingJobs.has(jobId);
    return `
        <div class="review-panel-header">
            <div>
                <strong>Chunks ready:</strong> ${chunks.length}
                ${reviewInfo.has_active_regen ? '<span class="review-chip warning">Regen running</span>' : ''}
            </div>
            <div class="review-panel-actions">
                <button class="btn-small btn-outline"
                        data-action="refresh-chunks"
                        data-job-id="${jobId}"
                        ${isRefreshing ? 'disabled' : ''}>
                    ${isRefreshing ? 'Refreshing…' : 'Refresh chunks'}
                </button>
                <button class="btn-small btn-secondary"
                        data-action="toggle-review"
                        data-job-id="${jobId}">
                    Hide panel
                </button>
                <button class="btn-small btn-warning"
                        data-action="regen-job"
                        data-job-id="${jobId}"
                        ${hasChunks ? '' : 'disabled'}>
                    Regenerate entire job
                </button>
                <button class="btn-small btn-primary"
                        data-action="finish-review"
                        data-job-id="${jobId}"
                        ${canFinish ? '' : 'disabled'}>
                    Finish review
                </button>
            </div>
        </div>
    `;
}

function renderChunkRow(jobId, chunk, regenState = {}, engine = '') {
    const isEditing = false;
    const playLabel = activeChunkId === chunk.id ? 'Stop' : 'Play';
    const regenStatusLabel = renderRegenStatus(regenState);
    const durationLabel = chunk.duration_seconds ? `${chunk.duration_seconds.toFixed(1)}s` : '—';
    const chunkLabel = `Chunk ${chunk.order_index + 1}`;
    const chapterLabel = chunk.chapter_index != null ? `Chapter ${chunk.chapter_index + 1}` : 'Single output';
    const voiceLabelTag = renderChunkVoiceLabel(jobId, chunk, engine);
    const voiceControl = renderChunkVoiceControl(jobId, chunk, engine);
    const cacheToken = chunk.cache_bust_token || chunk.regenerated_at || chunk.relative_file || Date.now().toString();
    const audioUrl = chunk.file_url ? cacheBustUrl(chunk.file_url, cacheToken) : '';

    return `
        <div class="chunk-row" data-chunk-id="${chunk.id}">
            <div class="chunk-row-meta">
                <div>
                    <strong>${chunkLabel}</strong> • <span>${chapterLabel}</span>
                </div>
                <div class="chunk-row-tags">
                    ${chunk.speaker ? `<span class="chunk-tag">${chunk.speaker}</span>` : ''}
                    <span class="chunk-tag subtle">${durationLabel}</span>
                    ${regenStatusLabel}
                    ${voiceLabelTag}
                </div>
            </div>
            <div class="chunk-row-audio">
                <button class="btn-small btn-secondary"
                        data-action="chunk-play"
                        data-job-id="${jobId}"
                        data-chunk-id="${chunk.id}"
                        data-audio-url="${audioUrl}">
                    ${playLabel}
                </button>
            </div>
            <div class="chunk-row-editor">
                <textarea data-chunk-text="${chunk.id}" disabled>${chunk.text || ''}</textarea>
            </div>
            ${voiceControl}
            <div class="chunk-row-controls">
                <button class="btn-small btn-secondary"
                        data-action="chunk-edit"
                        data-job-id="${jobId}"
                        data-chunk-id="${chunk.id}">
                    Edit text
                </button>
                <button class="btn-small btn-primary"
                        data-action="chunk-regenerate"
                        data-job-id="${jobId}"
                        data-chunk-id="${chunk.id}">
                    Re-generate chunk
                </button>
            </div>
        </div>
    `;
}

function renderRegenStatus(state = {}) {
    const status = state.status;
    if (!status) {
        return '';
    }
    const label = (() => {
        switch (status) {
            case 'queued':
                return 'Queued';
            case 'running':
                return 'Rendering';
            case 'completed':
                return 'Updated';
            case 'failed':
                return 'Failed';
            default:
                return status;
        }
    })();
    const tone = status === 'failed' ? 'danger' : status === 'completed' ? 'success' : 'warning';
    return `<span class="chunk-tag ${tone}">${label}</span>`;
}

function handleChunkPlayback(button) {
    const chunkId = button.dataset.chunkId;
    const audioUrl = button.dataset.audioUrl;
    if (!chunkId || !audioUrl) {
        alert('Chunk audio not ready yet.');
        return;
    }

    if (activeChunkId === chunkId) {
        stopActiveChunk();
        return;
    }

    stopActiveChunk();
    activeChunkAudio = new Audio(audioUrl);
    activeChunkId = chunkId;
    activeChunkButton = button;
    button.textContent = 'Stop';
    activeChunkAudio.play().catch(err => {
        console.error('Failed to play chunk audio', err);
        stopActiveChunk();
    });
    activeChunkAudio.addEventListener('ended', stopActiveChunk);
}

function stopActiveChunk() {
    if (activeChunkAudio) {
        activeChunkAudio.pause();
        activeChunkAudio.currentTime = 0;
    }
    if (activeChunkButton && document.body.contains(activeChunkButton)) {
        activeChunkButton.textContent = 'Play';
    }
    activeChunkAudio = null;
    activeChunkButton = null;
    activeChunkId = null;
}

function toggleChunkEditing(button) {
    const chunkId = button.dataset.chunkId;
    const jobId = button.dataset.jobId;
    const textarea = document.querySelector(`textarea[data-chunk-text="${chunkId}"]`);
    if (!textarea) {
        return;
    }
    const isDisabled = textarea.disabled;
    if (isDisabled) {
        textarea.disabled = false;
        textarea.focus();
        button.textContent = 'Lock text';
        activeEditingChunks.set(chunkId, jobId);
        stopQueueAutoRefresh();
    } else {
        textarea.disabled = true;
        button.textContent = 'Edit text';
        activeEditingChunks.delete(chunkId);
        resumeQueueAutoRefreshIfIdle();
    }
    const selectionEnd = textarea.value.length;
    textarea.setSelectionRange(selectionEnd, selectionEnd);
    cachePanelEditorState(jobId);
}

async function triggerChunkRegeneration(jobId, chunkId, button) {
    if (!jobId || !chunkId) return;
    const textarea = document.querySelector(`textarea[data-chunk-text="${chunkId}"]`);
    if (!textarea) {
        return;
    }
    const updatedText = textarea.value.trim();
    if (!updatedText) {
        alert('Chunk text cannot be empty.');
        return;
    }

    button.disabled = true;
    button.textContent = 'Re-generating…';
    try {
        const response = await fetch(`/api/jobs/${jobId}/review/regen`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chunk_id: chunkId,
                text: updatedText,
                voice: getVoicePayloadForChunk(jobId, chunkId),
            }),
        });
        const payload = await response.json();
        if (!payload.success) {
            throw new Error(payload.error || 'Failed to queue regeneration');
        }
        showReviewToast('Chunk regeneration queued.');
        renderReviewPanel(jobId, { silent: true });
        startChunkRegenWatcher(jobId, chunkId);
    } catch (error) {
        alert(error.message || 'Failed to queue chunk regeneration.');
    } finally {
        button.disabled = false;
        button.textContent = 'Re-generate chunk';
    }
}

function getVoicePayloadForChunk(jobId, chunkId) {
    const override = getChunkVoiceOverride(jobId, chunkId);
    let payload = override && Object.keys(override).length ? cloneVoiceAssignment(override) : null;
    if (!payload) {
        const select = document.querySelector(
            `[data-chunk-voice-select="true"][data-job-id="${jobId}"][data-chunk-id="${chunkId}"]`
        );
        payload = buildPayloadFromVoiceSelect(select);
    }
    if (!payload) {
        return null;
    }
    if (payload.voice && !payload.lang_code) {
        payload.lang_code = resolveLangCodeForVoice(payload.voice);
    }
    return payload;
}

async function finishReviewJob(jobId, button) {
    if (!jobId) return;
    button.disabled = true;
    button.textContent = 'Finishing…';
    try {
        const response = await fetch(`/api/jobs/${jobId}/review/finish`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const payload = await response.json();
        if (!payload.success) {
            throw new Error(payload.error || 'Failed to finish review');
        }
        clearChunkRegenWatchersForJob(jobId);
        closeReviewPanelForJob(jobId);
        showReviewToast('Review finalized! Merging chunks now.');
        loadQueue();
    } catch (error) {
        alert(error.message || 'Failed to finish review.');
    } finally {
        button.disabled = false;
        button.textContent = 'Finish review';
    }
}

function closeReviewPanelForJob(jobId) {
    if (!jobId) return;
    openReviewPanels.delete(jobId);
    reviewPanelScrollPositions.delete(jobId);
    reviewPanelContentCache.delete(jobId);
    clearPanelEditorState(jobId);
    clearEditingStateForJob(jobId);
    clearVoiceOverridesForJob(jobId);
    jobChunkMaps.delete(jobId);
    const row = document.querySelector(`.review-panel-row[data-review-row="${jobId}"]`);
    const panel = document.getElementById(`review-panel-${jobId}`);
    if (row) {
        row.classList.remove('open');
    }
    if (panel) {
        panel.classList.remove('open');
        panel.innerHTML = '';
    }
    updateReviewToggleButtons(jobId);
}

function syncReviewPanelState(jobs) {
    const reviewJobs = new Set(
        jobs.filter(job => job.review_mode).map(job => job.job_id)
    );
    Array.from(openReviewPanels).forEach(jobId => {
        if (!reviewJobs.has(jobId)) {
            openReviewPanels.delete(jobId);
        }
    });
}

function updateReviewToggleButtons(jobId) {
    const isOpen = openReviewPanels.has(jobId);
    document.querySelectorAll(`[data-action="toggle-review"][data-job-id="${jobId}"]`).forEach(button => {
        button.textContent = isOpen ? 'Hide review' : 'Review chunks';
    });
}

function cachePanelEditorState(jobId) {
    const panel = document.getElementById(`review-panel-${jobId}`);
    if (!panel) {
        reviewPanelEditorState.delete(jobId);
        return;
    }
    const state = {};
    panel.querySelectorAll('textarea[data-chunk-text]').forEach(textarea => {
        const chunkId = textarea.dataset.chunkText;
        if (!chunkId) {
            return;
        }
        const pendingText = chunkPendingTextEdits.get(chunkId);
        const lastValue = pendingText != null ? pendingText : textarea.value;
        let selectionStart = null;
        let selectionEnd = null;
        if (!textarea.disabled) {
            try {
                selectionStart = textarea.selectionStart;
                selectionEnd = textarea.selectionEnd;
            } catch (_) {
                selectionStart = selectionEnd = textarea.value.length;
            }
        }
        state[chunkId] = {
            text: lastValue,
            editing: !textarea.disabled,
            selectionStart,
            selectionEnd,
            hadFocus: document.activeElement === textarea,
        };
    });
    reviewPanelEditorState.set(jobId, state);
    const body = panel.querySelector('.review-panel-body');
    if (body) {
        reviewPanelScrollPositions.set(jobId, body.scrollTop);
    }
}

function restorePanelEditorState(jobId) {
    const state = reviewPanelEditorState.get(jobId);
    if (!state) {
        return;
    }
    Object.entries(state).forEach(([chunkId, info]) => {
        const textarea = document.querySelector(`textarea[data-chunk-text="${chunkId}"]`);
        const button = document.querySelector(`[data-action="chunk-edit"][data-chunk-id="${chunkId}"]`);
        if (!textarea) {
            return;
        }
        if (info.text != null && textarea.value !== info.text) {
            textarea.value = info.text;
        }
        if (info.editing) {
            textarea.disabled = false;
            if (button) {
                button.textContent = 'Lock text';
            }
            requestAnimationFrame(() => {
                try {
                    if (info.selectionStart != null && info.selectionEnd != null) {
                        textarea.setSelectionRange(info.selectionStart, info.selectionEnd);
                    }
                } catch (_) {
                    const end = textarea.value.length;
                    textarea.setSelectionRange(end, end);
                }
                if (info.hadFocus) {
                    textarea.focus();
                }
            });
        } else {
            textarea.disabled = true;
            if (button) {
                button.textContent = 'Edit text';
            }
        }
    });
}

function clearPanelEditorState(jobId) {
    reviewPanelEditorState.delete(jobId);
    cachePendingTextEdits(jobId, true);
}

function clearEditingStateForJob(jobId) {
    Array.from(activeEditingChunks.entries()).forEach(([chunkId, mappedJobId]) => {
        if (mappedJobId === jobId) {
            activeEditingChunks.delete(chunkId);
        }
    });
    resumeQueueAutoRefreshIfIdle();
}

function syncActiveChunkControls() {
    if (!activeChunkId) {
        return;
    }
    const button = document.querySelector(`[data-action="chunk-play"][data-chunk-id="${activeChunkId}"]`);
    if (!button) {
        stopActiveChunk();
        return;
    }
    activeChunkButton = button;
    if (activeChunkAudio && !activeChunkAudio.paused) {
        button.textContent = 'Stop';
    } else {
        button.textContent = 'Play';
    }
}

function showReviewToast(message) {
    const toast = document.createElement('div');
    toast.className = 'review-toast';
    toast.textContent = message;
    document.body.appendChild(toast);
    requestAnimationFrame(() => {
        toast.classList.add('show');
    });
    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 2500);
}
