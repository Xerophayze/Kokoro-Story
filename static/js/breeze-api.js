/* Hosted Breeze integration: uploads are always explicit and previewed. */
window.breezeApiVoices = [];
const breezeApiDefaults = {key: '', model: 'breeze-tts-2', default_voice: '', instructions: '',
    timeout: 180, max_parallel: 1, max_retries: 2, guidance_scale: 4, chunk_size: 1000};
const breezeInput = key => document.getElementById(`breeze-api-${key.replaceAll('_', '-')}`);
window.loadBreezeApiSettings = settings => {
    for (const [key, value] of Object.entries(breezeApiDefaults)) {
        if (breezeInput(key)) breezeInput(key).value = settings[`breeze_api_${key}`] ?? value;
    }
};
window.collectBreezeApiSettings = () => Object.fromEntries(Object.entries(breezeApiDefaults).map(([key, fallback]) => {
    const raw = breezeInput(key)?.value ?? fallback;
    return [`breeze_api_${key}`, typeof fallback === 'number' ? Number(raw) : String(raw).trim()];
}));
window.ensureBreezeVoiceOption = (select, value) => {
    if (!value) return;
    // Do not carry Kokoro IDs or local sample filenames into this provider.
    if (!String(value).startsWith('voc_') && !window.breezeApiVoices.some(v => v.voice_id === value)) return;
    if (!Array.from(select.options).some(o => o.value === value)) select.add(new Option(value, value));
    if (!select.value) select.value = value;
};
let breezeCatalogPending = null;
async function breezeFetch(url, body) {
    const response = await fetch(url, body === undefined ? {} : {
        method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});
    let data;
    try { data = await response.json(); } catch { throw new Error(`Breeze request failed (HTTP ${response.status}). Restart the backend if this route is unavailable.`); }
    if (!response.ok || !data.success) throw new Error(data.error || 'Breeze request failed.');
    return data;
}
window.loadBreezeApiCatalog = async (useSettingsKey = false) => {
    if (breezeCatalogPending) return breezeCatalogPending;
    const catalogStatus = document.getElementById('breeze-api-catalog-status');
    if (catalogStatus) catalogStatus.textContent = 'Loading Breeze models, personal voices and a public voice preview…';
    breezeCatalogPending = (async () => {
        try {
            const data = await breezeFetch('/api/breeze-api/catalog', useSettingsKey ? {api_key: breezeInput('key').value} : undefined);
            window.breezeApiVoices = data.voices || [];
            for (const [id, items, valueKey, nameKey] of [
                ['breeze-api-models', data.models || [], 'model_id', 'name'],
                ['breeze-api-voices', data.voices || [], 'voice_id', 'display_name']]) {
                const list = document.getElementById(id);
                list.replaceChildren(...items.map(item => new Option(item[nameKey] || item[valueKey], item[valueKey])));
            }
            populateVoiceSelects();
            populateDefaultVoiceSelect();
            if (catalogStatus) catalogStatus.textContent = `Loaded ${data.models.length} models, ${data.personal_count ?? 0} personal voices and ${data.public_count ?? 0} public voices.` +
                (data.public_has_more ? ' Showing the first 100 public voices. You can also enter a known voice ID manually.' : '');
            return data;
        } catch (error) {
            if (catalogStatus) catalogStatus.textContent = error.message;
            showNotification(error.message, 'warning');
            return null;
        } finally { breezeCatalogPending = null; }
    })();
    return breezeCatalogPending;
};
document.addEventListener('DOMContentLoaded', () => {
    let preview = null;
    const status = document.getElementById('breeze-api-status');
    async function busy(button, action) {
        button.disabled = true;
        status.textContent = 'Working… Please keep this panel open.';
        try { await action(); } catch (error) { status.textContent = error.message; }
        finally { button.disabled = button.id === 'breeze-api-save-voice' && !preview; }
    }
    document.getElementById('breeze-api-catalog').addEventListener('click', event => busy(event.currentTarget, async () => {
        const result = await window.loadBreezeApiCatalog(true);
        status.textContent = result ? `Loaded ${result.voices.length} voices. Save Settings to use this account.` : 'Catalog unavailable. Check your API key.';
    }));
    document.getElementById('breeze-api-load-samples').addEventListener('click', event => busy(event.currentTarget, async () => {
        const data = await breezeFetch('/api/voice-prompts');
        const select = document.getElementById('breeze-api-sample');
        select.replaceChildren(new Option('Select a sample…', ''));
        for (const sample of data.prompts || []) {
            const file = sample.file_name || sample.name;
            if (!/\.(wav|mp3)$/i.test(file)) continue;
            select.add(new Option(sample.display || sample.display_name || file, file));
        }
        status.textContent = 'Choose a sample and enter a name for the saved Breeze voice.';
    }));
    document.getElementById('breeze-api-upload').addEventListener('click', event => busy(event.currentTarget, async () => {
        const consent = document.getElementById('breeze-api-consent').checked;
        const file_name = document.getElementById('breeze-api-sample').value;
        if (!consent || !file_name) throw new Error('Select a sample and confirm your rights and consent.');
        if (!confirm('Upload this sample to BreezeBlue and create a clone preview? This may use account credits.')) { status.textContent = 'Upload cancelled.'; return; }
        preview = null;
        document.getElementById('breeze-api-save-voice').disabled = true;
        const name = document.getElementById('breeze-api-voice-name').value.trim() || file_name;
        const language = document.getElementById('breeze-api-language').value.trim();
        const data = await breezeFetch('/api/breeze-api/clone', {file_name, name, language, consent});
        preview = {preview_id: data.generated_voice_id, name, language};
        const player = document.getElementById('breeze-api-preview');
        player.src = `/api/breeze-api/preview/${encodeURIComponent(preview.preview_id)}`;
        player.hidden = false;
        document.getElementById('breeze-api-save-voice').disabled = !!data.requires_verification;
        status.textContent = data.requires_verification ? 'Breeze requires verification. Complete it on their platform before saving.' : 'Listen to the preview, then approve it to save a reusable private voice.';
    }));
    document.getElementById('breeze-api-save-voice').addEventListener('click', event => busy(event.currentTarget, async () => {
        if (!preview) throw new Error('Create a new preview first.');
        const data = await breezeFetch('/api/breeze-api/save-voice', preview);
        preview = null;
        await window.loadBreezeApiCatalog();
        status.textContent = `Saved ${data.voice_id}. Select this voice in Speaker Properties with Breeze API selected on the main page. Save your project to retain assignments.`;
    }));
});

