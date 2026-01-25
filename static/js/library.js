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

// Preview audio state
let previewAudio = null;
let previewButton = null;

// Voice map for looking up lang_code by voice id
let libraryVoiceMap = new Map();

// Locale code to human-readable language name mapping
const LIBRARY_LOCALE_NAMES = {
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

function getLibraryLanguageDisplayName(localeCode) {
    if (!localeCode) return '';
    return LIBRARY_LOCALE_NAMES[localeCode] || localeCode;
}

// Library voice dropdown filter state
let libraryVoiceFilters = {
    gender: 'all',
    language: 'all'
};

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
        'voxcpm_local': 'VoxCPM 1.5',
        'qwen3_custom': 'Qwen3-TTS (Custom Voice)',
        'qwen3_clone': 'Qwen3-TTS (Voice Clone)',
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
    stopPreviewAudio();

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
    const speakerInstructionMap = new Map();
    chunks.forEach(chunk => {
        const speaker = chunk.speaker || 'default';
        if (!speakerMap.has(speaker)) {
            speakerMap.set(speaker, { count: 0, voiceLabel: chunk.voice_label || chunk.voice || 'Default' });
        }
        speakerMap.get(speaker).count++;

        if (!speakerInstructionMap.has(speaker)) {
            const instruction = getChunkInstruction(chunk);
            if (instruction) {
                speakerInstructionMap.set(speaker, instruction);
            }
        }
    });

    // Build speaker section HTML - accordion layout
    const speakerRows = Array.from(speakerMap.entries()).map(([speaker, info]) => {
        const speakerInstruction = speakerInstructionMap.get(speaker) || '';
        return `
        <div class="bulk-speaker-card" data-speaker="${escapeHtml(speaker)}">
            <div class="bulk-speaker-summary" data-speaker="${escapeHtml(speaker)}">
                <input type="checkbox" class="bulk-speaker-checkbox" data-speaker="${escapeHtml(speaker)}">
                <span class="bulk-expand-toggle">▶</span>
                <span class="bulk-speaker-name">${escapeHtml(speaker)}</span>
                <span class="bulk-speaker-count">(${info.count} chunks)</span>
                <span class="bulk-speaker-voice">${escapeHtml(info.voiceLabel)}</span>
            </div>
            <div class="bulk-speaker-details collapsed" data-speaker="${escapeHtml(speaker)}">
                <div class="bulk-speaker-controls">
                    <div class="bulk-fx-section">
                        <div class="bulk-fx-title">Audio Effects</div>
                        <div class="bulk-fx-row">
                            <div class="bulk-fx-control">
                                <label>Speed</label>
                                <input type="range" class="bulk-speed-slider" data-speaker="${escapeHtml(speaker)}" min="0.5" max="2.0" step="0.05" value="1.0">
                                <span class="bulk-speed-value">1.0x</span>
                            </div>
                            <div class="bulk-fx-control">
                                <label>Pitch</label>
                                <input type="range" class="bulk-pitch-slider" data-speaker="${escapeHtml(speaker)}" min="-6" max="6" step="0.5" value="0">
                                <span class="bulk-pitch-value">0</span>
                            </div>
                            <button class="btn btn-sm btn-primary bulk-speaker-apply-fx" data-speaker="${escapeHtml(speaker)}" disabled>
                                Apply FX
                            </button>
                        </div>
                    </div>
                    <div class="bulk-regen-section">
                        <div class="bulk-regen-title">Regenerate</div>
                        <div class="bulk-regen-row">
                            <div class="bulk-regen-field">
                                <label>TTS Engine</label>
                                <select class="bulk-speaker-engine-select" data-speaker="${escapeHtml(speaker)}">
                                    <option value="">-- Same engine --</option>
                                </select>
                            </div>
                            <div class="bulk-regen-field">
                                <label>Voice</label>
                                <select class="bulk-speaker-voice-select" data-speaker="${escapeHtml(speaker)}">
                                    <option value="">-- Select voice --</option>
                                </select>
                            </div>
                            <button class="btn btn-sm btn-warning bulk-speaker-regen" data-speaker="${escapeHtml(speaker)}" disabled>
                                Regenerate All
                            </button>
                        </div>
                        <div class="bulk-prompt-filters" data-speaker="${escapeHtml(speaker)}" style="display: none; margin-top: 8px;">
                            <div class="bulk-regen-row" style="display: flex; gap: 10px; flex-wrap: wrap;">
                                <div class="bulk-regen-field">
                                    <label>Gender</label>
                                    <select class="bulk-voice-filter-gender" data-speaker="${escapeHtml(speaker)}" style="min-width: 140px;">
                                        <option value="all">All</option>
                                    </select>
                                </div>
                                <div class="bulk-regen-field">
                                    <label>Language</label>
                                    <select class="bulk-voice-filter-language" data-speaker="${escapeHtml(speaker)}" style="min-width: 160px;">
                                        <option value="all">All</option>
                                    </select>
                                </div>
                            </div>
                        </div>
                        <div class="bulk-qwen3-options" data-speaker="${escapeHtml(speaker)}" style="display: none;">
                            <div class="bulk-regen-row" style="margin-top: 8px;">
                                <div class="bulk-regen-field">
                                    <label>Language</label>
                                    <select class="bulk-qwen3-language" data-speaker="${escapeHtml(speaker)}">
                                        <option value="Auto">Auto</option>
                                    </select>
                                </div>
                                <div class="bulk-regen-field" style="flex: 2;">
                                    <label>Custom Instruction (optional)</label>
                                    <input type="text" class="bulk-qwen3-instruct" data-speaker="${escapeHtml(speaker)}" 
                                           value="${escapeHtml(speakerInstruction)}"
                                           placeholder="e.g., Speak with excitement" />
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
    }).join('');

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
            <span><strong>Original Engine:</strong> ${formatEngineName(engine)}</span>
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
    
    // Store original engine for reference
    body.dataset.originalEngine = engine;

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
    const currentVoiceLabel = voiceLabel ? `Current: ${voiceLabel}` : '-- Keep current --';
    const instruction = getChunkInstruction(chunk);
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
    
    // Truncate text for preview (first 80 chars)
    const textPreview = text.length > 80 ? text.substring(0, 80) + '...' : text;

    return `
        <div class="library-chunk-card" data-chunk-id="${chunkId}" data-idx="${idx}">
            <div class="library-chunk-summary" data-chunk-id="${chunkId}">
                <button class="btn btn-xs btn-secondary library-chunk-play" data-audio-url="${audioUrl}" ${audioUrl ? '' : 'disabled'}>
                    ▶
                </button>
                <span class="chunk-expand-toggle">▶</span>
                ${statusBadge}
                ${speakerTag}
                <span class="library-chunk-preview">${escapeHtml(textPreview)}</span>
            </div>
            <div class="library-chunk-details collapsed" data-chunk-id="${chunkId}">
                <div class="chunk-detail-section">
                    <div class="chunk-detail-label">Voice: <span class="library-chunk-voice-label">${escapeHtml(voiceLabel)}</span></div>
                    <div class="chunk-text-section">
                        <label>Text:</label>
                        <textarea class="library-chunk-textarea" data-chunk-id="${chunkId}" rows="3">${escapeHtml(text)}</textarea>
                    </div>
                </div>
                <div class="chunk-detail-section chunk-fx-section">
                    <div class="chunk-fx-title">Audio Effects</div>
                    <div class="chunk-fx-row">
                        <div class="chunk-fx-control">
                            <label>Speed</label>
                            <input type="range" class="chunk-speed-slider" data-chunk-id="${chunkId}" min="0.5" max="2.0" step="0.05" value="1.0">
                            <span class="chunk-speed-value">1.0x</span>
                        </div>
                        <div class="chunk-fx-control">
                            <label>Pitch</label>
                            <input type="range" class="chunk-pitch-slider" data-chunk-id="${chunkId}" min="-6" max="6" step="0.5" value="0">
                            <span class="chunk-pitch-value">0</span>
                        </div>
                        <button class="btn btn-sm btn-secondary library-chunk-preview-fx" data-chunk-id="${chunkId}" disabled>
                            ▶ Preview
                        </button>
                        <button class="btn btn-sm btn-primary library-chunk-apply-fx" data-chunk-id="${chunkId}" disabled>
                            Apply FX
                        </button>
                    </div>
                </div>
                <div class="chunk-detail-section chunk-regen-section">
                    <div class="chunk-regen-title">Regenerate</div>
                    <div class="chunk-regen-row">
                        <select class="library-chunk-engine-select" data-chunk-id="${chunkId}">
                            <option value="">-- Same engine --</option>
                        </select>
                        <select class="library-chunk-voice-select" data-chunk-id="${chunkId}" data-current-voice-label="${escapeHtml(voiceLabel)}">
                            <option value="">${escapeHtml(currentVoiceLabel)}</option>
                        </select>
                        <button class="btn btn-sm btn-warning library-chunk-regen" data-chunk-id="${chunkId}">
                            Regenerate
                        </button>
                    </div>
                    <div class="chunk-prompt-filters" data-chunk-id="${chunkId}" style="display: none; margin-top: 8px;">
                        <div style="display: grid; grid-template-columns: repeat(2, minmax(140px, 1fr)); gap: 10px; align-items: end;">
                            <label style="display: flex; flex-direction: column; gap: 4px;">
                                <span>Gender</span>
                                <select class="chunk-voice-filter-gender" data-chunk-id="${chunkId}">
                                    <option value="all">All</option>
                                </select>
                            </label>
                            <label style="display: flex; flex-direction: column; gap: 4px;">
                                <span>Language</span>
                                <select class="chunk-voice-filter-language" data-chunk-id="${chunkId}">
                                    <option value="all">All</option>
                                </select>
                            </label>
                        </div>
                    </div>
                    <div class="chunk-qwen3-options" data-chunk-id="${chunkId}" style="display: none;">
                        <div class="chunk-regen-row" style="margin-top: 8px;">
                            <select class="chunk-qwen3-language" data-chunk-id="${chunkId}">
                                <option value="Auto">Auto</option>
                            </select>
                            <input type="text" class="chunk-qwen3-instruct" data-chunk-id="${chunkId}" 
                                   value="${escapeHtml(instruction)}"
                                   placeholder="Custom instruction (optional)" style="flex: 2;" />
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;
}

function getChunkInstruction(chunk) {
    if (!chunk || typeof chunk !== 'object') return '';
    if (chunk.emotion) return chunk.emotion;
    const extra = chunk.voice_assignment?.extra;
    if (extra && extra.instruct) return extra.instruct;
    return '';
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
    stopPreviewAudio();

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
        btn.textContent = '▶';
        btn.classList.remove('playing');
    }
}

function wireChunkReviewEvents(jobId, chunks, engine) {
    const body = document.getElementById('chunk-review-modal-body');
    if (!body) return;

    // Chunk card expand/collapse toggle
    body.querySelectorAll('.library-chunk-summary').forEach(summary => {
        summary.addEventListener('click', (e) => {
            // Don't toggle if clicking the play button
            if (e.target.closest('.library-chunk-play')) return;
            
            const chunkId = summary.getAttribute('data-chunk-id');
            const details = body.querySelector(`.library-chunk-details[data-chunk-id="${chunkId}"]`);
            const toggle = summary.querySelector('.chunk-expand-toggle');
            
            if (details) {
                const isCollapsed = details.classList.contains('collapsed');
                if (isCollapsed) {
                    details.classList.remove('collapsed');
                    if (toggle) toggle.textContent = '▼';
                } else {
                    details.classList.add('collapsed');
                    if (toggle) toggle.textContent = '▶';
                }
            }
        });
    });

    // Play/Stop buttons
    body.querySelectorAll('.library-chunk-play').forEach(btn => {
        btn.addEventListener('click', (e) => {
            e.stopPropagation(); // Prevent triggering expand/collapse
            handleLibraryChunkPlayClick(btn);
        });
    });

    // Populate voice selects
    populateLibraryVoiceSelects(engine);

    // Regenerate buttons for individual chunks
    body.querySelectorAll('.library-chunk-regen').forEach(btn => {
        btn.addEventListener('click', () => {
            const chunkId = btn.getAttribute('data-chunk-id');
            triggerLibraryChunkRegen(jobId, chunkId, btn);
        });
    });

    // Bulk speaker accordion toggle
    body.querySelectorAll('.bulk-speaker-summary').forEach(summary => {
        summary.addEventListener('click', (e) => {
            // Don't toggle if clicking the checkbox
            if (e.target.closest('.bulk-speaker-checkbox')) return;
            
            const speaker = summary.getAttribute('data-speaker');
            const details = body.querySelector(`.bulk-speaker-details[data-speaker="${speaker}"]`);
            const toggle = summary.querySelector('.bulk-expand-toggle');
            
            if (details) {
                const isCollapsed = details.classList.contains('collapsed');
                if (isCollapsed) {
                    details.classList.remove('collapsed');
                    if (toggle) toggle.textContent = '▼';
                } else {
                    details.classList.add('collapsed');
                    if (toggle) toggle.textContent = '▶';
                }
            }
        });
    });

    // Bulk speaker checkbox and voice select handlers
    body.querySelectorAll('.bulk-speaker-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', (e) => {
            e.stopPropagation(); // Prevent triggering accordion
            updateBulkRegenButtonState(checkbox);
        });
    });

    body.querySelectorAll('.bulk-speaker-voice-select').forEach(select => {
        select.addEventListener('change', () => {
            const card = select.closest('.bulk-speaker-card');
            const checkbox = card?.querySelector('.bulk-speaker-checkbox');
            if (checkbox) updateBulkRegenButtonState(checkbox);
        });
    });

    // Bulk regenerate buttons
    body.querySelectorAll('.bulk-speaker-regen').forEach(btn => {
        btn.addEventListener('click', () => {
            const speaker = btn.getAttribute('data-speaker');
            // Use per-speaker engine dropdown or original engine
            const card = btn.closest('.bulk-speaker-card');
            const engineSelect = card?.querySelector('.bulk-speaker-engine-select');
            const engineOverride = engineSelect?.value || engine;
            triggerBulkSpeakerRegen(jobId, speaker, chunks, engineOverride, btn);
        });
    });

    // Individual chunk FX sliders
    body.querySelectorAll('.chunk-speed-slider').forEach(slider => {
        slider.addEventListener('input', () => {
            const valueSpan = slider.parentElement.querySelector('.chunk-speed-value');
            if (valueSpan) valueSpan.textContent = `${parseFloat(slider.value).toFixed(2)}x`;
            updateChunkApplyFxButtonState(slider);
        });
    });

    body.querySelectorAll('.chunk-pitch-slider').forEach(slider => {
        slider.addEventListener('input', () => {
            const valueSpan = slider.parentElement.querySelector('.chunk-pitch-value');
            if (valueSpan) valueSpan.textContent = parseFloat(slider.value).toFixed(1);
            updateChunkApplyFxButtonState(slider);
        });
    });

    // Individual chunk Preview FX buttons
    body.querySelectorAll('.library-chunk-preview-fx').forEach(btn => {
        btn.addEventListener('click', () => {
            const chunkId = btn.getAttribute('data-chunk-id');
            triggerChunkPreviewFx(jobId, chunkId, btn);
        });
    });

    // Individual chunk Apply FX buttons
    body.querySelectorAll('.library-chunk-apply-fx').forEach(btn => {
        btn.addEventListener('click', () => {
            const chunkId = btn.getAttribute('data-chunk-id');
            triggerChunkApplyFx(jobId, chunkId, btn);
        });
    });

    // Bulk speaker FX sliders
    body.querySelectorAll('.bulk-speed-slider').forEach(slider => {
        slider.addEventListener('input', () => {
            const valueSpan = slider.parentElement.querySelector('.bulk-speed-value');
            if (valueSpan) valueSpan.textContent = `${parseFloat(slider.value).toFixed(2)}x`;
            updateBulkApplyFxButtonState(slider);
        });
    });

    body.querySelectorAll('.bulk-pitch-slider').forEach(slider => {
        slider.addEventListener('input', () => {
            const valueSpan = slider.parentElement.querySelector('.bulk-pitch-value');
            if (valueSpan) valueSpan.textContent = parseFloat(slider.value).toFixed(1);
            updateBulkApplyFxButtonState(slider);
        });
    });

    // Bulk speaker Apply FX buttons
    body.querySelectorAll('.bulk-speaker-apply-fx').forEach(btn => {
        btn.addEventListener('click', () => {
            const speaker = btn.getAttribute('data-speaker');
            triggerBulkSpeakerApplyFx(jobId, speaker, chunks, btn);
        });
    });
}

