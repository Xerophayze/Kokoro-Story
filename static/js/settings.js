// Settings Management

const geminiPresetState = {
    list: [],
    editingId: null,
    isPersisting: false,
};

const LOCAL_LLM_BASE_URLS = {
    lmstudio: 'http://localhost:1234/v1',
    ollama: 'http://localhost:11434'
};
const ATLAS_CLOUD_BASE_URL = 'https://api.atlascloud.ai/v1';
const OPENROUTER_BASE_URL = 'https://openrouter.ai/api/v1';
const ELEVENLABS_BASE_URL = 'https://api.elevenlabs.io';
const OPENAI_TTS_BASE_URL = 'https://api.openai.com/v1';
const LOCALAI_TTS_BASE_URL = 'http://localhost:8080/v1';
const OPENAI_TTS_MODELS = [
    ['gpt-4o-mini-tts', 'GPT-4o mini TTS'],
    ['gpt-4o-mini-tts-2025-12-15', 'GPT-4o mini TTS (2025-12-15 snapshot)'],
    ['tts-1', 'TTS-1'],
    ['tts-1-hd', 'TTS-1 HD'],
];
const OPENAI_TTS_VOICES = [
    'alloy', 'ash', 'ballad', 'coral', 'echo', 'fable', 'onyx',
    'nova', 'sage', 'shimmer', 'verse', 'marin', 'cedar',
];
let settingsAzureSpeechVoices = [];
let settingsEdgeTtsVoices = [];
let settingsElevenLabsVoices = [];
let settingsElevenLabsModels = [];
let settingsLocalAITtsVoices = [];
let settingsLocalAITtsModels = [];
let llmBackupProfiles = [];
const MAX_LLM_BACKUP_PROFILES = 100;
let engineSetupCatalog = [];
let activeEngineInstallPoll = null;

function getRemoteEngineManagementToken() {
    const inputValue = document.getElementById('remote-engine-management-token')?.value?.trim() || '';
    if (inputValue) return inputValue;
    try {
        return sessionStorage.getItem('ttsStoryRemoteAdminToken') || '';
    } catch (_) {
        return '';
    }
}

function engineManagementHeaders({ json = false } = {}) {
    const headers = {};
    if (json) headers['Content-Type'] = 'application/json';
    const token = getRemoteEngineManagementToken();
    if (token) headers['X-TTS-Story-Admin-Token'] = token;
    return headers;
}
let activeEngineManagementJobId = null;

document.addEventListener('DOMContentLoaded', async () => {
    await loadSettings();
    setupSettingsListeners();
    document.getElementById('breeze-q8-install')?.addEventListener('click', event => {
        const status = document.querySelector('#engine-panel-breeze-tts-2 .engine-setup-status');
        startEngineInstall('breeze_tts_2', status, event.currentTarget, 'q8');
    });
    await loadEngineSetupStatus();
    await initializeFirstRunWelcome();
});

function readyEngineIds() {
    return new Set(engineSetupCatalog.filter(engine => engine.ready).map(engine => engine.id));
}

function filterEngineSelectors() {
    const ready = readyEngineIds();
    ['job-tts-engine', 'settings-tts-engine'].forEach(id => {
        const select = document.getElementById(id);
        if (!select) return;
        Array.from(select.options).forEach(option => {
            if (!option.value) return;
            const managed = engineSetupCatalog.some(engine => engine.id === option.value);
            if (!managed) return;
            const available = ready.has(option.value);
            option.hidden = !available;
            option.disabled = !available;
        });
        if (!ready.has(select.value)) {
            const fallback = Array.from(select.options).find(option => option.value && !option.disabled);
            if (fallback) {
                select.value = fallback.value;
                if (id === 'job-tts-engine') select.dispatchEvent(new Event('change'));
            } else {
                let placeholder = select.querySelector('option[data-no-engines]');
                if (!placeholder) {
                    placeholder = document.createElement('option');
                    placeholder.value = '';
                    placeholder.dataset.noEngines = 'true';
                    placeholder.textContent = 'Configure a TTS engine in Settings';
                    select.prepend(placeholder);
                }
                placeholder.hidden = false;
                placeholder.disabled = false;
                select.value = '';
            }
        }
    });
    const generateButton = document.getElementById('generate-btn');
    if (generateButton) {
        generateButton.disabled = ready.size === 0;
        generateButton.title = ready.size ? '' : 'Install or configure a TTS engine in Settings first.';
    }
    window.availableTtsEngineIds = Array.from(ready);
}

function engineStatusForTab(tabName) {
    return engineSetupCatalog.filter(engine => engine.settings_tab === tabName);
}

function renderEngineSetupStatus() {
    const breezeStatus = engineSetupCatalog.find(engine => engine.id === 'breeze_tts_2');
    const breezeLicense = document.getElementById('breeze-tts-2-license-accept');
    if (breezeLicense && breezeStatus?.license_accepted) breezeLicense.checked = true;
    const q8Status = document.getElementById('breeze-q8-status');
    if (q8Status) q8Status.textContent = breezeStatus?.q8_ready
        ? 'Q8 installed. Choose Q8 GGUF above and save Settings to use it.'
        : 'Q8 is not installed. Use Install / Repair Q8 below.';
    document.querySelectorAll('.engine-tab-btn[data-engine-tab]').forEach(button => {
        const entries = engineStatusForTab(button.dataset.engineTab);
        button.classList.remove('engine-status-ready', 'engine-status-missing');
        if (!entries.length) return;
        button.classList.add(entries.every(engine => engine.ready)
            ? 'engine-status-ready'
            : 'engine-status-missing');
    });

    document.querySelectorAll('.engine-panel[id^="engine-panel-"]').forEach(panel => {
        const tabName = panel.id.replace('engine-panel-', '');
        const entries = engineStatusForTab(tabName);
        panel.querySelector('.engine-setup-status')?.remove();
        if (!entries.length) return;
        const ready = entries.every(engine => engine.ready);
        const installTarget = entries.find(engine => !engine.ready && engine.install_target)?.install_target;
        const uninstallEntry = entries.find(engine => engine.ready && engine.uninstall_target);
        const status = document.createElement('div');
        status.className = `engine-setup-status ${ready ? 'ready' : 'missing'}`;
        status.dataset.engineSetupTab = tabName;
        const text = document.createElement('div');
        text.className = 'engine-setup-status-text';
        text.innerHTML = ready
            ? '<strong>Ready</strong> — this engine is available on the Generate page.'
            : (installTarget
                ? '<strong>Not installed.</strong> Install this local engine to make it available.'
                : '<strong>Configuration required.</strong> Complete the required connection fields and save Settings.');
        status.appendChild(text);
        if (installTarget) {
            const installButton = document.createElement('button');
            installButton.type = 'button';
            installButton.className = 'btn btn-primary btn-sm';
            installButton.textContent = 'Install Engine';
            installButton.dataset.installEngine = installTarget;
            installButton.addEventListener('click', () => startEngineInstall(installTarget, status, installButton));
            status.appendChild(installButton);
        }
        if (ready && uninstallEntry) {
            const uninstallButton = document.createElement('button');
            uninstallButton.type = 'button';
            uninstallButton.className = 'btn btn-danger btn-sm';
            uninstallButton.textContent = 'Uninstall Engine';
            uninstallButton.dataset.uninstallEngine = uninstallEntry.uninstall_target;
            uninstallButton.addEventListener('click', () => startEngineUninstall(
                uninstallEntry,
                status,
                uninstallButton,
            ));
            status.appendChild(uninstallButton);
        }
        const title = panel.querySelector('.settings-panel-title');
        if (title) title.insertAdjacentElement('afterend', status);
        else panel.prepend(status);
    });
    filterEngineSelectors();
}

async function loadEngineSetupStatus() {
    try {
        const response = await fetch('/api/engines/status');
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to load engine status');
        engineSetupCatalog = Array.isArray(data.engines) ? data.engines : [];
        renderEngineSetupStatus();
        await restoreActiveEngineManagementJob();
    } catch (error) {
        console.error('Unable to load TTS engine setup status', error);
    }
}

function engineManagementUi(job) {
    const entry = engineSetupCatalog.find(engine =>
        engine.install_target === job.engine || engine.uninstall_target === job.engine
    );
    const tabName = entry?.settings_tab || '';
    const statusElement = tabName
        ? document.querySelector(`.engine-setup-status[data-engine-setup-tab="${CSS.escape(tabName)}"]`)
        : null;
    if (!statusElement) return null;
    let button = statusElement.querySelector(
        job.action === 'uninstall' ? '[data-uninstall-engine]' : '[data-install-engine]'
    );
    button ||= statusElement.querySelector('[data-install-engine], [data-uninstall-engine]');
    if (job.runtime === 'q8') button = document.getElementById('breeze-q8-install') || button;
    let output = statusElement.querySelector('.engine-install-output');
    if (!output) {
        output = document.createElement('pre');
        output.className = 'engine-install-output';
        statusElement.appendChild(output);
    }
    return { entry, tabName, statusElement, button, output };
}

function setEngineManagementBusy(job, busy = true) {
    document.querySelectorAll('[data-install-engine], [data-uninstall-engine], #breeze-q8-install').forEach(button => {
        button.disabled = busy;
        if (busy) button.title = 'Another engine installation or removal is currently running.';
        else button.removeAttribute('title');
    });
    document.querySelectorAll('.engine-tab-btn.engine-status-busy').forEach(button => {
        button.classList.remove('engine-status-busy');
    });
    document.querySelectorAll('.engine-setup-status.busy').forEach(status => {
        status.classList.remove('busy');
    });
    if (!busy || !job) return;
    const ui = engineManagementUi(job);
    if (!ui) return;
    ui.statusElement.classList.add('busy');
    const tabButton = document.querySelector(
        `.engine-tab-btn[data-engine-tab="${CSS.escape(ui.tabName)}"]`
    );
    tabButton?.classList.add('engine-status-busy');
    const text = ui.statusElement.querySelector('.engine-setup-status-text');
    const verb = job.action === 'uninstall' ? 'Removing' : 'Installing';
    if (text) {
        text.innerHTML = `<strong>${verb} ${ui.entry?.name || job.engine}…</strong> This operation continues if you leave Settings or refresh the page.`;
    }
    if (ui.button) {
        ui.button.disabled = true;
        ui.button.textContent = job.action === 'uninstall' ? 'Removing…' : 'Installing…';
        ui.button.title = `${verb} is currently in progress.`;
    }
}

async function restoreActiveEngineManagementJob() {
    try {
        const response = await fetch('/api/engines/jobs');
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to load engine operations');
        const activeJob = (data.jobs || []).find(job => job.status === 'running');
        if (!activeJob) {
            if (!activeEngineManagementJobId) setEngineManagementBusy(null, false);
            const restartJob = (data.jobs || []).find(job => {
                if (job.status !== 'complete' || job.action !== 'install' || !job.restart_required) return false;
                const entries = engineSetupCatalog.filter(entry =>
                    entry.install_target === job.engine || entry.uninstall_target === job.engine
                );
                return entries.length > 0 && entries.some(entry => !entry.ready);
            });
            if (restartJob) showBackendRestartRequired(restartJob);
            return;
        }
        const ui = engineManagementUi(activeJob);
        if (!ui) return;
        setEngineManagementBusy(activeJob, true);
        ui.output.textContent = activeJob.output || 'Preparing engine operation…';
        ui.output.scrollTop = ui.output.scrollHeight;
        if (activeEngineManagementJobId !== activeJob.id || !activeEngineInstallPoll) {
            pollEngineInstall(
                activeJob.id,
                ui.statusElement,
                ui.button,
                ui.output,
                activeJob.action || 'install',
                activeJob.engine || '',
            );
        }
    } catch (error) {
        console.error('Unable to restore active engine operation', error);
    }
}

function showBackendRestartRequired(job) {
    const ui = engineManagementUi(job);
    if (!ui) return;
    ui.statusElement.classList.remove('missing', 'busy');
    ui.statusElement.classList.add('ready');
    const text = ui.statusElement.querySelector('.engine-setup-status-text');
    if (text) {
        text.innerHTML = '<strong>Installed.</strong> Restart the TTS-Story backend to load this engine.';
    }
    if (job.output) {
        ui.output.textContent = job.output;
        ui.output.scrollTop = ui.output.scrollHeight;
    }
    const oldButton = ui.statusElement.querySelector('[data-install-engine], [data-uninstall-engine]');
    const restartButton = document.createElement('button');
    restartButton.type = 'button';
    restartButton.className = 'btn btn-primary btn-sm';
    restartButton.textContent = 'Restart TTS-Story';
    restartButton.dataset.restartBackend = 'true';
    restartButton.addEventListener('click', () => restartTtsStoryBackend(restartButton));
    if (oldButton) oldButton.replaceWith(restartButton);
    else ui.statusElement.insertBefore(restartButton, ui.output);
}

