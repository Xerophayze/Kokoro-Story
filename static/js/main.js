// Main application logic

let currentJobId = null;
let currentStats = null;
let analyzeDebounceTimer = null;
let lastAnalyzedText = '';
const ANALYZE_DEBOUNCE_MS = 800;

function refreshChapterHint() {
    const chapterHint = document.getElementById('chapter-detection-hint');
    const chapterCheckbox = document.getElementById('split-chapters-checkbox');
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

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadHealthStatus();
    setupEventListeners();
    populateDefaultVoiceSelect();
    initAutoAnalyze();
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
    const downloadBtn = document.getElementById('download-btn');
    const newGenerationBtn = document.getElementById('new-generation-btn');
    const cancelBtn = document.getElementById('cancel-btn');
    const chapterCheckbox = document.getElementById('split-chapters-checkbox');

    if (analyzeBtn) {
        analyzeBtn.addEventListener('click', analyzeText);
    }
    if (generateBtn) {
        generateBtn.addEventListener('click', generateAudio);
    }
    if (downloadBtn) {
        downloadBtn.addEventListener('click', downloadAudio);
    }
    if (newGenerationBtn) {
        newGenerationBtn.addEventListener('click', resetGeneration);
    }
    if (cancelBtn) {
        cancelBtn.addEventListener('click', cancelGeneration);
    }
    if (chapterCheckbox) {
        chapterCheckbox.addEventListener('change', () => {
            chapterCheckbox.dataset.userToggled = 'true';
            refreshChapterHint();
        });
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
            <label>${speaker}:</label>
            <select class="voice-select" data-speaker="${speaker}">
                <option value="">Select Voice...</option>
            </select>
        `;
        container.appendChild(row);
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
        Object.entries(window.availableVoices).forEach(([langCode, voiceConfig]) => {
            const optgroup = document.createElement('optgroup');
            optgroup.label = voiceConfig.language;
            
            voiceConfig.voices.forEach(voiceName => {
                const option = document.createElement('option');
                option.value = voiceName;
                option.textContent = voiceName;
                optgroup.appendChild(option);
            });
            
            select.appendChild(optgroup);
        });
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
                voiceAssignments[speaker] = {
                    voice: defaultVoice,
                    lang_code: langCode
                };
            });
        } else {
            voiceAssignments['default'] = {
                voice: defaultVoice,
                lang_code: langCode
            };
        }
    }
    
    console.log('Voice assignments for generation:', voiceAssignments);
    
    // Don't disable the button - allow multiple submissions
    const generateBtn = document.getElementById('generate-btn');
    
    const splitByChapter = document.getElementById('split-chapters-checkbox')?.checked || false;
    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                text,
                voice_assignments: voiceAssignments,
                split_by_chapter: splitByChapter
            })
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success notification
            showNotification(`Job queued! Position: ${data.queue_position}`, 'success');
            
            // Update queue indicator
            updateQueueIndicator();
            
            // Clear the form for next submission
            currentStats = null;
            document.getElementById('stats-section').style.display = 'none';
            
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

// Populate default voice selector
function populateDefaultVoiceSelect() {
    const select = document.getElementById('default-voice-select');
    
    // Wait for voices to load
    const checkVoices = setInterval(() => {
        if (window.availableVoices) {
            clearInterval(checkVoices);
            
            // Clear existing options except the first one
            select.innerHTML = '<option value="">Select Default Voice...</option>';
            
            // Add all voices grouped by language
            Object.entries(window.availableVoices).forEach(([langCode, voiceConfig]) => {
                const optgroup = document.createElement('optgroup');
                optgroup.label = voiceConfig.language;
                
                voiceConfig.voices.forEach(voiceName => {
                    const option = document.createElement('option');
                    option.value = voiceName;
                    option.textContent = voiceName;
                    optgroup.appendChild(option);
                });
                
                select.appendChild(optgroup);
            });
        }
    }, 100);
}

// Helper function to get lang_code for a voice
function getLangCodeForVoice(voiceName) {
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
            
            assignments[speaker] = {
                voice: voiceName,
                lang_code: langCode
            };
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
