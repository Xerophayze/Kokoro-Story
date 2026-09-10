const MIN_CHATTERBOX_PROMPT_SECONDS = 5;
const QWEN_VOICE_DESIGN_INSTALL_MESSAGE = 'Install Qwen3-TTS from Settings → Engine Settings to generate voices.';
const BREEZE_VOICE_DESIGN_INSTALL_MESSAGE = 'Install Breeze TTS 2 and accept its non-commercial model license under Settings → Engine Settings to generate voices.';
window.qwenVoiceDesignAvailable = false;
window.qwenVoiceDesignAvailabilityKnown = false;
window.breezeVoiceDesignAvailable = false;
window.breezeVoiceDesignAvailabilityKnown = false;

const VOICE_DESIGN_ENGINES = {
    qwen3: {
        label: 'Qwen3-TTS',
        previewUrl: '/api/qwen3/voice-design/preview',
        saveUrl: '/api/qwen3/voice-design/save',
        taskUrl: id => `/api/qwen3/voice-design/tasks/${encodeURIComponent(id)}`,
        installMessage: QWEN_VOICE_DESIGN_INSTALL_MESSAGE,
        settingsTab: 'qwen3'
    },
    breeze: {
        label: 'Breeze TTS 2',
        previewUrl: '/api/breeze/voice-design/preview',
        saveUrl: '/api/breeze/voice-design/save',
        taskUrl: id => `/api/breeze/voice-design/tasks/${encodeURIComponent(id)}`,
        installMessage: BREEZE_VOICE_DESIGN_INSTALL_MESSAGE,
        settingsTab: 'breeze-tts-2'
    }
};

function normalizeVoiceDesignEngine(value) {
    return value === 'breeze' ? 'breeze' : 'qwen3';
}

function voiceDesignEngineAvailable(engine) {
    return normalizeVoiceDesignEngine(engine) === 'breeze'
        ? window.breezeVoiceDesignAvailable === true
        : window.qwenVoiceDesignAvailable === true;
}

function voiceDesignEngineAvailabilityKnown(engine) {
    return normalizeVoiceDesignEngine(engine) === 'breeze'
        ? window.breezeVoiceDesignAvailabilityKnown === true
        : window.qwenVoiceDesignAvailabilityKnown === true;
}

function getVoiceDesignEngineConfig(engine) {
    return VOICE_DESIGN_ENGINES[normalizeVoiceDesignEngine(engine)];
}