async function restartTtsStoryBackend(button) {
    if (!button || !confirm('Restart the TTS-Story backend now?')) return;
    const statusElement = button.closest('.engine-setup-status');
    const statusText = statusElement?.querySelector('.engine-setup-status-text');
    button.disabled = true;
    button.textContent = 'Restarting…';
    if (statusText) {
        statusText.innerHTML = '<strong>Restarting TTS-Story…</strong> Waiting for the backend to return.';
    }
    try {
        const response = await fetch('/api/system/restart', {
            method: 'POST',
            headers: engineManagementHeaders({ json: true }),
            body: '{}',
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to restart TTS-Story.');
        const previousInstance = data.instance_id || '';
        const deadline = Date.now() + 90000;
        while (Date.now() < deadline) {
            await new Promise(resolve => setTimeout(resolve, 750));
            try {
                const probe = await fetch(`/api/system/status?restart=${Date.now()}`, {
                    cache: 'no-store',
                });
                if (!probe.ok) continue;
                const current = await probe.json();
                if (current.success && current.instance_id && current.instance_id !== previousInstance) {
                    window.location.reload();
                    return;
                }
            } catch (_error) {
                // A refused request is expected while the backend is between processes.
            }
        }
        throw new Error('The backend did not return within 90 seconds. Check the TTS-Story terminal.');
    } catch (error) {
        button.disabled = false;
        button.textContent = 'Retry Restart';
        if (statusText) {
            statusText.innerHTML = `<strong>Restart failed.</strong> ${error.message || 'Check the TTS-Story terminal.'}`;
        }
    }
}

async function startEngineInstall(engine, statusElement, button, runtime = null) {
    if (!engine || !statusElement || !button) return;
    runtime ||= engine === 'breeze_tts_2'
        ? (document.getElementById('breeze-tts-2-runtime')?.value || 'pytorch') : 'pytorch';
    const licenseAccepted = engine === 'breeze_tts_2'
        ? Boolean(document.getElementById('breeze-tts-2-license-accept')?.checked)
        : undefined;
    if (engine === 'breeze_tts_2' && !licenseAccepted) {
        alert('Review and accept the BreezeBlue Research and Non-Commercial License before installing Breeze TTS 2.');
        return;
    }
    button.disabled = true;
    button.textContent = 'Starting...';
    let output = statusElement.querySelector('.engine-install-output');
    if (!output) {
        output = document.createElement('pre');
        output.className = 'engine-install-output';
        statusElement.appendChild(output);
    }
    output.textContent = 'Starting installer...';
    try {
        const response = await fetch('/api/engines/install', {
            method: 'POST',
            headers: engineManagementHeaders({ json: true }),
            body: JSON.stringify({ engine, license_accepted: licenseAccepted, runtime }),
        });
        const data = await response.json();
        if (response.status === 409 && data.job_id) {
            await restoreActiveEngineManagementJob();
            return;
        }
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to start installation');
        setEngineManagementBusy({ id: data.job_id, engine, action: 'install' }, true);
        pollEngineInstall(data.job_id, statusElement, button, output, 'install', engine);
    } catch (error) {
        button.disabled = false;
        button.textContent = 'Install Engine';
        output.textContent = error.message || 'Installation could not be started.';
    }
}

async function startEngineUninstall(engineEntry, statusElement, button) {
    const engine = engineEntry?.uninstall_target;
    if (!engine || !statusElement || !button) return;
    const warning = engineEntry.uninstall_warning
        || 'This removes the local engine runtime and downloaded models. Reinstalling later requires downloading them again.';
    if (!confirm(`${warning}\n\nDo you want to uninstall this engine?`)) return;
    button.disabled = true;
    button.textContent = 'Starting removal...';
    let output = statusElement.querySelector('.engine-install-output');
    if (!output) {
        output = document.createElement('pre');
        output.className = 'engine-install-output';
        statusElement.appendChild(output);
    }
    output.textContent = 'Preparing safe engine removal...';
    try {
        const response = await fetch('/api/engines/uninstall', {
            method: 'POST',
            headers: engineManagementHeaders({ json: true }),
            body: JSON.stringify({ engine }),
        });
        const data = await response.json();
        if (response.status === 409 && data.job_id) {
            await restoreActiveEngineManagementJob();
            return;
        }
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to start engine removal');
        setEngineManagementBusy({ id: data.job_id, engine, action: 'uninstall' }, true);
        pollEngineInstall(data.job_id, statusElement, button, output, 'uninstall', engine);
    } catch (error) {
        button.disabled = false;
        button.textContent = 'Uninstall Engine';
        output.textContent = error.message || 'Engine removal could not be started.';
    }
}

function pollEngineInstall(jobId, statusElement, button, output, action = 'install', engine = '') {
    if (activeEngineInstallPoll) clearTimeout(activeEngineInstallPoll);
    activeEngineManagementJobId = jobId;
    const poll = async () => {
        try {
            const response = await fetch(`/api/engines/jobs/${encodeURIComponent(jobId)}`);
            const data = await response.json();
            if (!response.ok || !data.success) throw new Error(data.error || 'Unable to read installation progress');
            const job = data.job || {};
            action = job.action || action;
            engine = job.engine || engine;
            const currentUi = engineManagementUi(job) || { statusElement, button, output };
            statusElement = currentUi.statusElement;
            button = currentUi.button || button;
            output = currentUi.output;
            setEngineManagementBusy(job, true);
            output.textContent = job.output || 'Installer is running...';
            output.scrollTop = output.scrollHeight;
            if (job.status === 'running') {
                button.textContent = action === 'uninstall' ? 'Removing...' : 'Installing...';
                activeEngineInstallPoll = setTimeout(poll, 1000);
                return;
            }
            activeEngineInstallPoll = null;
            activeEngineManagementJobId = null;
            setEngineManagementBusy(null, false);
            if (job.status === 'complete') {
                if (action === 'uninstall') {
                    engineSetupCatalog.forEach(entry => {
                        if (entry.uninstall_target === engine || entry.install_target === engine) {
                            entry.ready = false;
                            entry.action = 'install';
                            entry.uninstall_target = null;
                        }
                    });
                    renderEngineSetupStatus();
                    await loadHealthStatus();
                    alert('The engine runtime and its downloaded models were removed. Restart TTS-Story to finish unloading it. Your projects, generated audio, and saved voice samples were kept.');
                    return;
                }
                const settingsTab = statusElement.dataset.engineSetupTab || '';
                await loadEngineSetupStatus();
                await loadHealthStatus();
                const installedEntries = engineSetupCatalog.filter(entry =>
                    entry.install_target === engine || entry.uninstall_target === engine
                );
                if (installedEntries.length && installedEntries.every(entry => entry.ready)) {
                    return;
                }

                // A few legacy in-process engines cannot refresh their imported
                // availability flags until the backend restarts. Keep that case
                // explicit without forcing isolated engines such as Pocket TTS
                // to wait for a page refresh.
                showBackendRestartRequired({ ...job, settings_tab: settingsTab });
            } else {
                button.textContent = action === 'uninstall' ? 'Retry Removal' : 'Retry Install';
                button.disabled = false;
            }
        } catch (error) {
            output.textContent += `\n${error.message || 'Installation status temporarily unavailable.'}\nReconnecting…`;
            output.scrollTop = output.scrollHeight;
            activeEngineInstallPoll = setTimeout(poll, 2000);
        }
    };
    poll();
}

async function dismissFirstRunWelcome(openSettings = false) {
    try {
        await fetch('/api/onboarding', { method: 'POST' });
    } catch (error) {
        console.warn('Unable to save onboarding state', error);
    }
    document.getElementById('first-run-welcome-overlay')?.classList.add('hidden');
    document.getElementById('first-run-welcome-modal')?.classList.add('hidden');
    if (!openSettings) return;
    document.querySelector('.tab-button[data-tab="settings"]')?.click();
    document.getElementById('engine-settings-group')?.classList.remove('collapsed');
    const firstMissing = document.querySelector('.engine-tab-btn.engine-status-missing[data-engine-tab]');
    firstMissing?.click();
    document.getElementById('engine-settings-group')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

async function initializeFirstRunWelcome() {
    const overlay = document.getElementById('first-run-welcome-overlay');
    const modal = document.getElementById('first-run-welcome-modal');
    if (!overlay || !modal) return;
    document.getElementById('first-run-close-btn')?.addEventListener('click', () => dismissFirstRunWelcome(false));
    document.getElementById('first-run-settings-btn')?.addEventListener('click', () => dismissFirstRunWelcome(true));
    try {
        const response = await fetch('/api/onboarding');
        const data = await response.json();
        if (data.success && data.show_welcome) {
            overlay.classList.remove('hidden');
            modal.classList.remove('hidden');
        }
    } catch (error) {
        console.warn('Unable to load first-run welcome state', error);
    }
}

function updateLLMSettingsUI(provider = 'gemini') {
    const geminiCredentials = document.getElementById('gemini-credentials');
    const geminiModelGroup = document.getElementById('gemini-model-group');
    const geminiModelsActions = document.getElementById('gemini-models-actions');
    const atlasSettings = document.getElementById('llm-atlas-settings');
    const atlasModelsActions = document.getElementById('atlas-cloud-models-actions');
    const openRouterSettings = document.getElementById('llm-openrouter-settings');
    const openRouterModelsActions = document.getElementById('openrouter-models-actions');
    const localSettings = document.getElementById('llm-local-settings');
    const localModelsActions = document.getElementById('local-llm-models-actions');
    const geminiChunkGroup = document.getElementById('llm-gemini-chunk-group');
    const geminiChunkChaptersGroup = document.getElementById('llm-gemini-chunk-chapters-group');
    const localChunkGroup = document.getElementById('llm-local-chunk-group');
    const localChunkChaptersGroup = document.getElementById('llm-local-chunk-chapters-group');
    const nonGeminiTuning = document.getElementById('llm-non-gemini-tuning');

    const primaryProvider = (
        document.getElementById('llm-provider')?.value || provider || 'gemini'
    ).toLowerCase();
    const configuredProviders = new Set([
        primaryProvider,
        ...llmBackupProfiles.map(profile => (profile.provider || '').toLowerCase())
    ].filter(Boolean));
    const backupSection = document.getElementById('llm-backup-profiles-section');
    if (backupSection) backupSection.style.display = llmBackupProfiles.length ? '' : 'none';
    const isGemini = configuredProviders.has('gemini');
    const isAtlas = configuredProviders.has('atlas');
    const isOpenRouter = configuredProviders.has('openrouter');
    const isLocal = configuredProviders.has('local');
    if (geminiCredentials) geminiCredentials.style.display = isGemini ? '' : 'none';
    if (geminiModelGroup) geminiModelGroup.style.display = isGemini ? '' : 'none';
    if (geminiModelsActions) geminiModelsActions.style.display = isGemini ? '' : 'none';
    if (atlasSettings) atlasSettings.style.display = isAtlas ? '' : 'none';
    if (atlasModelsActions) atlasModelsActions.style.display = isAtlas ? '' : 'none';
    if (openRouterSettings) openRouterSettings.style.display = isOpenRouter ? '' : 'none';
    if (openRouterModelsActions) openRouterModelsActions.style.display = isOpenRouter ? '' : 'none';
    if (localSettings) localSettings.style.display = isLocal ? '' : 'none';
    if (localModelsActions) localModelsActions.style.display = isLocal ? '' : 'none';
    const primaryIsGemini = primaryProvider === 'gemini';
    if (geminiChunkGroup) geminiChunkGroup.style.display = primaryIsGemini ? '' : 'none';
    if (geminiChunkChaptersGroup) geminiChunkChaptersGroup.style.display = primaryIsGemini ? '' : 'none';
    if (localChunkGroup) localChunkGroup.style.display = primaryIsGemini ? 'none' : '';
    if (localChunkChaptersGroup) localChunkChaptersGroup.style.display = primaryIsGemini ? 'none' : '';
    if (nonGeminiTuning) nonGeminiTuning.style.display = configuredProviders.size === 1 && primaryIsGemini ? 'none' : '';
}

function createLLMBackupProfile(index) {
    const id = typeof crypto !== 'undefined' && crypto.randomUUID
        ? crypto.randomUUID()
        : `llm-backup-${Date.now()}-${index}`;
    return {
        id,
        name: `Backup ${index + 1}`,
        provider: 'openrouter',
        model: '',
        api_key: '',
        daily_request_limit: 18
    };
}

function normalizeLLMBackupProfile(profile, index) {
    const supportedProviders = new Set(['gemini', 'atlas', 'openrouter', 'local']);
    const provider = String(profile?.provider || 'openrouter').toLowerCase().trim();
    const rawDailyLimit = Number.parseInt(profile?.daily_request_limit, 10);
    return {
        id: String(profile?.id || createLLMBackupProfile(index).id),
        name: String(profile?.name || `Backup ${index + 1}`).trim() || `Backup ${index + 1}`,
        provider: supportedProviders.has(provider) ? provider : 'openrouter',
        model: String(profile?.model || '').trim(),
        api_key: String(profile?.api_key || '').trim(),
        daily_request_limit: Number.isFinite(rawDailyLimit) ? Math.max(0, rawDailyLimit) : 18
    };
}

function syncLLMBackupProfilesFromRows() {
    const rows = Array.from(document.querySelectorAll('[data-llm-backup-profile-index]'));
    rows.forEach(row => {
        const index = parseInt(row.dataset.llmBackupProfileIndex, 10);
        const profile = llmBackupProfiles[index];
        if (!profile) return;
        profile.name = row.querySelector('[data-profile-field="name"]')?.value?.trim() || `Backup ${index + 1}`;
        profile.provider = row.querySelector('[data-profile-field="provider"]')?.value || 'openrouter';
        profile.model = row.querySelector('[data-profile-field="model"]')?.value?.trim() || '';
        profile.api_key = row.querySelector('[data-profile-field="api_key"]')?.value?.trim() || '';
        const dailyLimit = Number.parseInt(row.querySelector('[data-profile-field="daily_request_limit"]')?.value, 10);
        profile.daily_request_limit = Number.isFinite(dailyLimit) ? Math.max(0, dailyLimit) : 18;
    });
}

function renderLLMBackupProfiles() {
    const list = document.getElementById('llm-backup-profiles-list');
    if (!list) return;
    list.innerHTML = llmBackupProfiles.map((profile, index) => `
        <div class="llm-backup-profile-card" data-llm-backup-profile-index="${index}">
            <div class="llm-backup-profile-heading">${index + 1}. ${escapeHtml(profile.name || `Backup ${index + 1}`)}</div>
            <div class="settings-form-grid">
                <div class="form-group">
                    <label>Profile Name</label>
                    <input type="text" data-profile-field="name" value="${escapeHtml(profile.name || '')}" placeholder="Backup ${index + 1}">
                </div>
                <div class="form-group">
                    <label>Provider</label>
                    <select data-profile-field="provider">
                        <option value="gemini" ${profile.provider === 'gemini' ? 'selected' : ''}>Gemini</option>
                        <option value="atlas" ${profile.provider === 'atlas' ? 'selected' : ''}>Atlas Cloud</option>
                        <option value="openrouter" ${profile.provider === 'openrouter' ? 'selected' : ''}>OpenRouter</option>
                        <option value="local" ${profile.provider === 'local' ? 'selected' : ''}>Local (LM Studio / Ollama)</option>
                    </select>
                </div>
                <div class="form-group">
                    <label>Model Override</label>
                    <input type="text" data-profile-field="model" list="llm-backup-model-suggestions" value="${escapeHtml(profile.model || '')}" placeholder="Blank uses provider default">
                </div>
                <div class="form-group">
                    <label>API Key Override</label>
                    <input type="password" data-profile-field="api_key" value="${escapeHtml(profile.api_key || '')}" placeholder="Blank uses provider API key above" autocomplete="off">
                </div>
                <div class="form-group">
                    <label>Daily Request Limit</label>
                    <input type="number" data-profile-field="daily_request_limit" min="0" max="1000000" step="1" value="${profile.daily_request_limit ?? 18}">
                    <small>Resets at midnight Pacific Time. Use 0 for unlimited requests.</small>
                </div>
            </div>
        </div>
    `).join('');
    list.querySelectorAll('input, select').forEach(control => {
        control.addEventListener('change', () => {
            syncLLMBackupProfilesFromRows();
            renderLLMModelSuggestions();
            updateLLMSettingsUI();
        });
        control.addEventListener('input', syncLLMBackupProfilesFromRows);
    });
    renderLLMModelSuggestions();
    updateLLMSettingsUI();
}

function resizeLLMBackupProfiles(rawCount) {
    syncLLMBackupProfilesFromRows();
    const count = Math.max(0, Math.min(
        MAX_LLM_BACKUP_PROFILES,
        parseInt(rawCount, 10) || 0
    ));
    while (llmBackupProfiles.length < count) {
        llmBackupProfiles.push(createLLMBackupProfile(llmBackupProfiles.length));
    }
    if (llmBackupProfiles.length > count) {
        llmBackupProfiles.length = count;
    }
    const countInput = document.getElementById('llm-backup-profile-count');
    if (countInput) countInput.value = String(count);
    renderLLMBackupProfiles();
}

function setLLMBackupProfiles(profiles) {
    llmBackupProfiles = (Array.isArray(profiles) ? profiles : [])
        .slice(0, MAX_LLM_BACKUP_PROFILES)
        .map(normalizeLLMBackupProfile);
    const countInput = document.getElementById('llm-backup-profile-count');
    if (countInput) countInput.value = String(llmBackupProfiles.length);
    renderLLMBackupProfiles();
}

function renderLLMModelSuggestions() {
    const datalist = document.getElementById('llm-backup-model-suggestions');
    if (!datalist) return;
    const modelIds = new Set();
    ['gemini-model', 'atlas-cloud-model', 'openrouter-model', 'llm-local-model'].forEach(id => {
        const control = document.getElementById(id);
        if (!control) return;
        if (control.tagName === 'SELECT') {
            Array.from(control.options).forEach(option => {
                if (option.value) modelIds.add(option.value);
            });
        } else if (control.value?.trim()) {
            modelIds.add(control.value.trim());
        }
    });
    datalist.innerHTML = Array.from(modelIds).sort().map(model => (
        `<option value="${escapeHtml(model)}"></option>`
    )).join('');
}

async function fetchAtlasCloudModels(buttonEl) {
    const apiKeyInput = document.getElementById('atlas-cloud-api-key');
    const baseUrlInput = document.getElementById('atlas-cloud-base-url');
    const timeoutInput = document.getElementById('atlas-cloud-timeout');
    const modelSelect = document.getElementById('atlas-cloud-model');
    const statusEl = document.getElementById('atlas-cloud-models-status');
    if (!apiKeyInput || !baseUrlInput || !modelSelect) return;

    const apiKey = apiKeyInput.value.trim();
    if (!apiKey) {
        if (statusEl) statusEl.textContent = 'Enter your Atlas Cloud API key first.';
        return;
    }

    const originalLabel = buttonEl ? buttonEl.textContent : '';
    if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.textContent = 'Fetching Atlas models...';
    }
    if (statusEl) statusEl.textContent = 'Contacting Atlas Cloud and its LLM catalog...';

    try {
        const response = await fetch('/api/atlas-cloud/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                api_key: apiKey,
                base_url: baseUrlInput.value.trim() || ATLAS_CLOUD_BASE_URL,
                model: modelSelect.value || 'deepseek-v3',
                timeout: parseInt(timeoutInput?.value, 10) || 30
            })
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Unable to fetch Atlas Cloud models');

        const models = data.models || [];
        if (!models.length) throw new Error('No Atlas Cloud LLM models were returned.');
        const previousValue = (modelSelect.value || '').trim();
        modelSelect.innerHTML = '';
        models.forEach(modelName => {
            const option = document.createElement('option');
            option.value = modelName;
            option.textContent = modelName;
            modelSelect.appendChild(option);
        });
        modelSelect.value = models.includes(previousValue) ? previousValue : models[0];
        if (statusEl) {
            const warning = (data.warnings || [])[0];
            statusEl.textContent = warning
                ? `Loaded ${models.length} Atlas LLM models. ${warning}`
                : `Loaded ${models.length} Atlas LLM models.`;
        }
    } catch (error) {
        console.error('Failed to fetch Atlas Cloud models:', error);
        if (statusEl) statusEl.textContent = error.message || 'Unable to fetch Atlas Cloud models.';
    } finally {
        if (buttonEl) {
            buttonEl.disabled = false;
            buttonEl.textContent = originalLabel || 'Fetch Atlas Models';
        }
        renderLLMModelSuggestions();
    }
}

async function fetchOpenRouterModels(buttonEl) {
    const apiKeyInput = document.getElementById('openrouter-api-key');
    const baseUrlInput = document.getElementById('openrouter-base-url');
    const timeoutInput = document.getElementById('openrouter-timeout');
    const modelSelect = document.getElementById('openrouter-model');
    const statusEl = document.getElementById('openrouter-models-status');
    if (!apiKeyInput || !baseUrlInput || !modelSelect) return;

    const apiKey = apiKeyInput.value.trim();
    if (!apiKey) {
        if (statusEl) statusEl.textContent = 'Enter your OpenRouter API key first.';
        return;
    }

    const originalLabel = buttonEl ? buttonEl.textContent : '';
    if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.textContent = 'Fetching OpenRouter models...';
    }
    if (statusEl) statusEl.textContent = 'Loading models available to this OpenRouter key...';

    try {
        const response = await fetch('/api/openrouter/models', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                api_key: apiKey,
                base_url: baseUrlInput.value.trim() || OPENROUTER_BASE_URL,
                model: modelSelect.value || 'openrouter/auto',
                timeout: parseInt(timeoutInput?.value, 10) || 30
            })
        });
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Unable to fetch OpenRouter models');

        const models = data.models || [];
        if (!models.length) throw new Error('No text-output OpenRouter models were returned.');
        const previousValue = (modelSelect.value || '').trim();
        modelSelect.innerHTML = '';
        models.forEach(modelName => {
            const option = document.createElement('option');
            option.value = modelName;
            option.textContent = modelName;
            modelSelect.appendChild(option);
        });
        modelSelect.value = models.includes(previousValue) ? previousValue : models[0];
        if (statusEl) statusEl.textContent = `Loaded ${models.length} OpenRouter models available to this key.`;
    } catch (error) {
        console.error('Failed to fetch OpenRouter models:', error);
        if (statusEl) statusEl.textContent = error.message || 'Unable to fetch OpenRouter models.';
    } finally {
        if (buttonEl) {
            buttonEl.disabled = false;
            buttonEl.textContent = originalLabel || 'Fetch OpenRouter Models';
        }
        renderLLMModelSuggestions();
    }
}

