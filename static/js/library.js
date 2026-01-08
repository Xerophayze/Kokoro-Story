// Library management

const currentChapterSelection = {};
let chunkReviewModalJobId = null;
let chunkReviewModalData = null;
let libraryChunkVoiceOverrides = {};
let libraryChunkRegenWatchers = {};
const LIBRARY_CHUNK_POLL_INTERVAL_MS = 2000;
const LIBRARY_CHUNK_MAX_ATTEMPTS = 60;

// Audio playback state for chunk review modal
let libraryActiveAudio = null;
let libraryActivePlayButton = null;

// Voice map for looking up lang_code by voice id
let libraryVoiceMap = new Map();

// Load library on tab switch
document.addEventListener('DOMContentLoaded', () => {
    // Load library when Library tab is clicked
    const libraryTab = document.querySelector('[data-tab="library"]');
    if (libraryTab) {
        libraryTab.addEventListener('click', () => {
            loadLibrary();
        });
    }
    
    // Refresh button
    const refreshBtn = document.getElementById('refresh-library-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadLibrary);
    }
    
    // Clear all button
    const clearBtn = document.getElementById('clear-library-btn');
    if (clearBtn) {
        clearBtn.addEventListener('click', clearLibrary);
    }

    // Chunk review modal close handlers
    const modalOverlay = document.getElementById('chunk-review-modal-overlay');
    const modalCloseBtn = document.getElementById('chunk-review-modal-close');
    const modalCloseFooterBtn = document.getElementById('chunk-review-close-btn');
    const recompileBtn = document.getElementById('chunk-review-recompile-btn');

    if (modalOverlay) {
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) {
                closeChunkReviewModal();
            }
        });
    }
    if (modalCloseBtn) {
        modalCloseBtn.addEventListener('click', closeChunkReviewModal);
    }
    if (modalCloseFooterBtn) {
        modalCloseFooterBtn.addEventListener('click', closeChunkReviewModal);
    }
    if (recompileBtn) {
        recompileBtn.addEventListener('click', recompileLibraryAudio);
    }
});

// Load library items
async function loadLibrary() {
    try {
        const response = await fetch('/api/library');
        const data = await response.json();
        
        if (data.success) {
            displayLibraryItems(data.items);
        } else {
            alert('Error loading library: ' + data.error);
        }
    } catch (error) {
        console.error('Error loading library:', error);
        alert('Failed to load library');
    }
}

// Display library items
function formatEngineName(engine) {
    if (!engine) return '';
    const engineMap = {
        'kokoro': 'Kokoro',
        'kokoro_replicate': 'Kokoro (Replicate)',
        'chatterbox_turbo_local': 'Chatterbox',
        'chatterbox_turbo_replicate': 'Chatterbox (Replicate)',
    };
    return engineMap[engine] || engine;
}

function formatChapterLabel(chapter) {
    if (!chapter) {
        return 'Chapter';
    }
    if (chapter.title) {
        return chapter.title;
    }
    if (chapter.index) {
        return `Chapter ${chapter.index}`;
    }
    return 'Chapter';
}

function renderChapterControls(item) {
    if (!item.chapters || item.chapters.length <= 1) {
        return '';
    }

    return `
        <div class="chapter-controls" data-job-id="${item.job_id}">
            <div class="chapter-controls-header">
                <strong>Chapters</strong>
            </div>
            <div class="chapter-pill-container">
                ${item.chapters.map((chapter, idx) => `
                    <button
                        class="btn btn-secondary btn-xs chapter-pill ${idx === 0 ? 'active' : ''}"
                        data-job-id="${item.job_id}"
                        data-relative-path="${chapter.relative_path}"
                        data-src="${chapter.output_file}"
                        data-index="${chapter.index || idx + 1}"
                    >
                        ${formatChapterLabel(chapter)}
                    </button>
                `).join('')}
            </div>
        </div>
    `;
}

function renderFullStoryBanner(item) {
    if (!item.full_story) {
        return '';
    }

    const full = item.full_story;
    return `
        <div class="full-story-banner" data-job-id="${item.job_id}">
            <div>
                <strong>Full Story Audiobook</strong>
                <p class="help-text">One continuous file combining every chapter.</p>
            </div>
            <div class="full-story-actions">
                <button class="btn btn-secondary btn-xs" onclick="playFullStory('${item.job_id}', '${full.output_file}', '${full.relative_path}')">
                    Play
                </button>
                <button class="btn btn-primary btn-xs" onclick="downloadFullStory('${item.job_id}', '${full.relative_path}')">
                    Download Full Story
                </button>
            </div>
        </div>
    `;
}