function openQwen3EngineSettings() {
    document.querySelector('.tab-button[data-tab="settings"]')?.click();
    document.getElementById('engine-settings-group')?.classList.remove('collapsed');
    document.querySelector('.engine-tab-btn[data-engine-tab="qwen3"]')?.click();
    document.getElementById('engine-settings-group')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
window.openQwen3EngineSettings = openQwen3EngineSettings;

function openBreezeEngineSettings() {
    document.querySelector('.tab-button[data-tab="settings"]')?.click();
    document.getElementById('engine-settings-group')?.classList.remove('collapsed');
    document.querySelector('.engine-tab-btn[data-engine-tab="breeze-tts-2"]')?.click();
    document.getElementById('engine-settings-group')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}
window.openBreezeEngineSettings = openBreezeEngineSettings;

function refreshQwenVoiceDesignControls() {
    const anyAvailable = window.qwenVoiceDesignAvailable === true || window.breezeVoiceDesignAvailable === true;
    const anyKnown = window.qwenVoiceDesignAvailabilityKnown === true && window.breezeVoiceDesignAvailabilityKnown === true;
    const hasDetectedSpeakers = Array.isArray(currentStats?.speakers) && currentStats.speakers.length > 0;

    const batchButton = document.getElementById('generate-voices-btn');
    if (batchButton) {
        batchButton.disabled = !anyAvailable || !hasDetectedSpeakers;
        batchButton.title = anyAvailable ? '' : (anyKnown
            ? 'Install Qwen3-TTS or Breeze TTS 2 under Settings → Engine Settings to generate voices.'
            : 'Checking voice-design engine availability…');
    }
    document.getElementById('generate-voices-unavailable')?.classList.toggle('hidden', !anyKnown || anyAvailable);

    document.querySelectorAll('[data-role="speaker-generate-voice"]').forEach(button => {
        const panel = button.closest('.speaker-profile-editor');
        const engine = normalizeVoiceDesignEngine(panel?.querySelector('[data-role="speaker-voice-design-engine"]')?.value);
        const available = voiceDesignEngineAvailable(engine);
        const known = voiceDesignEngineAvailabilityKnown(engine);
        button.disabled = !available;
        button.title = available ? '' : (known ? getVoiceDesignEngineConfig(engine).installMessage : 'Checking voice-design engine availability…');
    });
    document.querySelectorAll('[data-role="voice-design-unavailable"]').forEach(notice => {
        const panel = notice.closest('.speaker-profile-editor');
        const engine = normalizeVoiceDesignEngine(panel?.querySelector('[data-role="speaker-voice-design-engine"]')?.value);
        const available = voiceDesignEngineAvailable(engine);
        const known = voiceDesignEngineAvailabilityKnown(engine);
        notice.classList.toggle('hidden', !known || available);
        const message = notice.querySelector('[data-role="voice-design-unavailable-message"]');
        if (message) message.textContent = getVoiceDesignEngineConfig(engine).installMessage;
    });

    const voiceCreationButton = document.getElementById('qwen-voice-generate-btn');
    if (voiceCreationButton) {
        const engine = normalizeVoiceDesignEngine(document.querySelector('#voice-creation-engine-toggle [data-voice-engine].active')?.dataset.voiceEngine);
        const available = voiceDesignEngineAvailable(engine);
        const known = voiceDesignEngineAvailabilityKnown(engine);
        voiceCreationButton.disabled = !available;
        voiceCreationButton.title = available ? '' : (known ? getVoiceDesignEngineConfig(engine).installMessage : 'Checking voice-design engine availability…');
        document.getElementById('qwen-voice-unavailable')?.classList.toggle('hidden', !known || available);
    }

    document.querySelectorAll('[data-voice-design-option]').forEach(option => {
        const engine = normalizeVoiceDesignEngine(option.value);
        option.disabled = voiceDesignEngineAvailabilityKnown(engine) && !voiceDesignEngineAvailable(engine);
    });
}
window.refreshQwenVoiceDesignControls = refreshQwenVoiceDesignControls;

function setQwenVoiceDesignAvailability(available, known = true) {
    window.qwenVoiceDesignAvailable = available === true;
    window.qwenVoiceDesignAvailabilityKnown = known === true;
    refreshQwenVoiceDesignControls();
    window.dispatchEvent(new CustomEvent('qwenVoiceDesignAvailabilityChanged', {
        detail: {
            available: window.qwenVoiceDesignAvailable,
            known: window.qwenVoiceDesignAvailabilityKnown
        }
    }));
}
window.setQwenVoiceDesignAvailability = setQwenVoiceDesignAvailability;

function setBreezeVoiceDesignAvailability(available, known = true) {
    window.breezeVoiceDesignAvailable = available === true;
    window.breezeVoiceDesignAvailabilityKnown = known === true;
    refreshQwenVoiceDesignControls();
    window.dispatchEvent(new CustomEvent('breezeVoiceDesignAvailabilityChanged', {
        detail: {
            available: window.breezeVoiceDesignAvailable,
            known: window.breezeVoiceDesignAvailabilityKnown
        }
    }));
}
window.setBreezeVoiceDesignAvailability = setBreezeVoiceDesignAvailability;

const HELP_TOPICS = {
    'input-text': {
        title: 'Input Text',
        body: `
            <p>Paste or type your story here. Use <code>[speaker]</code> tags for multiple voices.</p>
            <ul>
                <li><strong>Single voice:</strong> Just write plain text.</li>
                <li><strong>Multi-voice:</strong> Wrap sections in tags like <code>[alice]Hello[/alice]</code>.</li>
                <li><strong>Drop files:</strong> Drag documents onto the text area to extract text.</li>
            </ul>
        `
    },
    projects: {
        title: 'Projects',
        body: `
            <p>Save and reload your full setup: text, speakers, voice assignments, and settings.</p>
            <ul>
                <li><strong>Save Project:</strong> Stores current text and configuration.</li>
                <li><strong>Load Project:</strong> Restores a previously saved project.</li>
            </ul>
        `
    },
    'prep-text': {
        title: 'Prep Text',
        body: `
            <p>Run your text through the selected LLM prompt before generating audio.</p>
            <ul>
                <li>Use this to clean formatting, fix punctuation, or add narration polish.</li>
                <li>The prompt preset defines the cleanup behavior.</li>
            </ul>
        `
    },
    'paralinguistic-tags': {
        title: 'Paralinguistic Tags',
        body: `
            <p>Insert expressive tags like <code>[sigh]</code> or <code>[laugh]</code> into your text.</p>
            <p>These are supported by Kokoro and OmniVoice engines to add non-verbal cues. Available tags differ per engine.</p>
        `
    },
    'text-statistics': {
        title: 'Text Statistics',
        body: `
            <p>Quick summary of your input: speaker count, chunks, words, and estimated duration.</p>
            <p>Click a speaker chip to open voice assignments.</p>
        `
    },
    'assign-voices': {
        title: 'Assign Voices',
        body: `
            <p>Set voices or reference prompts per speaker.</p>
            <ul>
                <li>Each speaker can use a unique voice or clone prompt.</li>
                <li>Use the inline controls to preview and fine-tune voice FX.</li>
            </ul>
        `
    },
    'generation-options': {
        title: 'Generation Options',
        body: `
            <p>Select the engine, output format, and chapter splitting behavior.</p>
            <ul>
                <li><strong>Engine:</strong> Choose the TTS engine for this job.</li>
                <li><strong>Format:</strong> Set output type and bitrate.</li>
                <li><strong>Sections:</strong> Split output by chapters if detected.</li>
            </ul>
        `
    },
    'speaker-edit': {
        title: 'Edit Speaker',
        body: `
            <p>Rename a speaker and refine how their voice is generated.</p>
            <ul>
                <li><strong>Speaker name:</strong> Clicking Apply updates the speaker tag names in the main text.</li>
                <li><strong>Profile:</strong> Describe the person’s background, role, and personality.</li>
                <li><strong>Voice type:</strong> Describe the sound of their voice (baritone, tenor, deep, airy).</li>
                <li><strong>Voice Design Prompt:</strong> A separate synthesis-only description used by Qwen3 or Breeze, including explicit gender, age, range, timbre, pace, accent, and delivery.</li>
                <li><strong>Voice candidates:</strong> Choose Qwen3 or Breeze. The default is one automatically assigned voice; increase Candidates to audition multiple alternatives and approve one.</li>
                <li><strong>Prep Text:</strong> When it detects speakers, profiles and voice types can auto-fill here.</li>
                <li><strong>Voice sample:</strong> Options change by engine—Kokoro has its own voices; other engines share the voice sample list.</li>
                <li><strong>Pitch & Speed:</strong> Fine-tune the tone and pacing for this speaker.</li>
            </ul>
        `
    },
    'audio-library': {
        title: 'Audio Library',
        body: `
            <p>Your saved jobs live here. Each entry shows the engine, size, and format (MP3/WAV).</p>
            <ul>
                <li><strong>Stacks:</strong> Click an item to expand the player.</li>
                <li><strong>Actions:</strong> Download, review chunks, or delete.</li>
                <li><strong>Review Chunks:</strong> Opens a new window to manage speakers and audio segments.</li>
                <li><strong>Speakers:</strong> See name + chunk count, then expand to swap engine, voice, pitch, and speed.</li>
                <li><strong>Regenerate:</strong> Check a speaker and apply to regenerate all of their chunks.</li>
                <li><strong>Chunks list:</strong> Play each chunk or expand to edit text, FX, engine, and voice.</li>
                <li><strong>Single-chunk regen:</strong> Regenerate one chunk without touching the rest.</li>
            </ul>
        `
    },
    'audio-library-actions': {
        title: 'Audio Library Actions',
        body: `
            <ul>
                <li><strong>Chapter chips:</strong> Click any chapter to open a quick menu with <em>Review Chunks</em> or <em>Download Chapter</em>.</li>
                <li><strong>Full Story chip:</strong> Opens the same menu, but the download option becomes <em>Download Full Story</em>.</li>
                <li><strong>Top-row play:</strong> Uses the player controls next to the title to play or stop the full story.</li>
                <li><strong>Delete:</strong> Permanently removes the entire audiobook (top-right).</li>
            </ul>
        `
    },
    'available-voices': {
        title: 'Available Voices',
        body: `
            <p>Everything related to voices lives here: built-in Kokoro voices, custom blends, Qwen/Breeze creation, and voice prompts.</p>
            <ul>
                <li><strong>Kokoro Voices:</strong> Built-in voices with instant previews.</li>
                <li><strong>Custom Kokoro Blends:</strong> Mix two Kokoro voices into a new voice.</li>
                <li><strong>Voice Creation:</strong> Generate custom voices with Qwen3, Breeze TTS 2, or OmniVoice.</li>
                <li><strong>Voice Prompts:</strong> Manage prompt clips and external voice libraries.</li>
            </ul>
        `
    },
    'kokoro-voices': {
        title: 'Kokoro Voices',
        body: `
            <p>The full list of Kokoro’s built-in voices.</p>
            <ul>
                <li>Click any voice to hear a preview sample.</li>
                <li>These voices appear in the voice selectors throughout the app.</li>
            </ul>
        `
    },
    'custom-kokoro-blends': {
        title: 'Custom Kokoro Voice Blends',
        body: `
            <p>Create new Kokoro voices by blending two built-in voices.</p>
            <ul>
                <li><strong>New Custom Voice:</strong> Pick two source voices and blend settings.</li>
                <li>Edit or delete saved blends from the list.</li>
                <li>Custom voices show up in voice selectors across the app.</li>
            </ul>
        `
    },
    'qwen-voice-creation': {
        title: 'AI Voice Creation',
        body: `
            <p>Use Qwen3 or Breeze TTS 2 to design a voice from written characteristics, preview it, and save the approved sample. OmniVoice remains available as a separate design option.</p>
            <ul>
                <li>Enter a prompt + sample text to generate a preview.</li>
                <li>Save the result into Voice Prompts for reuse.</li>
            </ul>
        `
    },
    'voice-prompts': {
        title: 'Voice Prompts',
        body: `
            <p>Manage your prompt library for Chatterbox, VoxCPM, and Qwen3.</p>
            <ul>
                <li>Upload or record prompt clips to build your own library.</li>
                <li>Load External Voices to browse hundreds of voices in many languages.</li>
                <li>Download voices you want, preview them, or delete entries.</li>
                <li>Edit name, gender, or language metadata as needed.</li>
            </ul>
        `
    },
    settings: {
        title: 'Settings',
        body: `
            <p>Control global defaults, engine configuration, audio generation behavior, and LLM prep options.</p>
            <ul>
                <li><strong>Quick Settings:</strong> Default engine + output format for new sessions.</li>
                <li><strong>Engine Settings:</strong> Per-engine parameters and API keys.</li>
                <li><strong>Audio & Generation:</strong> Chunking, merge settings, and speed.</li>
                <li><strong>LLM Pre-Processing:</strong> Prompting and speaker-profile automation.</li>
            </ul>
        `
    },
    'settings-quick': {
        title: 'Quick Settings',
        body: `
            <p>These defaults apply when the app starts and when creating new jobs.</p>
            <ul>
                <li><strong>Default Engine:</strong> Sets the initial TTS engine for new jobs.</li>
                <li><strong>File Format:</strong> MP3, WAV, or OGG for final output.</li>
                <li><strong>MP3 Bitrate:</strong> Higher values mean larger files and higher quality.</li>
            </ul>
        `
    },
    'settings-engines': {
        title: 'Engine Settings',
        body: `
            <p>Configure the behavior of each TTS engine and related cloud services.</p>
            <ul>
                <li>Select a tab to edit its engine-specific parameters.</li>
                <li>Cloud credentials and per-provider request limits are configured inside each cloud engine's tab.</li>
            </ul>
        `
    },
    'engine-kokoro': {
        title: 'Kokoro Settings',
        body: `
            <p>Kokoro runs locally with built-in voices.</p>
            <ul>
                <li>No engine parameters to configure here.</li>
                <li>Pick the default voice in the Generate tab.</li>
            </ul>
        `
    },
    'engine-chatterbox-local': {
        title: 'Chatterbox Local',
        body: `
            <p>Local Chatterbox Turbo on your GPU.</p>
            <ul>
                <li><strong>Device:</strong> Choose auto/cuda/cpu.</li>
                <li><strong>Chunk Size:</strong> Text length per generation step.</li>
                <li><strong>Default Prompt:</strong> Optional reference voice prompt.</li>
                <li><strong>Generation Parameters:</strong> Control creativity and emphasis.</li>
            </ul>
        `
    },
    'engine-chatterbox-cloud': {
        title: 'Chatterbox Cloud',
        body: `
            <p>Replicate-hosted Chatterbox Turbo for cloud inference.</p>
            <ul>
                <li><strong>Model Version:</strong> Exact Replicate model tag.</li>
                <li><strong>Default Voice:</strong> Default voice name for cloud runs.</li>
                <li><strong>Generation Parameters:</strong> Temperature, top-p, top-k, etc.</li>
                <li><strong>Replicate API Token:</strong> Shared with Kokoro Cloud.</li>
                <li><strong>Maximum Parallel Requests:</strong> Limits simultaneous Replicate chunks within one job.</li>
            </ul>
        `
    },
    'engine-voxcpm': {
        title: 'VoxCPM 1.5',
        body: `
            <p>Expressive local TTS with voice cloning.</p>
            <ul>
                <li>Set device, model ID, and default prompt.</li>
                <li>CFG + timesteps balance speed vs. quality.</li>
                <li>Normalization/denoise options refine output.</li>
            </ul>
        `
    },
    'engine-qwen3': {
        title: 'Qwen3-TTS',
        body: `
            <p>Configure Qwen3 custom voice and cloning defaults.</p>
            <ul>
                <li>Set model ID, device, dtype, attention, and defaults.</li>
                <li>Custom Voice and Voice Clone use separate defaults.</li>
                <li>Prompt transcript can auto-generate if left blank.</li>
            </ul>
        `
    },
    'engine-azure-speech': {
        title: 'Microsoft Azure Speech',
        body: `
            <p>Use your own Azure AI Speech resource for regional neural voice synthesis.</p>
            <ul>
                <li><strong>Resource Key + Region:</strong> Must belong to the same Azure Speech resource.</li>
                <li><strong>Load Voices:</strong> Validates the credentials and retrieves the voices available in that region.</li>
                <li><strong>Expression:</strong> Supported voices can expose styles, roles, intensity, rate, pitch, and volume controls.</li>
                <li><strong>Request Limit:</strong> Keep the value appropriate for your Azure pricing tier to avoid throttling.</li>
            </ul>
        `
    },
    'engine-kokoro-cloud': {
        title: 'Kokoro Cloud',
        body: `
            <p>Run Kokoro through the Replicate cloud service.</p>
            <ul>
                <li><strong>Replicate API Token:</strong> Shared with Chatterbox Cloud and saved locally.</li>
                <li><strong>Maximum Parallel Requests:</strong> Limits simultaneous Replicate chunks within one job.</li>
            </ul>
        `
    },
    'settings-audio': {
        title: 'Audio & Generation',
        body: `
            <p>Global generation controls for chunking, merging, and performance.</p>
            <ul>
                <li><strong>Chunk Size:</strong> Words per chunk.</li>
                <li><strong>Crossfade / Silence:</strong> Smooths transitions.</li>
                <li><strong>Simultaneous Cloud Projects:</strong> Global safety limit for separate cloud jobs running at once.</li>
                <li><strong>Local Parallel Chunks:</strong> Parallelism for local engines that support it.</li>
                <li><strong>Group by Speaker:</strong> Optimizes speaker switching.</li>
                <li><strong>Speech Speed:</strong> Overall rate adjustment.</li>
                <li><strong>Unload GPU:</strong> Saves VRAM after each job.</li>
            </ul>
        `
    },
    'settings-llm': {
        title: 'LLM Pre-Processing',
        body: `
            <p>Use an LLM to clean text, add punctuation, and build speaker profiles.</p>
            <ul>
                <li><strong>Provider:</strong> Gemini, Atlas Cloud, OpenRouter, or local LM Studio/Ollama.</li>
                <li><strong>API Key / Model:</strong> Required for cloud usage.</li>
                <li><strong>Local Settings:</strong> Base URL, model name, and timeout.</li>
                <li><strong>Prompt Prefix:</strong> Instructions for text prep.</li>
                <li><strong>Speaker Profile Prompt:</strong> Guides speaker profile creation.</li>
                <li><strong>Prompt Presets:</strong> Save reusable prompt templates.</li>
            </ul>
        `
    }
};

const VOICE_DESIGN_STANDARD_PREVIEW_TEXT = 'With this line of text, you will always know exactly where I stand, and what I sound like. Whether you like it or not, though, it may not be what you think. Listen carefully as my tone moves from quiet reflection toward clear and confident resolve.';

function buildCharacterPreviewText(_speaker, _profile = {}) {
    return VOICE_DESIGN_STANDARD_PREVIEW_TEXT;
}

function buildSpeakerVoiceDesignPayload(speaker, displayName) {
    const { profile } = findSpeakerProfile(speaker);
    const voiceType = profile?.voice?.trim() || '';
    const voiceGenderText = `${profile?.voice_design_prompt || ''} ${voiceType}`.toLowerCase();
    const gender = parseGenderFromSpeakerName(speaker)
        || (/\bfemale\b|\bwoman\b/.test(voiceGenderText) ? 'Female' : null)
        || (/\bmale\b|\bman\b/.test(voiceGenderText) ? 'Male' : null)
        || (/\bgender[- ]neutral\b|\bnonbinary\b/.test(voiceGenderText) ? 'Neutral' : null);
    if (!voiceType && !profile?.voice_design_prompt?.trim()) {
        throw new Error(`Add a Voice Type for ${speaker} before generating.`);
    }
    if (!gender) {
        throw new Error(`Add -male, -female, or -neutral to ${speaker}, or put an explicit adult gender phrase in its Voice Design Prompt.`);
    }
    return {
        name: displayName || speaker,
        speaker,
        gender,
        required_gender: true,
        language: 'English',
        description: voiceType,
        voice_type: voiceType,
        voice_design_prompt: profile?.voice_design_prompt?.trim() || '',
        text: buildCharacterPreviewText(speaker, profile || {})
    };
}

function createVoiceDesignCandidateSeed() {
    const values = new Uint32Array(1);
    if (globalThis.crypto?.getRandomValues) {
        globalThis.crypto.getRandomValues(values);
        return values[0] & 0x7fffffff;
    }
    return Math.floor(Math.random() * 0x7fffffff);
}

async function generateAndSaveVoiceCandidates(speaker, displayName, statusEl, engineOverride = null) {
    const payload = buildSpeakerVoiceDesignPayload(speaker, displayName);
    const { profile } = findSpeakerProfile(speaker);
    const designEngine = normalizeVoiceDesignEngine(engineOverride || profile?.voice_design_engine);
    await requireVoiceDesignBackend(designEngine);
    const engineConfig = getVoiceDesignEngineConfig(designEngine);
    const requestedCount = Number.parseInt(profile?.voice_candidate_count, 10);
    const count = Math.max(1, Math.min(Number.isFinite(requestedCount) ? requestedCount : 1, 10));
    const groupId = (globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`).toString();
    const candidates = [];
    const candidateSeeds = new Set();
    const taskIds = new Set();
    try {
        for (let index = 0; index < count; index += 1) {
            const label = String.fromCharCode(65 + index);
            const previewUrl = engineConfig.previewUrl;
            const saveUrl = engineConfig.saveUrl;
            const pollUrl = engineConfig.taskUrl;
            let candidateSeed = createVoiceDesignCandidateSeed();
            while (candidateSeeds.has(candidateSeed)) candidateSeed = (candidateSeed + 1) & 0x7fffffff;
            candidateSeeds.add(candidateSeed);
            const candidatePayload = { ...payload, seed: candidateSeed };
            if (statusEl) statusEl.textContent = `Generating ${engineConfig.label} candidate ${label} of ${count} for ${displayName || speaker}...`;
            const previewResponse = await fetch(previewUrl, {
                method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(candidatePayload)
            });
            const previewData = await parseVoiceDesignApiResponse(previewResponse, `enqueue ${engineConfig.label} voice generation`);
            if (!previewResponse.ok || !previewData.success) throw new Error(previewData.error || 'Failed to enqueue preview');
            taskIds.add(previewData.job_id);
            const result = await pollVoiceDesignTask(previewData.job_id, pollUrl, `Generating ${engineConfig.label} candidate ${label} of ${count}...`);
            if (!result.audio_base64) throw new Error(`Candidate ${label} did not return audio.`);
            const candidateName = count > 1 ? `${displayName || speaker} - Candidate ${label}` : (displayName || speaker);
            const saveResponse = await fetch(saveUrl, {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    ...candidatePayload,
                    ...result,
                    name: candidateName,
                    text: result.preview_text || candidatePayload.text,
                    audio_base64: result.audio_base64,
                    instruction: result.instruction || payload.voice_design_prompt || payload.voice_type,
                    candidate_group_id: groupId,
                    candidate_label: label,
                    source_task_id: result.task_id || previewData.job_id,
                    approval_status: count > 1 ? 'pending' : 'approved'
                })
            });
            const saveData = await parseVoiceDesignApiResponse(saveResponse, `save ${engineConfig.label} voice candidate`);
            if (!saveResponse.ok || !saveData.success) throw new Error(saveData.error || 'Failed to enqueue save');
            taskIds.add(saveData.job_id);
            const saved = await pollVoiceDesignTask(saveData.job_id, pollUrl, `Saving candidate ${label}...`);
            const candidate = { ...result, ...saved, label, candidate_group_id: groupId };
            delete candidate.audio_base64;
            candidates.push(candidate);
            await Promise.allSettled([previewData.job_id, saveData.job_id].map(id =>
                fetch(engineConfig.taskUrl(id), { method: 'DELETE' })
            ));
            taskIds.delete(previewData.job_id);
            taskIds.delete(saveData.job_id);
        }
    } catch (error) {
        // Candidate groups are atomic. Do not leave a saved Candidate A behind
        // when a later candidate fails, since it cannot be safely reviewed as
        // the requested complete group.
        await Promise.allSettled(candidates
            .map(candidate => candidate?.id)
            .filter(Boolean)
            .map(id => fetch(`/api/chatterbox-voices/${encodeURIComponent(id)}`, { method: 'DELETE' })));
        throw error;
    } finally {
        await Promise.allSettled([...taskIds].map(id =>
            fetch(engineConfig.taskUrl(id), { method: 'DELETE' })
        ));
    }
    return candidates;
}

async function generateSpeakerVoicePromptBatch(speaker, displayName, statusEl, designEngine) {
    if (!speaker) return { success: false, error: 'Missing speaker name' };
    const speakerKey = normalizeSpeakerKey(speaker);
    // Remove stale review cards before attempting this speaker. A failure must
    // show as a failure, not as an apparently successful set of old candidates.
    delete speakerVoiceDesignCandidates[speakerKey];
    try {
        const candidates = await generateAndSaveVoiceCandidates(speaker, displayName, statusEl, designEngine);
        if (candidates.length > 1) {
            speakerVoiceDesignCandidates[speakerKey] = candidates;
            if (statusEl) statusEl.textContent = `Created ${candidates.length} candidates for ${displayName || speaker}; select one in Speaker Properties.`;
        } else {
            delete speakerVoiceDesignCandidates[speakerKey];
            const promptValue = (candidates[0]?.prompt_path || candidates[0]?.file_name || '').trim();
            if (promptValue) {
                turboSelectionState[speaker] = promptValue;
                document.querySelectorAll('#inline-voice-assignment-list [data-role="turbo-control"] .reference-select, #speaker-edit-modal-body [data-role="turbo-control"] .reference-select')
                    .forEach(select => {
                        if (select?.dataset?.speaker === speaker) select.value = promptValue;
                    });
            }
            updateSpeakerProfileEntry(speaker, {
                selected_voice_id: candidates[0]?.id || '',
                selected_voice_name: candidates[0]?.name || displayName || speaker,
                selected_voice_path: promptValue
            });
        }
        return { success: true, error: '' };
    } catch (error) {
        console.error('Batch voice generation failed', error);
        if (error?.code === 'VOICE_DESIGN_BACKEND_RESTART_REQUIRED') throw error;
        if (statusEl) {
            statusEl.textContent = `Failed ${speaker}: ${error.message || 'Error'}`;
        }
        return { success: false, error: error.message || 'Unknown generation error' };
    }
}

function bulkVoiceSpeakerSignature(speakers) {
    return (speakers || []).map(speaker => normalizeSpeakerKey(speaker)).join('|');
}

function hasResumableBulkVoiceGeneration(speakers) {
    const state = bulkVoiceGenerationState;
    return !!state
        && ['running', 'paused', 'interrupted'].includes(state.status)
        && state.speaker_signature === bulkVoiceSpeakerSignature(speakers)
        && Number(state.next_index || 0) < speakers.length;
}

async function persistBulkVoiceGenerationState() {
    if (!activeProjectId) return false;
    const existing = savedProjects.find(item => String(item.id) === String(activeProjectId));
    if (!existing) return false;
    const project = getProjectState();
    project.id = existing.id;
    project.name = existing.name;
    project.saved_at = new Date().toISOString();
    project.bulk_voice_generation_state = JSON.parse(JSON.stringify(bulkVoiceGenerationState));
    await saveProject(project, { render: false });
    return true;
}

async function runBatchVoiceGeneration(prefix, statusEl, progressEls = {}, completionEls = {}, options = {}) {
    const speakers = Array.isArray(currentStats?.speakers) && currentStats.speakers.length
        ? currentStats.speakers
        : [];
    if (!speakers.length) {
        showNotification('No detected speakers to generate.', 'warning');
        return;
    }
    const { container, fill, label } = progressEls;
    const { completeCard, completeSummary } = completionEls;
    if (container) {
        container.style.display = 'flex';
    }
    if (fill) {
        fill.style.width = '0%';
    }
    if (label) {
        label.textContent = `0 / ${speakers.length} complete`;
    }
    if (completeCard) {
        completeCard.classList.add('hidden');
    }
    const resume = options.resume === true && hasResumableBulkVoiceGeneration(speakers);
    const startIndex = resume ? Math.max(0, Number(bulkVoiceGenerationState.next_index || 0)) : 0;
    const failures = resume && Array.isArray(bulkVoiceGenerationState.failures)
        ? bulkVoiceGenerationState.failures.map(item => typeof item === 'string'
            ? { speaker: '', error: item }
            : { speaker: item.speaker || '', error: item.error || 'Unknown generation error' })
        : [];
    let successCount = resume ? Math.max(0, Number(bulkVoiceGenerationState.success_count || 0)) : 0;
    bulkVoiceGenerationState = {
        version: 1,
        status: 'running',
        speaker_signature: bulkVoiceSpeakerSignature(speakers),
        total_speakers: speakers.length,
        next_index: startIndex,
        success_count: successCount,
        failures,
        prefix,
        candidate_count: Math.max(1, Math.min(Number.parseInt(document.getElementById('speaker-batch-candidate-count')?.value, 10) || 1, 10)),
        design_engine: normalizeVoiceDesignEngine(options.designEngine || bulkVoiceGenerationState?.design_engine),
        started_at: resume ? bulkVoiceGenerationState.started_at : new Date().toISOString(),
        updated_at: new Date().toISOString()
    };
    await persistBulkVoiceGenerationState();
    for (let index = startIndex; index < speakers.length; index += 1) {
        const speaker = speakers[index];
        const displayName = buildBatchVoiceName(prefix, speaker);
        if (statusEl) {
            statusEl.textContent = `Processing ${index + 1} of ${speakers.length}: ${displayName}`;
        }
        if (label) {
            label.textContent = `${index} / ${speakers.length} complete`;
        }
        if (fill) {
            fill.style.width = `${Math.round((index / speakers.length) * 100)}%`;
        }
        const result = await generateSpeakerVoicePromptBatch(speaker, displayName, statusEl, bulkVoiceGenerationState.design_engine);
        if (result.success) {
            successCount += 1;
        } else {
            failures.push({ speaker, error: result.error });
        }
        bulkVoiceGenerationState.next_index = index + 1;
        bulkVoiceGenerationState.success_count = successCount;
        bulkVoiceGenerationState.failures = failures;
        bulkVoiceGenerationState.updated_at = new Date().toISOString();
        if (options.shouldPause?.()) {
            bulkVoiceGenerationState.status = 'paused';
        }
        await persistBulkVoiceGenerationState();
        if (label) {
            label.textContent = `${index + 1} / ${speakers.length} complete`;
        }
        if (fill) {
            fill.style.width = `${Math.round(((index + 1) / speakers.length) * 100)}%`;
        }
        if (bulkVoiceGenerationState.status === 'paused') {
            await refreshChatterboxVoices();
            populateReferenceSelects();
            if (statusEl) statusEl.textContent = `Paused after ${index + 1} of ${speakers.length}. Reopen this window to resume.`;
            return { paused: true, successCount, failures };
        }
    }
    await refreshChatterboxVoices();
    populateReferenceSelects();
    bulkVoiceGenerationState.status = 'completed';
    bulkVoiceGenerationState.completed_at = new Date().toISOString();
    bulkVoiceGenerationState.updated_at = bulkVoiceGenerationState.completed_at;
    await persistBulkVoiceGenerationState();
    if (statusEl) {
        statusEl.textContent = '';
    }
    if (completeSummary) {
        completeSummary.textContent = failures.length
            ? `Generated ${getVoiceDesignEngineConfig(bulkVoiceGenerationState.design_engine).label} voices for ${successCount} of ${speakers.length} speakers. Failed: ${failures.map(item => `${item.speaker}: ${item.error}`).join(' | ')}`
            : `Generated ${getVoiceDesignEngineConfig(bulkVoiceGenerationState.design_engine).label} voices for all ${speakers.length} speakers. Speakers configured for multiple candidates still require a final selection.`;
    }
    if (completeCard) {
        completeCard.classList.remove('hidden');
    }
    if (label) {
        label.textContent = `Done: ${successCount}/${speakers.length} generated.`;
    }
    if (fill) {
        fill.style.width = '100%';
    }
    if (container) {
        container.style.display = 'none';
    }
    showNotification(
        failures.length
            ? `Voice generation completed with ${failures.length} failed speaker${failures.length === 1 ? '' : 's'}. Review the batch results for details.`
            : `${getVoiceDesignEngineConfig(bulkVoiceGenerationState.design_engine).label} voice generation complete. Select final voices for any speakers configured with multiple candidates.`,
        failures.length ? 'warning' : 'success'
    );
    return { paused: false, successCount, failures };
}

function buildBatchVoiceName(prefix, speaker) {
    const trimmedPrefix = (prefix || '').trim();
    if (!trimmedPrefix) return speaker;
    return `${trimmedPrefix} ${speaker}`.trim();
}

const HELP_SECTIONS = [
    {
        id: 'help-generate',
        title: 'Generate',
        topicIds: [
            'input-text',
            'projects',
            'prep-text',
            'paralinguistic-tags',
            'text-statistics',
            'assign-voices',
            'generation-options',
            'speaker-edit'
        ]
    },
    {
        id: 'help-audio-library',
        title: 'Audio Library',
        topicIds: ['audio-library']
    },
    {
        id: 'help-available-voices',
        title: 'Available Voices',
        topicIds: [
            'available-voices',
            'kokoro-voices',
            'custom-kokoro-blends',
            'qwen-voice-creation',
            'voice-prompts'
        ]
    },
    {
        id: 'help-settings',
        title: 'Settings',
        topicIds: [
            'settings',
            'settings-quick',
            'settings-engines',
            'engine-kokoro',
            'engine-chatterbox-local',
            'engine-chatterbox-cloud',
            'engine-kokoro-cloud',
            'engine-voxcpm',
            'engine-qwen3',
            'engine-azure-speech',
            'settings-audio',
            'settings-llm'
        ]
    }
];

// Locale code to human-readable language name mapping
const LOCALE_NAMES = {
    'af-ZA': 'Afrikaans', 'am-ET': 'Amharic', 'ar-AE': 'Arabic (UAE)', 'ar-BH': 'Arabic (Bahrain)',
    'ar-DZ': 'Arabic (Algeria)', 'ar-EG': 'Arabic (Egypt)', 'ar-IQ': 'Arabic (Iraq)', 'ar-JO': 'Arabic (Jordan)',
    'ar-KW': 'Arabic (Kuwait)', 'ar-LB': 'Arabic (Lebanon)', 'ar-LY': 'Arabic (Libya)', 'ar-MA': 'Arabic (Morocco)',
    'ar-OM': 'Arabic (Oman)', 'ar-QA': 'Arabic (Qatar)', 'ar-SA': 'Arabic (Saudi)', 'ar-SY': 'Arabic (Syria)',
    'ar-TN': 'Arabic (Tunisia)', 'ar-YE': 'Arabic (Yemen)', 'az-AZ': 'Azerbaijani', 'bg-BG': 'Bulgarian',
    'bn-BD': 'Bengali (Bangladesh)', 'bn-IN': 'Bengali (India)', 'bs-BA': 'Bosnian', 'ca-ES': 'Catalan',
    'cs-CZ': 'Czech', 'cy-GB': 'Welsh', 'da-DK': 'Danish', 'de-AT': 'German (Austria)', 'de-CH': 'German (Swiss)',
    'de-DE': 'German', 'el-GR': 'Greek', 'en-AU': 'English (AU)', 'en-CA': 'English (CA)', 'en-GB': 'English (UK)',
    'en-HK': 'English (HK)', 'en-IE': 'English (IE)', 'en-IN': 'English (IN)', 'en-KE': 'English (KE)',
    'en-NG': 'English (NG)', 'en-NZ': 'English (NZ)', 'en-PH': 'English (PH)', 'en-SG': 'English (SG)',
    'en-TZ': 'English (TZ)', 'en-US': 'English (US)', 'en-ZA': 'English (ZA)', 'es-AR': 'Spanish (AR)',
    'es-BO': 'Spanish (BO)', 'es-CL': 'Spanish (CL)', 'es-CO': 'Spanish (CO)', 'es-CR': 'Spanish (CR)',
    'es-CU': 'Spanish (CU)', 'es-DO': 'Spanish (DO)', 'es-EC': 'Spanish (EC)', 'es-ES': 'Spanish (ES)',
    'es-GQ': 'Spanish (GQ)', 'es-GT': 'Spanish (GT)', 'es-HN': 'Spanish (HN)', 'es-MX': 'Spanish (MX)',
    'es-NI': 'Spanish (NI)', 'es-PA': 'Spanish (PA)', 'es-PE': 'Spanish (PE)', 'es-PR': 'Spanish (PR)',
    'es-PY': 'Spanish (PY)', 'es-SV': 'Spanish (SV)', 'es-US': 'Spanish (US)', 'es-UY': 'Spanish (UY)',
    'es-VE': 'Spanish (VE)', 'et-EE': 'Estonian', 'eu-ES': 'Basque', 'fa-IR': 'Persian', 'fi-FI': 'Finnish',
    'fil-PH': 'Filipino', 'fr-BE': 'French (BE)', 'fr-CA': 'French (CA)', 'fr-CH': 'French (CH)', 'fr-FR': 'French',
    'ga-IE': 'Irish', 'gl-ES': 'Galician', 'gu-IN': 'Gujarati', 'he-IL': 'Hebrew', 'hi-IN': 'Hindi',
    'hr-HR': 'Croatian', 'hu-HU': 'Hungarian', 'hy-AM': 'Armenian', 'id-ID': 'Indonesian', 'is-IS': 'Icelandic',
    'it-IT': 'Italian', 'ja-JP': 'Japanese', 'jv-ID': 'Javanese', 'ka-GE': 'Georgian', 'kk-KZ': 'Kazakh',
    'km-KH': 'Khmer', 'kn-IN': 'Kannada', 'ko-KR': 'Korean', 'lo-LA': 'Lao', 'lt-LT': 'Lithuanian',
    'lv-LV': 'Latvian', 'mk-MK': 'Macedonian', 'ml-IN': 'Malayalam', 'mn-MN': 'Mongolian', 'mr-IN': 'Marathi',
    'ms-MY': 'Malay', 'mt-MT': 'Maltese', 'my-MM': 'Burmese', 'nb-NO': 'Norwegian', 'ne-NP': 'Nepali',
    'nl-BE': 'Dutch (BE)', 'nl-NL': 'Dutch', 'pl-PL': 'Polish', 'ps-AF': 'Pashto', 'pt-BR': 'Portuguese (BR)',
    'pt-PT': 'Portuguese', 'ro-RO': 'Romanian', 'ru-RU': 'Russian', 'si-LK': 'Sinhala', 'sk-SK': 'Slovak',
    'sl-SI': 'Slovenian', 'so-SO': 'Somali', 'sq-AL': 'Albanian', 'sr-RS': 'Serbian', 'su-ID': 'Sundanese',
    'sv-SE': 'Swedish', 'sw-KE': 'Swahili (KE)', 'sw-TZ': 'Swahili (TZ)', 'ta-IN': 'Tamil (IN)',
    'ta-LK': 'Tamil (LK)', 'ta-MY': 'Tamil (MY)', 'ta-SG': 'Tamil (SG)', 'te-IN': 'Telugu', 'th-TH': 'Thai',
    'tr-TR': 'Turkish', 'uk-UA': 'Ukrainian', 'ur-IN': 'Urdu (IN)', 'ur-PK': 'Urdu (PK)', 'uz-UZ': 'Uzbek',
    'vi-VN': 'Vietnamese', 'wuu-CN': 'Wu Chinese', 'yue-CN': 'Cantonese', 'zh-CN': 'Chinese (Mandarin)',
    'zh-HK': 'Chinese (HK)', 'zh-TW': 'Chinese (TW)', 'zu-ZA': 'Zulu',
};

function getLanguageDisplayName(localeCode) {
    if (!localeCode) return '';
    return LOCALE_NAMES[localeCode] || localeCode;
}

function openLegacyHelpModal(helpId) {
    const topic = HELP_TOPICS[helpId];
    if (!topic) return;
    const overlay = document.getElementById('help-modal-overlay');
    const modal = document.getElementById('help-modal');
    const title = document.getElementById('help-modal-title');
    const body = document.getElementById('help-modal-body');
    if (!overlay || !modal || !title || !body) return;
    title.textContent = topic.title;
    body.innerHTML = topic.body;
    overlay.classList.remove('hidden');
    modal.classList.remove('hidden');
}

function stopSpeakerPreviewAudio() {
    if (currentFxPreviewAudio) {
        currentFxPreviewAudio.pause();
        currentFxPreviewAudio.currentTime = 0;
        currentFxPreviewAudio = null;
    }
    if (currentFxPreviewButton) {
        currentFxPreviewButton.classList.remove('is-playing');
        currentFxPreviewButton.textContent = currentFxPreviewButton.dataset.labelPlay || 'Quick Test';
        currentFxPreviewButton.disabled = false;
        currentFxPreviewButton = null;
    }
    if (window.chatterboxPreviewController) {
        window.chatterboxPreviewController.stop();
    }
}

function closeHelpModal() {
    const overlay = document.getElementById('help-modal-overlay');
    const modal = document.getElementById('help-modal');
    if (overlay) overlay.classList.add('hidden');
    if (modal) modal.classList.add('hidden');
}

function stripHelpHtml(html) {
    if (!html) return '';
    return html.replace(/<[^>]+>/g, ' ').replace(/\s+/g, ' ').trim();
}

function buildHelpSectionMap() {
    return HELP_SECTIONS.reduce((acc, section) => {
        section.topicIds.forEach(topicId => {
            acc[topicId] = section.title;
        });
        return acc;
    }, {});
}

function openHelpSearchModal() {
    const overlay = document.getElementById('help-search-modal-overlay');
    const modal = document.getElementById('help-search-modal');
    if (!overlay || !modal) return;
    overlay.classList.remove('hidden');
    modal.classList.remove('hidden');
    const input = document.getElementById('help-search-input');
    if (input) {
        input.focus();
        input.select();
    }
}

function closeHelpSearchModal() {
    const overlay = document.getElementById('help-search-modal-overlay');
    const modal = document.getElementById('help-search-modal');
    if (overlay) overlay.classList.add('hidden');
    if (modal) modal.classList.add('hidden');
}

function renderHelpSearchResults(query, searchIndex, sectionMap) {
    const resultsContainer = document.getElementById('help-search-results');
    if (!resultsContainer) return;
    const trimmed = query.trim().toLowerCase();
    const matches = searchIndex.filter(item => {
        if (!trimmed) return true;
        return item.title.includes(trimmed) || item.body.includes(trimmed) || item.section.includes(trimmed);
    });
    resultsContainer.innerHTML = '';
    if (!matches.length) {
        const empty = document.createElement('div');
        empty.className = 'help-search-empty';
        empty.textContent = 'No results. Try a different keyword.';
        resultsContainer.appendChild(empty);
        return;
    }
    matches.forEach(match => {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'help-search-result';
        button.innerHTML = `
            <span class="help-search-result-title">${HELP_TOPICS[match.id].title}</span>
            <span class="help-search-result-meta">${sectionMap[match.id] || 'Help'}</span>
        `;
        button.addEventListener('click', () => {
            closeHelpSearchModal();
            openLegacyHelpModal(match.id);
        });
        resultsContainer.appendChild(button);
    });
}

const KITTEN_TTS_VOICES = ['Bella', 'Jasper', 'Luna', 'Bruno', 'Rosie', 'Hugo', 'Kiki', 'Leo'];

function appendKittenVoiceOptions(selectElement) {
    KITTEN_TTS_VOICES.forEach(voiceName => {
        const option = document.createElement('option');
        option.value = voiceName;
        option.textContent = voiceName;
        selectElement.appendChild(option);
    });
}

function appendPocketPresetVoiceOptions(selectElement) {
    const voices = Array.isArray(window.availablePocketTtsVoices)
        ? window.availablePocketTtsVoices
        : [];
    voices.forEach(voiceName => {
        const option = document.createElement('option');
        option.value = voiceName;
        option.textContent = voiceName;
        selectElement.appendChild(option);
    });
}

function buildHelpTopicsList() {
    const container = document.getElementById('help-topics-list');
    if (!container) return;
    container.innerHTML = '';
    HELP_SECTIONS.forEach((section, index) => {
        const topics = section.topicIds
            .map(topicId => ({ topicId, topic: HELP_TOPICS[topicId] }))
            .filter(entry => entry.topic);
        if (!topics.length) return;
        const sectionEl = document.createElement('div');
        sectionEl.className = 'help-topics-section';
        if (index > 0) {
            sectionEl.classList.add('collapsed');
        }
        sectionEl.innerHTML = `
            <button type="button" class="help-topics-section-header">
                <span class="help-topics-section-title">${section.title}</span>
                <span class="help-topics-section-toggle">${index > 0 ? '▶' : '▼'}</span>
            </button>
            <div class="help-topics-section-content">
                <div class="help-topics-grid"></div>
            </div>
        `;
        const grid = sectionEl.querySelector('.help-topics-grid');
        topics.forEach(({ topicId, topic }) => {
            const card = document.createElement('button');
            card.type = 'button';
            card.className = 'help-topic-card';
            card.dataset.helpId = topicId;
            card.innerHTML = `
                <div class="help-topic-title">${topic.title}</div>
                <div class="help-topic-description">Click to read more.</div>
            `;
            card.addEventListener('click', () => openLegacyHelpModal(topicId));
            grid.appendChild(card);
        });
        const header = sectionEl.querySelector('.help-topics-section-header');
        const toggle = sectionEl.querySelector('.help-topics-section-toggle');
        if (header && toggle) {
            header.addEventListener('click', () => {
                sectionEl.classList.toggle('collapsed');
                toggle.textContent = sectionEl.classList.contains('collapsed') ? '▶' : '▼';
            });
        }
        container.appendChild(sectionEl);
    });
}

function initLegacyHelpSystem() {
    document.querySelectorAll('.help-icon').forEach(icon => {
        icon.addEventListener('click', event => {
            event.stopPropagation();
            event.preventDefault();
            const target = event.currentTarget;
            const helpId = target.dataset.helpId;
            openLegacyHelpModal(helpId);
        });
    });
    const overlay = document.getElementById('help-modal-overlay');
    if (overlay) {
        overlay.addEventListener('click', event => {
            if (event.target === overlay) {
                closeHelpModal();
            }
        });
    }
    document.getElementById('help-modal-close')?.addEventListener('click', closeHelpModal);
    document.getElementById('help-modal-close-btn')?.addEventListener('click', closeHelpModal);
    const searchBtn = document.getElementById('help-search-btn');
    const searchOverlay = document.getElementById('help-search-modal-overlay');
    const searchClose = document.getElementById('help-search-modal-close');
    const searchCloseBtn = document.getElementById('help-search-close-btn');
    const searchInput = document.getElementById('help-search-input');
    const sectionMap = buildHelpSectionMap();
    const searchIndex = Object.entries(HELP_TOPICS).map(([id, topic]) => {
        return {
            id,
            title: (topic.title || '').toLowerCase(),
            body: stripHelpHtml(topic.body).toLowerCase(),
            section: (sectionMap[id] || '').toLowerCase()
        };
    });
    if (searchBtn) {
        searchBtn.addEventListener('click', () => {
            openHelpSearchModal();
            if (searchInput) {
                searchInput.value = '';
                renderHelpSearchResults('', searchIndex, sectionMap);
            }
        });
    }
    if (searchInput) {
        searchInput.addEventListener('input', event => {
            renderHelpSearchResults(event.target.value || '', searchIndex, sectionMap);
        });
    }
    if (searchOverlay) {
        searchOverlay.addEventListener('click', event => {
            if (event.target === searchOverlay) {
                closeHelpSearchModal();
            }
        });
    }
    searchClose?.addEventListener('click', closeHelpSearchModal);
    searchCloseBtn?.addEventListener('click', closeHelpSearchModal);
    buildHelpTopicsList();
}

function resolveBookTitleFromSections(sections) {
    if (!Array.isArray(sections)) return '';
    for (const section of sections) {
        const rawTitle = (section?.title || '').trim();
        if (!rawTitle) continue;
        const title = rawTitle.split('—')[0].trim();
        const lower = title.toLowerCase();
        if (!lower || lower === 'full story' || lower === 'title') continue;
        if (/^(chapter|section|book|part|letter|prologue|epilogue)\b/i.test(title)) {
            continue;
        }
        return title;
    }
    return '';
}

async function fetchSpeakerProfiles() {
    if (!currentStats?.speakers?.length) {
        setSpeakerProfiles({});
        return;
    }
    const contextParts = [];
    if (latestGeminiBookTitle) {
        contextParts.push(`Book title: ${latestGeminiBookTitle}`);
    }
    const context = contextParts.join('\n');
    const promptOverride = document.getElementById('gemini-speaker-profile-prompt')?.value?.trim() || '';
    const processedText = document.getElementById('input-text')?.value?.trim() || '';
    try {
        const response = await fetch('/api/gemini/speaker-profiles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                speakers: currentStats.speakers,
                context,
                prompt_override: promptOverride || undefined,
                processed_text: processedText || undefined
            })
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to build speaker profiles');
        }
        setSpeakerProfiles(data.profiles || {});
        if (activeSpeakerModal) {
            renderSpeakerProfileSummary(activeSpeakerModal);
        }
        const missingSpeakers = Array.isArray(data.missing_speakers) ? data.missing_speakers : [];
        if (missingSpeakers.length) {
            showNotification(
                `Speaker profiles generated, but ${missingSpeakers.length} speaker${missingSpeakers.length === 1 ? '' : 's'} still need a profile: ${missingSpeakers.join(', ')}`,
                'warning'
            );
        } else {
            showNotification('Speaker profiles and voice types generated.', 'success');
        }
    } catch (error) {
        console.error('Speaker profile generation failed:', error);
        showNotification(error.message || 'Failed to generate speaker profiles.', 'warning');
    }
}

function readLegacyBrowserProjects() {
    try {
        const projects = JSON.parse(localStorage.getItem(PROJECT_STORAGE_KEY) || '[]');
        return Array.isArray(projects) ? projects.filter(project => project && typeof project === 'object') : [];
    } catch (error) {
        console.warn('Unable to read legacy browser projects', error);
        return [];
    }
}

async function initializeProjectLibrary() {
    if (projectLibraryPromise) return projectLibraryPromise;
    projectLibraryPromise = (async () => {
        const legacyProjects = readLegacyBrowserProjects();
        const response = await fetch(legacyProjects.length ? '/api/projects/import' : '/api/projects', {
            method: legacyProjects.length ? 'POST' : 'GET',
            headers: legacyProjects.length ? { 'Content-Type': 'application/json' } : undefined,
            body: legacyProjects.length ? JSON.stringify({ projects: legacyProjects }) : undefined
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Unable to load the shared project library.');
        }
        savedProjects = Array.isArray(data.projects) ? data.projects : [];
        if (legacyProjects.length) {
            // Only remove origin-specific storage after the backend confirms the
            // projects were merged into the shared library.
            localStorage.removeItem(PROJECT_STORAGE_KEY);
        }
        return savedProjects;
    })().catch(error => {
        projectLibraryPromise = null;
        const legacyProjects = readLegacyBrowserProjects();
        if (legacyProjects.length) savedProjects = legacyProjects;
        throw error;
    });
    return projectLibraryPromise;
}

async function refreshProjectLibrary() {
    await initializeProjectLibrary();
    const response = await fetch('/api/projects');
    const data = await response.json();
    if (!response.ok || !data.success) {
        throw new Error(data.error || 'Unable to refresh the shared project library.');
    }
    savedProjects = Array.isArray(data.projects) ? data.projects : [];
    return savedProjects;
}

async function saveProject(project, { render = true } = {}) {
    if (!project) return null;
    const response = await fetch('/api/projects', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ project })
    });
    const data = await response.json();
    if (!response.ok || !data.success) {
        throw new Error(data.error || 'Unable to save the project.');
    }
    const saved = data.project;
    const matchIndex = savedProjects.findIndex(item => String(item.id) === String(saved.id));
    if (matchIndex >= 0) savedProjects[matchIndex] = saved;
    else savedProjects.push(saved);
    if (render) renderProjectList();
    return saved;
}

async function deleteProject(projectId) {
    const response = await fetch(`/api/projects/${encodeURIComponent(projectId)}`, { method: 'DELETE' });
    const data = await response.json();
    if (!response.ok || !data.success) {
        throw new Error(data.error || 'Unable to delete the project.');
    }
    savedProjects = savedProjects.filter(item => String(item.id) !== String(projectId));
    renderProjectList();
}

function formatSpeakerTagName(value) {
    const raw = (value || '').toString().trim().toLowerCase();
    if (!raw) return '';
    const spaced = raw.replace(/\s+/g, '-');
    const cleaned = spaced.replace(/[^a-z0-9_-]/g, '');
    return cleaned.replace(/-+/g, '-').replace(/^-+|-+$/g, '');
}

function appendQwen3VoiceOptions(selectElement) {
    if (!qwen3Metadata || !Array.isArray(qwen3Metadata.speakers)) {
        return;
    }
    qwen3Metadata.speakers.forEach(speaker => {
        const option = document.createElement('option');
        option.value = speaker;
        option.textContent = speaker;
        selectElement.appendChild(option);
    });
}

async function loadQwen3Metadata(force = false) {
    if (qwen3Metadata && !force) {
        populateQwen3Controls();
        return;
    }
    try {
        const response = await fetch('/api/qwen3/metadata');
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to load Qwen3 metadata');
        }
        qwen3Metadata = {
            speakers: data.speakers || [],
            languages: data.languages || []
        };
        populateQwen3Controls();
    } catch (error) {
        console.error('Failed to load Qwen3 metadata:', error);
    }
}

function populateQwen3Controls() {
    const speakerSelect = document.getElementById('qwen3-default-speaker');
    const languageSelect = document.getElementById('qwen3-default-language');
    if (speakerSelect && qwen3Metadata?.speakers) {
        const previous = speakerSelect.value;
        speakerSelect.innerHTML = '<option value="">Select Qwen3 speaker...</option>';
        qwen3Metadata.speakers.forEach(speaker => {
            const option = document.createElement('option');
            option.value = speaker;
            option.textContent = speaker;
            speakerSelect.appendChild(option);
        });
        if (previous) speakerSelect.value = previous;
    }
    if (languageSelect && qwen3Metadata?.languages) {
        const previous = languageSelect.value;
        languageSelect.innerHTML = '<option value="Auto">Auto</option>';
        qwen3Metadata.languages.forEach(language => {
            const option = document.createElement('option');
            option.value = language;
            option.textContent = language;
            languageSelect.appendChild(option);
        });
        if (previous) languageSelect.value = previous;
    }
    // Also update multi-voice assignment dropdowns if Qwen3 is selected
    const engineName = getSelectedJobEngine() || runtimeSettings?.tts_engine || 'kokoro';
    if (isQwenEngine(engineName)) {
        populateVoiceSelects();
    }
}

// Voice dropdown filter state
let voiceDropdownFilters = {
    gender: 'all',
    language: 'all'
};

function preloadGenerationControls() {
    fetch('/api/settings')
        .then(resp => resp.json())
        .then(data => {
            if (!data?.success || !data.settings) return;
            const settings = data.settings;
            runtimeSettings = settings;
            setAvailableGeminiPresets(settings.gemini_prompt_presets || []);
            const formatSelect = document.getElementById('job-output-format');
            const bitrateSelect = document.getElementById('job-output-bitrate');
            if (formatSelect && settings.output_format) {
                formatSelect.value = settings.output_format;
                handleOutputFormatChange(formatSelect.value);
                refreshGlobalChatterboxPreviewButton();
}
            if (bitrateSelect && settings.output_bitrate_kbps) {
                bitrateSelect.value = String(settings.output_bitrate_kbps);
            }
            applyEngineDefaults(settings);
        })
        .catch(err => {
            console.error('Failed to preload output controls', err);
        });
}

function handleChatterboxVoicesUpdated(event) {
    const voices = Array.isArray(event?.detail?.voices) ? event.detail.voices : [];
    availableChatterboxVoices = voices;
    updateVoiceDropdownFilterOptions();
    populateReferenceSelects();
    refreshGlobalChatterboxPreviewButton();
}

function handleOutputFormatChange(value) {
    const bitrateSelect = document.getElementById('job-output-bitrate');
    if (!bitrateSelect) return;
    const isMp3 = value === 'mp3';
    bitrateSelect.disabled = !isMp3;
    bitrateSelect.parentElement?.classList.toggle('disabled', !isMp3);
}

function applyEngineDefaults(settings) {
    const engineSelect = document.getElementById('job-tts-engine');
    const defaultEngine = (settings.tts_engine || 'kokoro').toLowerCase();
    if (engineSelect) {
        engineSelect.value = defaultEngine;
    }
    hydrateTurboLocalJobFields(settings);
    hydrateTurboReplicateJobFields(settings);
    updateEngineUI(defaultEngine);
}

function updateJobEngineOptionVisibility(engineName) {
    const jobTurboLocal = document.getElementById('job-chatterbox-turbo-local-options');
    const jobTurboReplicate = document.getElementById('job-chatterbox-turbo-replicate-options');
    if (jobTurboLocal) {
        jobTurboLocal.style.display = engineName === 'chatterbox_turbo_local' ? 'grid' : 'none';
    }
    if (jobTurboReplicate) {
        jobTurboReplicate.style.display = engineName === 'chatterbox_turbo_replicate' ? 'grid' : 'none';
    }
}

function hydrateTurboLocalJobFields(settings) {
    const promptInput = document.getElementById('job-turbo-local-prompt');
    const tempInput = document.getElementById('job-turbo-local-temperature');
    const topPInput = document.getElementById('job-turbo-local-top-p');
    const topKInput = document.getElementById('job-turbo-local-top-k');
    const repPenaltyInput = document.getElementById('job-turbo-local-rep-penalty');
    const cfgInput = document.getElementById('job-turbo-local-cfg-weight');
    const exaggerationInput = document.getElementById('job-turbo-local-exaggeration');
    const normCheck = document.getElementById('job-turbo-local-norm');
    const promptNormCheck = document.getElementById('job-turbo-local-prompt-norm');

    if (promptInput) {
        promptInput.placeholder = settings.chatterbox_turbo_local_default_prompt || promptInput.placeholder;
    }
    if (tempInput) {
        tempInput.value = settings.chatterbox_turbo_local_temperature ?? 0.8;
    }
    if (topPInput) {
        topPInput.value = settings.chatterbox_turbo_local_top_p ?? 0.95;
    }
    if (topKInput) {
        topKInput.value = settings.chatterbox_turbo_local_top_k ?? 1000;
    }
    if (repPenaltyInput) {
        repPenaltyInput.value = settings.chatterbox_turbo_local_repetition_penalty ?? 1.2;
    }
    if (cfgInput) {
        cfgInput.value = settings.chatterbox_turbo_local_cfg_weight ?? 0.0;
    }
    if (exaggerationInput) {
        exaggerationInput.value = settings.chatterbox_turbo_local_exaggeration ?? 0.0;
    }
    if (normCheck) {
        normCheck.checked = settings.chatterbox_turbo_local_norm_loudness !== false;
    }
    if (promptNormCheck) {
        promptNormCheck.checked = settings.chatterbox_turbo_local_prompt_norm_loudness !== false;
    }
}

function hydrateTurboReplicateJobFields(settings) {
    const modelInput = document.getElementById('job-turbo-replicate-model');
    const voiceInput = document.getElementById('job-turbo-replicate-voice');
    const tempInput = document.getElementById('job-turbo-replicate-temperature');
    const topPInput = document.getElementById('job-turbo-replicate-top-p');
    const topKInput = document.getElementById('job-turbo-replicate-top-k');
    const repPenaltyInput = document.getElementById('job-turbo-replicate-rep-penalty');
    const seedInput = document.getElementById('job-turbo-replicate-seed');

    if (modelInput) {
        modelInput.placeholder = settings.chatterbox_turbo_replicate_model || modelInput.placeholder;
    }
    if (voiceInput) {
        voiceInput.placeholder = settings.chatterbox_turbo_replicate_voice || voiceInput.placeholder;
    }
    if (tempInput) {
        tempInput.value = settings.chatterbox_turbo_replicate_temperature ?? 0.8;
    }
    if (topPInput) {
        topPInput.value = settings.chatterbox_turbo_replicate_top_p ?? 0.95;
    }
    if (topKInput) {
        topKInput.value = settings.chatterbox_turbo_replicate_top_k ?? 1000;
    }
    if (repPenaltyInput) {
        repPenaltyInput.value = settings.chatterbox_turbo_replicate_repetition_penalty ?? 1.2;
    }
    if (seedInput) {
        const seed = settings.chatterbox_turbo_replicate_seed;
        seedInput.value = seed === null || seed === undefined ? '' : seed;
    }
}

async function loadAzureSpeechVoices(force = false) {
    if (azureSpeechVoices.length && !force) return azureSpeechVoices;
    if (azureSpeechVoicesPromise && !force) return azureSpeechVoicesPromise;
    azureSpeechVoicesPromise = (async () => {
        const response = await fetch(`/api/azure-speech/voices${force ? '?force=true' : ''}`);
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Unable to load Azure Speech voices.');
        }
        azureSpeechVoices = Array.isArray(data.voices) ? data.voices : [];
        window.availableAzureSpeechVoices = azureSpeechVoices;
        populateVoiceSelects();
        return azureSpeechVoices;
    })();
    try {
        return await azureSpeechVoicesPromise;
    } catch (error) {
        showNotification(error.message || 'Unable to load Azure Speech voices.', 'warning');
        if (isAzureSpeechEngine(getSelectedJobEngine() || runtimeSettings?.tts_engine)) {
            setCatalogVoicePlaceholder('Configure Azure Speech in Settings');
        }
        return [];
    } finally {
        azureSpeechVoicesPromise = null;
    }
}

async function loadEdgeTtsVoices(force = false) {
    if (edgeTtsVoices.length && !force) return edgeTtsVoices;
    if (edgeTtsVoicesPromise && !force) return edgeTtsVoicesPromise;
    edgeTtsVoicesPromise = (async () => {
        const response = await fetch(`/api/edge-tts/voices${force ? '?force=true' : ''}`);
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to load Edge TTS voices.');
        edgeTtsVoices = Array.isArray(data.voices) ? data.voices : [];
        window.availableEdgeTtsVoices = edgeTtsVoices;
        populateDefaultVoiceSelect();
        populateVoiceSelects();
        return edgeTtsVoices;
    })();
    try {
        return await edgeTtsVoicesPromise;
    } catch (error) {
        showNotification(error.message || 'Unable to load Edge TTS voices.', 'warning');
        if (isEdgeTtsEngine(getSelectedJobEngine() || runtimeSettings?.tts_engine)) {
            setCatalogVoicePlaceholder('Unable to load Edge voices');
        }
        return [];
    } finally {
        edgeTtsVoicesPromise = null;
    }
}

async function loadElevenLabsCatalog(force = false) {
    if (elevenLabsVoices.length && elevenLabsModels.length && !force) {
        return { voices: elevenLabsVoices, models: elevenLabsModels };
    }
    if (elevenLabsCatalogPromise && !force) return elevenLabsCatalogPromise;
    elevenLabsCatalogPromise = (async () => {
        const response = await fetch(`/api/elevenlabs/catalog${force ? '?force=true' : ''}`);
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to load ElevenLabs.');
        elevenLabsVoices = Array.isArray(data.voices) ? data.voices : [];
        elevenLabsModels = Array.isArray(data.models) ? data.models : [];
        window.availableElevenLabsVoices = elevenLabsVoices;
        window.availableElevenLabsModels = elevenLabsModels;
        populateDefaultVoiceSelect();
        populateVoiceSelects();
        return data;
    })();
    try {
        return await elevenLabsCatalogPromise;
    } catch (error) {
        showNotification(error.message || 'Unable to load ElevenLabs.', 'warning');
        if (isElevenLabsEngine(getSelectedJobEngine() || runtimeSettings?.tts_engine)) {
            setCatalogVoicePlaceholder('Configure ElevenLabs in Settings');
        }
        return { voices: [], models: [] };
    } finally {
        elevenLabsCatalogPromise = null;
    }
}

async function loadOpenAITtsCatalog(force = false) {
    if (openAITtsVoices.length && !force) return { voices: openAITtsVoices };
    if (openAITtsCatalogPromise && !force) return openAITtsCatalogPromise;
    openAITtsCatalogPromise = (async () => {
        const response = await fetch('/api/openai-tts/catalog');
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to load OpenAI TTS voices.');
        openAITtsVoices = Array.isArray(data.voices) ? data.voices : [];
        window.availableOpenAITtsVoices = openAITtsVoices;
        populateDefaultVoiceSelect();
        populateVoiceSelects();
        return data;
    })();
    try {
        return await openAITtsCatalogPromise;
    } catch (error) {
        showNotification(error.message || 'Unable to load OpenAI TTS voices.', 'warning');
        return { voices: [] };
    } finally {
        openAITtsCatalogPromise = null;
    }
}

async function loadLocalAITtsCatalog(force = false) {
    if (localAITtsVoices.length && !force) return { voices: localAITtsVoices, models: localAITtsModels };
    if (localAITtsCatalogPromise && !force) return localAITtsCatalogPromise;
    localAITtsCatalogPromise = (async () => {
        const response = await fetch('/api/localai-tts/catalog');
        const data = await response.json();
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to load LocalAI TTS voices.');
        localAITtsVoices = Array.isArray(data.voices) ? data.voices : [];
        localAITtsModels = Array.isArray(data.models) ? data.models : [];
        window.availableLocalAITtsVoices = localAITtsVoices;
        populateDefaultVoiceSelect();
        populateVoiceSelects();
        return data;
    })();
    try {
        return await localAITtsCatalogPromise;
    } catch (error) {
        showNotification(error.message || 'Unable to load LocalAI TTS voices.', 'warning');
        if (isLocalAITtsEngine(getSelectedJobEngine() || runtimeSettings?.tts_engine)) {
            setCatalogVoicePlaceholder('Configure LocalAI TTS in Settings');
        }
        return { voices: [], models: [] };
    } finally {
        localAITtsCatalogPromise = null;
    }
}

function getAzureVoice(voiceName) {
    return azureSpeechVoices.find(voice => voice.short_name === voiceName) || null;
}

function getAzureAssignmentRow(speaker) {
    return document.querySelector(
        `#speaker-edit-modal-body .voice-assignment-row[data-speaker="${speaker}"]`
    ) || document.querySelector(
        `#inline-voice-assignment-list .voice-assignment-row[data-speaker="${speaker}"]`
    );
}

function readAzureVoiceOptions(row) {
    if (!row) return {};
    return {
        style: row.querySelector('.azure-style-select')?.value || '',
        role: row.querySelector('.azure-role-select')?.value || '',
        style_degree: parseFloat(row.querySelector('.azure-style-degree')?.value) || 1,
        volume: parseFloat(row.querySelector('.azure-volume')?.value) || 0,
    };
}

function rememberAzureVoiceOptions(row) {
    const speaker = row?.dataset?.speaker;
    if (speaker) azureVoiceOptionState[speaker] = readAzureVoiceOptions(row);
}

function replaceAzureOptionList(select, values, emptyLabel, preferredValue = '') {
    if (!select) return;
    const selected = preferredValue || select.value || '';
    select.innerHTML = `<option value="">${emptyLabel}</option>`;
    (values || []).forEach(value => {
        const option = document.createElement('option');
        option.value = value;
        option.textContent = value;
        select.appendChild(option);
    });
    select.value = Array.from(select.options).some(option => option.value === selected) ? selected : '';
}

function updateAzureVoiceControls(row, preferredOptions = null) {
    if (!row) return;
    const speaker = row.dataset.speaker || 'default';
    const options = preferredOptions || azureVoiceOptionState[speaker] || readAzureVoiceOptions(row);
    const voiceName = row.querySelector('.voice-select')?.value || '';
    const voice = getAzureVoice(voiceName);
    replaceAzureOptionList(row.querySelector('.azure-style-select'), voice?.styles || [], 'Neutral', options.style);
    replaceAzureOptionList(row.querySelector('.azure-role-select'), voice?.roles || [], 'Default role', options.role);
    const degree = row.querySelector('.azure-style-degree');
    const volume = row.querySelector('.azure-volume');
    if (degree) degree.value = Math.max(0.01, Math.min(2, Number(options.style_degree) || 1));
    if (volume) volume.value = Math.max(-100, Math.min(100, Number(options.volume) || 0));
    const info = row.querySelector('[data-role="azure-voice-info"]');
    if (info) {
        info.textContent = voice
            ? `${voice.locale_name || voice.locale} · ${voice.gender || 'Unknown'} · ${voice.sample_rate_hertz || '?'} Hz`
            : 'Select an Azure voice to see its supported styles and roles.';
    }
    rememberAzureVoiceOptions(row);
}

function collectAzureVoiceOptions(row, voiceName) {
    const selected = readAzureVoiceOptions(row);
    const voice = getAzureVoice(voiceName);
    const extra = { locale: voice?.locale || '' };
    if (selected.style) {
        extra.style = selected.style;
        extra.style_degree = Math.max(0.01, Math.min(2, Number(selected.style_degree) || 1));
    }
    if (selected.role) extra.role = selected.role;
    if (Math.abs(Number(selected.volume) || 0) > 0.01) {
        extra.volume = Math.max(-100, Math.min(100, Number(selected.volume)));
    }
    return extra;
}

function isTurboEngine(engineName) {
    const value = (engineName || '').toLowerCase();
    return value === 'chatterbox_turbo_local'
        || value === 'chatterbox_turbo_replicate'
        || value === 'voxcpm_local'
        || value === 'qwen3_clone'
        || value === 'omnivoice_clone'
        || value === 'dots_tts'
        || value === 'audio8_tts'
        || value === 'breeze_tts_2';
}

function isPromptEngine(engineName) {
    const value = (engineName || '').toLowerCase();
    return isTurboEngine(value) || value === 'pocket_tts' || value === 'index_tts' || value === 'breeze_api';
}

function isOmniVoiceEngine(engineName) {
    const value = (engineName || '').toLowerCase();
    return value === 'omnivoice_clone' || value === 'omnivoice_design';
}

function isOmniVoiceCloneEngine(engineName) {
    return (engineName || '').toLowerCase() === 'omnivoice_clone';
}

function isOmniVoiceDesignEngine(engineName) {
    return (engineName || '').toLowerCase() === 'omnivoice_design';
}

function isPocketPresetEngine(engineName) {
    return (engineName || '').toLowerCase() === 'pocket_tts_preset';
}

function isKokoroEngine(engineName) {
    const value = (engineName || '').toLowerCase();
    return value === 'kokoro' || value === 'kokoro_replicate';
}

function isQwenEngine(engineName) {
    return (engineName || '').toLowerCase() === 'qwen3_custom';
}

function isKittenEngine(engineName) {
    return (engineName || '').toLowerCase() === 'kitten_tts';
}

function isIndexTTSEngine(engineName) {
    return (engineName || '').toLowerCase() === 'index_tts';
}

function isDotsTTSEngine(engineName) {
    return (engineName || '').toLowerCase() === 'dots_tts';
}

function isAzureSpeechEngine(engineName) {
    return (engineName || '').toLowerCase() === 'azure_speech';
}

function isEdgeTtsEngine(engineName) {
    return (engineName || '').toLowerCase() === 'edge_tts';
}

function isElevenLabsEngine(engineName) {
    return (engineName || '').toLowerCase() === 'elevenlabs';
}

function isOpenAITtsEngine(engineName) {
    return (engineName || '').toLowerCase() === 'openai_tts';
}

function isLocalAITtsEngine(engineName) {
    return (engineName || '').toLowerCase() === 'localai_tts';
}

function isCatalogCloudEngine(engineName) {
    if (engineName === 'breeze_api') return true;
    return isAzureSpeechEngine(engineName) || isEdgeTtsEngine(engineName) || isElevenLabsEngine(engineName) || isOpenAITtsEngine(engineName) || isLocalAITtsEngine(engineName);
}

function isQwenCloneEngine(engineName) {
    return (engineName || '').toLowerCase() === 'qwen3_clone';
}

function updateEngineUI(engineName) {
    updateJobEngineOptionVisibility(engineName);
    const kokoroCard = document.getElementById('kokoro-default-voice-card');
    const turboCard = document.getElementById('chatterbox-turbo-voice-card');
    const qwenCard = document.getElementById('qwen3-voice-card');
    const paralinguisticTagsBar = document.getElementById('paralinguistic-tags-bar');
    const isTurbo = isTurboEngine(engineName);
    const isPrompt = isPromptEngine(engineName);
    const isQwen = isQwenEngine(engineName);
    const isPocketPreset = isPocketPresetEngine(engineName);
    const isQwenClone = isQwenCloneEngine(engineName);
    const isOmniClone = isOmniVoiceCloneEngine(engineName);
    const isKokoro = isKokoroEngine(engineName);
    const isKitten = isKittenEngine(engineName);
    const isIndexTTS = isIndexTTSEngine(engineName);
    const isAzureSpeech = isAzureSpeechEngine(engineName);
    const isEdgeTts = isEdgeTtsEngine(engineName);
    const isElevenLabs = isElevenLabsEngine(engineName);
    const isOpenAITts = isOpenAITtsEngine(engineName);
    const isLocalAITts = isLocalAITtsEngine(engineName);
    const isCloneStyle = isQwenClone || isOmniClone;
    if (kokoroCard) {
        kokoroCard.style.display = isPrompt || isQwen || isCloneStyle ? 'none' : 'block';
    }
    if (turboCard) {
        turboCard.style.display = (isPrompt || isCloneStyle) ? 'block' : 'none';
    }
    if (qwenCard) {
        qwenCard.style.display = isQwen ? 'block' : 'none';
    }
    const isOmniVoice = isOmniVoiceEngine(engineName);
    if (paralinguisticTagsBar) {
        paralinguisticTagsBar.style.display = (isKokoro || isOmniVoice) ? 'flex' : 'none';
        const kokoroTags = document.getElementById('paralinguistic-tags-kokoro');
        const omniTags = document.getElementById('paralinguistic-tags-omnivoice');
        if (kokoroTags) kokoroTags.style.display = isKokoro ? '' : 'none';
        if (omniTags) omniTags.style.display = isOmniVoice ? '' : 'none';
    }
    updateAssignmentModes(engineName);
    if (isPrompt || isCloneStyle || isIndexTTS) {
        fetchReferencePrompts();
    }
    if (isQwen) {
        loadQwen3Metadata();
    }
    if (isAzureSpeech) {
        loadAzureSpeechVoices();
    }
    if (isEdgeTts) {
        loadEdgeTtsVoices();
    }
    if (isElevenLabs) {
        loadElevenLabsCatalog();
    }
    if (isOpenAITts) {
        loadOpenAITtsCatalog();
    }
    if (isLocalAITts) {
        loadLocalAITtsCatalog();
    }
    if (engineName === 'breeze_api') window.loadBreezeApiCatalog?.();
    // Repopulate voice selects when engine changes
    populateVoiceSelects();
}

function getAssignmentRows() {
    return Array.from(document.querySelectorAll(
        '#inline-voice-assignment-list .voice-assignment-row, #speaker-edit-modal-body .voice-assignment-row'
    ));
}

function updateAssignmentModes(engineName) {
    const usesReferenceSamples = isPromptEngine(engineName);
    const isQwen = isQwenEngine(engineName);
    const isQwenClone = isQwenCloneEngine(engineName);
    const isOmniClone = isOmniVoiceCloneEngine(engineName);
    const isCloneStyle = isQwenClone || isOmniClone;
    const isAzureSpeech = isAzureSpeechEngine(engineName);
    const isEdgeTts = isEdgeTtsEngine(engineName);
    const isElevenLabs = isElevenLabsEngine(engineName);
    const isOpenAITts = isOpenAITtsEngine(engineName);
    const isLocalAITts = isLocalAITtsEngine(engineName);
    getAssignmentRows().forEach(row => {
        const kokoroControl = row.querySelector('[data-role="kokoro-control"]');
        const turboControl = row.querySelector('[data-role="turbo-control"]');
        const qwenControl = row.querySelector('[data-role="qwen3-control"]');
        const azureControl = row.querySelector('[data-role="azure-speech-control"]');
        const localAIControl = row.querySelector('[data-role="localai-control"]');
        const kokoroPanel = row.querySelector('[data-role="kokoro-panel"]');
        if (kokoroControl) {
            const showCatalogControl = engineName === 'breeze_api' || !(usesReferenceSamples || isCloneStyle || isLocalAITts);
            kokoroControl.hidden = !showCatalogControl;
            kokoroControl.style.setProperty('display', showCatalogControl ? 'flex' : 'none', 'important');
            const label = kokoroControl.querySelector('label');
            if (label) {
                label.textContent = engineName === 'breeze_api' ? 'Hosted voice (used only when no local sample is selected)' : isQwen
                    ? 'Qwen3 Speaker'
                    : (isAzureSpeech ? 'Azure Voice'
                        : (isEdgeTts ? 'Edge Voice'
                            : (isElevenLabs ? 'ElevenLabs Voice'
                                : (isOpenAITts ? 'OpenAI TTS Voice'
                                    : (isLocalAITts ? 'LocalAI Voice Profile' : row.dataset.speaker || 'Voice')))));
            }
        }
        if (turboControl) {
            const showReferenceControl = usesReferenceSamples || isCloneStyle;
            turboControl.hidden = !showReferenceControl;
            turboControl.style.setProperty('display', showReferenceControl ? 'flex' : 'none', 'important');
        }
        if (qwenControl) {
            qwenControl.style.display = isQwen ? 'flex' : 'none';
        }
        if (azureControl) {
            azureControl.style.display = isAzureSpeech ? 'block' : 'none';
            if (isAzureSpeech) updateAzureVoiceControls(row);
        }
        if (localAIControl) {
            localAIControl.style.display = isLocalAITts ? 'flex' : 'none';
        }
        if (kokoroPanel) {
            kokoroPanel.style.display = 'flex';
        }
    });
    // Populate Qwen3 language dropdowns if Qwen3 is selected
    if (isQwen && qwen3Metadata?.languages) {
        document.querySelectorAll('#inline-voice-assignment-list .qwen3-language-select, #speaker-edit-modal-body .qwen3-language-select').forEach(select => {
            if (select.options.length <= 1) {
                qwen3Metadata.languages.forEach(lang => {
                    const option = document.createElement('option');
                    option.value = lang;
                    option.textContent = lang;
                    select.appendChild(option);
                });
            }
        });
    }
}

// Minimum duration requirements per engine (in seconds)
const ENGINE_MIN_DURATION = {
    'chatterbox_turbo_local': 5.0,
    'chatterbox_turbo_replicate': 5.0,
    'chatterbox': 5.0,
    'voxcpm_local': 0,  // VoxCPM accepts any duration
    'pocket_tts': 0,
    'qwen3_custom': 0,
    'qwen3_clone': 0,
    'omnivoice_clone': 0,
    'omnivoice_design': 0,
    'dots_tts': 0,
    'audio8_tts': 0.5,
    'breeze_api': 3.0,
    'kokoro': 0,
    'kokoro_replicate': 0,
};

function getMinDurationForEngine(engineName) {
    const normalized = (engineName || '').toLowerCase().trim();
    return ENGINE_MIN_DURATION[normalized] ?? 0;
}

function populateReferenceDropdown(selectEl, placeholderText = 'Use preset voice', engineName = null, filters = null) {
    if (!selectEl) return;
    const previousValue = selectEl.value;
    selectEl.innerHTML = '';
    if (placeholderText) {
        const option = document.createElement('option');
        option.value = '';
        option.textContent = placeholderText;
        selectEl.appendChild(option);
    }
    
    // Get current engine if not provided
    const currentEngine = engineName || getSelectedJobEngine() || window.runtimeSettings?.tts_engine || 'kokoro';
    const minDuration = getMinDurationForEngine(currentEngine);
    
    // Use provided filters or global filters
    const activeFilters = filters || voiceDropdownFilters;
    
    // Filter and sort voices
    let filteredVoices = availableChatterboxVoices.filter(entry => {
        const promptPath = (entry?.prompt_path || entry?.file_name || '').trim();
        return !entry?.archived || promptPath === previousValue;
    });
    const searchQuery = (selectEl.dataset.filterQuery || '').trim().toLowerCase();
    
    // Apply gender filter
    if (activeFilters.gender && activeFilters.gender !== 'all') {
        filteredVoices = filteredVoices.filter(v => 
            (v.gender || '').toLowerCase() === activeFilters.gender.toLowerCase()
        );
    }
    
    // Apply language filter
    if (activeFilters.language && activeFilters.language !== 'all') {
        filteredVoices = filteredVoices.filter(v => v.language === activeFilters.language);
    }

    // Speaker Properties and inline assignments can narrow large prompt libraries
    // without discarding the voice that is currently selected.
    if (searchQuery) {
        filteredVoices = filteredVoices.filter(entry => {
            const promptPath = (entry?.prompt_path || entry?.file_name || '').trim();
            const searchable = [
                entry?.name,
                promptPath,
                entry?.gender,
                entry?.language,
                entry?.description,
                entry?.voice_design?.instruction
            ].filter(Boolean).join(' ').toLowerCase();
            return searchable.includes(searchQuery) || promptPath === previousValue;
        });
    }
    
    // Sort voices alphabetically by name
    const sortedVoices = filteredVoices.sort((a, b) =>
        (a.name || '').toLowerCase().localeCompare((b.name || '').toLowerCase())
    );
    
    sortedVoices.forEach(entry => {
        const option = document.createElement('option');
        const promptPath = (entry?.prompt_path || entry?.file_name || '').trim();
        option.value = promptPath;
        const duration = entry?.duration_seconds ?? null;
        const durationLabel = duration !== null ? ` · ${duration.toFixed(1)}s` : '';
        
        // Build label with gender and language
        const gender = entry?.gender ? ` [${entry.gender.charAt(0).toUpperCase()}]` : '';
        const lang = entry?.language ? ` ${getLanguageDisplayName(entry.language)}` : '';
        const metaLabel = (gender || lang) ? ` ·${gender}${lang}` : '';
        
        option.textContent = `${entry?.name || promptPath}${metaLabel}${durationLabel}`;
        option.dataset.durationSeconds = duration ?? '';
        option.dataset.gender = entry?.gender || '';
        option.dataset.language = entry?.language || '';
        
        // Check if duration meets minimum requirement for current engine
        if (minDuration > 0 && duration !== null && duration < minDuration) {
            option.disabled = true;
            option.style.color = '#ff6b6b';
            option.textContent = `${entry?.name || promptPath}${metaLabel}${durationLabel} (too short)`;
        }
        if (['audio8_tts', 'breeze_tts_2'].includes((currentEngine || '').toLowerCase()) && !entry?.transcript) {
            option.disabled = true;
            option.style.color = '#ff6b6b';
            option.textContent = `${entry?.name || promptPath}${metaLabel}${durationLabel} (transcript required)`;
            option.title = 'Generate or enter this sample\'s exact transcript in Available Voices first.';
        }
        
        selectEl.appendChild(option);
    });
    
    if (previousValue) {
        // Only restore if the option is not disabled
        const prevOption = selectEl.querySelector(`option[value="${CSS.escape(previousValue)}"]`);
        if (prevOption && !prevOption.disabled) {
            selectEl.value = previousValue;
        }
    }
}

function updateVoiceDropdownFilterOptions() {
    // Collect unique genders and languages from available voices
    const genders = new Set();
    const languages = new Set();
    
    availableChatterboxVoices.forEach(v => {
        if (v.gender) genders.add(v.gender);
        if (v.language) languages.add(v.language);
    });
    
    // Update gender filter selects
    document.querySelectorAll('.voice-filter-gender').forEach(select => {
        const currentValue = select.value;
        select.innerHTML = '<option value="all">All Genders</option>';
        [...genders].sort().forEach(g => {
            const opt = document.createElement('option');
            opt.value = g.toLowerCase();
            opt.textContent = g;
            select.appendChild(opt);
        });
        if (currentValue) select.value = currentValue;
    });
    
    // Update language filter selects
    document.querySelectorAll('.voice-filter-language').forEach(select => {
        const currentValue = select.value;
        select.innerHTML = '<option value="all">All Languages</option>';
        [...languages].sort((a, b) => 
            getLanguageDisplayName(a).localeCompare(getLanguageDisplayName(b))
        ).forEach(lang => {
            const opt = document.createElement('option');
            opt.value = lang;
            opt.textContent = getLanguageDisplayName(lang);
            select.appendChild(opt);
        });
        if (currentValue) select.value = currentValue;
    });
}

function populatePresetSelect(selectEl, selectedValue, placeholderText = 'Select a saved voice') {
    if (!selectEl) return;
    const previousValue = selectedValue || selectEl.value;
    selectEl.innerHTML = '';
    if (placeholderText) {
        const placeholder = document.createElement('option');
        placeholder.value = '';
        placeholder.textContent = placeholderText;
        selectEl.appendChild(placeholder);
    }
    // Sort voices alphabetically by name
    const sortedVoices = [...availableChatterboxVoices].sort((a, b) =>
        (a.name || '').toLowerCase().localeCompare((b.name || '').toLowerCase())
    );
    sortedVoices.forEach(entry => {
        const pathValue = (entry?.prompt_path || entry?.file_name || '').trim();
        if (!pathValue) {
            return;
        }
        const option = document.createElement('option');
        option.value = pathValue;
        option.textContent = entry?.name || pathValue;
        if (entry.missing_file) {
            option.disabled = true;
            option.textContent = `${option.textContent} (missing file)`;
        }
        selectEl.appendChild(option);
    });
    if (previousValue) {
        selectEl.value = previousValue;
    }
}

function populateReferenceSelects() {
    populateReferenceDropdown(
        document.getElementById('chatterbox-reference-select'),
        'Select saved Chatterbox voice'
    );
    document.querySelectorAll('#inline-voice-assignment-list [data-role="turbo-control"] .reference-select, #speaker-edit-modal-body [data-role="turbo-control"] .reference-select')
        .forEach(select => {
            populateReferenceDropdown(select, 'Inherit from global selection');
            const speaker = select.dataset.speaker;
            const selection = speaker ? turboSelectionState[speaker] : '';
            if (selection) {
                select.value = selection;
            }
    });
    getAssignmentRows().forEach(row => updateInlineSampleButtonState(row));
}

function syncSpeakerReferenceAssignment(speaker, promptValue = '') {
    if (!speaker) return false;
    const selectedValue = (promptValue || turboSelectionState[speaker]
        || findSpeakerProfile(speaker).profile?.selected_voice_path || '').trim();
    if (selectedValue) turboSelectionState[speaker] = selectedValue;
    const engineName = getSelectedJobEngine() || runtimeSettings?.tts_engine || 'kokoro';
    updateAssignmentModes(engineName);
    let matched = false;
    document.querySelectorAll(
        `#inline-voice-assignment-list .reference-select[data-speaker="${CSS.escape(speaker)}"],` +
        `#speaker-edit-modal-body .reference-select[data-speaker="${CSS.escape(speaker)}"]`
    ).forEach(select => {
        populateReferenceDropdown(select, 'Select Voice Sample...', engineName);
        const option = Array.from(select.options).find(entry => (
            entry.value === selectedValue && !entry.disabled
        ));
        if (option) {
            select.value = selectedValue;
            matched = true;
        }
        updateInlineSampleButtonState(select.closest('.voice-assignment-row'), { stopPlayback: false });
    });
    return matched;
}

async function handleReferenceUpload(event) {
    const files = event.target.files;
    if (!files || !files.length) {
        return;
    }
    const file = files[0];
    const formData = new FormData();
    formData.append('file', file);
    try {
        const response = await fetch('/api/voice-prompts/upload', {
            method: 'POST',
            body: formData,
        });
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Upload failed');
        }
        showNotification('Reference prompt uploaded.', 'success');
        await fetchReferencePrompts();
    } catch (error) {
        console.error('Prompt upload failed', error);
        showNotification(error.message || 'Failed to upload prompt', 'error');
    } finally {
        event.target.value = '';
    }
}

