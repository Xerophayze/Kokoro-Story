// Settings Management

document.addEventListener('DOMContentLoaded', () => {
    loadSettings();
    setupSettingsListeners();
});

// Setup event listeners
function setupSettingsListeners() {
    // Mode selection
    document.querySelectorAll('input[name="mode"]').forEach(radio => {
        radio.addEventListener('change', (e) => {
            const replicateSettings = document.getElementById('replicate-settings');
            replicateSettings.style.display = e.target.value === 'replicate' ? 'block' : 'none';
        });
    });
    
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

// Apply settings to UI
function applySettings(settings) {
    // Mode
    const modeRadio = document.querySelector(`input[name="mode"][value="${settings.mode}"]`);
    if (modeRadio) {
        modeRadio.checked = true;
        const replicateSettings = document.getElementById('replicate-settings');
        replicateSettings.style.display = settings.mode === 'replicate' ? 'block' : 'none';
    }
    
    // API Key
    if (settings.replicate_api_key) {
        document.getElementById('api-key').value = settings.replicate_api_key;
    }
    
    // Chunk size
    document.getElementById('chunk-size').value = settings.chunk_size || 500;
    
    // Speed
    const speed = settings.speed || 1.0;
    document.getElementById('speed').value = speed;
    document.getElementById('speed-value').textContent = speed + 'x';
    
    // Output format
    document.getElementById('output-format').value = settings.output_format || 'mp3';
    
    // Crossfade
    document.getElementById('crossfade').value = settings.crossfade_duration || 0.1;
    
    // Silence controls
    document.getElementById('intro-silence').value = settings.intro_silence_ms ?? 0;
    document.getElementById('inter-silence').value = settings.inter_chunk_silence_ms ?? 0;

    // Gemini settings
    document.getElementById('gemini-api-key').value = settings.gemini_api_key || '';
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
    document.getElementById('gemini-prompt').value = settings.gemini_prompt || '';
}

// Save settings
async function saveSettings() {
    const settings = {
        mode: document.querySelector('input[name="mode"]:checked').value,
        replicate_api_key: document.getElementById('api-key').value,
        chunk_size: parseInt(document.getElementById('chunk-size').value),
        speed: parseFloat(document.getElementById('speed').value),
        output_format: document.getElementById('output-format').value,
        crossfade_duration: parseFloat(document.getElementById('crossfade').value),
        intro_silence_ms: parseInt(document.getElementById('intro-silence').value, 10) || 0,
        inter_chunk_silence_ms: parseInt(document.getElementById('inter-silence').value, 10) || 0,
        gemini_api_key: document.getElementById('gemini-api-key').value,
        gemini_model: document.getElementById('gemini-model').value,
        gemini_prompt: document.getElementById('gemini-prompt').value
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
            loadHealthStatus(); // Refresh status bar
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
        inter_chunk_silence_ms: 0
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