async function fetchLocalLlmModels(buttonEl) {
    const providerSelect = document.getElementById('llm-local-provider');
    const baseUrlInput = document.getElementById('llm-local-base-url');
    const apiKeyInput = document.getElementById('llm-local-api-key');
    const timeoutInput = document.getElementById('llm-local-timeout');
    const modelSelect = document.getElementById('llm-local-model');
    const statusEl = document.getElementById('local-llm-models-status');

    if (!providerSelect || !baseUrlInput || !modelSelect) return;

    const provider = providerSelect.value || 'lmstudio';
    const baseUrl = baseUrlInput.value.trim();
    const apiKey = apiKeyInput?.value?.trim() || '';
    const timeout = parseInt(timeoutInput?.value, 10) || 30;

    const originalLabel = buttonEl ? buttonEl.textContent : '';
    if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.textContent = 'Fetching local models...';
    }
    if (statusEl) {
        statusEl.textContent = 'Contacting local LLM server...';
    }

    try {
        const response = await fetch('/api/local-llm/models', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                provider,
                base_url: baseUrl,
                api_key: apiKey,
                timeout
            })
        });

        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Unable to fetch local models');
        }

        const models = data.models || [];
        if (!models.length) {
            throw new Error('No local models were returned. Verify the server is running.');
        }

        const previousValue = (modelSelect.value || '').trim();
        modelSelect.innerHTML = '';
        models.forEach(modelName => {
            const option = document.createElement('option');
            option.value = modelName;
            option.textContent = modelName;
            modelSelect.appendChild(option);
        });

        if (previousValue && models.includes(previousValue)) {
            modelSelect.value = previousValue;
        } else {
            modelSelect.value = models[0];
        }

        if (statusEl) {
            statusEl.textContent = `Loaded ${models.length} local models.`;
        }
    } catch (error) {
        console.error('Failed to fetch local LLM models:', error);
        if (statusEl) {
            statusEl.textContent = error.message || 'Unable to fetch local models.';
        }
    } finally {
        if (buttonEl) {
            buttonEl.disabled = false;
            buttonEl.textContent = originalLabel || 'Fetch Local Models';
        }
        renderLLMModelSuggestions();
    }
}

function setupLlmProviderHandlers() {
    const providerSelect = document.getElementById('llm-provider');
    const backupProfileCount = document.getElementById('llm-backup-profile-count');
    const localProviderSelect = document.getElementById('llm-local-provider');
    if (providerSelect) {
        providerSelect.addEventListener('change', () => updateLLMSettingsUI(providerSelect.value));
    }
    if (backupProfileCount) {
        backupProfileCount.addEventListener('change', () => resizeLLMBackupProfiles(backupProfileCount.value));
    }
    if (localProviderSelect) {
        localProviderSelect.addEventListener('change', () => {
            updateLocalProviderDefaults(localProviderSelect.value);
        });
    }
}

function updateLocalProviderDefaults(nextProvider) {
    const baseUrlInput = document.getElementById('llm-local-base-url');
    if (!baseUrlInput) return;
    const currentValue = baseUrlInput.value.trim();
    const fallback = LOCAL_LLM_BASE_URLS[nextProvider] || '';
    if (!currentValue || Object.values(LOCAL_LLM_BASE_URLS).includes(currentValue)) {
        baseUrlInput.value = fallback;
    }
}

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
        'kokoro_replicate': 'kokoro-replicate',
        'chatterbox_turbo_local': 'chatterbox-local',
        'chatterbox_turbo_replicate': 'chatterbox-replicate',
        'voxcpm_local': 'voxcpm',
        'pocket_tts': 'pocket-tts',
        'pocket_tts_preset': 'pocket-tts',
        'qwen3_custom': 'qwen3',
        'qwen3_clone': 'qwen3',
        'omnivoice_clone': 'omnivoice',
        'omnivoice_design': 'omnivoice',
        'kitten_tts': 'kitten-tts',
        'index_tts': 'index-tts',
        'dots_tts': 'dots-tts',
        'audio8_tts': 'audio8-tts',
        'breeze_tts_2': 'breeze-tts-2',
        'azure_speech': 'azure-speech',
        'edge_tts': 'edge-tts',
        'elevenlabs': 'elevenlabs',
        'openai_tts': 'openai-tts',
        'localai_tts': 'localai-tts'
    };
    
    const targetTab = engineTabMap[engineName];
    if (targetTab) {
        const tabBtn = document.querySelector(`.engine-tab-btn[data-engine-tab="${targetTab}"]`);
        if (tabBtn) {
            tabBtn.click();
        }
    }
}

function syncOmniVoicePerformancePreset() {
    const preset = document.getElementById('omnivoice-performance-preset');
    const stepsInput = document.getElementById('omnivoice-num-step');
    if (!preset || !stepsInput) return;
    const steps = parseInt(stepsInput.value, 10);
    preset.value = steps === 16
        ? 'fast'
        : steps === 32
            ? 'balanced'
            : steps === 48
                ? 'quality'
                : 'custom';
}

