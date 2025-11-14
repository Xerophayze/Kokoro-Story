// Voice Manager - Handles voice library and selection

let voiceData = null;
// Make availableVoices globally accessible for main.js
window.availableVoices = null;

const audioPreviewCache = {};
let currentPreviewAudio = null;
let currentPreviewItem = null;
let samplesReady = false;
let lastFailedSamples = [];

const generateSamplesBtnId = 'generate-voice-samples-btn';
const regenerateSamplesBtnId = 'regenerate-voice-samples-btn';
const sampleStatusId = 'voice-sample-status';

// Load voices on page load
document.addEventListener('DOMContentLoaded', () => {
    loadVoices();
});

// Load available voices from API
async function loadVoices() {
    try {
        const response = await fetch('/api/voices');
        const data = await response.json();
        
        if (data.success) {
            voiceData = data.voices;
            window.availableVoices = data.voices; // Make globally accessible
            samplesReady = data.samples_ready;
            updateSampleStatus(data);
            displayVoiceLibrary(data.voices);
        } else {
            displaySampleError(data.error || 'Unable to load voices');
        }
    } catch (error) {
        console.error('Error loading voices:', error);
        displaySampleError('Error loading voices');
    }
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
                updateSampleStatus(data);
                displayVoiceLibrary(data.voices);
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