function handleReferenceSelectChange(event) {
    const selected = event.target.value;
    const promptInput = document.getElementById('job-turbo-local-prompt');
    if (promptInput !== null) {
        promptInput.value = selected;
    }
    refreshGlobalChatterboxPreviewButton();
}

async function fetchReferencePrompts() {
    try {
        const response = await fetch('/api/voice-prompts');
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Unable to load reference prompts');
        }
        window.availableReferencePrompts = data.prompts || [];
    } catch (error) {
        console.error('Failed to fetch reference prompts', error);
        window.availableReferencePrompts = [];
    } finally {
        populateReferenceSelects();
        refreshGlobalChatterboxPreviewButton();
    }
}

function findChatterboxVoiceByPath(pathValue) {
    if (!pathValue) return null;
    const normalized = pathValue.trim();
    if (!normalized) return null;
    return availableChatterboxVoices.find(entry => {
        const promptPath = (entry?.prompt_path || '').trim();
        const fileName = (entry?.file_name || '').trim();
        return promptPath === normalized || fileName === normalized;
    }) || null;
}

function refreshGlobalChatterboxPreviewButton() {
    const select = document.getElementById('chatterbox-reference-select');
    const button = document.getElementById('global-chatterbox-preview-btn');
    if (!button) return;
    const hasSelection = !!(select?.value?.trim());
    if (!hasSelection) {
        button.disabled = true;
        button.classList.remove('is-playing', 'is-loading');
        button.textContent = button.dataset.labelPlay || 'Play';
    } else {
        button.disabled = false;
    }
}
window.refreshGlobalChatterboxPreviewButton = refreshGlobalChatterboxPreviewButton;

function getSelectedJobEngine() {
    const select = document.getElementById('job-tts-engine');
    if (!select) return null;
    const value = (select.value || '').trim().toLowerCase();
    return value || null;
}

function getGlobalReferenceSelection() {
    const select = document.getElementById('chatterbox-reference-select');
    if (select && select.value) {
        return select.value.trim();
    }
    const promptInput = document.getElementById('job-turbo-local-prompt');
    return (promptInput?.value || '').trim();
}

function collectEngineOverrides(engineName) {
    if (!engineName) return null;
    switch (engineName) {
        case 'chatterbox':
            return collectChatterboxOverrides();
        case 'chatterbox_turbo_local':
            return collectTurboLocalOverrides();
        case 'chatterbox_turbo_replicate':
            return collectTurboReplicateOverrides();
        case 'qwen3_custom':
            return collectQwen3Overrides();
        case 'qwen3_clone':
            return null;
        default:
            return null;
    }
}

function collectQwen3Overrides() {
    const options = {};
    const instruction = document.getElementById('qwen3-default-instruct')?.value.trim();
    if (instruction) {
        options.default_instruct = instruction;
    }
    return Object.keys(options).length ? options : null;
}

function collectTurboLocalOverrides() {
    const options = {};
    const prompt = document.getElementById('job-turbo-local-prompt')?.value.trim();
    if (prompt) {
        options.default_prompt = prompt;
    }
    const temperature = readNumericInput('job-turbo-local-temperature');
    if (temperature !== null) {
        options.temperature = temperature;
    }
    const topP = readNumericInput('job-turbo-local-top-p');
    if (topP !== null) {
        options.top_p = topP;
    }
    const topK = readNumericInput('job-turbo-local-top-k', true);
    if (topK !== null) {
        options.top_k = topK;
    }
    const repPenalty = readNumericInput('job-turbo-local-rep-penalty');
    if (repPenalty !== null) {
        options.repetition_penalty = repPenalty;
    }
    const cfgWeight = readNumericInput('job-turbo-local-cfg-weight');
    if (cfgWeight !== null) {
        options.cfg_weight = cfgWeight;
    }
    const exaggeration = readNumericInput('job-turbo-local-exaggeration');
    if (exaggeration !== null) {
        options.exaggeration = exaggeration;
    }
    const normCheckbox = document.getElementById('job-turbo-local-norm');
    if (normCheckbox) {
        options.norm_loudness = normCheckbox.checked;
    }
    const promptNormCheckbox = document.getElementById('job-turbo-local-prompt-norm');
    if (promptNormCheckbox) {
        options.prompt_norm_loudness = promptNormCheckbox.checked;
    }
    return Object.keys(options).length ? options : null;
}

function collectTurboReplicateOverrides() {
    const options = {};
    const model = document.getElementById('job-turbo-replicate-model')?.value.trim();
    if (model) {
        options.model = model;
    }
    const voice = document.getElementById('job-turbo-replicate-voice')?.value.trim();
    if (voice) {
        options.voice = voice;
    }
    const temperature = readNumericInput('job-turbo-replicate-temperature');
    if (temperature !== null) {
        options.temperature = temperature;
    }
    const topP = readNumericInput('job-turbo-replicate-top-p');
    if (topP !== null) {
        options.top_p = topP;
    }
    const topK = readNumericInput('job-turbo-replicate-top-k', true);
    if (topK !== null) {
        options.top_k = topK;
    }
    const repPenalty = readNumericInput('job-turbo-replicate-rep-penalty');
    if (repPenalty !== null) {
        options.repetition_penalty = repPenalty;
    }
    const seedValue = document.getElementById('job-turbo-replicate-seed')?.value.trim();
    if (seedValue) {
        const parsedSeed = parseInt(seedValue, 10);
        if (Number.isFinite(parsedSeed) && parsedSeed >= 0) {
            options.seed = parsedSeed;
        }
    }
    return Object.keys(options).length ? options : null;
}

function readNumericInput(elementId, integerOnly = false) {
    const raw = document.getElementById(elementId)?.value;
    if (raw === undefined || raw === null || raw === '') {
        return null;
    }
    const parsed = integerOnly ? parseInt(raw, 10) : parseFloat(raw);
    if (!Number.isFinite(parsed)) {
        return null;
    }
    return parsed;
}

// Main application logic

let currentJobId = null;
let currentStats = null;
let analyzeDebounceTimer = null;
let lastAnalyzedText = '';
let analyzeInFlight = false;
let analyzeRerunRequested = false;
let sectionReviewInFlight = false;
let sectionReviewData = null;
let sectionReviewLastFetchedText = null;
let sectionReviewLastFetchedHeadingKey = null;
let sectionEditTarget = null;
let inlineSampleHandlersReady = false;
const turboSelectionState = {};
const TTS_STORY_VOICE_REFERENCE_PREFIX = 'tts-story://voice-prompts/';
const speakerReadyState = {};
const speakerProfiles = {};
const speakerVoiceDesignCandidates = {};
let activeSpeakerModal = null;
let activeSpeakerRow = null;
let pendingProjectLoad = null;
let activeProjectId = null;
let bulkVoiceGenerationState = null;
let latestGeminiBookTitle = '';
const ANALYZE_DEBOUNCE_MS = 800;
const VOICES_EVENT_NAME = window.VOICES_UPDATED_EVENT || 'voices:updated';
const DEFAULT_FX_STATE = Object.freeze({
    pitch: 0,
    speed: 1,
    sampleText: ''
});
const voiceFxState = {};
let currentFxPreviewAudio = null;
let currentFxPreviewButton = null;
let queuePollInFlight = false;
const PROJECT_STORAGE_KEY = 'tts-story-projects';
let savedProjects = [];
let projectLibraryPromise = null;
let activeSpeakerRowOrigin = null;
let runtimeSettings = null;
let availableChatterboxVoices = [];
let azureSpeechVoices = [];
let azureSpeechVoicesPromise = null;
const azureVoiceOptionState = {};
let edgeTtsVoices = [];
let edgeTtsVoicesPromise = null;
let elevenLabsVoices = [];
let elevenLabsModels = [];
let elevenLabsCatalogPromise = null;
let openAITtsVoices = [];
let openAITtsCatalogPromise = null;
let localAITtsVoices = [];
let localAITtsModels = [];
let localAITtsCatalogPromise = null;
let qwen3Metadata = null;
let availableGeminiPromptPresets = [];

window.customVoiceMap = window.customVoiceMap || {};
window.addEventListener(VOICES_EVENT_NAME, handleVoicesUpdated);
const CHATTERBOX_VOICES_EVENT_NAME = window.CHATTERBOX_VOICES_EVENT || 'chatterboxVoices:updated';
window.CHATTERBOX_VOICES_EVENT = CHATTERBOX_VOICES_EVENT_NAME;
window.addEventListener(CHATTERBOX_VOICES_EVENT_NAME, handleChatterboxVoicesUpdated);

function localAIVoiceReferenceToPromptPath(value) {
    const reference = (value || '').trim();
    if (!reference.startsWith(TTS_STORY_VOICE_REFERENCE_PREFIX)) return '';
    try {
        const decoded = decodeURIComponent(reference.slice(TTS_STORY_VOICE_REFERENCE_PREFIX.length));
        return decoded.split(/[\\/]/).pop()?.trim() || '';
    } catch (error) {
        console.warn('Unable to decode TTS-Story voice reference', error);
        return '';
    }
}

function promptPathToLocalAIVoiceReference(value) {
    const promptPath = (value || '').trim();
    if (!promptPath) return '';
    const fileName = promptPath.split(/[\\/]/).pop()?.trim() || '';
    return fileName
        ? `${TTS_STORY_VOICE_REFERENCE_PREFIX}${encodeURIComponent(fileName)}`
        : '';
}

function rememberCompatibleVoiceSample(speaker, value) {
    if (!speaker) return false;
    const selection = (value || '').trim();
    if (!selection) return false;
    const promptPath = selection.startsWith(TTS_STORY_VOICE_REFERENCE_PREFIX)
        ? localAIVoiceReferenceToPromptPath(selection)
        : selection;
    if (!promptPath) return false;
    turboSelectionState[speaker] = promptPath;
    return true;
}

function captureCompatibleVoiceSamples() {
    getAssignmentRows().forEach(row => {
        const speaker = row.dataset.speaker;
        if (!speaker) return;
        const providerValue = row.querySelector('.voice-select')?.value?.trim() || '';
        if (providerValue.startsWith(TTS_STORY_VOICE_REFERENCE_PREFIX)) {
            rememberCompatibleVoiceSample(speaker, providerValue);
            return;
        }
        const referenceValue = row.querySelector('.reference-select')?.value?.trim() || '';
        if (referenceValue) {
            rememberCompatibleVoiceSample(speaker, referenceValue);
        }
    });
}

function restoreCompatibleLocalAIVoiceSample(selectElement) {
    const speaker = selectElement?.dataset?.speaker;
    const promptPath = speaker ? turboSelectionState[speaker] : '';
    const reference = promptPathToLocalAIVoiceReference(promptPath);
    if (!reference) return false;
    const match = Array.from(selectElement.options).find(option => (
        option.value === reference && !option.disabled
    ));
    if (!match) return false;
    selectElement.value = reference;
    return true;
}
window.addEventListener('geminiPresets:changed', event => {
    setAvailableGeminiPresets(event?.detail?.presets || []);
});

function setAvailableGeminiPresets(presets = []) {
    const normalized = [];
    if (Array.isArray(presets)) {
        presets.forEach(preset => {
            const title = (preset?.title || '').trim();
            const prompt = (preset?.prompt || '').trim();
            let id = (preset?.id || '').trim();
            if (!title || !prompt) {
                return;
            }
            if (!id) {
                id = typeof crypto !== 'undefined' && crypto.randomUUID
                    ? crypto.randomUUID()
                    : `preset-${Date.now()}-${normalized.length}`;
            }
            normalized.push({ id, title, prompt });
        });
    }
    availableGeminiPromptPresets = normalized;
    populateGeminiPresetDropdown();
}

function populateGeminiPresetDropdown(selectedId) {
    const select = document.getElementById('gemini-preset-select');
    if (!select) return;
    const previousValue = selectedId !== undefined ? selectedId : select.value;
    select.innerHTML = '';
    const defaultOption = document.createElement('option');
    defaultOption.value = '';
    defaultOption.textContent = 'Use default prompt';
    select.appendChild(defaultOption);
    availableGeminiPromptPresets.forEach(preset => {
        const option = document.createElement('option');
        option.value = preset.id;
        option.textContent = preset.title;
        option.title = preset.prompt;
        select.appendChild(option);
    });
    if (previousValue) {
        select.value = previousValue;
        if (select.value !== previousValue) {
            select.value = '';
        }
    }
}

function handleVoicesUpdated(event) {
    const detail = event?.detail || {};
    if (detail.voices) {
        window.availableVoices = detail.voices;
    }
    if (detail.customVoiceMap) {
        window.customVoiceMap = detail.customVoiceMap;
    }
    if (Array.isArray(detail.pocketTtsVoices)) {
        window.availablePocketTtsVoices = detail.pocketTtsVoices;
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
            speed: DEFAULT_FX_STATE.speed,
            sampleText: DEFAULT_FX_STATE.sampleText
        };
    }
    return voiceFxState[key];
}

function getFxPayload(speaker) {
    const state = getFxState(speaker);
    const payload = {};
    const pitch = Number(state.pitch) || 0;
    if (Math.abs(pitch) > 0.01) {
        payload.pitch = pitch;
    }
    return Object.keys(payload).length ? payload : null;
}

function createAssignment(voiceName, langCode, speakerKey) {
    const state = getFxState(speakerKey);
    const assignment = {
        voice: voiceName,
        lang_code: langCode
    };
    const fxPayload = getFxPayload(speakerKey);
    if (fxPayload) {
        assignment.fx = fxPayload;
    }
    const speedValue = Number(state.speed) || 1;
    if (Math.abs(speedValue - 1) > 0.005) {
        assignment.speed = Number(speedValue.toFixed(2));
    }
    return assignment;
}

function createPresetAssignment(voiceName, speakerKey) {
    const state = getFxState(speakerKey);
    const assignment = { voice: voiceName };
    const fxPayload = getFxPayload(speakerKey);
    if (fxPayload) {
        assignment.fx = fxPayload;
    }
    const speedValue = Number(state.speed) || 1;
    if (Math.abs(speedValue - 1) > 0.005) {
        assignment.speed = Number(speedValue.toFixed(2));
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
    const sharedActionsMarkup = useSharedPreview
        ? `
            <div class="fx-field fx-inline fx-actions">
                <button type="button" class="btn btn-sm" data-role="fx-preview-btn">Quick Test</button>
                <span class="fx-status" data-role="fx-status"></span>
            </div>
        `
        : '';
    const previewMarkup = !useSharedPreview
        ? `
            <div class="fx-field fx-preview">
                <textarea data-role="fx-sample-text" rows="2" placeholder="Preview text">${state.sampleText || buildDefaultSampleText(speaker)}</textarea>
                <div class="fx-preview-actions">
                    <button type="button" class="btn btn-sm" data-role="fx-preview-btn">Quick Test</button>
                    <span class="fx-status" data-role="fx-status"></span>
                </div>
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
                    <label>Speed</label>
                    <div class="slider-group">
                        <input type="range" min="0.5" max="2.0" step="0.01" value="${state.speed}" data-role="fx-speed">
                        <span class="slider-value" data-role="fx-speed-value">${state.speed.toFixed(2)}x</span>
                    </div>
                </div>
                ${sharedActionsMarkup}
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
    const speedInput = container.querySelector('[data-role="fx-speed"]');
    const speedValue = container.querySelector('[data-role="fx-speed-value"]');
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
    if (speedInput && speedValue) {
        speedInput.addEventListener('input', event => {
            state.speed = parseFloat(event.target.value) || 1;
            speedValue.textContent = `${state.speed.toFixed(2)}x`;
        });
    }
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
    const engineName = getSelectedJobEngine() || runtimeSettings?.tts_engine || 'kokoro';
    if (isQwenEngine(engineName)) {
        if (speaker === 'default' || !speaker) {
            return document.getElementById('qwen3-default-speaker')?.value || '';
        }
    } else if (speaker === 'default' || !speaker) {
        return document.getElementById('default-voice-select')?.value || '';
    }
    const selector = document.querySelector(
        `#speaker-edit-modal-body .voice-assignment-row[data-speaker="${speaker}"] .voice-select`
    ) || document.querySelector(
        `#inline-voice-assignment-list .voice-select[data-speaker="${speaker}"]`
    );
    return selector?.value || '';
}

function resolveVoiceSampleSelection(speaker) {
    if (speaker === 'default' || !speaker) {
        return getGlobalReferenceSelection();
    }
    const selector = document.querySelector(
        `#speaker-edit-modal-body .voice-assignment-row[data-speaker="${speaker}"] .reference-select`
    ) || document.querySelector(
        `#inline-voice-assignment-list .reference-select[data-speaker="${speaker}"]`
    );
    const fromSelect = selector?.value?.trim() || '';
    if (selector && getSelectedJobEngine() === 'breeze_api') return fromSelect;
    if (fromSelect) return fromSelect;
    // Fall back to in-memory turbo selection state, then global reference
    return turboSelectionState[speaker] || getGlobalReferenceSelection() || '';
}

async function previewVoiceSampleFx({ promptPath, pitch, speed }) {
    const response = await fetch('/api/voice-prompts/preview-fx', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ prompt_path: promptPath, pitch, speed })
    });
    const data = await response.json();
    if (!data.success || !data.audio_base64) {
        throw new Error(data.error || 'Preview failed');
    }
    return data;
}

async function handleFxPreview(speaker, container) {
    if (!container) return;
    const statusEl = container.querySelector('[data-role="fx-status"]');
    const previewBtn = container.querySelector('[data-role="fx-preview-btn"]');
    if (previewBtn) {
        if (!previewBtn.dataset.labelPlay) {
            previewBtn.dataset.labelPlay = previewBtn.textContent.trim() || 'Quick Test';
        }
        if (!previewBtn.dataset.labelStop) {
            previewBtn.dataset.labelStop = 'Stop';
        }
    }
    if (previewBtn && currentFxPreviewAudio && currentFxPreviewButton === previewBtn) {
        currentFxPreviewAudio.pause();
        currentFxPreviewAudio.currentTime = 0;
        currentFxPreviewAudio = null;
        previewBtn.classList.remove('is-playing');
        previewBtn.textContent = previewBtn.dataset.labelPlay || 'Quick Test';
        if (statusEl) statusEl.textContent = '';
        return;
    }
    const engineName = getSelectedJobEngine() || runtimeSettings?.tts_engine || 'kokoro';
    const usesPromptEngine = isPromptEngine(engineName);
    const samplePrompt = usesPromptEngine ? resolveVoiceSampleSelection(speaker) : '';
    const usesSamplePreview = usesPromptEngine && !!samplePrompt;
    const voiceName = usesSamplePreview ? '' : resolveVoiceSelection(speaker);
    if (!voiceName && !samplePrompt) {
        if (statusEl) {
            statusEl.textContent = usesPromptEngine
                ? 'Select a voice sample first.'
                : 'Select a voice first.';
        }
        return;
    }
    const langCode = isQwenEngine(engineName)
        ? (document.getElementById('qwen3-default-language')?.value || 'Auto')
        : getLangCodeForVoice(voiceName);
    const state = getFxState(speaker);
    const sampleText = speaker === 'default'
        ? (state.sampleText || '').trim() || buildDefaultSampleText(speaker)
        : getSharedPreviewText();
    const panelSpeed = Number(state.speed) || NaN;
    const globalSpeed = parseFloat(document.getElementById('speed')?.value) || 1.0;
    let previewSpeed = Number.isFinite(panelSpeed) ? panelSpeed : globalSpeed;
    previewSpeed = Math.max(0.5, Math.min(previewSpeed, 2.0));
    const pitchValue = Number(state.pitch) || 0;

    const payload = {
        voice: usesSamplePreview ? samplePrompt : voiceName,
        lang_code: langCode,
        text: sampleText,
    };
    const fxPayload = getFxPayload(speaker);
    if (fxPayload) {
        payload.fx = fxPayload;
    }
    payload.speed = previewSpeed;

    if (isAzureSpeechEngine(engineName)) {
        payload.extra = collectAzureVoiceOptions(getAzureAssignmentRow(speaker), voiceName);
    }

    if (!usesSamplePreview) {
        const selectedEngine = engineName;
        if (selectedEngine) {
            payload.tts_engine = selectedEngine;
            const overrides = collectEngineOverrides(selectedEngine);
            if (overrides) {
                payload.engine_options = overrides;
            }
        }
    }

    try {
        if (previewBtn) previewBtn.disabled = true;
        if (statusEl) statusEl.textContent = 'Rendering preview…';

        const data = usesSamplePreview
            ? await previewVoiceSampleFx({
                promptPath: samplePrompt,
                pitch: pitchValue,
                speed: previewSpeed
            })
            : await (async () => {
                const response = await fetch('/api/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const result = await response.json();
                if (!result.success || !result.audio_base64) {
                    throw new Error(result.error || 'Preview failed');
                }
                return result;
            })();
        if (currentFxPreviewAudio) {
            currentFxPreviewAudio.pause();
            currentFxPreviewAudio = null;
        }
        const mime = data.mime_type || 'audio/wav';
        currentFxPreviewAudio = new Audio(`data:${mime};base64,${data.audio_base64}`);
        currentFxPreviewButton = previewBtn || null;
        currentFxPreviewAudio.play().then(() => {
            if (statusEl) statusEl.textContent = 'Playing preview…';
            if (previewBtn) {
                previewBtn.disabled = false;
                previewBtn.classList.add('is-playing');
                previewBtn.textContent = previewBtn.dataset.labelStop || 'Stop';
            }
        }).catch(err => {
            console.error('Preview playback failed', err);
            if (statusEl) statusEl.textContent = 'Unable to play preview.';
            if (previewBtn) {
                previewBtn.classList.remove('is-playing');
                previewBtn.textContent = previewBtn.dataset.labelPlay || 'Quick Test';
            }
        });
        if (currentFxPreviewAudio) {
            currentFxPreviewAudio.onended = () => {
                if (statusEl) statusEl.textContent = '';
                currentFxPreviewAudio = null;
                if (previewBtn) {
                    previewBtn.classList.remove('is-playing');
                    previewBtn.textContent = previewBtn.dataset.labelPlay || 'Quick Test';
                }
                currentFxPreviewButton = null;
            };
        }
    } catch (error) {
        console.error('Preview failed:', error);
        if (statusEl) statusEl.textContent = error.message || 'Preview failed';
    } finally {
        if (previewBtn && !currentFxPreviewAudio) {
            previewBtn.disabled = false;
        }
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

    if (!currentStats || !currentStats.section_detection) {
        chapterHint.textContent = chapterCheckbox.checked
            ? 'Section splitting enabled. Awaiting analysis to determine sections.'
            : 'Sections not analyzed yet.';
        return;
    }

    const { detected, count, kind, book_count: bookCount = 0, section_count: sectionCount = 0 } = currentStats.section_detection;
    const label = kind === 'book' ? 'book' : 'section';
    const summary = kind === 'book'
        ? `${bookCount || count} book${(bookCount || count) === 1 ? '' : 's'} · ${sectionCount} section${sectionCount === 1 ? '' : 's'}`
        : `${count} ${label}${count === 1 ? '' : 's'}`;
    if (!detected) {
        chapterHint.textContent = chapterCheckbox.checked
            ? 'Splitting enabled, but no section headings were detected. The whole story will be one file.'
            : 'No section headings detected. Add headings like "Chapter 1" to enable split outputs.';
        return;
    }

    if (chapterCheckbox.checked) {
        chapterHint.textContent = `Splitting enabled: ${summary} will become individual audio files.`;
    } else {
        chapterHint.textContent = `Detected ${summary}. Enable the checkbox to create separate audio files.`;
    }
}

function escapeHtml(value) {
    const text = String(value ?? '');
    return text
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#39;');
}

function updateSectionReviewButton(enabled) {
    const reviewBtn = document.getElementById('review-sections-btn');
    if (!reviewBtn) return;
    reviewBtn.disabled = !enabled;
}

function closeSectionReviewModal() {
    const overlay = document.getElementById('section-review-modal-overlay');
    const modal = document.getElementById('section-review-modal');
    if (overlay) overlay.classList.add('hidden');
    if (modal) modal.classList.add('hidden');
}

function openSectionReviewModal() {
    const overlay = document.getElementById('section-review-modal-overlay');
    const modal = document.getElementById('section-review-modal');
    if (!overlay || !modal) return;
    overlay.classList.remove('hidden');
    modal.classList.remove('hidden');
}

function closeSectionEditModal() {
    const overlay = document.getElementById('section-edit-modal-overlay');
    const modal = document.getElementById('section-edit-modal');
    if (overlay) overlay.classList.add('hidden');
    if (modal) modal.classList.add('hidden');
    sectionEditTarget = null;
}

function openSectionEditModal(target) {
    if (!target) return;
    sectionEditTarget = target;
    const overlay = document.getElementById('section-edit-modal-overlay');
    const modal = document.getElementById('section-edit-modal');
    const input = document.getElementById('section-edit-input');
    const original = document.getElementById('section-edit-original');
    if (original) {
        original.textContent = target.heading
            ? `Current heading: ${target.heading}`
            : 'Current heading not available.';
    }
    if (input) {
        input.value = target.heading || target.title || '';
        input.focus();
        input.select();
    }
    if (overlay) overlay.classList.remove('hidden');
    if (modal) modal.classList.remove('hidden');
}

function cleanHeadingClient(value) {
    if (!value) return '';
    return value.replace(/\[[^\]]+\]/g, '').replace(/\s+/g, ' ').trim();
}

function updateSectionCardTitle(target, newHeading) {
    const card = document.querySelector(`[data-section-id="${target.sectionId}"]`);
    if (!card) return;
    const titleEl = card.querySelector('.section-review-title');
    if (titleEl) {
        const cleaned = cleanHeadingClient(newHeading);
        titleEl.textContent = cleaned || newHeading || 'Untitled section';
    }
}

function updateSectionDataHeading(target, newHeading) {
    if (!sectionReviewData || !target) return;
    if (target.kind === 'book') {
        const book = sectionReviewData.books?.[target.bookIndex];
        const chapter = book?.chapters?.[target.chapterIndex];
        if (chapter) {
            chapter.heading = newHeading;
            chapter.title = cleanHeadingClient(newHeading) || chapter.title;
        }
        return;
    }
    const section = sectionReviewData.sections?.[target.sectionIndex];
    if (section) {
        section.heading = newHeading;
        section.title = cleanHeadingClient(newHeading) || section.title;
    }
}

function applySectionHeadingEdit(newHeading) {
    if (!sectionEditTarget) return;
    const input = document.getElementById('input-text');
    if (!input) return;
    const start = sectionEditTarget.headingStart;
    const end = sectionEditTarget.headingEnd;
    if (typeof start !== 'number' || typeof end !== 'number') {
        showNotification('Heading position missing. Re-run section detection first.', 'warning');
        return;
    }
    const text = input.value || '';
    if (start < 0 || end < start || end > text.length) {
        showNotification('Heading location is out of date. Re-run section detection first.', 'warning');
        return;
    }
    const updated = `${text.slice(0, start)}${newHeading}${text.slice(end)}`;
    input.value = updated;

    // Invalidate both caches so the next modal open re-fetches fresh data
    // with correct offsets, and analysis reflects the updated text.
    invalidateSectionReviewCache();
    lastAnalyzedText = '';

    closeSectionEditModal();
    showNotification('Heading updated. Refreshing sections…', 'success');

    // Re-fetch section preview so the Review modal cards are immediately current,
    // then re-run text analysis so speaker/chapter info stays in sync.
    (async () => {
        try {
            const enabledHeadings = getEnabledSectionHeadings();
            const payload = { text: updated, section_headings: enabledHeadings };
            const response = await fetch('/api/sections/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            const data = await response.json();
            if (data && data.success) {
                sectionReviewLastFetchedText = updated;
                sectionReviewLastFetchedHeadingKey = getSectionHeadingCacheKey(enabledHeadings);
            }
            renderSectionReview(data);
        } catch (_) {
            // Non-fatal — user can click Review Sections again to refresh
        }
    })();

    // Trigger analysis refresh (debounced) so chapter/speaker detection updates
    input.dispatchEvent(new Event('input', { bubbles: true }));
}

function renderSectionReview(data) {
    const body = document.getElementById('section-review-modal-body');
    if (!body) return;

    sectionReviewData = data && data.success ? data : null;

    if (!data || !data.success) {
        const message = data?.error || 'Unable to load section preview.';
        body.innerHTML = `<div class="section-review-error">${escapeHtml(message)}</div>`;
        return;
    }

    if (data.kind === 'none' || (!data.books?.length && !data.sections?.length)) {
        body.innerHTML = '<div class="section-review-empty">No section headings detected.</div>';
        return;
    }

    const summary = data.kind === 'book'
        ? `${data.book_count || 0} book${data.book_count === 1 ? '' : 's'} · ${data.section_count || 0} section${data.section_count === 1 ? '' : 's'}`
        : `${data.section_count || 0} section${data.section_count === 1 ? '' : 's'}`;

    const summaryHtml = `<div class="section-review-summary">Detected: <strong>${escapeHtml(summary)}</strong></div>`;

    if (data.kind === 'book') {
        const bookBlocks = (data.books || []).map((book, bookIdx) => {
            const chapters = book.chapters || [];
            const chapterCards = chapters.map((chapter, chapterIdx) => {
                const title = chapter.title || 'Untitled section';
                const sectionId = `book-${bookIdx}-chapter-${chapterIdx}`;
                return `
                    <div class="section-review-card" data-section-id="${sectionId}" data-section-kind="book" data-book-index="${bookIdx}" data-chapter-index="${chapterIdx}" data-heading-start="${chapter.heading_start ?? ''}" data-heading-end="${chapter.heading_end ?? ''}" data-heading="${escapeHtml(chapter.heading || '')}" data-title="${escapeHtml(title)}">
                        <div class="section-review-title">${escapeHtml(title)}</div>
                        <div class="section-review-preview">${escapeHtml(chapter.preview || '')}</div>
                        <button class="btn btn-secondary section-review-edit" type="button" data-section-id="${sectionId}">Edit heading</button>
                    </div>
                `;
            }).join('');
            return `
                <div class="section-review-card section-review-book">
                    <div class="section-review-book-title">
                        ${escapeHtml(book.title || `Book ${bookIdx + 1}`)}
                        <span class="section-review-count">${chapters.length} sections</span>
                    </div>
                    <div class="section-review-list">${chapterCards}</div>
                </div>
            `;
        }).join('');
        body.innerHTML = `${summaryHtml}<div class="section-review-list">${bookBlocks}</div>`;
        return;
    }

    const sectionCards = (data.sections || []).map((section, sectionIdx) => {
        const title = section.title || 'Untitled section';
        const sectionId = `section-${sectionIdx}`;
        return `
            <div class="section-review-card" data-section-id="${sectionId}" data-section-kind="section" data-section-index="${sectionIdx}" data-heading-start="${section.heading_start ?? ''}" data-heading-end="${section.heading_end ?? ''}" data-heading="${escapeHtml(section.heading || '')}" data-title="${escapeHtml(title)}">
                <div class="section-review-title">${escapeHtml(title)}</div>
                <div class="section-review-preview">${escapeHtml(section.preview || '')}</div>
                <button class="btn btn-secondary section-review-edit" type="button" data-section-id="${sectionId}">Edit heading</button>
            </div>
        `;
    }).join('');

    body.innerHTML = `${summaryHtml}<div class="section-review-list">${sectionCards}</div>`;
}

function getSelectedGeminiPromptOverride() {
    const select = document.getElementById('gemini-preset-select');
    if (!select) return '';
    const selectedId = select.value;
    if (!selectedId) return '';
    const preset = availableGeminiPromptPresets.find(entry => entry.id === selectedId);
    return preset?.prompt || '';
}

let _geminiPrepPauseRequested = false;
let _geminiPrepAbortRequested = false;

function _geminiPrepHash(text) {
    let h = 0;
    for (let i = 0; i < Math.min(text.length, 2000); i++) {
        h = (Math.imul(31, h) + text.charCodeAt(i)) | 0;
    }
    return (h >>> 0).toString(36) + '_' + text.length;
}

async function _savePrepProgress(textHash, sections, outputs, knownSpeakers, activeProfile = '') {
    try {
        await fetch('/api/prep-progress/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text_hash: textHash,
                sections,
                outputs,
                known_speakers: Array.from(knownSpeakers),
                active_profile: activeProfile || '',
                timestamp: Date.now()
            })
        });
    } catch (e) { /* network error — ignore, progress already in memory */ }
}

