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
}

// Save settings
async function saveSettings() {
    const settings = {
        mode: document.querySelector('input[name="mode"]:checked').value,
        replicate_api_key: document.getElementById('api-key').value,
        chunk_size: parseInt(document.getElementById('chunk-size').value),
        speed: parseFloat(document.getElementById('speed').value),
        output_format: document.getElementById('output-format').value,
        crossfade_duration: parseFloat(document.getElementById('crossfade').value)
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
        crossfade_duration: 0.1
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