async function initLibraryVoiceFilters(engine) {
    const normalizedEngine = (engine || '').toLowerCase();
    const usesPrompts = normalizedEngine.includes('chatterbox')
        || normalizedEngine.includes('voxcpm')
        || (normalizedEngine.includes('qwen3') && normalizedEngine.includes('clone'));
    if (!usesPrompts) return;
    
    const genderFilter = document.getElementById('library-voice-filter-gender');
    const languageFilter = document.getElementById('library-voice-filter-language');
    
    if (!genderFilter || !languageFilter) return;
    
    // Reset filter state
    libraryVoiceFilters = { gender: 'all', language: 'all' };
    
    // Fetch voice prompts to populate filter options
    try {
        const response = await fetch('/api/voice-prompts');
        const data = await response.json();
        if (data.success && data.prompts) {
            const genders = new Set();
            const languages = new Set();
            
            data.prompts.forEach(p => {
                if (p.gender) genders.add(p.gender);
                if (p.language) languages.add(p.language);
            });
            
            // Populate gender filter
            genderFilter.innerHTML = '<option value="all">All Genders</option>';
            [...genders].sort().forEach(g => {
                const opt = document.createElement('option');
                opt.value = g.toLowerCase();
                opt.textContent = g;
                genderFilter.appendChild(opt);
            });
            
            // Populate language filter
            languageFilter.innerHTML = '<option value="all">All Languages</option>';
            [...languages].sort((a, b) => 
                getLibraryLanguageDisplayName(a).localeCompare(getLibraryLanguageDisplayName(b))
            ).forEach(lang => {
                const opt = document.createElement('option');
                opt.value = lang;
                opt.textContent = getLibraryLanguageDisplayName(lang);
                languageFilter.appendChild(opt);
            });
        }
    } catch (err) {
        console.error('Failed to load voice prompts for filters:', err);
    }
    
    // Wire up filter change events
    genderFilter.addEventListener('change', () => {
        libraryVoiceFilters.gender = genderFilter.value;
        populateLibraryVoiceSelects(engine);
    });
    
    languageFilter.addEventListener('change', () => {
        libraryVoiceFilters.language = languageFilter.value;
        populateLibraryVoiceSelects(engine);
    });
}