function displayLibraryItems(items) {
    const container = document.getElementById('library-items');
    const emptyMessage = document.getElementById('library-empty');
    
    if (items.length === 0) {
        container.innerHTML = '';
        emptyMessage.style.display = 'block';
        return;
    }
    
    emptyMessage.style.display = 'none';
    container.innerHTML = '';
    
    items.forEach(item => {
        const itemCard = document.createElement('div');
        itemCard.className = 'library-item';
        
        const createdDate = new Date(item.created_at);
        const formattedDate = createdDate.toLocaleString();
        const fileSizeMB = (item.file_size / (1024 * 1024)).toFixed(2);
        const initialChapter = (item.chapters && item.chapters.length > 0) ? item.chapters[0] : null;
        if (initialChapter) {
            currentChapterSelection[item.job_id] = initialChapter;
        }

        // Format engine name for display
        const engineLabel = formatEngineName(item.engine);

        itemCard.innerHTML = `
            <div class="library-item-header">
                <div class="library-item-info">
                    <strong>${item.chapter_mode ? 'Chapter Collection' : 'Generated Audio'}</strong>
                    <span class="library-item-date">${formattedDate}</span>
                </div>
                <div class="library-item-meta">
                    ${engineLabel ? `<span class="library-item-engine">${engineLabel}</span>` : ''}
                    <span class="library-item-size">${fileSizeMB} MB</span>
                    <span class="library-item-format">${item.format.toUpperCase()}</span>
                </div>
            </div>
            <div class="library-item-player">
                <audio controls id="player-${item.job_id}"></audio>
            </div>
            ${renderChapterControls(item)}
            ${renderFullStoryBanner(item)}
            <div class="library-item-actions">
                <button class="btn btn-primary btn-sm" onclick="downloadLibraryItem('${item.job_id}')">
                    Download ${item.chapter_mode ? 'Selected Chapter' : ''}
                </button>
                ${item.chapter_mode && item.chapters && item.chapters.length > 1 ? `
                    <button class="btn btn-secondary btn-sm" onclick="downloadChapterZip('${item.job_id}')">
                        Download All (ZIP)
                    </button>
                ` : ''}
                ${item.has_chunks ? `
                    <button class="btn btn-secondary btn-sm" onclick="restoreToReview('${item.job_id}')">
                        Review Chunks
                    </button>
                ` : ''}
                <button class="btn btn-secondary btn-sm" onclick="deleteLibraryItem('${item.job_id}')">
                    Delete
                </button>
            </div>
        `;
        
        container.appendChild(itemCard);

        const player = itemCard.querySelector(`#player-${item.job_id}`);
        if (player && initialChapter) {
            player.src = initialChapter.output_file;
            player.load();
        } else if (player) {
            player.src = item.output_file;
            player.load();
        }

        // Wire chapter buttons
        const chapterButtons = itemCard.querySelectorAll(`.chapter-pill[data-job-id="${item.job_id}"]`);
        chapterButtons.forEach(button => {
            button.addEventListener('click', () => {
                const relativePath = button.getAttribute('data-relative-path');
                const src = button.getAttribute('data-src');
                const jobId = button.getAttribute('data-job-id');
                const playerEl = document.getElementById(`player-${jobId}`);

                chapterButtons.forEach(btn => btn.classList.remove('active'));
                button.classList.add('active');

                if (playerEl && src) {
                    playerEl.src = src;
                    playerEl.load();
                }

                const selectedChapter = (item.chapters || []).find(ch => ch.relative_path === relativePath) || {
                    output_file: src,
                    relative_path: relativePath,
                    title: button.textContent.trim()
                };
                currentChapterSelection[jobId] = selectedChapter;
            });
        });
    });
}

// Download library item
function downloadLibraryItem(jobId) {
    const selected = currentChapterSelection[jobId];
    const query = selected ? `?file=${encodeURIComponent(selected.relative_path)}` : '';
    window.location.href = `/api/download/${jobId}${query}`;
}

function downloadChapterZip(jobId) {
    window.location.href = `/api/download/${jobId}/zip`;
}