async function _loadPrepProgress(textHash) {
    try {
        const resp = await fetch(`/api/prep-progress/load?text_hash=${encodeURIComponent(textHash)}`);
        const data = await resp.json();
        if (data.success && data.found) return data.progress;
        return null;
    } catch (e) { return null; }
}

async function _clearPrepProgress(textHash) {
    try {
        await fetch(`/api/prep-progress/clear?text_hash=${encodeURIComponent(textHash)}`, { method: 'DELETE' });
    } catch (e) {}
}

function _showPrepResumePanel(completedCount, totalCount, onResume, onRestart, onAbort) {
    const panel = document.getElementById('gemini-resume-panel');
    const label = document.getElementById('gemini-resume-label');
    const resumeBtn = document.getElementById('gemini-resume-btn');
    const restartBtn = document.getElementById('gemini-restart-btn');
    const abortBtn = document.getElementById('gemini-abort-panel-btn');
    if (!panel) return;
    const remaining = totalCount - completedCount;
    if (label) label.textContent = `⚠️ ${completedCount} of ${totalCount} sections completed. ${remaining} remaining — will resume from section ${completedCount + 1}.`;
    panel.style.display = 'block';
    [resumeBtn, restartBtn, abortBtn].forEach(btn => {
        if (!btn) return;
        const clone = btn.cloneNode(true);
        btn.replaceWith(clone);
    });
    document.getElementById('gemini-resume-btn').addEventListener('click', () => {
        panel.style.display = 'none';
        onResume();
    });
    document.getElementById('gemini-restart-btn').addEventListener('click', () => {
        panel.style.display = 'none';
        onRestart();
    });
    const abortPanelBtn = document.getElementById('gemini-abort-panel-btn');
    if (abortPanelBtn) {
        abortPanelBtn.addEventListener('click', () => {
            panel.style.display = 'none';
            if (onAbort) onAbort();
        });
    }
}

function _hidePrepResumePanel() {
    const panel = document.getElementById('gemini-resume-panel');
    if (panel) panel.style.display = 'none';
}

async function _checkAndShowPrepResume() {
    const inputEl = document.getElementById('input-text');
    if (!inputEl || !inputEl.value.trim()) return;
    const textHash = _geminiPrepHash(inputEl.value);
    const saved = await _loadPrepProgress(textHash);
    if (saved && saved.outputs && saved.outputs.length > 0 && saved.sections) {
        const geminiBtn = document.getElementById('gemini-process-btn');
        _showPrepResumePanel(
            saved.outputs.length,
            saved.sections.length,
            () => _runGeminiPrep(geminiBtn, inputEl.value, textHash, saved),
            async () => {
                await _clearPrepProgress(textHash);
                await _runGeminiPrep(geminiBtn, inputEl.value, textHash, null);
            },
            async () => {
                await _clearPrepProgress(textHash);
                showNotification('Prep aborted. All progress discarded.', 'error');
            }
        );
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

    const textHash = _geminiPrepHash(text);
    const savedProgress = await _loadPrepProgress(textHash);

    if (savedProgress && savedProgress.outputs && savedProgress.outputs.length > 0 && savedProgress.sections) {
        _showPrepResumePanel(
            savedProgress.outputs.length,
            savedProgress.sections.length,
            () => _runGeminiPrep(buttonEl, text, textHash, savedProgress),
            async () => {
                await _clearPrepProgress(textHash);
                await _runGeminiPrep(buttonEl, text, textHash, null);
            },
            async () => {
                await _clearPrepProgress(textHash);
                showNotification('Prep aborted. All progress discarded.', 'error');
            }
        );
        return;
    }

    await _runGeminiPrep(buttonEl, text, textHash, null);
}

async function _runGeminiPrep(buttonEl, text, textHash, savedProgress) {
    const inputEl = document.getElementById('input-text');
    const enabledHeadings = getEnabledSectionHeadings();
    const promptOverride = getSelectedGeminiPromptOverride();
    updateGeminiProgress({ visible: true, label: 'Preparing LLM request…', count: '', fill: 5 });

    const originalLabel = buttonEl ? buttonEl.textContent : '';
    if (buttonEl) {
        buttonEl.disabled = true;
        buttonEl.textContent = 'Processing with LLM...';
    }

    _geminiPrepPauseRequested = false;
    _geminiPrepAbortRequested = false;
    _hidePrepResumePanel();

    const pauseBtn = document.getElementById('gemini-pause-btn');
    const abortBtn = document.getElementById('gemini-abort-btn');
    if (pauseBtn) {
        pauseBtn.textContent = 'Pause';
        pauseBtn.disabled = false;
        pauseBtn.onclick = () => {
            _geminiPrepPauseRequested = true;
            pauseBtn.textContent = 'Pausing…';
            pauseBtn.disabled = true;
        };
    }
    if (abortBtn) {
        abortBtn.style.display = 'inline-block';
        abortBtn.textContent = 'Abort';
        abortBtn.disabled = false;
        abortBtn.onclick = () => {
            _geminiPrepAbortRequested = true;
            abortBtn.textContent = 'Aborting…';
            abortBtn.disabled = true;
            if (pauseBtn) { pauseBtn.disabled = true; }
        };
    }

    showNotification('Preparing text with the selected LLM...', 'info');

    try {
        let sections, outputs, knownSpeakers, activeProfile;

        if (savedProgress) {
            sections = savedProgress.sections;
            outputs = savedProgress.outputs.slice();
            knownSpeakers = new Set(savedProgress.known_speakers || []);
            activeProfile = savedProgress.active_profile || '';
            latestGeminiBookTitle = resolveBookTitleFromSections(sections) || latestGeminiBookTitle;
            updateGeminiProgress({
                visible: true,
                label: `Resuming from section ${outputs.length + 1} of ${sections.length}…`,
                count: `${outputs.length} / ${sections.length}`,
                fill: Math.round((outputs.length / sections.length) * 100)
            });
        } else {
            updateGeminiProgress({
                visible: true,
                label: 'Building section list for the LLM…',
                count: '',
                fill: 15
            });

            const sectionsResponse = await fetch('/api/gemini/sections', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    text,
                    prefer_chapters: true,
                    section_headings: enabledHeadings
                })
            });

            const sectionsData = await sectionsResponse.json();
            if (!sectionsData.success) {
                throw new Error(sectionsData.error || 'Unable to build LLM sections');
            }

            sections = sectionsData.sections || [];
            if (!sections.length) {
                throw new Error('No sections were generated for LLM processing.');
            }
            latestGeminiBookTitle = resolveBookTitleFromSections(sections) || latestGeminiBookTitle;

            outputs = [];
            knownSpeakers = new Set();
            activeProfile = '';
            if (currentStats?.speakers?.length) {
                currentStats.speakers.forEach(name => {
                    if (typeof name === 'string' && name.trim()) {
                        knownSpeakers.add(name.trim().toLowerCase());
                    }
                });
            }
        }

        const MAX_RETRIES = 5;
        const RETRY_BASE_DELAY_MS = 8000;
        const resumeFrom = outputs.length;

        for (let i = resumeFrom; i < sections.length; i++) {
            const section = sections[i];
            const currentIndex = i + 1;
            updateGeminiProgress({
                visible: true,
                label: `Processing section ${currentIndex} of ${sections.length}…`,
                count: `${currentIndex} / ${sections.length}`,
                fill: Math.round((currentIndex / sections.length) * 100)
            });

            const payload = {
                content: section.content || ''
            };
            if (promptOverride) {
                payload.prompt_override = promptOverride;
            }
            if (knownSpeakers.size > 0) {
                payload.known_speakers = Array.from(knownSpeakers);
            }
            if (activeProfile) {
                payload.preferred_profile = activeProfile;
            }

            let sectionData = null;
            let retryAttempt = 0;
            let retryProfileId = payload.preferred_profile || '';
            while (true) {
                const sectionResponse = await fetch('/api/gemini/process-section', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });

                sectionData = await sectionResponse.json();

                if (sectionData.success) break;

                const isRetryable = sectionData.retryable === true || sectionResponse.status === 503;
                if (!isRetryable) {
                    throw new Error(sectionData.error || `The LLM failed on section ${currentIndex}`);
                }

                const reportedRetryProfile = sectionData.retry_profile?.id || payload.preferred_profile || '';
                if (reportedRetryProfile && reportedRetryProfile !== retryProfileId) {
                    retryProfileId = reportedRetryProfile;
                    payload.preferred_profile = reportedRetryProfile;
                    retryAttempt = 0;
                }

                if (retryAttempt >= MAX_RETRIES) {
                    const nextProfile = sectionData.next_profile || null;
                    if (!nextProfile?.id) {
                        throw new Error(sectionData.error || `The LLM failed on section ${currentIndex}`);
                    }
                    const previousName = sectionData.retry_profile?.name || retryProfileId || 'current LLM profile';
                    retryProfileId = nextProfile.id;
                    payload.preferred_profile = nextProfile.id;
                    activeProfile = nextProfile.id;
                    retryAttempt = 0;
                    showNotification(
                        `${previousName} remained unavailable after ${MAX_RETRIES} retries. Switching to ${nextProfile.name || nextProfile.id}.`,
                        'warning'
                    );
                    continue;
                }

                retryAttempt += 1;
                const delaySec = Math.round((RETRY_BASE_DELAY_MS * retryAttempt) / 1000);
                updateGeminiProgress({
                    visible: true,
                    label: `Section ${currentIndex}: ${sectionData.retry_profile?.name || 'LLM'} busy — retrying in ${delaySec}s (${retryAttempt}/${MAX_RETRIES})…`,
                    count: `${currentIndex} / ${sections.length}`,
                    fill: Math.round((currentIndex / sections.length) * 100)
                });
                await new Promise(resolve => setTimeout(resolve, RETRY_BASE_DELAY_MS * retryAttempt));
            }

            const previousProfile = activeProfile;
            const profileUsed = sectionData.llm_profile_used || null;
            if (profileUsed?.id) {
                activeProfile = profileUsed.id;
            }
            if (profileUsed && previousProfile && activeProfile !== previousProfile) {
                showNotification(`LLM preprocessing switched to ${profileUsed.name} (${profileUsed.provider}: ${profileUsed.model || 'default model'}).`, 'warning');
            } else if (profileUsed && Array.isArray(sectionData.provider_failures) && sectionData.provider_failures.length > 0) {
                showNotification(`Primary LLM was unavailable. Continuing with ${profileUsed.name} (${profileUsed.provider}: ${profileUsed.model || 'default model'}).`, 'warning');
            }

            if (Array.isArray(sectionData.speakers)) {
                sectionData.speakers.forEach(speaker => {
                    if (typeof speaker === 'string' && speaker.trim()) {
                        knownSpeakers.add(speaker.trim().toLowerCase());
                    }
                });
            }
            outputs.push(sectionData.result_text || '');
            await _savePrepProgress(textHash, sections, outputs, knownSpeakers, activeProfile);

            if (_geminiPrepAbortRequested) {
                await _clearPrepProgress(textHash);
                showNotification('Prep aborted. All progress discarded.', 'error');
                return;
            }

            if (_geminiPrepPauseRequested) {
                _showPrepResumePanel(
                    outputs.length,
                    sections.length,
                    () => _runGeminiPrep(buttonEl, text, textHash, { sections, outputs, known_speakers: Array.from(knownSpeakers), active_profile: activeProfile }),
                    async () => {
                        await _clearPrepProgress(textHash);
                        await _runGeminiPrep(buttonEl, text, textHash, null);
                    },
                    async () => { await _clearPrepProgress(textHash); showNotification('Prep aborted. All progress discarded.', 'error'); }
                );
                showNotification(`Prep paused at section ${outputs.length} of ${sections.length}. Progress saved — click Resume to continue.`, 'warning');
                return;
            }
        }

        updateGeminiProgress({
            visible: true,
            label: 'Combining LLM output…',
            count: `${sections.length} / ${sections.length}`,
            fill: 100
        });

        await _clearPrepProgress(textHash);
        inputEl.value = outputs.join('\n\n').trim();

        lastAnalyzedText = '';
        showNotification('LLM processing complete! Text updated.', 'success');
        const analysisSucceeded = await analyzeText({ auto: true });
        if (analysisSucceeded) {
            await fetchSpeakerProfiles();
        }
    } catch (error) {
        console.error('LLM processing failed:', error);
        const saved = await _loadPrepProgress(textHash);
        if (saved && saved.outputs && saved.outputs.length > 0) {
            _showPrepResumePanel(
                saved.outputs.length,
                saved.sections.length,
                () => _runGeminiPrep(buttonEl, text, textHash, saved),
                async () => {
                    await _clearPrepProgress(textHash);
                    await _runGeminiPrep(buttonEl, text, textHash, null);
                },
                async () => { await _clearPrepProgress(textHash); showNotification('Prep aborted. All progress discarded.', 'error'); }
            );
            showNotification(`Prep stopped at section ${saved.outputs.length} of ${saved.sections.length}. Progress saved — click Resume to continue.`, 'warning');
        } else {
            alert(error.message || 'Failed to process with the selected LLM');
        }
    } finally {
        if (buttonEl) {
            buttonEl.disabled = false;
            buttonEl.textContent = originalLabel || 'Prep Text';
        }
        const pauseBtn = document.getElementById('gemini-pause-btn');
        if (pauseBtn) { pauseBtn.textContent = 'Pause'; pauseBtn.disabled = false; }
        const abortBtnFin = document.getElementById('gemini-abort-btn');
        if (abortBtnFin) { abortBtnFin.style.display = 'none'; abortBtnFin.disabled = false; }
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

// Section heading chips management
const DEFAULT_SECTION_HEADINGS = ['book', 'chapter', 'section', 'letter', 'part', 'prologue', 'epilogue'];
let enabledSectionHeadings = [...DEFAULT_SECTION_HEADINGS];
let customSectionHeadings = [];

function initSectionHeadingChips() {
    renderDefaultHeadingChips();
    renderCustomHeadingChips();
    setupHeadingChipEventListeners();
}

function renderDefaultHeadingChips() {
    const container = document.getElementById('default-heading-chips');
    if (!container) return;

    container.innerHTML = '';
    DEFAULT_SECTION_HEADINGS.forEach(heading => {
        const chip = document.createElement('div');
        const isEnabled = enabledSectionHeadings.includes(heading);
        chip.className = 'heading-chip';
        chip.dataset.heading = heading;
        chip.dataset.type = 'default';
        chip.style.cssText = `
            padding: 6px 12px;
            border-radius: 16px;
            border: 1px solid ${isEnabled ? 'var(--primary-color, #6366f1)' : 'var(--border-color, #4a5568)'};
            background: ${isEnabled ? 'var(--primary-color, #6366f1)' : 'transparent'};
            color: ${isEnabled ? 'white' : 'var(--text-color, #e2e8f0)'};
            cursor: pointer;
            font-size: 0.85rem;
            user-select: none;
            transition: all 0.2s ease;
        `;
        chip.textContent = heading.charAt(0).toUpperCase() + heading.slice(1);
        chip.addEventListener('click', () => toggleDefaultHeading(heading));
        container.appendChild(chip);
    });
}

function renderCustomHeadingChips() {
    const container = document.getElementById('custom-heading-chips');
    if (!container) return;

    container.innerHTML = '';
    customSectionHeadings.forEach(heading => {
        const chip = document.createElement('div');
        chip.className = 'heading-chip';
        chip.dataset.heading = heading;
        chip.dataset.type = 'custom';
        chip.style.cssText = `
            padding: 6px 12px;
            border-radius: 16px;
            border: 1px solid var(--success-color, #10b981);
            background: rgba(16, 185, 129, 0.1);
            color: var(--success-color, #10b981);
            cursor: pointer;
            font-size: 0.85rem;
            user-select: none;
            display: flex;
            align-items: center;
            gap: 6px;
            transition: all 0.2s ease;
        `;
        chip.innerHTML = `
            <span>${heading.charAt(0).toUpperCase() + heading.slice(1)}</span>
            <span style="font-size: 1.1rem; line-height: 1; cursor: pointer; opacity: 0.7;">&times;</span>
        `;
        chip.addEventListener('click', (e) => {
            if (e.target.tagName === 'SPAN' && e.target.textContent === '×') {
                removeCustomHeading(heading);
            }
        });
        container.appendChild(chip);
    });
}

function toggleDefaultHeading(heading) {
    const index = enabledSectionHeadings.indexOf(heading);
    if (index > -1) {
        enabledSectionHeadings.splice(index, 1);
    } else {
        enabledSectionHeadings.push(heading);
    }
    invalidateSectionReviewCache();
    lastAnalyzedText = '';
    renderDefaultHeadingChips();
    // Trigger re-analysis to update section detection
    const input = document.getElementById('input-text');
    if (input && input.value.trim()) {
        analyzeText({ auto: true });
    }
}

function addCustomHeading(heading) {
    const normalized = heading.trim().toLowerCase();
    if (!normalized) return;
    if (DEFAULT_SECTION_HEADINGS.includes(normalized)) {
        alert('This is already a default heading. Toggle it above instead.');
        return;
    }
    if (customSectionHeadings.includes(normalized)) {
        alert('This custom heading already exists.');
        return;
    }
    customSectionHeadings.push(normalized);
    invalidateSectionReviewCache();
    lastAnalyzedText = '';
    renderCustomHeadingChips();
    // Trigger re-analysis to update section detection
    const input = document.getElementById('input-text');
    if (input && input.value.trim()) {
        analyzeText({ auto: true });
    }
}

function removeCustomHeading(heading) {
    const index = customSectionHeadings.indexOf(heading);
    if (index > -1) {
        customSectionHeadings.splice(index, 1);
        invalidateSectionReviewCache();
        lastAnalyzedText = '';
        renderCustomHeadingChips();
        // Trigger re-analysis to update section detection
        const input = document.getElementById('input-text');
        if (input && input.value.trim()) {
            analyzeText({ auto: true });
        }
    }
}

function setupHeadingChipEventListeners() {
    const addBtn = document.getElementById('add-custom-heading-btn');
    const input = document.getElementById('custom-heading-input');
    if (addBtn && input) {
        addBtn.addEventListener('click', () => {
            const heading = input.value.trim();
            if (heading) {
                addCustomHeading(heading);
                input.value = '';
            }
        });
        input.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                addBtn.click();
            }
        });
    }
}

function getEnabledSectionHeadings() {
    return [...enabledSectionHeadings, ...customSectionHeadings];
}

function getSectionHeadingCacheKey(headings = getEnabledSectionHeadings()) {
    return JSON.stringify(
        headings
            .map(heading => String(heading || '').trim().toLowerCase())
            .filter(Boolean)
            .sort()
    );
}

function invalidateSectionReviewCache() {
    sectionReviewData = null;
    sectionReviewLastFetchedText = null;
    sectionReviewLastFetchedHeadingKey = null;
}

// Initialize app
document.addEventListener('DOMContentLoaded', () => {
    initTabs();
    loadHealthStatus();
    setupEventListeners();
    preloadGenerationControls();
    initDefaultVoiceFxPanel();
    _checkAndShowPrepResume();
    if (typeof loadLibraryItems === 'function') {
        loadLibraryItems();
    }
    initAutoAnalyze();
    const chapterCheckbox = document.getElementById('split-chapters-checkbox');
    syncFullStoryOption(chapterCheckbox, true);
    initVoiceDropdownFilters();
    initSectionHeadingChips();
    if (!currentStats) {
        displayStatistics({
            speakers: [],
            speaker_count: 1,
            total_chunks: 0,
            word_count: 0,
            estimated_duration: 0,
            has_speaker_tags: false
        });
    }
    window.TTSStoryHelp?.init();
    document.addEventListener('click', event => {
        if (event.target instanceof Element && event.target.closest('[data-open-qwen3-settings]')) {
            openQwen3EngineSettings();
        }
    });
});

function initVoiceDropdownFilters() {
    // Set up filter change handlers for main voice dropdown
    const genderFilter = document.getElementById('main-voice-filter-gender');
    const languageFilter = document.getElementById('main-voice-filter-language');
    
    if (genderFilter) {
        genderFilter.addEventListener('change', () => {
            voiceDropdownFilters.gender = genderFilter.value;
            populateReferenceSelects();
        });
    }
    
    if (languageFilter) {
        languageFilter.addEventListener('change', () => {
            voiceDropdownFilters.language = languageFilter.value;
            populateReferenceSelects();
        });
    }
}

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
    updateSectionReviewButton(false);
    refreshChapterHint();
}

// Tab switching
function initTabs() {
    const tabList = document.querySelector('.tabs');
    const tabButtons = Array.from(document.querySelectorAll('.tab-button'));
    const tabContents = Array.from(document.querySelectorAll('.tab-content'));
    if (!tabButtons.length) return;
    if (tabList) {
        tabList.setAttribute('role', 'tablist');
        tabList.setAttribute('aria-label', 'TTS-Story pages');
    }

    function activateTab(button) {
        const tabName = button.dataset.tab;

        tabButtons.forEach(btn => {
            const isActive = btn === button;
            btn.classList.toggle('active', isActive);
            btn.setAttribute('aria-selected', String(isActive));
            btn.setAttribute('tabindex', isActive ? '0' : '-1');
        });

        tabContents.forEach(content => {
            const isActive = content.id === `${tabName}-tab`;
            content.classList.toggle('active', isActive);
            content.setAttribute('aria-hidden', String(!isActive));
        });
    }

    tabButtons.forEach((button, index) => {
        const tabName = button.dataset.tab;
        const panel = document.getElementById(`${tabName}-tab`);
        button.id = button.id || `${tabName}-tab-button`;
        button.setAttribute('role', 'tab');
        button.setAttribute('aria-controls', `${tabName}-tab`);
        if (panel) {
            panel.setAttribute('role', 'tabpanel');
            panel.setAttribute('aria-labelledby', button.id);
        }
        button.addEventListener('click', () => {
            activateTab(button);
        });
        button.addEventListener('keydown', event => {
            let targetIndex = null;
            if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
                targetIndex = (index + 1) % tabButtons.length;
            } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
                targetIndex = (index - 1 + tabButtons.length) % tabButtons.length;
            } else if (event.key === 'Home') {
                targetIndex = 0;
            } else if (event.key === 'End') {
                targetIndex = tabButtons.length - 1;
            }
            if (targetIndex === null) return;
            event.preventDefault();
            const target = tabButtons[targetIndex];
            target.click();
            target.focus();
        });
    });

    activateTab(tabButtons.find(button => button.classList.contains('active')) || tabButtons[0]);
}

