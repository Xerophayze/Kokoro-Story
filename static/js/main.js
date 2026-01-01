// Main application logic

let currentJobId = null;
let currentStats = null;
let analyzeDebounceTimer = null;
let lastAnalyzedText = '';
const ANALYZE_DEBOUNCE_MS = 800;
const VOICES_EVENT_NAME = window.VOICES_UPDATED_EVENT || 'voices:updated';
const DEFAULT_FX_STATE = Object.freeze({
    pitch: 0,
    tempo: 1,
    tone: 'neutral',
    sampleText: ''
});
const voiceFxState = {};
let currentFxPreviewAudio = null;

window.customVoiceMap = window.customVoiceMap || {};
window.addEventListener(VOICES_EVENT_NAME, handleVoicesUpdated);

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
            tempo: DEFAULT_FX_STATE.tempo,
            tone: DEFAULT_FX_STATE.tone,
            sampleText: DEFAULT_FX_STATE.sampleText
        };
    }
    return voiceFxState[key];
}

function getFxPayload(speaker) {
    const state = getFxState(speaker);
    return {
        pitch: Number(state.pitch) || 0,
        tempo: Number(state.tempo) || 1,
        tone: state.tone || 'neutral'
    };
}

function createAssignment(voiceName, langCode, speakerKey) {
    const assignment = {
        voice: voiceName,
        lang_code: langCode
    };
    const fxPayload = getFxPayload(speakerKey);
    if (fxPayload) {
        assignment.fx = fxPayload;
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
    const previewMarkup = !useSharedPreview
        ? `
            <div class="fx-field fx-preview">
                <textarea data-role="fx-sample-text" rows="2" placeholder="Preview text">${state.sampleText || buildDefaultSampleText(speaker)}</textarea>
                <button type="button" class="btn btn-sm" data-role="fx-preview-btn">Quick Test</button>
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
                    <label>Tempo</label>
                    <div class="slider-group">
                        <input type="range" min="0.75" max="1.35" step="0.01" value="${state.tempo}" data-role="fx-tempo">
                        <span class="slider-value" data-role="fx-tempo-value">${state.tempo.toFixed(2)}x</span>
                    </div>
                </div>
                <div class="fx-field fx-inline fx-tone ${useSharedPreview ? 'fx-tone-actions' : ''}">
                    <label>Tone</label>
                    <div class="tone-pill-group" data-role="fx-tone-group">
                        ${['neutral', 'warm', 'bright'].map(tone => `
                            <button type="button" class="tone-pill ${state.tone === tone ? 'active' : ''}" data-tone="${tone}">
                                ${tone.charAt(0).toUpperCase() + tone.slice(1)}
                            </button>
                        `).join('')}
                    </div>
                    ${useSharedPreview ? '<button type="button" class="btn btn-sm" data-role="fx-preview-btn">Quick Test</button>' : ''}
                </div>
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
    const tempoInput = container.querySelector('[data-role="fx-tempo"]');
    const tempoValue = container.querySelector('[data-role="fx-tempo-value"]');
    const toneButtonsEls = container.querySelectorAll('[data-tone]');
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
    if (tempoInput && tempoValue) {
        tempoInput.addEventListener('input', event => {
            state.tempo = parseFloat(event.target.value) || 1;
            tempoValue.textContent = `${state.tempo.toFixed(2)}x`;
        });
    }
    toneButtonsEls.forEach(button => {
        button.addEventListener('click', () => {
            const selectedTone = button.dataset.tone || 'neutral';
            state.tone = selectedTone;
            toneButtonsEls.forEach(btn => btn.classList.toggle('active', btn === button));
        });
    });
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
        speed: parseFloat(document.getElementById('speed')?.value) || 1.0,
    };
    const fxPayload = getFxPayload(speaker);
    if (fxPayload) {
        payload.fx = fxPayload;
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

async function processWithGemini(buttonEl) {
    const inputEl = document.getElementById('input-text');
    if (!inputEl) return;

    const text = inputEl.value;
    if (!text.trim()) {
        alert('Please enter some text first');
        return;
    }

    const splitByChapter = document.getElementById('split-chapters-checkbox')?.checked ?? false;
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
                body: JSON.stringify({ text })
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
    populateDefaultVoiceSelect();
    initDefaultVoiceFxPanel();
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

// Load health status
async function loadHealthStatus() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        
        if (data.success) {
            document.getElementById('current-mode').textContent = 
                data.mode === 'local' ? 'Local GPU' : 'Replicate API';
            document.getElementById('cuda-status').textContent = 
                data.cuda_available ? 'Available' : 'Not Available';
            
            // Update mode indicator color
            const modeEl = document.getElementById('current-mode');
            modeEl.style.color = data.mode === 'local' ? '#10b981' : '#f59e0b';
        }
    } catch (error) {
        console.error('Error loading health status:', error);
    }
}

// Analyze text
async function analyzeText(options = {}) {
    const { auto = false } = options;
    const text = document.getElementById('input-text').value;
    
    if (!text.trim()) {
        alert('Please enter some text first');
        return false;
    }
    
    if (!auto) {
        showNotification('Analyzing text...', 'info');
    }
    
    try {
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ text })
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
        row.innerHTML = `
            <div class="voice-fx-inline voice-inline-card" data-speaker="${speaker}"></div>
        `;
        container.appendChild(row);
        const fxContainer = row.querySelector('.voice-fx-inline');
        if (fxContainer) {
            renderFxPanel(fxContainer, speaker, {
                title: `${speaker} FX`,
                showHeader: false,
                useSharedPreview: true
            });

            const fields = fxContainer.querySelector('.fx-fields');
            if (fields) {
                const selectBlock = document.createElement('div');
                selectBlock.className = 'fx-field voice-select-inline';
                const label = document.createElement('label');
                label.textContent = speaker;
                const selectEl = document.createElement('select');
                selectEl.className = 'voice-select';
                selectEl.dataset.speaker = speaker;
                selectEl.innerHTML = '<option value="">Select Voice...</option>';
                selectBlock.appendChild(label);
                selectBlock.appendChild(selectEl);
                fields.insertBefore(selectBlock, fields.firstChild);
            }
        }
    });
    
    // Populate voice options (wait for voices to load if needed)
    if (window.availableVoices) {
        populateVoiceSelects();
    } else {
        // Wait for voices to load
        const checkVoices = setInterval(() => {
            if (window.availableVoices) {
                clearInterval(checkVoices);
                populateVoiceSelects();
            }
        }, 100);
    }
    
    document.getElementById('inline-voice-assignments').style.display = 'block';
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
    
    // Don't disable the button - allow multiple submissions
    const generateBtn = document.getElementById('generate-btn');
    
    const splitByChapter = document.getElementById('split-chapters-checkbox')?.checked || false;
    const generateFullStory = splitByChapter && (document.getElementById('full-story-checkbox')?.checked || false);
    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                text,
                voice_assignments: voiceAssignments,
                split_by_chapter: splitByChapter,
                generate_full_story: generateFullStory
            })
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
    }
}

// Start periodic queue indicator updates
setInterval(updateQueueIndicator, 2000);

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
        if (key === 'default') {
            voiceFxState[key] = {
                pitch: DEFAULT_FX_STATE.pitch,
                tempo: DEFAULT_FX_STATE.tempo,
                tone: DEFAULT_FX_STATE.tone,
                sampleText: DEFAULT_FX_STATE.sampleText
            };
        } else {
            delete voiceFxState[key];
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
function getVoiceAssignments() {
    const assignments = {};
    const selects = document.querySelectorAll('#inline-voice-assignment-list .voice-select');
    
    selects.forEach(select => {
        const speaker = select.dataset.speaker;
        const voiceName = select.value;
        
        if (voiceName && window.availableVoices) {
            const langCode = getLangCodeForVoice(voiceName);
            console.log(`Voice ${voiceName} found with lang_code: ${langCode}`);
            
            assignments[speaker] = createAssignment(voiceName, langCode, speaker);
        }
    });
    
    console.log('Voice assignments:', assignments);
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