function playFullStory(jobId, fileUrl, relativePath) {
    const playerEl = document.getElementById(`player-${jobId}`);
    if (playerEl && fileUrl) {
        playerEl.src = fileUrl;
        playerEl.load();
    }
    currentChapterSelection[jobId] = {
        output_file: fileUrl,
        relative_path: relativePath,
        title: 'Full Story'
    };
}

function downloadFullStory(jobId, relativePath) {
    window.location.href = `/api/download/${jobId}?file=${encodeURIComponent(relativePath)}`;
}

// Delete library item
async function deleteLibraryItem(jobId) {
    if (!confirm('Are you sure you want to delete this audio file?')) {
        return;
    }
    
    try {
        const response = await fetch(`/api/library/${jobId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (data.success) {
            loadLibrary(); // Reload library
        } else {
            alert('Error deleting item: ' + data.error);
        }
    } catch (error) {
        console.error('Error deleting item:', error);
        alert('Failed to delete item');
    }
}

// Open chunk review modal for a library item
async function restoreToReview(jobId) {
    chunkReviewModalJobId = jobId;
    chunkReviewModalData = null;
    libraryChunkVoiceOverrides = {};

    const overlay = document.getElementById('chunk-review-modal-overlay');
    const modal = document.getElementById('chunk-review-modal');
    const body = document.getElementById('chunk-review-modal-body');
    const recompileBtn = document.getElementById('chunk-review-recompile-btn');

    if (overlay) overlay.classList.remove('hidden');
    if (modal) modal.classList.remove('hidden');
    if (body) body.innerHTML = '<div class="chunk-review-loading">Loading chunks...</div>';
    if (recompileBtn) recompileBtn.disabled = true;

    try {
        const response = await fetch(`/api/library/${jobId}/chunks`);
        const data = await response.json();

        if (!data.success) {
            if (body) body.innerHTML = `<div class="chunk-review-error">Error: ${data.error}</div>`;
            return;
        }

        chunkReviewModalData = data;
        renderChunkReviewModal(data);
        if (recompileBtn) recompileBtn.disabled = false;

    } catch (error) {
        console.error('Error loading chunks:', error);
        if (body) body.innerHTML = '<div class="chunk-review-error">Failed to load chunk data.</div>';
    }
}

function closeChunkReviewModal() {
    const overlay = document.getElementById('chunk-review-modal-overlay');
    const modal = document.getElementById('chunk-review-modal');

    if (overlay) overlay.classList.add('hidden');
    if (modal) modal.classList.add('hidden');

    // Stop any playing audio
    stopLibraryChunkAudio();

    // Clear watchers
    Object.keys(libraryChunkRegenWatchers).forEach(key => {
        const entry = libraryChunkRegenWatchers[key];
        if (entry && entry.timer) {
            clearTimeout(entry.timer);
        }
    });
    libraryChunkRegenWatchers = {};
    chunkReviewModalJobId = null;
    chunkReviewModalData = null;
    libraryChunkVoiceOverrides = {};
}

function renderChunkReviewModal(data) {
    const body = document.getElementById('chunk-review-modal-body');
    if (!body) return;

    const chunks = data.chunks || [];
    const chapters = data.chapters || [];
    const hasChapters = data.has_chapters || false;
    const engine = data.engine || 'kokoro';
    const jobId = data.job_id;

    if (chunks.length === 0) {
        body.innerHTML = '<div class="chunk-review-empty">No chunks available.</div>';
        return;
    }

    // Extract unique speakers and count their chunks
    const speakerMap = new Map();
    chunks.forEach(chunk => {
        const speaker = chunk.speaker || 'default';
        if (!speakerMap.has(speaker)) {
            speakerMap.set(speaker, { count: 0, voiceLabel: chunk.voice_label || chunk.voice || 'Default' });
        }
        speakerMap.get(speaker).count++;
    });

    // Build speaker section HTML
    const speakerRows = Array.from(speakerMap.entries()).map(([speaker, info]) => `
        <div class="bulk-speaker-row" data-speaker="${escapeHtml(speaker)}">
            <label class="bulk-speaker-label">
                <input type="checkbox" class="bulk-speaker-checkbox" data-speaker="${escapeHtml(speaker)}">
                <span class="bulk-speaker-name">${escapeHtml(speaker)}</span>
                <span class="bulk-speaker-count">(${info.count} chunks)</span>
                <span class="bulk-speaker-voice">${escapeHtml(info.voiceLabel)}</span>
            </label>
            <div class="bulk-speaker-actions">
                <select class="bulk-speaker-voice-select" data-speaker="${escapeHtml(speaker)}">
                    <option value="">-- Select voice --</option>
                </select>
                <button class="btn btn-xs btn-warning bulk-speaker-regen" data-speaker="${escapeHtml(speaker)}" disabled>
                    Regenerate All
                </button>
            </div>
        </div>
    `).join('');

    // Build chunk content - either grouped by chapter or flat list
    let chunkContent = '';
    if (hasChapters && chapters.length > 0) {
        // Group chunks by chapter_index
        const chunksByChapter = new Map();
        chunks.forEach((chunk, idx) => {
            const chapterIdx = chunk.chapter_index ?? 0;
            if (!chunksByChapter.has(chapterIdx)) {
                chunksByChapter.set(chapterIdx, []);
            }
            chunksByChapter.get(chapterIdx).push({ chunk, idx });
        });

        // Render chapters with expandable sections
        chunkContent = chapters.map((chapter, chapterNum) => {
            // Try both 0-indexed and the raw index from manifest for backwards compatibility
            const chapterIdx = chapter.index ?? chapterNum;
            let chapterChunks = chunksByChapter.get(chapterIdx) || [];
            // Fallback: if no chunks found and index looks 1-indexed, try 0-indexed lookup
            if (chapterChunks.length === 0 && chapterIdx > 0) {
                chapterChunks = chunksByChapter.get(chapterIdx - 1) || [];
            }
            // Another fallback: try using the array position (chapterNum) directly
            if (chapterChunks.length === 0) {
                chapterChunks = chunksByChapter.get(chapterNum) || [];
            }
            const chapterTitle = chapter.title || `Chapter ${chapterIdx + 1}`;
            const chunkRows = chapterChunks.map(({ chunk, idx }) => 
                renderLibraryChunkRow(jobId, chunk, engine, idx)
            ).join('');

            return `
                <div class="chapter-section" data-chapter-index="${chapterIdx}">
                    <div class="chapter-header" data-chapter-index="${chapterIdx}">
                        <span class="chapter-toggle">▶</span>
                        <span class="chapter-title">${escapeHtml(chapterTitle)}</span>
                        <span class="chapter-chunk-count">${chapterChunks.length} chunks</span>
                    </div>
                    <div class="chapter-chunks collapsed" data-chapter-index="${chapterIdx}">
                        ${chunkRows}
                    </div>
                </div>
            `;
        }).join('');
    } else {
        // No chapters - flat list
        chunkContent = chunks.map((chunk, idx) => renderLibraryChunkRow(jobId, chunk, engine, idx)).join('');
    }

    const chapterInfo = hasChapters ? `<span><strong>Chapters:</strong> ${chapters.length}</span>` : '';

    body.innerHTML = `
        <div class="chunk-review-header">
            <span><strong>Engine:</strong> ${engine}</span>
            ${chapterInfo}
            <span><strong>Chunks:</strong> ${chunks.length}</span>
        </div>
        <div class="bulk-speaker-section">
            <div class="bulk-speaker-header">
                <strong>Bulk Speaker Regeneration</strong>
                <span class="bulk-speaker-hint">Select speakers and choose a voice to regenerate all their chunks</span>
            </div>
            ${speakerRows}
        </div>
        <div class="chunk-review-table">
            ${chunkContent}
        </div>
    `;

    // Wire chapter toggle events if chapters exist
    if (hasChapters) {
        wireChapterToggleEvents();
    }

    wireChunkReviewEvents(jobId, chunks, engine);
}

function wireChapterToggleEvents() {
    const headers = document.querySelectorAll('.chapter-header');
    headers.forEach(header => {
        header.addEventListener('click', () => {
            const chapterIdx = header.getAttribute('data-chapter-index');
            const chunksContainer = document.querySelector(`.chapter-chunks[data-chapter-index="${chapterIdx}"]`);
            const toggle = header.querySelector('.chapter-toggle');
            
            if (chunksContainer) {
                const isCollapsed = chunksContainer.classList.contains('collapsed');
                if (isCollapsed) {
                    chunksContainer.classList.remove('collapsed');
                    if (toggle) toggle.textContent = '▼';
                } else {
                    chunksContainer.classList.add('collapsed');
                    if (toggle) toggle.textContent = '▶';
                }
            }
        });
    });
}

function renderLibraryChunkRow(jobId, chunk, engine, idx) {
    const chunkId = chunk.id;
    const text = chunk.text || '';
    const speaker = chunk.speaker || '';
    const voiceLabel = chunk.voice_label || chunk.voice || 'Default';
    const fileUrl = chunk.file_url || '';
    const cacheToken = chunk.regenerated_at || chunk.relative_file || Date.now().toString();
    const audioUrl = fileUrl ? `${fileUrl}?t=${encodeURIComponent(cacheToken)}` : '';
    const regenStatus = chunk.regen_status || '';

    let statusBadge = '';
    if (regenStatus === 'queued') {
        statusBadge = '<span class="review-chip warning">Queued</span>';
    } else if (regenStatus === 'running') {
        statusBadge = '<span class="review-chip warning">Rendering</span>';
    } else if (regenStatus === 'failed') {
        statusBadge = '<span class="review-chip error">Failed</span>';
    }

    // Speaker tag display
    const speakerTag = speaker ? `<span class="library-chunk-speaker">${escapeHtml(speaker)}</span>` : '';

    return `
        <div class="library-chunk-row" data-chunk-id="${chunkId}" data-idx="${idx}">
            <div class="library-chunk-controls">
                <button class="btn btn-xs btn-secondary library-chunk-play" data-audio-url="${audioUrl}" ${audioUrl ? '' : 'disabled'}>
                    ▶ Play
                </button>
                ${statusBadge}
                ${speakerTag}
                <span class="library-chunk-voice-label">${escapeHtml(voiceLabel)}</span>
            </div>
            <div class="library-chunk-text">
                <textarea class="library-chunk-textarea" data-chunk-id="${chunkId}" rows="2">${escapeHtml(text)}</textarea>
            </div>
            <div class="library-chunk-actions">
                <select class="library-chunk-voice-select" data-chunk-id="${chunkId}">
                    <option value="">-- Keep current --</option>
                </select>
                <button class="btn btn-xs btn-warning library-chunk-regen" data-chunk-id="${chunkId}">
                    Regenerate
                </button>
            </div>
        </div>
    `;
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

function handleLibraryChunkPlayClick(btn) {
    const url = btn.getAttribute('data-audio-url');
    if (!url) return;

    // If this button is currently playing, stop it
    if (libraryActiveAudio && libraryActivePlayButton === btn) {
        stopLibraryChunkAudio();
        return;
    }

    // Stop any other playing audio first
    if (libraryActiveAudio) {
        stopLibraryChunkAudio();
    }

    // Start playing
    const audio = new Audio(url);
    libraryActiveAudio = audio;
    libraryActivePlayButton = btn;

    // Update button to show stop state
    btn.textContent = '■ Stop';
    btn.classList.add('playing');

    audio.addEventListener('ended', () => {
        resetLibraryPlayButton(btn);
        libraryActiveAudio = null;
        libraryActivePlayButton = null;
    });

    audio.addEventListener('error', (err) => {
        console.error('Playback error:', err);
        resetLibraryPlayButton(btn);
        libraryActiveAudio = null;
        libraryActivePlayButton = null;
    });

    audio.play().catch(err => {
        console.error('Playback error:', err);
        resetLibraryPlayButton(btn);
        libraryActiveAudio = null;
        libraryActivePlayButton = null;
    });
}

function stopLibraryChunkAudio() {
    if (libraryActiveAudio) {
        libraryActiveAudio.pause();
        libraryActiveAudio.currentTime = 0;
        libraryActiveAudio = null;
    }
    if (libraryActivePlayButton) {
        resetLibraryPlayButton(libraryActivePlayButton);
        libraryActivePlayButton = null;
    }
}

function resetLibraryPlayButton(btn) {
    if (btn) {
        btn.textContent = '▶ Play';
        btn.classList.remove('playing');
    }
}

function wireChunkReviewEvents(jobId, chunks, engine) {
    const body = document.getElementById('chunk-review-modal-body');
    if (!body) return;

    // Play/Stop buttons
    body.querySelectorAll('.library-chunk-play').forEach(btn => {
        btn.addEventListener('click', () => handleLibraryChunkPlayClick(btn));
    });

    // Populate voice selects (both individual and bulk)
    populateLibraryVoiceSelects(engine);

    // Regenerate buttons for individual chunks
    body.querySelectorAll('.library-chunk-regen').forEach(btn => {
        btn.addEventListener('click', () => {
            const chunkId = btn.getAttribute('data-chunk-id');
            triggerLibraryChunkRegen(jobId, chunkId, btn);
        });
    });

    // Bulk speaker checkbox and voice select handlers
    body.querySelectorAll('.bulk-speaker-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', () => updateBulkRegenButtonState(checkbox));
    });

    body.querySelectorAll('.bulk-speaker-voice-select').forEach(select => {
        select.addEventListener('change', () => {
            const row = select.closest('.bulk-speaker-row');
            const checkbox = row?.querySelector('.bulk-speaker-checkbox');
            if (checkbox) updateBulkRegenButtonState(checkbox);
        });
    });

    // Bulk regenerate buttons
    body.querySelectorAll('.bulk-speaker-regen').forEach(btn => {
        btn.addEventListener('click', () => {
            const speaker = btn.getAttribute('data-speaker');
            triggerBulkSpeakerRegen(jobId, speaker, chunks, engine, btn);
        });
    });
}

async function populateLibraryVoiceSelects(engine) {
    const body = document.getElementById('chunk-review-modal-body');
    if (!body) return;

    const normalizedEngine = (engine || '').toLowerCase().replace(/[_-]/g, '');
    const isChatterbox = normalizedEngine.includes('chatterbox');

    let voices = [];
    try {
        if (isChatterbox) {
            // Chatterbox uses voice prompts
            const response = await fetch('/api/voice-prompts');
            const data = await response.json();
            if (data.success) {
                voices = (data.prompts || []).map(p => ({
                    id: p.name,  // API returns 'name' as the filename
                    name: p.display || p.name.replace('.wav', ''),
                    isPrompt: true
                }));
            }
        } else {
            // Kokoro and others use /api/voices - returns nested structure by language
            const response = await fetch('/api/voices');
            const data = await response.json();
            if (data.success && data.voices) {
                // Flatten the nested voice structure, keeping lang_code for each voice
                Object.entries(data.voices).forEach(([langKey, langConfig]) => {
                    const langLabel = langConfig.language || langKey;
                    const langCode = langConfig.lang_code || 'a';
                    // Add built-in voices
                    (langConfig.voices || []).forEach(voiceName => {
                        voices.push({
                            id: voiceName,
                            name: `${voiceName} (${langLabel})`,
                            langCode: langCode,
                            isPrompt: false
                        });
                    });
                    // Add custom voices
                    (langConfig.custom_voices || []).forEach(cv => {
                        voices.push({
                            id: cv.code || cv.id,
                            name: `${cv.name || cv.code} (${langLabel}, custom)`,
                            langCode: langCode,
                            isPrompt: false
                        });
                    });
                });
            }
        }
    } catch (err) {
        console.error('Failed to load voices:', err);
    }

    // Store voice map globally for lookup during regeneration
    libraryVoiceMap = new Map();
    voices.forEach(v => libraryVoiceMap.set(v.id, v));

    body.querySelectorAll('.library-chunk-voice-select').forEach(select => {
        const chunkId = select.getAttribute('data-chunk-id');
        select.innerHTML = '<option value="">-- Keep current --</option>';
        voices.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.id;
            opt.textContent = v.name;
            select.appendChild(opt);
        });

        select.addEventListener('change', () => {
            const value = select.value;
            if (value) {
                const voiceData = libraryVoiceMap.get(value);
                if (isChatterbox) {
                    // For Chatterbox, store as audio_prompt_path (what the engine expects)
                    libraryChunkVoiceOverrides[chunkId] = { audio_prompt_path: value };
                } else {
                    // For Kokoro, include both voice name and lang_code
                    libraryChunkVoiceOverrides[chunkId] = { 
                        voice: value,
                        lang_code: voiceData?.langCode || 'a'
                    };
                }
            } else {
                delete libraryChunkVoiceOverrides[chunkId];
            }
        });
    });

    // Also populate bulk speaker voice selects
    body.querySelectorAll('.bulk-speaker-voice-select').forEach(select => {
        select.innerHTML = '<option value="">-- Select voice --</option>';
        voices.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.id;
            opt.textContent = v.name;
            select.appendChild(opt);
        });
    });

    // Store engine info for bulk regen
    body.dataset.isChatterbox = isChatterbox ? 'true' : 'false';
}

function updateBulkRegenButtonState(checkbox) {
    const row = checkbox.closest('.bulk-speaker-row');
    if (!row) return;

    const select = row.querySelector('.bulk-speaker-voice-select');
    const btn = row.querySelector('.bulk-speaker-regen');
    if (!select || !btn) return;

    // Enable button only if checkbox is checked AND a voice is selected
    const isChecked = checkbox.checked;
    const hasVoice = select.value !== '';
    btn.disabled = !(isChecked && hasVoice);
}

async function triggerBulkSpeakerRegen(jobId, speaker, chunks, engine, button) {
    const body = document.getElementById('chunk-review-modal-body');
    const row = button.closest('.bulk-speaker-row');
    const select = row?.querySelector('.bulk-speaker-voice-select');
    const voiceValue = select?.value;

    if (!voiceValue) {
        alert('Please select a voice first.');
        return;
    }

    // Get all chunks for this speaker
    const speakerChunks = chunks.filter(c => (c.speaker || 'default') === speaker);
    if (speakerChunks.length === 0) {
        alert('No chunks found for this speaker.');
        return;
    }

    const normalizedEngine = (engine || '').toLowerCase().replace(/[_-]/g, '');
    const isChatterbox = normalizedEngine.includes('chatterbox');

    // Build voice payload with lang_code for Kokoro
    const voiceData = libraryVoiceMap.get(voiceValue);
    const voicePayload = isChatterbox 
        ? { audio_prompt_path: voiceValue }
        : { voice: voiceValue, lang_code: voiceData?.langCode || 'a' };

    button.disabled = true;
    button.textContent = `Regenerating ${speakerChunks.length}...`;

    try {
        // First restore the job to review mode
        await fetch(`/api/library/${jobId}/restore-review`, { method: 'POST' });

        // Regenerate each chunk for this speaker
        for (const chunk of speakerChunks) {
            const chunkId = chunk.id;
            const chunkRow = document.querySelector(`.library-chunk-row[data-chunk-id="${chunkId}"]`);
            const textarea = chunkRow?.querySelector('.library-chunk-textarea');
            const text = textarea ? textarea.value.trim() : chunk.text;

            if (!text) continue;

            // Update the individual chunk's voice override
            libraryChunkVoiceOverrides[chunkId] = { ...voicePayload };

            const response = await fetch(`/api/jobs/${jobId}/review/regen`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    chunk_id: chunkId,
                    text: text,
                    voice: voicePayload,
                }),
            });

            const data = await response.json();
            if (data.success) {
                updateLibraryChunkStatus(chunkId, 'queued');
                startLibraryChunkRegenWatcher(jobId, chunkId);
            }
        }

        button.textContent = 'Queued!';
        setTimeout(() => {
            button.textContent = 'Regenerate All';
            button.disabled = false;
        }, 2000);

    } catch (error) {
        console.error('Bulk regen error:', error);
        alert(error.message || 'Failed to queue bulk regeneration');
        button.textContent = 'Regenerate All';
        button.disabled = false;
    }
}

async function triggerLibraryChunkRegen(jobId, chunkId, button) {
    const row = button.closest('.library-chunk-row');
    const textarea = row ? row.querySelector('.library-chunk-textarea') : null;
    const text = textarea ? textarea.value.trim() : '';

    if (!text) {
        alert('Chunk text cannot be empty.');
        return;
    }

    button.disabled = true;
    button.textContent = 'Queuing...';

    const voicePayload = libraryChunkVoiceOverrides[chunkId] || {};

    try {
        // First restore the job to review mode if not already
        await fetch(`/api/library/${jobId}/restore-review`, { method: 'POST' });

        const response = await fetch(`/api/jobs/${jobId}/review/regen`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chunk_id: chunkId,
                text: text,
                voice: voicePayload,
            }),
        });

        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to queue regeneration');
        }

        // Update UI to show queued status
        updateLibraryChunkStatus(chunkId, 'queued');
        startLibraryChunkRegenWatcher(jobId, chunkId);

    } catch (error) {
        console.error('Regen error:', error);
        alert(error.message || 'Failed to regenerate chunk');
    } finally {
        button.disabled = false;
        button.textContent = 'Regenerate';
    }
}

function updateLibraryChunkStatus(chunkId, status) {
    const row = document.querySelector(`.library-chunk-row[data-chunk-id="${chunkId}"]`);
    if (!row) return;

    const controls = row.querySelector('.library-chunk-controls');
    if (!controls) return;

    // Remove existing status badges
    controls.querySelectorAll('.review-chip').forEach(el => el.remove());

    let badge = '';
    if (status === 'queued') {
        badge = '<span class="review-chip warning">Queued</span>';
    } else if (status === 'running') {
        badge = '<span class="review-chip warning">Rendering</span>';
    } else if (status === 'failed') {
        badge = '<span class="review-chip error">Failed</span>';
    } else if (status === 'completed') {
        badge = '<span class="review-chip success">Updated</span>';
    }

    if (badge) {
        const playBtn = controls.querySelector('.library-chunk-play');
        if (playBtn) {
            playBtn.insertAdjacentHTML('afterend', badge);
        }
    }
}

function startLibraryChunkRegenWatcher(jobId, chunkId) {
    const key = `${jobId}:${chunkId}`;
    if (libraryChunkRegenWatchers[key]) {
        clearTimeout(libraryChunkRegenWatchers[key].timer);
    }

    const entry = { attempts: 0, timer: null };
    libraryChunkRegenWatchers[key] = entry;

    pollLibraryChunkStatus(jobId, chunkId, entry);
}

async function pollLibraryChunkStatus(jobId, chunkId, entry) {
    entry.attempts++;

    try {
        const response = await fetch(`/api/jobs/${jobId}/chunks`);
        const data = await response.json();

        if (data.success) {
            const chunks = data.chunks || [];
            const regenTasks = data.regen_tasks || {};
            const task = regenTasks[chunkId];
            const status = task ? task.status : null;

            updateLibraryChunkStatus(chunkId, status || 'completed');

            // Update audio URL if completed
            if (!status || status === 'completed' || status === 'failed') {
                const chunk = chunks.find(c => c.id === chunkId);
                if (chunk && chunk.file_url) {
                    const row = document.querySelector(`.library-chunk-row[data-chunk-id="${chunkId}"]`);
                    if (row) {
                        const playBtn = row.querySelector('.library-chunk-play');
                        const cacheToken = chunk.regenerated_at || Date.now().toString();
                        const newUrl = `${chunk.file_url}?t=${encodeURIComponent(cacheToken)}`;
                        if (playBtn) {
                            playBtn.setAttribute('data-audio-url', newUrl);
                            playBtn.disabled = false;
                        }
                        // Update voice label (API returns 'voice', not 'voice_label')
                        const voiceLabelEl = row.querySelector('.library-chunk-voice-label');
                        const newVoiceLabel = chunk.voice || chunk.voice_label;
                        if (voiceLabelEl && newVoiceLabel) {
                            voiceLabelEl.textContent = newVoiceLabel;
                        }
                    }
                }

                delete libraryChunkRegenWatchers[`${jobId}:${chunkId}`];
                return;
            }
        }
    } catch (err) {
        console.error('Poll error:', err);
    }

    if (entry.attempts >= LIBRARY_CHUNK_MAX_ATTEMPTS) {
        delete libraryChunkRegenWatchers[`${jobId}:${chunkId}`];
        return;
    }

    entry.timer = setTimeout(() => pollLibraryChunkStatus(jobId, chunkId, entry), LIBRARY_CHUNK_POLL_INTERVAL_MS);
}

async function recompileLibraryAudio() {
    const jobId = chunkReviewModalJobId;
    if (!jobId) return;

    const recompileBtn = document.getElementById('chunk-review-recompile-btn');
    if (recompileBtn) {
        recompileBtn.disabled = true;
        recompileBtn.textContent = 'Recompiling...';
    }

    try {
        // Finish review to recompile
        const response = await fetch(`/api/jobs/${jobId}/review/finish`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });

        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to recompile audio');
        }

        alert('Audio recompiled successfully!');
        closeChunkReviewModal();
        loadLibrary();

    } catch (error) {
        console.error('Recompile error:', error);
        alert(error.message || 'Failed to recompile audio');
    } finally {
        if (recompileBtn) {
            recompileBtn.disabled = false;
            recompileBtn.textContent = 'Recompile Audio';
        }
    }
}

// Clear all library items
async function clearLibrary() {
    if (!confirm('Are you sure you want to delete ALL audio files? This cannot be undone!')) {
        return;
    }
    
    try {
        const response = await fetch('/api/library/clear', {
            method: 'POST'
        });
        
        const data = await response.json();
        
        if (data.success) {
            loadLibrary(); // Reload library
        } else {
            alert('Error clearing library: ' + data.error);
        }
    } catch (error) {
        console.error('Error clearing library:', error);
        alert('Failed to clear library');
    }
}