// Setup event listeners
function setupEventListeners() {
    const analyzeBtn = document.getElementById('analyze-btn');
    const generateBtn = document.getElementById('generate-btn');
    const engineFirstRunOverlay = document.getElementById('engine-first-run-overlay');
    const engineFirstRunClose = document.getElementById('engine-first-run-close');
    const engineFirstRunOk = document.getElementById('engine-first-run-ok');
    const geminiBtn = document.getElementById('gemini-process-btn');
    const downloadBtn = document.getElementById('download-btn');
    const newGenerationBtn = document.getElementById('new-generation-btn');
    const resetAssignmentsBtn = document.getElementById('reset-assignments-btn');
    const cancelBtn = document.getElementById('cancel-btn');
    const chapterCheckbox = document.getElementById('split-chapters-checkbox');
    const fullStoryCheckbox = document.getElementById('full-story-checkbox');
    const reviewSectionsBtn = document.getElementById('review-sections-btn');
    const sectionReviewOverlay = document.getElementById('section-review-modal-overlay');
    const sectionReviewClose = document.getElementById('section-review-modal-close');
    const sectionReviewFooterClose = document.getElementById('section-review-close-btn');
    const sectionReviewBody = document.getElementById('section-review-modal-body');
    const sectionEditOverlay = document.getElementById('section-edit-modal-overlay');
    const sectionEditClose = document.getElementById('section-edit-modal-close');
    const sectionEditCancel = document.getElementById('section-edit-cancel-btn');
    const sectionEditSave = document.getElementById('section-edit-save-btn');
    const sectionEditInput = document.getElementById('section-edit-input');
    const speakersList = document.getElementById('speakers-list');
    const speakerModalOverlay = document.getElementById('speaker-edit-modal-overlay');
    const speakerModalClose = document.getElementById('speaker-edit-modal-close');
    const speakerModalFooterClose = document.getElementById('speaker-edit-modal-close-btn');
    const speakerReadyCheckbox = document.getElementById('speaker-ready-checkbox');
    const buildSpeakerProfilesBtn = document.getElementById('build-speaker-profiles-btn');
    const batchGenerateBtn = document.getElementById('generate-voices-btn');
    const batchModalOverlay = document.getElementById('speaker-batch-modal-overlay');
    const batchModalClose = document.getElementById('speaker-batch-modal-close');
    const batchModalCancel = document.getElementById('speaker-batch-cancel-btn');
    const batchStartOver = document.getElementById('speaker-batch-start-over-btn');
    const batchModalConfirm = document.getElementById('speaker-batch-confirm-btn');
    const batchPrefixInput = document.getElementById('speaker-batch-prefix');
    const batchCandidateCountInput = document.getElementById('speaker-batch-candidate-count');
    const batchDesignEngineSelect = document.getElementById('speaker-batch-design-engine');
    const batchStatus = document.getElementById('speaker-batch-status');
    const batchProgress = document.getElementById('speaker-batch-progress');
    const batchProgressFill = document.getElementById('speaker-batch-progress-fill');
    const batchProgressLabel = document.getElementById('speaker-batch-progress-label');
    const batchComplete = document.getElementById('speaker-batch-complete');
    const batchCompleteSummary = document.getElementById('speaker-batch-complete-summary');
    const batchOkBtn = document.getElementById('speaker-batch-ok-btn');
    let batchGenerationInFlight = false;
    let batchPauseRequested = false;
    const projectManageBtn = document.getElementById('project-manage-btn');
    const projectModalOverlay = document.getElementById('project-modal-overlay');
    const projectModalClose = document.getElementById('project-modal-close');
    const projectModalFooterClose = document.getElementById('project-modal-close-btn');
    const projectSaveConfirm = document.getElementById('project-save-confirm');
    const projectList = document.getElementById('project-list');
    const projectNameInput = document.getElementById('project-name-input');
    const projectStatus = document.getElementById('project-status');

    engineFirstRunClose?.addEventListener('click', closeEngineFirstRunNotice);
    engineFirstRunOk?.addEventListener('click', closeEngineFirstRunNotice);
    engineFirstRunOverlay?.addEventListener('click', event => {
        if (event.target === engineFirstRunOverlay) closeEngineFirstRunNotice();
    });

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
    if (buildSpeakerProfilesBtn) {
        buildSpeakerProfilesBtn.addEventListener('click', async () => {
            const idleLabel = buildSpeakerProfilesBtn.textContent || 'Build Profiles';
            buildSpeakerProfilesBtn.disabled = true;
            buildSpeakerProfilesBtn.textContent = 'Building…';
            try {
                await fetchSpeakerProfiles();
            } finally {
                buildSpeakerProfilesBtn.textContent = idleLabel;
                buildSpeakerProfilesBtn.disabled = !currentStats?.speakers?.length;
            }
        });
    }
    if (cancelBtn) {
        cancelBtn.addEventListener('click', cancelGeneration);
    }
    if (reviewSectionsBtn) {
        reviewSectionsBtn.addEventListener('click', async () => {
            if (sectionReviewInFlight) return;
            const text = document.getElementById('input-text')?.value || '';
            if (!text.trim()) {
                showNotification('Enter text first to review sections.', 'warning');
                return;
            }
            openSectionReviewModal();
            const enabledHeadings = getEnabledSectionHeadings();
            const headingCacheKey = getSectionHeadingCacheKey(enabledHeadings);

            // Reuse edited preview data only when both the story and active
            // detector selection are unchanged.
            if (
                sectionReviewData
                && sectionReviewLastFetchedText === text
                && sectionReviewLastFetchedHeadingKey === headingCacheKey
            ) {
                renderSectionReview(sectionReviewData);
                return;
            }

            sectionReviewInFlight = true;
            try {
                const payload = { text, section_headings: enabledHeadings };
                const response = await fetch('/api/sections/preview', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                const data = await response.json();
                if (data && data.success) {
                    sectionReviewLastFetchedText = text;
                    sectionReviewLastFetchedHeadingKey = headingCacheKey;
                    sectionReviewData = data;
                }
                renderSectionReview(data);
            } catch (error) {
                renderSectionReview({ success: false, error: error.message || 'Unable to load section preview.' });
            } finally {
                sectionReviewInFlight = false;
            }
        });
    }
    if (sectionReviewOverlay) {
        sectionReviewOverlay.addEventListener('click', event => {
            if (event.target === sectionReviewOverlay) {
                closeSectionReviewModal();
            }
        });
    }
    if (sectionReviewBody) {
        sectionReviewBody.addEventListener('click', event => {
            const target = event.target instanceof HTMLElement ? event.target : null;
            const button = target?.closest('.section-review-edit');
            if (!button) return;
            const sectionId = button.dataset.sectionId;
            const card = sectionReviewBody.querySelector(`[data-section-id="${sectionId}"]`);
            if (!card) return;
            const headingStart = Number(card.dataset.headingStart);
            const headingEnd = Number(card.dataset.headingEnd);
            openSectionEditModal({
                sectionId,
                kind: card.dataset.sectionKind,
                bookIndex: Number(card.dataset.bookIndex),
                chapterIndex: Number(card.dataset.chapterIndex),
                sectionIndex: Number(card.dataset.sectionIndex),
                heading: card.dataset.heading || '',
                title: card.dataset.title || '',
                headingStart: Number.isFinite(headingStart) ? headingStart : null,
                headingEnd: Number.isFinite(headingEnd) ? headingEnd : null,
            });
        });
    }
    if (sectionReviewClose) {
        sectionReviewClose.addEventListener('click', closeSectionReviewModal);
    }
    if (sectionReviewFooterClose) {
        sectionReviewFooterClose.addEventListener('click', closeSectionReviewModal);
    }
    if (sectionEditOverlay) {
        sectionEditOverlay.addEventListener('click', event => {
            if (event.target === sectionEditOverlay) {
                closeSectionEditModal();
            }
        });
    }
    if (sectionEditClose) {
        sectionEditClose.addEventListener('click', closeSectionEditModal);
    }
    if (sectionEditCancel) {
        sectionEditCancel.addEventListener('click', closeSectionEditModal);
    }
    if (sectionEditSave) {
        sectionEditSave.addEventListener('click', () => {
            const value = sectionEditInput?.value?.trim();
            if (!value) {
                showNotification('Heading text cannot be empty.', 'warning');
                return;
            }
            applySectionHeadingEdit(value);
        });
    }
    if (sectionEditInput) {
        sectionEditInput.addEventListener('keydown', event => {
            if (event.key === 'Enter') {
                event.preventDefault();
                const value = sectionEditInput.value.trim();
                if (!value) {
                    showNotification('Heading text cannot be empty.', 'warning');
                    return;
                }
                applySectionHeadingEdit(value);
            }
        });
    }
    if (speakersList) {
        speakersList.addEventListener('click', event => {
            const target = event.target instanceof HTMLElement ? event.target : null;
            const chip = target?.closest('.speaker-tag');
            if (!chip) return;
            const speaker = chip.dataset.speaker;
            if (speaker) {
                openSpeakerEditModal(speaker);
                populateReferenceSelects();
                populateVoiceSelects();
                updateAssignmentModes(getSelectedJobEngine() || runtimeSettings?.tts_engine || 'kokoro');
            }
        });
    }
    if (speakerModalOverlay) {
        speakerModalOverlay.addEventListener('click', event => {
            if (event.target === speakerModalOverlay) {
                closeSpeakerEditModal();
            }
        });
    }
    if (speakerModalClose) {
        speakerModalClose.addEventListener('click', closeSpeakerEditModal);
    }
    if (speakerModalFooterClose) {
        speakerModalFooterClose.addEventListener('click', closeSpeakerEditModal);
    }
    if (speakerReadyCheckbox) {
        speakerReadyCheckbox.addEventListener('change', event => {
            const speaker = event.currentTarget.dataset.speaker;
            if (speaker) {
                setSpeakerReadyState(speaker, event.currentTarget.checked);
            }
        });
    }
    if (projectManageBtn) {
        projectManageBtn.addEventListener('click', () => {
            openProjectModal();
            if (projectNameInput && !projectNameInput.value) {
                const customHeadings = customSectionHeadings.join(', ') || '';
                projectNameInput.value = customHeadings || projectNameInput.value;
            }
        });
    }
    if (projectModalOverlay) {
        projectModalOverlay.addEventListener('click', event => {
            if (event.target === projectModalOverlay) {
                closeProjectModal();
            }
        });
    }
    if (projectModalClose) {
        projectModalClose.addEventListener('click', closeProjectModal);
    }
    if (projectModalFooterClose) {
        projectModalFooterClose.addEventListener('click', closeProjectModal);
    }
    function resetBatchModal() {
        batchPauseRequested = false;
        if (batchStatus) {
            batchStatus.textContent = '';
        }
        if (batchProgress) {
            batchProgress.style.display = 'none';
        }
        if (batchComplete) {
            batchComplete.classList.add('hidden');
        }
        if (batchOkBtn) {
            batchOkBtn.classList.add('hidden');
        }
        if (batchModalCancel) {
            batchModalCancel.classList.remove('hidden');
            batchModalCancel.textContent = 'Cancel';
            batchModalCancel.disabled = false;
        }
        if (batchStartOver) {
            batchStartOver.classList.add('hidden');
        }
        if (batchModalConfirm) {
            batchModalConfirm.classList.remove('hidden');
            batchModalConfirm.disabled = false;
            batchModalConfirm.textContent = 'Generate';
        }
        if (batchProgressFill) {
            batchProgressFill.style.width = '0%';
        }
        if (batchProgressLabel) {
            batchProgressLabel.textContent = 'Preparing...';
        }
    }
    if (batchGenerateBtn) {
        batchGenerateBtn.addEventListener('click', () => {
            if (batchModalOverlay) {
                batchModalOverlay.classList.remove('hidden');
            }
            document.getElementById('speaker-batch-modal')?.classList.remove('hidden');
            resetBatchModal();
            const speakers = currentStats?.speakers || [];
            if (hasResumableBulkVoiceGeneration(speakers)) {
                const next = Math.max(0, Number(bulkVoiceGenerationState.next_index || 0));
                batchModalConfirm.dataset.resume = 'true';
                batchModalConfirm.textContent = `Resume at ${next + 1} of ${speakers.length}`;
                if (batchStatus) batchStatus.textContent = `A saved casting batch is ready to resume. ${next} of ${speakers.length} speakers are already complete.`;
                if (batchPrefixInput) batchPrefixInput.value = bulkVoiceGenerationState.prefix || '';
                if (batchCandidateCountInput) batchCandidateCountInput.value = String(bulkVoiceGenerationState.candidate_count || 1);
                if (batchDesignEngineSelect) batchDesignEngineSelect.value = normalizeVoiceDesignEngine(bulkVoiceGenerationState.design_engine);
                batchStartOver?.classList.remove('hidden');
            } else {
                delete batchModalConfirm.dataset.resume;
            }
            batchPrefixInput?.focus();
        });
    }
    function closeBatchModal() {
        if (batchGenerationInFlight) {
            batchPauseRequested = true;
            if (batchModalCancel) {
                batchModalCancel.disabled = true;
                batchModalCancel.textContent = 'Pausing...';
            }
            if (batchStatus) batchStatus.textContent = 'Pause requested. The current speaker will finish before this batch stops.';
            return;
        }
        batchModalOverlay?.classList.add('hidden');
        document.getElementById('speaker-batch-modal')?.classList.add('hidden');
        resetBatchModal();
    }
    if (batchModalOverlay) {
        batchModalOverlay.addEventListener('click', event => {
            if (event.target === batchModalOverlay) {
                closeBatchModal();
            }
        });
    }
    if (batchModalClose) {
        batchModalClose.addEventListener('click', closeBatchModal);
    }
    if (batchModalCancel) {
        batchModalCancel.addEventListener('click', () => {
            if (!batchGenerationInFlight) {
                closeBatchModal();
                return;
            }
            batchPauseRequested = true;
            batchModalCancel.disabled = true;
            batchModalCancel.textContent = 'Pausing...';
            if (batchStatus) batchStatus.textContent = 'Pause requested. The current speaker will finish, then the checkpoint will be saved.';
        });
    }
    if (batchStartOver) {
        batchStartOver.addEventListener('click', async () => {
            bulkVoiceGenerationState = null;
            delete batchModalConfirm.dataset.resume;
            batchModalConfirm.textContent = 'Generate';
            batchStartOver.classList.add('hidden');
            if (batchStatus) batchStatus.textContent = 'The previous checkpoint was cleared. A new batch will start from the first speaker.';
            await persistBulkVoiceGenerationState();
        });
    }
    if (batchModalConfirm) {
        batchModalConfirm.addEventListener('click', async () => {
            if (batchGenerationInFlight) return;
            batchGenerationInFlight = true;
            batchPauseRequested = false;
            const resumeRequested = batchModalConfirm.dataset.resume === 'true';
            batchModalConfirm.disabled = true;
            batchModalConfirm.textContent = 'Generating...';
            try {
                const batchCandidateCount = Math.max(
                    1,
                    Math.min(Number.parseInt(batchCandidateCountInput?.value, 10) || 1, 10)
                );
                if (batchCandidateCountInput) batchCandidateCountInput.value = String(batchCandidateCount);
                const batchDesignEngine = normalizeVoiceDesignEngine(batchDesignEngineSelect?.value);
                await requireVoiceDesignBackend(batchDesignEngine);
                (currentStats?.speakers || []).forEach(speaker => {
                    updateSpeakerProfileEntry(speaker, {
                        voice_candidate_count: batchCandidateCount,
                        voice_design_engine: batchDesignEngine
                    });
                });
                const batchResult = await runBatchVoiceGeneration(batchPrefixInput?.value || '', batchStatus, {
                    container: batchProgress,
                    fill: batchProgressFill,
                    label: batchProgressLabel
                }, {
                    completeCard: batchComplete,
                    completeSummary: batchCompleteSummary
                }, {
                    resume: resumeRequested,
                    shouldPause: () => batchPauseRequested,
                    designEngine: batchDesignEngine
                });
                if (batchResult?.paused) {
                    batchModalConfirm.classList.remove('hidden');
                    batchModalConfirm.dataset.resume = 'true';
                    batchModalConfirm.textContent = `Resume at ${bulkVoiceGenerationState.next_index + 1} of ${bulkVoiceGenerationState.total_speakers}`;
                    batchStartOver?.classList.remove('hidden');
                    batchModalCancel.classList.remove('hidden');
                    batchModalCancel.textContent = 'Close';
                    batchModalCancel.disabled = false;
                    return;
                }
                if (batchOkBtn) {
                    batchOkBtn.classList.remove('hidden');
                }
                if (batchModalCancel) {
                    batchModalCancel.classList.add('hidden');
                }
                if (batchModalConfirm) {
                    batchModalConfirm.classList.add('hidden');
                }
            } catch (error) {
                console.error('Bulk voice generation stopped', error);
                if (bulkVoiceGenerationState) {
                    bulkVoiceGenerationState.status = 'interrupted';
                    bulkVoiceGenerationState.updated_at = new Date().toISOString();
                    await persistBulkVoiceGenerationState().catch(() => false);
                    batchModalConfirm.dataset.resume = 'true';
                    batchModalConfirm.textContent = `Resume at ${bulkVoiceGenerationState.next_index + 1} of ${bulkVoiceGenerationState.total_speakers}`;
                    batchStartOver?.classList.remove('hidden');
                }
                if (batchStatus) batchStatus.textContent = error.message || 'Voice generation stopped.';
                showNotification(error.message || 'Voice generation stopped.', 'warning');
            } finally {
                batchGenerationInFlight = false;
                batchModalConfirm.disabled = false;
                if (batchModalConfirm.dataset.resume !== 'true') batchModalConfirm.textContent = 'Generate';
            }
        });
    }
    if (batchOkBtn) {
        batchOkBtn.addEventListener('click', () => {
            closeBatchModal();
            document.querySelector('.tab-button[data-tab="generate"]')?.click();
        });
    }

    // ── Auto Assign modal ──────────────────────────────────────────────────
    const autoAssignBtn = document.getElementById('auto-assign-voices-btn');
    const autoAssignModalOverlay = document.getElementById('auto-assign-modal-overlay');
    const autoAssignModal = document.getElementById('auto-assign-modal');
    const autoAssignModalClose = document.getElementById('auto-assign-modal-close');
    const autoAssignCancelBtn = document.getElementById('auto-assign-cancel-btn');
    const autoAssignConfirmBtn = document.getElementById('auto-assign-confirm-btn');
    const autoAssignTableBody = document.getElementById('auto-assign-table-body');
    const autoAssignTable = document.getElementById('auto-assign-table');
    const autoAssignNoVoices = document.getElementById('auto-assign-no-voices');
    const autoAssignNoSpeakers = document.getElementById('auto-assign-no-speakers');
    const autoAssignThresholdSlider = document.getElementById('auto-assign-threshold-slider');
    const autoAssignThresholdLabel = document.getElementById('auto-assign-threshold-label');

    function fuzzyMatchScore(a, b) {
        const sa = (a || '').toLowerCase().trim();
        const sb = (b || '').toLowerCase().trim();
        if (!sa || !sb) return 0;
        if (sa === sb) return 1;
        const longer = sa.length > sb.length ? sa : sb;
        const shorter = sa.length > sb.length ? sb : sa;
        if (longer.includes(shorter)) return shorter.length / longer.length;
        let matches = 0;
        const used = new Array(sb.length).fill(false);
        for (let i = 0; i < sa.length; i++) {
            for (let j = 0; j < sb.length; j++) {
                if (!used[j] && sa[i] === sb[j]) {
                    matches++;
                    used[j] = true;
                    break;
                }
            }
        }
        return (2 * matches) / (sa.length + sb.length);
    }

    function buildAutoAssignProposals() {
        const speakers = Array.isArray(currentStats?.speakers) ? currentStats.speakers : [];
        const voices = availableChatterboxVoices || [];
        return speakers.map(speaker => {
            let bestScore = 0;
            let bestVoice = null;
            voices.forEach(v => {
                const score = fuzzyMatchScore(speaker, v.name || '');
                if (score > bestScore) {
                    bestScore = score;
                    bestVoice = v;
                }
            });
            return {
                speaker,
                bestVoice,
                score: bestScore,
                bestPromptValue: (bestVoice?.prompt_path || bestVoice?.file_name || '').trim()
            };
        });
    }

    function renderAutoAssignTable(threshold) {
        const speakers = Array.isArray(currentStats?.speakers) ? currentStats.speakers : [];
        const voices = availableChatterboxVoices || [];
        if (!autoAssignTableBody || speakers.length === 0 || voices.length === 0) return;
        const proposals = buildAutoAssignProposals();
        const sortedVoices = voices.slice().sort((a, b) => (a.name || '').localeCompare(b.name || ''));
        autoAssignTableBody.innerHTML = '';
        proposals.forEach(({ speaker, score, bestPromptValue }) => {
            const meetsThreshold = score >= threshold;
            const promptValue = meetsThreshold ? bestPromptValue : '';
            const scoreClass = score >= 0.9 ? 'score-high' : score >= threshold ? 'score-med' : 'score-none';
            const scoreLabel = score > 0 ? `${Math.round(score * 100)}%` : 'No match';
            const voiceOptions = sortedVoices
                .map(v => {
                    const vPath = (v.prompt_path || v.file_name || '').trim();
                    const selected = vPath && vPath === promptValue ? ' selected' : '';
                    return `<option value="${vPath}"${selected}>${v.name || vPath}</option>`;
                })
                .join('');
            const tr = document.createElement('tr');
            tr.innerHTML = `
                <td class="speaker-name-cell">${speaker}</td>
                <td>
                    <select class="auto-assign-voice-select" data-speaker="${speaker}">
                        <option value="">— No assignment —</option>
                        ${voiceOptions}
                    </select>
                </td>
                <td><span class="auto-assign-score ${scoreClass}">${scoreLabel}</span></td>
            `;
            autoAssignTableBody.appendChild(tr);
        });
    }

    function getAutoAssignThreshold() {
        return (parseInt(autoAssignThresholdSlider?.value, 10) || 80) / 100;
    }

    function openAutoAssignModal() {
        const speakers = Array.isArray(currentStats?.speakers) ? currentStats.speakers : [];
        const voices = availableChatterboxVoices || [];

        autoAssignNoSpeakers?.classList.toggle('hidden', speakers.length > 0);
        autoAssignNoVoices?.classList.toggle('hidden', voices.length > 0);
        autoAssignTable?.classList.toggle('hidden', speakers.length === 0 || voices.length === 0);

        if (autoAssignThresholdSlider) {
            autoAssignThresholdSlider.value = 80;
        }
        if (autoAssignThresholdLabel) {
            autoAssignThresholdLabel.textContent = '80%';
        }

        if (speakers.length > 0 && voices.length > 0) {
            renderAutoAssignTable(0.8);
        }

        autoAssignModalOverlay?.classList.remove('hidden');
        autoAssignModal?.classList.remove('hidden');
    }

    function closeAutoAssignModal() {
        autoAssignModalOverlay?.classList.add('hidden');
        autoAssignModal?.classList.add('hidden');
        if (autoAssignTableBody) autoAssignTableBody.innerHTML = '';
    }

    function applyAutoAssignSelections() {
        if (!autoAssignTableBody) return;
        autoAssignTableBody.querySelectorAll('.auto-assign-voice-select').forEach(select => {
            const speaker = select.dataset.speaker;
            const promptValue = select.value?.trim();
            if (!speaker) return;
            if (promptValue) {
                turboSelectionState[speaker] = promptValue;
            } else {
                delete turboSelectionState[speaker];
            }
            document.querySelectorAll(
                `#inline-voice-assignment-list .reference-select[data-speaker="${speaker}"],` +
                `#speaker-edit-modal-body .reference-select[data-speaker="${speaker}"]`
            ).forEach(refSelect => {
                refSelect.value = promptValue || '';
                const row = refSelect.closest('.voice-assignment-row');
                if (row) updateInlineSampleButtonState(row, { stopPlayback: false });
            });
        });
        showNotification('Voice samples assigned.', 'success');
        closeAutoAssignModal();
    }

    if (autoAssignThresholdSlider) {
        autoAssignThresholdSlider.addEventListener('input', () => {
            const pct = parseInt(autoAssignThresholdSlider.value, 10) || 80;
            if (autoAssignThresholdLabel) autoAssignThresholdLabel.textContent = `${pct}%`;
            renderAutoAssignTable(pct / 100);
        });
    }
    if (autoAssignBtn) {
        autoAssignBtn.addEventListener('click', openAutoAssignModal);
    }
    if (autoAssignModalOverlay) {
        autoAssignModalOverlay.addEventListener('click', event => {
            if (event.target === autoAssignModalOverlay) closeAutoAssignModal();
        });
    }
    if (autoAssignModalClose) {
        autoAssignModalClose.addEventListener('click', closeAutoAssignModal);
    }
    if (autoAssignCancelBtn) {
        autoAssignCancelBtn.addEventListener('click', closeAutoAssignModal);
    }
    if (autoAssignConfirmBtn) {
        autoAssignConfirmBtn.addEventListener('click', applyAutoAssignSelections);
    }
    // ── End Auto Assign modal ──────────────────────────────────────────────

    if (projectSaveConfirm) {
        projectSaveConfirm.addEventListener('click', async () => {
            const project = getProjectState();
            const name = projectNameInput?.value?.trim() || `Project ${new Date().toLocaleString()}`;
            project.name = name;
            try {
                await refreshProjectLibrary();
            } catch (error) {
                showNotification(error.message || 'Unable to open the shared project library.', 'warning');
                return;
            }
            const existingByName = savedProjects.find(item => item.name === name);
            if (existingByName) {
                const confirmed = confirm(`"${name}" already exists. Overwrite this project?`);
                if (!confirmed) {
                    return;
                }
                project.id = existingByName.id;
            }
            try {
                const saved = await saveProject(project);
                activeProjectId = saved?.id || project.id;
                if (projectStatus) {
                    projectStatus.textContent = `Saved ${name}`;
                }
            } catch (error) {
                showNotification(error.message || 'Unable to save the project.', 'warning');
            }
        });
    }
    if (projectList) {
        projectList.addEventListener('click', async event => {
            const target = event.target instanceof HTMLElement ? event.target : null;
            const button = target?.closest('[data-project-action]');
            if (!button) return;
            const action = button.dataset.projectAction;
            const projectId = button.dataset.projectId;
            const project = savedProjects.find(item => String(item.id) === String(projectId));
            if (action === 'load' && project) {
                closeProjectModal();
                applyProjectState(project);
            }
            if (action === 'delete' && projectId) {
                try {
                    await deleteProject(projectId);
                } catch (error) {
                    showNotification(error.message || 'Unable to delete the project.', 'warning');
                }
            }
        });
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

    const outputFormatSelect = document.getElementById('job-output-format');
    if (outputFormatSelect) {
        outputFormatSelect.addEventListener('change', event => {
            handleOutputFormatChange(event.target.value);
        });
        handleOutputFormatChange(outputFormatSelect.value);
    }

    const jobEngineSelect = document.getElementById('job-tts-engine');
    if (jobEngineSelect) {
        jobEngineSelect.addEventListener('change', event => {
            // Preserve any assigned cloning sample before engine-specific controls
            // are repopulated or Analyze Text rebuilds the speaker rows.
            captureCompatibleVoiceSamples();
            const engineName = (event.target.value || '').toLowerCase();
            updateEngineUI(engineName);
            updateModeIndicator(engineName);
            // Refresh voice prompt dropdowns to apply engine-specific duration filtering
            populateReferenceSelects();
            const currentText = document.getElementById('input-text')?.value?.trim();
            if (currentText && lastAnalyzedText && currentText === lastAnalyzedText) {
                analyzeText({ auto: true });
            }
        });
    }

    const referenceUploadInput = document.getElementById('reference-prompt-upload-input');
    if (referenceUploadInput) {
        referenceUploadInput.addEventListener('change', handleReferenceUpload);
    }
    const globalReferenceSelect = document.getElementById('chatterbox-reference-select');
    if (globalReferenceSelect) {
        globalReferenceSelect.addEventListener('change', handleReferenceSelectChange);
    }
    refreshGlobalChatterboxPreviewButton();
    const globalPreviewBtn = document.getElementById('global-chatterbox-preview-btn');
    if (globalPreviewBtn) {
        globalPreviewBtn.addEventListener('click', event => {
            const select = document.getElementById('chatterbox-reference-select');
            const selection = select?.value?.trim();
            if (!selection) {
                showNotification('Select a reference voice first.', 'warning');
                return;
            }
            const voiceEntry = findChatterboxVoiceByPath(selection);
            if (!voiceEntry || !voiceEntry.id) {
                showNotification('Unable to resolve that reference voice.', 'warning');
                return;
            }
            if (!window.chatterboxPreviewController) {
                showNotification('Preview controls are still loading. Try again shortly.', 'warning');
                return;
            }
            window.chatterboxPreviewController.toggleById(voiceEntry.id, event.currentTarget);
        });
    }
    initializeProjectLibrary()
        .then(() => renderProjectList())
        .catch(error => console.warn('Shared project library initialization failed', error));
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

// Engine display name mapping
const engineDisplayNames = {
    'kokoro': 'Kokoro · Local GPU',
    'kokoro_replicate': 'Kokoro · Replicate',
    'chatterbox_turbo_local': 'Chatterbox · Local GPU',
    'chatterbox_turbo_replicate': 'Chatterbox · Replicate',
    'voxcpm_local': 'VoxCPM 1.5 · Local GPU',
    'qwen3_custom': 'Qwen3-TTS · Custom Voice',
    'qwen3_clone': 'Qwen3-TTS · Voice Clone',
    'pocket_tts': 'Pocket TTS · Clone',
    'pocket_tts_preset': 'Pocket TTS · Preset',
    'kitten_tts': 'KittenTTS',
    'index_tts': 'IndexTTS',
    'dots_tts': 'Dot.TTS · Voice Clone',
    'audio8_tts': 'Audio8 TTS · Voice Clone',
    'breeze_tts_2': 'Breeze TTS 2 · Design / Clone / Direction',
    'omnivoice_clone': 'OmniVoice · Clone',
    'omnivoice_design': 'OmniVoice · Design',
    'azure_speech': 'Microsoft Azure Speech · Cloud',
    'edge_tts': 'Microsoft Edge TTS · Experimental Cloud',
    'elevenlabs': 'ElevenLabs · Cloud',
    'openai_tts': 'OpenAI-compatible TTS · Cloud',
    'localai_tts': 'LocalAI TTS · Self-hosted',
    'breeze_api': 'Breeze API · Hosted'
};

// Update mode indicator based on engine name (called when dropdown changes)
function updateModeIndicator(engineName) {
    const modeEl = document.getElementById('current-mode');
    if (!modeEl) return;

    const normalizedEngine = (engineName || 'kokoro').toLowerCase();
    const isLocal = ['kokoro', 'chatterbox_turbo_local', 'voxcpm_local', 'qwen3_custom', 'qwen3_clone', 'pocket_tts', 'pocket_tts_preset', 'kitten_tts', 'index_tts', 'dots_tts', 'audio8_tts', 'breeze_tts_2', 'localai_tts']
        .includes(normalizedEngine);

    modeEl.textContent = engineDisplayNames[normalizedEngine] || normalizedEngine;
    modeEl.style.color = isLocal ? '#10b981' : '#f59e0b';
}

// Load health status
async function loadHealthStatus() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        
        if (data.success) {
            setQwenVoiceDesignAvailability(
                data.qwen3_voice_design_available ?? data.qwen3_available,
                true
            );
            setBreezeVoiceDesignAvailability(data.breeze_voice_design_available, true);
            const engineName = data.tts_engine || 'kokoro';
            updateModeIndicator(engineName);
            document.getElementById('cuda-status').textContent = 
                data.cuda_available ? 'Available' : 'Not Available';
        }
    } catch (error) {
        console.error('Error loading health status:', error);
        setQwenVoiceDesignAvailability(false, false);
        setBreezeVoiceDesignAvailability(false, false);
    }
}

// Analyze text
async function analyzeText(options = {}) {
    _updateTagErrorBanner();
    const { auto = false } = options;
    if (auto && analyzeInFlight) {
        analyzeRerunRequested = true;
        return false;
    }
    const text = document.getElementById('input-text').value;
    
    if (!text.trim()) {
        alert('Please enter some text first');
        return false;
    }
    
    if (!auto) {
        showNotification('Analyzing text...', 'info');
    }
    
    analyzeInFlight = true;
    analyzeRerunRequested = false;
    try {
        const enabledHeadings = getEnabledSectionHeadings();
        const payload = { text, section_headings: enabledHeadings };
        const selectedEngine = getSelectedJobEngine() || runtimeSettings?.tts_engine;
        if (selectedEngine) {
            payload.tts_engine = selectedEngine;
        }
        const response = await fetch('/api/analyze', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
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
    finally {
        const shouldRerun = analyzeRerunRequested;
        analyzeRerunRequested = false;
        analyzeInFlight = false;
        if (shouldRerun) {
            analyzeText({ auto: true });
        }
    }
}

function normalizeSpeakerLabel(label) {
    return (label || '').toString().trim().toLowerCase().replace(/[^a-z0-9]/g, '');
}

function normalizeSpeakerKey(label) {
    const normalized = normalizeSpeakerLabel(label);
    return normalized || (label || '').toString().trim().toLowerCase();
}

function inferVoiceAgeCategory(source) {
    const text = (source || '').toString().toLowerCase();
    const ageMatch = text.match(/\b(\d{1,2})(?:\s*[-–]\s*(\d{1,2}))?\s*[- ]?\s*(?:years?|yrs?)(?:\s*[- ]\s*old)?\b/);
    if (ageMatch) {
        const age = Math.max(Number(ageMatch[1]), Number(ageMatch[2] || ageMatch[1]));
        if (age <= 12) return 'child';
        if (age <= 17) return 'teenage';
        if (age <= 29) return 'young-adult';
        if (age >= 65) return 'elderly';
        if (age >= 45) return 'middle-aged';
        return 'adult';
    }
    if (/\b(child|child-like|kid|pre-?teen|boy|girl)\b/.test(text)) return 'child';
    if (/\b(teen|teenage|adolescent)\b/.test(text)) return 'teenage';
    if (/\byoung adult\b/.test(text)) return 'young-adult';
    if (/\b(middle-aged|middle aged)\b/.test(text)) return 'middle-aged';
    if (/\b(elderly|senior|older adult)\b/.test(text)) return 'elderly';
    return 'adult';
}

function buildVoiceAgeGenderPrefix(gender, source) {
    const genderLabel = gender === 'female' ? 'FEMALE' : gender === 'male' ? 'MALE' : 'GENDER-NEUTRAL';
    const age = inferVoiceAgeCategory(source);
    if (age === 'child') return `${genderLabel} CHILD VOICE`;
    const ageLabel = {
        'teenage': 'TEENAGE',
        'young-adult': 'YOUNG ADULT',
        'middle-aged': 'MIDDLE-AGED',
        'elderly': 'ELDERLY',
        'adult': 'ADULT'
    }[age];
    return `${ageLabel} ${genderLabel} VOICE`;
}

function buildLocalVoiceDesignPrompt(speaker, voiceType, suppliedPrompt = '') {
    const supplied = (suppliedPrompt || '').toString().replace(/\s+/g, ' ').trim();
    const voice = (voiceType || '').toString().replace(/\s+/g, ' ').trim();
    if (!voice && !supplied) return '';
    const source = `${speaker || ''} ${voice} ${supplied}`.toLowerCase();
    let gender = 'neutral';
    if (/\bfemale\b|\bwoman\b|\bgirl\b|\bsoprano\b|\balto\b/.test(source)) {
        gender = 'female';
    } else if (/\bmale\b|\bman\b|\bboy\b|\bbaritone\b|\bbass\b|\btenor\b/.test(source)) {
        gender = 'male';
    }
    const genderPhrase = buildVoiceAgeGenderPrefix(gender, source);
    let positiveVoice = (supplied || voice)
        .replace(/\b(?:suitable\s+)?for\s+(?:sustained\s+)?(?:an?\s+)?audiobook(?:\s+(?:dialogue|narration))?\b/gi, ' ')
        .replace(/\baudiobook(?:\s+(?:dialogue|narration))?\b/gi, ' ')
        .replace(/\b(?:(?:female|male|gender[- ]neutral)\s+child|(?:teenage|young adult|middle[- ]aged|elderly|adult)\s+(?:female|male|gender[- ]neutral))\s+voice\b[.,;:]?/gi, ' ')
        .replace(/\bchild[- ]like\s*\((\d{1,2}(?:\s*[-–]\s*\d{1,2})?)\s*years?\)/gi, 'age $1')
        .replace(/\bchild[- ]like\b/gi, ' ')
        .replace(/\bemotional(?=\s*[.,;]|$)/gi, 'delivery')
        .replace(/\b(?:but\s+)?(?:not|never|no)\b[^,.;]*[,.;]?/gi, '')
        .replace(/\s+/g, ' ')
        .trim()
        .replace(/[.;,]+$/, '');
    if (!positiveVoice) positiveVoice = voice.replace(/\s+/g, ' ').trim().replace(/[.;,]+$/, '');
    if (positiveVoice && !/\baccent\b|\bEnglish\b/i.test(positiveVoice)) {
        positiveVoice = `${positiveVoice}. Neutral English accent`;
    }
    let prompt = `${genderPhrase}. ${positiveVoice}`.replace(/\s+/g, ' ').trim().replace(/\.+$/, '');
    if (prompt.length > 150) {
        const shortened = prompt.slice(0, 150);
        prompt = shortened.slice(0, shortened.lastIndexOf(' ') > 100 ? shortened.lastIndexOf(' ') : 150);
    }
    return `${prompt}.`;
}

function setSpeakerProfiles(profiles) {
    Object.keys(speakerProfiles).forEach(key => delete speakerProfiles[key]);
    if (!profiles) return;
    Object.entries(profiles).forEach(([key, profile]) => {
        const normalized = normalizeSpeakerKey(key || profile?.name || '');
        if (!normalized) return;
        const name = profile?.name || key;
        const voice = profile?.voice || '';
        speakerProfiles[normalized] = {
            name,
            description: profile?.description || '',
            voice,
            voice_design_prompt: buildLocalVoiceDesignPrompt(name, voice, profile?.voice_design_prompt),
            voice_preview_text: profile?.voice_preview_text || '',
            voice_candidate_count: Math.max(1, Math.min(Number.parseInt(profile?.voice_candidate_count, 10) || 1, 10)),
            voice_design_engine: normalizeVoiceDesignEngine(profile?.voice_design_engine),
            selected_voice_id: profile?.selected_voice_id || '',
            selected_voice_name: profile?.selected_voice_name || '',
            selected_voice_path: profile?.selected_voice_path || ''
        };
    });
}

function findSpeakerProfile(speaker) {
    const key = normalizeSpeakerKey(speaker);
    if (speakerProfiles[key]) {
        return { profile: speakerProfiles[key], matchKey: key };
    }
    const strippedKey = key.replace(/(male|female|man|woman)$/i, '');
    if (strippedKey && speakerProfiles[strippedKey]) {
        return { profile: speakerProfiles[strippedKey], matchKey: strippedKey };
    }
    const matches = Object.entries(speakerProfiles).filter(([profileKey]) =>
        key.includes(profileKey) || profileKey.includes(key)
    );
    if (matches.length === 1) {
        return { profile: matches[0][1], matchKey: matches[0][0] };
    }
    return { profile: null, matchKey: key };
}

function updateSpeakerProfileEntry(speaker, updates = {}) {
    if (!speaker) return;
    const { profile, matchKey } = findSpeakerProfile(speaker);
    const targetKey = matchKey || normalizeSpeakerKey(speaker);
    const nextProfile = {
        name: profile?.name || speaker,
        description: profile?.description || '',
        voice: profile?.voice || '',
        voice_design_prompt: profile?.voice_design_prompt || '',
        voice_preview_text: profile?.voice_preview_text || '',
        voice_candidate_count: profile?.voice_candidate_count || 1,
        voice_design_engine: normalizeVoiceDesignEngine(profile?.voice_design_engine),
        selected_voice_id: profile?.selected_voice_id || '',
        selected_voice_name: profile?.selected_voice_name || '',
        selected_voice_path: profile?.selected_voice_path || '',
        ...updates
    };
    speakerProfiles[targetKey] = nextProfile;
}

function findGeneratedSpeakerProfile(speaker, profiles) {
    if (!speaker || !profiles || typeof profiles !== 'object') return null;
    const speakerKey = normalizeSpeakerKey(speaker);
    const speakerBaseKey = speakerKey.replace(/(male|female|neutral)$/i, '');
    const entries = Object.entries(profiles);
    const exactMatch = entries.find(([key, profile]) =>
        normalizeSpeakerKey(profile?.name || key) === speakerKey
    );
    if (exactMatch) return exactMatch[1];
    const baseMatch = entries.find(([key, profile]) => {
        const candidateKey = normalizeSpeakerKey(profile?.name || key);
        return speakerBaseKey && candidateKey.replace(/(male|female|neutral)$/i, '') === speakerBaseKey;
    });
    if (baseMatch) return baseMatch[1];
    return entries.length === 1 ? entries[0][1] : null;
}

async function buildSingleSpeakerProfile(speaker) {
    if (!speaker) return;
    const buildBtn = document.querySelector('#speaker-profile-summary [data-role="speaker-build-profile"]');
    const promptOverride = document.getElementById('gemini-speaker-profile-prompt')?.value?.trim() || '';
    const processedText = document.getElementById('input-text')?.value?.trim() || '';
    if (!processedText) {
        showNotification('Paste or load tagged story text before building a speaker profile.', 'warning');
        return;
    }
    const context = latestGeminiBookTitle ? `Book title: ${latestGeminiBookTitle}` : '';
    try {
        if (buildBtn) {
            buildBtn.disabled = true;
            buildBtn.classList.add('is-loading');
            buildBtn.textContent = 'Building...';
        }
        showNotification(`Building a profile for ${speaker}...`, 'info');
        const response = await fetch('/api/gemini/speaker-profiles', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                speakers: [speaker],
                context,
                prompt_override: promptOverride || undefined,
                processed_text: processedText
            })
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to build the speaker profile');
        }
        const generatedProfile = findGeneratedSpeakerProfile(speaker, data.profiles);
        if (!generatedProfile) {
            throw new Error(`The LLM did not return a usable profile for ${speaker}.`);
        }
        const existingProfile = findSpeakerProfile(speaker).profile;
        const generatedVoice = generatedProfile.voice || '';
        updateSpeakerProfileEntry(speaker, {
            name: speaker,
            description: generatedProfile.description || '',
            voice: generatedVoice,
            voice_design_prompt: buildLocalVoiceDesignPrompt(
                speaker,
                generatedVoice,
                generatedProfile.voice_design_prompt || existingProfile?.voice_design_prompt || ''
            ),
            voice_preview_text: generatedProfile.voice_preview_text || existingProfile?.voice_preview_text || ''
        });
        renderSpeakerProfileSummary(speaker);
        const profileName = data.llm_profile_used?.name;
        showNotification(
            `Profile built for ${speaker}${profileName ? ` using ${profileName}` : ''}.`,
            'success'
        );
    } catch (error) {
        console.error('Single-speaker profile generation failed:', error);
        showNotification(error.message || 'Failed to build the speaker profile.', 'warning');
    } finally {
        const currentBuildBtn = document.querySelector('#speaker-profile-summary [data-role="speaker-build-profile"]');
        if (currentBuildBtn) {
            currentBuildBtn.disabled = false;
            currentBuildBtn.classList.remove('is-loading');
            currentBuildBtn.textContent = 'Build Profile';
        }
    }
}

function parseGenderFromSpeakerName(speaker) {
    const tokens = (speaker || '').toString().toLowerCase().split(/[^a-z0-9]+/).filter(Boolean);
    if (tokens.includes('female')) return 'Female';
    if (tokens.includes('male')) return 'Male';
    if (tokens.includes('neutral') || tokens.includes('nonbinary')) return 'Neutral';
    return null;
}

async function parseVoiceDesignApiResponse(response, operation = 'complete the voice-design request') {
    const rawBody = await response.text();
    let data = null;
    try {
        data = rawBody ? JSON.parse(rawBody) : {};
    } catch (_error) {
        if (response.status === 404) {
            const restartError = new Error('The updated voice-design backend is not running. Close TTS-Story completely, restart it, and try again.');
            restartError.code = 'VOICE_DESIGN_BACKEND_RESTART_REQUIRED';
            throw restartError;
        }
        throw new Error(`The server returned an invalid response while trying to ${operation}.`);
    }
    if (!response.ok) {
        throw new Error(data.error || `Unable to ${operation} (HTTP ${response.status}).`);
    }
    return data;
}

async function requireVoiceDesignBackend(engine = 'qwen3') {
    const normalizedEngine = normalizeVoiceDesignEngine(engine);
    const engineConfig = getVoiceDesignEngineConfig(normalizedEngine);
    let response;
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 8000);
    try {
        response = await fetch('/api/health', { signal: controller.signal });
    } catch (_error) {
        const restartError = new Error('TTS-Story lost its connection to the backend. Restart TTS-Story before generating voices.');
        restartError.code = 'VOICE_DESIGN_BACKEND_RESTART_REQUIRED';
        throw restartError;
    } finally {
        clearTimeout(timeoutId);
    }
    const data = await parseVoiceDesignApiResponse(response, `verify the ${engineConfig.label} voice-design backend`);
    const apiVersion = normalizedEngine === 'breeze'
        ? Number(data.breeze_voice_design_api_version || 0)
        : Number(data.qwen3_voice_design_api_version || 0);
    const minimumVersion = normalizedEngine === 'breeze' ? 1 : 2;
    if (apiVersion < minimumVersion) {
        const restartError = new Error('The browser has newer voice-design controls than the running backend. Close TTS-Story completely, restart it, and try again.');
        restartError.code = 'VOICE_DESIGN_BACKEND_RESTART_REQUIRED';
        throw restartError;
    }
    const available = normalizedEngine === 'breeze'
        ? data.breeze_voice_design_available
        : (data.qwen3_voice_design_available ?? data.qwen3_available);
    if (normalizedEngine === 'breeze') setBreezeVoiceDesignAvailability(available, true);
    else setQwenVoiceDesignAvailability(available, true);
    if (!available) {
        const installError = new Error(engineConfig.installMessage);
        installError.code = 'VOICE_DESIGN_INSTALL_REQUIRED';
        throw installError;
    }
}

async function requireQwenVoiceDesignBackend() {
    return requireVoiceDesignBackend('qwen3');
}

async function pollVoiceDesignTask(taskId, urlFactory, statusLabel) {
    if (!taskId) {
        throw new Error('Missing task id for queued request.');
    }
    if (statusLabel) {
        showNotification(statusLabel, 'info');
    }
    const start = Date.now();
    const timeoutMs = 30 * 60 * 1000;
    while (Date.now() - start < timeoutMs) {
        const url = typeof urlFactory === 'function' ? urlFactory(taskId) : `/api/qwen3/voice-design/tasks/${taskId}`;
        const response = await fetch(url);
        const data = await parseVoiceDesignApiResponse(response, 'check voice generation status');
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
    throw new Error('Timed out waiting for voice generation.');
}

async function pollQwenVoiceTask(taskId, statusLabel) {
    if (!taskId) {
        throw new Error('Missing task id for queued request.');
    }
    if (statusLabel) {
        showNotification(statusLabel, 'info');
    }
    const start = Date.now();
    const timeoutMs = 30 * 60 * 1000;
    while (Date.now() - start < timeoutMs) {
        const response = await fetch(`/api/qwen3/voice-design/tasks/${taskId}`);
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
    throw new Error('Timed out waiting for voice generation.');
}

async function refreshChatterboxVoices() {
    try {
        const response = await fetch('/api/chatterbox-voices');
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Unable to load voice prompts');
        }
        window.dispatchEvent(new CustomEvent(CHATTERBOX_VOICES_EVENT_NAME, {
            detail: { voices: data.voices || [] }
        }));
    } catch (error) {
        console.error('Failed to refresh voice prompts', error);
        showNotification(error.message || 'Failed to refresh voice prompts.', 'warning');
    }
}

async function generateSpeakerVoicePrompt(speaker) {
    if (!speaker) return;
    const generateBtn = document.querySelector('#speaker-profile-summary [data-role="speaker-generate-voice"]');
    const { profile } = findSpeakerProfile(speaker);
    const description = profile?.description || '';
    const voice = profile?.voice || '';
    const instruct = profile?.voice_design_prompt || voice || '';
    const shortDescription = voice || '';
    const sampleText = buildCharacterPreviewText(speaker, profile || {});
    if (!shortDescription) {
        showNotification('Add a voice type before generating a voice.', 'warning');
        return;
    }
    if (!instruct) {
        showNotification('Add a Voice Type or Voice Design Prompt before generating a voice.', 'warning');
        return;
    }
    const payload = {
        name: speaker,
        gender: parseGenderFromSpeakerName(speaker),
        language: 'English',
        description: shortDescription,
        text: sampleText,
        instruct
    };
    try {
        if (generateBtn) {
            if (!generateBtn.dataset.labelIdle) {
                generateBtn.dataset.labelIdle = generateBtn.textContent.trim() || 'Generate Voice';
            }
            generateBtn.disabled = true;
            generateBtn.classList.add('is-loading');
            generateBtn.textContent = 'Generating…';
        }
        showNotification('Generating voice preview...', 'info');
        const previewResponse = await fetch('/api/qwen3/voice-design/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                text: payload.text,
                instruct: payload.instruct,
                language: payload.language
            })
        });
        const previewData = await previewResponse.json();
        if (!previewData.success) {
            throw new Error(previewData.error || 'Failed to enqueue preview');
        }
        const previewResult = await pollQwenVoiceTask(previewData.job_id, 'Generating voice preview...');
        if (!previewResult.audio_base64) {
            throw new Error('Preview audio missing from response.');
        }
        showNotification('Saving voice prompt...', 'info');
        if (generateBtn) {
            generateBtn.textContent = 'Saving…';
        }
        const saveResponse = await fetch('/api/qwen3/voice-design/save', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                ...payload,
                audio_base64: previewResult.audio_base64
            })
        });
        const saveData = await saveResponse.json();
        if (!saveData.success) {
            throw new Error(saveData.error || 'Failed to enqueue save');
        }
        await pollQwenVoiceTask(saveData.job_id, 'Saving voice prompt...');
        await refreshChatterboxVoices();
        populateReferenceSelects();
        const latestVoice = availableChatterboxVoices
            .filter(entry => (entry?.name || '').trim().toLowerCase() === speaker.toLowerCase())
            .sort((a, b) => new Date(b?.created_at || 0) - new Date(a?.created_at || 0))[0];
        const promptValue = (latestVoice?.prompt_path || latestVoice?.file_name || '').trim();
        if (promptValue) {
            turboSelectionState[speaker] = promptValue;
            document.querySelectorAll('#inline-voice-assignment-list [data-role="turbo-control"] .reference-select, #speaker-edit-modal-body [data-role="turbo-control"] .reference-select')
                .forEach(select => {
                    if (select?.dataset?.speaker === speaker) {
                        select.value = promptValue;
                    }
                });
            updateInlineSampleButtonState(activeSpeakerRow, { stopPlayback: true });
        }
        showNotification('Voice prompt generated and added to the library.', 'success');
    } catch (error) {
        console.error('Generate voice failed', error);
        showNotification(error.message || 'Failed to generate voice.', 'warning');
    } finally {
        if (generateBtn) {
            generateBtn.disabled = window.qwenVoiceDesignAvailable !== true;
            generateBtn.classList.remove('is-loading');
            generateBtn.textContent = generateBtn.dataset.labelIdle || 'Generate Voice';
        }
    }
}