function setupOmniVoicePerformancePreset() {
    const preset = document.getElementById('omnivoice-performance-preset');
    const stepsInput = document.getElementById('omnivoice-num-step');
    if (!preset || !stepsInput) return;

    const presetSteps = { fast: 16, balanced: 32, quality: 48 };
    preset.addEventListener('change', () => {
        const steps = presetSteps[preset.value];
        if (steps) {
            stepsInput.value = String(steps);
            stepsInput.dispatchEvent(new Event('change', { bubbles: true }));
        }
    });
    stepsInput.addEventListener('input', syncOmniVoicePerformancePreset);
    syncOmniVoicePerformancePreset();
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

    document.getElementById('generate-remote-engine-management-token')?.addEventListener('click', () => {
        const bytes = new Uint8Array(32);
        crypto.getRandomValues(bytes);
        const token = Array.from(bytes, byte => byte.toString(16).padStart(2, '0')).join('');
        const input = document.getElementById('remote-engine-management-token');
        if (input) {
            input.value = token;
            input.type = 'text';
            input.select();
        }
    });

    const fetchGeminiModelsBtn = document.getElementById('fetch-gemini-models-btn');
    if (fetchGeminiModelsBtn) {
        fetchGeminiModelsBtn.addEventListener('click', () => fetchGeminiModels(fetchGeminiModelsBtn));
    }
    const fetchAtlasModelsBtn = document.getElementById('fetch-atlas-cloud-models-btn');
    if (fetchAtlasModelsBtn) {
        fetchAtlasModelsBtn.addEventListener('click', () => fetchAtlasCloudModels(fetchAtlasModelsBtn));
    }
    const fetchOpenRouterModelsBtn = document.getElementById('fetch-openrouter-models-btn');
    if (fetchOpenRouterModelsBtn) {
        fetchOpenRouterModelsBtn.addEventListener('click', () => fetchOpenRouterModels(fetchOpenRouterModelsBtn));
    }
    const fetchLocalModelsBtn = document.getElementById('fetch-local-llm-models-btn');
    if (fetchLocalModelsBtn) {
        fetchLocalModelsBtn.addEventListener('click', () => fetchLocalLlmModels(fetchLocalModelsBtn));
    }
    const fetchAzureVoicesBtn = document.getElementById('fetch-azure-speech-voices');
    if (fetchAzureVoicesBtn) {
        fetchAzureVoicesBtn.addEventListener('click', () => fetchAzureSpeechVoices(fetchAzureVoicesBtn));
    }
    const fetchEdgeVoicesBtn = document.getElementById('fetch-edge-tts-voices');
    if (fetchEdgeVoicesBtn) {
        fetchEdgeVoicesBtn.addEventListener('click', () => fetchEdgeTtsVoices(fetchEdgeVoicesBtn));
    }
    const fetchElevenLabsCatalogBtn = document.getElementById('fetch-elevenlabs-catalog');
    if (fetchElevenLabsCatalogBtn) {
        fetchElevenLabsCatalogBtn.addEventListener('click', () => fetchElevenLabsCatalog(fetchElevenLabsCatalogBtn));
    }
    const fetchLocalAITtsCatalogBtn = document.getElementById('fetch-localai-tts-catalog');
    if (fetchLocalAITtsCatalogBtn) {
        fetchLocalAITtsCatalogBtn.addEventListener('click', () => fetchLocalAITtsCatalog(fetchLocalAITtsCatalogBtn));
    }
    const localAITtsModel = document.getElementById('localai-tts-model');
    if (localAITtsModel) {
        localAITtsModel.addEventListener('change', () => fetchLocalAITtsCatalog());
    }
    const localAIConsent = document.getElementById('localai-tts-voice-profile-consent-confirmed');
    if (localAIConsent) {
        localAIConsent.addEventListener('change', () => fetchLocalAITtsCatalog());
    }
    const openAITtsCustomVoices = document.getElementById('openai-tts-custom-voices');
    if (openAITtsCustomVoices) {
        openAITtsCustomVoices.addEventListener('change', () => {
            populateOpenAITtsSettingsOptions({
                openai_tts_model: document.getElementById('openai-tts-custom-model')?.value?.trim()
                    || document.getElementById('openai-tts-model')?.value
                    || 'gpt-4o-mini-tts',
                openai_tts_default_voice: document.getElementById('openai-tts-default-voice')?.value || 'coral',
                openai_tts_custom_voices: openAITtsCustomVoices.value,
            });
        });
    }
    const azureDefaultVoice = document.getElementById('azure-speech-default-voice');
    if (azureDefaultVoice) {
        azureDefaultVoice.addEventListener('change', () => updateAzureDefaultExpressionOptions());
    }

    const pocketHuggingFaceVerifyButton = document.getElementById('pocket-tts-verify-huggingface-btn');
    if (pocketHuggingFaceVerifyButton) {
        pocketHuggingFaceVerifyButton.addEventListener('click', verifyPocketTtsHuggingFaceAccess);
    }

    const ttsEngineSelect = document.getElementById('settings-tts-engine');
    if (ttsEngineSelect) {
        ttsEngineSelect.addEventListener('change', (event) => {
            const engineName = (event.target.value || '').toLowerCase();
            toggleEngineSettingsSections(engineName);
            // Update the header mode indicator
            if (typeof updateModeIndicator === 'function') {
                updateModeIndicator(engineName);
            }
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
    setupSharedReplicateSettings();
    setupLlmProviderHandlers();
    setupOmniVoicePerformancePreset();
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
        renderLLMModelSuggestions();
    }
}

function populateAzureDefaultVoiceSelect(voices, preferredVoice = '') {
    const select = document.getElementById('azure-speech-default-voice');
    if (!select) return;
    const selected = preferredVoice || select.value || 'en-US-AvaMultilingualNeural';
    select.innerHTML = '';
    const groups = new Map();
    (voices || []).forEach(voice => {
        const localeLabel = voice.locale_name || voice.locale || 'Azure voices';
        if (!groups.has(localeLabel)) groups.set(localeLabel, []);
        groups.get(localeLabel).push(voice);
    });
    groups.forEach((entries, localeLabel) => {
        const group = document.createElement('optgroup');
        group.label = localeLabel;
        entries.forEach(voice => {
            const option = document.createElement('option');
            option.value = voice.short_name;
            option.textContent = `${voice.display_name || voice.short_name} · ${voice.gender || 'Unknown'} (${voice.short_name})`;
            group.appendChild(option);
        });
        select.appendChild(group);
    });
    if (!Array.from(select.options).some(option => option.value === selected)) {
        const option = document.createElement('option');
        option.value = selected;
        option.textContent = selected;
        select.insertBefore(option, select.firstChild);
    }
    select.value = selected;
    updateAzureDefaultExpressionOptions();
}

async function verifyPocketTtsHuggingFaceAccess() {
    const tokenInput = document.getElementById('pocket-tts-huggingface-token');
    const button = document.getElementById('pocket-tts-verify-huggingface-btn');
    const status = document.getElementById('pocket-tts-huggingface-status');
    if (!tokenInput || !button || !status) return;
    const token = tokenInput.value.trim();
    if (!token) {
        status.textContent = 'Enter a token before checking access.';
        status.style.color = 'var(--danger-color, #ef4444)';
        return;
    }
    button.disabled = true;
    button.textContent = 'Checking...';
    status.textContent = 'Contacting Hugging Face...';
    status.style.color = '';
    try {
        const response = await fetch('/api/pocket-tts/huggingface-access', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ token }),
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Access could not be verified.');
        status.textContent = data.message || 'Voice-cloning access confirmed.';
        status.style.color = 'var(--success-color, #34d399)';
    } catch (error) {
        status.textContent = error.message || 'Access could not be verified.';
        status.style.color = 'var(--danger-color, #ef4444)';
    } finally {
        button.disabled = false;
        button.textContent = 'Verify Voice-Cloning Access';
    }
}

function setupSharedReplicateSettings() {
    const keyInputs = [
        document.getElementById('kokoro-replicate-api-key'),
        document.getElementById('chatterbox-replicate-api-key'),
    ].filter(Boolean);
    const concurrencyInputs = [
        document.getElementById('kokoro-replicate-max-parallel'),
        document.getElementById('chatterbox-replicate-max-parallel'),
    ].filter(Boolean);
    const synchronize = (inputs, source) => {
        inputs.forEach(input => {
            if (input !== source) input.value = source.value;
        });
    };
    keyInputs.forEach(input => input.addEventListener('input', () => synchronize(keyInputs, input)));
    concurrencyInputs.forEach(input => input.addEventListener('input', () => synchronize(concurrencyInputs, input)));
}

function populateAzureExpressionSelect(select, values, emptyLabel, preferredValue = '') {
    if (!select) return;
    const selected = preferredValue || select.value || '';
    select.innerHTML = `<option value="">${emptyLabel}</option>`;
    (values || []).forEach(value => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
    });
    if (selected && !Array.from(select.options).some(option => option.value === selected)) {
        const option = document.createElement('option');
        option.value = selected;
        option.textContent = `${selected} (saved)`;
        select.appendChild(option);
    }
    select.value = selected;
}

function updateAzureDefaultExpressionOptions(preferredStyle, preferredRole) {
    const voiceName = document.getElementById('azure-speech-default-voice')?.value || '';
    const voice = settingsAzureSpeechVoices.find(entry => entry.short_name === voiceName);
    populateAzureExpressionSelect(
        document.getElementById('azure-speech-default-style'),
        voice?.styles || [],
        'Neutral / default',
        preferredStyle
    );
    populateAzureExpressionSelect(
        document.getElementById('azure-speech-default-role'),
        voice?.roles || [],
        'Default role',
        preferredRole
    );
}

async function fetchAzureSpeechVoices(buttonEl) {
    const status = document.getElementById('azure-speech-voices-status');
    const key = document.getElementById('azure-speech-key')?.value?.trim() || '';
    const region = document.getElementById('azure-speech-region')?.value?.trim() || '';
    if (!key || !region) {
        if (status) status.textContent = 'Enter both the resource key and region first.';
        return;
    }
    const originalLabel = buttonEl?.textContent;
    if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.textContent = 'Loading Azure voices…';
    }
    if (status) status.textContent = 'Connecting to Azure Speech…';
    try {
        const response = await fetch('/api/azure-speech/voices', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ key, region, force: true })
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to load Azure voices.');
        settingsAzureSpeechVoices = Array.isArray(data.voices) ? data.voices : [];
        populateAzureDefaultVoiceSelect(
            settingsAzureSpeechVoices,
            document.getElementById('azure-speech-default-voice')?.value || ''
        );
        if (status) status.textContent = `Connected. Loaded ${settingsAzureSpeechVoices.length} voices for ${data.region}.`;
    } catch (error) {
        if (status) status.textContent = error.message || 'Unable to load Azure voices.';
    } finally {
        if (buttonEl) {
            buttonEl.disabled = false;
            buttonEl.textContent = originalLabel || 'Test Connection & Load Voices';
        }
    }
}

function populateProviderVoiceSelect(selectId, voices, preferredVoice, fallbackVoice, providerLabel) {
    const select = document.getElementById(selectId);
    if (!select) return;
    const selected = preferredVoice || select.value || fallbackVoice || '';
    select.innerHTML = '';
    const groups = new Map();
    (voices || []).forEach(voice => {
        const locale = voice.locale_name || voice.locale || providerLabel;
        if (!groups.has(locale)) groups.set(locale, []);
        groups.get(locale).push(voice);
    });
    groups.forEach((entries, locale) => {
        const group = document.createElement('optgroup');
        group.label = locale;
        entries.forEach(voice => {
            const option = document.createElement('option');
            option.value = voice.short_name || voice.voice_id;
            const details = [voice.gender, voice.category].filter(Boolean).join(' · ');
            option.textContent = `${voice.display_name || option.value}${details ? ` · ${details}` : ''}`;
            group.appendChild(option);
        });
        select.appendChild(group);
    });
    if (selected && !Array.from(select.options).some(option => option.value === selected)) {
        const option = document.createElement('option');
        option.value = selected;
        option.textContent = selected;
        select.insertBefore(option, select.firstChild);
    }
    if (selected) select.value = selected;
}

function populateElevenLabsModelSelect(models, preferredModel = '') {
    const select = document.getElementById('elevenlabs-model');
    if (!select) return;
    const selected = preferredModel || select.value || 'eleven_multilingual_v2';
    select.innerHTML = '';
    (models || []).forEach(model => {
        const option = document.createElement('option');
        option.value = model.model_id;
        option.textContent = model.name || model.model_id;
        option.title = model.description || '';
        select.appendChild(option);
    });
    if (!Array.from(select.options).some(option => option.value === selected)) {
        const option = document.createElement('option');
        option.value = selected;
        option.textContent = selected;
        select.insertBefore(option, select.firstChild);
    }
    select.value = selected;
}

async function fetchEdgeTtsVoices(buttonEl, { force = true } = {}) {
    const status = document.getElementById('edge-tts-voices-status');
    const originalLabel = buttonEl?.textContent;
    if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.textContent = 'Loading Edge voices…';
    }
    if (status) status.textContent = 'Connecting to the Edge speech service…';
    try {
        const response = await fetch('/api/edge-tts/voices', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ force })
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to load Edge voices.');
        settingsEdgeTtsVoices = Array.isArray(data.voices) ? data.voices : [];
        populateProviderVoiceSelect(
            'edge-tts-default-voice',
            settingsEdgeTtsVoices,
            document.getElementById('edge-tts-default-voice')?.value,
            'en-US-AriaNeural',
            'Edge voices'
        );
        if (status) status.textContent = `Connected. Loaded ${settingsEdgeTtsVoices.length} voices.`;
        return data;
    } catch (error) {
        if (status) status.textContent = error.message || 'Unable to load Edge voices.';
        return null;
    } finally {
        if (buttonEl) {
            buttonEl.disabled = false;
            buttonEl.textContent = originalLabel || 'Test Connection & Load Voices';
        }
    }
}

async function fetchElevenLabsCatalog(buttonEl, { force = true } = {}) {
    const status = document.getElementById('elevenlabs-catalog-status');
    const usage = document.getElementById('elevenlabs-usage-status');
    const apiKey = document.getElementById('elevenlabs-api-key')?.value?.trim() || '';
    const baseUrl = document.getElementById('elevenlabs-base-url')?.value?.trim() || ELEVENLABS_BASE_URL;
    if (!apiKey) {
        if (status) status.textContent = 'Enter your ElevenLabs API key first.';
        return null;
    }
    const originalLabel = buttonEl?.textContent;
    if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.textContent = 'Loading ElevenLabs catalog…';
    }
    if (status) status.textContent = 'Connecting to ElevenLabs…';
    try {
        const response = await fetch('/api/elevenlabs/catalog', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ api_key: apiKey, base_url: baseUrl, force })
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to load ElevenLabs.');
        settingsElevenLabsVoices = Array.isArray(data.voices) ? data.voices : [];
        settingsElevenLabsModels = Array.isArray(data.models) ? data.models : [];
        populateElevenLabsModelSelect(
            settingsElevenLabsModels,
            document.getElementById('elevenlabs-model')?.value
        );
        populateProviderVoiceSelect(
            'elevenlabs-default-voice',
            settingsElevenLabsVoices,
            document.getElementById('elevenlabs-default-voice')?.value,
            'JBFqnCBsd6RMkjVDRZzb',
            'ElevenLabs voices'
        );
        if (status) {
            const warning = Array.isArray(data.warnings) ? data.warnings[0] : '';
            status.textContent = `Connected. Loaded ${settingsElevenLabsVoices.length} voices and ${settingsElevenLabsModels.length} TTS models.${warning ? ` ${warning}` : ''}`;
        }
        if (usage) {
            const subscription = data.subscription || {};
            const used = Number(subscription.character_count);
            const limit = Number(subscription.character_limit);
            usage.textContent = Number.isFinite(used) && Number.isFinite(limit)
                ? `Plan: ${subscription.tier || 'unknown'} · ${used.toLocaleString()} of ${limit.toLocaleString()} characters used.`
                : `Plan: ${subscription.tier || 'unknown'}`;
        }
        return data;
    } catch (error) {
        if (status) status.textContent = error.message || 'Unable to load ElevenLabs.';
        return null;
    } finally {
        if (buttonEl) {
            buttonEl.disabled = false;
            buttonEl.textContent = originalLabel || 'Test Connection & Load Catalog';
        }
    }
}

function populateLocalAITtsCatalog(settings = {}) {
    const modelSelect = document.getElementById('localai-tts-model');
    const voiceInput = document.getElementById('localai-tts-default-voice');
    const voiceOptions = document.getElementById('localai-tts-voice-options');
    const selectedModel = settings.localai_tts_model ?? modelSelect?.value ?? '';
    const selectedVoice = settings.localai_tts_default_voice ?? voiceInput?.value ?? '';
    if (modelSelect) {
        const entries = [...settingsLocalAITtsModels];
        if (selectedModel && !entries.some(model => (model.model_id || model.id) === selectedModel)) {
            entries.unshift({ model_id: selectedModel, name: `${selectedModel} (saved)` });
        }
        modelSelect.innerHTML = '';
        if (!entries.length) modelSelect.add(new Option('Load the LocalAI catalog first', ''));
        entries.forEach(model => modelSelect.add(new Option(
            model.name || model.model_id || model.id,
            model.model_id || model.id
        )));
        modelSelect.value = selectedModel || entries[0]?.model_id || entries[0]?.id || '';
    }
    if (voiceOptions) {
        voiceOptions.innerHTML = '';
        settingsLocalAITtsVoices.forEach(voice => {
            const id = voice.voice_id || voice.short_name;
            if (!id || voice.disabled) return;
            const option = document.createElement('option');
            option.value = id;
            option.label = `${voice.display_name || id}${voice.locale ? ` · ${voice.locale}` : ''}`;
            voiceOptions.appendChild(option);
        });
    }
    if (voiceInput) voiceInput.value = selectedVoice;
}