window.openBreezeProductions = async (jobId = null) => {
    document.getElementById('breeze-productions-dialog')?.remove();
    const dialog = document.createElement('dialog');
    dialog.id = 'breeze-productions-dialog';
    dialog.style.cssText = 'background:#111827;color:#e5e7eb;border:1px solid #64748b;border-radius:12px;padding:24px;width:min(850px,90vw);max-height:85vh;overflow:auto';
    dialog.innerHTML = '<h2>Breeze Production Voices</h2><p>Remote voices belong to one production. Local samples and finished audio are preserved. Release only after delivery, approval and payment, or when deliberately abandoning a production. Releasing closes the production: further generation requires a new job.</p><button type="button" data-refresh>Refresh status</button> <button type="button" data-close>Close</button><p data-status role="status"></p><div data-productions></div>';
    document.body.appendChild(dialog);
    dialog.showModal();
    const status = dialog.querySelector('[data-status]');
    let pending = false;
    let releasing = false;
    async function refresh() {
        if (pending || releasing) return;
        pending = true;
        try {
            const data = await breezeFetch('/api/breeze-api/productions');
            const list = dialog.querySelector('[data-productions]');
            list.replaceChildren();
            const items = data.productions.filter(p => !jobId || p.production_id === jobId);
            if (!items.length) status.textContent = 'No managed sample uploads for this production. Catalog voices are shared and are never deleted here.';
            for (const production of items) {
                const card = document.createElement('section');
                card.style.cssText = 'border-top:1px solid #475569;padding:16px 0';
                const heading = document.createElement('h3');
                heading.textContent = production.title || production.production_id;
                const info = document.createElement('p');
                info.textContent = `Production ${production.production_id} · ${production.released ? 'Closed for generation' : 'Open'} · ${production.created_at}`;
                card.append(heading, info);
                const voices = Object.values(production.voices || {});
                for (const [sampleKey, voice] of Object.entries(production.voices || {})) {
                    const row = document.createElement('p');
                    row.textContent = `${voice.speakers.join(', ')} — ${voice.state}${voice.voice_id ? ` · ${voice.voice_id}` : ''}`;
                    card.appendChild(row);
                    if (!production.released && ['uploading', 'saving'].includes(voice.state)) {
                        const recover = document.createElement('button');
                        recover.type = 'button';
                        recover.textContent = `Recover ${voice.speakers.join(', ')}`;
                        recover.onclick = async () => {
                            if (releasing) return;
                            releasing = true;
                            recover.disabled = true;
                            status.textContent = 'Checking saved production voices on Breeze…';
                            const reconcile = async (confirmAbsent) => {
                                const response = await fetch(`/api/breeze-api/productions/${encodeURIComponent(production.production_id)}/recover`, {
                                    method: 'POST', headers: typeof engineManagementHeaders === 'function' ? engineManagementHeaders({json: true}) : {'Content-Type': 'application/json'},
                                    body: JSON.stringify({sample_key: sampleKey, confirm_absent: confirmAbsent})});
                                const result = await response.json();
                                if (!response.ok || !result.success) throw new Error(result.error || 'Voice recovery failed.');
                                return result;
                            };
                            try {
                                let result = await reconcile(false);
                                if (result.needs_confirmation) {
                                    const approved = confirm(`No saved voice named ${result.remote_name} was found. Check Breeze's voice previews and account history as well: an unsaved preview may still exist.\n\nOnly continue if the previous operation has stopped and you have verified it is safe to retry. A new upload/save on resume may consume credits. Authorize retry?`);
                                    if (!approved) { status.textContent = 'Recovery left unchanged. Check Breeze before retrying.'; return; }
                                    result = await reconcile(true);
                                }
                                status.textContent = result.state === 'ready' ? 'Existing remote voice recovered. You can resume the job.' : 'Retry authorized. Resume the job to continue; completed voices are preserved.';
                            } catch (error) { status.textContent = error.message; }
                            finally { releasing = false; recover.disabled = false; await refresh(); }
                        };
                        card.appendChild(recover);
                    }
                }
                const uncertain = voices.some(v => ['uploading', 'saving', 'verification'].includes(v.state));
                if (uncertain) {
                    const warning = document.createElement('p');
                    warning.textContent = 'An upload may still be running, require verification, or have an uncertain result. Refresh after it finishes. For interrupted operations, check Breeze for voices named with this production ID; do not start duplicate uploads.';
                    card.appendChild(warning);
                }
                const release = document.createElement('button');
                release.type = 'button';
                release.textContent = 'Release production voices';
                release.disabled = !!production.released_at && !voices.some(v => v.voice_id && v.state !== 'deleted');
                release.onclick = async () => {
                    const count = voices.filter(v => v.voice_id && v.state !== 'deleted').length;
                    if (!confirm(`Release ${count} tracked Breeze voice(s) for production ${production.production_id}? Confirm it is delivered, approved and paid, or deliberately abandoned. This closes the production and cannot be undone. Local samples and audio remain. Any unconfirmed uploads must be checked separately on Breeze.`)) return;
                    release.disabled = true;
                    releasing = true;
                    status.textContent = 'Releasing tracked remote voices…';
                    try {
                        const response = await fetch(`/api/breeze-api/productions/${encodeURIComponent(production.production_id)}/release`, {
                            method: 'POST', headers: typeof engineManagementHeaders === 'function' ? engineManagementHeaders({json: true}) : {'Content-Type': 'application/json'},
                            body: JSON.stringify({confirm_release: true})});
                        const result = await response.json();
                        if (!response.ok || !result.success) throw new Error(result.error || 'Voice release failed.');
                        status.textContent = 'Tracked remote voices released. Local samples and finished audio were kept.';
                    } catch (error) { status.textContent = error.message; }
                    finally { releasing = false; release.disabled = false; await refresh(); }
                };
                card.appendChild(release);
                list.appendChild(card);
            }
        } catch (error) { status.textContent = error.message; }
        finally { pending = false; }
    }
    dialog.querySelector('[data-close]').onclick = () => dialog.close();
    dialog.querySelector('[data-refresh]').onclick = refresh;
    const timer = setInterval(() => { if (dialog.open) refresh(); else clearInterval(timer); }, 5000);
    dialog.addEventListener('close', () => { clearInterval(timer); dialog.remove(); });
    await refresh();
};