async function generateSpeakerVoiceCandidatesForSpeaker(speaker) {
    if (!speaker) return;
    const generateBtn = document.querySelector('#speaker-profile-summary [data-role="speaker-generate-voice"]');
    const candidateCount = Math.max(1, Math.min(Number.parseInt(findSpeakerProfile(speaker).profile?.voice_candidate_count, 10) || 1, 10));
    try {
        if (generateBtn) {
            generateBtn.disabled = true;
            generateBtn.classList.add('is-loading');
            generateBtn.textContent = candidateCount === 1 ? 'Generating...' : `Generating ${candidateCount}...`;
        }
        showNotification(
            candidateCount === 1 ? 'Generating voice...' : `Generating ${candidateCount} voice candidates...`,
            'info'
        );
        const { profile } = findSpeakerProfile(speaker);
        const designEngine = normalizeVoiceDesignEngine(profile?.voice_design_engine);
        const candidates = await generateAndSaveVoiceCandidates(speaker, speaker, null, designEngine);
        await refreshChatterboxVoices();
        populateReferenceSelects();
        if (candidates.length > 1) {
            speakerVoiceDesignCandidates[normalizeSpeakerKey(speaker)] = candidates;
        } else {
            delete speakerVoiceDesignCandidates[normalizeSpeakerKey(speaker)];
            const promptValue = (candidates[0]?.prompt_path || candidates[0]?.file_name || '').trim();
            if (promptValue) {
                turboSelectionState[speaker] = promptValue;
                syncSpeakerReferenceAssignment(speaker, promptValue);
            }
            updateSpeakerProfileEntry(speaker, {
                selected_voice_id: candidates[0]?.id || '',
                selected_voice_name: candidates[0]?.name || speaker,
                selected_voice_path: promptValue
            });
        }
        renderSpeakerProfileSummary(speaker);
        syncSpeakerReferenceAssignment(speaker);
        showNotification(
            candidates.length === 1
                ? 'Voice generated and assigned.'
                : `${candidates.length} candidates are ready. Listen and select one.`,
            'success'
        );
    } catch (error) {
        console.error('Generate voice candidates failed', error);
        showNotification(error.message || 'Failed to generate voice candidates.', 'warning');
    } finally {
        const currentButton = document.querySelector('#speaker-profile-summary [data-role="speaker-generate-voice"]');
        if (currentButton) {
            const { profile } = findSpeakerProfile(speaker);
            currentButton.disabled = !voiceDesignEngineAvailable(profile?.voice_design_engine);
            currentButton.classList.remove('is-loading');
            currentButton.textContent = 'Generate Voice';
        }
    }
}

async function approveSpeakerVoiceCandidate(speaker, candidateId, groupId) {
    try {
        const groupCandidates = speakerVoiceDesignCandidates[normalizeSpeakerKey(speaker)] || [];
        const response = await fetch('/api/voice-design/candidates/approve', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                selected_id: candidateId,
                candidate_group_id: groupId,
                candidate_ids: groupCandidates.map(candidate => candidate?.id).filter(Boolean)
            })
        });
        const data = await parseVoiceDesignApiResponse(response, 'approve the selected voice candidate');
        if (!response.ok || !data.success) throw new Error(data.error || 'Unable to approve candidate.');
        await refreshChatterboxVoices();
        populateReferenceSelects();
        const promptValue = (data.voice?.prompt_path || data.voice?.file_name || '').trim();
        if (promptValue) {
            turboSelectionState[speaker] = promptValue;
            syncSpeakerReferenceAssignment(speaker, promptValue);
        }
        updateSpeakerProfileEntry(speaker, {
            selected_voice_id: data.voice?.id || candidateId,
            selected_voice_name: data.voice?.name || '',
            selected_voice_path: promptValue
        });
        delete speakerVoiceDesignCandidates[normalizeSpeakerKey(speaker)];
        renderSpeakerProfileSummary(speaker);
        syncSpeakerReferenceAssignment(speaker);
        updateInlineSampleButtonState(activeSpeakerRow, { stopPlayback: true });
        showNotification(`${data.voice?.name || 'Voice candidate'} approved and assigned.`, 'success');
    } catch (error) {
        showNotification(error.message || 'Unable to approve voice candidate.', 'warning');
    }
}

function renderSpeakerProfileSummary(speaker) {
    const summary = document.getElementById('speaker-profile-summary');
    if (!summary) return;
    if (!speaker) {
        summary.classList.add('hidden');
        summary.innerHTML = '';
        return;
    }
    const { profile } = findSpeakerProfile(speaker);
    const hasProfiles = Object.keys(speakerProfiles).length > 0;
    const description = profile?.description || '';
    const voice = profile?.voice || '';
    const voiceDesignPrompt = profile?.voice_design_prompt || '';
    const voiceDesignEngine = normalizeVoiceDesignEngine(profile?.voice_design_engine);
    const previewText = profile?.voice_preview_text || buildCharacterPreviewText(speaker, profile || {});
    const candidateCount = Math.max(1, Math.min(Number.parseInt(profile?.voice_candidate_count, 10) || 1, 10));
    const selectedVoiceName = profile?.selected_voice_name || '';
    const selectedVoicePath = profile?.selected_voice_path || '';
    const candidates = speakerVoiceDesignCandidates[normalizeSpeakerKey(speaker)] || [];
    const emptyMessage = hasProfiles
        ? 'No profile matched this speaker yet.'
        : 'No speaker profile data yet. Build this profile or run Prep Text.';
    summary.innerHTML = `
        <div class="speaker-profile-row speaker-profile-editor">
            <div class="speaker-profile-fields">
                <label>
                    <strong>Profile:</strong>
                    <textarea class="speaker-profile-input" data-role="speaker-profile-description" rows="3" placeholder="${escapeHtml(emptyMessage)}">${escapeHtml(description)}</textarea>
                </label>
                <label>
                    <strong>Voice Type:</strong>
                    <input class="speaker-profile-input" data-role="speaker-profile-voice" type="text" value="${escapeHtml(voice)}" placeholder="Not available yet." />
                </label>
                <label>
                    <strong>Voice Design Prompt:</strong>
                    <textarea class="speaker-profile-input" data-role="speaker-voice-design-prompt" rows="2" placeholder="ADULT FEMALE VOICE. Warm alto; measured, expressive delivery.">${escapeHtml(voiceDesignPrompt)}</textarea>
                    <small>The selected design engine receives this voice-only instruction, or builds one from Voice Type. The narrative profile is kept separate.</small>
                </label>
                <label>
                    <strong>Voice Design Engine:</strong>
                    <select class="speaker-profile-input" data-role="speaker-voice-design-engine">
                        <option value="qwen3" data-voice-design-option ${voiceDesignEngine === 'qwen3' ? 'selected' : ''}>Qwen3-TTS</option>
                        <option value="breeze" data-voice-design-option ${voiceDesignEngine === 'breeze' ? 'selected' : ''}>Breeze TTS 2</option>
                    </select>
                </label>
                <label>
                    <strong>Preview Text:</strong>
                    <textarea class="speaker-profile-input" data-role="speaker-voice-preview-text" rows="2" readonly>${escapeHtml(previewText)}</textarea>
                    <small>The same standardized inflection passage is used for every candidate.</small>
                </label>
                <label>
                    <strong>Voice Candidates:</strong>
                    <input class="speaker-profile-input speaker-candidate-count" data-role="speaker-voice-candidate-count" type="number" min="1" max="10" step="1" value="${candidateCount}" />
                    <small>Generate one voice by default, or increase this to audition multiple alternatives.</small>
                </label>
            </div>
            <div class="speaker-profile-actions">
                <button type="button" class="btn btn-secondary btn-sm" data-role="speaker-build-profile">Build Profile</button>
                <button type="button" class="btn btn-secondary btn-sm" data-role="speaker-generate-voice" disabled title="Checking voice-design engine availability…">Generate Voice</button>
            </div>
            <div class="engine-action-notice hidden" data-role="voice-design-unavailable">
                <span data-role="voice-design-unavailable-message">Install the selected voice-design engine before generating.</span>
                <button type="button" class="btn btn-secondary btn-sm" data-role="open-voice-design-settings">Open Engine Settings</button>
            </div>
        </div>
        ${candidates.length ? `
            <div class="voice-design-candidates">
                <strong>Select a VoiceDesign candidate:</strong>
                <div class="voice-design-candidate-grid">
                    ${candidates.map(candidate => `
                        <article class="voice-design-candidate">
                            <strong>Candidate ${escapeHtml(candidate.label)}</strong>
                            <audio controls preload="metadata" src="${candidate.audio_base64
                                ? `data:${escapeHtml(candidate.mime_type || 'audio/wav')};base64,${candidate.audio_base64}`
                                : `/api/chatterbox-voices/${encodeURIComponent(candidate.id)}/preview`}"></audio>
                            <button type="button" class="btn btn-secondary btn-sm" data-role="approve-voice-candidate" data-candidate-id="${escapeHtml(candidate.id)}" data-group-id="${escapeHtml(candidate.candidate_group_id)}">Use Candidate ${escapeHtml(candidate.label)}</button>
                        </article>
                    `).join('')}
                </div>
            </div>` : ''}
        ${selectedVoiceName || selectedVoicePath ? `
            <div class="voice-design-selected">
                <strong>Selected Voice:</strong>
                <span>${escapeHtml(selectedVoiceName || selectedVoicePath)}</span>
            </div>` : ''}
    `;
    const descriptionInput = summary.querySelector('[data-role="speaker-profile-description"]');
    const voiceInput = summary.querySelector('[data-role="speaker-profile-voice"]');
    const voiceDesignInput = summary.querySelector('[data-role="speaker-voice-design-prompt"]');
    const voiceDesignEngineSelect = summary.querySelector('[data-role="speaker-voice-design-engine"]');
    const candidateCountInput = summary.querySelector('[data-role="speaker-voice-candidate-count"]');
    const buildBtn = summary.querySelector('[data-role="speaker-build-profile"]');
    const generateBtn = summary.querySelector('[data-role="speaker-generate-voice"]');
    refreshQwenVoiceDesignControls();
    if (descriptionInput) {
        descriptionInput.addEventListener('input', event => {
            updateSpeakerProfileEntry(speaker, { description: event.currentTarget.value || '' });
        });
    }
    if (voiceInput) {
        voiceInput.addEventListener('input', event => {
            updateSpeakerProfileEntry(speaker, { voice: event.currentTarget.value || '' });
        });
    }
    if (voiceDesignInput) {
        voiceDesignInput.addEventListener('input', event => {
            updateSpeakerProfileEntry(speaker, { voice_design_prompt: event.currentTarget.value || '' });
        });
    }
    if (voiceDesignEngineSelect) {
        voiceDesignEngineSelect.addEventListener('change', event => {
            const engine = normalizeVoiceDesignEngine(event.currentTarget.value);
            updateSpeakerProfileEntry(speaker, { voice_design_engine: engine });
            refreshQwenVoiceDesignControls();
        });
    }
    if (candidateCountInput) {
        candidateCountInput.addEventListener('change', event => {
            const value = Math.max(1, Math.min(Number.parseInt(event.currentTarget.value, 10) || 1, 10));
            event.currentTarget.value = String(value);
            updateSpeakerProfileEntry(speaker, { voice_candidate_count: value });
        });
    }
    if (buildBtn) {
        buildBtn.addEventListener('click', () => buildSingleSpeakerProfile(speaker));
    }
    if (generateBtn) {
        generateBtn.addEventListener('click', () => generateSpeakerVoiceCandidatesForSpeaker(speaker));
    }
    summary.querySelector('[data-role="open-voice-design-settings"]')?.addEventListener('click', () => {
        const engine = normalizeVoiceDesignEngine(voiceDesignEngineSelect?.value);
        if (engine === 'breeze') openBreezeEngineSettings();
        else openQwen3EngineSettings();
    });
    summary.querySelectorAll('[data-role="approve-voice-candidate"]').forEach(button => {
        button.addEventListener('click', () => approveSpeakerVoiceCandidate(
            speaker, button.dataset.candidateId, button.dataset.groupId
        ));
    });
    summary.classList.remove('hidden');
}

function levenshteinDistance(a, b) {
    const source = a || '';
    const target = b || '';
    if (source === target) return 0;
    if (!source.length) return target.length;
    if (!target.length) return source.length;

    const matrix = Array.from({ length: source.length + 1 }, () => []);
    for (let i = 0; i <= source.length; i += 1) {
        matrix[i][0] = i;
    }
    for (let j = 0; j <= target.length; j += 1) {
        matrix[0][j] = j;
    }
    for (let i = 1; i <= source.length; i += 1) {
        for (let j = 1; j <= target.length; j += 1) {
            const cost = source[i - 1] === target[j - 1] ? 0 : 1;
            matrix[i][j] = Math.min(
                matrix[i - 1][j] + 1,
                matrix[i][j - 1] + 1,
                matrix[i - 1][j - 1] + cost
            );
        }
    }
    return matrix[source.length][target.length];
}

function speakerSimilarity(a, b) {
    const normalizedA = normalizeSpeakerLabel(a);
    const normalizedB = normalizeSpeakerLabel(b);
    if (!normalizedA || !normalizedB) return 0;
    if (normalizedA === normalizedB) return 1;
    const distance = levenshteinDistance(normalizedA, normalizedB);
    const maxLength = Math.max(normalizedA.length, normalizedB.length) || 1;
    return 1 - distance / maxLength;
}

function getSpeakerDuplicates(speakers, threshold = 0.82) {
    if (!Array.isArray(speakers)) return [];
    const pairs = [];
    for (let i = 0; i < speakers.length; i += 1) {
        for (let j = i + 1; j < speakers.length; j += 1) {
            const score = speakerSimilarity(speakers[i], speakers[j]);
            if (score >= threshold) {
                pairs.push({
                    first: speakers[i],
                    second: speakers[j],
                    score
                });
            }
        }
    }
    return pairs.sort((a, b) => b.score - a.score).slice(0, 6);
}

function renderSpeakerDuplicates(speakers) {
    const container = document.getElementById('speakers-duplicates');
    if (!container) return;
    const duplicates = getSpeakerDuplicates(speakers);
    if (!duplicates.length) {
        container.style.display = 'none';
        container.innerHTML = '';
        return;
    }
    container.style.display = 'block';
    container.innerHTML = '<strong>Possible duplicates detected:</strong>';
    duplicates.forEach(({ first, second, score }) => {
        const row = document.createElement('div');
        row.className = 'duplicate-item';
        const badge = document.createElement('span');
        badge.className = 'duplicate-badge';
        badge.textContent = `${Math.round(score * 100)}% match`;
        const text = document.createElement('span');
        text.textContent = `${first} ↔ ${second}`;
        row.appendChild(text);
        row.appendChild(badge);
        container.appendChild(row);
    });
}

function applySpeakerRename(stats, oldName, newName) {
    if (!stats || !Array.isArray(stats.speakers)) return;
    const updated = stats.speakers.map(name => (name === oldName ? newName : name));
    const seen = new Set();
    const deduped = [];
    updated.forEach(name => {
        const trimmed = (name || '').toString().trim();
        if (!trimmed) return;
        const key = normalizeSpeakerLabel(trimmed) || trimmed.toLowerCase();
        if (!seen.has(key)) {
            seen.add(key);
            deduped.push(trimmed);
        }
    });
    stats.speakers = deduped;
    stats.speaker_count = deduped.length;
    if (stats.speaker_emotions && stats.speaker_emotions[oldName]) {
        stats.speaker_emotions[newName] = stats.speaker_emotions[oldName];
        delete stats.speaker_emotions[oldName];
    }
    if (speakerReadyState[oldName]) {
        speakerReadyState[newName] = speakerReadyState[oldName];
        delete speakerReadyState[oldName];
    }
    if (turboSelectionState[oldName] && !turboSelectionState[newName]) {
        turboSelectionState[newName] = turboSelectionState[oldName];
    }
    delete turboSelectionState[oldName];
    const oldKey = normalizeSpeakerKey(oldName);
    const newKey = normalizeSpeakerKey(newName);
    if (speakerProfiles[oldKey]) {
        speakerProfiles[newKey] = { ...speakerProfiles[oldKey], name: newName };
        delete speakerProfiles[oldKey];
    }
    renderSpeakerProfileSummary(newName);
}

function handleSpeakerEdit(originalName, inputEl) {
    if (!inputEl) return;
    const rawName = inputEl.value.trim();
    const newName = formatSpeakerTagName(rawName);
    if (!newName) {
        inputEl.value = originalName;
        return;
    }
    if (newName !== rawName) {
        inputEl.value = newName;
    }
    if (!currentStats || newName === originalName) return;
    applySpeakerRename(currentStats, originalName, newName);
    displayStatistics(currentStats);
    updateVoiceAssignments(currentStats.speakers);
}

function applySpeakerRenameToText(oldName, newName) {
    const input = document.getElementById('input-text');
    if (!input || !oldName || !newName || oldName === newName) return false;
    const escapedOld = oldName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const escapedNew = newName.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
    const openTag = new RegExp(`\\[${escapedOld}\\]`, 'g');
    const closeTag = new RegExp(`\\[\\/${escapedOld}\\]`, 'g');
    const updated = input.value
        .replace(openTag, `[${escapedNew}]`)
        .replace(closeTag, `[/${escapedNew}]`);
    if (updated === input.value) return false;
    input.value = updated;
    return true;
}

function handleInlineRename(originalName, inputEl) {
    if (!inputEl) return;
    const rawName = inputEl.value.trim();
    const newName = formatSpeakerTagName(rawName);
    if (!newName) {
        inputEl.value = originalName;
        return;
    }
    if (newName !== rawName) {
        inputEl.value = newName;
    }
    if (!currentStats || newName === originalName) return;
    applySpeakerRename(currentStats, originalName, newName);
    applySpeakerRenameToText(originalName, newName);
    displayStatistics(currentStats);
    updateVoiceAssignments(currentStats.speakers);
    if (activeSpeakerModal && activeSpeakerModal === originalName) {
        closeSpeakerEditModal();
    }
    analyzeText({ auto: true });
}

function setSpeakerReadyState(speaker, ready) {
    if (!speaker) return;
    speakerReadyState[speaker] = !!ready;
    const chip = document.querySelector(`#speakers-list .speaker-tag[data-speaker="${speaker}"]`);
    if (chip) {
        chip.classList.toggle('ready', !!ready);
    }
}

function openSpeakerEditModal(speaker) {
    const overlay = document.getElementById('speaker-edit-modal-overlay');
    const modal = document.getElementById('speaker-edit-modal');
    const body = document.getElementById('speaker-edit-modal-body');
    const title = document.getElementById('speaker-edit-modal-title');
    const readyCheckbox = document.getElementById('speaker-ready-checkbox');
    const profileSummary = document.getElementById('speaker-profile-summary');
    const list = document.getElementById('inline-voice-assignment-list');
    if (!overlay || !modal || !body || !list) return;

    if (activeSpeakerRow && activeSpeakerRowOrigin) {
        activeSpeakerRowOrigin.appendChild(activeSpeakerRow);
    }

    const row = list.querySelector(`.voice-assignment-row[data-speaker="${speaker}"]`);
    if (!row) return;

    body.innerHTML = '';
    body.appendChild(row);
    activeSpeakerRow = row;
    activeSpeakerRowOrigin = list;
    activeSpeakerModal = speaker;

    const header = row.querySelector('.assignment-header');
    if (profileSummary && header) {
        header.insertAdjacentElement('afterend', profileSummary);
    }

    if (title) {
        title.textContent = `Edit Speaker: ${speaker}`;
    }
    if (readyCheckbox) {
        readyCheckbox.checked = !!speakerReadyState[speaker];
        readyCheckbox.dataset.speaker = speaker;
    }
    renderSpeakerProfileSummary(speaker);
    populateReferenceSelects();
    syncSpeakerReferenceAssignment(speaker);

    overlay.classList.remove('hidden');
    modal.classList.remove('hidden');
}

function closeSpeakerEditModal() {
    const overlay = document.getElementById('speaker-edit-modal-overlay');
    const modal = document.getElementById('speaker-edit-modal');
    const body = document.getElementById('speaker-edit-modal-body');
    const modalBody = document.querySelector('#speaker-edit-modal .modal-body');
    const profileSummary = document.getElementById('speaker-profile-summary');
    const modalAnchor = document.getElementById('speaker-edit-modal-body');
    if (activeSpeakerRow && activeSpeakerRowOrigin) {
        activeSpeakerRowOrigin.appendChild(activeSpeakerRow);
    }
    if (profileSummary && modalBody && modalAnchor) {
        modalBody.insertBefore(profileSummary, modalAnchor);
    }
    stopSpeakerPreviewAudio();
    if (body) {
        body.innerHTML = '';
    }
    renderSpeakerProfileSummary(null);
    activeSpeakerRow = null;
    activeSpeakerRowOrigin = null;
    activeSpeakerModal = null;
    if (overlay) overlay.classList.add('hidden');
    if (modal) modal.classList.add('hidden');
}

function serializeVoiceDesignCandidateGroups() {
    const groups = {};
    Object.entries(speakerVoiceDesignCandidates).forEach(([speakerKey, candidates]) => {
        if (!Array.isArray(candidates) || !candidates.length) return;
        groups[speakerKey] = candidates.map(candidate => ({
            id: candidate.id || '',
            name: candidate.name || '',
            label: candidate.label || '',
            candidate_group_id: candidate.candidate_group_id || '',
            prompt_path: candidate.prompt_path || candidate.file_name || '',
            file_name: candidate.file_name || '',
            mime_type: candidate.mime_type || 'audio/wav',
            engine: candidate.engine || candidate.voice_design?.engine || '',
            instruction: candidate.instruction || candidate.voice_design?.instruction || '',
            preview_text: candidate.preview_text || candidate.voice_design?.preview_text || '',
            wav_sha256: candidate.wav_sha256 || candidate.voice_design?.wav_sha256 || ''
        }));
    });
    return groups;
}

function restoreVoiceDesignCandidateGroups(groups) {
    Object.keys(speakerVoiceDesignCandidates).forEach(key => delete speakerVoiceDesignCandidates[key]);
    if (!groups || typeof groups !== 'object') return;
    Object.entries(groups).forEach(([speakerKey, candidates]) => {
        if (!Array.isArray(candidates) || !candidates.length) return;
        speakerVoiceDesignCandidates[normalizeSpeakerKey(speakerKey)] = candidates.map(candidate => ({ ...candidate }));
    });
}

function collectPerSpeakerControlValues(selector) {
    return getAssignmentRows().reduce((acc, row) => {
        const speaker = row.dataset.speaker;
        const control = row.querySelector(selector);
        if (speaker && control) acc[speaker] = control.value || '';
        return acc;
    }, {});
}

function getProjectState() {
    return {
        project_schema_version: 2,
        id: Date.now(),
        name: '',
        saved_at: new Date().toISOString(),
        text: document.getElementById('input-text')?.value || '',
        engine: document.getElementById('job-tts-engine')?.value || '',
        default_voice: document.getElementById('default-voice-select')?.value || '',
        reference_prompt: document.getElementById('chatterbox-reference-select')?.value || '',
        qwen_default_speaker: document.getElementById('qwen3-default-speaker')?.value || '',
        qwen_default_language: document.getElementById('qwen3-default-language')?.value || '',
        qwen_default_instruct: document.getElementById('qwen3-default-instruct')?.value || '',
        split_chapters: document.getElementById('split-chapters-checkbox')?.checked || false,
        full_story: document.getElementById('full-story-checkbox')?.checked || false,
        custom_heading: document.getElementById('custom-heading-input')?.value || '',
        enabled_headings: enabledSectionHeadings,
        custom_headings: customSectionHeadings,
        book_title: latestGeminiBookTitle,
        output_format: document.getElementById('job-output-format')?.value || 'mp3',
        output_bitrate: document.getElementById('job-output-bitrate')?.value || '128',
        acx_compliance: document.getElementById('acx-compliance-checkbox')?.checked || false,
        gemini_prompt: document.getElementById('gemini-prompt')?.value || '',
        gemini_preset: document.getElementById('gemini-preset-select')?.value || '',
        bulk_voice_prefix: document.getElementById('speaker-batch-prefix')?.value || '',
        bulk_voice_candidate_count: Math.max(1, Math.min(Number.parseInt(document.getElementById('speaker-batch-candidate-count')?.value, 10) || 1, 10)),
        bulk_voice_design_engine: normalizeVoiceDesignEngine(document.getElementById('speaker-batch-design-engine')?.value),
        assignments: getVoiceAssignments(),
        turbo_selections: buildTurboSelectionMap(),
        qwen_inline_languages: collectPerSpeakerControlValues('.qwen3-language-select'),
        qwen_inline_instructs: collectPerSpeakerControlValues('.qwen3-instruct-input'),
        word_replacements: getAltWordRegistry().filter(entry => entry.original && entry.replacement),
        fx_state: JSON.parse(JSON.stringify(voiceFxState || {})),
        azure_voice_options: JSON.parse(JSON.stringify(azureVoiceOptionState || {})),
        ready_state: JSON.parse(JSON.stringify(speakerReadyState || {})),
        speaker_profiles: JSON.parse(JSON.stringify(speakerProfiles || {})),
        voice_design_candidate_groups: serializeVoiceDesignCandidateGroups(),
        bulk_voice_generation_state: bulkVoiceGenerationState
            ? JSON.parse(JSON.stringify(bulkVoiceGenerationState))
            : null
    };
}

function renderProjectList() {
    const list = document.getElementById('project-list');
    if (!list) return;
    const projects = [...savedProjects];
    if (!projects.length) {
        list.innerHTML = '<p class="help-text">No saved projects yet.</p>';
        return;
    }
    list.innerHTML = '';
    projects.sort((a, b) => new Date(b.saved_at) - new Date(a.saved_at));
    projects.forEach(project => {
        const row = document.createElement('div');
        row.className = 'project-row';
        row.innerHTML = `
            <div class="project-row-info">
                <strong>${escapeHtml(project.name || 'Untitled Project')}</strong>
                <span>${new Date(project.saved_at).toLocaleString()}</span>
            </div>
            <div class="project-row-actions">
                <button class="btn btn-sm btn-secondary" data-project-action="load" data-project-id="${escapeHtml(String(project.id))}">Load</button>
                <button class="btn btn-sm btn-ghost" data-project-action="delete" data-project-id="${escapeHtml(String(project.id))}">Delete</button>
            </div>
        `;
        list.appendChild(row);
    });
}

async function loadProjectList() {
    const list = document.getElementById('project-list');
    if (list) list.innerHTML = '<p class="help-text">Loading saved projects...</p>';
    try {
        await refreshProjectLibrary();
        renderProjectList();
    } catch (error) {
        if (list) list.innerHTML = `<p class="help-text">${escapeHtml(error.message || 'Unable to load saved projects.')}</p>`;
    }
}

function openProjectModal() {
    const overlay = document.getElementById('project-modal-overlay');
    const modal = document.getElementById('project-modal');
    if (!overlay || !modal) return;
    overlay.classList.remove('hidden');
    modal.classList.remove('hidden');
    loadProjectList();
}

function closeProjectModal() {
    const overlay = document.getElementById('project-modal-overlay');
    const modal = document.getElementById('project-modal');
    if (overlay) overlay.classList.add('hidden');
    if (modal) modal.classList.add('hidden');
}

async function applyProjectState(project) {
    if (!project) return;
    pendingProjectLoad = project;
    activeProjectId = project.id || null;
    const input = document.getElementById('input-text');
    if (input) {
        input.value = project.text || '';
        input.dispatchEvent(new Event('input', { bubbles: true }));
    }
    const engineSelect = document.getElementById('job-tts-engine');
    if (engineSelect && project.engine) {
        engineSelect.value = project.engine;
        updateEngineUI(project.engine);
        if (isAzureSpeechEngine(project.engine)) {
            await loadAzureSpeechVoices();
        }
        if (isEdgeTtsEngine(project.engine)) {
            await loadEdgeTtsVoices();
        }
        if (isElevenLabsEngine(project.engine)) {
            await loadElevenLabsCatalog();
        }
        if (isOpenAITtsEngine(project.engine)) {
            await loadOpenAITtsCatalog();
        }
        if (isLocalAITtsEngine(project.engine)) {
            await loadLocalAITtsCatalog();
        }
    }
    const defaultVoice = document.getElementById('default-voice-select');
    if (defaultVoice && project.default_voice) defaultVoice.value = project.default_voice;
    const referenceSelect = document.getElementById('chatterbox-reference-select');
    if (referenceSelect) referenceSelect.value = project.reference_prompt || '';
    const qwenDefaultSpeaker = document.getElementById('qwen3-default-speaker');
    if (qwenDefaultSpeaker) qwenDefaultSpeaker.value = project.qwen_default_speaker || '';
    const qwenDefaultLang = document.getElementById('qwen3-default-language');
    if (qwenDefaultLang) qwenDefaultLang.value = project.qwen_default_language || 'Auto';
    const qwenDefaultInstruct = document.getElementById('qwen3-default-instruct');
    if (qwenDefaultInstruct) qwenDefaultInstruct.value = project.qwen_default_instruct || '';
    const splitChapters = document.getElementById('split-chapters-checkbox');
    if (splitChapters) splitChapters.checked = project.split_chapters != null ? !!project.split_chapters : splitChapters.defaultChecked;
    const fullStory = document.getElementById('full-story-checkbox');
    if (fullStory) fullStory.checked = project.full_story != null ? !!project.full_story : fullStory.defaultChecked;
    const heading = document.getElementById('custom-heading-input');
    if (heading) heading.value = project.custom_heading || '';
    // Load heading configuration if available
    if (project.enabled_headings) {
        enabledSectionHeadings = project.enabled_headings.filter(h => DEFAULT_SECTION_HEADINGS.includes(h));
        customSectionHeadings = project.custom_headings || [];
        renderDefaultHeadingChips();
        renderCustomHeadingChips();
    }
    const projectNameInput = document.getElementById('project-name-input');
    if (projectNameInput && project.name) {
        projectNameInput.value = project.name;
    }
    const formatSelect = document.getElementById('job-output-format');
    if (formatSelect) formatSelect.value = project.output_format || 'mp3';
    const bitrateSelect = document.getElementById('job-output-bitrate');
    if (bitrateSelect) bitrateSelect.value = project.output_bitrate || '128';
    const acxCheckbox = document.getElementById('acx-compliance-checkbox');
    if (acxCheckbox) acxCheckbox.checked = !!project.acx_compliance;
    const geminiPrompt = document.getElementById('gemini-prompt');
    if (geminiPrompt) geminiPrompt.value = project.gemini_prompt || '';
    const geminiPreset = document.getElementById('gemini-preset-select');
    if (geminiPreset) geminiPreset.value = project.gemini_preset || '';
    const batchCandidateCount = document.getElementById('speaker-batch-candidate-count');
    if (batchCandidateCount) {
        batchCandidateCount.value = String(Math.max(1, Math.min(Number.parseInt(project.bulk_voice_candidate_count, 10) || 1, 10)));
    }
    const batchPrefix = document.getElementById('speaker-batch-prefix');
    if (batchPrefix) batchPrefix.value = project.bulk_voice_prefix || '';
    const batchDesignEngine = document.getElementById('speaker-batch-design-engine');
    if (batchDesignEngine) batchDesignEngine.value = normalizeVoiceDesignEngine(project.bulk_voice_design_engine);
    latestGeminiBookTitle = project.book_title || '';
    setAltWordRegistry(project.word_replacements || project.alt_word_registry || []);

    Object.keys(voiceFxState).forEach(key => delete voiceFxState[key]);
    Object.assign(voiceFxState, project.fx_state || {});
    Object.keys(azureVoiceOptionState).forEach(key => delete azureVoiceOptionState[key]);
    Object.assign(azureVoiceOptionState, project.azure_voice_options || {});
    Object.keys(speakerReadyState).forEach(key => delete speakerReadyState[key]);
    Object.assign(speakerReadyState, project.ready_state || {});
    setSpeakerProfiles(project.speaker_profiles || {});
    restoreVoiceDesignCandidateGroups(project.voice_design_candidate_groups || {});
    bulkVoiceGenerationState = project.bulk_voice_generation_state
        ? JSON.parse(JSON.stringify(project.bulk_voice_generation_state))
        : null;

    await analyzeText({ auto: true });
    pendingProjectLoad = project;
    applyProjectAssignments(project);
    pendingProjectLoad = null;
    showNotification('Project loaded.', 'success');
}

function applyProjectAssignments(project) {
    if (!project) return;
    const assignments = project.assignments || {};
    const turboSelections = project.turbo_selections || {};
    const qwenLangs = project.qwen_inline_languages || {};
    const qwenInstructs = project.qwen_inline_instructs || {};
    Object.keys(turboSelectionState).forEach(key => delete turboSelectionState[key]);
    Object.entries(turboSelections).forEach(([speakerKey, selection]) => {
        const reference = selection?.reference || '';
        if (reference) {
            rememberCompatibleVoiceSample(speakerKey, reference);
        }
    });
    Object.entries(assignments).forEach(([speakerKey, assignment]) => {
        if (assignment?.audio_prompt_path) rememberCompatibleVoiceSample(speakerKey, assignment.audio_prompt_path);
        const localAIReference = assignment?.voice || '';
        if (localAIReference.startsWith(TTS_STORY_VOICE_REFERENCE_PREFIX)) {
            rememberCompatibleVoiceSample(speakerKey, localAIReference);
        }
    });
    Object.values(speakerProfiles).forEach(profile => {
        const speaker = profile?.name;
        const selectedPath = profile?.selected_voice_path;
        if (speaker && selectedPath && !turboSelectionState[speaker]) {
            turboSelectionState[speaker] = selectedPath;
        }
    });

    displayStatistics(currentStats || { speakers: [], speaker_count: 0, total_chunks: 0, word_count: 0, estimated_duration: 0, has_speaker_tags: false });

    getAssignmentRows().forEach(row => {
        const speaker = row.dataset.speaker;
        if (!speaker) return;
        const voiceSelect = row.querySelector('.voice-select');
        const refSelect = row.querySelector('.reference-select');
        const qwenLang = row.querySelector('.qwen3-language-select');
        const qwenInstruct = row.querySelector('.qwen3-instruct-input');
        const localAIVoice = row.querySelector('.localai-voice-input');
        const localAILanguage = row.querySelector('.localai-language-input');
        if (voiceSelect && assignments[speaker]?.voice) {
            if (project.engine === 'breeze_api') window.ensureBreezeVoiceOption?.(voiceSelect, assignments[speaker].voice);
            voiceSelect.value = assignments[speaker].voice;
        }
        if (localAIVoice) {
            localAIVoice.value = assignments[speaker]?.voice || '';
        }
        if (localAILanguage) {
            localAILanguage.value = assignments[speaker]?.lang_code || '';
        }
        if (isAzureSpeechEngine(project.engine) && assignments[speaker]?.extra) {
            azureVoiceOptionState[speaker] = { ...assignments[speaker].extra };
            updateAzureVoiceControls(row, azureVoiceOptionState[speaker]);
        }
        if (refSelect) {
            const selection = turboSelectionState[speaker] || turboSelections[speaker]?.reference || '';
            if (selection) {
                refSelect.value = selection;
            }
        }
        if (qwenLang && qwenLangs[speaker]) {
            qwenLang.value = qwenLangs[speaker];
        }
        if (qwenInstruct && typeof qwenInstructs[speaker] === 'string') {
            qwenInstruct.value = qwenInstructs[speaker];
        }
        updateInlineSampleButtonState(row, { stopPlayback: true });
    });
}

// Display statistics
function displayStatistics(stats) {
    const detectedSpeakers = Array.isArray(stats.speakers) ? stats.speakers : [];
    const hasDetectedSpeakers = stats.has_speaker_tags && detectedSpeakers.length > 0;
    const activeSpeakers = hasDetectedSpeakers ? detectedSpeakers : ['Speaker 1'];
    const speakerCount = hasDetectedSpeakers
        ? (stats.speaker_count || detectedSpeakers.length)
        : 1;
    document.getElementById('stat-speakers').textContent = speakerCount;
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
    if (chapterInfo && stats.section_detection) {
        const {
            detected,
            count,
            titles,
            kind,
            book_count: bookCount = 0,
            section_count: sectionCount = 0
        } = stats.section_detection;
        if (detected) {
            chapterInfo.style.display = 'block';
            const titleList = titles && titles.length ? ` (<em>${titles.slice(0, 5).join(', ')}${titles.length > 5 ? ', …' : ''}</em>)` : '';
            if (kind === 'book') {
                const booksLabel = bookCount || count;
                chapterInfo.innerHTML = `📚 Books detected: <strong>${booksLabel}</strong> · Sections detected: <strong>${sectionCount}</strong>${titleList}`;
            } else {
                chapterInfo.innerHTML = `📚 Sections detected: <strong>${count}</strong>${titleList}`;
            }
            if (chapterCheckbox && !chapterCheckbox.dataset.userToggled) {
                chapterCheckbox.disabled = false;
                chapterCheckbox.classList.remove('disabled');
            }
            updateSectionReviewButton(true);
        } else {
            chapterInfo.style.display = 'block';
            chapterInfo.innerHTML = '📚 No section headings detected.';
            updateSectionReviewButton(false);
        }
    }
    refreshChapterHint();

    const batchBtn = document.getElementById('generate-voices-btn');
    if (batchBtn) {
        batchBtn.disabled = !hasDetectedSpeakers || !(
            window.qwenVoiceDesignAvailable === true || window.breezeVoiceDesignAvailable === true
        );
    }
    const buildProfilesBtn = document.getElementById('build-speaker-profiles-btn');
    if (buildProfilesBtn) {
        buildProfilesBtn.disabled = !hasDetectedSpeakers;
    }
    const autoAssignVoicesBtn = document.getElementById('auto-assign-voices-btn');
    if (autoAssignVoicesBtn) {
        autoAssignVoicesBtn.disabled = !hasDetectedSpeakers;
    }

    if (hasDetectedSpeakers) {
        speakersList.innerHTML = '<p><strong>Detected Speakers:</strong></p>';
        const tagsWrap = document.createElement('div');
        tagsWrap.className = 'speaker-tags-wrap';
        detectedSpeakers.forEach(speaker => {
            const tag = document.createElement('button');
            tag.type = 'button';
            tag.className = `speaker-tag${speakerReadyState[speaker] ? ' ready' : ''}`;
            tag.dataset.speaker = speaker;
            tag.textContent = speaker;
            tagsWrap.appendChild(tag);
        });
        speakersList.appendChild(tagsWrap);
        const hint = document.createElement('p');
        hint.className = 'speaker-modal-hint';
        hint.textContent = 'Click any speaker chip to open assignments.';
        speakersList.appendChild(hint);
        renderSpeakerDuplicates(detectedSpeakers);
        
        // Show emotion tag detection info
        if (stats.has_emotion_tags) {
            const emotionInfo = document.createElement('p');
            emotionInfo.className = 'emotion-detection-info';
            emotionInfo.innerHTML = `🎭 <strong>Emotion tags detected:</strong> ${stats.segments_with_emotion} segment(s) with emotions (will be used as Qwen3 instructions)`;
            speakersList.appendChild(emotionInfo);
        }
        
        // Show inline voice assignments with emotion data
        displayInlineVoiceAssignments(detectedSpeakers, stats.speaker_emotions || {});
    } else {
        speakersList.innerHTML = '<p><strong>Detected Speakers:</strong></p>';
        const tagsWrap = document.createElement('div');
        tagsWrap.className = 'speaker-tags-wrap';
        const tag = document.createElement('button');
        tag.type = 'button';
        tag.className = `speaker-tag${speakerReadyState['Speaker 1'] ? ' ready' : ''}`;
        tag.dataset.speaker = 'Speaker 1';
        tag.textContent = 'Speaker 1';
        tagsWrap.appendChild(tag);
        speakersList.appendChild(tagsWrap);
        const hint = document.createElement('p');
        hint.className = 'speaker-modal-hint';
        hint.textContent = 'Click the speaker chip to open assignments.';
        speakersList.appendChild(hint);
        displayInlineVoiceAssignments(activeSpeakers, {});
        renderSpeakerDuplicates([]);
    }
    
    document.getElementById('stats-section').style.display = 'block';
}