async function fetchLocalAITtsCatalog(buttonEl) {
    const status = document.getElementById('localai-tts-catalog-status');
    const originalLabel = buttonEl?.textContent;
    if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.textContent = 'Loading LocalAI catalog…';
    }
    if (status) status.textContent = 'Connecting to LocalAI…';
    try {
        const response = await fetch('/api/localai-tts/catalog', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                base_url: document.getElementById('localai-tts-base-url')?.value?.trim() || LOCALAI_TTS_BASE_URL,
                api_key: document.getElementById('localai-tts-api-key')?.value || '',
                timeout: parseInt(document.getElementById('localai-tts-timeout')?.value, 10) || 180,
                model: document.getElementById('localai-tts-model')?.value || '',
                consent_confirmed: Boolean(document.getElementById('localai-tts-voice-profile-consent-confirmed')?.checked),
            })
        });
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to load LocalAI.');
        settingsLocalAITtsModels = Array.isArray(data.models) ? data.models : [];
        settingsLocalAITtsVoices = Array.isArray(data.voices) ? data.voices : [];
        populateLocalAITtsCatalog({
            localai_tts_model: document.getElementById('localai-tts-model')?.value || data.configured_model || settingsLocalAITtsModels[0]?.model_id || '',
            localai_tts_default_voice: document.getElementById('localai-tts-default-voice')?.value || data.configured_voice || '',
        });
        if (status) {
            const cloning = data.selected_model_voice_cloning === true
                ? ` ${data.tts_story_voice_ready_count || 0} TTS-Story sample(s) ready for cloning.`
                : (data.selected_model_voice_cloning === false ? ' The selected model does not advertise voice cloning.' : ' Select a model and reload to check voice cloning.');
            const voiceNote = settingsLocalAITtsVoices.length
                ? ` Loaded ${settingsLocalAITtsVoices.length} voice suggestion(s).`
                : ' No saved voice profiles were advertised; freeform voice or speaker IDs can still be entered.';
            status.textContent = `Connected${data.version ? ` (${data.version})` : ''}. Loaded ${settingsLocalAITtsModels.length} TTS model(s).${voiceNote}${cloning}`;
        }
        return data;
    } catch (error) {
        if (status) status.textContent = error.message || 'Unable to load LocalAI.';
        return null;
    } finally {
        if (buttonEl) {
            buttonEl.disabled = false;
            buttonEl.textContent = originalLabel || 'Test Connection & Load Catalog';
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

function populateOpenAITtsSettingsOptions(settings) {
    const populate = (id, entries, selected) => {
        const select = document.getElementById(id);
        if (!select) return;
        const normalized = entries.map(entry => Array.isArray(entry) ? entry : [entry, entry]);
        if (selected && !normalized.some(([value]) => value === selected)) {
            normalized.push([selected, `${selected} (custom)`]);
        }
        select.innerHTML = '';
        normalized.forEach(([value, label]) => {
            const option = document.createElement('option');
            option.value = value;
            option.textContent = label;
            select.appendChild(option);
        });
        select.value = selected || normalized[0]?.[0] || '';
    };

    const customVoices = String(settings.openai_tts_custom_voices || '')
        .split(',')
        .map(value => value.trim())
        .filter(Boolean);
    populate(
        'openai-tts-model',
        OPENAI_TTS_MODELS,
        settings.openai_tts_model || 'gpt-4o-mini-tts'
    );
    setElementValue(
        'openai-tts-custom-model',
        OPENAI_TTS_MODELS.some(([value]) => value === settings.openai_tts_model)
            ? ''
            : (settings.openai_tts_model || '')
    );
    populate(
        'openai-tts-default-voice',
        [...new Set([...OPENAI_TTS_VOICES, ...customVoices])].map(value => [
            value,
            OPENAI_TTS_VOICES.includes(value)
                ? value.charAt(0).toUpperCase() + value.slice(1)
                : `${value} (custom)`,
        ]),
        settings.openai_tts_default_voice || 'coral'
    );
}

// Apply settings to UI
function applySettings(settings) {
    const remoteManagementEnabled = document.getElementById('remote-engine-management-enabled');
    if (remoteManagementEnabled) {
        remoteManagementEnabled.checked = Boolean(settings.remote_engine_management_enabled);
    }
    // Replicate-hosted TTS engines share one provider token and request limit.
    setElementValue('kokoro-replicate-api-key', settings.replicate_api_key || '');
    setElementValue('chatterbox-replicate-api-key', settings.replicate_api_key || '');
    setElementValue('kokoro-replicate-max-parallel', settings.replicate_max_parallel ?? settings.parallel_chunks ?? 3, 3);
    setElementValue('chatterbox-replicate-max-parallel', settings.replicate_max_parallel ?? settings.parallel_chunks ?? 3, 3);
    
    // Chunk size
    setElementValue('chunk-size', settings.chunk_size ?? 500, 500);
    setElementValue('kokoro-chunk-size', settings.kokoro_chunk_size ?? 500, 500);
    
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
    setElementValue('pause-marker-three-seconds', settings.pause_marker_three_seconds ?? 0.25, 0.25);
    setElementValue('pause-marker-six-seconds', settings.pause_marker_six_seconds ?? 0.5, 0.5);

    // Parallel processing
    setElementValue('parallel-chunks', settings.parallel_chunks ?? 3, 3);
    setCheckboxValue('group-chunks-by-speaker', settings.group_chunks_by_speaker ?? false, false);

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
    setElementValue('gemini-speaker-profile-prompt', settings.gemini_speaker_profile_prompt || '');
    setGeminiPresetState(settings.gemini_prompt_presets || []);

    // Local LLM settings
    const llmProvider = settings.llm_provider || 'gemini';
    setElementValue('llm-provider', llmProvider, 'gemini');
    setElementValue('atlas-cloud-api-key', settings.atlas_cloud_api_key || '');
    setElementValue('atlas-cloud-base-url', settings.atlas_cloud_base_url || ATLAS_CLOUD_BASE_URL, ATLAS_CLOUD_BASE_URL);
    setElementValue('atlas-cloud-timeout', settings.atlas_cloud_timeout ?? 120, 120);
    const atlasModelSelect = document.getElementById('atlas-cloud-model');
    const savedAtlasModel = settings.atlas_cloud_model || 'deepseek-v3';
    if (atlasModelSelect && savedAtlasModel) {
        const hasOption = Array.from(atlasModelSelect.options).some(option => option.value === savedAtlasModel);
        if (!hasOption) {
            const option = document.createElement('option');
            option.value = savedAtlasModel;
            option.textContent = savedAtlasModel;
            atlasModelSelect.appendChild(option);
        }
        atlasModelSelect.value = savedAtlasModel;
    }
    setElementValue('openrouter-api-key', settings.openrouter_api_key || '');
    setElementValue('openrouter-base-url', settings.openrouter_base_url || OPENROUTER_BASE_URL, OPENROUTER_BASE_URL);
    setElementValue('openrouter-timeout', settings.openrouter_timeout ?? 120, 120);
    const openRouterModelSelect = document.getElementById('openrouter-model');
    const savedOpenRouterModel = settings.openrouter_model || 'openrouter/auto';
    if (openRouterModelSelect && savedOpenRouterModel) {
        const hasOption = Array.from(openRouterModelSelect.options).some(option => option.value === savedOpenRouterModel);
        if (!hasOption) {
            const option = document.createElement('option');
            option.value = savedOpenRouterModel;
            option.textContent = savedOpenRouterModel;
            openRouterModelSelect.appendChild(option);
        }
        openRouterModelSelect.value = savedOpenRouterModel;
    }
    setElementValue('azure-speech-key', settings.azure_speech_key || '');
    setElementValue('azure-speech-region', settings.azure_speech_region || '');
    setElementValue('azure-speech-output-format', settings.azure_speech_output_format || 'riff-24khz-16bit-mono-pcm');
    setElementValue('azure-speech-timeout', settings.azure_speech_timeout ?? 60, 60);
    setElementValue('azure-speech-max-parallel', settings.azure_speech_max_parallel ?? 2, 2);
    setElementValue('azure-speech-requests-per-minute', settings.azure_speech_requests_per_minute ?? 20, 20);
    setElementValue('azure-speech-chunk-size', settings.azure_speech_chunk_size ?? 1000, 1000);
    setElementValue('azure-speech-default-style-degree', settings.azure_speech_default_style_degree ?? 1, 1);
    populateAzureDefaultVoiceSelect(
        settingsAzureSpeechVoices,
        settings.azure_speech_default_voice || 'en-US-AvaMultilingualNeural'
    );
    updateAzureDefaultExpressionOptions(
        settings.azure_speech_default_style || '',
        settings.azure_speech_default_role || ''
    );
    setElementValue('edge-tts-timeout', settings.edge_tts_timeout ?? 60, 60);
    setElementValue('edge-tts-max-parallel', settings.edge_tts_max_parallel ?? 2, 2);
    setElementValue('edge-tts-max-retries', settings.edge_tts_max_retries ?? 4, 4);
    setElementValue('edge-tts-chunk-size', settings.edge_tts_chunk_size ?? 1000, 1000);
    setElementValue('edge-tts-default-volume', settings.edge_tts_default_volume ?? 0, 0);
    populateProviderVoiceSelect(
        'edge-tts-default-voice',
        settingsEdgeTtsVoices,
        settings.edge_tts_default_voice || 'en-US-AriaNeural',
        'en-US-AriaNeural',
        'Edge voices'
    );
    setElementValue('elevenlabs-api-key', settings.elevenlabs_api_key || '');
    window.loadBreezeApiSettings?.(settings);
    setElementValue('elevenlabs-base-url', settings.elevenlabs_base_url || ELEVENLABS_BASE_URL, ELEVENLABS_BASE_URL);
    setElementValue('elevenlabs-output-format', settings.elevenlabs_output_format || 'mp3_44100_128');
    setElementValue('elevenlabs-timeout', settings.elevenlabs_timeout ?? 120, 120);
    setElementValue('elevenlabs-max-parallel', settings.elevenlabs_max_parallel ?? 2, 2);
    setElementValue('elevenlabs-chunk-size', settings.elevenlabs_chunk_size ?? 4000, 4000);
    setElementValue('elevenlabs-stability', settings.elevenlabs_stability ?? 0.5, 0.5);
    setElementValue('elevenlabs-similarity-boost', settings.elevenlabs_similarity_boost ?? 0.75, 0.75);
    setElementValue('elevenlabs-style', settings.elevenlabs_style ?? 0, 0);
    setCheckboxValue('elevenlabs-use-speaker-boost', settings.elevenlabs_use_speaker_boost ?? true, true);
    populateElevenLabsModelSelect(
        settingsElevenLabsModels,
        settings.elevenlabs_model || 'eleven_multilingual_v2'
    );
    populateProviderVoiceSelect(
        'elevenlabs-default-voice',
        settingsElevenLabsVoices,
        settings.elevenlabs_default_voice || 'JBFqnCBsd6RMkjVDRZzb',
        'JBFqnCBsd6RMkjVDRZzb',
        'ElevenLabs voices'
    );
    setElementValue('openai-tts-api-key', settings.openai_tts_api_key || '');
    setElementValue('openai-tts-base-url', settings.openai_tts_base_url || OPENAI_TTS_BASE_URL, OPENAI_TTS_BASE_URL);
    populateOpenAITtsSettingsOptions(settings);
    setElementValue('openai-tts-custom-voices', settings.openai_tts_custom_voices || '');
    setElementValue('openai-tts-instructions', settings.openai_tts_instructions || '');
    setElementValue('openai-tts-timeout', settings.openai_tts_timeout ?? 120, 120);
    setElementValue('openai-tts-max-parallel', settings.openai_tts_max_parallel ?? 2, 2);
    setElementValue('openai-tts-chunk-size', settings.openai_tts_chunk_size ?? 4000, 4000);
    setElementValue('localai-tts-api-key', settings.localai_tts_api_key || '');
    setElementValue('localai-tts-base-url', settings.localai_tts_base_url || LOCALAI_TTS_BASE_URL, LOCALAI_TTS_BASE_URL);
    populateLocalAITtsCatalog(settings);
    setElementValue('localai-tts-default-language', settings.localai_tts_default_language || '');
    setElementValue('localai-tts-instructions', settings.localai_tts_instructions || '');
    setElementValue('localai-tts-timeout', settings.localai_tts_timeout ?? 180, 180);
    setElementValue('localai-tts-max-parallel', settings.localai_tts_max_parallel ?? 1, 1);
    setElementValue('localai-tts-max-retries', settings.localai_tts_max_retries ?? 4, 4);
    setElementValue('localai-tts-chunk-size', settings.localai_tts_chunk_size ?? 1000, 1000);
    const localAIConsent = document.getElementById('localai-tts-voice-profile-consent-confirmed');
    if (localAIConsent) localAIConsent.checked = Boolean(settings.localai_tts_voice_profile_consent_confirmed);
    setElementValue('cloud-tts-concurrent-jobs', settings.cloud_tts_concurrent_jobs ?? 2, 2);
    setElementValue('llm-local-provider', settings.llm_local_provider || 'lmstudio', 'lmstudio');
    setElementValue('llm-local-base-url', settings.llm_local_base_url || LOCAL_LLM_BASE_URLS.lmstudio, LOCAL_LLM_BASE_URLS.lmstudio);
    setElementValue('llm-local-model', settings.llm_local_model || '');
    setElementValue('llm-local-api-key', settings.llm_local_api_key || '');
    setElementValue('llm-local-timeout', settings.llm_local_timeout ?? 120, 120);
    setElementValue('llm-local-temperature', settings.llm_local_temperature ?? 0.2, 0.2);
    setElementValue('llm-local-top-p', settings.llm_local_top_p ?? 1.0, 1.0);
    setElementValue('llm-local-top-k', settings.llm_local_top_k ?? 0, 0);
    setElementValue('llm-local-repeat-penalty', settings.llm_local_repeat_penalty ?? 1.0, 1.0);
    setElementValue('llm-local-max-tokens', settings.llm_local_max_tokens ?? 0, 0);
    setCheckboxValue('llm-local-disable-reasoning', settings.llm_local_disable_reasoning ?? false, false);
    setElementValue('llm-gemini-chunk-size', settings.llm_gemini_chunk_size ?? 500, 500);
    setElementValue('llm-local-chunk-size', settings.llm_local_chunk_size ?? 500, 500);
    setCheckboxValue('llm-gemini-chunk-chapters', settings.llm_gemini_chunk_chapters ?? true, true);
    setCheckboxValue('llm-local-chunk-chapters', settings.llm_local_chunk_chapters ?? true, true);
    setLLMBackupProfiles(settings.llm_backup_profiles || []);

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
    const voxcpmChunkSize = document.getElementById('voxcpm-chunk-size');
    if (voxcpmChunkSize) {
        voxcpmChunkSize.value = settings.voxcpm_chunk_size ?? 550;
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
    const qwen3ChunkSize = document.getElementById('qwen3-chunk-size');
    if (qwen3ChunkSize) {
        qwen3ChunkSize.value = settings.qwen3_chunk_size ?? 500;
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

    // OmniVoice settings
    const omnivoiceModelId = document.getElementById('omnivoice-model-id');
    if (omnivoiceModelId) {
        omnivoiceModelId.value = settings.omnivoice_clone_model_id || settings.omnivoice_design_model_id || 'k2-fsa/OmniVoice';
    }
    const omnivoiceChunkSize = document.getElementById('omnivoice-chunk-size');
    if (omnivoiceChunkSize) {
        omnivoiceChunkSize.value = settings.omnivoice_chunk_size ?? 500;
    }
    const omnivoiceDevice = document.getElementById('omnivoice-device');
    if (omnivoiceDevice) {
        omnivoiceDevice.value = settings.omnivoice_clone_device || settings.omnivoice_design_device || 'auto';
    }
    const omnivoiceDtype = document.getElementById('omnivoice-dtype');
    if (omnivoiceDtype) {
        omnivoiceDtype.value = settings.omnivoice_clone_dtype || settings.omnivoice_design_dtype || 'float16';
    }
    const omnivoiceNumStep = document.getElementById('omnivoice-num-step');
    if (omnivoiceNumStep) {
        omnivoiceNumStep.value = settings.omnivoice_clone_num_step || settings.omnivoice_design_num_step || 32;
    }
    syncOmniVoicePerformancePreset();
    const omnivoiceBatchSize = document.getElementById('omnivoice-batch-size');
    if (omnivoiceBatchSize) {
        omnivoiceBatchSize.value = settings.omnivoice_batch_size ?? 1;
    }
    const omnivoiceClonePrompt = document.getElementById('omnivoice-clone-prompt');
    if (omnivoiceClonePrompt) {
        omnivoiceClonePrompt.value = settings.omnivoice_clone_default_prompt || '';
    }
    const omnivoiceClonePromptText = document.getElementById('omnivoice-clone-prompt-text');
    if (omnivoiceClonePromptText) {
        omnivoiceClonePromptText.value = settings.omnivoice_clone_default_prompt_text || '';
    }
    const omnivoiceDesignInstruct = document.getElementById('omnivoice-design-instruct');
    if (omnivoiceDesignInstruct) {
        omnivoiceDesignInstruct.value = settings.omnivoice_design_default_instruct || '';
    }
    const omnivoicePostProcess = document.getElementById('omnivoice-post-process');
    if (omnivoicePostProcess) {
        omnivoicePostProcess.checked = settings.omnivoice_post_process !== false;
    }
    const omnivoiceDurationSafetyMargin = document.getElementById('omnivoice-duration-safety-margin');
    if (omnivoiceDurationSafetyMargin) {
        omnivoiceDurationSafetyMargin.value = settings.omnivoice_duration_safety_margin ?? 0.25;
    }

    // Pocket TTS settings
    const pocketVariant = document.getElementById('pocket-tts-model-variant');
    if (pocketVariant) {
        pocketVariant.value = settings.pocket_tts_model_variant || 'b6369a24';
    }
    setElementValue('pocket-tts-huggingface-token', settings.huggingface_token || '');
    const pocketChunkSize = document.getElementById('pocket-tts-chunk-size');
    if (pocketChunkSize) {
        pocketChunkSize.value = settings.pocket_tts_chunk_size ?? 450;
    }
    const pocketTemp = document.getElementById('pocket-tts-temp');
    if (pocketTemp) {
        pocketTemp.value = settings.pocket_tts_temp ?? 0.7;
    }
    const pocketSteps = document.getElementById('pocket-tts-steps');
    if (pocketSteps) {
        pocketSteps.value = settings.pocket_tts_lsd_decode_steps ?? 1;
    }
    const pocketNoise = document.getElementById('pocket-tts-noise-clamp');
    if (pocketNoise) {
        pocketNoise.value = settings.pocket_tts_noise_clamp ?? '';
    }
    const pocketEos = document.getElementById('pocket-tts-eos');
    if (pocketEos) {
        pocketEos.value = settings.pocket_tts_eos_threshold ?? -4.0;
    }
    const pocketPrompt = document.getElementById('pocket-tts-default-prompt');
    if (pocketPrompt) {
        pocketPrompt.value = settings.pocket_tts_default_prompt || '';
    }
    const pocketTruncate = document.getElementById('pocket-tts-prompt-truncate');
    if (pocketTruncate) {
        pocketTruncate.checked = settings.pocket_tts_prompt_truncate === true;
    }
    const pocketThreads = document.getElementById('pocket-tts-num-threads');
    if (pocketThreads) {
        pocketThreads.value = settings.pocket_tts_num_threads ?? '';
    }
    const pocketInterop = document.getElementById('pocket-tts-interop-threads');
    if (pocketInterop) {
        pocketInterop.value = settings.pocket_tts_interop_threads ?? '';
    }

    // KittenTTS settings
    const kittenModelId = document.getElementById('kitten-tts-model-id');
    if (kittenModelId) {
        kittenModelId.value = settings.kitten_tts_model_id || 'KittenML/kitten-tts-mini-0.8';
    }
    const kittenVoice = document.getElementById('kitten-tts-default-voice');
    if (kittenVoice) {
        kittenVoice.value = settings.kitten_tts_default_voice || 'Jasper';
    }
    const kittenChunkSize = document.getElementById('kitten-tts-chunk-size');
    if (kittenChunkSize) {
        kittenChunkSize.value = settings.kitten_tts_chunk_size ?? 300;
    }

    // IndexTTS settings
    const indexModelVersion = document.getElementById('index-tts-model-version');
    if (indexModelVersion) {
        indexModelVersion.value = settings.index_tts_model_version || 'IndexTTS-2';
    }
    const indexChunkSize = document.getElementById('index-tts-chunk-size');
    if (indexChunkSize) {
        indexChunkSize.value = settings.index_tts_chunk_size ?? 400;
    }
    const indexDevice = document.getElementById('index-tts-device');
    if (indexDevice) {
        indexDevice.value = settings.index_tts_device || 'auto';
    }
    const indexDefaultPrompt = document.getElementById('index-tts-default-prompt');
    if (indexDefaultPrompt) {
        indexDefaultPrompt.value = settings.index_tts_default_prompt || '';
    }
    const indexUseFp16 = document.getElementById('index-tts-use-fp16');
    if (indexUseFp16) {
        indexUseFp16.checked = settings.index_tts_use_fp16 !== false;
    }
    const indexUseDeepspeed = document.getElementById('index-tts-use-deepspeed');
    if (indexUseDeepspeed) {
        indexUseDeepspeed.checked = settings.index_tts_use_deepspeed === true;
    }
    const indexUseTorchCompile = document.getElementById('index-tts-use-torch-compile');
    if (indexUseTorchCompile) {
        indexUseTorchCompile.checked = settings.index_tts_use_torch_compile === true;
    }
    const indexUseAccel = document.getElementById('index-tts-use-accel');
    if (indexUseAccel) {
        indexUseAccel.checked = settings.index_tts_use_accel === true;
    }
    const indexNumBeams = document.getElementById('index-tts-num-beams');
    if (indexNumBeams) {
        indexNumBeams.value = settings.index_tts_num_beams ?? 1;
    }
    const indexDiffusionSteps = document.getElementById('index-tts-diffusion-steps');
    if (indexDiffusionSteps) {
        indexDiffusionSteps.value = settings.index_tts_diffusion_steps ?? 25;
    }
    const indexTemperature = document.getElementById('index-tts-temperature');
    if (indexTemperature) {
        indexTemperature.value = settings.index_tts_temperature ?? 0.8;
    }
    const indexTopP = document.getElementById('index-tts-top-p');
    if (indexTopP) {
        indexTopP.value = settings.index_tts_top_p ?? 0.8;
    }
    const indexTopK = document.getElementById('index-tts-top-k');
    if (indexTopK) {
        indexTopK.value = settings.index_tts_top_k ?? 30;
    }
    const indexRepetitionPenalty = document.getElementById('index-tts-repetition-penalty');
    if (indexRepetitionPenalty) {
        indexRepetitionPenalty.value = settings.index_tts_repetition_penalty ?? 10.0;
    }
    const indexMaxMelTokens = document.getElementById('index-tts-max-mel-tokens');
    if (indexMaxMelTokens) {
        indexMaxMelTokens.value = settings.index_tts_max_mel_tokens ?? 1500;
    }
    const indexMaxTextTokens = document.getElementById('index-tts-max-text-tokens-per-segment');
    if (indexMaxTextTokens) {
        indexMaxTextTokens.value = settings.index_tts_max_text_tokens_per_segment ?? 120;
    }

    // Dot.TTS settings
    const dotsModelId = document.getElementById('dots-tts-model-id');
    if (dotsModelId) {
        dotsModelId.value = settings.dots_tts_model_id || 'rednote-hilab/dots.tts-soar';
    }
    const dotsChunkSize = document.getElementById('dots-tts-chunk-size');
    if (dotsChunkSize) {
        dotsChunkSize.value = settings.dots_tts_chunk_size ?? 250;
    }
    const dotsDevice = document.getElementById('dots-tts-device');
    if (dotsDevice) {
        dotsDevice.value = settings.dots_tts_device || 'auto';
    }
    const dotsPrecision = document.getElementById('dots-tts-precision');
    if (dotsPrecision) {
        dotsPrecision.value = settings.dots_tts_precision || 'auto';
    }
    const dotsPrompt = document.getElementById('dots-tts-default-prompt');
    if (dotsPrompt) {
        dotsPrompt.value = settings.dots_tts_default_prompt || '';
    }
    const dotsPromptText = document.getElementById('dots-tts-default-prompt-text');
    if (dotsPromptText) {
        dotsPromptText.value = settings.dots_tts_default_prompt_text || '';
    }
    const dotsNumSteps = document.getElementById('dots-tts-num-steps');
    if (dotsNumSteps) {
        dotsNumSteps.value = settings.dots_tts_num_steps ?? 10;
    }
    const dotsGuidance = document.getElementById('dots-tts-guidance-scale');
    if (dotsGuidance) {
        dotsGuidance.value = settings.dots_tts_guidance_scale ?? 1.2;
    }
    const dotsSpeakerScale = document.getElementById('dots-tts-speaker-scale');
    if (dotsSpeakerScale) {
        dotsSpeakerScale.value = settings.dots_tts_speaker_scale ?? 1.5;
    }
    const dotsSeed = document.getElementById('dots-tts-seed');
    if (dotsSeed) {
        dotsSeed.value = settings.dots_tts_seed ?? 42;
    }
    const dotsLanguage = document.getElementById('dots-tts-language');
    if (dotsLanguage) {
        dotsLanguage.value = settings.dots_tts_language || 'none';
    }
    const dotsNormalize = document.getElementById('dots-tts-normalize-text');
    if (dotsNormalize) {
        dotsNormalize.checked = settings.dots_tts_normalize_text === true;
    }
    const dotsOptimize = document.getElementById('dots-tts-optimize');
    if (dotsOptimize) {
        dotsOptimize.checked = settings.dots_tts_optimize === true;
    }
    const dotsAllowXvector = document.getElementById('dots-tts-allow-xvector-only');
    if (dotsAllowXvector) {
        dotsAllowXvector.checked = settings.dots_tts_allow_xvector_only === true;
    }

    const audio8Values = {
        'audio8-tts-model-id': settings.audio8_tts_model_id || 'Audio8/Audio8-TTS-Preview-0.6b',
        'audio8-tts-device': settings.audio8_tts_device || 'auto',
        'audio8-tts-dtype': settings.audio8_tts_dtype || 'auto',
        'audio8-tts-temperature': settings.audio8_tts_temperature ?? 0.8,
        'audio8-tts-top-p': settings.audio8_tts_top_p ?? 0.95,
        'audio8-tts-top-k': settings.audio8_tts_top_k ?? 50,
        'audio8-tts-max-new-tokens': settings.audio8_tts_max_new_tokens ?? 1024,
        'audio8-tts-retry-max-new-tokens': settings.audio8_tts_retry_max_new_tokens ?? 2000,
        'audio8-tts-seed': settings.audio8_tts_seed ?? 42,
        'audio8-tts-default-prompt': settings.audio8_tts_default_prompt || '',
        'audio8-tts-default-prompt-text': settings.audio8_tts_default_prompt_text || '',
        'audio8-tts-chunk-size': settings.audio8_tts_chunk_size ?? 140,
        'audio8-tts-hard-chunk-size': settings.audio8_tts_hard_chunk_size ?? 400,
    };
    Object.entries(audio8Values).forEach(([id, value]) => {
        const input = document.getElementById(id);
        if (input) input.value = value;
    });
    const breezeValues = {
        'breeze-tts-2-model-id': settings.breeze_tts_2_model_id || 'BreezeBlue/Breeze-TTS-2',
        'breeze-tts-2-runtime': settings.breeze_tts_2_runtime || 'pytorch',
        'breeze-tts-2-device': settings.breeze_tts_2_device || 'auto',
        'breeze-tts-2-seed': settings.breeze_tts_2_seed ?? 42,
        'breeze-tts-2-clone-cfg': settings.breeze_tts_2_clone_cfg_scale ?? 1,
        'breeze-tts-2-design-cfg': settings.breeze_tts_2_design_cfg_scale ?? 4,
        'breeze-tts-2-direction-cfg': settings.breeze_tts_2_direction_cfg_scale ?? 4,
        'breeze-tts-2-max-new-tokens': settings.breeze_tts_2_max_new_tokens ?? 1500,
        'breeze-tts-2-max-seq-len': settings.breeze_tts_2_max_seq_len ?? 2048,
        'breeze-tts-2-default-prompt': settings.breeze_tts_2_default_prompt || '',
        'breeze-tts-2-default-prompt-text': settings.breeze_tts_2_default_prompt_text || '',
        'breeze-tts-2-default-instruction': settings.breeze_tts_2_default_instruction || 'Speak clearly and naturally.',
        'breeze-tts-2-chunk-size': settings.breeze_tts_2_chunk_size ?? 500,
    };
    Object.entries(breezeValues).forEach(([id, value]) => {
        const input = document.getElementById(id);
        if (input) input.value = value;
    });
    const breezeFastMode = document.getElementById('breeze-tts-2-fast-mode');
    if (breezeFastMode) breezeFastMode.checked = settings.breeze_tts_2_fast_mode === true;

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

    const parseSilenceInput = (inputId) => {
        const rawValue = document.getElementById(inputId)?.value?.trim() || '';
        const parsed = parseFloat(rawValue);
        if (!Number.isFinite(parsed)) {
            return 0;
        }
        if (parsed <= 20) {
            return Math.round(parsed * 1000);
        }
        return Math.round(parsed);
    };
    const parseClampedFloat = (inputId, fallback, minimum = 0, maximum = 1) => {
        const parsed = parseFloat(document.getElementById(inputId)?.value);
        const value = Number.isFinite(parsed) ? parsed : fallback;
        return Math.max(minimum, Math.min(maximum, value));
    };

    const kokoroReplicateKeyEl = document.getElementById('kokoro-replicate-api-key')
        || document.getElementById('chatterbox-replicate-api-key');
    syncLLMBackupProfilesFromRows();
    const settings = {
        replicate_api_key: kokoroReplicateKeyEl ? kokoroReplicateKeyEl.value : '',
        chunk_size: parseInt(document.getElementById('chunk-size').value),
        kokoro_chunk_size: parseInt(document.getElementById('kokoro-chunk-size')?.value, 10) || 500,
        speed: parseFloat(document.getElementById('speed').value),
        output_format: defaultFormat,
        crossfade_duration: parseFloat(document.getElementById('crossfade').value),
        intro_silence_ms: parseSilenceInput('intro-silence'),
        inter_chunk_silence_ms: parseSilenceInput('inter-silence'),
        pause_marker_three_seconds: parseClampedFloat('pause-marker-three-seconds', 0.25, 0, 30),
        pause_marker_six_seconds: parseClampedFloat('pause-marker-six-seconds', 0.5, 0, 30),
        replicate_max_parallel: Math.min(8, Math.max(1, parseInt(
            document.getElementById('kokoro-replicate-max-parallel')?.value
            || document.getElementById('chatterbox-replicate-max-parallel')?.value,
            10
        ) || 3)),
        parallel_chunks: Math.min(8, Math.max(1, parseInt(
            document.getElementById('parallel-chunks')?.value,
            10
        ) || 3)),
        group_chunks_by_speaker: document.getElementById('group-chunks-by-speaker')?.checked ?? false,
        cleanup_vram_after_job: document.getElementById('cleanup-vram-after-job')?.checked ?? false,
        remote_engine_management_enabled: Boolean(document.getElementById('remote-engine-management-enabled')?.checked),
        remote_engine_management_token: document.getElementById('remote-engine-management-token')?.value?.trim() || '',
        gemini_api_key: document.getElementById('gemini-api-key').value,
        gemini_model: document.getElementById('gemini-model').value,
        gemini_prompt: document.getElementById('gemini-prompt').value,
        gemini_speaker_profile_prompt: document.getElementById('gemini-speaker-profile-prompt')?.value || '',
        gemini_prompt_presets: geminiPresetState.list.map(preset => ({ ...preset })),
        llm_provider: document.getElementById('llm-provider')?.value || 'gemini',
        llm_backup_profiles: llmBackupProfiles.map(profile => ({ ...profile })),
        atlas_cloud_api_key: document.getElementById('atlas-cloud-api-key')?.value || '',
        atlas_cloud_base_url: document.getElementById('atlas-cloud-base-url')?.value || ATLAS_CLOUD_BASE_URL,
        atlas_cloud_model: document.getElementById('atlas-cloud-model')?.value || 'deepseek-v3',
        atlas_cloud_timeout: parseInt(document.getElementById('atlas-cloud-timeout')?.value, 10) || 120,
        openrouter_api_key: document.getElementById('openrouter-api-key')?.value || '',
        openrouter_base_url: document.getElementById('openrouter-base-url')?.value || OPENROUTER_BASE_URL,
        openrouter_model: document.getElementById('openrouter-model')?.value || 'openrouter/auto',
        openrouter_timeout: parseInt(document.getElementById('openrouter-timeout')?.value, 10) || 120,
        azure_speech_key: document.getElementById('azure-speech-key')?.value || '',
        azure_speech_region: document.getElementById('azure-speech-region')?.value?.trim().toLowerCase() || '',
        azure_speech_default_voice: document.getElementById('azure-speech-default-voice')?.value || 'en-US-AvaMultilingualNeural',
        azure_speech_output_format: document.getElementById('azure-speech-output-format')?.value || 'riff-24khz-16bit-mono-pcm',
        azure_speech_timeout: Math.max(10, parseInt(document.getElementById('azure-speech-timeout')?.value, 10) || 60),
        azure_speech_max_parallel: Math.max(1, Math.min(8, parseInt(document.getElementById('azure-speech-max-parallel')?.value, 10) || 2)),
        azure_speech_requests_per_minute: Math.max(0, parseInt(document.getElementById('azure-speech-requests-per-minute')?.value, 10) || 0),
        azure_speech_chunk_size: Math.max(100, parseInt(document.getElementById('azure-speech-chunk-size')?.value, 10) || 1000),
        azure_speech_default_style: document.getElementById('azure-speech-default-style')?.value || '',
        azure_speech_default_role: document.getElementById('azure-speech-default-role')?.value || '',
        azure_speech_default_style_degree: Math.max(0.01, Math.min(2, parseFloat(document.getElementById('azure-speech-default-style-degree')?.value) || 1)),
        edge_tts_default_voice: document.getElementById('edge-tts-default-voice')?.value || 'en-US-AriaNeural',
        edge_tts_timeout: Math.max(10, Math.min(300, parseInt(document.getElementById('edge-tts-timeout')?.value, 10) || 60)),
        edge_tts_max_parallel: Math.max(1, Math.min(8, parseInt(document.getElementById('edge-tts-max-parallel')?.value, 10) || 2)),
        edge_tts_max_retries: Math.max(0, Math.min(6, parseInt(document.getElementById('edge-tts-max-retries')?.value, 10) || 0)),
        edge_tts_chunk_size: Math.max(100, Math.min(5000, parseInt(document.getElementById('edge-tts-chunk-size')?.value, 10) || 1000)),
        edge_tts_default_volume: Math.max(-100, Math.min(100, parseInt(document.getElementById('edge-tts-default-volume')?.value, 10) || 0)),
        elevenlabs_api_key: document.getElementById('elevenlabs-api-key')?.value || '',
        ...window.collectBreezeApiSettings?.(),
        elevenlabs_base_url: document.getElementById('elevenlabs-base-url')?.value?.trim() || ELEVENLABS_BASE_URL,
        elevenlabs_model: document.getElementById('elevenlabs-model')?.value || 'eleven_multilingual_v2',
        elevenlabs_default_voice: document.getElementById('elevenlabs-default-voice')?.value || 'JBFqnCBsd6RMkjVDRZzb',
        elevenlabs_output_format: document.getElementById('elevenlabs-output-format')?.value || 'mp3_44100_128',
        elevenlabs_timeout: Math.max(10, Math.min(600, parseInt(document.getElementById('elevenlabs-timeout')?.value, 10) || 120)),
        elevenlabs_max_parallel: Math.max(1, Math.min(8, parseInt(document.getElementById('elevenlabs-max-parallel')?.value, 10) || 2)),
        elevenlabs_chunk_size: Math.max(100, Math.min(10000, parseInt(document.getElementById('elevenlabs-chunk-size')?.value, 10) || 4000)),
        elevenlabs_stability: parseClampedFloat('elevenlabs-stability', 0.5),
        elevenlabs_similarity_boost: parseClampedFloat('elevenlabs-similarity-boost', 0.75),
        elevenlabs_style: parseClampedFloat('elevenlabs-style', 0),
        elevenlabs_use_speaker_boost: document.getElementById('elevenlabs-use-speaker-boost')?.checked ?? true,
        openai_tts_api_key: document.getElementById('openai-tts-api-key')?.value || '',
        openai_tts_base_url: document.getElementById('openai-tts-base-url')?.value?.trim() || OPENAI_TTS_BASE_URL,
        openai_tts_model: document.getElementById('openai-tts-custom-model')?.value?.trim()
            || document.getElementById('openai-tts-model')?.value?.trim()
            || 'gpt-4o-mini-tts',
        openai_tts_default_voice: document.getElementById('openai-tts-default-voice')?.value?.trim() || 'coral',
        openai_tts_custom_voices: document.getElementById('openai-tts-custom-voices')?.value?.trim() || '',
        openai_tts_instructions: document.getElementById('openai-tts-instructions')?.value?.trim() || '',
        openai_tts_timeout: Math.max(10, Math.min(600, parseInt(document.getElementById('openai-tts-timeout')?.value, 10) || 120)),
        openai_tts_max_parallel: Math.max(1, Math.min(8, parseInt(document.getElementById('openai-tts-max-parallel')?.value, 10) || 2)),
        openai_tts_chunk_size: Math.max(100, Math.min(4000, parseInt(document.getElementById('openai-tts-chunk-size')?.value, 10) || 4000)),
        localai_tts_api_key: document.getElementById('localai-tts-api-key')?.value || '',
        localai_tts_base_url: document.getElementById('localai-tts-base-url')?.value?.trim() || LOCALAI_TTS_BASE_URL,
        localai_tts_model: document.getElementById('localai-tts-model')?.value?.trim() || '',
        localai_tts_default_voice: document.getElementById('localai-tts-default-voice')?.value?.trim() || '',
        localai_tts_default_language: document.getElementById('localai-tts-default-language')?.value?.trim() || '',
        localai_tts_instructions: document.getElementById('localai-tts-instructions')?.value?.trim() || '',
        localai_tts_timeout: Math.max(10, Math.min(600, parseInt(document.getElementById('localai-tts-timeout')?.value, 10) || 180)),
        localai_tts_max_parallel: Math.max(1, Math.min(8, parseInt(document.getElementById('localai-tts-max-parallel')?.value, 10) || 1)),
        localai_tts_max_retries: Math.max(0, Math.min(8, parseInt(document.getElementById('localai-tts-max-retries')?.value, 10) || 0)),
        localai_tts_chunk_size: Math.max(100, Math.min(4000, parseInt(document.getElementById('localai-tts-chunk-size')?.value, 10) || 1000)),
        localai_tts_voice_profile_consent_confirmed: Boolean(document.getElementById('localai-tts-voice-profile-consent-confirmed')?.checked),
        cloud_tts_concurrent_jobs: Math.max(1, Math.min(4, parseInt(document.getElementById('cloud-tts-concurrent-jobs')?.value, 10) || 2)),
        llm_local_provider: document.getElementById('llm-local-provider')?.value || 'lmstudio',
        llm_local_base_url: document.getElementById('llm-local-base-url')?.value || LOCAL_LLM_BASE_URLS.lmstudio,
        llm_local_model: document.getElementById('llm-local-model')?.value || '',
        llm_local_api_key: document.getElementById('llm-local-api-key')?.value || '',
        llm_local_timeout: parseInt(document.getElementById('llm-local-timeout')?.value, 10) || 120,
        llm_local_temperature: parseFloat(document.getElementById('llm-local-temperature')?.value) || 0.2,
        llm_local_top_p: parseFloat(document.getElementById('llm-local-top-p')?.value) || 1.0,
        llm_local_top_k: parseInt(document.getElementById('llm-local-top-k')?.value, 10) || 0,
        llm_local_repeat_penalty: parseFloat(document.getElementById('llm-local-repeat-penalty')?.value) || 1.0,
        llm_local_max_tokens: parseInt(document.getElementById('llm-local-max-tokens')?.value, 10) || 0,
        llm_local_disable_reasoning: document.getElementById('llm-local-disable-reasoning')?.checked ?? false,
        llm_gemini_chunk_size: Math.max(50, parseInt(document.getElementById('llm-gemini-chunk-size')?.value, 10) || 500),
        llm_local_chunk_size: Math.max(50, parseInt(document.getElementById('llm-local-chunk-size')?.value, 10) || 500),
        llm_gemini_chunk_chapters: document.getElementById('llm-gemini-chunk-chapters')?.checked ?? true,
        llm_local_chunk_chapters: document.getElementById('llm-local-chunk-chapters')?.checked ?? true,
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
        voxcpm_chunk_size: parseInt(document.getElementById('voxcpm-chunk-size')?.value, 10) || 550,
        voxcpm_local_device: document.getElementById('voxcpm-local-device').value,
        voxcpm_local_default_prompt: document.getElementById('voxcpm-local-prompt').value,
        voxcpm_local_default_prompt_text: document.getElementById('voxcpm-local-prompt-text').value,
        voxcpm_local_cfg_value: parseFloat(document.getElementById('voxcpm-local-cfg').value) || 2.0,
        voxcpm_local_inference_timesteps: parseInt(document.getElementById('voxcpm-local-steps').value, 10) || 10,
        voxcpm_local_normalize: document.getElementById('voxcpm-local-normalize').checked,
        voxcpm_local_denoise: document.getElementById('voxcpm-local-denoise').checked,
        qwen3_custom_model_id: document.getElementById('qwen3-custom-model-id').value,
        qwen3_chunk_size: parseInt(document.getElementById('qwen3-chunk-size')?.value, 10) || 500,
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
        omnivoice_clone_model_id: document.getElementById('omnivoice-model-id')?.value || 'k2-fsa/OmniVoice',
        omnivoice_design_model_id: document.getElementById('omnivoice-model-id')?.value || 'k2-fsa/OmniVoice',
        omnivoice_chunk_size: parseInt(document.getElementById('omnivoice-chunk-size')?.value, 10) || 500,
        omnivoice_clone_device: document.getElementById('omnivoice-device')?.value || 'auto',
        omnivoice_design_device: document.getElementById('omnivoice-device')?.value || 'auto',
        omnivoice_clone_dtype: document.getElementById('omnivoice-dtype')?.value || 'float16',
        omnivoice_design_dtype: document.getElementById('omnivoice-dtype')?.value || 'float16',
        omnivoice_clone_num_step: parseInt(document.getElementById('omnivoice-num-step')?.value, 10) || 32,
        omnivoice_design_num_step: parseInt(document.getElementById('omnivoice-num-step')?.value, 10) || 32,
        omnivoice_batch_size: Math.max(1, Math.min(parseInt(document.getElementById('omnivoice-batch-size')?.value, 10) || 1, 8)),
        omnivoice_clone_default_prompt: document.getElementById('omnivoice-clone-prompt')?.value || '',
        omnivoice_clone_default_prompt_text: document.getElementById('omnivoice-clone-prompt-text')?.value || '',
        omnivoice_design_default_instruct: document.getElementById('omnivoice-design-instruct')?.value || '',
        omnivoice_post_process: document.getElementById('omnivoice-post-process')?.checked !== false,
        omnivoice_duration_safety_margin: (() => {
            const value = parseFloat(document.getElementById('omnivoice-duration-safety-margin')?.value);
            return Number.isFinite(value) ? Math.max(0, Math.min(value, 2)) : 0.25;
        })(),
        pocket_tts_model_variant: document.getElementById('pocket-tts-model-variant')?.value || 'b6369a24',
        huggingface_token: document.getElementById('pocket-tts-huggingface-token')?.value?.trim() || '',
        pocket_tts_chunk_size: parseInt(document.getElementById('pocket-tts-chunk-size')?.value, 10) || 450,
        pocket_tts_temp: parseFloat(document.getElementById('pocket-tts-temp')?.value) || 0.7,
        pocket_tts_lsd_decode_steps: parseInt(document.getElementById('pocket-tts-steps')?.value, 10) || 1,
        pocket_tts_noise_clamp: (() => {
            const raw = document.getElementById('pocket-tts-noise-clamp')?.value?.trim();
            if (!raw) return null;
            const parsed = parseFloat(raw);
            return Number.isFinite(parsed) ? parsed : null;
        })(),
        pocket_tts_eos_threshold: parseFloat(document.getElementById('pocket-tts-eos')?.value) || -4.0,
        pocket_tts_default_prompt: document.getElementById('pocket-tts-default-prompt')?.value || '',
        pocket_tts_prompt_truncate: document.getElementById('pocket-tts-prompt-truncate')?.checked ?? false,
        pocket_tts_num_threads: (() => {
            const raw = document.getElementById('pocket-tts-num-threads')?.value?.trim();
            if (!raw) return null;
            const parsed = parseInt(raw, 10);
            return Number.isFinite(parsed) ? parsed : null;
        })(),
        pocket_tts_interop_threads: (() => {
            const raw = document.getElementById('pocket-tts-interop-threads')?.value?.trim();
            if (!raw) return null;
            const parsed = parseInt(raw, 10);
            return Number.isFinite(parsed) ? parsed : null;
        })(),
        kitten_tts_model_id: document.getElementById('kitten-tts-model-id')?.value || 'KittenML/kitten-tts-mini-0.8',
        kitten_tts_default_voice: document.getElementById('kitten-tts-default-voice')?.value || 'Jasper',
        kitten_tts_chunk_size: parseInt(document.getElementById('kitten-tts-chunk-size')?.value, 10) || 300,
        index_tts_model_version: document.getElementById('index-tts-model-version')?.value || 'IndexTTS-2',
        index_tts_chunk_size: parseInt(document.getElementById('index-tts-chunk-size')?.value, 10) || 400,
        index_tts_device: document.getElementById('index-tts-device')?.value || 'auto',
        index_tts_default_prompt: document.getElementById('index-tts-default-prompt')?.value || '',
        index_tts_use_fp16: document.getElementById('index-tts-use-fp16')?.checked ?? true,
        index_tts_use_deepspeed: document.getElementById('index-tts-use-deepspeed')?.checked ?? false,
        index_tts_use_torch_compile: document.getElementById('index-tts-use-torch-compile')?.checked ?? false,
        index_tts_use_accel: document.getElementById('index-tts-use-accel')?.checked ?? false,
        index_tts_num_beams: parseInt(document.getElementById('index-tts-num-beams')?.value, 10) || 1,
        index_tts_diffusion_steps: parseInt(document.getElementById('index-tts-diffusion-steps')?.value, 10) || 25,
        index_tts_temperature: parseFloat(document.getElementById('index-tts-temperature')?.value) || 0.8,
        index_tts_top_p: parseFloat(document.getElementById('index-tts-top-p')?.value) || 0.8,
        index_tts_top_k: parseInt(document.getElementById('index-tts-top-k')?.value, 10) || 30,
        index_tts_repetition_penalty: parseFloat(document.getElementById('index-tts-repetition-penalty')?.value) || 10.0,
        index_tts_max_mel_tokens: parseInt(document.getElementById('index-tts-max-mel-tokens')?.value, 10) || 1500,
        index_tts_max_text_tokens_per_segment: parseInt(document.getElementById('index-tts-max-text-tokens-per-segment')?.value, 10) || 120,
        dots_tts_model_id: document.getElementById('dots-tts-model-id')?.value || 'rednote-hilab/dots.tts-soar',
        dots_tts_chunk_size: parseInt(document.getElementById('dots-tts-chunk-size')?.value, 10) || 250,
        dots_tts_device: document.getElementById('dots-tts-device')?.value || 'auto',
        dots_tts_precision: document.getElementById('dots-tts-precision')?.value || 'auto',
        dots_tts_default_prompt: document.getElementById('dots-tts-default-prompt')?.value || '',
        dots_tts_default_prompt_text: document.getElementById('dots-tts-default-prompt-text')?.value || '',
        dots_tts_num_steps: parseInt(document.getElementById('dots-tts-num-steps')?.value, 10) || 10,
        dots_tts_guidance_scale: parseFloat(document.getElementById('dots-tts-guidance-scale')?.value) || 1.2,
        dots_tts_speaker_scale: parseFloat(document.getElementById('dots-tts-speaker-scale')?.value) || 1.5,
        dots_tts_seed: (() => {
            const raw = document.getElementById('dots-tts-seed')?.value?.trim();
            if (!raw) return null;
            const parsed = parseInt(raw, 10);
            return Number.isFinite(parsed) ? parsed : 42;
        })(),
        dots_tts_language: document.getElementById('dots-tts-language')?.value || 'none',
        dots_tts_normalize_text: document.getElementById('dots-tts-normalize-text')?.checked ?? false,
        dots_tts_optimize: document.getElementById('dots-tts-optimize')?.checked ?? false,
        dots_tts_allow_xvector_only: document.getElementById('dots-tts-allow-xvector-only')?.checked ?? false,
        audio8_tts_model_id: document.getElementById('audio8-tts-model-id')?.value || 'Audio8/Audio8-TTS-Preview-0.6b',
        audio8_tts_device: document.getElementById('audio8-tts-device')?.value || 'auto',
        audio8_tts_dtype: document.getElementById('audio8-tts-dtype')?.value || 'auto',
        audio8_tts_temperature: parseFloat(document.getElementById('audio8-tts-temperature')?.value) || 0.8,
        audio8_tts_top_p: parseFloat(document.getElementById('audio8-tts-top-p')?.value) || 0.95,
        audio8_tts_top_k: parseInt(document.getElementById('audio8-tts-top-k')?.value, 10) || 50,
        audio8_tts_max_new_tokens: parseInt(document.getElementById('audio8-tts-max-new-tokens')?.value, 10) || 1024,
        audio8_tts_retry_max_new_tokens: parseInt(document.getElementById('audio8-tts-retry-max-new-tokens')?.value, 10) || 2000,
        audio8_tts_seed: parseInt(document.getElementById('audio8-tts-seed')?.value, 10) || 42,
        audio8_tts_default_prompt: document.getElementById('audio8-tts-default-prompt')?.value || '',
        audio8_tts_default_prompt_text: document.getElementById('audio8-tts-default-prompt-text')?.value || '',
        audio8_tts_chunk_size: parseInt(document.getElementById('audio8-tts-chunk-size')?.value, 10) || 140,
        audio8_tts_hard_chunk_size: parseInt(document.getElementById('audio8-tts-hard-chunk-size')?.value, 10) || 400,
        breeze_tts_2_model_id: document.getElementById('breeze-tts-2-model-id')?.value || 'BreezeBlue/Breeze-TTS-2',
        breeze_tts_2_runtime: document.getElementById('breeze-tts-2-runtime')?.value || 'pytorch',
        breeze_tts_2_device: document.getElementById('breeze-tts-2-device')?.value || 'auto',
        breeze_tts_2_seed: parseInt(document.getElementById('breeze-tts-2-seed')?.value, 10) || 42,
        breeze_tts_2_clone_cfg_scale: parseFloat(document.getElementById('breeze-tts-2-clone-cfg')?.value) || 1,
        breeze_tts_2_design_cfg_scale: parseFloat(document.getElementById('breeze-tts-2-design-cfg')?.value) || 4,
        breeze_tts_2_direction_cfg_scale: parseFloat(document.getElementById('breeze-tts-2-direction-cfg')?.value) || 4,
        breeze_tts_2_max_new_tokens: parseInt(document.getElementById('breeze-tts-2-max-new-tokens')?.value, 10) || 1500,
        breeze_tts_2_max_seq_len: parseInt(document.getElementById('breeze-tts-2-max-seq-len')?.value, 10) || 2048,
        breeze_tts_2_fast_mode: document.getElementById('breeze-tts-2-fast-mode')?.checked ?? false,
        breeze_tts_2_default_prompt: document.getElementById('breeze-tts-2-default-prompt')?.value || '',
        breeze_tts_2_default_prompt_text: document.getElementById('breeze-tts-2-default-prompt-text')?.value || '',
        breeze_tts_2_default_instruction: document.getElementById('breeze-tts-2-default-instruction')?.value || 'Speak clearly and naturally.',
        breeze_tts_2_chunk_size: parseInt(document.getElementById('breeze-tts-2-chunk-size')?.value, 10) || 500,
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
            headers: engineManagementHeaders({ json: true }),
            body: JSON.stringify(settings)
        });
        
        const data = await response.json();
        
        if (data.success) {
            const remoteToken = document.getElementById('remote-engine-management-token')?.value?.trim() || '';
            if (remoteToken) {
                try { sessionStorage.setItem('ttsStoryRemoteAdminToken', remoteToken); } catch (_) {}
            }
            alert('Settings saved successfully!');
            // LocalAI voice availability depends on the selected model and the
            // explicit voice-cloning rights confirmation. Refresh the shared
            // catalog so already-open Speaker Properties selectors update now.
            if (typeof loadLocalAITtsCatalog === 'function') {
                await loadLocalAITtsCatalog(true);
            }
            // Refresh status bar - loadHealthStatus is defined in main.js
            if (typeof loadHealthStatus === 'function') {
                loadHealthStatus();
            } else {
                console.warn('loadHealthStatus not available, reloading page');
                location.reload();
            }
            await loadEngineSetupStatus();
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
        kokoro_chunk_size: 500,
        speed: 1.0,
        output_format: 'mp3',
        crossfade_duration: 0.1,
        intro_silence_ms: 0,
        inter_chunk_silence_ms: 0,
        pause_marker_three_seconds: 0.25,
        pause_marker_six_seconds: 0.5,
        replicate_max_parallel: 3,
        parallel_chunks: 3,
        group_chunks_by_speaker: false,
        cleanup_vram_after_job: false,
        gemini_api_key: '',
        gemini_model: 'gemini-1.5-flash',
        gemini_prompt: '',
        gemini_prompt_presets: [],
        llm_provider: 'gemini',
        llm_backup_profiles: [],
        atlas_cloud_api_key: '',
        atlas_cloud_base_url: ATLAS_CLOUD_BASE_URL,
        atlas_cloud_model: 'deepseek-v3',
        atlas_cloud_timeout: 120,
        openrouter_api_key: '',
        openrouter_base_url: OPENROUTER_BASE_URL,
        openrouter_model: 'openrouter/auto',
        openrouter_timeout: 120,
        azure_speech_key: '',
        azure_speech_region: '',
        azure_speech_default_voice: 'en-US-AvaMultilingualNeural',
        azure_speech_output_format: 'riff-24khz-16bit-mono-pcm',
        azure_speech_timeout: 60,
        azure_speech_max_parallel: 2,
        azure_speech_requests_per_minute: 20,
        azure_speech_chunk_size: 1000,
        azure_speech_default_style: '',
        azure_speech_default_role: '',
        azure_speech_default_style_degree: 1,
        edge_tts_default_voice: 'en-US-AriaNeural',
        edge_tts_timeout: 60,
        edge_tts_max_parallel: 2,
        edge_tts_max_retries: 4,
        edge_tts_chunk_size: 1000,
        edge_tts_default_volume: 0,
        elevenlabs_api_key: '',
        elevenlabs_base_url: ELEVENLABS_BASE_URL,
        elevenlabs_model: 'eleven_multilingual_v2',
        elevenlabs_default_voice: 'JBFqnCBsd6RMkjVDRZzb',
        elevenlabs_output_format: 'mp3_44100_128',
        elevenlabs_timeout: 120,
        elevenlabs_max_parallel: 2,
        elevenlabs_chunk_size: 4000,
        elevenlabs_stability: 0.5,
        elevenlabs_similarity_boost: 0.75,
        elevenlabs_style: 0,
        elevenlabs_use_speaker_boost: true,
        openai_tts_api_key: '',
        openai_tts_base_url: OPENAI_TTS_BASE_URL,
        openai_tts_model: 'gpt-4o-mini-tts',
        openai_tts_default_voice: 'coral',
        openai_tts_custom_voices: '',
        openai_tts_instructions: '',
        openai_tts_timeout: 120,
        openai_tts_max_parallel: 2,
        openai_tts_chunk_size: 4000,
        localai_tts_api_key: '',
        localai_tts_base_url: LOCALAI_TTS_BASE_URL,
        localai_tts_model: '',
        localai_tts_default_voice: '',
        localai_tts_default_language: '',
        localai_tts_instructions: '',
        localai_tts_timeout: 180,
        localai_tts_max_parallel: 1,
        localai_tts_max_retries: 4,
        localai_tts_chunk_size: 1000,
        localai_tts_voice_profile_consent_confirmed: false,
        cloud_tts_concurrent_jobs: 2,
        llm_local_provider: 'lmstudio',
        llm_local_base_url: LOCAL_LLM_BASE_URLS.lmstudio,
        llm_local_model: '',
        llm_local_api_key: '',
        llm_local_timeout: 120,
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
        qwen3_clone_default_prompt_text: '',
        omnivoice_clone_model_id: 'k2-fsa/OmniVoice',
        omnivoice_design_model_id: 'k2-fsa/OmniVoice',
        omnivoice_chunk_size: 500,
        omnivoice_clone_device: 'auto',
        omnivoice_design_device: 'auto',
        omnivoice_clone_dtype: 'float16',
        omnivoice_design_dtype: 'float16',
        omnivoice_clone_num_step: 32,
        omnivoice_design_num_step: 32,
        omnivoice_batch_size: 1,
        omnivoice_clone_default_prompt: '',
        omnivoice_clone_default_prompt_text: '',
        omnivoice_design_default_instruct: '',
        omnivoice_post_process: true,
        omnivoice_duration_safety_margin: 0.25,
        pocket_tts_model_variant: 'b6369a24',
        huggingface_token: '',
        pocket_tts_temp: 0.7,
        pocket_tts_lsd_decode_steps: 1,
        pocket_tts_noise_clamp: null,
        pocket_tts_eos_threshold: -4.0,
        pocket_tts_default_prompt: '',
        pocket_tts_prompt_truncate: false,
        pocket_tts_num_threads: null,
        pocket_tts_interop_threads: null,
        dots_tts_model_id: 'rednote-hilab/dots.tts-soar',
        dots_tts_chunk_size: 250,
        dots_tts_device: 'auto',
        dots_tts_precision: 'auto',
        dots_tts_default_prompt: '',
        dots_tts_default_prompt_text: '',
        dots_tts_num_steps: 10,
        dots_tts_guidance_scale: 1.2,
        dots_tts_speaker_scale: 1.5,
        dots_tts_seed: 42,
        dots_tts_language: 'none',
        dots_tts_normalize_text: false,
        dots_tts_optimize: false,
        dots_tts_allow_xvector_only: false,
        audio8_tts_model_id: 'Audio8/Audio8-TTS-Preview-0.6b',
        audio8_tts_device: 'auto',
        audio8_tts_dtype: 'auto',
        audio8_tts_temperature: 0.8,
        audio8_tts_top_p: 0.95,
        audio8_tts_top_k: 50,
        audio8_tts_max_new_tokens: 1024,
        audio8_tts_retry_max_new_tokens: 2000,
        audio8_tts_seed: 42,
        audio8_tts_default_prompt: '',
        audio8_tts_default_prompt_text: '',
        audio8_tts_chunk_size: 140,
        audio8_tts_hard_chunk_size: 400,
        breeze_tts_2_model_id: 'BreezeBlue/Breeze-TTS-2',
        breeze_tts_2_runtime: 'pytorch',
        breeze_tts_2_device: 'auto',
        breeze_tts_2_seed: 42,
        breeze_tts_2_clone_cfg_scale: 1,
        breeze_tts_2_design_cfg_scale: 4,
        breeze_tts_2_direction_cfg_scale: 4,
        breeze_tts_2_max_new_tokens: 1500,
        breeze_tts_2_max_seq_len: 2048,
        breeze_tts_2_fast_mode: false,
        breeze_tts_2_default_prompt: '',
        breeze_tts_2_default_prompt_text: '',
        breeze_tts_2_default_instruction: 'Speak clearly and naturally.',
        breeze_tts_2_chunk_size: 500,
        remote_engine_management_enabled: false,
        remote_engine_management_token: ''
    };
    
    try {
        const response = await fetch('/api/settings', {
            method: 'POST',
            headers: engineManagementHeaders({ json: true }),
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