async function populateLibraryVoiceSelects(engine) {
    const body = document.getElementById('chunk-review-modal-body');
    if (!body) return;

    const chunks = chunkReviewModalData?.chunks || [];

    const normalizedEngine = (engine || '').toLowerCase().replace(/[_-]/g, '');
    const isChatterbox = normalizedEngine.includes('chatterbox');
    const isVoxCPM = normalizedEngine.includes('voxcpm');
    const isQwen = normalizedEngine.includes('qwen3');
    const isQwenClone = normalizedEngine.includes('qwen3') && normalizedEngine.includes('clone');
    const usesVoicePrompts = isChatterbox || isVoxCPM || isQwenClone;

    let voices = [];
    try {
        if (usesVoicePrompts) {
            // Chatterbox and VoxCPM use voice prompts
            const response = await fetch('/api/voice-prompts');
            const data = await response.json();
            if (data.success) {
                voices = (data.prompts || []).map(p => ({
                    id: p.name,  // API returns 'name' as the filename
                    name: p.display || p.name.replace('.wav', ''),
                    duration: p.duration_seconds,
                    gender: p.gender,
                    language: p.language,
                    transcript: p.transcript,
                    isPrompt: true
                }));
                
                // Apply filters
                if (libraryVoiceFilters.gender && libraryVoiceFilters.gender !== 'all') {
                    voices = voices.filter(v => 
                        (v.gender || '').toLowerCase() === libraryVoiceFilters.gender.toLowerCase()
                    );
                }
                if (libraryVoiceFilters.language && libraryVoiceFilters.language !== 'all') {
                    voices = voices.filter(v => v.language === libraryVoiceFilters.language);
                }
            }
        } else if (isQwen) {
            // Qwen3 uses /api/qwen3/metadata for speakers
            const response = await fetch('/api/qwen3/metadata');
            const data = await response.json();
            if (data.success && data.speakers) {
                voices = data.speakers.map(speaker => ({
                    id: speaker,
                    name: speaker,
                    isQwen: true
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

    // Helper to populate a single chunk voice select based on engine
    // Minimum duration requirements per engine (in seconds)
    const ENGINE_MIN_DURATION = {
        'chatterbox': 5.0,
        'chatterboxturbolocal': 5.0,
        'chatterboxturborepl': 5.0,
        'voxcpmlocal': 0,  // VoxCPM accepts any duration
    };
    
    function getMinDuration(engineName) {
        const normalized = (engineName || '').toLowerCase().replace(/[_-]/g, '');
        for (const [key, val] of Object.entries(ENGINE_MIN_DURATION)) {
            if (normalized.includes(key)) return val;
        }
        return 0;
    }

    function getPromptFilters(container, genderSelector, languageSelector) {
        if (!container) {
            return { gender: 'all', language: 'all' };
        }
        const genderSelect = container.querySelector(genderSelector);
        const languageSelect = container.querySelector(languageSelector);
        return {
            gender: genderSelect?.value || 'all',
            language: languageSelect?.value || 'all'
        };
    }

    async function populatePromptFilterOptions(genderSelect, languageSelect) {
        if (!genderSelect || !languageSelect) return;
        try {
            const response = await fetch('/api/voice-prompts');
            const data = await response.json();
            if (!data.success || !data.prompts) return;
            const genders = new Set();
            const languages = new Set();
            data.prompts.forEach(prompt => {
                if (prompt.gender) genders.add(prompt.gender);
                if (prompt.language) languages.add(prompt.language);
            });
            const currentGender = genderSelect.value || 'all';
            const currentLanguage = languageSelect.value || 'all';
            genderSelect.innerHTML = '<option value="all">All</option>';
            [...genders].sort().forEach(gender => {
                const opt = document.createElement('option');
                opt.value = gender.toLowerCase();
                opt.textContent = gender;
                genderSelect.appendChild(opt);
            });
            languageSelect.innerHTML = '<option value="all">All</option>';
            [...languages].sort((a, b) =>
                getLibraryLanguageDisplayName(a).localeCompare(getLibraryLanguageDisplayName(b))
            ).forEach(language => {
                const opt = document.createElement('option');
                opt.value = language;
                opt.textContent = getLibraryLanguageDisplayName(language);
                languageSelect.appendChild(opt);
            });
            genderSelect.value = currentGender;
            languageSelect.value = currentLanguage;
        } catch (err) {
            console.error('Failed to load prompt filter options:', err);
        }
    }

    async function populateChunkVoiceSelect(select, chunkId, engineName, filters = null, currentLabel = '') {
        const usesPrompts = engineName.includes('chatterbox')
            || engineName.includes('voxcpm')
            || (engineName.includes('qwen3') && engineName.includes('clone'));
        const isQwenEngine = engineName.includes('qwen3');
        const minDuration = getMinDuration(engineName);
        const activeFilters = filters || libraryVoiceFilters;
        let chunkVoices = [];
        
        try {
            if (usesPrompts) {
                const response = await fetch('/api/voice-prompts');
                const data = await response.json();
                if (data.success && data.prompts) {
                    chunkVoices = data.prompts.map(p => ({
                        id: p.path || p.name,
                        name: p.display || p.name,
                        duration: p.duration_seconds,
                        gender: p.gender,
                        language: p.language,
                        isPrompt: true
                    }));
                }
            } else if (isQwenEngine) {
                const response = await fetch('/api/qwen3/metadata');
                const data = await response.json();
                if (data.success && data.speakers) {
                    chunkVoices = data.speakers.map(speaker => ({
                        id: speaker,
                        name: speaker,
                        isQwen: true
                    }));
                }
            } else {
                const response = await fetch('/api/voices');
                const data = await response.json();
                if (data.success && data.voices) {
                    Object.entries(data.voices).forEach(([langKey, langConfig]) => {
                        const langLabel = langConfig.language || langKey;
                        const langCode = langConfig.lang_code || 'a';
                        (langConfig.voices || []).forEach(voiceName => {
                            chunkVoices.push({
                                id: voiceName,
                                name: `${voiceName} (${langLabel})`,
                                langCode: langCode,
                                isPrompt: false
                            });
                        });
                        (langConfig.custom_voices || []).forEach(cv => {
                            chunkVoices.push({
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
            console.error('Failed to load voices for chunk:', err);
        }
        
        // Apply filters for prompt-based voices
        if (usesPrompts) {
            if (activeFilters.gender && activeFilters.gender !== 'all') {
                chunkVoices = chunkVoices.filter(v => 
                    (v.gender || '').toLowerCase() === activeFilters.gender.toLowerCase()
                );
            }
            if (activeFilters.language && activeFilters.language !== 'all') {
                chunkVoices = chunkVoices.filter(v => v.language === activeFilters.language);
            }
        }
        
        const defaultLabel = currentLabel ? `Current: ${currentLabel}` : '-- Keep current --';
        select.innerHTML = `<option value="">${defaultLabel}</option>`;
        chunkVoices.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.id;
            const durationLabel = v.duration != null ? ` · ${v.duration.toFixed(1)}s` : '';
            
            // Build label with gender and language for prompt voices
            let displayName = v.name;
            if (v.isPrompt && (v.gender || v.language)) {
                const gender = v.gender ? ` [${v.gender.charAt(0).toUpperCase()}]` : '';
                const lang = v.language ? ` ${getLibraryLanguageDisplayName(v.language)}` : '';
                displayName = `${v.name} ·${gender}${lang}`;
            }
            
            opt.textContent = `${displayName}${durationLabel}`;
            opt.dataset.gender = v.gender || '';
            opt.dataset.language = v.language || '';
            
            // Disable if duration is too short for this engine
            if (minDuration > 0 && v.duration != null && v.duration < minDuration) {
                opt.disabled = true;
                opt.style.color = '#ff6b6b';
                opt.textContent = `${displayName}${durationLabel} (too short)`;
            }
            
            select.appendChild(opt);
        });
        
        // Clear any previous voice override for this chunk
        delete libraryChunkVoiceOverrides[chunkId];
    }

    // Helper to populate bulk speaker voice select based on engine
    async function populateBulkVoiceSelect(select, speaker, engineName, filters = null) {
        const usesPrompts = engineName.includes('chatterbox')
            || engineName.includes('voxcpm')
            || (engineName.includes('qwen3') && engineName.includes('clone'));
        const isQwenEngine = engineName.includes('qwen3');
        const minDuration = getMinDuration(engineName);
        const activeFilters = filters || libraryVoiceFilters;
        let bulkVoices = [];
        
        try {
            if (usesPrompts) {
                const response = await fetch('/api/voice-prompts');
                const data = await response.json();
                if (data.success && data.prompts) {
                    bulkVoices = data.prompts.map(p => ({
                        id: p.path || p.name,
                        name: p.display || p.name,
                        duration: p.duration_seconds,
                        gender: p.gender,
                        language: p.language,
                        isPrompt: true
                    }));
                }
            } else if (isQwenEngine) {
                const response = await fetch('/api/qwen3/metadata');
                const data = await response.json();
                if (data.success && data.speakers) {
                    bulkVoices = data.speakers.map(speaker => ({
                        id: speaker,
                        name: speaker,
                        isQwen: true
                    }));
                }
            } else {
                const response = await fetch('/api/voices');
                const data = await response.json();
                if (data.success && data.voices) {
                    Object.entries(data.voices).forEach(([langKey, langConfig]) => {
                        const langLabel = langConfig.language || langKey;
                        const langCode = langConfig.lang_code || 'a';
                        (langConfig.voices || []).forEach(voiceName => {
                            bulkVoices.push({
                                id: voiceName,
                                name: `${voiceName} (${langLabel})`,
                                langCode: langCode,
                                isPrompt: false
                            });
                        });
                        (langConfig.custom_voices || []).forEach(cv => {
                            bulkVoices.push({
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
            console.error('Failed to load voices for bulk speaker:', err);
        }
        
        // Apply filters for prompt-based voices
        if (usesPrompts) {
            if (activeFilters.gender && activeFilters.gender !== 'all') {
                bulkVoices = bulkVoices.filter(v => 
                    (v.gender || '').toLowerCase() === activeFilters.gender.toLowerCase()
                );
            }
            if (activeFilters.language && activeFilters.language !== 'all') {
                bulkVoices = bulkVoices.filter(v => v.language === activeFilters.language);
            }
        }
        
        select.innerHTML = '<option value="">-- Select voice --</option>';
        bulkVoices.forEach(v => {
            const opt = document.createElement('option');
            opt.value = v.id;
            const durationLabel = v.duration != null ? ` · ${v.duration.toFixed(1)}s` : '';
            
            // Build label with gender and language for prompt voices
            let displayName = v.name;
            if (v.isPrompt && (v.gender || v.language)) {
                const gender = v.gender ? ` [${v.gender.charAt(0).toUpperCase()}]` : '';
                const lang = v.language ? ` ${getLibraryLanguageDisplayName(v.language)}` : '';
                displayName = `${v.name} ·${gender}${lang}`;
            }
            
            opt.textContent = `${displayName}${durationLabel}`;
            opt.dataset.gender = v.gender || '';
            opt.dataset.language = v.language || '';
            
            // Disable if duration is too short for this engine
            if (minDuration > 0 && v.duration != null && v.duration < minDuration) {
                opt.disabled = true;
                opt.style.color = '#ff6b6b';
                opt.textContent = `${displayName}${durationLabel} (too short)`;
            }
            
            select.appendChild(opt);
        });
    }

    const chunkById = new Map(chunks.map(chunk => [chunk.id, chunk]));

    // Populate chunk engine selects
    body.querySelectorAll('.library-chunk-engine-select').forEach(select => {
        const chunkId = select.getAttribute('data-chunk-id');
        const chunk = chunkById.get(chunkId);
        const currentEngine = chunk?.engine || engine;
        const currentEngineLabel = currentEngine ? `Current: ${formatEngineName(currentEngine)}` : '-- Same engine --';
        const normalizedCurrentEngine = (currentEngine || '').toLowerCase();
        select.innerHTML = `
            <option value="">${currentEngineLabel}</option>
            <option value="kokoro">Kokoro</option>
            <option value="chatterbox_turbo_local">Chatterbox</option>
            <option value="chatterbox_turbo_api">Chatterbox API</option>
            <option value="voxcpm_local">VoxCPM 1.5</option>
            <option value="qwen3_custom">Qwen3-TTS</option>
            <option value="qwen3_clone">Qwen3-TTS · Voice Clone</option>
        `;
        if (normalizedCurrentEngine) {
            Array.from(select.options).forEach(option => {
                if (option.value && normalizedCurrentEngine.includes(option.value.replace(/[_-]/g, ''))) {
                    option.textContent = `Current: ${option.textContent}`;
                }
            });
        }

        const regenSection = select.closest('.chunk-regen-section');
        const voiceSelect = regenSection?.querySelector('.library-chunk-voice-select');
        const qwen3Options = regenSection?.querySelector('.chunk-qwen3-options');
        const promptFilters = regenSection?.querySelector('.chunk-prompt-filters');
        const genderFilter = regenSection?.querySelector('.chunk-voice-filter-gender');
        const languageFilter = regenSection?.querySelector('.chunk-voice-filter-language');
        if (voiceSelect) {
            const currentVoiceLabel = voiceSelect.dataset.currentVoiceLabel || '';
            const filters = getPromptFilters(regenSection, '.chunk-voice-filter-gender', '.chunk-voice-filter-language');
            populateChunkVoiceSelect(voiceSelect, chunkId, currentEngine, filters, currentVoiceLabel);
        }
        const normalizedEngineValue = (currentEngine || '').toLowerCase();
        const isQwen = normalizedEngineValue.includes('qwen3') && !normalizedEngineValue.includes('clone');
        const usesPrompts = normalizedEngineValue.includes('chatterbox')
            || normalizedEngineValue.includes('voxcpm')
            || (normalizedEngineValue.includes('qwen3') && normalizedEngineValue.includes('clone'));
        if (promptFilters) {
            promptFilters.style.display = usesPrompts ? 'block' : 'none';
            if (usesPrompts) {
                populatePromptFilterOptions(genderFilter, languageFilter);
            }
        }
        if (qwen3Options) {
            qwen3Options.style.display = isQwen ? 'block' : 'none';
            if (isQwen) {
                const langSelect = qwen3Options.querySelector('.chunk-qwen3-language');
                if (langSelect && langSelect.options.length <= 1) {
                    populateQwen3LanguageSelect(langSelect);
                }
            }
        }
        if (genderFilter) {
            genderFilter.addEventListener('change', () => {
                if (!voiceSelect) return;
                const currentVoiceLabel = voiceSelect.dataset.currentVoiceLabel || '';
                const filters = getPromptFilters(regenSection, '.chunk-voice-filter-gender', '.chunk-voice-filter-language');
                populateChunkVoiceSelect(voiceSelect, chunkId, currentEngine, filters, currentVoiceLabel);
            });
        }
        if (languageFilter) {
            languageFilter.addEventListener('change', () => {
                if (!voiceSelect) return;
                const currentVoiceLabel = voiceSelect.dataset.currentVoiceLabel || '';
                const filters = getPromptFilters(regenSection, '.chunk-voice-filter-gender', '.chunk-voice-filter-language');
                populateChunkVoiceSelect(voiceSelect, chunkId, currentEngine, filters, currentVoiceLabel);
            });
        }

        // When engine changes, repopulate the voice dropdown for this chunk and show/hide Qwen3 options
        select.addEventListener('change', async () => {
            const selectedEngine = select.value || currentEngine || engine;
            const regenSection = select.closest('.chunk-regen-section');
            const voiceSelect = regenSection?.querySelector('.library-chunk-voice-select');
            const qwen3Options = regenSection?.querySelector('.chunk-qwen3-options');
            const promptFilters = regenSection?.querySelector('.chunk-prompt-filters');
            const genderFilter = regenSection?.querySelector('.chunk-voice-filter-gender');
            const languageFilter = regenSection?.querySelector('.chunk-voice-filter-language');
            
            if (voiceSelect) {
                const currentVoiceLabel = voiceSelect.dataset.currentVoiceLabel || '';
                const filters = getPromptFilters(regenSection, '.chunk-voice-filter-gender', '.chunk-voice-filter-language');
                await populateChunkVoiceSelect(voiceSelect, chunkId, selectedEngine, filters, currentVoiceLabel);
            }
            
            // Show/hide Qwen3 options based on engine
            const normalizedSelectedEngine = selectedEngine.toLowerCase();
            const isQwen = normalizedSelectedEngine.includes('qwen3')
                && !normalizedSelectedEngine.includes('clone');
            const usesPrompts = normalizedSelectedEngine.includes('chatterbox')
                || normalizedSelectedEngine.includes('voxcpm')
                || (normalizedSelectedEngine.includes('qwen3') && normalizedSelectedEngine.includes('clone'));
            if (promptFilters) {
                promptFilters.style.display = usesPrompts ? 'block' : 'none';
                if (usesPrompts) {
                    await populatePromptFilterOptions(genderFilter, languageFilter);
                }
            }
            if (qwen3Options) {
                qwen3Options.style.display = isQwen ? 'block' : 'none';
                // Populate language dropdown if Qwen3 selected
                if (isQwen) {
                    const langSelect = qwen3Options.querySelector('.chunk-qwen3-language');
                    if (langSelect && langSelect.options.length <= 1) {
                        await populateQwen3LanguageSelect(langSelect);
                    }
                }
            }
        });
    });

    // Populate bulk speaker engine selects
    body.querySelectorAll('.bulk-speaker-engine-select').forEach(select => {
        const speaker = select.getAttribute('data-speaker');
        select.innerHTML = `
            <option value="">-- Same engine --</option>
            <option value="kokoro">Kokoro</option>
            <option value="chatterbox_turbo_local">Chatterbox</option>
            <option value="chatterbox_turbo_api">Chatterbox API</option>
            <option value="voxcpm_local">VoxCPM 1.5</option>
            <option value="qwen3_custom">Qwen3-TTS</option>
            <option value="qwen3_clone">Qwen3-TTS · Voice Clone</option>
        `;
        
        // When engine changes, repopulate the voice dropdown for this speaker and show/hide Qwen3 options
        select.addEventListener('change', async () => {
            const selectedEngine = select.value || engine;
            const regenSection = select.closest('.bulk-regen-section');
            const voiceSelect = regenSection?.querySelector('.bulk-speaker-voice-select');
            const qwen3Options = regenSection?.querySelector('.bulk-qwen3-options');
            const promptFilters = regenSection?.querySelector('.bulk-prompt-filters');
            const genderFilter = regenSection?.querySelector('.bulk-voice-filter-gender');
            const languageFilter = regenSection?.querySelector('.bulk-voice-filter-language');
            
            if (voiceSelect) {
                const filters = getPromptFilters(regenSection, '.bulk-voice-filter-gender', '.bulk-voice-filter-language');
                await populateBulkVoiceSelect(voiceSelect, speaker, selectedEngine, filters);
            }
            
            // Show/hide Qwen3 options based on engine
            const normalizedSelectedEngine = selectedEngine.toLowerCase();
            const isQwen = normalizedSelectedEngine.includes('qwen3')
                && !normalizedSelectedEngine.includes('clone');
            const usesPrompts = normalizedSelectedEngine.includes('chatterbox')
                || normalizedSelectedEngine.includes('voxcpm')
                || (normalizedSelectedEngine.includes('qwen3') && normalizedSelectedEngine.includes('clone'));
            if (promptFilters) {
                promptFilters.style.display = usesPrompts ? 'block' : 'none';
                if (usesPrompts) {
                    await populatePromptFilterOptions(genderFilter, languageFilter);
                }
            }
            if (qwen3Options) {
                qwen3Options.style.display = isQwen ? 'block' : 'none';
                // Populate language dropdown if Qwen3 selected
                if (isQwen) {
                    const langSelect = qwen3Options.querySelector('.bulk-qwen3-language');
                    if (langSelect && langSelect.options.length <= 1) {
                        await populateQwen3LanguageSelect(langSelect);
                    }
                }
            }
        });
    });

    // Also populate bulk speaker voice selects
    body.querySelectorAll('.bulk-speaker-voice-select').forEach(select => {
        select.innerHTML = '<option value="">-- Select voice --</option>';
    });

    // Initialize prompt filters and voice lists for bulk speakers
    body.querySelectorAll('.bulk-speaker-card').forEach(card => {
        const engineSelect = card.querySelector('.bulk-speaker-engine-select');
        const voiceSelect = card.querySelector('.bulk-speaker-voice-select');
        const promptFilters = card.querySelector('.bulk-prompt-filters');
        const genderFilter = card.querySelector('.bulk-voice-filter-gender');
        const languageFilter = card.querySelector('.bulk-voice-filter-language');
        if (!engineSelect || !voiceSelect) return;
        const selectedEngine = engineSelect.value || engine;
        const normalizedEngine = selectedEngine.toLowerCase();
        const usesPrompts = normalizedEngine.includes('chatterbox')
            || normalizedEngine.includes('voxcpm')
            || (normalizedEngine.includes('qwen3') && normalizedEngine.includes('clone'));
        if (promptFilters) {
            promptFilters.style.display = usesPrompts ? 'block' : 'none';
            if (usesPrompts) {
                populatePromptFilterOptions(genderFilter, languageFilter);
                const filters = getPromptFilters(card, '.bulk-voice-filter-gender', '.bulk-voice-filter-language');
                populateBulkVoiceSelect(voiceSelect, card.dataset.speaker || '', selectedEngine, filters);
            }
        }

        if (genderFilter) {
            genderFilter.addEventListener('change', async () => {
                const currentEngine = engineSelect.value || engine;
                const filters = getPromptFilters(card, '.bulk-voice-filter-gender', '.bulk-voice-filter-language');
                await populateBulkVoiceSelect(voiceSelect, card.dataset.speaker || '', currentEngine, filters);
            });
        }
        if (languageFilter) {
            languageFilter.addEventListener('change', async () => {
                const currentEngine = engineSelect.value || engine;
                const filters = getPromptFilters(card, '.bulk-voice-filter-gender', '.bulk-voice-filter-language');
                await populateBulkVoiceSelect(voiceSelect, card.dataset.speaker || '', currentEngine, filters);
            });
        }
    });

    // Store engine info for bulk regen (usesVoicePrompts covers both Chatterbox and VoxCPM)
    body.dataset.usesVoicePrompts = usesVoicePrompts ? 'true' : 'false';
}

// Helper to populate Qwen3 language dropdown
async function populateQwen3LanguageSelect(select) {
    try {
        const response = await fetch('/api/qwen3/metadata');
        const data = await response.json();
        if (data.success && data.languages) {
            data.languages.forEach(lang => {
                const opt = document.createElement('option');
                opt.value = lang;
                opt.textContent = lang;
                select.appendChild(opt);
            });
        }
    } catch (err) {
        console.error('Failed to load Qwen3 languages:', err);
    }
}

function updateBulkRegenButtonState(checkbox) {
    const card = checkbox.closest('.bulk-speaker-card');
    if (!card) return;

    const select = card.querySelector('.bulk-speaker-voice-select');
    const btn = card.querySelector('.bulk-speaker-regen');
    if (!select || !btn) return;

    // Enable button only if checkbox is checked AND a voice is selected
    const isChecked = checkbox.checked;
    const hasVoice = select.value !== '';
    btn.disabled = !(isChecked && hasVoice);
}

async function triggerBulkSpeakerRegen(jobId, speaker, chunks, engine, button) {
    const body = document.getElementById('chunk-review-modal-body');
    const card = button.closest('.bulk-speaker-card');
    const select = card?.querySelector('.bulk-speaker-voice-select');
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
    const isVoxCPM = normalizedEngine.includes('voxcpm');
    const isQwenEngine = normalizedEngine.includes('qwen3');
    const isQwenClone = normalizedEngine.includes('qwen3') && normalizedEngine.includes('clone');
    const usesVoicePrompts = isChatterbox || isVoxCPM || isQwenClone;

    // Build voice payload based on engine type
    const voiceData = libraryVoiceMap.get(voiceValue);
    let voicePayload;
    if (usesVoicePrompts) {
        const promptEntry = libraryVoiceMap.get(voiceValue);
        voicePayload = {
            audio_prompt_path: voiceValue,
            ...(promptEntry?.transcript ? { extra: { prompt_text: promptEntry.transcript } } : {})
        };
    } else if (isQwenEngine) {
        // Get Qwen3 language and instruction from the bulk options
        const qwen3Options = card?.querySelector('.bulk-qwen3-options');
        const langSelect = qwen3Options?.querySelector('.bulk-qwen3-language');
        const instructInput = qwen3Options?.querySelector('.bulk-qwen3-instruct');
        const language = langSelect?.value || 'Auto';
        let instruct = instructInput?.value?.trim() || '';
        if (!instruct) {
            const originalInstruction = speakerChunks
                .map(chunk => getChunkInstruction(chunk))
                .find(Boolean) || '';
            instruct = originalInstruction;
        }
        voicePayload = { 
            voice: voiceValue, 
            extra: { 
                language: language,
                ...(instruct && { instruct: instruct })
            } 
        };
    } else {
        voicePayload = { voice: voiceValue, lang_code: voiceData?.langCode || 'a' };
    }

    button.disabled = true;
    button.textContent = `Regenerating ${speakerChunks.length}...`;

    try {
        // First restore the job to review mode
        await fetch(`/api/library/${jobId}/restore-review`, { method: 'POST' });

        // Regenerate each chunk for this speaker
        for (const chunk of speakerChunks) {
            const chunkId = chunk.id;
            const chunkCard = document.querySelector(`.library-chunk-card[data-chunk-id="${chunkId}"]`);
            const textarea = chunkCard?.querySelector('.library-chunk-textarea');
            const text = textarea ? textarea.value.trim() : chunk.text;

            if (!text) continue;

            // Update the individual chunk's voice override
            libraryChunkVoiceOverrides[chunkId] = { ...voicePayload };
            
            const requestBody = {
                chunk_id: chunkId,
                text: text,
                voice: voicePayload,
            };
            // Use the engine passed in from the per-speaker dropdown
            if (engine) {
                requestBody.engine = engine;
            }

            const response = await fetch(`/api/jobs/${jobId}/review/regen`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(requestBody),
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
    const card = button.closest('.library-chunk-card');
    const textarea = card ? card.querySelector('.library-chunk-textarea') : null;
    const text = textarea ? textarea.value.trim() : '';

    if (!text) {
        alert('Chunk text cannot be empty.');
        return;
    }

    button.disabled = true;
    button.textContent = 'Queuing...';

    // Get engine override from per-chunk dropdown
    const chunkEngineSelect = card?.querySelector('.library-chunk-engine-select');
    const engineOverride = chunkEngineSelect?.value || '';
    
    // Get voice selection from per-chunk dropdown
    const voiceSelect = card?.querySelector('.library-chunk-voice-select');
    const voiceValue = voiceSelect?.value || '';
    
    // Build voice payload based on engine type
    let voicePayload = libraryChunkVoiceOverrides[chunkId] || {};
    const originalChunk = (chunkReviewModalData?.chunks || []).find(chunk => chunk.id === chunkId);
    const normalizedEngine = (engineOverride || originalChunk?.engine || chunkReviewModalData?.engine || '')
        .toLowerCase()
        .replace(/[_-]/g, '');
    const isChatterbox = normalizedEngine.includes('chatterbox');
    const isVoxCPM = normalizedEngine.includes('voxcpm');
    const isQwenEngine = normalizedEngine.includes('qwen3');
    const isQwenClone = normalizedEngine.includes('qwen3') && normalizedEngine.includes('clone');
    const usesVoicePrompts = isChatterbox || isVoxCPM || isQwenClone;
    const voiceData = libraryVoiceMap.get(voiceValue);

    if (usesVoicePrompts) {
        if (voiceValue) {
            const promptEntry = libraryVoiceMap.get(voiceValue);
            voicePayload = {
                audio_prompt_path: voiceValue,
                ...(promptEntry?.transcript ? { extra: { prompt_text: promptEntry.transcript } } : {})
            };
        }
    } else if (isQwenEngine) {
        // Get Qwen3 language and instruction from the chunk options
        const qwen3Options = card?.querySelector('.chunk-qwen3-options');
        const langSelect = qwen3Options?.querySelector('.chunk-qwen3-language');
        const instructInput = qwen3Options?.querySelector('.chunk-qwen3-instruct');
        const language = langSelect?.value || 'Auto';
        let instruct = instructInput?.value?.trim() || '';
        if (!instruct) {
            instruct = getChunkInstruction(originalChunk);
        }
        const existingExtra = voicePayload.extra || {};
        voicePayload = {
            ...(voiceValue ? { voice: voiceValue } : {}),
            ...voicePayload,
            extra: {
                ...existingExtra,
                language: language,
                ...(instruct && { instruct: instruct })
            }
        };
    } else if (voiceValue) {
        voicePayload = { voice: voiceValue, lang_code: voiceData?.langCode || 'a' };
    }

    try {
        // First restore the job to review mode if not already
        await fetch(`/api/library/${jobId}/restore-review`, { method: 'POST' });

        const requestBody = {
            chunk_id: chunkId,
            text: text,
            voice: voicePayload,
        };
        if (engineOverride) {
            requestBody.engine = engineOverride;
        }

        const response = await fetch(`/api/jobs/${jobId}/review/regen`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
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
    const card = document.querySelector(`.library-chunk-card[data-chunk-id="${chunkId}"]`);
    if (!card) return;

    const summary = card.querySelector('.library-chunk-summary');
    if (!summary) return;

    // Remove existing status badges
    summary.querySelectorAll('.review-chip').forEach(el => el.remove());

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
        const toggle = summary.querySelector('.chunk-expand-toggle');
        if (toggle) {
            toggle.insertAdjacentHTML('afterend', badge);
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
                    const card = document.querySelector(`.library-chunk-card[data-chunk-id="${chunkId}"]`);
                    if (card) {
                        const playBtn = card.querySelector('.library-chunk-play');
                        const cacheToken = chunk.regenerated_at || Date.now().toString();
                        const newUrl = `${chunk.file_url}?t=${encodeURIComponent(cacheToken)}`;
                        if (playBtn) {
                            playBtn.setAttribute('data-audio-url', newUrl);
                            playBtn.disabled = false;
                        }
                        // Update voice label (API returns 'voice', not 'voice_label')
                        const voiceLabelEl = card.querySelector('.library-chunk-voice-label');
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

// FX button state helpers
function updateChunkApplyFxButtonState(slider) {
    const card = slider.closest('.library-chunk-card');
    if (!card) return;
    
    const speedSlider = card.querySelector('.chunk-speed-slider');
    const pitchSlider = card.querySelector('.chunk-pitch-slider');
    const applyBtn = card.querySelector('.library-chunk-apply-fx');
    const previewBtn = card.querySelector('.library-chunk-preview-fx');
    
    const speed = parseFloat(speedSlider?.value || 1.0);
    const pitch = parseFloat(pitchSlider?.value || 0);
    
    // Enable if either value is changed from default
    const hasChanges = Math.abs(speed - 1.0) > 0.01 || Math.abs(pitch) > 0.1;
    if (applyBtn) applyBtn.disabled = !hasChanges;
    if (previewBtn) previewBtn.disabled = !hasChanges;
}

function updateBulkApplyFxButtonState(slider) {
    const card = slider.closest('.bulk-speaker-card');
    if (!card) return;
    
    const speedSlider = card.querySelector('.bulk-speed-slider');
    const pitchSlider = card.querySelector('.bulk-pitch-slider');
    const applyBtn = card.querySelector('.bulk-speaker-apply-fx');
    
    if (!applyBtn) return;
    
    const speed = parseFloat(speedSlider?.value || 1.0);
    const pitch = parseFloat(pitchSlider?.value || 0);
    
    // Enable if either value is changed from default
    const hasChanges = Math.abs(speed - 1.0) > 0.01 || Math.abs(pitch) > 0.1;
    applyBtn.disabled = !hasChanges;
}

async function triggerChunkPreviewFx(jobId, chunkId, button) {
    const card = button.closest('.library-chunk-card');
    if (!card) return;
    
    // If already previewing, stop it
    if (previewAudio && previewButton === button) {
        stopPreviewAudio();
        return;
    }
    
    // Stop any existing preview or regular playback
    stopPreviewAudio();
    stopLibraryChunkAudio();
    
    const speedSlider = card.querySelector('.chunk-speed-slider');
    const pitchSlider = card.querySelector('.chunk-pitch-slider');
    
    const speed = parseFloat(speedSlider?.value || 1.0);
    const pitch = parseFloat(pitchSlider?.value || 0);
    
    const originalText = button.textContent;
    button.textContent = '⏳ Loading...';
    button.disabled = true;
    
    try {
        const response = await fetch(`/api/jobs/${jobId}/review/preview-fx`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chunk_id: chunkId, speed, pitch }),
        });
        
        if (!response.ok) {
            const data = await response.json();
            throw new Error(data.error || 'Failed to preview effects');
        }
        
        // Get the audio blob and play it
        const blob = await response.blob();
        const audioUrl = URL.createObjectURL(blob);
        
        previewAudio = new Audio(audioUrl);
        previewButton = button;
        
        button.textContent = '■ Stop';
        button.disabled = false;
        button.classList.add('previewing');
        
        previewAudio.addEventListener('ended', () => {
            stopPreviewAudio();
            button.textContent = originalText;
            button.disabled = false;
            // Re-check if button should be enabled based on slider values
            updateChunkApplyFxButtonState(speedSlider);
        });
        
        previewAudio.addEventListener('error', (err) => {
            console.error('Preview playback error:', err);
            stopPreviewAudio();
            button.textContent = originalText;
            button.disabled = false;
            updateChunkApplyFxButtonState(speedSlider);
        });
        
        await previewAudio.play();
        
    } catch (error) {
        console.error('Preview FX error:', error);
        alert(error.message || 'Failed to preview effects');
        button.textContent = originalText;
        button.disabled = false;
        updateChunkApplyFxButtonState(speedSlider);
    }
}

function stopPreviewAudio() {
    if (previewAudio) {
        previewAudio.pause();
        previewAudio.currentTime = 0;
        if (previewAudio.src && previewAudio.src.startsWith('blob:')) {
            URL.revokeObjectURL(previewAudio.src);
        }
        previewAudio = null;
    }
    if (previewButton) {
        previewButton.classList.remove('previewing');
        previewButton = null;
    }
}

async function triggerChunkApplyFx(jobId, chunkId, button) {
    const card = button.closest('.library-chunk-card');
    if (!card) return;
    
    const speedSlider = card.querySelector('.chunk-speed-slider');
    const pitchSlider = card.querySelector('.chunk-pitch-slider');
    
    const speed = parseFloat(speedSlider?.value || 1.0);
    const pitch = parseFloat(pitchSlider?.value || 0);
    
    button.disabled = true;
    button.textContent = 'Applying...';
    
    try {
        // First restore the job to review mode if not already
        await fetch(`/api/library/${jobId}/restore-review`, { method: 'POST' });

        const response = await fetch(`/api/jobs/${jobId}/review/apply-fx`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                chunks: [{ chunk_id: chunkId, speed, pitch }]
            }),
        });
        
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to apply effects');
        }
        
        // Show success feedback
        button.textContent = 'Applied!';
        updateLibraryChunkStatus(chunkId, 'completed');
        
        // Reset sliders to default
        if (speedSlider) speedSlider.value = 1.0;
        if (pitchSlider) pitchSlider.value = 0;
        card.querySelector('.chunk-speed-value').textContent = '1.0x';
        card.querySelector('.chunk-pitch-value').textContent = '0';
        
        // Update audio player URL to bust cache
        const playBtn = card.querySelector('.library-chunk-play');
        if (playBtn) {
            const currentUrl = playBtn.getAttribute('data-audio-url');
            if (currentUrl) {
                const baseUrl = currentUrl.split('?')[0];
                playBtn.setAttribute('data-audio-url', `${baseUrl}?t=${Date.now()}`);
            }
        }
        
        setTimeout(() => {
            button.textContent = 'Apply';
            button.disabled = true;
        }, 1500);
        
    } catch (error) {
        console.error('Apply FX error:', error);
        alert(error.message || 'Failed to apply effects');
        button.textContent = 'Apply';
        button.disabled = false;
    }
}

async function triggerBulkSpeakerApplyFx(jobId, speaker, chunks, button) {
    const card = button.closest('.bulk-speaker-card');
    if (!card) return;
    
    const speedSlider = card.querySelector('.bulk-speed-slider');
    const pitchSlider = card.querySelector('.bulk-pitch-slider');
    
    const speed = parseFloat(speedSlider?.value || 1.0);
    const pitch = parseFloat(pitchSlider?.value || 0);
    
    // Get all chunks for this speaker
    const speakerChunks = chunks.filter(c => (c.speaker || 'default') === speaker);
    if (speakerChunks.length === 0) {
        alert('No chunks found for this speaker.');
        return;
    }
    
    button.disabled = true;
    button.textContent = `Applying to ${speakerChunks.length}...`;
    
    try {
        // First restore the job to review mode if not already
        await fetch(`/api/library/${jobId}/restore-review`, { method: 'POST' });

        const chunksFx = speakerChunks.map(c => ({
            chunk_id: c.id,
            speed,
            pitch
        }));
        
        const response = await fetch(`/api/jobs/${jobId}/review/apply-fx`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ chunks: chunksFx }),
        });
        
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to apply effects');
        }
        
        // Show success feedback
        button.textContent = `Applied to ${data.processed}!`;
        
        // Update status for each chunk
        speakerChunks.forEach(c => {
            updateLibraryChunkStatus(c.id, 'completed');
            
            // Update audio player URL to bust cache
            const chunkCard = document.querySelector(`.library-chunk-card[data-chunk-id="${c.id}"]`);
            if (chunkCard) {
                const playBtn = chunkCard.querySelector('.library-chunk-play');
                if (playBtn) {
                    const currentUrl = playBtn.getAttribute('data-audio-url');
                    if (currentUrl) {
                        const baseUrl = currentUrl.split('?')[0];
                        playBtn.setAttribute('data-audio-url', `${baseUrl}?t=${Date.now()}`);
                    }
                }
            }
        });
        
        // Reset sliders to default
        if (speedSlider) speedSlider.value = 1.0;
        if (pitchSlider) pitchSlider.value = 0;
        card.querySelector('.bulk-speed-value').textContent = '1.0x';
        card.querySelector('.bulk-pitch-value').textContent = '0';
        
        setTimeout(() => {
            button.textContent = 'Apply FX';
            button.disabled = true;
        }, 2000);
        
    } catch (error) {
        console.error('Bulk apply FX error:', error);
        alert(error.message || 'Failed to apply effects');
        button.textContent = 'Apply FX';
        button.disabled = false;
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