// Display inline voice assignments in Generate tab
function displayInlineVoiceAssignments(speakers, speakerEmotions = {}) {
    const container = document.getElementById('inline-voice-assignment-list');
    const voiceSelectSnapshot = {};
    container.querySelectorAll('.voice-assignment-row').forEach(row => {
        const spk = row.dataset.speaker;
        if (!spk) return;
        const vs = row.querySelector('.voice-select');
        if (vs && vs.value) voiceSelectSnapshot[spk] = vs.value;
        const localVoice = row.querySelector('.localai-voice-input');
        const localLanguage = row.querySelector('.localai-language-input');
        if (localVoice?.value || localLanguage?.value) {
            voiceSelectSnapshot[`${spk}:localai`] = {
                voice: localVoice?.value || '',
                language: localLanguage?.value || '',
            };
        }
        const rs = row.querySelector('.reference-select');
        if (vs?.value?.startsWith(TTS_STORY_VOICE_REFERENCE_PREFIX)) {
            rememberCompatibleVoiceSample(spk, vs.value);
        } else if (rs && rs.value) {
            rememberCompatibleVoiceSample(spk, rs.value);
        }
        rememberAzureVoiceOptions(row);
    });
    container.innerHTML = '';
    
    speakers.forEach(speaker => {
        const emotion = speakerEmotions[speaker] || '';
        const row = document.createElement('div');
        row.className = 'voice-assignment-row';
        row.dataset.speaker = speaker;
        row.innerHTML = `
            <div class="assignment-header">
                <span class="speaker-label">${speaker}</span>
                <div class="speaker-rename">
                    <input type="text" class="speaker-rename-input" data-role="speaker-rename-input" />
                    <button type="button" class="btn btn-sm speaker-rename-btn" data-role="speaker-rename-btn">Apply</button>
                </div>
            </div>
            <div class="assignment-body compact-assignment">
                <div class="assignment-selection-group">
                    <div class="assignment-select voice-select-inline" data-role="kokoro-control">
                        <label>${speaker}</label>
                        <select class="voice-select" data-speaker="${speaker}">
                            <option value="">Select Voice...</option>
                        </select>
                    </div>
                    <div class="assignment-select turbo-inline-control" data-role="turbo-control">
                        <label>Voice Sample</label>
                        <input type="search" class="voice-sample-filter" data-speaker="${speaker}" placeholder="Filter voice samples..." autocomplete="off" />
                        <div class="voice-sample-row">
                            <select class="reference-select" data-speaker="${speaker}">
                                <option value="">Inherit from global selection</option>
                            </select>
                            <button type="button" class="btn btn-sm voice-sample-preview-btn" data-role="voice-sample-preview-btn" data-label-play="Play" data-label-stop="Stop" disabled>
                                Play
                            </button>
                        </div>
                    </div>
                </div>
                <div class="qwen3-inline-options" data-role="qwen3-control" style="display: none;">
                    <div class="qwen3-options-row">
                        <div class="assignment-select qwen3-lang-select">
                            <label>Language</label>
                            <select class="qwen3-language-select" data-speaker="${speaker}">
                                <option value="Auto">Auto</option>
                            </select>
                        </div>
                        <div class="assignment-select qwen3-instruct-field">
                            <label>Custom Instruction${emotion ? ' (from emotion tag)' : ' (optional)'}</label>
                            <input type="text" class="qwen3-instruct-input" data-speaker="${speaker}" 
                                   value="${emotion.replace(/"/g, '&quot;')}"
                                   placeholder="e.g., Speak with excitement" />
                        </div>
                    </div>
                    <div class="assignment-select localai-inline-control" data-role="localai-control" style="display: none;">
                        <label>LocalAI Voice / Speaker ID</label>
                        <input type="text" class="localai-voice-input" data-speaker="${speaker}" list="localai-tts-voice-options" placeholder="Model default, discovered profile, or custom ID" />
                        <label>Language (optional)</label>
                        <input type="text" class="localai-language-input" data-speaker="${speaker}" placeholder="e.g. en, en-US, French" />
                        <small class="help-text">Values are passed directly to the selected LocalAI model.</small>
                    </div>
                </div>
                <div class="azure-speech-inline-options" data-role="azure-speech-control" style="display: none;">
                    <div class="qwen3-options-row">
                        <div class="assignment-select">
                            <label>Speaking Style</label>
                            <select class="azure-style-select" data-speaker="${speaker}"><option value="">Neutral</option></select>
                        </div>
                        <div class="assignment-select">
                            <label>Role</label>
                            <select class="azure-role-select" data-speaker="${speaker}"><option value="">Default role</option></select>
                        </div>
                        <div class="assignment-select">
                            <label>Style Intensity</label>
                            <input type="number" class="azure-style-degree" min="0.01" max="2" step="0.01" value="1" />
                        </div>
                        <div class="assignment-select">
                            <label>Volume Change (%)</label>
                            <input type="number" class="azure-volume" min="-100" max="100" step="1" value="0" />
                        </div>
                    </div>
                    <small class="help-text" data-role="azure-voice-info">Select an Azure voice to see its supported styles and roles.</small>
                </div>
                <div class="voice-fx-inline voice-inline-card" data-speaker="${speaker}" data-role="kokoro-panel"></div>
            </div>
        `;
        container.appendChild(row);
        const renameInput = row.querySelector('[data-role="speaker-rename-input"]');
        if (renameInput) {
            renameInput.value = speaker;
            renameInput.addEventListener('keydown', (event) => {
                if (event.key === 'Enter') {
                    event.preventDefault();
                    const applyButton = row.querySelector('[data-role="speaker-rename-btn"]');
                    applyButton?.click();
                }
            });
        }
        const renameButton = row.querySelector('[data-role="speaker-rename-btn"]');
        if (renameButton && renameInput) {
            renameButton.addEventListener('click', () => handleInlineRename(speaker, renameInput));
        }
        const fxContainer = row.querySelector('.voice-fx-inline');
        if (fxContainer) {
            renderFxPanel(fxContainer, speaker, {
                title: `${speaker} FX`,
                showHeader: false,
                useSharedPreview: true
            });
        }
        row.querySelector('.voice-select')?.addEventListener('change', event => {
            const selectedVoice = event.currentTarget?.value?.trim() || '';
            if (selectedVoice.startsWith(TTS_STORY_VOICE_REFERENCE_PREFIX)) {
                rememberCompatibleVoiceSample(speaker, selectedVoice);
            }
            if (isAzureSpeechEngine(getSelectedJobEngine() || runtimeSettings?.tts_engine)) {
                updateAzureVoiceControls(row, {});
            }
        });
        row.querySelectorAll('.azure-style-select, .azure-role-select, .azure-style-degree, .azure-volume').forEach(control => {
            control.addEventListener('change', () => rememberAzureVoiceOptions(row));
        });
    });
    
    initInlineSampleHandlers();
    const restoreVoiceSelects = () => {
        container.querySelectorAll('.voice-assignment-row').forEach(row => {
            const spk = row.dataset.speaker;
            if (!spk) return;
            const vs = row.querySelector('.voice-select');
            if (vs && voiceSelectSnapshot[spk]) {
                restoreSelectValue(vs, voiceSelectSnapshot[spk]);
            }
            const localSnapshot = voiceSelectSnapshot[`${spk}:localai`];
            if (localSnapshot) {
                const voiceInput = row.querySelector('.localai-voice-input');
                const languageInput = row.querySelector('.localai-language-input');
                if (voiceInput) voiceInput.value = localSnapshot.voice || '';
                if (languageInput) languageInput.value = localSnapshot.language || '';
            }
            if (isAzureSpeechEngine(getSelectedJobEngine() || runtimeSettings?.tts_engine)) {
                updateAzureVoiceControls(row, azureVoiceOptionState[spk] || {});
            }
        });
    };
    if (window.availableVoices) {
        populateVoiceSelects();
        restoreVoiceSelects();
    } else {
        const checkVoices = setInterval(() => {
            if (window.availableVoices) {
                clearInterval(checkVoices);
                populateVoiceSelects();
                restoreVoiceSelects();
            }
        }, 100);
    }
    
    const inlineAssignments = document.getElementById('inline-voice-assignments');
    if (inlineAssignments) {
        inlineAssignments.style.display = 'none';
    }
    populateReferenceSelects();
    updateAssignmentModes(getSelectedJobEngine() || runtimeSettings?.tts_engine || 'kokoro');
}

function updateInlineSampleButtonState(row, options = {}) {
    if (!row) return;
    const button = row.querySelector('[data-role="voice-sample-preview-btn"]');
    if (!button) return;
    const selection = row.querySelector('.reference-select')?.value?.trim() || '';
    if (!selection) {
        button.disabled = true;
        button.classList.remove('is-playing', 'is-loading');
        button.textContent = button.dataset.labelPlay || 'Play';
        if (options.stopPlayback && window.chatterboxPreviewController) {
            window.chatterboxPreviewController.stop();
        }
        return;
    }
    button.disabled = false;
    if (options.stopPlayback && window.chatterboxPreviewController) {
        window.chatterboxPreviewController.stop();
    }
}

function initInlineSampleHandlers() {
    const containers = [
        document.getElementById('inline-voice-assignment-list'),
        document.getElementById('speaker-edit-modal-body')
    ].filter(Boolean);
    if (!containers.length) return;
    containers.forEach(container => {
        if (container.dataset.handlersReady === 'true') return;
        container.addEventListener('change', event => {
            if (!(event.target instanceof HTMLElement)) return;
            if (!event.target.classList.contains('reference-select')) return;
            const row = event.target.closest('.voice-assignment-row');
            const speaker = row?.dataset?.speaker;
            if (speaker) {
                const selection = event.target.value?.trim() || '';
                if (selection) {
                    rememberCompatibleVoiceSample(speaker, selection);
                } else {
                    delete turboSelectionState[speaker];
                }
            }
            updateInlineSampleButtonState(row, { stopPlayback: true });
        });
        container.addEventListener('click', event => {
            const target = event.target instanceof HTMLElement ? event.target : null;
            const button = target?.closest('[data-role="voice-sample-preview-btn"]');
            if (!button) return;
            const row = button.closest('.voice-assignment-row');
            const selection = row?.querySelector('.reference-select')?.value?.trim();
            if (!selection) {
                showNotification('Select a voice sample first.', 'warning');
                return;
            }
            const voiceEntry = findChatterboxVoiceByPath(selection);
            if (!voiceEntry?.id) {
                showNotification('Unable to resolve that voice sample.', 'warning');
                return;
            }
            if (!window.chatterboxPreviewController) {
                showNotification('Preview controls are still loading. Try again shortly.', 'warning');
                return;
            }
            window.chatterboxPreviewController.toggleById(voiceEntry.id, button);
        });
        container.addEventListener('input', event => {
            if (!(event.target instanceof HTMLElement)) return;
            if (!event.target.classList.contains('voice-sample-filter')) return;
            const row = event.target.closest('.voice-assignment-row');
            const select = row?.querySelector('.reference-select');
            if (!select) return;
            select.dataset.filterQuery = event.target.value || '';
            populateReferenceDropdown(select, 'Inherit from global selection');
            const speaker = row?.dataset?.speaker;
            const selected = speaker ? turboSelectionState[speaker] : '';
            if (selected) select.value = selected;
            updateInlineSampleButtonState(row);
        });
        container.dataset.handlersReady = 'true';
    });
    inlineSampleHandlersReady = true;
}

// Populate voice select dropdowns
function setCatalogVoicePlaceholder(label = 'Loading voices...') {
    document.querySelectorAll('#inline-voice-assignment-list .voice-select, #speaker-edit-modal-body .voice-select')
        .forEach(select => {
            select.innerHTML = '';
            const option = document.createElement('option');
            option.value = '';
            option.textContent = label;
            select.appendChild(option);
        });
}

function populateVoiceSelects() {
    const engineName = getSelectedJobEngine() || runtimeSettings?.tts_engine || 'kokoro';
    const usesReferenceSamples = isPromptEngine(engineName);
    const isAzureSpeech = isAzureSpeechEngine(engineName);
    const isEdgeTts = isEdgeTtsEngine(engineName);
    const isElevenLabs = isElevenLabsEngine(engineName);
    const isOpenAITts = isOpenAITtsEngine(engineName);
    const isLocalAITts = isLocalAITtsEngine(engineName);
    if (isAzureSpeech && !azureSpeechVoices.length) {
        setCatalogVoicePlaceholder('Loading Azure voices...');
        if (!azureSpeechVoicesPromise) loadAzureSpeechVoices();
        return;
    }
    if (isEdgeTts && !edgeTtsVoices.length) {
        setCatalogVoicePlaceholder('Loading Edge voices...');
        if (!edgeTtsVoicesPromise) loadEdgeTtsVoices();
        return;
    }
    if (isElevenLabs && !elevenLabsVoices.length) {
        setCatalogVoicePlaceholder('Loading ElevenLabs voices...');
        if (!elevenLabsCatalogPromise) loadElevenLabsCatalog();
        return;
    }
    if (isOpenAITts && !openAITtsVoices.length) {
        setCatalogVoicePlaceholder('Loading OpenAI TTS voices...');
        if (!openAITtsCatalogPromise) loadOpenAITtsCatalog();
        return;
    }
    if (isLocalAITts && !localAITtsVoices.length) {
        if (!localAITtsCatalogPromise) loadLocalAITtsCatalog();
    }
    if (!window.availableVoices && !window.availablePocketTtsVoices && !isKittenEngine(engineName) && !isIndexTTSEngine(engineName) && !isDotsTTSEngine(engineName) && !isCatalogCloudEngine(engineName)) return;
    const isQwen = isQwenEngine(engineName);
    const isPocketPreset = isPocketPresetEngine(engineName);
    const isKitten = isKittenEngine(engineName);
    const selects = document.querySelectorAll('#inline-voice-assignment-list .voice-select, #speaker-edit-modal-body .voice-select');
    selects.forEach(select => {
        const previousValue = select.value;
        if (usesReferenceSamples && engineName !== 'breeze_api') {
            // Reference-capable engines (including Breeze and OmniVoice Clone)
            // use the transcript-aware saved sample selector. Never leave a
            // hidden Kokoro catalog populated where it can be exposed by a
            // later render or stale CSS state.
            select.innerHTML = '<option value="">Voice samples are listed below</option>';
            select.disabled = true;
            return;
        }
        select.disabled = false;
        select.innerHTML = '<option value="">Select Voice...</option>';
        if (engineName === 'breeze_api') {
            appendProviderVoiceOptions(select, window.breezeApiVoices || [], 'Breeze saved voices');
            window.ensureBreezeVoiceOption?.(select, previousValue || runtimeSettings?.breeze_api_default_voice);
        } else if (isQwen) {
            appendQwen3VoiceOptions(select);
        } else if (isPocketPreset) {
            appendPocketPresetVoiceOptions(select);
        } else if (isKitten) {
            appendKittenVoiceOptions(select);
        } else if (isAzureSpeech) {
            appendAzureSpeechVoiceOptions(select);
        } else if (isEdgeTts) {
            appendProviderVoiceOptions(select, edgeTtsVoices, 'Edge voices');
        } else if (isElevenLabs) {
            appendProviderVoiceOptions(select, elevenLabsVoices, 'ElevenLabs voices');
        } else if (isOpenAITts) {
            appendProviderVoiceOptions(select, openAITtsVoices, 'OpenAI TTS voices');
        } else if (isLocalAITts) {
            appendProviderVoiceOptions(select, localAITtsVoices, 'LocalAI voice profiles');
        } else {
            appendVoiceOptions(select);
        }
        restoreSelectValue(select, previousValue);
        if (isLocalAITts) {
            if (select.value.startsWith(TTS_STORY_VOICE_REFERENCE_PREFIX)) {
                rememberCompatibleVoiceSample(select.dataset.speaker, select.value);
            } else if (!select.value) {
                restoreCompatibleLocalAIVoiceSample(select);
            }
        }
        if (isAzureSpeech) updateAzureVoiceControls(select.closest('.voice-assignment-row'));
    });
    if (isLocalAITts) {
        const sharedDatalist = document.getElementById('localai-tts-voice-options');
        if (sharedDatalist) {
            sharedDatalist.innerHTML = '';
            localAITtsVoices.forEach(voice => {
                const id = voice.voice_id || voice.short_name;
                if (!id || voice.disabled) return;
                const option = document.createElement('option');
                option.value = id;
                option.label = `${voice.display_name || id}${voice.locale ? ` · ${voice.locale}` : ''}`;
                sharedDatalist.appendChild(option);
            });
        }
        getAssignmentRows().forEach(row => {
            const input = row.querySelector('.localai-voice-input');
            if (!input) return;
            const currentValue = input.value;
            input.value = currentValue || runtimeSettings?.localai_tts_default_voice || '';
            const languageInput = row.querySelector('.localai-language-input');
            if (languageInput && !languageInput.value) {
                languageInput.value = runtimeSettings?.localai_tts_default_language || '';
            }
        });
    }
}

// Generate audio
function closeEngineFirstRunNotice() {
    document.getElementById('engine-first-run-overlay')?.classList.add('hidden');
    document.getElementById('engine-first-run-modal')?.classList.add('hidden');
}

function showEngineFirstRunNotice(engineName) {
    const overlay = document.getElementById('engine-first-run-overlay');
    const modal = document.getElementById('engine-first-run-modal');
    if (!overlay || !modal) return;
    const engineSelect = document.getElementById('job-tts-engine');
    const selectedOption = Array.from(engineSelect?.options || []).find(option =>
        option.value === engineName
    );
    const displayName = selectedOption?.textContent?.trim() || engineName || 'This TTS engine';
    const message = document.getElementById('engine-first-run-message');
    if (message) {
        message.textContent = `${displayName} may need to download additional model files and prepare its runtime before generating its first audio.`;
    }
    overlay.classList.remove('hidden');
    modal.classList.remove('hidden');
    document.getElementById('engine-first-run-ok')?.focus();
}

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
    
    // Check for unbalanced speaker tags before submitting
    {
        _updateTagErrorBanner();
        if (_tagIssues.length > 0) {
            _tagIssueIndex = 0;
            _scrollToTagIssue(0);
            const banner = document.getElementById('tag-error-banner');
            if (banner) banner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            showNotification(`Fix ${_tagIssues.length} unmatched speaker tag${_tagIssues.length === 1 ? '' : 's'} before submitting`, 'warning');
            return;
        }
    }

    // Get voice assignments
    let voiceAssignments = getVoiceAssignments();
    
    const hasDetectedSpeakers = Array.isArray(currentStats?.speakers) && currentStats.speakers.length > 0;
    // Require per-speaker assignments since default voice selectors are no longer shown
    if (Object.keys(voiceAssignments).length === 0) {
        const warningMessage = hasDetectedSpeakers
            ? 'Assign voices for the detected speakers before generating audio.'
            : 'Assign a voice for Speaker 1 before generating audio.';
        showNotification(warningMessage, 'warning');
        return;
    }
    
    console.log('Voice assignments for generation:', voiceAssignments);

    const splitByChapter = document.getElementById('split-chapters-checkbox')?.checked || false;
    const enabledHeadings = getEnabledSectionHeadings();
    const generateFullStory = splitByChapter && (document.getElementById('full-story-checkbox')?.checked || false);
    const outputFormat = document.getElementById('job-output-format')?.value || undefined;
    const outputBitrate = document.getElementById('job-output-bitrate')?.value || undefined;
    const acxCompliance = document.getElementById('acx-compliance-checkbox')?.checked || false;

    const selectedEngine = getSelectedJobEngine() || runtimeSettings?.tts_engine;
    const wordReplacements = getAltWordRegistry().filter(e => e.original && e.replacement);
    const payload = {
        text,
        split_by_chapter: splitByChapter,
        generate_full_story: generateFullStory,
        voice_assignments: voiceAssignments,
        review_mode: true  // Always enabled - chunk review happens in library
    };
    if (selectedEngine === 'breeze_api' && Object.values(voiceAssignments).some(a => a.audio_prompt_path)) {
        const count = new Set(Object.values(voiceAssignments).map(a => a.audio_prompt_path).filter(Boolean)).size;
        if (!confirm(`This production will upload and save ${count} selected local voice sample(s) to Breeze as needed. Uploads may use credits and private voice slots. Confirm you have the required rights/consent and approve these selected samples. They remain online until you explicitly release this production's voices.`)) return;
        payload.breeze_upload_consent = true;
        payload.production_title = document.getElementById('project-name-input')?.value?.trim() || text.slice(0, 100);
    }
    if (wordReplacements.length > 0) {
        payload.word_replacements = wordReplacements;
    }
    payload.section_headings = enabledHeadings;
    if (selectedEngine) {
        payload.tts_engine = selectedEngine;
        const overrides = collectEngineOverrides(selectedEngine);
        if (overrides) {
            payload.engine_options = overrides;
        }
    }
    if (outputFormat) {
        payload.output_format = outputFormat;
    }
    if (outputFormat === 'mp3' && outputBitrate) {
        payload.output_bitrate_kbps = parseInt(outputBitrate, 10);
    }
    payload.acx_compliance = acxCompliance;
    try {
        const response = await fetch('/api/generate', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify(payload)
        });
        
        const data = await response.json();
        
        if (data.success) {
            // Show success notification
            showNotification(`Job queued! Position: ${data.queue_position}`, 'success');

            if (data.first_run_notice) {
                showEngineFirstRunNotice(data.engine || selectedEngine);
            }
            
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

// ── Speaker tag balance checker & inline banner ───────────────────────────────

const _TAG_RESERVED = new Set();
// Keep synchronized with src/tag_validation.py. Unknown opening IDs must not
// disappear merely because their closing tags are missing.
const _TAG_EXPRESSIONS = new Set(['laugh', 'laughter', 'chuckle', 'sigh', 'sush', 'shush', 'cough', 'groan',
    'sniff', 'gasp', 'grunt', 'breath', 'pause', 'cry', 'crying', 'sobbing', 'snort', 'scream',
    'whisper', 'whispering', 'sighing', 'laughing', 'confirmation-en', 'question-en', 'question-ah',
    'question-oh', 'question-ei', 'question-yi', 'surprise-ah', 'surprise-oh', 'surprise-wa',
    'surprise-yo', 'dissatisfaction-hnn']);

/**
 * Returns an array of error objects, each with:
 *   { message, pos, kind ('orphan-open'|'orphan-close'|'mismatch'), tag }
 * `pos` is the character index in `text` of the offending tag.
 */
function getSpeakerTagIssues(text) {
    const openRe = /\[([a-zA-Z][a-zA-Z0-9_\-]*)\]/g;
    const closeRe = /\[\/([a-zA-Z][a-zA-Z0-9_\-]*)\]/g;

    // Only known standalone expression cues can be excluded without a closer.
    const closedTags = new Set();
    let m;
    while ((m = closeRe.exec(text)) !== null) {
        closedTags.add(m[1].toLowerCase());
    }

    const events = [];
    openRe.lastIndex = 0;
    closeRe.lastIndex = 0;
    while ((m = openRe.exec(text)) !== null) {
        const tag = m[1].toLowerCase();
        if (!_TAG_EXPRESSIONS.has(tag) || closedTags.has(tag)) events.push({ pos: m.index, len: m[0].length, kind: 'open', tag });
    }
    while ((m = closeRe.exec(text)) !== null) {
        const tag = m[1].toLowerCase();
        if (!_TAG_RESERVED.has(tag)) events.push({ pos: m.index, len: m[0].length, kind: 'close', tag });
    }
    events.sort((a, b) => a.pos - b.pos);

    const issues = [];
    const stack = []; // { tag, pos, len }
    let lastCloseEvent = null;
    for (const ev of events) {
        if (ev.kind === 'open') {
            if (stack.length) issues.push({message: `Nested tag [${ev.tag}] before closing [/${stack[stack.length - 1].tag}]`,
                pos: ev.pos, kind: 'nested', tag: ev.tag, focusStart: ev.pos, focusEnd: ev.pos + ev.len,
                blockStart: stack[stack.length - 1].pos, blockEnd: ev.pos + ev.len});
            stack.push(ev);
        } else {
            if (stack.length === 0) {
                const blockStart = lastCloseEvent ? lastCloseEvent.pos + lastCloseEvent.len : 0;
                issues.push({
                    message: `Closing tag [/${ev.tag}] has no matching opening tag`,
                    pos: ev.pos,
                    kind: 'orphan-close',
                    tag: ev.tag,
                    focusStart: ev.pos,
                    focusEnd: ev.pos + ev.len,
                    blockStart,
                    blockEnd: ev.pos + ev.len,
                });
            } else if (stack[stack.length - 1].tag !== ev.tag) {
                const top = stack.pop();
                issues.push({
                    message: `Mismatched tags: expected [/${top.tag}] but found [/${ev.tag}]`,
                    pos: ev.pos,
                    kind: 'mismatch',
                    tag: ev.tag,
                    openerTag: top.tag,
                    openerPos: top.pos,
                    focusStart: ev.pos,
                    focusEnd: ev.pos + ev.len,
                    blockStart: top.pos,
                    blockEnd: ev.pos + ev.len,
                });
            } else {
                stack.pop();
            }
            lastCloseEvent = ev;
        }
    }
    for (const unclosed of stack) {
        const nextOpen = events.find(e => e.kind === 'open' && e.pos > unclosed.pos);
        issues.push({
            message: `Opening tag [${unclosed.tag}] has no matching closing tag`,
            pos: unclosed.pos,
            kind: 'orphan-open',
            tag: unclosed.tag,
            focusStart: unclosed.pos,
            focusEnd: unclosed.pos + unclosed.len,
            blockStart: unclosed.pos,
            blockEnd: nextOpen ? nextOpen.pos : text.length,
        });
    }
    return issues;
}

/** Convenience: returns error message strings only (for submit guard). */
function checkSpeakerTagBalance(text) {
    return getSpeakerTagIssues(text).map(i => i.message);
}

// ── Banner state ──────────────────────────────────────────────────────────────
let _tagIssues = [];          // current list of issues
let _tagIssueIndex = -1;      // which issue the user is navigating to

function _updateTagErrorBanner() {
    const textarea = document.getElementById('input-text');
    const banner   = document.getElementById('tag-error-banner');
    const summary  = document.getElementById('tag-error-summary');
    if (!textarea || !banner || !summary) return;

    const text = textarea.value;
    // Only run the check when the text actually contains any speaker tags
    const hasTags = /\[\/?[a-zA-Z][a-zA-Z0-9_\-]*\]/.test(text);
    if (!hasTags) {
        _tagIssues = [];
        banner.classList.add('hidden');
        textarea.classList.remove('tag-error-highlight');
        return;
    }

    _tagIssues = getSpeakerTagIssues(text);
    if (_tagIssues.length === 0) {
        banner.classList.add('hidden');
        textarea.classList.remove('tag-error-highlight');
        return;
    }

    const n = _tagIssues.length;
    summary.textContent = `${n} speaker/direction tag issue${n === 1 ? '' : 's'} found`;
    banner.classList.remove('hidden');
    textarea.classList.add('tag-error-highlight');
    if (_tagIssueIndex < 0 || _tagIssueIndex >= n) _tagIssueIndex = 0;
}

function _navigateTagIssue(delta) {
    if (_tagIssues.length === 0) return;
    _tagIssueIndex = (_tagIssueIndex + delta + _tagIssues.length) % _tagIssues.length;
    _scrollToTagIssue(_tagIssueIndex);
}

/**
 * Returns the pixel scrollTop value that places charIndex at the top of the
 * textarea's visible area, by using a hidden mirror div with identical
 * typography and width.
 */
function _computeScrollTopForChar(textarea, charIndex) {
    const text = textarea.value || '';
    const cs   = window.getComputedStyle(textarea);

    // Build mirror with identical layout properties
    const mirror = document.createElement('div');
    [
        'paddingTop','paddingRight','paddingBottom','paddingLeft',
        'fontFamily','fontSize','fontWeight','fontStyle',
        'lineHeight','letterSpacing','wordSpacing','tabSize',
    ].forEach(p => { mirror.style[p] = cs[p]; });

    // Width must match the textarea's inner content width precisely
    const innerWidth = textarea.clientWidth
        - parseFloat(cs.paddingLeft)  - parseFloat(cs.paddingRight);
    mirror.style.width     = innerWidth + 'px';
    mirror.style.boxSizing = 'content-box';
    mirror.style.position  = 'absolute';
    mirror.style.top       = '0';
    mirror.style.left      = '0';
    mirror.style.visibility= 'hidden';
    mirror.style.whiteSpace= 'pre-wrap';
    mirror.style.wordWrap  = 'break-word';
    mirror.style.overflow  = 'hidden';

    // We only need the text up to the target character to measure line position
    const before = document.createTextNode(text.slice(0, charIndex));
    const marker = document.createElement('span');
    marker.textContent = '\u200B'; // zero-width space as anchor
    mirror.appendChild(before);
    mirror.appendChild(marker);

    // Append to a hidden container so layout is computed correctly
    const host = document.createElement('div');
    host.style.cssText = 'position:fixed;top:0;left:0;width:' + textarea.clientWidth + 'px;visibility:hidden;overflow:visible;pointer-events:none;';
    host.appendChild(mirror);
    document.body.appendChild(host);

    // marker.offsetTop is relative to mirror (its offset parent)
    const markerOffsetTop = marker.offsetTop;
    document.body.removeChild(host);

    // markerOffsetTop is the distance from mirror's top to the marker line.
    // Subtract paddingTop so scrollTop=0 corresponds to the first line.
    const paddingTop = parseFloat(cs.paddingTop) || 0;
    return Math.max(0, markerOffsetTop - paddingTop);
}

function _scrollToTagIssue(idx) {
    const textarea = document.getElementById('input-text');
    if (!textarea || !_tagIssues[idx]) return;
    const issue    = _tagIssues[idx];
    const text     = textarea.value || '';

    const focusStart = Number.isInteger(issue.focusStart) ? issue.focusStart : issue.pos;
    const focusEnd   = Number.isInteger(issue.focusEnd)   ? issue.focusEnd   : Math.min(text.length, focusStart + 1);
    const blockStart = Number.isInteger(issue.blockStart) ? issue.blockStart : focusStart;
    const blockEnd   = Number.isInteger(issue.blockEnd)   ? issue.blockEnd   : focusEnd;
    const blockLen   = Math.max(0, blockEnd - blockStart);

    const useBlock = blockLen > 0 && blockLen <= 3000;
    const selStart = useBlock ? blockStart : focusStart;
    const selEnd   = useBlock ? blockEnd   : focusEnd;

    textarea.focus();
    textarea.setSelectionRange(selStart, selEnd);

    // Compute where the focus tag sits in the content and place it at the top.
    // Double-rAF ensures our assignment runs after the browser's own scroll-to-selection pass.
    const targetScrollTop = _computeScrollTopForChar(textarea, focusStart);
    requestAnimationFrame(() => requestAnimationFrame(() => {
        textarea.scrollTop = targetScrollTop;
    }));

    // Update banner summary
    const startLine = text.substring(0, focusStart).split('\n').length;
    const endLine   = text.substring(0, selEnd).split('\n').length;
    const summary   = document.getElementById('tag-error-summary');
    if (summary) {
        const highlightText = useBlock
            ? `Highlighted affected block (lines ${startLine}–${endLine}).`
            : `Highlighted unmatched tag at line ${startLine}.`;
        summary.textContent = `Issue ${idx + 1} of ${_tagIssues.length}: ${issue.message} — ${highlightText}`;
    }
}

/**
 * Auto-fix: collect all issues in one pass, build a list of insertions,
 * sort them back-to-front, then apply them all in one shot.
 *
 * Rules:
 *  - orphan-open  : insert [/tag] just before the next opening tag, or at EOF
 *  - orphan-close : insert [tag] just after the previous closing tag, or at BOF
 *  - mismatch     : insert [/openerTag] at the position of the mismatched close
 *                   (openerTag is stored from getSpeakerTagIssues)
 */
function _autoFixTagBalance() {
    const textarea = document.getElementById('input-text');
    if (!textarea) return;

    const text   = textarea.value;
    const issues = getSpeakerTagIssues(text);
    if (issues.length === 0) return;
    if (issues.some(issue => issue.kind === 'nested')) {
        showNotification('Nested tags need manual review. Close each direction or speaker block before opening the next one.', 'warning');
        return;
    }

    // The directed-output failure has an unambiguous correction: replace the
    // wrong control closer, rather than adding a closer and leaving it orphaned.
    const wrongDirectionClosers = issues.filter(issue => issue.kind === 'mismatch'
        && issue.tag === 'direction' && !['direction', 'emotion'].includes(issue.openerTag));
    if (wrongDirectionClosers.length && !issues.some(issue => issue.kind === 'nested')) {
        let fixed = text;
        for (const issue of wrongDirectionClosers.sort((a, b) => b.pos - a.pos)) {
            fixed = fixed.slice(0, issue.focusStart) + `[/${issue.openerTag}]` + fixed.slice(issue.focusEnd);
        }
        textarea.value = fixed;
        lastAnalyzedText = null;
        _updateTagErrorBanner();
        textarea.dispatchEvent(new Event('input', {bubbles: true}));
        return;
    }

    // Build flat sorted list of every tag occurrence for neighbour lookup
    function allTags(t) {
        const out = [];
        let m;
        const paired = new Set([...t.matchAll(/\[\/([a-zA-Z][a-zA-Z0-9_\-]*)\]/g)].map(m => m[1].toLowerCase()));
        const r1 = /\[([a-zA-Z][a-zA-Z0-9_\-]*)\]/g;
        while ((m = r1.exec(t)) !== null) {
            const tg = m[1].toLowerCase();
            if (!_TAG_EXPRESSIONS.has(tg) || paired.has(tg)) out.push({ pos: m.index, end: m.index + m[0].length, kind: 'open', tag: tg });
        }
        const r2 = /\[\/([a-zA-Z][a-zA-Z0-9_\-]*)\]/g;
        while ((m = r2.exec(t)) !== null) {
            const tg = m[1].toLowerCase();
            if (!_TAG_RESERVED.has(tg)) out.push({ pos: m.index, end: m.index + m[0].length, kind: 'close', tag: tg });
        }
        out.sort((a, b) => a.pos - b.pos);
        return out;
    }

    const tags = allTags(text);

    // Each insertion: { at: charIndex, text: string }
    const insertions = [];

    for (const issue of issues) {
        if (issue.kind === 'orphan-open') {
            // Insert closing tag just before the next opening tag after this one (or EOF)
            const nextOpen = tags.find(t => t.kind === 'open' && t.pos > issue.pos);
            const at = nextOpen ? nextOpen.pos : text.length;
            insertions.push({ at, insert: `\n[/${issue.tag}]` });

        } else if (issue.kind === 'mismatch') {
            // The opener (openerTag) has no matching close — insert its close
            // just before the next opening tag after the opener's position
            const openerTag = issue.openerTag || issue.tag;
            const openerPos = issue.openerPos != null ? issue.openerPos : issue.pos;
            const nextOpen  = tags.find(t => t.kind === 'open' && t.pos > openerPos);
            const at = nextOpen ? nextOpen.pos : text.length;
            insertions.push({ at, insert: `\n[/${openerTag}]` });

        } else if (issue.kind === 'orphan-close') {
            // Insert opening tag just after the previous closing tag before this one (or BOF)
            const prevClose = [...tags].reverse().find(t => t.kind === 'close' && t.end <= issue.pos);
            const at = prevClose ? prevClose.end : 0;
            insertions.push({ at, insert: `\n[${issue.tag}]` });
        }
    }

    // Deduplicate insertions at the same position with the same text
    const seen = new Set();
    const unique = insertions.filter(ins => {
        const key = ins.at + '|' + ins.insert;
        if (seen.has(key)) return false;
        seen.add(key);
        return true;
    });

    // Apply back-to-front so earlier offsets stay valid
    unique.sort((a, b) => b.at - a.at);

    let result = text;
    for (const { at, insert } of unique) {
        const before = result[at - 1];
        const after  = result[at];
        // insert starts with \n; if there's already a newline before, trim the leading \n
        const actualInsert = (before === '\n' ? insert.replace(/^\n/, '') : insert)
            + (after && after !== '\n' ? '\n' : '');
        result = result.slice(0, at) + actualInsert + result.slice(at);
    }

    textarea.value = result;
    lastAnalyzedText = null;
    _updateTagErrorBanner();
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
}

// ── Wire up events once DOM is ready ─────────────────────────────────────────
function _initTagErrorBanner() {
    const textarea = document.getElementById('input-text');
    const prevBtn  = document.getElementById('tag-error-prev-btn');
    const nextBtn  = document.getElementById('tag-error-next-btn');
    const fixBtn   = document.getElementById('tag-error-fix-btn');
    if (!textarea) return;

    let _tagCheckTimer = null;
    textarea.addEventListener('input', () => {
        clearTimeout(_tagCheckTimer);
        _tagCheckTimer = setTimeout(_updateTagErrorBanner, 600);
    });
    textarea.addEventListener('paste', () => {
        clearTimeout(_tagCheckTimer);
        _tagCheckTimer = setTimeout(_updateTagErrorBanner, 800);
    });

    if (prevBtn) prevBtn.addEventListener('click', () => _navigateTagIssue(-1));
    if (nextBtn) nextBtn.addEventListener('click', () => _navigateTagIssue(+1));
    if (fixBtn)  fixBtn.addEventListener('click',  _autoFixTagBalance);
}

document.addEventListener('DOMContentLoaded', _initTagErrorBanner);

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
    if (queuePollInFlight) {
        return;
    }
    queuePollInFlight = true;
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
    } finally {
        queuePollInFlight = false;
    }
}

// Start periodic queue indicator updates
setInterval(updateQueueIndicator, 2000);
updateQueueIndicator();

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
        if (!voiceFxState[key]) {
            voiceFxState[key] = {
                pitch: DEFAULT_FX_STATE.pitch,
                speed: DEFAULT_FX_STATE.speed,
                sampleText: DEFAULT_FX_STATE.sampleText
            };
        } else {
            // Ensure legacy objects get any new defaults
            voiceFxState[key] = {
                pitch: Number.isFinite(voiceFxState[key].pitch) ? voiceFxState[key].pitch : DEFAULT_FX_STATE.pitch,
                speed: Number.isFinite(voiceFxState[key].speed) ? voiceFxState[key].speed : DEFAULT_FX_STATE.speed,
                sampleText: voiceFxState[key].sampleText ?? DEFAULT_FX_STATE.sampleText
            };
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
    updateSectionReviewButton(false);
    initDefaultVoiceFxPanel();
    showNotification('Assignments reset. Run Analyze Text again when you\'re ready.', 'info');
}

// Populate default voice selector
function populateDefaultVoiceSelect() {
    const select = document.getElementById('default-voice-select');
    if (!select) {
        return;
    }

    const engineName = getSelectedJobEngine() || runtimeSettings?.tts_engine || 'kokoro';
    const isPocketPreset = isPocketPresetEngine(engineName);
    const isCloudCatalog = isCatalogCloudEngine(engineName);
    if (!isPocketPreset && !isCloudCatalog && !window.availableVoices) {
        return;
    }
    if (isPocketPreset && !window.availablePocketTtsVoices) {
        return;
    }

    const configuredDefault = isAzureSpeechEngine(engineName)
        ? runtimeSettings?.azure_speech_default_voice
        : (isEdgeTtsEngine(engineName)
            ? runtimeSettings?.edge_tts_default_voice
            : (isElevenLabsEngine(engineName) ? runtimeSettings?.elevenlabs_default_voice
                : (isOpenAITtsEngine(engineName) ? runtimeSettings?.openai_tts_default_voice
                    : (isLocalAITtsEngine(engineName) ? runtimeSettings?.localai_tts_default_voice : ''))));
    const previousValue = select.value;
    select.innerHTML = '<option value="">Select Default Voice...</option>';
    if (engineName === 'breeze_api') {
        appendProviderVoiceOptions(select, window.breezeApiVoices || [], 'Breeze saved voices');
        window.ensureBreezeVoiceOption?.(select, runtimeSettings?.breeze_api_default_voice);
        select.value = runtimeSettings?.breeze_api_default_voice || '';
    } else if (isPocketPreset) {
        appendPocketPresetVoiceOptions(select);
    } else if (isAzureSpeechEngine(engineName)) {
        appendProviderVoiceOptions(select, azureSpeechVoices, 'Azure voices');
    } else if (isEdgeTtsEngine(engineName)) {
        appendProviderVoiceOptions(select, edgeTtsVoices, 'Edge voices');
    } else if (isElevenLabsEngine(engineName)) {
        appendProviderVoiceOptions(select, elevenLabsVoices, 'ElevenLabs voices');
    } else if (isOpenAITtsEngine(engineName)) {
        appendProviderVoiceOptions(select, openAITtsVoices, 'OpenAI TTS voices');
    } else if (isLocalAITtsEngine(engineName)) {
        appendProviderVoiceOptions(select, localAITtsVoices, 'LocalAI voice profiles');
    } else {
        appendVoiceOptions(select);
    }
    restoreSelectValue(select, previousValue);
    if (!select.value && configuredDefault && Array.from(select.options).some(option => option.value === configuredDefault)) {
        select.value = configuredDefault;
    }
}

function appendAzureSpeechVoiceOptions(selectElement) {
    const groups = new Map();
    azureSpeechVoices.forEach(voice => {
        const groupLabel = voice.locale_name || voice.locale || 'Azure voices';
        if (!groups.has(groupLabel)) groups.set(groupLabel, []);
        groups.get(groupLabel).push(voice);
    });
    groups.forEach((voices, groupLabel) => {
        const group = document.createElement('optgroup');
        group.label = groupLabel;
        voices.forEach(voice => {
            const option = document.createElement('option');
            option.value = voice.short_name;
            option.textContent = `${voice.display_name || voice.short_name} · ${voice.gender || 'Unknown'} (${voice.short_name})`;
            option.dataset.locale = voice.locale || '';
            group.appendChild(option);
        });
        selectElement.appendChild(group);
    });
}

function appendProviderVoiceOptions(selectElement, voices, fallbackLabel) {
    const groups = new Map();
    (voices || []).forEach(voice => {
        const groupLabel = voice.locale_name || voice.locale || fallbackLabel;
        if (!groups.has(groupLabel)) groups.set(groupLabel, []);
        groups.get(groupLabel).push(voice);
    });
    groups.forEach((entries, groupLabel) => {
        const group = document.createElement('optgroup');
        group.label = groupLabel;
        entries.forEach(voice => {
            const option = document.createElement('option');
            option.value = voice.short_name || voice.voice_id;
            const details = [voice.gender, voice.category].filter(Boolean).join(' · ');
            option.textContent = `${voice.display_name || option.value}${details ? ` · ${details}` : ''}`;
            option.dataset.locale = voice.locale || '';
            option.disabled = Boolean(voice.disabled);
            if (voice.disabled_reason) option.title = voice.disabled_reason;
            group.appendChild(option);
        });
        selectElement.appendChild(group);
    });
}

function appendVoiceOptions(selectElement) {
    if (!window.availableVoices) {
        return;
    }
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

    const azureVoice = getAzureVoice(voiceName);
    if (azureVoice) return azureVoice.locale || 'en-US';

    const providerVoice = [...edgeTtsVoices, ...elevenLabsVoices, ...openAITtsVoices, ...localAITtsVoices, ...(window.breezeApiVoices || [])]
        .find(voice => (voice.short_name || voice.voice_id) === voiceName);
    if (providerVoice) return providerVoice.locale || '';

    if (!window.availableVoices) return 'a';
    
    for (const [key, voiceConfig] of Object.entries(window.availableVoices)) {
        if (voiceConfig.voices.includes(voiceName)) {
            return voiceConfig.lang_code;
        }
    }
    return 'a'; // Default to American English
}

// Get voice assignments from UI (from inline assignments in Generate tab)
function buildTurboSelectionMap() {
    const map = {};
    captureCompatibleVoiceSamples();
    Object.entries(turboSelectionState).forEach(([speaker, reference]) => {
        if (speaker && reference) {
            map[speaker] = { reference };
        }
    });
    getAssignmentRows().forEach(row => {
        const speaker = row.dataset.speaker;
        if (!speaker) return;
        const providerValue = row.querySelector('.voice-select')?.value?.trim() || '';
        if (providerValue.startsWith(TTS_STORY_VOICE_REFERENCE_PREFIX)) {
            const reference = localAIVoiceReferenceToPromptPath(providerValue);
            if (reference) map[speaker] = { reference };
            return;
        }
        const reference = row.querySelector('.reference-select')?.value.trim();
        if (reference) {
            map[speaker] = { reference };
        }
    });
    return map;
}

function applyTurboSelections(assignments, turboSelections, globalReference) {
    Object.entries(assignments).forEach(([speakerKey, assignment]) => {
        const selection = turboSelections[speakerKey] || {};
        const resolvedReference = selection.reference || globalReference || '';
        if (!assignment.audio_prompt_path && resolvedReference) {
            assignment.audio_prompt_path = resolvedReference;
            const promptEntry = findReferencePromptByPath(resolvedReference);
            if (promptEntry?.transcript) {
                assignment.extra = {
                    ...(assignment.extra || {}),
                    prompt_text: promptEntry.transcript,
                };
            }
        }
    });
}

function buildTurboAssignment(speakerKey, referencePath) {
    const assignment = {};
    if (referencePath) {
        assignment.audio_prompt_path = referencePath;
        const promptEntry = findReferencePromptByPath(referencePath);
        if (promptEntry?.transcript) {
            assignment.extra = {
                ...(assignment.extra || {}),
                prompt_text: promptEntry.transcript,
            };
        }
    }
    const fxPayload = getFxPayload(speakerKey);
    if (fxPayload) {
        assignment.fx = fxPayload;
    }
    const state = getFxState(speakerKey);
    const speedValue = Number(state?.speed) || 1;
    if (Math.abs(speedValue - 1) > 0.005) {
        assignment.speed = Number(speedValue.toFixed(2));
    }
    return Object.keys(assignment).length ? assignment : null;
}

function getVoiceAssignments() {
    const assignments = {};
    const selects = document.querySelectorAll('#inline-voice-assignment-list .voice-select, #speaker-edit-modal-body .voice-select');
    const engineName = getSelectedJobEngine() || runtimeSettings?.tts_engine || 'kokoro';
    if (engineName === 'breeze_api') {
        const selections = buildTurboSelectionMap();
        const globalReference = getGlobalReferenceSelection();
        getAssignmentRows().forEach(row => {
            const speaker = row.dataset.speaker;
            const refSelect = row.querySelector('.reference-select');
            const reference = refSelect ? refSelect.value.trim() : selections[speaker]?.reference || globalReference || '';
            if (reference) {
                assignments[speaker] = buildTurboAssignment(speaker, reference) || {audio_prompt_path: reference};
                const profile = findSpeakerProfile(speaker).profile;
                const language = findReferencePromptByPath(reference)?.language || profile?.language || 'en';
                const languages = {english: 'en', chinese: 'zh', japanese: 'ja', korean: 'ko', french: 'fr', german: 'de', spanish: 'es', portuguese: 'pt', italian: 'it', russian: 'ru', arabic: 'ar', hindi: 'hi', dutch: 'nl', polish: 'pl', turkish: 'tr', vietnamese: 'vi', thai: 'th', indonesian: 'id', greek: 'el', czech: 'cs', finnish: 'fi', romanian: 'ro', ukrainian: 'uk'};
                assignments[speaker].extra = {...(assignments[speaker].extra || {}),
                    breeze_language: languages[language.toLowerCase()] || language.toLowerCase().split('-')[0]};
                return;
            }
            const voice = row.querySelector('.voice-select')?.value || runtimeSettings?.breeze_api_default_voice || '';
            const entry = (window.breezeApiVoices || []).find(v => v.voice_id === voice);
            assignments[speaker] = {voice, lang_code: entry?.locale || '', fx: getFxPayload(speaker),
                speed: Number(getFxState(speaker)?.speed) || 1};
        });
        return assignments;
    }
    const turboEnabled = isPromptEngine(engineName);
    const qwenEnabled = isQwenEngine(engineName);
    const qwenCloneEnabled = isQwenCloneEngine(engineName);
    const pocketPresetEnabled = isPocketPresetEngine(engineName);
    const pocketPresetDefault = pocketPresetEnabled
        ? document.getElementById('default-voice-select')?.value?.trim() || ''
        : '';
    const omniDesignEnabled = isOmniVoiceDesignEngine(engineName);
    const omniCloneEnabled = isOmniVoiceCloneEngine(engineName);
    const turboSelections = (turboEnabled || qwenCloneEnabled || omniCloneEnabled) ? buildTurboSelectionMap() : {};
    const globalReference = (turboEnabled || qwenCloneEnabled || omniCloneEnabled) ? getGlobalReferenceSelection() : '';
    const qwenSpeakerDefault = document.getElementById('qwen3-default-speaker')?.value || '';
    const qwenLanguage = document.getElementById('qwen3-default-language')?.value || 'Auto';

    if (isLocalAITtsEngine(engineName)) {
        const rows = getAssignmentRows();
        const targets = rows.length ? rows : [];
        targets.forEach(row => {
            const speaker = row.dataset.speaker;
            if (!speaker) return;
            const voice = row.querySelector('.localai-voice-input')?.value?.trim()
                || runtimeSettings?.localai_tts_default_voice || '';
            const language = row.querySelector('.localai-language-input')?.value?.trim()
                || runtimeSettings?.localai_tts_default_language || '';
            const assignment = createAssignment(voice, language, speaker);
            assignment.voice = voice;
            assignment.lang_code = language;
            assignments[speaker] = assignment;
        });
        if (!targets.length) {
            assignments.default = createAssignment(
                runtimeSettings?.localai_tts_default_voice || '',
                runtimeSettings?.localai_tts_default_language || '',
                'default'
            );
        }
        return assignments;
    }

    if (engineName === 'breeze_tts_2') {
        const rows = getAssignmentRows();
        const targets = rows.length
            ? rows.map(row => row.dataset.speaker).filter(Boolean)
            : (currentStats?.speakers?.length ? currentStats.speakers : ['default']);
        targets.forEach(speakerKey => {
            const selection = turboSelections[speakerKey] || {};
            const reference = selection.reference || globalReference || '';
            const profile = findSpeakerProfile(speakerKey).profile;
            const assignment = buildTurboAssignment(speakerKey, reference) || {};
            assignment.extra = {
                ...(assignment.extra || {}),
                voice_design_prompt: profile?.voice_design_prompt || profile?.voice || '',
            };
            assignments[speakerKey] = assignment;
        });
        return assignments;
    }

    // OmniVoice Clone: build per-speaker assignment from the reference-select.
    // If no reference is selected, emit an empty assignment so the empty-map
    // guard doesn't fire — the backend will fall back to the configured default prompt.
    if (omniCloneEnabled) {
        const uiRows = getAssignmentRows();
        const targets = uiRows.length
            ? uiRows.map(r => r.dataset.speaker).filter(Boolean)
            : (currentStats?.has_speaker_tags && currentStats.speakers?.length ? currentStats.speakers : ['Speaker 1']);
        targets.forEach(speakerKey => {
            const row = document.querySelector(`#inline-voice-assignment-list .voice-assignment-row[data-speaker="${speakerKey}"], #speaker-edit-modal-body .voice-assignment-row[data-speaker="${speakerKey}"]`);
            const refSelect = row?.querySelector('.reference-select');
            const refValue = refSelect?.value?.trim() || turboSelections[speakerKey]?.reference || globalReference || '';
            const fxPayload = getFxPayload(speakerKey);
            const state = getFxState(speakerKey);
            const speedValue = Number(state?.speed) || 1;
            const assignment = {};
            if (refValue) {
                assignment.audio_prompt_path = refValue;
                const promptEntry = findReferencePromptByPath(refValue);
                if (promptEntry?.transcript) {
                    assignment.extra = { prompt_text: promptEntry.transcript };
                }
            }
            if (fxPayload) assignment.fx = fxPayload;
            if (Math.abs(speedValue - 1) > 0.005) assignment.speed = Number(speedValue.toFixed(2));
            assignments[speakerKey] = assignment;
        });
        return assignments;
    }

    // OmniVoice Design needs no reference prompt — instruct string drives generation.
    // Build a minimal assignment for every detected speaker so validation passes.
    if (omniDesignEnabled) {
        const uiRows = getAssignmentRows();
        const targets = uiRows.length
            ? uiRows.map(r => r.dataset.speaker).filter(Boolean)
            : (currentStats?.has_speaker_tags && currentStats.speakers?.length ? currentStats.speakers : ['Speaker 1']);
        targets.forEach(speakerKey => {
            const row = document.querySelector(`#inline-voice-assignment-list .voice-assignment-row[data-speaker="${speakerKey}"]`);
            const instructInput = row?.querySelector('.omnivoice-instruct-input');
            const instruct = instructInput?.value?.trim() || '';
            const fxPayload = getFxPayload(speakerKey);
            const state = getFxState(speakerKey);
            const speedValue = Number(state?.speed) || 1;
            const assignment = {};
            if (instruct) assignment.voice = instruct;
            if (fxPayload) assignment.fx = fxPayload;
            if (Math.abs(speedValue - 1) > 0.005) assignment.speed = Number(speedValue.toFixed(2));
            assignments[speakerKey] = assignment;
        });
        return assignments;
    }

    selects.forEach(select => {
        const speaker = select.dataset.speaker;
        const voiceName = select.value;
        if (qwenEnabled) {
            const selectedVoice = voiceName || qwenSpeakerDefault;
            if (selectedVoice) {
                // Get per-speaker Qwen3 settings from inline controls
                const row = select.closest('.voice-assignment-row');
                const langSelect = row?.querySelector('.qwen3-language-select');
                const instructInput = row?.querySelector('.qwen3-instruct-input');
                const speakerLang = langSelect?.value || qwenLanguage;
                const speakerInstruct = instructInput?.value?.trim() || '';
                
                assignments[speaker] = {
                    voice: selectedVoice,
                    extra: { 
                        language: speakerLang,
                        ...(speakerInstruct && { instruct: speakerInstruct })
                    }
                };
            }
            return;
        }

        if (qwenCloneEnabled) {
            return;
        }

        if (pocketPresetEnabled) {
            const presetVoice = voiceName || pocketPresetDefault;
            if (presetVoice) {
                assignments[speaker] = createPresetAssignment(presetVoice, speaker);
            }
            return;
        }

        if (voiceName && (window.availableVoices || isCatalogCloudEngine(engineName))) {
            const langCode = getLangCodeForVoice(voiceName);
            assignments[speaker] = createAssignment(voiceName, langCode, speaker);
            if (isAzureSpeechEngine(engineName)) {
                assignments[speaker].extra = collectAzureVoiceOptions(select.closest('.voice-assignment-row'), voiceName);
            }
        }
    });

    if (pocketPresetEnabled && !Object.keys(assignments).length) {
        const fallbackVoice = pocketPresetDefault;
        if (fallbackVoice) {
            assignments.default = createPresetAssignment(fallbackVoice, 'default');
        }
    }

    if (turboEnabled || qwenCloneEnabled) {
        if (Object.keys(assignments).length) {
            applyTurboSelections(assignments, turboSelections, globalReference);
        } else {
            const rowSpeakers = getAssignmentRows()
                .map(row => row.dataset.speaker)
                .filter(Boolean);
            const targets = rowSpeakers.length
                ? rowSpeakers
                : ((currentStats?.speakers && currentStats.speakers.length)
                    ? currentStats.speakers
                    : ['default']);
            targets.forEach(speakerKey => {
                const selection = turboSelections[speakerKey] || {};
                const resolvedReference = selection.reference || globalReference || '';
                const turboAssignment = buildTurboAssignment(speakerKey, resolvedReference);
                if (turboAssignment) {
                    assignments[speakerKey] = turboAssignment;
                }
            });
        }
    }
    
    if (qwenEnabled && !Object.keys(assignments).length) {
        const fallbackSpeaker = qwenSpeakerDefault;
        if (fallbackSpeaker) {
            const targets = (currentStats?.speakers && currentStats.speakers.length)
                ? currentStats.speakers
                : ['default'];
            targets.forEach(speakerKey => {
                assignments[speakerKey] = {
                    voice: fallbackSpeaker,
                    extra: { language: qwenLanguage }
                };
            });
        }
    }

    return assignments;
}

function findReferencePromptByPath(pathValue) {
    if (!pathValue) return null;
    const normalized = pathValue.trim();
    if (!normalized) return null;
    const prompts = window.availableReferencePrompts || [];
    return prompts.find(entry => {
        const name = (entry?.name || '').trim();
        const display = (entry?.display || '').trim();
        return name === normalized || display === normalized;
    });
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

// ============================================================
// Document Upload / Drag-Drop Functionality
// ============================================================

function initDocumentUpload() {
    const wrapper = document.getElementById('text-input-wrapper');
    const textarea = document.getElementById('input-text');
    const dropOverlay = document.getElementById('drop-overlay');
    const browseBtn = document.getElementById('browse-document-btn');
    const fileInput = document.getElementById('document-file-input');
    const statusEl = document.getElementById('document-upload-status');
    const clearBtn = document.getElementById('clear-text-btn');

    if (!wrapper || !textarea || !fileInput) return;

    // Clear button click
    clearBtn?.addEventListener('click', () => {
        if (textarea.value.trim() && !confirm('Clear all text from the input?')) {
            return;
        }
        textarea.value = '';
        textarea.dispatchEvent(new Event('input', { bubbles: true }));
        if (statusEl) {
            statusEl.textContent = '';
            statusEl.className = 'upload-status';
        }
    });

    // Drag and drop events
    ['dragenter', 'dragover'].forEach(eventName => {
        wrapper.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            wrapper.classList.add('drag-over');
        });
    });

    ['dragleave', 'drop'].forEach(eventName => {
        wrapper.addEventListener(eventName, (e) => {
            e.preventDefault();
            e.stopPropagation();
            wrapper.classList.remove('drag-over');
        });
    });

    wrapper.addEventListener('drop', (e) => {
        const files = e.dataTransfer?.files;
        if (files && files.length > 0) {
            handleMultipleDocuments(Array.from(files), statusEl, textarea);
        }
    });

    // Browse button click
    browseBtn?.addEventListener('click', () => {
        fileInput.click();
    });

    // File input change - support multiple files
    fileInput.setAttribute('multiple', 'true');
    fileInput.addEventListener('change', () => {
        if (fileInput.files && fileInput.files.length > 0) {
            handleMultipleDocuments(Array.from(fileInput.files), statusEl, textarea);
            fileInput.value = ''; // Reset for next selection
        }
    });
}

async function handleMultipleDocuments(files, statusEl, textarea) {
    const supportedExtensions = ['.txt', '.pdf', '.doc', '.docx', '.rtf', '.epub', '.odt', '.md', '.html', '.htm'];
    
    // Filter to supported files
    const validFiles = files.filter(file => {
        const ext = '.' + file.name.toLowerCase().split('.').pop();
        return supportedExtensions.includes(ext);
    });

    if (validFiles.length === 0) {
        if (statusEl) {
            statusEl.textContent = 'No supported documents found';
            statusEl.className = 'upload-status error';
        }
        return;
    }

    if (statusEl) {
        statusEl.textContent = `Extracting text from ${validFiles.length} document(s)...`;
        statusEl.className = 'upload-status loading';
    }

    let totalWords = 0;
    let successCount = 0;
    let errors = [];

    for (const file of validFiles) {
        try {
            const result = await extractSingleDocument(file);
            if (result.success) {
                // Always append
                const existingText = textarea.value.trim();
                if (existingText) {
                    textarea.value = existingText + '\n\n' + result.text;
                } else {
                    textarea.value = result.text;
                }
                totalWords += result.word_count;
                successCount++;
            } else {
                errors.push(`${file.name}: ${result.error}`);
            }
        } catch (err) {
            errors.push(`${file.name}: ${err.message}`);
        }
    }

    // Update status
    if (statusEl) {
        if (successCount > 0) {
            statusEl.textContent = `✓ Loaded ${successCount} doc(s): ${totalWords.toLocaleString()} words`;
            statusEl.className = 'upload-status';
        } else {
            statusEl.textContent = 'Failed to extract documents';
            statusEl.className = 'upload-status error';
        }
    }

    // Trigger input event
    textarea.dispatchEvent(new Event('input', { bubbles: true }));

    // Show notification
    if (successCount > 0) {
        showNotification(`Extracted ${totalWords.toLocaleString()} words from ${successCount} document(s)`, 'success');
    }
    if (errors.length > 0) {
        console.warn('Document extraction errors:', errors);
    }
}

async function extractSingleDocument(file) {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('/api/extract-document', {
        method: 'POST',
        body: formData
    });

    return await response.json();
}

// Initialize document upload on page load
document.addEventListener('DOMContentLoaded', initDocumentUpload);

// ============================================================
// Paralinguistic Tag Insertion
// ============================================================

function initParalinguisticTags() {
    const tagsBar = document.querySelector('.paralinguistic-tags-bar');
    const textarea = document.getElementById('input-text');
    
    if (!tagsBar || !textarea) return;
    
    tagsBar.addEventListener('click', (e) => {
        const btn = e.target.closest('.btn-tag');
        if (!btn) return;
        
        const tag = btn.dataset.tag;
        if (!tag) return;
        
        insertTextAtCursor(textarea, tag);
    });
}

function insertTextAtCursor(textarea, text) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const before = textarea.value.substring(0, start);
    const after = textarea.value.substring(end);
    
    textarea.value = before + text + after;
    
    // Move cursor to after the inserted text
    const newPos = start + text.length;
    textarea.selectionStart = newPos;
    textarea.selectionEnd = newPos;
    
    // Focus the textarea
    textarea.focus();
    
    // Trigger input event for any listeners
    textarea.dispatchEvent(new Event('input', { bubbles: true }));
}

document.addEventListener('DOMContentLoaded', initParalinguisticTags);

// ============================================================
// Alt Word Registry
// ============================================================

const ALT_WORD_REGISTRY_KEY = 'tts-alt-word-registry';

// In-memory registry: [{original, replacement}]
let altWordRegistry = [];

// Currently-playing preview audio for the entry modal
let awrPreviewAudio = null;
// Index being edited (-1 = new entry)
let awrEditIndex = -1;

function loadAltWordRegistry() {
    // Session-only: do not restore from localStorage
    altWordRegistry = [];
}

function saveAltWordRegistry() {
    // Session-only: do not persist to localStorage
}

/** Return the registry as [{original, replacement}] for use by generateAudio */
function getAltWordRegistry() {
    return altWordRegistry.slice();
}
window.getAltWordRegistry = getAltWordRegistry;

function setAltWordRegistry(entries) {
    altWordRegistry = Array.isArray(entries)
        ? entries
            .filter(entry => entry && entry.original && entry.replacement)
            .map(entry => ({
                original: String(entry.original).trim(),
                replacement: String(entry.replacement).trim()
            }))
            .filter(entry => entry.original && entry.replacement)
        : [];
    saveAltWordRegistry();
    renderAltWordTable();
}
window.setAltWordRegistry = setAltWordRegistry;

/** Count case-insensitive occurrences of `word` in `text` (whole-word match) */
function countWordInstances(word, text) {
    if (!word || !text) return 0;
    try {
        const escaped = word.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
        const re = new RegExp(escaped, 'gi');
        return (text.match(re) || []).length;
    } catch (e) {
        return 0;
    }
}

function getCurrentInputText() {
    return document.getElementById('input-text')?.value || '';
}

function renderAltWordTable() {
    const tbody = document.getElementById('awr-table-body');
    const countLabel = document.getElementById('awr-count-label');
    if (!tbody) return;

    const text = getCurrentInputText();

    if (altWordRegistry.length === 0) {
        tbody.innerHTML = '<tr id="awr-empty-row"><td colspan="4" class="awr-empty">No entries yet. Click <strong>＋ Add Entry</strong> to get started.</td></tr>';
        if (countLabel) countLabel.textContent = '';
        return;
    }

    if (countLabel) countLabel.textContent = `${altWordRegistry.length} entr${altWordRegistry.length === 1 ? 'y' : 'ies'}`;

    tbody.innerHTML = altWordRegistry.map((entry, idx) => {
        const instances = countWordInstances(entry.original, text);
        const badgeClass = instances === 0 ? 'awr-instances-badge awr-zero' : 'awr-instances-badge';
        return `
        <tr>
            <td class="awr-original-cell">${escapeHtml(entry.original)}</td>
            <td class="awr-replacement-cell">${escapeHtml(entry.replacement)}</td>
            <td class="awr-instances-cell"><span class="${badgeClass}">${instances}</span></td>
            <td class="awr-actions-cell">
                <button class="awr-edit-btn" data-idx="${idx}" title="Edit">✏️</button>
                <button class="awr-delete-btn" data-idx="${idx}" title="Delete">🗑️</button>
            </td>
        </tr>`;
    }).join('');

    // Bind row action buttons
    tbody.querySelectorAll('.awr-edit-btn').forEach(btn => {
        btn.addEventListener('click', () => openAwrEntryModal(parseInt(btn.dataset.idx, 10)));
    });
    tbody.querySelectorAll('.awr-delete-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            const idx = parseInt(btn.dataset.idx, 10);
            altWordRegistry.splice(idx, 1);
            saveAltWordRegistry();
            renderAltWordTable();
        });
    });
}

// ---- Main registry modal ----

function openAltWordRegistryModal() {
    renderAltWordTable();
    document.getElementById('alt-word-registry-overlay')?.classList.remove('hidden');
    document.getElementById('alt-word-registry-modal')?.classList.remove('hidden');
}

function closeAltWordRegistryModal() {
    document.getElementById('alt-word-registry-overlay')?.classList.add('hidden');
    document.getElementById('alt-word-registry-modal')?.classList.add('hidden');
}

// ---- Entry sub-modal ----

async function awrPopulateVoiceSelect(engineName) {
    const select = document.getElementById('awr-preview-voice');
    if (!select) return;
    const prev = select.value;
    select.innerHTML = '<option value="">-- Select voice --</option>';

    const norm = (engineName || '').toLowerCase().replace(/[_-]/g, '');
    const usesPrompts = norm.includes('chatterbox') || norm.includes('voxcpm')
        || (norm.includes('pockettts') && !norm.includes('pocketttspreset'))
        || (norm.includes('qwen3') && norm.includes('clone'))
        || norm.includes('omnivoice')
        || norm.includes('indextts')
        || norm.includes('dotstts');
    const isQwen = norm.includes('qwen3') && !norm.includes('clone');
    const isPocketPreset = norm.includes('pocketttspreset');
    const isKittenTts = norm.includes('kittentts');
    const isAzureSpeech = norm.includes('azurespeech');
    const isEdgeTts = norm.includes('edgetts');
    const isElevenLabs = norm.includes('elevenlabs');
    const isOpenAITts = norm.includes('openaitts');
    const isLocalAITts = norm.includes('localaitts');
    const isBreezeApi = norm.includes('breezeapi');

    try {
        if (usesPrompts) {
            const resp = await fetch('/api/voice-prompts');
            const data = await resp.json();
            if (data.success && data.prompts) {
                data.prompts.forEach(p => {
                    const opt = document.createElement('option');
                    opt.value = p.path || p.name;
                    opt.textContent = p.display || p.name;
                    select.appendChild(opt);
                });
            }
        } else if (isQwen) {
            const resp = await fetch('/api/qwen3/metadata');
            const data = await resp.json();
            if (data.success && data.speakers) {
                data.speakers.forEach(s => {
                    const opt = document.createElement('option');
                    opt.value = s;
                    opt.textContent = s;
                    select.appendChild(opt);
                });
            }
        } else if (isPocketPreset) {
            const resp = await fetch('/api/pocket-tts/voices');
            const data = await resp.json();
            if (data.success && data.voices) {
                data.voices.forEach(v => {
                    const opt = document.createElement('option');
                    opt.value = v;
                    opt.textContent = v;
                    select.appendChild(opt);
                });
            }
        } else if (isKittenTts) {
            KITTEN_TTS_VOICES.forEach(voiceName => {
                const opt = document.createElement('option');
                opt.value = voiceName;
                opt.textContent = voiceName;
                select.appendChild(opt);
            });
        } else if (isAzureSpeech) {
            const resp = await fetch('/api/azure-speech/voices');
            const data = await resp.json();
            if (data.success && data.voices) {
                data.voices.forEach(voice => {
                    const opt = document.createElement('option');
                    opt.value = voice.short_name;
                    opt.textContent = `${voice.display_name || voice.short_name} (${voice.locale_name || voice.locale})`;
                    select.appendChild(opt);
                });
            }
        } else if (isEdgeTts || isElevenLabs || isOpenAITts || isLocalAITts || isBreezeApi) {
            const endpoint = isBreezeApi ? '/api/breeze-api/catalog' : isEdgeTts ? '/api/edge-tts/voices'
                : (isElevenLabs ? '/api/elevenlabs/catalog'
                    : (isLocalAITts ? '/api/localai-tts/catalog' : '/api/openai-tts/catalog'));
            const resp = await fetch(endpoint);
            const data = await resp.json();
            if (data.success && data.voices) {
                data.voices.forEach(voice => {
                    const opt = document.createElement('option');
                    opt.value = voice.short_name || voice.voice_id;
                    opt.textContent = `${voice.display_name || opt.value}${voice.locale ? ` (${voice.locale})` : ''}`;
                    select.appendChild(opt);
                });
            }
        } else {
            // Kokoro / standard voices
            if (window.availableVoices) {
                Object.values(window.availableVoices).forEach(vc => {
                    const grp = document.createElement('optgroup');
                    grp.label = vc.language || 'Voices';
                    (vc.voices || []).forEach(name => {
                        const opt = document.createElement('option');
                        opt.value = name;
                        opt.textContent = name;
                        grp.appendChild(opt);
                    });
                    select.appendChild(grp);
                });
            }
        }
    } catch (e) {
        console.warn('AWR: failed to load voices', e);
    }

    // Restore previous selection if still valid
    if (prev && Array.from(select.options).some(o => o.value === prev)) {
        select.value = prev;
    }
    updateAwrPlayButtons();
}

function updateAwrPlayButtons() {
    const voice = document.getElementById('awr-preview-voice')?.value || '';
    const hasVoice = voice.trim() !== '';
    const origBtn = document.getElementById('awr-play-original');
    const replBtn = document.getElementById('awr-play-replacement');
    if (origBtn) origBtn.disabled = !hasVoice;
    if (replBtn) replBtn.disabled = !hasVoice;
}

function openAwrEntryModal(editIdx = -1) {
    awrEditIndex = editIdx;
    const titleEl = document.getElementById('awr-entry-title');
    const origInput = document.getElementById('awr-original-input');
    const replInput = document.getElementById('awr-replacement-input');

    if (editIdx >= 0 && altWordRegistry[editIdx]) {
        if (titleEl) titleEl.textContent = 'Edit Alt Word Entry';
        if (origInput) origInput.value = altWordRegistry[editIdx].original;
        if (replInput) replInput.value = altWordRegistry[editIdx].replacement;
    } else {
        if (titleEl) titleEl.textContent = 'Add Alt Word Entry';
        if (origInput) origInput.value = '';
        if (replInput) replInput.value = '';
    }

    // Sync engine dropdown to current job engine
    const engineSelect = document.getElementById('awr-preview-engine');
    if (engineSelect) {
        const currentEngine = getSelectedJobEngine() || window.runtimeSettings?.tts_engine || 'kokoro';
        const norm = currentEngine.toLowerCase().replace(/[_-]/g, '');
        const matchingOpt = Array.from(engineSelect.options).find(o =>
            o.value.toLowerCase().replace(/[_-]/g, '') === norm
        );
        if (matchingOpt) engineSelect.value = matchingOpt.value;
    }

    awrPopulateVoiceSelect(engineSelect?.value || 'kokoro');

    const statusEl = document.getElementById('awr-preview-status');
    if (statusEl) statusEl.textContent = '';

    document.getElementById('awr-entry-overlay')?.classList.remove('hidden');
    document.getElementById('awr-entry-modal')?.classList.remove('hidden');
    origInput?.focus();
}

function closeAwrEntryModal() {
    awrStopPreview();
    document.getElementById('awr-entry-overlay')?.classList.add('hidden');
    document.getElementById('awr-entry-modal')?.classList.add('hidden');
}

function awrStopPreview() {
    if (awrPreviewAudio) {
        awrPreviewAudio.pause();
        awrPreviewAudio = null;
    }
}

async function awrPlayText(text) {
    awrStopPreview();
    const engineSelect = document.getElementById('awr-preview-engine');
    const voiceSelect = document.getElementById('awr-preview-voice');
    const statusEl = document.getElementById('awr-preview-status');

    const engineName = engineSelect?.value || 'kokoro';
    const voice = voiceSelect?.value || '';
    if (!voice) {
        if (statusEl) statusEl.textContent = 'Select a voice first.';
        return;
    }
    if (!text.trim()) {
        if (statusEl) statusEl.textContent = 'No text to preview.';
        return;
    }

    if (statusEl) statusEl.textContent = 'Generating…';

    try {
        const payload = {
            text: text.trim(),
            tts_engine: engineName,
            voice: voice,
            lang_code: getLangCodeForVoice(voice),
            speed: 1.0,
        };
        const resp = await fetch('/api/preview', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        });
        const data = await resp.json();

        if (!data.success) {
            if (statusEl) statusEl.textContent = data.error || 'Preview failed.';
            return;
        }
        const mime = data.mime_type || 'audio/wav';
        awrPreviewAudio = new Audio(`data:${mime};base64,${data.audio_base64}`);
        awrPreviewAudio.play();
        if (statusEl) statusEl.textContent = 'Playing…';
        awrPreviewAudio.onended = () => {
            awrPreviewAudio = null;
            if (statusEl) statusEl.textContent = '';
        };
    } catch (e) {
        if (statusEl) statusEl.textContent = 'Preview error.';
        console.error('AWR preview error:', e);
    }
}

function initAltWordRegistry() {
    loadAltWordRegistry();

    // Open main modal
    document.getElementById('alt-word-registry-btn')?.addEventListener('click', openAltWordRegistryModal);

    // Close main modal
    document.getElementById('alt-word-registry-close')?.addEventListener('click', closeAltWordRegistryModal);
    document.getElementById('alt-word-registry-cancel')?.addEventListener('click', closeAltWordRegistryModal);
    document.getElementById('alt-word-registry-overlay')?.addEventListener('click', (e) => {
        if (e.target === document.getElementById('alt-word-registry-overlay')) closeAltWordRegistryModal();
    });

    // Open add entry modal
    document.getElementById('awr-add-btn')?.addEventListener('click', () => openAwrEntryModal(-1));

    // Clear all entries
    document.getElementById('awr-clear-btn')?.addEventListener('click', () => {
        if (altWordRegistry.length === 0) return;
        if (!confirm('Clear all Alt Word Registry entries?')) return;
        altWordRegistry = [];
        renderAltWordTable();
    });

    // Close entry modal
    document.getElementById('awr-entry-close')?.addEventListener('click', closeAwrEntryModal);
    document.getElementById('awr-entry-cancel')?.addEventListener('click', closeAwrEntryModal);
    document.getElementById('awr-entry-overlay')?.addEventListener('click', (e) => {
        if (e.target === document.getElementById('awr-entry-overlay')) closeAwrEntryModal();
    });

    // Engine change → repopulate voices
    document.getElementById('awr-preview-engine')?.addEventListener('change', (e) => {
        awrPopulateVoiceSelect(e.target.value);
    });

    // Voice change → update play button state
    document.getElementById('awr-preview-voice')?.addEventListener('change', updateAwrPlayButtons);

    // Play original
    document.getElementById('awr-play-original')?.addEventListener('click', () => {
        const text = document.getElementById('awr-original-input')?.value || '';
        awrPlayText(text);
    });

    // Play replacement
    document.getElementById('awr-play-replacement')?.addEventListener('click', () => {
        const text = document.getElementById('awr-replacement-input')?.value || '';
        awrPlayText(text);
    });

    // OK – save entry
    document.getElementById('awr-entry-ok')?.addEventListener('click', () => {
        const original = (document.getElementById('awr-original-input')?.value || '').trim();
        const replacement = (document.getElementById('awr-replacement-input')?.value || '').trim();
        if (!original) {
            alert('Please enter the original word or phrase.');
            return;
        }
        if (!replacement) {
            alert('Please enter the replacement word or phrase.');
            return;
        }
        const entry = { original, replacement };
        if (awrEditIndex >= 0 && awrEditIndex < altWordRegistry.length) {
            altWordRegistry[awrEditIndex] = entry;
        } else {
            altWordRegistry.push(entry);
        }
        saveAltWordRegistry();
        closeAwrEntryModal();
        renderAltWordTable();
    });

    // Re-render table when text changes (updates instance counts)
    document.getElementById('input-text')?.addEventListener('input', () => {
        const overlay = document.getElementById('alt-word-registry-overlay');
        if (overlay && !overlay.classList.contains('hidden')) {
            renderAltWordTable();
        }
    });
}

document.addEventListener('DOMContentLoaded', initAltWordRegistry);
