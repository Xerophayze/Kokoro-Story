// Library management

const currentChapterSelection = {};
let chunkReviewModalJobId = null;
let chunkReviewModalData = null;
let chapterReviewMode = false;
let libraryChunkVoiceOverrides = {};
let libraryChunkRegenWatchers = {};
let libraryBulkRegenWatcher = null;
let libraryRecompileProgressWatcher = null;
const LIBRARY_CHUNK_POLL_INTERVAL_MS = 2000;
const LIBRARY_CHUNK_MAX_ERROR_BACKOFF_MS = 15000;

// Library item playback state (only one item should play at a time)
let activeLibraryPlayer = null;
let activeLibraryUpdateControls = null;

function setActiveLibraryPlayer(player, updateControls) {
    if (activeLibraryPlayer && activeLibraryPlayer !== player) {
        activeLibraryPlayer.pause();
        activeLibraryPlayer.currentTime = 0;
        if (activeLibraryUpdateControls) {
            activeLibraryUpdateControls();
        }
    }
    activeLibraryPlayer = player;
    activeLibraryUpdateControls = updateControls;
}

function closeChapterActionMenus(root = document) {
    root.querySelectorAll('.chapter-action-menu').forEach(menu => {
        menu.classList.add('hidden');
        menu.innerHTML = '';
        menu.style.left = '';
        menu.style.top = '';
    });
}

function ensureChapterActionMenu(container) {
    if (!container) return null;
    let menu = container.querySelector('.chapter-action-menu');
    if (!menu) {
        menu = document.createElement('div');
        menu.className = 'chapter-action-menu hidden';
        container.appendChild(menu);
    }
    return menu;
}

function showChapterActionMenu({ menu, button, container, items }) {
    if (!menu || !button || !container) return;
    menu.innerHTML = '';
    items.forEach(({ label, onClick }) => {
        const itemButton = document.createElement('button');
        itemButton.type = 'button';
        itemButton.className = 'chapter-action-menu-item';
        itemButton.textContent = label;
        itemButton.addEventListener('click', (event) => {
            event.stopPropagation();
            onClick();
            closeChapterActionMenus(container);
        });
        menu.appendChild(itemButton);
    });

    menu.classList.remove('hidden');
    const containerRect = container.getBoundingClientRect();
    const buttonRect = button.getBoundingClientRect();
    const left = buttonRect.left - containerRect.left;
    const top = buttonRect.bottom - containerRect.top + 6;
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;

    requestAnimationFrame(() => {
        const maxLeft = container.clientWidth - menu.offsetWidth - 8;
        if (menu.offsetWidth && left > maxLeft) {
            menu.style.left = `${Math.max(8, maxLeft)}px`;
        }
    });
}

function ensureChunkReviewCloseHandlers() {
    const modalOverlay = document.getElementById('chunk-review-modal-overlay');
    const modalCloseBtn = document.getElementById('chunk-review-modal-close');
    const modalCloseFooterBtn = document.getElementById('chunk-review-close-btn');
    const recompileBtn = document.getElementById('chunk-review-recompile-btn');
    if (modalOverlay && !modalOverlay.dataset.closeBound) {
        modalOverlay.addEventListener('click', (e) => {
            if (e.target === modalOverlay) {
                closeChunkReviewModal();
            }
        });
        modalOverlay.dataset.closeBound = 'true';
    }
    if (modalCloseBtn && !modalCloseBtn.dataset.closeBound) {
        modalCloseBtn.addEventListener('click', closeChunkReviewModal);
        modalCloseBtn.dataset.closeBound = 'true';
    }
    if (modalCloseFooterBtn && !modalCloseFooterBtn.dataset.closeBound) {
        modalCloseFooterBtn.addEventListener('click', closeChunkReviewModal);
        modalCloseFooterBtn.dataset.closeBound = 'true';
    }
    if (recompileBtn && !recompileBtn.dataset.recompileBound) {
        recompileBtn.addEventListener('click', recompileLibraryAudio);
        recompileBtn.dataset.recompileBound = 'true';
    }
    if (!document.body.dataset.chunkReviewEscBound) {
        document.addEventListener('keydown', (event) => {
            if (event.key === 'Escape') {
                const overlay = document.getElementById('chunk-review-modal-overlay');
                if (overlay && !overlay.classList.contains('hidden')) {
                    closeChunkReviewModal();
                }
            }
        });
        document.body.dataset.chunkReviewEscBound = 'true';
    }
}

async function openChapterReviewModal(jobId, relativePath, fallbackTitle) {
    if (!jobId) return;
    ensureChunkReviewCloseHandlers();
    chapterReviewMode = true;
    chunkReviewModalJobId = jobId;
    chunkReviewModalData = null;
    libraryChunkVoiceOverrides = {};

    const overlay = document.getElementById('chunk-review-modal-overlay');
    const modal = document.getElementById('chunk-review-modal');
    const body = document.getElementById('chunk-review-modal-body');
    const titleEl = document.getElementById('chunk-review-modal-title');
    const renameBtn = document.getElementById('chunk-review-rename-btn');
    if (overlay) overlay.classList.remove('hidden');
    if (modal) modal.classList.remove('hidden');
    if (body) body.innerHTML = '<div class="chunk-review-loading">Loading chapter...</div>';
    if (titleEl) titleEl.textContent = fallbackTitle || 'Chapter Review';

    // Store chapter index for rename functionality
    let chapterIndex = null;
    let currentTitle = fallbackTitle || 'Chapter Review';

    try {
        const response = await fetch(`/api/library/${jobId}/chunks`);
        const data = await response.json();
        if (!data.success) {
            throw new Error(data.error || 'Failed to load chapter');
        }

        const chapters = data.chapters || [];
        const target = chapters.find(ch => ch.relative_path === relativePath)
            || chapters.find(ch => ch.output_filename && relativePath?.endsWith(ch.output_filename))
            || null;
        if (!target) {
            throw new Error('Chapter details not found');
        }

        chapterIndex = target.index ?? null;
        currentTitle = target.title || fallbackTitle || 'Chapter Review';

        const filtered = filterChapterReviewData(data, target);
        chunkReviewModalData = filtered;
        if (titleEl) {
            titleEl.textContent = currentTitle;
        }

        // Wire up rename button
        if (renameBtn && chapterIndex !== null) {
            renameBtn.style.display = 'inline-block';
            renameBtn.onclick = () => {
                openChapterRenameModal(jobId, chapterIndex, currentTitle);
            };
        } else if (renameBtn) {
            renameBtn.style.display = 'none';
        }

        renderChunkReviewModal(filtered);
    } catch (error) {
        console.error('Error loading chapter review:', error);
        if (body) body.innerHTML = '<div class="chunk-review-empty">Failed to load chapter.</div>';
        alert(error.message || 'Failed to load chapter review');
    }
}

function filterChapterReviewData(data, chapter) {
    const chapterIndex = chapter?.index ?? null;
    const chunks = (data.chunks || []).filter(chunk => {
        if (chapterIndex === null) return false;
        return (chunk.chapter_index ?? 0) === chapterIndex;
    });
    return {
        ...data,
        chunks,
        chapters: [],
        books: [],
        has_chapters: false,
        has_books: false,
        full_story_available: false,
        review_chapter_index: chapterIndex,
    };
}

function clearActiveLibraryPlayer(player) {
    if (activeLibraryPlayer === player) {
        activeLibraryPlayer = null;
        activeLibraryUpdateControls = null;
    }
}

// Audio playback state for chunk review modal
let libraryActiveAudio = null;
let libraryActivePlayButton = null;

// Continuous chunk playback state
let chunkSequenceAudio = null;
let chunkSequenceItems = [];
let chunkSequenceIndex = -1;
let chunkSequenceButton = null;
let chunkSequenceLabel = null;
let chunkSequenceLastCard = null;
let chunkSequenceStartIndex = null;
let chunkSequenceResumeIndex = null;

// Preview audio state
let previewAudio = null;
let previewButton = null;

// Voice map for looking up lang_code by voice id
let libraryVoiceMap = new Map();

function setRegenButtonBusy(button, isBusy, label = 'Regenerating...') {
    if (!button) return;
    if (isBusy) {
        if (!button.dataset.originalText) {
            button.dataset.originalText = button.textContent || 'Regenerate';
        }
        button.disabled = true;
        button.classList.add('is-loading');
        button.textContent = label;
    } else {
        button.disabled = false;
        button.classList.remove('is-loading');
        button.textContent = button.dataset.originalText || 'Regenerate';
        delete button.dataset.originalText;
    }
}

function resetChunkRegenButton(chunkId) {
    const card = document.querySelector(`.library-chunk-card[data-chunk-id="${chunkId}"]`);
    if (!card) return;
    const btn = card.querySelector('.library-chunk-regen');
    setRegenButtonBusy(btn, false);
}

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

function wireBookToggleEvents() {
    const headers = document.querySelectorAll('.book-header');
    headers.forEach(header => {
        header.addEventListener('click', () => {
            const bookIdx = header.getAttribute('data-book-index');
            const chaptersContainer = document.querySelector(`.book-chapters[data-book-index="${bookIdx}"]`);
            const toggle = header.querySelector('.book-toggle');

            if (chaptersContainer) {
                const isCollapsed = chaptersContainer.classList.contains('collapsed');
                if (isCollapsed) {
                    chaptersContainer.classList.remove('collapsed');
                    if (toggle) toggle.textContent = '▼';
                } else {
                    chaptersContainer.classList.add('collapsed');
                    if (toggle) toggle.textContent = '▶';
                }
            }
        });
    });

}

function setLibraryRecompileButtonState(hasActiveRegen, label = '') {
    const button = document.getElementById('chunk-review-recompile-btn');
    if (!button || button.dataset.recompileBusy === 'true') return;
    button.disabled = Boolean(hasActiveRegen);
    button.textContent = label || (hasActiveRegen ? 'Waiting for regeneration...' : 'Recompile Audio');
}

function setLibraryBulkActionState(isActive) {
    const button = document.getElementById('chunk-review-rebuild-selected');
    if (!button) return;
    const hasSelection = Boolean(document.querySelector('.bulk-speaker-checkbox:checked'));
    button.disabled = Boolean(isActive) || !hasSelection;
    button.textContent = isActive ? 'Regeneration in progress...' : 'Regen Selected Speakers';
}

async function requestLibraryReviewRestore(jobId) {
    const response = await fetch(`/api/library/${jobId}/restore-review`, { method: 'POST' });
    const data = await response.json();
    if (!response.ok || !data.success) {
        throw new Error(data.error || 'Failed to prepare this Library item for review');
    }
    return data;
}

async function fetchLibraryReviewPayload(jobId) {
    const response = await fetch(`/api/jobs/${jobId}/chunks`);
    const data = await response.json();
    if (!response.ok || !data.success) {
        throw new Error(data.error || 'Failed to load regeneration status');
    }
    return data;
}

function syncLibraryChunkRegenState(jobId, payload = {}) {
    const regenTasks = payload.regen_tasks || {};
    const activeChunkIds = [];
    Object.entries(regenTasks).forEach(([chunkId, task]) => {
        const status = task?.status;
        if (!status) return;
        updateLibraryChunkStatus(chunkId, status);
        if (status === 'queued' || status === 'running') {
            activeChunkIds.push(chunkId);
        }
    });
    if (activeChunkIds.length) {
        const requestedTimes = activeChunkIds
            .map(chunkId => Date.parse(regenTasks[chunkId]?.requested_at))
            .filter(timestamp => Number.isFinite(timestamp));
        startLibraryBulkRegenWatcher(jobId, activeChunkIds, {
            resumed: true,
            startedAt: requestedTimes.length ? Math.min(...requestedTimes) : Date.now(),
        });
    }
    setLibraryRecompileButtonState(Boolean(payload.review?.has_active_regen));
}

async function refreshLibraryRecompileState(jobId) {
    try {
        const payload = await fetchLibraryReviewPayload(jobId);
        setLibraryRecompileButtonState(Boolean(payload.review?.has_active_regen));
        return payload;
    } catch (error) {
        console.error('Failed to refresh Library regeneration state:', error);
        setLibraryRecompileButtonState(true, 'Status unavailable');
        return null;
    }
}

// Library voice dropdown filter state
let libraryVoiceFilters = {
    gender: 'all',
    language: 'all'
};

// Load library on tab switch
document.addEventListener('DOMContentLoaded', () => {
    loadLibrary();
    if (typeof setupGlobalPlayerControls === 'function') {
        setupGlobalPlayerControls();
    }
    if (typeof setupLibraryControls === 'function') {
        setupLibraryControls();
    }
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
});

document.addEventListener('library:refresh', () => {
    loadLibrary();
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
        'pocket_tts': 'Pocket TTS (Clone Voices)',
        'pocket_tts_preset': 'Pocket TTS (Preset Voices)',
        'qwen3_custom': 'Qwen3-TTS (Custom Voice)',
        'qwen3_clone': 'Qwen3-TTS (Voice Clone)',
        'omnivoice_clone': 'OmniVoice (Voice Clone)',
        'omnivoice_design': 'OmniVoice (Voice Design)',
        'dots_tts': 'Dot.TTS (Voice Clone)',
        'audio8_tts': 'Audio8 TTS (Voice Clone)',
        'azure_speech': 'Microsoft Azure Speech',
        'edge_tts': 'Microsoft Edge TTS (Experimental)',
        'elevenlabs': 'ElevenLabs',
    };
    return engineMap[engine] || engine;
}

function formatSectionLabel(section, fallbackLabel) {
    if (!section) {
        return fallbackLabel;
    }
    if (section.title) {
        return section.title;
    }
    if (section.index) {
        return `${fallbackLabel} ${section.index}`;
    }
    return fallbackLabel;
}

function renderChapterControls(item) {
    const sections = item.book_mode && item.books?.length ? item.books : item.chapters;
    if (!sections || sections.length <= 1) {
        if (!item.has_chunks) return '';
        // Single-chapter or no chapters but chunk data exists — render just the review button
        const reviewAllButton = `
            <button
                class="btn btn-secondary btn-xs chapter-pill chapter-review-all"
                type="button"
                data-review-all="true"
                data-job-id="${item.job_id}"
                data-full-story-src="${item.full_story?.output_file || ''}"
                data-full-story-path="${item.full_story?.relative_path || ''}"
            >
                Review Chunks
            </button>
        `;
        return `
            <div class="chapter-controls" data-job-id="${item.job_id}">
                <div class="chapter-pill-container">
                    ${reviewAllButton}
                </div>
            </div>
        `;
    }

    const label = item.book_mode ? 'Books' : 'Chapters';
    const fallbackLabel = item.book_mode ? 'Book' : 'Chapter';

    const reviewAllButton = item.has_chunks
        ? `
            <button
                class="btn btn-secondary btn-xs chapter-pill chapter-review-all"
                type="button"
                data-review-all="true"
                data-job-id="${item.job_id}"
                data-full-story-src="${item.full_story?.output_file || ''}"
                data-full-story-path="${item.full_story?.relative_path || ''}"
            >
                Full Story
            </button>
        `
        : '';

    return `
        <div class="chapter-controls" data-job-id="${item.job_id}">
            <div class="chapter-controls-header">
                <strong>${label}</strong>
            </div>
            <div class="chapter-pill-container">
                ${sections.map((section, idx) => `
                    <button
                        class="btn btn-secondary btn-xs chapter-pill ${idx === 0 ? 'active' : ''}"
                        data-job-id="${item.job_id}"
                        data-relative-path="${section.relative_path}"
                        data-src="${section.output_file}"
                        data-index="${(section.index ?? (idx + 1))}"
                    >
                        ${formatSectionLabel(section, fallbackLabel)}
                    </button>
                `).join('')}
                ${reviewAllButton}
            </div>
        </div>
    `;
}

function renderFullStoryBanner() {
    return '';
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
        const sectionList = item.book_mode && item.books?.length ? item.books : item.chapters;
        const initialChapter = (sectionList && sectionList.length > 0) ? sectionList[0] : null;
        if (initialChapter) {
            const initialIndex = Number.isFinite(initialChapter.index)
                ? initialChapter.index
                : (sectionList ? sectionList.indexOf(initialChapter) : 0);
            currentChapterSelection[item.job_id] = {
                ...initialChapter,
                chapter_number: Number.isFinite(initialIndex) ? initialIndex + 1 : 1,
            };
        }

        // Format engine name for display
        const engineLabel = formatEngineName(item.engine);

        const defaultTitle = item.book_mode ? 'Book Collection' : (item.chapter_mode ? 'Chapter Collection' : 'Generated Audio');
        const displayTitle = item.collection_title || defaultTitle;

        const hasBooks = item.book_mode && Array.isArray(item.books) && item.books.length > 0;
        const hasChapters = Array.isArray(item.chapters) && item.chapters.length > 0;
        itemCard.innerHTML = `
            <div class="library-item-header library-item-summary" data-job-id="${item.job_id}">
                <button class="library-item-toggle" aria-expanded="false" aria-label="Toggle details">▶</button>
                <div class="library-item-controls" data-job-id="${item.job_id}" data-full-story-src="${item.full_story ? item.full_story.output_file : ''}" data-full-story-path="${item.full_story ? item.full_story.relative_path : ''}">
                    <button class="btn btn-secondary btn-xs library-item-control-btn library-item-play" data-job-id="${item.job_id}" aria-label="Play">▶</button>
                    <button class="btn btn-secondary btn-xs library-item-control-btn library-item-pause" data-job-id="${item.job_id}" aria-label="Pause">⏸</button>
                </div>
                <div class="library-item-info">
                    <strong class="library-item-title">${escapeHtml(displayTitle)}</strong>
                    <button class="btn btn-secondary btn-xs library-title-edit" type="button" title="Edit title">✎</button>
                    <span class="library-item-date">${formattedDate}</span>
                </div>
                <div class="library-item-meta">
                    ${engineLabel ? `<span class="library-item-engine">${engineLabel}</span>` : ''}
                    <span class="library-item-size">${fileSizeMB} MB</span>
                    <span class="library-item-format">${item.format.toUpperCase()}</span>
                    <button class="btn btn-secondary btn-xs library-item-meta-action" type="button" onclick="openLibraryAwr('${item.job_id}')">Alt Words</button>
                    ${item.timing_metrics ? `<button class="btn btn-secondary btn-xs library-item-meta-action" type="button" onclick="openLibraryMetrics('${item.job_id}', this)">Metrics</button>` : ''}
                    <button class="btn btn-secondary btn-xs library-item-meta-action timecodes-open-btn" type="button" data-job-id="${item.job_id}" data-title="${escapeHtml(displayTitle)}">Time Codes</button>
                    <button class="btn btn-secondary btn-xs library-item-meta-action" type="button" onclick="downloadLibraryAudio('${item.job_id}')">Download</button>
                    ${item.chapter_mode ? `<button class="btn btn-secondary btn-xs library-item-meta-action" type="button" onclick="openM4BDownloadModal('${item.job_id}', '${escapeHtml(displayTitle)}')">Download M4B</button>` : ''}
                    <button class="btn btn-secondary btn-xs library-item-meta-action" type="button" onclick="openAudiobookMetadataModal('${item.job_id}')">Edit Metadata</button>
                    <button class="btn btn-secondary btn-xs library-item-meta-action" type="button" onclick="repairLibraryItem('${item.job_id}', this)">Rebuild</button>
                    ${item.engine === 'breeze_api' ? `<button class="btn btn-secondary btn-xs library-item-meta-action" type="button" onclick="openBreezeProductions('${item.job_id}')">Breeze Voices</button>` : ''}
                    <button class="btn btn-secondary btn-xs library-item-meta-action" type="button" onclick="deleteLibraryItem('${item.job_id}')">Delete</button>
                    <button type="button" class="help-icon library-item-meta-action" data-help-id="audio-library-actions" aria-label="Help: Audio Library Actions">?</button>
                </div>
            </div>
            <div class="library-item-details collapsed" data-job-id="${item.job_id}">
                <div class="library-item-player">
                    <audio controls id="player-${item.job_id}"></audio>
                </div>
                ${renderChapterControls(item)}
                ${renderFullStoryBanner(item)}
            </div>
        `;
        
        if (item.timing_metrics) {
            itemCard.dataset.timingMetrics = JSON.stringify(item.timing_metrics);
        }

        container.appendChild(itemCard);

        const player = itemCard.querySelector(`#player-${item.job_id}`);
        if (player && initialChapter) {
            player.src = initialChapter.output_file;
            player.load();
        } else if (player) {
            player.src = item.output_file;
            player.load();
        }

        const summaryHeader = itemCard.querySelector(`.library-item-summary[data-job-id="${item.job_id}"]`);
        const details = itemCard.querySelector(`.library-item-details[data-job-id="${item.job_id}"]`);
        const toggleBtn = itemCard.querySelector(`.library-item-toggle`);
        const controls = itemCard.querySelector(`.library-item-controls[data-job-id="${item.job_id}"]`);
        const playBtn = itemCard.querySelector(`.library-item-play[data-job-id="${item.job_id}"]`);
        const pauseBtn = itemCard.querySelector(`.library-item-pause[data-job-id="${item.job_id}"]`);
        const titleEl = itemCard.querySelector('.library-item-title');
        const editTitleBtn = itemCard.querySelector('.library-title-edit');

        if (summaryHeader && details && toggleBtn) {
            summaryHeader.addEventListener('click', (event) => {
                if (event.target.closest('.library-item-controls') || event.target.closest('.library-title-edit') || event.target.closest('.library-item-meta-action')) {
                    return;
                }
                const isCollapsed = details.classList.contains('collapsed');
                details.classList.toggle('collapsed');
                toggleBtn.textContent = isCollapsed ? '▼' : '▶';
                toggleBtn.setAttribute('aria-expanded', String(isCollapsed));
            });
        }

        if (editTitleBtn && titleEl) {
            editTitleBtn.addEventListener('click', async (event) => {
                event.stopPropagation();
                const nextTitle = prompt('Collection title', titleEl.textContent || '');
                if (!nextTitle) {
                    return;
                }

                try {
                    const response = await fetch(`/api/library/${item.job_id}/title`, {
                        method: 'PUT',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ title: nextTitle })
                    });
                    const data = await response.json();
                    if (!data.success) {
                        alert(`Failed to update title: ${data.error}`);
                        return;
                    }
                    titleEl.textContent = data.title;
                } catch (error) {
                    console.error('Error updating collection title:', error);
                    alert('Failed to update title');
                }
            });
        }

        if (controls && player) {
            const getFullStoryInfo = () => {
                const fullStorySrc = controls.getAttribute('data-full-story-src');
                const fullStoryPath = controls.getAttribute('data-full-story-path');
                return { fullStorySrc, fullStoryPath };
            };

            const updateControls = () => {
                if (!playBtn || !pauseBtn) return;

                const isStopped = (player.currentTime === 0 && player.paused) || player.ended;

                if (isStopped) {
                    // Fully stopped: show play button, hide pause button
                    playBtn.textContent = '▶';
                    playBtn.setAttribute('aria-label', 'Play');
                    pauseBtn.style.display = 'none';
                } else {
                    // Playing or paused (but not stopped): show stop button and pause button
                    playBtn.textContent = '■';
                    playBtn.setAttribute('aria-label', 'Stop');
                    pauseBtn.style.display = 'inline-block';
                }
            };

            // Initialize button states
            updateControls();

            if (playBtn) {
                playBtn.addEventListener('click', (event) => {
                    event.stopPropagation();
                    
                    // If playing or paused, stop it
                    if (player.currentTime > 0) {
                        player.pause();
                        player.currentTime = 0;
                        clearActiveLibraryPlayer(player);
                        updateControls();
                        return;
                    }

                    // Start playing
                    const { fullStorySrc, fullStoryPath } = getFullStoryInfo();
                    if (fullStorySrc) {
                        const separator = fullStorySrc.includes('?') ? '&' : '?';
                        player.src = `${fullStorySrc}${separator}v=${Date.now()}`;
                        player.load();
                        currentChapterSelection[item.job_id] = {
                            output_file: fullStorySrc,
                            relative_path: fullStoryPath,
                            title: 'Full Story'
                        };
                    }
                    setActiveLibraryPlayer(player, updateControls);
                    player.play();
                    updateControls();
                });
            }

            if (pauseBtn) {
                pauseBtn.addEventListener('click', (event) => {
                    event.stopPropagation();
                    
                    // Toggle pause/unpause
                    if (!player.paused) {
                        player.pause();
                    } else if (player.currentTime > 0) {
                        player.play();
                    }
                    // Don't call updateControls here - let the play/pause events handle it
                });
            }

            player.addEventListener('play', () => {
                updateControls();
            });

            player.addEventListener('pause', () => {
                updateControls();
            });

            player.addEventListener('ended', () => {
                clearActiveLibraryPlayer(player);
                updateControls();
            });
        }

        // Wire chapter buttons
        const chapterControls = itemCard.querySelector('.chapter-controls');
        const chapterButtons = itemCard.querySelectorAll(`.chapter-pill[data-job-id="${item.job_id}"]`);
        const reviewAllButton = itemCard.querySelector('.chapter-review-all');
        const menu = ensureChapterActionMenu(chapterControls);

        chapterButtons.forEach(button => {
            if (button === reviewAllButton) return;
            button.addEventListener('click', (event) => {
                event.stopPropagation();
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

                const chapterNumber = Number(button.getAttribute('data-index')) || null;
                const selectedChapter = (sectionList || []).find(ch => ch.relative_path === relativePath) || {
                    output_file: src,
                    relative_path: relativePath,
                    title: button.textContent.trim(),
                    index: chapterNumber ? chapterNumber - 1 : null,
                };
                currentChapterSelection[jobId] = {
                    ...selectedChapter,
                    chapter_number: chapterNumber || (Number.isFinite(selectedChapter.index) ? selectedChapter.index + 1 : null),
                };
                const anchorId = relativePath || button.textContent.trim();
                if (menu && !menu.classList.contains('hidden') && menu.dataset.anchorId === anchorId) {
                    closeChapterActionMenus(chapterControls);
                    return;
                }
                if (menu) {
                    menu.dataset.anchorId = anchorId;
                }
                showChapterActionMenu({
                    menu,
                    button,
                    container: chapterControls,
                    items: [
                        {
                            label: 'Review Chunks',
                            onClick: () => openChapterReviewModal(jobId, relativePath, button.textContent.trim())
                        },
                        {
                            label: 'Rename Chapter',
                            onClick: () => openChapterRenameModal(jobId, (Number(button.getAttribute('data-index')) || 1) - 1, button.textContent.trim())
                        },
                        {
                            label: 'Download Chapter',
                            onClick: () => downloadLibraryItem(jobId)
                        }
                    ]
                });
            });
        });

        if (reviewAllButton) {
            reviewAllButton.addEventListener('click', (event) => {
                event.stopPropagation();
                const jobId = reviewAllButton.getAttribute('data-job-id');
                const fullStorySrc = reviewAllButton.getAttribute('data-full-story-src');
                const fullStoryPath = reviewAllButton.getAttribute('data-full-story-path');
                const playerEl = document.getElementById(`player-${jobId}`);
                if (playerEl && fullStorySrc) {
                    chapterButtons.forEach(btn => btn.classList.remove('active'));
                    reviewAllButton.classList.add('active');
                    const separator = fullStorySrc.includes('?') ? '&' : '?';
                    playerEl.src = `${fullStorySrc}${separator}v=${Date.now()}`;
                    playerEl.load();
                    currentChapterSelection[jobId] = {
                        output_file: fullStorySrc,
                        relative_path: fullStoryPath,
                        title: 'Full Story'
                    };
                }
                const anchorId = 'review-all';
                if (menu && !menu.classList.contains('hidden') && menu.dataset.anchorId === anchorId) {
                    closeChapterActionMenus(chapterControls);
                    return;
                }
                if (menu) {
                    menu.dataset.anchorId = anchorId;
                }
                const menuItems = [
                    {
                        label: 'Review Chunks',
                        onClick: () => restoreToReview(jobId)
                    }
                ];
                if (fullStoryPath) {
                    menuItems.push({
                        label: 'Download Full Story',
                        onClick: () => downloadFullStory(jobId, fullStoryPath)
                    });
                }
                showChapterActionMenu({
                    menu,
                    button: reviewAllButton,
                    container: chapterControls,
                    items: menuItems
                });
            });
        }
    });

    if (!document.body.dataset.chapterMenuBound) {
        document.addEventListener('click', (event) => {
            if (!event.target.closest('.chapter-pill') && !event.target.closest('.chapter-action-menu')) {
                closeChapterActionMenus();
            }
        });
        document.body.dataset.chapterMenuBound = 'true';
    }

}

// Library Metrics Modal
function openLibraryMetrics(jobId, btn) {
    const card = btn ? btn.closest('.library-item') : document.querySelector(`.library-item [data-job-id="${jobId}"]`)?.closest('.library-item');
    const tm = card && card.dataset.timingMetrics ? JSON.parse(card.dataset.timingMetrics) : null;
    if (!tm) { alert('No metrics data available for this item.'); return; }

    function fmtTime(iso) { return iso ? new Date(iso).toLocaleString() : 'N/A'; }

    const startedAt  = fmtTime(tm.started_at);
    const completedAt = fmtTime(tm.completed_at);
    const totalTime  = fmtDuration(tm.total_seconds);
    const avgChunk   = tm.avg_chunk_seconds != null ? fmtDuration(tm.avg_chunk_seconds) : 'N/A';
    const minChunk   = tm.min_chunk_seconds != null ? fmtDuration(tm.min_chunk_seconds) : 'N/A';
    const maxChunk   = tm.max_chunk_seconds != null ? fmtDuration(tm.max_chunk_seconds) : 'N/A';
    const chunkCount = tm.chunk_count != null ? tm.chunk_count : 'N/A';
    const chart      = buildChunkChart(tm.chunk_times, tm.chunk_count, tm.total_seconds);

    // Build or reuse overlay
    let overlay = document.getElementById('library-metrics-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'library-metrics-overlay';
        overlay.style.cssText = 'position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:9000;display:flex;align-items:center;justify-content:center;';
        overlay.addEventListener('click', e => { if (e.target === overlay) overlay.remove(); });
        document.body.appendChild(overlay);
    }
    overlay.innerHTML = `
        <div style="background:var(--bg-card,#1a1d2e);border:1px solid var(--border,rgba(99,102,241,0.2));border-radius:12px;padding:24px;min-width:340px;max-width:560px;width:90%;max-height:90vh;overflow-y:auto;box-shadow:0 8px 32px rgba(0,0,0,0.5);">
            <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px;">
                <h3 style="margin:0;font-size:1rem;color:var(--accent,#7eb8f7);">Generation Metrics</h3>
                <button onclick="document.getElementById('library-metrics-overlay').remove()" style="background:none;border:none;color:var(--text-muted,#8892a4);font-size:1.2rem;cursor:pointer;padding:2px 6px;">✕</button>
            </div>
            <div class="job-detail-timing-grid" style="margin-bottom:16px;">
                <div class="timing-row"><span class="timing-label">Started</span><span class="timing-value">${startedAt}</span></div>
                <div class="timing-row"><span class="timing-label">Completed</span><span class="timing-value">${completedAt}</span></div>
                <div class="timing-row timing-highlight"><span class="timing-label">Total Job Time</span><span class="timing-value">${totalTime}</span></div>
                <div class="timing-row"><span class="timing-label">Chunks</span><span class="timing-value">${chunkCount}</span></div>
                <div class="timing-row timing-highlight"><span class="timing-label">Avg Chunk Time</span><span class="timing-value">${avgChunk}</span></div>
                <div class="timing-row"><span class="timing-label">Fastest Chunk</span><span class="timing-value">${minChunk}</span></div>
                <div class="timing-row"><span class="timing-label">Slowest Chunk</span><span class="timing-value">${maxChunk}</span></div>
            </div>
            ${chart}
        </div>`;
    if (!document.getElementById('library-metrics-overlay')) {
        document.body.appendChild(overlay);
    }

    // Close on Escape
    const escHandler = e => { if (e.key === 'Escape') { overlay.remove(); document.removeEventListener('keydown', escHandler); } };
    document.addEventListener('keydown', escHandler);
}

// Download library item
function downloadLibraryItem(jobId) {
    const selected = currentChapterSelection[jobId];
    if (!selected || !selected.relative_path) {
        window.location.href = `/api/download/${jobId}`;
        return;
    }

    const queryParts = [`file=${encodeURIComponent(selected.relative_path)}`];
    const downloadName = buildChapterDownloadName(selected);
    if (downloadName) {
        queryParts.push(`download_name=${encodeURIComponent(downloadName)}`);
    }
    window.location.href = `/api/download/${jobId}?${queryParts.join('&')}`;
}

function buildChapterDownloadName(selected) {
    if (!selected || !selected.relative_path) return '';
    const rawTitle = selected.title || 'Chapter';
    const sanitizedTitle = rawTitle.replace(/[^a-z0-9\-_. ]/gi, '').trim().replace(/\s+/g, ' ');
    const extension = selected.relative_path.split('.').pop() || 'mp3';
    const chapterNumber = Number.isFinite(selected.chapter_number)
        ? selected.chapter_number
        : (Number.isFinite(selected.index) ? selected.index + 1 : null);
    const displayNumber = chapterNumber ? String(chapterNumber).padStart(2, '0') : '';
    const prefix = displayNumber ? `Chapter-${displayNumber}` : 'Chapter';
    const titlePart = sanitizedTitle && sanitizedTitle.toLowerCase() !== 'full story'
        ? `_${sanitizedTitle.replace(/\s+/g, '-')}`
        : '';
    return `${prefix}${titlePart}.${extension}`;
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

// Download regular audio format
function downloadLibraryAudio(jobId) {
    window.location.href = `/api/download/${jobId}`;
}

// Open M4B download options modal
function openM4BDownloadModal(jobId, title) {
    const modal = document.createElement('div');
    modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(15, 23, 42, 0.95); display: flex; align-items: center; justify-content: center; z-index: 99999;';
    modal.innerHTML = `
        <div style="background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border-color); max-width: 500px; width: 90%; max-height: 90vh; overflow: hidden; display: flex; flex-direction: column; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);">
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-color);">
                <h2 style="margin: 0; font-size: 1.25rem;">Download M4B Audiobook</h2>
                <button type="button" style="background: none; border: none; font-size: 1.5rem; cursor: pointer; color: var(--text-muted); padding: 0; line-height: 1;" class="modal-close">&times;</button>
            </div>
            <div style="padding: 20px; overflow-y: auto;">
                <p style="margin-top: 0;">Download "${escapeHtml(title)}" as an M4B audiobook with chapter markers.</p>
                <div style="margin-bottom: 16px;">
                    <label style="display: block; margin-bottom: 6px; font-weight: 500;">Bitrate:</label>
                    <select id="m4b-bitrate" style="width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-color); background: var(--bg-color); color: var(--text-color);">
                        <option value="64">64 kbps (smaller file)</option>
                        <option value="96">96 kbps</option>
                        <option value="128" selected>128 kbps (recommended)</option>
                        <option value="192">192 kbps (higher quality)</option>
                    </select>
                </div>
                <div style="margin-bottom: 16px;">
                    <label style="display: flex; align-items: center; gap: 8px; cursor: pointer;">
                        <input type="checkbox" id="m4b-acx-compliance" style="cursor: pointer;">
                        <span id="m4b-acx-label">ACX Compliance (apply audiobook loudness standards)</span>
                    </label>
                </div>
                <div style="margin-bottom: 16px;">
                    <label style="display: block; margin-bottom: 6px; font-weight: 500;">Cover Art (optional):</label>
                    <input type="file" id="m4b-cover-art" accept="image/*" style="width: 100%; padding: 8px; border-radius: 6px; border: 1px solid var(--border-color); background: var(--bg-color); color: var(--text-color);">
                    <small style="display: block; margin-top: 4px; color: var(--text-muted); font-size: 0.85rem;">Recommended: square 3000x3000px PNG or JPG; minimum warning threshold: 1400x1400px.</small>
                    <div id="m4b-cover-preview" style="display: none; margin-top: 10px; padding: 10px; border: 1px solid var(--border-color); border-radius: 8px; gap: 10px; align-items: center;">
                        <img id="m4b-cover-preview-image" alt="Selected audiobook cover preview" style="width: 84px; height: 84px; object-fit: contain; background: #090d18; border-radius: 4px;">
                        <div>
                            <div id="m4b-cover-dimensions" style="font-size: 0.9rem; color: var(--text-color);"></div>
                            <div id="m4b-cover-warning" style="margin-top: 4px; font-size: 0.82rem; color: #f59e0b;"></div>
                        </div>
                    </div>
                </div>
                <div style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px;">
                    <button type="button" id="m4b-cancel" style="padding: 8px 16px; border-radius: 6px; border: 1px solid var(--border-color); background: var(--bg-color); color: var(--text-color); cursor: pointer;">Cancel</button>
                    <button type="button" id="m4b-download" style="padding: 8px 16px; border-radius: 6px; border: none; background: var(--primary-color); color: white; cursor: pointer;">Download M4B</button>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    const coverArtInput = modal.querySelector('#m4b-cover-art');
    const coverPreview = modal.querySelector('#m4b-cover-preview');
    const coverPreviewImage = modal.querySelector('#m4b-cover-preview-image');
    const coverDimensions = modal.querySelector('#m4b-cover-dimensions');
    const coverWarning = modal.querySelector('#m4b-cover-warning');
    let coverArtInfo = null;

    const inspectCoverFile = (file) => new Promise((resolve, reject) => {
        const objectUrl = URL.createObjectURL(file);
        const image = new Image();
        image.onload = () => {
            const info = {
                file,
                width: image.naturalWidth,
                height: image.naturalHeight,
                previewUrl: objectUrl,
            };
            resolve(info);
        };
        image.onerror = () => {
            URL.revokeObjectURL(objectUrl);
            reject(new Error('The selected cover image could not be decoded.'));
        };
        image.src = objectUrl;
    });

    const renderCoverInfo = (info) => {
        if (coverArtInfo?.previewUrl && coverArtInfo.previewUrl !== info?.previewUrl) {
            URL.revokeObjectURL(coverArtInfo.previewUrl);
        }
        coverArtInfo = info;
        if (!info) {
            coverPreview.style.display = 'none';
            coverPreviewImage.removeAttribute('src');
            return;
        }
        coverPreview.style.display = 'flex';
        coverPreviewImage.src = info.previewUrl;
        coverDimensions.textContent = `${info.width} × ${info.height}px`;
        const warnings = [];
        if (info.width !== info.height) {
            warnings.push('This image is not square. Explicit confirmation will be required; TTS-Story will not crop it.');
        }
        if (Math.min(info.width, info.height) < 1400) {
            warnings.push('Resolution is below the 1400px minimum warning threshold.');
        }
        coverWarning.textContent = warnings.join(' ');
    };

    coverArtInput?.addEventListener('change', async () => {
        const file = coverArtInput.files?.[0];
        if (!file) {
            renderCoverInfo(null);
            return;
        }
        try {
            renderCoverInfo(await inspectCoverFile(file));
        } catch (error) {
            renderCoverInfo(null);
            coverArtInput.value = '';
            alert(error.message || 'Unable to inspect cover art.');
        }
    });

    // Check if files are already ACX compliant
    (async () => {
        try {
            const response = await fetch('/api/library');
            const data = await response.json();
            const jobItem = data.items?.find(item => item.job_id === jobId);
            if (jobItem && jobItem.acx_compliance) {
                const acxCheckbox = modal.querySelector('#m4b-acx-compliance');
                const acxLabel = modal.querySelector('#m4b-acx-label');
                if (acxCheckbox && acxLabel) {
                    acxCheckbox.checked = false;
                    acxCheckbox.disabled = true;
                    acxCheckbox.style.cursor = 'not-allowed';
                    acxCheckbox.style.opacity = '0.5';
                    acxLabel.textContent = 'Already ACX compliant (skipped)';
                    acxLabel.style.color = '#10b981';
                    acxLabel.style.cursor = 'default';
                }
            }
        } catch (e) {
            console.warn('Failed to check ACX compliance status:', e);
        }
    })();

    const closeModal = () => {
        if (coverArtInfo?.previewUrl) {
            URL.revokeObjectURL(coverArtInfo.previewUrl);
        }
        modal.remove();
    };

    modal.querySelector('.modal-close').addEventListener('click', closeModal);
    modal.querySelector('#m4b-cancel').addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });

    modal.querySelector('#m4b-download').addEventListener('click', async () => {
        const bitrate = parseInt(document.getElementById('m4b-bitrate').value);
        const acxCompliance = document.getElementById('m4b-acx-compliance').checked;
        let coverArtData = null;
        let allowNonSquareCover = false;

        if (coverArtInput.files.length > 0) {
            const file = coverArtInput.files[0];
            try {
                if (!coverArtInfo || coverArtInfo.file !== file) {
                    renderCoverInfo(await inspectCoverFile(file));
                }
            } catch (error) {
                alert(error.message || 'Unable to inspect cover art.');
                return;
            }
            if (coverArtInfo.width !== coverArtInfo.height) {
                allowNonSquareCover = confirm(
                    `The selected cover is ${coverArtInfo.width}x${coverArtInfo.height}px, not square. ` +
                    'Embed it without cropping anyway?'
                );
                if (!allowNonSquareCover) return;
            }
            coverArtData = await new Promise((resolve) => {
                const reader = new FileReader();
                reader.onload = (e) => resolve(e.target.result);
                reader.readAsDataURL(file);
            });
        }

        const downloadBtn = modal.querySelector('#m4b-download');
        const originalText = downloadBtn.textContent;
        downloadBtn.disabled = true;
        downloadBtn.textContent = 'Generating...';
        downloadBtn.style.opacity = '0.6';
        downloadBtn.style.cursor = 'not-allowed';

        // Add progress indicator
        const progressDiv = document.createElement('div');
        progressDiv.style.cssText = 'margin-top: 12px; padding: 12px; background: rgba(99, 102, 241, 0.1); border-radius: 6px; border: 1px solid rgba(99, 102, 241, 0.3);';
        progressDiv.innerHTML = `
            <div style="margin-bottom: 8px; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 0.85rem; color: var(--text-color);">Generating M4B audiobook...</span>
                <span id="m4b-progress-percent" style="font-size: 0.85rem; font-weight: 500; color: var(--primary-color);">0%</span>
            </div>
            <div style="width: 100%; height: 8px; background: rgba(99, 102, 241, 0.2); border-radius: 4px; overflow: hidden;">
                <div id="m4b-progress-bar" style="width: 0%; height: 100%; background: var(--primary-color); transition: width 0.3s ease; border-radius: 4px;"></div>
            </div>
            <div id="m4b-progress-status" style="margin-top: 6px; font-size: 0.8rem; color: var(--text-muted);">Initializing...</div>
        `;
        downloadBtn.parentNode.insertBefore(progressDiv, downloadBtn.nextSibling);

        const progressBar = progressDiv.querySelector('#m4b-progress-bar');
        const progressPercent = progressDiv.querySelector('#m4b-progress-percent');
        const progressStatus = progressDiv.querySelector('#m4b-progress-status');

        // Poll for progress
        const pollProgress = async () => {
            try {
                const response = await fetch(`/api/download/${jobId}/m4b/progress`);
                const data = await response.json();
                
                if (data.progress !== undefined) {
                    const percent = Math.round(data.progress * 100);
                    progressBar.style.width = `${percent}%`;
                    progressPercent.textContent = `${percent}%`;
                    
                    if (data.status === 'encoding') {
                        if (data.progress < 0.5) {
                            const encodingPercent = Math.min(100, Math.round((data.progress / 0.5) * 100));
                            progressStatus.textContent = `Encoding audio (${encodingPercent}% of first pass)...`;
                        } else if (data.progress < 0.75) {
                            progressStatus.textContent = 'Merging audio files...';
                        } else if (data.progress < 0.95) {
                            progressStatus.textContent = 'Adding chapter markers...';
                        } else {
                            progressStatus.textContent = 'Finalizing...';
                        }
                    } else if (data.status === 'complete') {
                        progressStatus.textContent = 'Complete!';
                        progressBar.style.width = '100%';
                        progressPercent.textContent = '100%';
                        return true; // Done
                    } else if (data.status === 'error') {
                        progressStatus.textContent = `Error: ${data.error}`;
                        progressStatus.style.color = '#ef4444';
                        return false; // Error
                    }
                }
                return false; // Not done yet
            } catch (e) {
                console.error('Error polling progress:', e);
                return false;
            }
        };

        // Start polling
        const pollInterval = setInterval(async () => {
            const done = await pollProgress();
            if (done !== false) {
                clearInterval(pollInterval);
            }
        }, 500);

        try {
            const response = await fetch(`/api/download/${jobId}/m4b`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    bitrate,
                    acx_compliance: acxCompliance,
                    cover_art: coverArtData,
                    allow_non_square_cover: allowNonSquareCover
                })
            });

            clearInterval(pollInterval);

            if (!response.ok) {
                const error = await response.json();
                throw new Error(error.error || 'Failed to generate M4B');
            }

            const blob = await response.blob();
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `${title.replace(/[^a-z0-9]/gi, '_')}.m4b`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            closeModal();
        } catch (error) {
            clearInterval(pollInterval);
            alert('Error: ' + error.message);
            downloadBtn.disabled = false;
            downloadBtn.textContent = originalText;
            downloadBtn.style.opacity = '';
            downloadBtn.style.cursor = '';
            progressDiv.remove();
        }
    });
}

// Open chapter rename modal
function openChapterRenameModal(jobId, chapterIndex, currentTitle) {
    const modal = document.createElement('div');
    modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(15, 23, 42, 0.95); display: flex; align-items: center; justify-content: center; z-index: 99999;';
    modal.innerHTML = `
        <div style="background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border-color); max-width: 400px; width: 90%; max-height: 90vh; overflow: hidden; display: flex; flex-direction: column; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);">
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-color);">
                <h2 style="margin: 0; font-size: 1.25rem;">Rename Chapter</h2>
                <button type="button" style="background: none; border: none; font-size: 1.5rem; cursor: pointer; color: var(--text-muted); padding: 0; line-height: 1;" class="modal-close">&times;</button>
            </div>
            <div style="padding: 20px; overflow-y: auto;">
                <div style="margin-bottom: 16px;">
                    <label style="display: block; margin-bottom: 6px; font-weight: 500;">Chapter Title:</label>
                    <input type="text" id="chapter-title" value="${escapeHtml(currentTitle)}" style="width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-color); background: var(--bg-color); color: var(--text-color);">
                </div>
                <div style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px;">
                    <button type="button" id="chapter-rename-cancel" style="padding: 8px 16px; border-radius: 6px; border: 1px solid var(--border-color); background: var(--bg-color); color: var(--text-color); cursor: pointer;">Cancel</button>
                    <button type="button" id="chapter-rename-save" style="padding: 8px 16px; border-radius: 6px; border: none; background: var(--primary-color); color: white; cursor: pointer;">Save</button>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    const closeModal = () => {
        modal.remove();
    };

    modal.querySelector('.modal-close').addEventListener('click', closeModal);
    modal.querySelector('#chapter-rename-cancel').addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });

    modal.querySelector('#chapter-rename-save').addEventListener('click', async () => {
        const newTitle = document.getElementById('chapter-title').value.trim();
        if (!newTitle) {
            alert('Title cannot be empty');
            return;
        }

        const saveBtn = modal.querySelector('#chapter-rename-save');
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';

        try {
            const response = await fetch(`/api/library/${jobId}/chapter/${chapterIndex}/rename`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle })
            });

            const data = await response.json();

            if (data.success) {
                closeModal();
                loadLibrary(); // Reload library to reflect changes
            } else {
                alert('Error: ' + data.error);
                saveBtn.disabled = false;
                saveBtn.textContent = 'Save';
            }
        } catch (error) {
            alert('Error: ' + error.message);
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save';
        }
    });
}

// Open audiobook metadata edit modal
async function openAudiobookMetadataModal(jobId) {
    // Fetch existing metadata
    let existingMetadata = {};
    try {
        const response = await fetch(`/api/library`);
        const data = await response.json();
        const item = data.items?.find(i => i.job_id === jobId);
        if (item) {
            existingMetadata = {
                title: item.audiobook_title || item.collection_title || '',
                author: item.audiobook_author || '',
                genre: item.audiobook_genre || '',
                year: item.audiobook_year || '',
                description: item.audiobook_description || ''
            };
        }
    } catch (e) {
        console.warn('Failed to fetch existing metadata:', e);
    }

    const modal = document.createElement('div');
    modal.style.cssText = 'position: fixed; top: 0; left: 0; right: 0; bottom: 0; background-color: rgba(15, 23, 42, 0.95); display: flex; align-items: center; justify-content: center; z-index: 99999;';
    modal.innerHTML = `
        <div style="background: var(--card-bg); border-radius: 12px; border: 1px solid var(--border-color); max-width: 500px; width: 90%; max-height: 90vh; overflow: hidden; display: flex; flex-direction: column; box-shadow: 0 20px 60px rgba(0, 0, 0, 0.5);">
            <div style="display: flex; justify-content: space-between; align-items: center; padding: 16px 20px; border-bottom: 1px solid var(--border-color);">
                <h2 style="margin: 0; font-size: 1.25rem;">Edit Audiobook Metadata</h2>
                <button type="button" style="background: none; border: none; font-size: 1.5rem; cursor: pointer; color: var(--text-muted); padding: 0; line-height: 1;" class="modal-close">&times;</button>
            </div>
            <div style="padding: 20px; overflow-y: auto;">
                <div style="margin-bottom: 16px;">
                    <label style="display: block; margin-bottom: 6px; font-weight: 500;">Title:</label>
                    <input type="text" id="metadata-title" value="${escapeHtml(existingMetadata.title)}" style="width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-color); background: var(--bg-color); color: var(--text-color);">
                </div>
                <div style="margin-bottom: 16px;">
                    <label style="display: block; margin-bottom: 6px; font-weight: 500;">Author:</label>
                    <input type="text" id="metadata-author" value="${escapeHtml(existingMetadata.author)}" style="width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-color); background: var(--bg-color); color: var(--text-color);">
                </div>
                <div style="margin-bottom: 16px;">
                    <label style="display: block; margin-bottom: 6px; font-weight: 500;">Genre:</label>
                    <input type="text" id="metadata-genre" value="${escapeHtml(existingMetadata.genre)}" style="width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-color); background: var(--bg-color); color: var(--text-color);">
                </div>
                <div style="margin-bottom: 16px;">
                    <label style="display: block; margin-bottom: 6px; font-weight: 500;">Year:</label>
                    <input type="text" id="metadata-year" value="${escapeHtml(existingMetadata.year)}" style="width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-color); background: var(--bg-color); color: var(--text-color);">
                </div>
                <div style="margin-bottom: 16px;">
                    <label style="display: block; margin-bottom: 6px; font-weight: 500;">Description:</label>
                    <textarea id="metadata-description" rows="3" style="width: 100%; padding: 8px 12px; border-radius: 6px; border: 1px solid var(--border-color); background: var(--bg-color); color: var(--text-color); resize: vertical;">${escapeHtml(existingMetadata.description)}</textarea>
                </div>
                <div style="display: flex; gap: 10px; justify-content: flex-end; margin-top: 20px;">
                    <button type="button" id="metadata-cancel" style="padding: 8px 16px; border-radius: 6px; border: 1px solid var(--border-color); background: var(--bg-color); color: var(--text-color); cursor: pointer;">Cancel</button>
                    <button type="button" id="metadata-save" style="padding: 8px 16px; border-radius: 6px; border: none; background: var(--primary-color); color: white; cursor: pointer;">Save</button>
                </div>
            </div>
        </div>
    `;

    document.body.appendChild(modal);

    const closeModal = () => {
        modal.remove();
    };

    modal.querySelector('.modal-close').addEventListener('click', closeModal);
    modal.querySelector('#metadata-cancel').addEventListener('click', closeModal);
    modal.addEventListener('click', (e) => {
        if (e.target === modal) closeModal();
    });

    modal.querySelector('#metadata-save').addEventListener('click', async () => {
        const metadata = {
            title: document.getElementById('metadata-title').value.trim(),
            author: document.getElementById('metadata-author').value.trim(),
            genre: document.getElementById('metadata-genre').value.trim(),
            year: document.getElementById('metadata-year').value.trim(),
            description: document.getElementById('metadata-description').value.trim()
        };

        const saveBtn = modal.querySelector('#metadata-save');
        saveBtn.disabled = true;
        saveBtn.textContent = 'Saving...';

        try {
            const response = await fetch(`/api/library/${jobId}/metadata`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(metadata)
            });

            const data = await response.json();

            if (data.success) {
                closeModal();
                loadLibrary(); // Reload library to reflect changes
            } else {
                alert('Error: ' + data.error);
                saveBtn.disabled = false;
                saveBtn.textContent = 'Save';
            }
        } catch (error) {
            alert('Error: ' + error.message);
            saveBtn.disabled = false;
            saveBtn.textContent = 'Save';
        }
    });
}

// Delete library item
function releaseLibraryItemAudio(jobId) {
    const jobAudioPath = `/static/audio/${jobId}/`;
    const players = new Set([
        activeLibraryPlayer,
        libraryActiveAudio,
        chunkSequenceAudio,
        previewAudio,
        ...document.querySelectorAll('audio'),
    ].filter(Boolean));

    players.forEach(player => {
        const sourceUrls = [
            player.currentSrc,
            player.getAttribute?.('src'),
            player.src,
            ...Array.from(player.querySelectorAll?.('source') || []).map(source => source.src),
        ].filter(Boolean);
        if (!sourceUrls.some(url => String(url).includes(jobAudioPath))) return;

        try {
            player.pause();
            player.removeAttribute?.('src');
            player.querySelectorAll?.('source')?.forEach(source => source.removeAttribute('src'));
            player.load?.();
        } catch (error) {
            console.warn('Could not fully release Library audio before deletion:', error);
        }
        if (activeLibraryPlayer === player) {
            activeLibraryPlayer = null;
            activeLibraryUpdateControls = null;
        }
        if (libraryActiveAudio === player) libraryActiveAudio = null;
        if (chunkSequenceAudio === player) chunkSequenceAudio = null;
        if (previewAudio === player) previewAudio = null;
    });

    stopLibraryChunkAudio();
    stopChunkSequence();
    stopPreviewAudio();
}

async function deleteLibraryItem(jobId) {
    if (!confirm('Are you sure you want to delete this audio file?')) {
        return;
    }

    try {
        releaseLibraryItemAudio(jobId);
        // Give an in-flight Flask audio response a moment to observe the
        // browser abort before Windows filesystem deletion begins.
        await new Promise(resolve => setTimeout(resolve, 200));
        const response = await fetch(`/api/library/${jobId}`, {
            method: 'DELETE'
        });
        
        const data = await response.json();
        
        if (response.ok && data.success) {
            loadLibrary(); // Reload library
        } else {
            alert('Error deleting item: ' + data.error);
        }
    } catch (error) {
        console.error('Error deleting item:', error);
        alert('Failed to delete item');
    }
}

async function repairLibraryItem(jobId, trigger) {
    if (!confirm('This will recompile all chapter audio files from the individual audio file chunks and also recompile the full audiobook from the chapter audio files. Continue?')) {
        return;
    }
    const button = trigger instanceof HTMLElement ? trigger : null;
    const originalLabel = button ? button.innerHTML : null;
    if (button) {
        button.disabled = true;
        button.classList.add('is-busy');
        button.innerHTML = 'Rebuilding <span class="library-action-spinner" aria-hidden="true"></span>';
    }
    try {
        const response = await fetch(`/api/library/${jobId}/rebuild/all`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        });
        const data = await response.json();
        if (!data.success) {
            alert(`Rebuild failed: ${data.error || 'Unknown error'}`);
            return;
        }
        alert('Rebuild completed. Reloading library...');
        loadLibrary();
    } catch (error) {
        console.error('Rebuild library item error:', error);
        alert('Rebuild failed. Check the console for details.');
    } finally {
        if (button) {
            button.disabled = false;
            button.classList.remove('is-busy');
            button.innerHTML = originalLabel || 'Rebuild';
        }
    }
}

// Open chunk review modal for a library item
async function restoreToReview(jobId) {
    chunkReviewModalJobId = jobId;
    chunkReviewModalData = null;
    libraryChunkVoiceOverrides = {};
    chapterReviewMode = false;
    ensureChunkReviewCloseHandlers();

    const overlay = document.getElementById('chunk-review-modal-overlay');
    const modal = document.getElementById('chunk-review-modal');
    const body = document.getElementById('chunk-review-modal-body');
    const titleEl = document.getElementById('chunk-review-modal-title');

    if (overlay) overlay.classList.remove('hidden');
    if (modal) modal.classList.remove('hidden');
    if (body) body.innerHTML = '<div class="chunk-review-loading">Loading chunks...</div>';
    if (titleEl) titleEl.textContent = 'Review Chunks';
    setLibraryRecompileButtonState(true, 'Loading...');

    try {
        const response = await fetch(`/api/library/${jobId}/chunks`);
        const data = await response.json();

        if (!response.ok || !data.success) {
            if (body) body.innerHTML = `<div class="chunk-review-error">Error: ${data.error}</div>`;
            setLibraryRecompileButtonState(true, 'Unavailable');
            return;
        }

        chunkReviewModalData = data;
        renderChunkReviewModal(data);
        try {
            await requestLibraryReviewRestore(jobId);
            const reviewPayload = await fetchLibraryReviewPayload(jobId);
            syncLibraryChunkRegenState(jobId, reviewPayload);
        } catch (statusError) {
            console.error('Error preparing Library review state:', statusError);
            setLibraryRecompileButtonState(true, 'Status unavailable');
        }

    } catch (error) {
        console.error('Error loading chunks:', error);
        if (body) body.innerHTML = '<div class="chunk-review-error">Failed to load chunk data.</div>';
        setLibraryRecompileButtonState(true, 'Unavailable');
    }
}

function closeChunkReviewModal() {
    const overlay = document.getElementById('chunk-review-modal-overlay');
    const modal = document.getElementById('chunk-review-modal');
    const titleEl = document.getElementById('chunk-review-modal-title');

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
    stopLibraryBulkRegenWatcher();
    stopLibraryRecompileProgressWatcher();
    chunkReviewModalJobId = null;
    chunkReviewModalData = null;
    libraryChunkVoiceOverrides = {};
    chapterReviewMode = false;
    const recompileBtn = document.getElementById('chunk-review-recompile-btn');
    if (recompileBtn) {
        recompileBtn.dataset.recompileBusy = 'false';
        recompileBtn.disabled = true;
        recompileBtn.textContent = 'Recompile Audio';
    }
    if (titleEl) titleEl.textContent = 'Review Chunks';
}

function renderChunkReviewModal(data) {
    const body = document.getElementById('chunk-review-modal-body');
    if (!body) return;

    const chunks = data.chunks || [];
    const chapters = data.chapters || [];
    const books = data.books || [];
    const hasChapters = data.has_chapters || false;
    const hasBooks = data.has_books || false;
    const fullStoryAvailable = data.full_story_available || false;
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
                                <input type="range" class="bulk-speed-slider" data-speaker="${escapeHtml(speaker)}" min="0.5" max="2.0" step="0.01" value="1.0">
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
                    <div class="bulk-silence-section">
                        <div class="bulk-silence-row">
                            <span style="margin-right: 8px; font-size: 0.85em;">Silence:</span>
                            <label style="font-size: 0.85em;">Lead</label>
                            <input type="number" class="bulk-leading-silence" data-speaker="${escapeHtml(speaker)}" min="0" max="30" step="0.1" value="0" style="width: 60px;">
                            <span class="bulk-leading-silence-value" style="font-size: 0.85em; margin-right: 12px;">0s</span>
                            <label style="font-size: 0.85em;">Trail</label>
                            <input type="number" class="bulk-trailing-silence" data-speaker="${escapeHtml(speaker)}" min="0" max="30" step="0.1" value="0" style="width: 60px;">
                            <span class="bulk-trailing-silence-value" style="font-size: 0.85em;">0s</span>
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

    const chunksByChapter = new Map();
    chunks.forEach((chunk, idx) => {
        const chapterIdx = chunk.chapter_index ?? 0;
        if (!chunksByChapter.has(chapterIdx)) {
            chunksByChapter.set(chapterIdx, []);
        }
        chunksByChapter.get(chapterIdx).push({ chunk, idx });
    });

    const buildChapterSection = (chapter, chapterNum) => {
        const chapterIdx = chapter.index ?? chapterNum;
        let chapterChunks = chunksByChapter.get(chapterIdx) || [];
        if (chapterChunks.length === 0 && chapterIdx > 0) {
            chapterChunks = chunksByChapter.get(chapterIdx - 1) || [];
        }
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
                    <label class="chapter-select">
                        <input type="checkbox" class="chapter-rebuild-checkbox" data-chapter-index="${chapterIdx}">
                    </label>
                    <span class="chapter-title">${escapeHtml(chapterTitle)}</span>
                    <span class="chapter-chunk-count">${chapterChunks.length} chunks</span>
                    <button class="btn btn-xs btn-secondary chapter-rebuild-btn" data-chapter-index="${chapterIdx}" type="button">
                        Rebuild Chapter
                    </button>
                </div>
                <div class="chapter-chunks collapsed" data-chapter-index="${chapterIdx}">
                    ${chunkRows}
                </div>
            </div>
        `;
    };

    // Build chunk content - grouped by book/chapters or flat list
    let chunkContent = '';
    if (hasBooks && books.length > 0) {
        chunkContent = books.map((book, bookNum) => {
            const bookIdx = book.index ?? bookNum;
            const chapterIndices = new Set(book.chapter_indices || []);
            const bookChapters = chapters
                .filter(ch => (ch.book_index ?? bookIdx) === bookIdx || chapterIndices.has(ch.index))
                .sort((a, b) => (a.book_order ?? a.index ?? 0) - (b.book_order ?? b.index ?? 0));
            const chapterBlocks = bookChapters.map((chapter, chapterNum) => 
                buildChapterSection(chapter, chapterNum)
            ).join('');
            const bookTitle = book.title || `Book ${bookIdx + 1}`;
            return `
                <div class="book-section" data-book-index="${bookIdx}">
                    <div class="book-header" data-book-index="${bookIdx}">
                        <span class="book-toggle">▶</span>
                        <span class="book-title">${escapeHtml(bookTitle)}</span>
                        <span class="book-chapter-count">${bookChapters.length} chapters</span>
                    </div>
                    <div class="book-chapters collapsed" data-book-index="${bookIdx}">
                        ${chapterBlocks}
                    </div>
                </div>
            `;
        }).join('');
    } else if (hasChapters && chapters.length > 0) {
        chunkContent = chapters.map((chapter, chapterNum) => buildChapterSection(chapter, chapterNum)).join('');
    } else {
        chunkContent = chunks.map((chunk, idx) => renderLibraryChunkRow(jobId, chunk, engine, idx)).join('');
    }

    const chapterInfo = hasBooks
        ? `<span><strong>Books:</strong> ${books.length}</span><span><strong>Chapters:</strong> ${chapters.length}</span>`
        : (hasChapters ? `<span><strong>Chapters:</strong> ${chapters.length}</span>` : '');
    const fullStoryControls = '';
    const chapterRebuildControls = chapterReviewMode && data.review_chapter_index !== null
        ? `
            <button class="btn btn-sm btn-secondary" id="chunk-review-rebuild-chapter" type="button">
                Rebuild Chapter Audio File
            </button>
        `
        : '';
    const batchControls = chunks.length
        ? `
            <label class="chunk-review-select-all">
                <input type="checkbox" id="chunk-review-select-all">
                <span>Select all</span>
            </label>
            <button class="btn btn-sm btn-secondary" id="chunk-review-rebuild-selected" type="button" disabled>
                Regen Selected Speakers
            </button>
        `
        : '';

    body.innerHTML = `
        <div class="chunk-review-header">
            <div class="chunk-review-meta">
                <span><strong>Original Engine:</strong> ${formatEngineName(engine)}</span>
                ${chapterInfo}
                <span><strong>Chunks:</strong> ${chunks.length}</span>
            </div>
            <div class="chunk-review-actions">
                ${batchControls}
                ${chapterRebuildControls}
                ${fullStoryControls}
            </div>
        </div>
        <section id="library-regen-progress" class="library-regen-progress" hidden aria-live="polite">
            <div class="library-regen-progress-heading">
                <strong id="library-regen-progress-title">Regenerating selected speakers</strong>
                <span id="library-regen-progress-percent">0%</span>
            </div>
            <div class="library-regen-progress-track" role="progressbar" aria-valuemin="0" aria-valuemax="100" aria-valuenow="0">
                <div id="library-regen-progress-fill" class="library-regen-progress-fill"></div>
            </div>
            <div class="library-regen-progress-details">
                <span id="library-regen-progress-count">Preparing regeneration...</span>
                <span id="library-regen-progress-time">Elapsed: 0s · Estimating time remaining...</span>
            </div>
            <div id="library-regen-progress-current" class="library-regen-progress-current">
                Waiting for the first chunk to begin...
            </div>
            <div id="library-regen-progress-statuses" class="library-regen-progress-statuses"></div>
        </section>
        <div class="bulk-speaker-section">
            <div class="bulk-speaker-header">
                <strong>Bulk Speaker Regeneration</strong>
                <span class="bulk-speaker-hint">Select speakers and choose a voice to regenerate all their chunks</span>
            </div>
            ${speakerRows}
        </div>
        <div class="chunk-review-sequence">
            <button class="btn btn-sm btn-secondary chunk-review-play-icon" id="chunk-review-play-all" type="button" aria-label="Start audio review">
                ▶
            </button>
            <span class="chunk-review-play-label" id="chunk-review-play-all-label">Start Audio Review</span>
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
    if (hasBooks) {
        wireBookToggleEvents();
    }

    wireChunkReviewEvents(jobId, chunks, engine);
    wireChapterRebuildEvents(jobId);
    wireChapterReviewRebuildEvent(jobId, data.review_chapter_index);
    wireBatchRebuildEvents(jobId, chunks, engine);
}

function wireChapterReviewRebuildEvent(jobId, chapterIndex) {
    const button = document.getElementById('chunk-review-rebuild-chapter');
    if (!button || chapterIndex === null || chapterIndex === undefined) {
        return;
    }
    button.addEventListener('click', async (event) => {
        event.stopPropagation();
        const originalText = button.textContent;
        button.disabled = true;
        button.textContent = 'Rebuilding...';
        try {
            const response = await fetch(`/api/library/${jobId}/rebuild/chapter`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ chapter_index: Number(chapterIndex) })
            });
            const data = await response.json();
            if (!data.success) {
                throw new Error(data.error || 'Failed to rebuild chapter');
            }
            alert('Chapter rebuilt successfully.');
            loadLibrary();
        } catch (error) {
            console.error('Rebuild chapter error:', error);
            alert(error.message || 'Failed to rebuild chapter');
        } finally {
            button.disabled = false;
            button.textContent = originalText;
        }
    });
}

function wireBatchRebuildEvents(jobId, chunks, engine) {
    const selectAll = document.getElementById('chunk-review-select-all');
    const rebuildSelected = document.getElementById('chunk-review-rebuild-selected');
    const checkboxes = Array.from(document.querySelectorAll('.bulk-speaker-checkbox'));

    const updateSelectedState = () => {
        if (!rebuildSelected) return;
        const selected = checkboxes.filter(box => box.checked);
        rebuildSelected.disabled = selected.length === 0 || Boolean(libraryBulkRegenWatcher);
    };

    if (selectAll) {
        selectAll.addEventListener('change', () => {
            checkboxes.forEach(box => {
                box.checked = selectAll.checked;
            });
            updateSelectedState();
        });
    }

    checkboxes.forEach(box => {
        box.addEventListener('click', (event) => {
            event.stopPropagation();
        });
        box.addEventListener('change', () => {
            if (selectAll) {
                selectAll.checked = checkboxes.every(cb => cb.checked);
            }
            updateSelectedState();
        });
    });

    if (rebuildSelected) {
        rebuildSelected.addEventListener('click', async (event) => {
            event.stopPropagation();
            const selected = checkboxes.filter(box => box.checked);
            if (!selected.length) return;

            const missingVoices = [];
            const selectedCards = selected.map(box => box.closest('.bulk-speaker-card')).filter(Boolean);
            selectedCards.forEach(card => {
                const speaker = card.getAttribute('data-speaker') || 'default';
                const voiceSelect = card.querySelector('.bulk-speaker-voice-select');
                if (!voiceSelect || !voiceSelect.value) {
                    missingVoices.push(speaker);
                }
            });
            if (missingVoices.length) {
                alert(`Select a voice for: ${missingVoices.join(', ')}`);
                return;
            }

            const originalText = rebuildSelected.textContent;
            rebuildSelected.disabled = true;
            rebuildSelected.textContent = 'Regenerating...';
            try {
                await requestLibraryReviewRestore(jobId);
                setLibraryRecompileButtonState(true);
                const queuedChunkIds = [];
                for (const card of selectedCards) {
                    const speaker = card.getAttribute('data-speaker') || 'default';
                    const engineSelect = card.querySelector('.bulk-speaker-engine-select');
                    const engineOverride = engineSelect?.value || engine;
                    const button = card.querySelector('.bulk-speaker-regen');
                    if (button) {
                        const queued = await triggerBulkSpeakerRegen(
                            jobId,
                            speaker,
                            chunks,
                            engineOverride,
                            button,
                            { skipRestore: true }
                        );
                        if (!queued) {
                            throw new Error(`Failed to queue regeneration for ${speaker}`);
                        }
                        queuedChunkIds.push(...queued);
                    }
                }
                if (queuedChunkIds.length) {
                    startLibraryBulkRegenWatcher(jobId, queuedChunkIds);
                }
            } catch (error) {
                console.error('Bulk regen selected error:', error);
                alert(error.message || 'Failed to regenerate selected speakers');
            } finally {
                rebuildSelected.textContent = libraryBulkRegenWatcher
                    ? 'Regeneration in progress...'
                    : originalText;
                updateSelectedState();
            }
        });
    }

    updateSelectedState();
}

function wireChapterRebuildEvents(jobId) {
    const buttons = document.querySelectorAll('.chapter-rebuild-btn');
    buttons.forEach(btn => {
        btn.addEventListener('click', async (event) => {
            event.stopPropagation();
            const chapterIdx = btn.getAttribute('data-chapter-index');
            if (chapterIdx === null) return;
            const originalText = btn.textContent;
            btn.disabled = true;
            btn.textContent = 'Rebuilding...';
            try {
                const response = await fetch(`/api/library/${jobId}/rebuild/chapter`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ chapter_index: Number(chapterIdx) })
                });
                const data = await response.json();
                if (!data.success) {
                    throw new Error(data.error || 'Failed to rebuild chapter');
                }
                alert('Chapter rebuilt successfully.');
                loadLibrary();
            } catch (error) {
                console.error('Rebuild chapter error:', error);
                alert(error.message || 'Failed to rebuild chapter');
            } finally {
                btn.disabled = false;
                btn.textContent = originalText;
            }
        });
    });
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
                            <input type="range" class="chunk-speed-slider" data-chunk-id="${chunkId}" min="0.5" max="2.0" step="0.01" value="${(chunk.voice_assignment?.speed ?? chunk.fx_applied?.speed ?? 1.0).toFixed(2)}">
                            <span class="chunk-speed-value">${(chunk.voice_assignment?.speed ?? chunk.fx_applied?.speed ?? 1.0).toFixed(2)}x</span>
                        </div>
                        <div class="chunk-fx-control">
                            <label>Pitch</label>
                            <input type="range" class="chunk-pitch-slider" data-chunk-id="${chunkId}" min="-6" max="6" step="0.5" value="${(chunk.voice_assignment?.fx?.pitch ?? chunk.fx_applied?.pitch ?? 0).toFixed(1)}">
                            <span class="chunk-pitch-value">${(chunk.voice_assignment?.fx?.pitch ?? chunk.fx_applied?.pitch ?? 0).toFixed(1)}</span>
                        </div>
                        <button class="btn btn-sm btn-secondary library-chunk-preview-fx" data-chunk-id="${chunkId}" disabled>
                            ▶ Preview
                        </button>
                        <button class="btn btn-sm btn-primary library-chunk-apply-fx" data-chunk-id="${chunkId}" disabled>
                            Apply FX
                        </button>
                    </div>
                </div>
                <div class="chunk-detail-section chunk-silence-section">
                    <div class="chunk-silence-row">
                        <span style="margin-right: 8px; font-size: 0.85em;">Silence:</span>
                        <label style="font-size: 0.85em;">Lead</label>
                        <input type="number" class="chunk-leading-silence" data-chunk-id="${chunkId}" min="0" max="30" step="0.1" value="${((chunk.voice_assignment?.leading_silence_ms ?? chunk.silence_applied?.leading ?? 0) / 1000).toFixed(1)}" style="width: 60px;">
                        <span class="chunk-leading-silence-value" style="font-size: 0.85em; margin-right: 12px;">${((chunk.voice_assignment?.leading_silence_ms ?? chunk.silence_applied?.leading ?? 0) / 1000).toFixed(1)}s</span>
                        <label style="font-size: 0.85em;">Trail</label>
                        <input type="number" class="chunk-trailing-silence" data-chunk-id="${chunkId}" min="0" max="30" step="0.1" value="${((chunk.voice_assignment?.trailing_silence_ms ?? chunk.silence_applied?.trailing ?? 0) / 1000).toFixed(1)}" style="width: 60px;">
                        <span class="chunk-trailing-silence-value" style="font-size: 0.85em;">${((chunk.voice_assignment?.trailing_silence_ms ?? chunk.silence_applied?.trailing ?? 0) / 1000).toFixed(1)}s</span>
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
    stopChunkSequence(false);
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

function resetChunkSequenceHighlight() {
    chunkSequenceItems.forEach(({ card }) => {
        card.classList.remove('is-playing-sequence');
        card.classList.remove('is-playing-sequence-stopped');
    });
}

function stopChunkSequence(keepHighlight = false, preserveResume = false) {
    const lastIndex = chunkSequenceIndex;
    if (chunkSequenceAudio) {
        chunkSequenceAudio.pause();
        chunkSequenceAudio.currentTime = 0;
    }
    chunkSequenceAudio = null;
    chunkSequenceItems = [];
    chunkSequenceIndex = -1;
    if (keepHighlight && chunkSequenceLastCard) {
        if (lastIndex >= 0) {
            chunkSequenceResumeIndex = lastIndex;
        }
        resetChunkSequenceHighlight();
        chunkSequenceLastCard.classList.add('is-playing-sequence-stopped');
        chunkSequenceStartIndex = null;
    } else {
        resetChunkSequenceHighlight();
        if (!preserveResume) {
            chunkSequenceResumeIndex = null;
        }
    }
    if (chunkSequenceButton) {
        chunkSequenceButton.textContent = '▶';
        chunkSequenceButton.classList.remove('playing');
    }
    if (chunkSequenceLabel) {
        chunkSequenceLabel.textContent = 'Start Audio Review';
    }
    chunkSequenceButton = null;
    chunkSequenceLabel = null;
}

function setChunkSequenceStartFromCard(card) {
    if (!card) return;
    const rawIndex = card.getAttribute('data-idx');
    const index = rawIndex === null ? NaN : Number(rawIndex);
    if (!Number.isNaN(index)) {
        chunkSequenceStartIndex = index;
        chunkSequenceResumeIndex = index;
    }
}

function highlightManualChunkSelection(card) {
    if (!card) return;
    document.querySelectorAll('.library-chunk-card').forEach(item => {
        item.classList.remove('is-playing-sequence');
        item.classList.remove('is-playing-sequence-stopped');
    });
    card.classList.add('is-playing-sequence-stopped');
}

function startChunkSequence(items, startIndex = 0) {
    if (!items.length) return;
    const currentButton = chunkSequenceButton;
    const currentLabel = chunkSequenceLabel;
    stopChunkSequence(false, true);
    chunkSequenceButton = currentButton;
    chunkSequenceLabel = currentLabel;
    chunkSequenceItems = items;
    chunkSequenceIndex = Math.max(0, startIndex);
    chunkSequenceAudio = new Audio();
    const playIndex = (index) => {
        if (!chunkSequenceAudio) return;
        if (index >= chunkSequenceItems.length) {
            stopChunkSequence();
            return;
        }
        const item = chunkSequenceItems[index];
        if (!item || !item.url) {
            playIndex(index + 1);
            return;
        }
        chunkSequenceIndex = index;
        chunkSequenceResumeIndex = index;
        resetChunkSequenceHighlight();
        item.card.classList.add('is-playing-sequence');
        chunkSequenceLastCard = item.card;
        chunkSequenceAudio.src = item.url;
        chunkSequenceAudio.play().catch(() => {
            playIndex(index + 1);
        });
    };

    chunkSequenceAudio.addEventListener('ended', () => {
        playIndex(chunkSequenceIndex + 1);
    });
    chunkSequenceAudio.addEventListener('error', () => {
        playIndex(chunkSequenceIndex + 1);
    });
    playIndex(chunkSequenceIndex);
    if (chunkSequenceButton) {
        chunkSequenceButton.textContent = '■';
        chunkSequenceButton.classList.add('playing');
    }
    if (chunkSequenceLabel) {
        chunkSequenceLabel.textContent = 'Stop Audio Review';
    }
}

function wireChunkReviewEvents(jobId, chunks, engine) {
    const body = document.getElementById('chunk-review-modal-body');
    if (!body) return;

    const playAllButton = body.querySelector('#chunk-review-play-all');
    const playAllLabel = body.querySelector('#chunk-review-play-all-label');
    if (playAllButton) {
        playAllButton.addEventListener('click', () => {
            if (chunkSequenceAudio) {
                stopChunkSequence(true);
                return;
            }
            const cards = Array.from(body.querySelectorAll('.library-chunk-card'));
            const items = cards.map(card => {
                const playButton = card.querySelector('.library-chunk-play');
                return {
                    card,
                    url: playButton?.getAttribute('data-audio-url') || '',
                    index: Number(card.getAttribute('data-idx'))
                };
            }).filter(item => item.url);
            let startIndex = 0;
            const preferredIndex = chunkSequenceStartIndex ?? chunkSequenceResumeIndex;
            if (preferredIndex !== null && preferredIndex !== undefined) {
                const preferredPos = items.findIndex(item => item.index === preferredIndex);
                if (preferredPos >= 0) {
                    startIndex = preferredPos;
                } else {
                    const nextPos = items.findIndex(item => item.index > preferredIndex);
                    if (nextPos >= 0) {
                        startIndex = nextPos;
                    }
                }
            }
            chunkSequenceButton = playAllButton;
            chunkSequenceLabel = playAllLabel || null;
            startChunkSequence(items, startIndex);
        });
    }

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
                    const card = summary.closest('.library-chunk-card');
                    setChunkSequenceStartFromCard(card);
                    highlightManualChunkSelection(card);
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
            const card = btn.closest('.library-chunk-card');
            setChunkSequenceStartFromCard(card);
            highlightManualChunkSelection(card);
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

    body.querySelectorAll('.library-chunk-voice-select').forEach(select => {
        select.addEventListener('change', () => {
            const chunkId = select.getAttribute('data-chunk-id');
            if (!chunkId) return;
            const card = select.closest('.library-chunk-card');
            const engineSelect = card?.querySelector('.library-chunk-engine-select');
            const engineOverride = engineSelect?.value
                || engineSelect?.dataset.selectedEngine
                || engineSelect?.dataset.currentEngine
                || '';
            const normalizedEngine = (engineOverride || engine || '').toLowerCase().replace(/[_-]/g, '');
            const value = (select.value || '').trim();

            if (!value) {
                delete libraryChunkVoiceOverrides[chunkId];
                return;
            }

            if (normalizedEngine.includes('chatterbox')
                || normalizedEngine.includes('voxcpm')
                || normalizedEngine.includes('pockettts')
                || (normalizedEngine.includes('qwen3') && normalizedEngine.includes('clone'))
                || (normalizedEngine.includes('omnivoice') && normalizedEngine.includes('clone'))
                || normalizedEngine.includes('dotstts')
            ) {
                libraryChunkVoiceOverrides[chunkId] = { audio_prompt_path: value };
            } else {
                const voiceData = libraryVoiceMap.get(value);
                libraryChunkVoiceOverrides[chunkId] = {
                    voice: value,
                    lang_code: voiceData?.langCode || (
                        normalizedEngine.includes('edgetts') || normalizedEngine.includes('elevenlabs') || normalizedEngine.includes('openaitts') ? '' : 'a'
                    ),
                    ...(normalizedEngine.includes('azurespeech')
                        ? { extra: { locale: voiceData?.langCode || '' } }
                        : {}),
                };
            }
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

    // Individual chunk silence inputs
    body.querySelectorAll('.chunk-leading-silence').forEach(input => {
        input.addEventListener('input', () => {
            const valueSpan = input.parentElement.querySelector('.chunk-leading-silence-value');
            if (valueSpan) valueSpan.textContent = `${parseFloat(input.value).toFixed(1)}s`;
        });
    });

    body.querySelectorAll('.chunk-trailing-silence').forEach(input => {
        input.addEventListener('input', () => {
            const valueSpan = input.parentElement.querySelector('.chunk-trailing-silence-value');
            if (valueSpan) valueSpan.textContent = `${parseFloat(input.value).toFixed(1)}s`;
        });
    });

    // Bulk speaker silence inputs
    body.querySelectorAll('.bulk-leading-silence').forEach(input => {
        input.addEventListener('input', () => {
            const valueSpan = input.parentElement.querySelector('.bulk-leading-silence-value');
            if (valueSpan) valueSpan.textContent = `${parseFloat(input.value).toFixed(1)}s`;
        });
    });

    body.querySelectorAll('.bulk-trailing-silence').forEach(input => {
        input.addEventListener('input', () => {
            const valueSpan = input.parentElement.querySelector('.bulk-trailing-silence-value');
            if (valueSpan) valueSpan.textContent = `${parseFloat(input.value).toFixed(1)}s`;
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
        || normalizedEngine.includes('pockettts')
        || (normalizedEngine.includes('qwen3') && normalizedEngine.includes('clone'))
        || normalizedEngine.replace(/[_-]/g, '').includes('dotstts');
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

const libraryCloudCatalogCache = new Map();
const libraryCloudCatalogRequests = new Map();

async function getLibraryCloudCatalog(engineName) {
    const normalized = (engineName || '').toLowerCase().replace(/[_-]/g, '');
    const provider = normalized.includes('edgetts')
        ? 'edge_tts'
        : (normalized.includes('elevenlabs') ? 'elevenlabs'
            : (normalized.includes('openaitts') ? 'openai_tts'
                : (normalized.includes('localaitts') ? 'localai_tts' : '')));
    if (!provider) return { success: false, voices: [] };
    if (libraryCloudCatalogCache.has(provider)) return libraryCloudCatalogCache.get(provider);
    if (!libraryCloudCatalogRequests.has(provider)) {
        const endpoint = provider === 'edge_tts' ? '/api/edge-tts/voices'
            : (provider === 'elevenlabs' ? '/api/elevenlabs/catalog'
                : (provider === 'localai_tts' ? '/api/localai-tts/catalog' : '/api/openai-tts/catalog'));
        const request = fetch(endpoint)
            .then(response => response.json())
            .then(data => {
                if (data.success) libraryCloudCatalogCache.set(provider, data);
                libraryCloudCatalogRequests.delete(provider);
                return data;
            })
            .catch(error => {
                libraryCloudCatalogRequests.delete(provider);
                throw error;
            });
        libraryCloudCatalogRequests.set(provider, request);
    }
    return libraryCloudCatalogRequests.get(provider);
}

function mapLibraryCloudVoices(data, provider) {
    return (data?.voices || []).map(voice => ({
        id: voice.short_name || voice.voice_id,
        name: `${voice.display_name || voice.short_name || voice.voice_id}${voice.locale ? ` (${voice.locale_name || voice.locale})` : ''}`,
        langCode: voice.locale || '',
        gender: voice.gender || '',
        language: voice.locale || '',
        isEdgeTts: provider === 'edge_tts',
        isElevenLabs: provider === 'elevenlabs',
        isOpenAITts: provider === 'openai_tts',
        isLocalAITts: provider === 'localai_tts',
        disabled: Boolean(voice.disabled),
        disabledReason: voice.disabled_reason || '',
        isPrompt: false,
    }));
}

function appendLocalAIFreeformOption(select) {
    if (!select || Array.from(select.options).some(option => option.value === '__localai_custom__')) return;
    const option = document.createElement('option');
    option.value = '__localai_custom__';
    option.textContent = 'Type a custom voice / speaker ID…';
    select.appendChild(option);
}

function resolveLocalAIFreeformSelection(select) {
    if (!select || select.value !== '__localai_custom__') return null;
    const voice = window.prompt('Enter the voice name or speaker ID accepted by this LocalAI model:', '')?.trim();
    if (!voice) {
        select.value = '';
        return { cancelled: true, voice: '', language: '' };
    }
    const language = window.prompt('Optional language value for this model (leave blank for its default):', '')?.trim() || '';
    const option = document.createElement('option');
    option.value = voice;
    option.textContent = `${voice}${language ? ` (${language})` : ''} · custom`;
    select.insertBefore(option, Array.from(select.options).find(item => item.value === '__localai_custom__') || null);
    select.value = voice;
    libraryVoiceMap.set(voice, { id: voice, name: voice, langCode: language, isLocalAITts: true });
    return { cancelled: false, voice, language };
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
    const isOmniClone = normalizedEngine.includes('omnivoice') && normalizedEngine.includes('clone');
    const isDotsTts = normalizedEngine.includes('dotstts');
    const isAzureSpeech = normalizedEngine.includes('azurespeech');
    const isEdgeTts = normalizedEngine.includes('edgetts');
    const isElevenLabs = normalizedEngine.includes('elevenlabs');
    const isOpenAITts = normalizedEngine.includes('openaitts');
    const isLocalAITts = normalizedEngine.includes('localaitts');
    const isPocketPreset = normalizedEngine.includes('pocketttspreset');
    const isPocket = normalizedEngine.includes('pockettts') && !isPocketPreset;
    const usesVoicePrompts = isChatterbox || isVoxCPM || isQwenClone || isOmniClone || isDotsTts || isPocket;

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
        } else if (isPocketPreset) {
            const response = await fetch('/api/pocket-tts/voices');
            const data = await response.json();
            if (data.success && data.voices) {
                voices = data.voices.map(voice => ({
                    id: voice,
                    name: voice,
                    isPrompt: false
                }));
            }
        } else if (isAzureSpeech) {
            const response = await fetch('/api/azure-speech/voices');
            const data = await response.json();
            if (data.success && data.voices) {
                voices = data.voices.map(voice => ({
                    id: voice.short_name,
                    name: `${voice.display_name || voice.short_name} (${voice.locale_name || voice.locale})`,
                    langCode: voice.locale,
                    styles: voice.styles || [],
                    roles: voice.roles || [],
                    isAzureSpeech: true,
                }));
            }
        } else if (isEdgeTts || isElevenLabs || isOpenAITts || isLocalAITts) {
            const data = await getLibraryCloudCatalog(engine);
            if (data.success) {
                voices = mapLibraryCloudVoices(data, isEdgeTts ? 'edge_tts'
                    : (isElevenLabs ? 'elevenlabs' : (isLocalAITts ? 'localai_tts' : 'openai_tts')));
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
        'pockettts': 0,
        'pocketttspreset': 0,
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

    let voicePromptCache = null;
    let voicePromptRequest = null;
    let qwenMetadataCache = null;
    let qwenMetadataRequest = null;
    let voicesCache = null;
    let voicesRequest = null;
    let pocketTtsVoicesCache = null;
    let pocketTtsVoicesRequest = null;
    let azureSpeechVoicesCache = null;
    let azureSpeechVoicesRequest = null;

    async function getVoicePromptsCached() {
        if (voicePromptCache) return voicePromptCache;
        if (!voicePromptRequest) {
            voicePromptRequest = fetch('/api/voice-prompts')
                .then(response => response.json())
                .then(data => {
                    voicePromptCache = data;
                    return data;
                })
                .catch(err => {
                    voicePromptRequest = null;
                    throw err;
                });
        }
        return voicePromptRequest;
    }

    async function getQwenMetadataCached() {
        if (qwenMetadataCache) return qwenMetadataCache;
        if (!qwenMetadataRequest) {
            qwenMetadataRequest = fetch('/api/qwen3/metadata')
                .then(response => response.json())
                .then(data => {
                    qwenMetadataCache = data;
                    return data;
                })
                .catch(err => {
                    qwenMetadataRequest = null;
                    throw err;
                });
        }
        return qwenMetadataRequest;
    }

    async function getVoicesCached() {
        if (voicesCache) return voicesCache;
        if (!voicesRequest) {
            voicesRequest = fetch('/api/voices')
                .then(response => response.json())
                .then(data => {
                    voicesCache = data;
                    return data;
                })
                .catch(err => {
                    voicesRequest = null;
                    throw err;
                });
        }
        return voicesRequest;
    }

    async function getPocketTtsVoicesCached() {
        if (pocketTtsVoicesCache) return pocketTtsVoicesCache;
        if (!pocketTtsVoicesRequest) {
            pocketTtsVoicesRequest = fetch('/api/pocket-tts/voices')
                .then(response => response.json())
                .then(data => {
                    pocketTtsVoicesCache = data;
                    return data;
                })
                .catch(err => {
                    pocketTtsVoicesRequest = null;
                    throw err;
                });
        }
        return pocketTtsVoicesRequest;
    }

    async function getAzureSpeechVoicesCached() {
        if (azureSpeechVoicesCache) return azureSpeechVoicesCache;
        if (!azureSpeechVoicesRequest) {
            azureSpeechVoicesRequest = fetch('/api/azure-speech/voices')
                .then(response => response.json())
                .then(data => {
                    azureSpeechVoicesCache = data;
                    return data;
                })
                .catch(err => {
                    azureSpeechVoicesRequest = null;
                    throw err;
                });
        }
        return azureSpeechVoicesRequest;
    }

    async function populatePromptFilterOptions(genderSelect, languageSelect) {
        if (!genderSelect || !languageSelect) return;
        try {
            const data = await getVoicePromptsCached();
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

    async function populateChunkVoiceSelect(select, chunkId, engineName, filters = null, currentLabel = '', selectedValue = '') {
        engineName = (engineName || '').toLowerCase().replace(/[_-]/g, '');
        const isPocketPreset = engineName.includes('pocketttspreset');
        const usesPrompts = engineName.includes('chatterbox')
            || engineName.includes('voxcpm')
            || (engineName.includes('pockettts') && !isPocketPreset)
            || (engineName.includes('qwen3') && engineName.includes('clone'))
            || (engineName.includes('omnivoice') && engineName.includes('clone'))
            || engineName.includes('indextts')
            || engineName.includes('dotstts');
        const isQwenEngine = engineName.includes('qwen3');
        const isKittenTts = engineName.includes('kittentts');
        const isAzureSpeech = engineName.includes('azurespeech');
        const isEdgeTts = engineName.includes('edgetts');
        const isElevenLabs = engineName.includes('elevenlabs');
        const isOpenAITts = engineName.includes('openaitts');
        const isLocalAITts = engineName.includes('localaitts');
        const minDuration = getMinDuration(engineName);
        const activeFilters = filters || libraryVoiceFilters;
        let chunkVoices = [];
        
        try {
            if (usesPrompts) {
                const data = await getVoicePromptsCached();
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
                const data = await getQwenMetadataCached();
                if (data.success && data.speakers) {
                    chunkVoices = data.speakers.map(speaker => ({
                        id: speaker,
                        name: speaker,
                        isQwen: true
                    }));
                }
            } else if (isPocketPreset) {
                const data = await getPocketTtsVoicesCached();
                if (data.success && data.voices) {
                    chunkVoices = data.voices.map(voice => ({
                        id: voice,
                        name: voice,
                        isPrompt: false
                    }));
                }
            } else if (isKittenTts) {
                chunkVoices = ['Bella', 'Jasper', 'Luna', 'Bruno', 'Rosie', 'Hugo', 'Kiki', 'Leo']
                    .map(voice => ({ id: voice, name: voice, isPrompt: false }));
            } else if (isAzureSpeech) {
                const data = await getAzureSpeechVoicesCached();
                if (data.success && data.voices) {
                    chunkVoices = data.voices.map(voice => ({
                        id: voice.short_name,
                        name: `${voice.display_name || voice.short_name} (${voice.locale_name || voice.locale})`,
                        langCode: voice.locale,
                        styles: voice.styles || [],
                        roles: voice.roles || [],
                        isAzureSpeech: true,
                    }));
                }
            } else if (isEdgeTts || isElevenLabs || isOpenAITts || isLocalAITts) {
                const data = await getLibraryCloudCatalog(engineName);
                if (data.success) {
                    chunkVoices = mapLibraryCloudVoices(data, isEdgeTts ? 'edge_tts'
                        : (isElevenLabs ? 'elevenlabs' : (isLocalAITts ? 'localai_tts' : 'openai_tts')));
                }
            } else {
                const data = await getVoicesCached();
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
        chunkVoices.forEach(voice => libraryVoiceMap.set(voice.id, voice));
        
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
            if (v.disabled) {
                opt.disabled = true;
                opt.title = v.disabledReason || '';
            }
            
            // Disable if duration is too short for this engine
            if (minDuration > 0 && v.duration != null && v.duration < minDuration) {
                opt.disabled = true;
                opt.style.color = '#ff6b6b';
                opt.textContent = `${displayName}${durationLabel} (too short)`;
            }
            
            select.appendChild(opt);
        });
        if (isLocalAITts) appendLocalAIFreeformOption(select);
        
        if (selectedValue) {
            select.value = selectedValue;
            if (select.value !== selectedValue) {
                select.value = '';
            }
        }
    }

    // Helper to populate bulk speaker voice select based on engine
    async function populateBulkVoiceSelect(select, speaker, engineName, filters = null) {
        engineName = (engineName || '').toLowerCase().replace(/[_-]/g, '');
        const isPocketPreset = engineName.includes('pocketttspreset');
        const usesPrompts = engineName.includes('chatterbox')
            || engineName.includes('voxcpm')
            || (engineName.includes('pockettts') && !isPocketPreset)
            || (engineName.includes('qwen3') && engineName.includes('clone'))
            || (engineName.includes('omnivoice') && engineName.includes('clone'))
            || engineName.includes('indextts')
            || engineName.includes('dotstts');
        const isQwenEngine = engineName.includes('qwen3');
        const isKittenTts = engineName.includes('kittentts');
        const isAzureSpeech = engineName.includes('azurespeech');
        const isEdgeTts = engineName.includes('edgetts');
        const isElevenLabs = engineName.includes('elevenlabs');
        const isOpenAITts = engineName.includes('openaitts');
        const isLocalAITts = engineName.includes('localaitts');
        const minDuration = getMinDuration(engineName);
        const activeFilters = filters || libraryVoiceFilters;
        let bulkVoices = [];
        
        try {
            if (usesPrompts) {
                const data = await getVoicePromptsCached();
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
                const data = await getQwenMetadataCached();
                if (data.success && data.speakers) {
                    bulkVoices = data.speakers.map(speaker => ({
                        id: speaker,
                        name: speaker,
                        isQwen: true
                    }));
                }
            } else if (isPocketPreset) {
                const data = await getPocketTtsVoicesCached();
                if (data.success && data.voices) {
                    bulkVoices = data.voices.map(voice => ({
                        id: voice,
                        name: voice,
                        isPrompt: false
                    }));
                }
            } else if (isKittenTts) {
                bulkVoices = ['Bella', 'Jasper', 'Luna', 'Bruno', 'Rosie', 'Hugo', 'Kiki', 'Leo']
                    .map(voice => ({ id: voice, name: voice, isPrompt: false }));
            } else if (isAzureSpeech) {
                const data = await getAzureSpeechVoicesCached();
                if (data.success && data.voices) {
                    bulkVoices = data.voices.map(voice => ({
                        id: voice.short_name,
                        name: `${voice.display_name || voice.short_name} (${voice.locale_name || voice.locale})`,
                        langCode: voice.locale,
                        styles: voice.styles || [],
                        roles: voice.roles || [],
                        isAzureSpeech: true,
                    }));
                }
            } else if (isEdgeTts || isElevenLabs || isOpenAITts || isLocalAITts) {
                const data = await getLibraryCloudCatalog(engineName);
                if (data.success) {
                    bulkVoices = mapLibraryCloudVoices(data, isEdgeTts ? 'edge_tts'
                        : (isElevenLabs ? 'elevenlabs' : (isLocalAITts ? 'localai_tts' : 'openai_tts')));
                }
            } else {
                const data = await getVoicesCached();
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
        bulkVoices.forEach(voice => libraryVoiceMap.set(voice.id, voice));
        
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
            if (v.disabled) {
                opt.disabled = true;
                opt.title = v.disabledReason || '';
            }
            
            // Disable if duration is too short for this engine
            if (minDuration > 0 && v.duration != null && v.duration < minDuration) {
                opt.disabled = true;
                opt.style.color = '#ff6b6b';
                opt.textContent = `${displayName}${durationLabel} (too short)`;
            }
            
            select.appendChild(opt);
        });
        if (isLocalAITts) appendLocalAIFreeformOption(select);
    }

    const chunkById = new Map(chunks.map(chunk => [chunk.id, chunk]));

    // Populate chunk engine selects
    body.querySelectorAll('.library-chunk-engine-select').forEach(select => {
        const chunkId = select.getAttribute('data-chunk-id');
        const chunk = chunkById.get(chunkId);
        const currentEngine = chunk?.engine || engine;
        const currentEngineLabel = currentEngine ? `Current: ${formatEngineName(currentEngine)}` : '-- Same engine --';
        const normalizedCurrentEngine = (currentEngine || '').toLowerCase();
        select.dataset.currentEngine = currentEngine || '';
        select.dataset.selectedEngine = '';
        select.innerHTML = `
            <option value="">${currentEngineLabel}</option>
            <option value="kokoro">Kokoro · Local</option>
            <option value="kokoro_replicate">Kokoro · Replicate</option>
            <option value="chatterbox_turbo_local">Chatterbox · Local</option>
            <option value="chatterbox_turbo_replicate">Chatterbox · Replicate</option>
            <option value="voxcpm_local">VoxCPM 1.5</option>
            <option value="pocket_tts">Pocket TTS · Clone Voices</option>
            <option value="pocket_tts_preset">Pocket TTS · Preset Voices</option>
            <option value="qwen3_custom">Qwen3-TTS</option>
            <option value="qwen3_clone">Qwen3-TTS · Voice Clone</option>
            <option value="omnivoice_clone">OmniVoice · Voice Clone</option>
            <option value="omnivoice_design">OmniVoice · Voice Design</option>
            <option value="kitten_tts">KittenTTS</option>
            <option value="index_tts">IndexTTS</option>
            <option value="dots_tts">Dot.TTS · Voice Clone</option>
            <option value="audio8_tts">Audio8 TTS · Voice Clone</option>
            <option value="azure_speech">Microsoft Azure Speech</option>
            <option value="edge_tts">Microsoft Edge TTS (Experimental)</option>
            <option value="elevenlabs">ElevenLabs</option>
            <option value="openai_tts">OpenAI-compatible TTS</option>
            <option value="localai_tts">LocalAI TTS</option>
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
            const voiceAssignment = chunk?.voice_assignment || {};
            const override = libraryChunkVoiceOverrides[chunkId] || {};
            const selectedValue = override.audio_prompt_path || override.voice
                || voiceAssignment.audio_prompt_path || voiceAssignment.voice || '';
            const filters = getPromptFilters(regenSection, '.chunk-voice-filter-gender', '.chunk-voice-filter-language');
            populateChunkVoiceSelect(voiceSelect, chunkId, currentEngine, filters, currentVoiceLabel, selectedValue);
        }
        const normalizedEngineValue = (currentEngine || '').toLowerCase();
        const isQwen = normalizedEngineValue.includes('qwen3') && !normalizedEngineValue.includes('clone');
        const usesPrompts = normalizedEngineValue.includes('chatterbox')
            || normalizedEngineValue.includes('voxcpm')
            || (normalizedEngineValue.includes('pockettts') && !normalizedEngineValue.includes('pocketttspreset'))
            || (normalizedEngineValue.includes('qwen3') && normalizedEngineValue.includes('clone'))
            || (normalizedEngineValue.includes('omnivoice') && normalizedEngineValue.includes('clone'))
            || normalizedEngineValue.replace(/[_-]/g, '').includes('dotstts');
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
                const voiceAssignment = chunk?.voice_assignment || {};
                const override = libraryChunkVoiceOverrides[chunkId] || {};
                const selectedValue = override.audio_prompt_path || override.voice
                    || voiceAssignment.audio_prompt_path || voiceAssignment.voice || '';
                const filters = getPromptFilters(regenSection, '.chunk-voice-filter-gender', '.chunk-voice-filter-language');
                populateChunkVoiceSelect(voiceSelect, chunkId, currentEngine, filters, currentVoiceLabel, selectedValue);
            });
        }
        if (languageFilter) {
            languageFilter.addEventListener('change', () => {
                if (!voiceSelect) return;
                const currentVoiceLabel = voiceSelect.dataset.currentVoiceLabel || '';
                const voiceAssignment = chunk?.voice_assignment || {};
                const override = libraryChunkVoiceOverrides[chunkId] || {};
                const selectedValue = override.audio_prompt_path || override.voice
                    || voiceAssignment.audio_prompt_path || voiceAssignment.voice || '';
                const filters = getPromptFilters(regenSection, '.chunk-voice-filter-gender', '.chunk-voice-filter-language');
                populateChunkVoiceSelect(voiceSelect, chunkId, currentEngine, filters, currentVoiceLabel, selectedValue);
            });
        }

        // When engine changes, repopulate the voice dropdown for this chunk and show/hide Qwen3 options
        select.addEventListener('change', async () => {
            const selectedEngine = select.value || currentEngine || engine;
            select.dataset.selectedEngine = selectedEngine || '';
            const regenSection = select.closest('.chunk-regen-section');
            const voiceSelect = regenSection?.querySelector('.library-chunk-voice-select');
            const qwen3Options = regenSection?.querySelector('.chunk-qwen3-options');
            const promptFilters = regenSection?.querySelector('.chunk-prompt-filters');
            const genderFilter = regenSection?.querySelector('.chunk-voice-filter-gender');
            const languageFilter = regenSection?.querySelector('.chunk-voice-filter-language');
            
            if (voiceSelect) {
                const currentVoiceLabel = voiceSelect.dataset.currentVoiceLabel || '';
                const voiceAssignment = chunk?.voice_assignment || {};
                const override = libraryChunkVoiceOverrides[chunkId] || {};
                const selectedValue = override.audio_prompt_path || override.voice
                    || voiceAssignment.audio_prompt_path || voiceAssignment.voice || '';
                const filters = getPromptFilters(regenSection, '.chunk-voice-filter-gender', '.chunk-voice-filter-language');
                await populateChunkVoiceSelect(voiceSelect, chunkId, selectedEngine, filters, currentVoiceLabel, selectedValue);
            }
            
            // Show/hide Qwen3 options based on engine
            const normalizedSelectedEngine = selectedEngine.toLowerCase();
            const isQwen = normalizedSelectedEngine.includes('qwen3')
                && !normalizedSelectedEngine.includes('clone');
            const usesPrompts = normalizedSelectedEngine.includes('chatterbox')
                || normalizedSelectedEngine.includes('voxcpm')
                || (normalizedSelectedEngine.includes('pockettts') && !normalizedSelectedEngine.includes('pocketttspreset'))
                || (normalizedSelectedEngine.includes('qwen3') && normalizedSelectedEngine.includes('clone'))
                || normalizedSelectedEngine.replace(/[_-]/g, '').includes('dotstts');
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
            <option value="kokoro">Kokoro · Local</option>
            <option value="kokoro_replicate">Kokoro · Replicate</option>
            <option value="chatterbox_turbo_local">Chatterbox · Local</option>
            <option value="chatterbox_turbo_replicate">Chatterbox · Replicate</option>
            <option value="voxcpm_local">VoxCPM 1.5</option>
            <option value="pocket_tts">Pocket TTS · Clone Voices</option>
            <option value="pocket_tts_preset">Pocket TTS · Preset Voices</option>
            <option value="qwen3_custom">Qwen3-TTS</option>
            <option value="qwen3_clone">Qwen3-TTS · Voice Clone</option>
            <option value="omnivoice_clone">OmniVoice · Voice Clone</option>
            <option value="omnivoice_design">OmniVoice · Voice Design</option>
            <option value="kitten_tts">KittenTTS</option>
            <option value="index_tts">IndexTTS</option>
            <option value="dots_tts">Dot.TTS · Voice Clone</option>
            <option value="audio8_tts">Audio8 TTS · Voice Clone</option>
            <option value="azure_speech">Microsoft Azure Speech</option>
            <option value="edge_tts">Microsoft Edge TTS (Experimental)</option>
            <option value="elevenlabs">ElevenLabs</option>
            <option value="openai_tts">OpenAI-compatible TTS</option>
            <option value="localai_tts">LocalAI TTS</option>
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
                || (normalizedSelectedEngine.includes('qwen3') && normalizedSelectedEngine.includes('clone'))
                || (normalizedSelectedEngine.includes('omnivoice') && normalizedSelectedEngine.includes('clone'))
                || normalizedSelectedEngine.replace(/[_-]/g, '').includes('dotstts');
            if (promptFilters) {
                promptFilters.style.display = usesPrompts ? 'block' : 'none';
                if (usesPrompts) {
                    await populatePromptFilterOptions(genderFilter, languageFilter);
                }
            }
            if (qwen3Options) {
                qwen3Options.style.display = isQwen ? 'block' : 'none';
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
            || (normalizedEngine.includes('pockettts') && !normalizedEngine.includes('pocketttspreset'))
            || (normalizedEngine.includes('qwen3') && normalizedEngine.includes('clone'))
            || (normalizedEngine.includes('omnivoice') && normalizedEngine.includes('clone'))
            || normalizedEngine.replace(/[_-]/g, '').includes('dotstts');
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

async function triggerBulkSpeakerRegen(
    jobId,
    speaker,
    chunks,
    engine,
    button,
    { skipRestore = false } = {}
) {
    const body = document.getElementById('chunk-review-modal-body');
    const card = button.closest('.bulk-speaker-card');
    const select = card?.querySelector('.bulk-speaker-voice-select');
    const normalizedEngine = (engine || '').toLowerCase().replace(/[_-]/g, '');
    const isLocalAI = normalizedEngine.includes('localaitts');
    const freeform = isLocalAI ? resolveLocalAIFreeformSelection(select) : null;
    if (freeform?.cancelled) return;
    const voiceValue = freeform?.voice || select?.value;

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

    const isChatterbox = normalizedEngine.includes('chatterbox');
    const isVoxCPM = normalizedEngine.includes('voxcpm');
    const isQwenEngine = normalizedEngine.includes('qwen3');
    const isQwenClone = normalizedEngine.includes('qwen3') && normalizedEngine.includes('clone');
    const isOmniClone = normalizedEngine.includes('omnivoice') && normalizedEngine.includes('clone');
    const isDotsTts = normalizedEngine.includes('dotstts');
    const isAzureSpeech = normalizedEngine.includes('azurespeech');
    const usesVoicePrompts = isChatterbox || isVoxCPM || isQwenClone || isOmniClone || isDotsTts;

    // Build voice payload based on engine type
    const voiceData = libraryVoiceMap.get(voiceValue || '');
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
    } else if (isLocalAI) {
        voicePayload = {
            voice: voiceValue,
            lang_code: freeform?.language || voiceData?.langCode || '',
        };
    } else {
        voicePayload = {
            voice: voiceValue,
            lang_code: voiceData?.langCode || (
                normalizedEngine.includes('edgetts') || normalizedEngine.includes('elevenlabs') || normalizedEngine.includes('openaitts') ? '' : 'a'
            ),
            ...(isAzureSpeech ? { extra: { locale: voiceData?.langCode || '' } } : {}),
        };
    }

    // Attach fx/speed from the bulk speaker sliders
    const bulkSpeedSlider = card?.querySelector('.bulk-speed-slider');
    const bulkPitchSlider = card?.querySelector('.bulk-pitch-slider');
    const bulkLeadingSilence = card?.querySelector('.bulk-leading-silence');
    const bulkTrailingSilence = card?.querySelector('.bulk-trailing-silence');
    const bulkSpeed = parseFloat(bulkSpeedSlider?.value || 1.0);
    const bulkPitch = parseFloat(bulkPitchSlider?.value || 0);
    const leadingSilenceSec = parseFloat(bulkLeadingSilence?.value || 0);
    const trailingSilenceSec = parseFloat(bulkTrailingSilence?.value || 0);
    if (Math.abs(bulkSpeed - 1.0) > 0.005) {
        voicePayload = { ...(voicePayload || {}), speed: parseFloat(bulkSpeed.toFixed(2)) };
    }
    if (Math.abs(bulkPitch) > 0.01) {
        voicePayload = { ...(voicePayload || {}), fx: { ...((voicePayload || {}).fx || {}), pitch: parseFloat(bulkPitch.toFixed(1)) } };
    }
    // Always send silence values (even when zero) so backend knows to explicitly remove existing silence
    voicePayload = { ...(voicePayload || {}), leading_silence_ms: Math.round(leadingSilenceSec * 1000), trailing_silence_ms: Math.round(trailingSilenceSec * 1000) };

    button.disabled = true;
    button.textContent = `Regenerating ${speakerChunks.length}...`;

    try {
        if (!skipRestore) {
            await requestLibraryReviewRestore(jobId);
        }
        setLibraryRecompileButtonState(true);

        const queuedChunkIds = [];
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
            if (!response.ok || !data.success) {
                throw new Error(
                    data.error || `Failed to queue chunk ${chunkId} for ${speaker}`
                );
            }
            updateLibraryChunkStatus(chunkId, 'queued');
            queuedChunkIds.push(chunkId);
        }

        if (!skipRestore && queuedChunkIds.length) {
            startLibraryBulkRegenWatcher(jobId, queuedChunkIds);
        }
        button.textContent = 'Queued!';
        setTimeout(() => {
            button.textContent = 'Regenerate All';
            button.disabled = false;
        }, 2000);
        return queuedChunkIds;

    } catch (error) {
        console.error('Bulk regen error:', error);
        if (!skipRestore) {
            alert(error.message || 'Failed to queue bulk regeneration');
        }
        button.textContent = 'Regenerate All';
        button.disabled = false;
        await refreshLibraryRecompileState(jobId);
        return false;
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

    setRegenButtonBusy(button, true, '⟳ Queued...');

    // Get engine override from per-chunk dropdown
    const chunkEngineSelect = card?.querySelector('.library-chunk-engine-select');
    const resolvedEngine = chunkEngineSelect?.value
        || chunkEngineSelect?.dataset.selectedEngine
        || chunkEngineSelect?.dataset.currentEngine
        || (chunkReviewModalData?.chunks || []).find(chunk => chunk.id === chunkId)?.engine
        || chunkReviewModalData?.engine
        || '';
    
    // Get voice selection from per-chunk dropdown or stored override
    const voiceSelect = card?.querySelector('.library-chunk-voice-select');
    let voiceValue = voiceSelect?.value || '';
    const storedOverride = libraryChunkVoiceOverrides[chunkId] || {};
    const selectedVoiceValue = voiceValue || storedOverride.audio_prompt_path || storedOverride.voice || '';
    
    // Build voice payload based on engine type
    let voicePayload = libraryChunkVoiceOverrides[chunkId] || {};
    const originalChunk = (chunkReviewModalData?.chunks || []).find(chunk => chunk.id === chunkId);
    const normalizedEngine = (resolvedEngine || originalChunk?.engine || chunkReviewModalData?.engine || '')
        .toLowerCase()
        .replace(/[_-]/g, '');
    const isLocalAI = normalizedEngine.includes('localaitts');
    const freeform = isLocalAI ? resolveLocalAIFreeformSelection(voiceSelect) : null;
    if (freeform?.cancelled) {
        setRegenButtonBusy(button, false);
        return;
    }
    if (freeform?.voice) voiceValue = freeform.voice;
    const resolvedSelectedVoiceValue = freeform?.voice || selectedVoiceValue;
    const isChatterbox = normalizedEngine.includes('chatterbox');
    const isVoxCPM = normalizedEngine.includes('voxcpm');
    const isQwenEngine = normalizedEngine.includes('qwen3');
    const isQwenClone = normalizedEngine.includes('qwen3') && normalizedEngine.includes('clone');
    const isOmniClone = normalizedEngine.includes('omnivoice') && normalizedEngine.includes('clone');
    const isDotsTts = normalizedEngine.includes('dotstts');
    const isAzureSpeech = normalizedEngine.includes('azurespeech');
    const usesVoicePrompts = isChatterbox || isVoxCPM || isQwenClone || isOmniClone || isDotsTts;
    const voiceData = libraryVoiceMap.get(voiceValue);

    if (usesVoicePrompts) {
        if (selectedVoiceValue) {
            const promptEntry = libraryVoiceMap.get(selectedVoiceValue);
            voicePayload = {
                audio_prompt_path: selectedVoiceValue,
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
            ...voicePayload,
            ...(selectedVoiceValue ? { voice: selectedVoiceValue } : {}),
            extra: {
                ...existingExtra,
                language: language,
                ...(instruct && { instruct: instruct })
            }
        };
    } else if (isLocalAI && resolvedSelectedVoiceValue) {
        voicePayload = {
            voice: resolvedSelectedVoiceValue,
            lang_code: freeform?.language || libraryVoiceMap.get(resolvedSelectedVoiceValue)?.langCode
                || originalChunk?.voice_assignment?.lang_code || '',
        };
    } else if (selectedVoiceValue) {
        const originalAssignment = originalChunk?.voice_assignment || {};
        const keepAzureExpression = isAzureSpeech && selectedVoiceValue === originalAssignment.voice;
        const existingExtra = voicePayload.extra || {};
        voicePayload = {
            voice: selectedVoiceValue,
            lang_code: voiceData?.langCode || originalAssignment.lang_code || (
                normalizedEngine.includes('edgetts') || normalizedEngine.includes('elevenlabs') || normalizedEngine.includes('openaitts') ? '' : 'a'
            ),
            ...(isAzureSpeech ? {
                extra: {
                    ...(keepAzureExpression ? (originalAssignment.extra || {}) : {}),
                    ...existingExtra,
                    locale: voiceData?.langCode || originalAssignment.extra?.locale || '',
                },
            } : {}),
        };
    }

    // Attach fx/speed from the chunk's sliders so regeneration matches original settings
    const chunkFxCard = card;
    const chunkSpeedSlider = chunkFxCard?.querySelector('.chunk-speed-slider');
    const chunkPitchSlider = chunkFxCard?.querySelector('.chunk-pitch-slider');
    const chunkLeadingSilence = chunkFxCard?.querySelector('.chunk-leading-silence');
    const chunkTrailingSilence = chunkFxCard?.querySelector('.chunk-trailing-silence');
    const chunkSpeed = parseFloat(chunkSpeedSlider?.value || 1.0);
    const chunkPitch = parseFloat(chunkPitchSlider?.value || 0);
    const leadingSilenceSec = parseFloat(chunkLeadingSilence?.value || 0);
    const trailingSilenceSec = parseFloat(chunkTrailingSilence?.value || 0);
    if (Math.abs(chunkSpeed - 1.0) > 0.005) {
        voicePayload = { ...(voicePayload || {}), speed: parseFloat(chunkSpeed.toFixed(2)) };
    }
    if (Math.abs(chunkPitch) > 0.01) {
        voicePayload = { ...(voicePayload || {}), fx: { ...((voicePayload || {}).fx || {}), pitch: parseFloat(chunkPitch.toFixed(1)) } };
    }
    // Always send silence values (even when zero) so backend knows to explicitly remove existing silence
    voicePayload = { ...(voicePayload || {}), leading_silence_ms: Math.round(leadingSilenceSec * 1000), trailing_silence_ms: Math.round(trailingSilenceSec * 1000) };

    if (Object.keys(voicePayload || {}).length > 0) {
        libraryChunkVoiceOverrides[chunkId] = { ...voicePayload };
    }

    try {
        // First restore the job to review mode if not already
        await requestLibraryReviewRestore(jobId);
        setLibraryRecompileButtonState(true);

        const requestBody = {
            chunk_id: chunkId,
            text: text,
            voice: voicePayload,
            engine: resolvedEngine, // Always send resolved engine
        };

        const response = await fetch(`/api/jobs/${jobId}/review/regen`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
        });

        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to queue regeneration');
        }

        // Update UI to show queued status
        updateLibraryChunkStatus(chunkId, 'queued');
        startLibraryChunkRegenWatcher(jobId, chunkId);

    } catch (error) {
        console.error('Regen error:', error);
        alert(error.message || 'Failed to regenerate chunk');
        setRegenButtonBusy(button, false);
        await refreshLibraryRecompileState(jobId);
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
    } else if (status === 'unknown') {
        badge = '<span class="review-chip error">Refresh needed</span>';
    }

    const regenButton = card.querySelector('.library-chunk-regen');
    if (status === 'queued') {
        setRegenButtonBusy(regenButton, true, '⟳ Queued...');
    } else if (status === 'running') {
        setRegenButtonBusy(regenButton, true, '⟳ Rendering...');
    } else if (status === 'completed' || status === 'failed' || status === 'unknown') {
        setRegenButtonBusy(regenButton, false);
    }

    if (badge) {
        const toggle = summary.querySelector('.chunk-expand-toggle');
        if (toggle) {
            toggle.insertAdjacentHTML('afterend', badge);
        }
    }
}

function formatLibraryRegenDuration(totalSeconds) {
    const seconds = Math.max(0, Math.round(Number(totalSeconds) || 0));
    if (seconds < 60) return `${seconds}s`;
    const minutes = Math.floor(seconds / 60);
    const remainder = seconds % 60;
    if (minutes < 60) return remainder ? `${minutes}m ${remainder}s` : `${minutes}m`;
    const hours = Math.floor(minutes / 60);
    const minuteRemainder = minutes % 60;
    return minuteRemainder ? `${hours}h ${minuteRemainder}m` : `${hours}h`;
}

function updateLibraryCompletedChunk(chunkId, chunk) {
    if (!chunk?.file_url) return;
    const card = document.querySelector(`.library-chunk-card[data-chunk-id="${chunkId}"]`);
    if (card) {
        const playBtn = card.querySelector('.library-chunk-play');
        const cacheToken = chunk.regenerated_at || Date.now().toString();
        const newUrl = `${chunk.file_url}?t=${encodeURIComponent(cacheToken)}`;
        if (playBtn) {
            playBtn.setAttribute('data-audio-url', newUrl);
            playBtn.disabled = false;
        }
        const voiceLabelEl = card.querySelector('.library-chunk-voice-label');
        const newVoiceLabel = chunk.voice || chunk.voice_label;
        if (voiceLabelEl && newVoiceLabel) {
            voiceLabelEl.textContent = newVoiceLabel;
        }
    }
    const cachedChunk = (chunkReviewModalData?.chunks || []).find(item => item.id === chunkId);
    if (cachedChunk) {
        Object.assign(cachedChunk, chunk);
    }
}

function renderLibraryBulkRegenProgress(watcher, payload = {}) {
    const panel = document.getElementById('library-regen-progress');
    if (!panel || !watcher) return;

    const tasks = payload.regen_tasks || {};
    const chunks = payload.chunks || [];
    const chunkById = new Map(chunks.map(chunk => [String(chunk.id), chunk]));
    const counts = { completed: 0, running: 0, queued: 0, failed: 0, unknown: 0 };
    let runningChunkId = null;

    watcher.chunkIds.forEach(chunkId => {
        let status = tasks[chunkId]?.status;
        if (!status) {
            status = payload.review?.has_active_regen ? 'queued' : 'unknown';
        }
        if (!(status in counts)) status = 'unknown';
        counts[status] += 1;
        if (status === 'running' && !runningChunkId) runningChunkId = chunkId;
        updateLibraryChunkStatus(chunkId, status);
        if (status === 'completed') {
            updateLibraryCompletedChunk(chunkId, chunkById.get(String(chunkId)));
        }
    });

    const total = watcher.chunkIds.length;
    const finished = counts.completed + counts.failed;
    const percent = total ? Math.round((finished / total) * 100) : 0;
    const elapsedSeconds = (Date.now() - watcher.startedAt) / 1000;
    const remaining = counts.queued + counts.running;
    const completedDurations = watcher.chunkIds
        .map(chunkId => tasks[chunkId])
        .filter(task => task?.status === 'completed' && task.started_at && task.completed_at)
        .map(task => (Date.parse(task.completed_at) - Date.parse(task.started_at)) / 1000)
        .filter(duration => Number.isFinite(duration) && duration > 0);

    let timeText = `Elapsed: ${formatLibraryRegenDuration(elapsedSeconds)}`;
    if (remaining > 0 && completedDurations.length) {
        const averageSeconds = completedDurations.reduce((sum, duration) => sum + duration, 0) / completedDurations.length;
        timeText += ` · About ${formatLibraryRegenDuration(averageSeconds * remaining)} remaining`;
    } else if (remaining > 0) {
        timeText += ' · Estimating time remaining...';
    }

    const title = document.getElementById('library-regen-progress-title');
    const percentEl = document.getElementById('library-regen-progress-percent');
    const fill = document.getElementById('library-regen-progress-fill');
    const track = panel.querySelector('.library-regen-progress-track');
    const count = document.getElementById('library-regen-progress-count');
    const time = document.getElementById('library-regen-progress-time');
    const current = document.getElementById('library-regen-progress-current');
    const statuses = document.getElementById('library-regen-progress-statuses');

    panel.hidden = false;
    panel.classList.toggle('has-errors', counts.failed > 0);
    panel.classList.toggle('is-complete', remaining === 0 && counts.unknown === 0);
    if (title) {
        title.textContent = remaining > 0
            ? (watcher.resumed ? 'Regeneration in progress' : 'Regenerating selected speakers')
            : (counts.failed ? 'Regeneration finished with errors' : 'Regeneration complete');
    }
    if (percentEl) percentEl.textContent = `${percent}%`;
    if (fill) fill.style.width = `${percent}%`;
    if (track) track.setAttribute('aria-valuenow', String(percent));
    if (count) count.textContent = `${finished} of ${total} chunks finished`;
    if (time) time.textContent = timeText;
    if (statuses) {
        statuses.innerHTML = `
            <span class="library-regen-stat success">${counts.completed} updated</span>
            <span class="library-regen-stat active">${counts.running} rendering</span>
            <span class="library-regen-stat queued">${counts.queued} queued</span>
            <span class="library-regen-stat error">${counts.failed} failed</span>
        `;
    }

    if (current) {
        if (runningChunkId) {
            const chunk = chunkById.get(String(runningChunkId));
            const position = watcher.chunkIds.indexOf(runningChunkId) + 1;
            const speaker = chunk?.speaker || 'default';
            const preview = String(chunk?.text || '').replace(/\s+/g, ' ').trim();
            current.textContent = `Rendering chunk ${position} of ${total} · ${speaker}${preview ? ` · ${preview.slice(0, 90)}${preview.length > 90 ? '…' : ''}` : ''}`;
        } else if (remaining > 0) {
            current.textContent = 'Waiting for the next queued chunk to begin rendering...';
        } else if (counts.unknown > 0) {
            current.textContent = 'Some chunk statuses could not be confirmed. Refresh the Library item before recompiling.';
        } else if (counts.failed > 0) {
            current.textContent = `${counts.failed} chunk${counts.failed === 1 ? '' : 's'} failed. Review the failed chunks before recompiling.`;
        } else {
            current.textContent = `All ${total} chunks were updated successfully. You can now recompile the audio.`;
        }
    }

    setLibraryRecompileButtonState(
        remaining > 0 || Boolean(payload.review?.has_active_regen),
        remaining > 0 ? `Regenerating ${finished} of ${total}...` : ''
    );
    setLibraryBulkActionState(remaining > 0 || Boolean(payload.review?.has_active_regen));
    return { ...counts, total, finished, remaining };
}

function stopLibraryBulkRegenWatcher() {
    if (libraryBulkRegenWatcher?.timer) {
        clearTimeout(libraryBulkRegenWatcher.timer);
    }
    libraryBulkRegenWatcher = null;
}

function startLibraryBulkRegenWatcher(jobId, chunkIds, { resumed = false, startedAt = Date.now() } = {}) {
    const uniqueChunkIds = [...new Set((chunkIds || []).map(String))];
    if (!uniqueChunkIds.length) return;

    stopLibraryBulkRegenWatcher();
    uniqueChunkIds.forEach(chunkId => {
        const key = `${jobId}:${chunkId}`;
        if (libraryChunkRegenWatchers[key]?.timer) {
            clearTimeout(libraryChunkRegenWatchers[key].timer);
        }
        delete libraryChunkRegenWatchers[key];
        updateLibraryChunkStatus(chunkId, 'queued');
    });

    const watcher = {
        jobId,
        chunkIds: uniqueChunkIds,
        startedAt,
        resumed,
        failures: 0,
        timer: null,
    };
    libraryBulkRegenWatcher = watcher;
    renderLibraryBulkRegenProgress(watcher, {
        regen_tasks: Object.fromEntries(uniqueChunkIds.map(chunkId => [chunkId, { status: 'queued' }])),
        review: { has_active_regen: true },
        chunks: chunkReviewModalData?.chunks || [],
    });
    pollLibraryBulkRegenStatus(watcher);
}

async function pollLibraryBulkRegenStatus(watcher) {
    if (chunkReviewModalJobId !== watcher.jobId || libraryBulkRegenWatcher !== watcher) return;

    try {
        const payload = await fetchLibraryReviewPayload(watcher.jobId);
        watcher.failures = 0;
        const progress = renderLibraryBulkRegenProgress(watcher, payload);
        const hasActiveRegen = Boolean(payload.review?.has_active_regen);
        if (progress && progress.remaining === 0 && !hasActiveRegen) {
            libraryBulkRegenWatcher = null;
            return;
        }
    } catch (error) {
        console.error('Bulk regeneration progress error:', error);
        watcher.failures += 1;
        const current = document.getElementById('library-regen-progress-current');
        if (current) {
            current.textContent = 'Temporarily unable to retrieve progress. Retrying automatically...';
        }
    }

    const retryDelay = Math.min(
        LIBRARY_CHUNK_POLL_INTERVAL_MS * (2 ** Math.min(watcher.failures, 3)),
        LIBRARY_CHUNK_MAX_ERROR_BACKOFF_MS
    );
    watcher.timer = setTimeout(() => pollLibraryBulkRegenStatus(watcher), retryDelay);
}

function startLibraryChunkRegenWatcher(jobId, chunkId) {
    const key = `${jobId}:${chunkId}`;
    if (libraryChunkRegenWatchers[key]) {
        clearTimeout(libraryChunkRegenWatchers[key].timer);
    }

    const initialChunk = (chunkReviewModalData?.chunks || []).find(chunk => chunk.id === chunkId);
    const entry = {
        failures: 0,
        timer: null,
        initialRegeneratedAt: initialChunk?.regenerated_at || null,
    };
    libraryChunkRegenWatchers[key] = entry;

    pollLibraryChunkStatus(jobId, chunkId, entry);
}

async function pollLibraryChunkStatus(jobId, chunkId, entry) {
    const watcherKey = `${jobId}:${chunkId}`;
    if (chunkReviewModalJobId !== jobId || libraryChunkRegenWatchers[watcherKey] !== entry) {
        delete libraryChunkRegenWatchers[watcherKey];
        return;
    }

    try {
        const data = await fetchLibraryReviewPayload(jobId);
        entry.failures = 0;

        const chunks = data.chunks || [];
        const chunk = chunks.find(item => item.id === chunkId);
        const task = (data.regen_tasks || {})[chunkId];
        const hasActiveRegen = Boolean(data.review?.has_active_regen);
        let status = task?.status || null;

        if (!status) {
            const timestampChanged = Boolean(
                chunk?.regenerated_at
                && chunk.regenerated_at !== entry.initialRegeneratedAt
            );
            if (hasActiveRegen) {
                status = 'queued';
            } else {
                status = timestampChanged ? 'completed' : 'unknown';
            }
        }

        updateLibraryChunkStatus(chunkId, status);
        setLibraryRecompileButtonState(hasActiveRegen);

        if (status === 'completed' || status === 'failed' || status === 'unknown') {
            resetChunkRegenButton(chunkId);
            if (status === 'completed' && chunk?.file_url) {
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
                const cachedChunk = (chunkReviewModalData?.chunks || []).find(item => item.id === chunkId);
                if (cachedChunk) {
                    Object.assign(cachedChunk, chunk);
                }
            }
            delete libraryChunkRegenWatchers[watcherKey];
            return;
        }
    } catch (err) {
        console.error('Poll error:', err);
        entry.failures += 1;
    }

    const retryDelay = Math.min(
        LIBRARY_CHUNK_POLL_INTERVAL_MS * (2 ** Math.min(entry.failures, 3)),
        LIBRARY_CHUNK_MAX_ERROR_BACKOFF_MS
    );
    entry.timer = setTimeout(() => pollLibraryChunkStatus(jobId, chunkId, entry), retryDelay);
}

function renderLibraryRecompileProgress({
    percent = 0,
    done = 0,
    total = 0,
    label = 'Preparing audio files...',
    elapsedSeconds = 0,
    completed = false,
    failed = false,
} = {}) {
    const panel = document.getElementById('library-regen-progress');
    if (!panel) return;
    const safePercent = Math.max(0, Math.min(100, Math.round(Number(percent) || 0)));
    const title = document.getElementById('library-regen-progress-title');
    const percentEl = document.getElementById('library-regen-progress-percent');
    const fill = document.getElementById('library-regen-progress-fill');
    const track = panel.querySelector('.library-regen-progress-track');
    const count = document.getElementById('library-regen-progress-count');
    const time = document.getElementById('library-regen-progress-time');
    const current = document.getElementById('library-regen-progress-current');
    const statuses = document.getElementById('library-regen-progress-statuses');

    panel.hidden = false;
    panel.classList.toggle('is-complete', completed);
    panel.classList.toggle('has-errors', failed);
    if (title) {
        title.textContent = failed
            ? 'Recompile failed'
            : (completed ? 'Recompile complete' : 'Recompiling project audio');
    }
    if (percentEl) percentEl.textContent = `${safePercent}%`;
    if (fill) fill.style.width = `${safePercent}%`;
    if (track) track.setAttribute('aria-valuenow', String(safePercent));
    if (count) {
        count.textContent = total > 0
            ? `${Math.min(done, total)} of ${total} audio outputs finished`
            : 'Preparing output plan...';
    }
    if (time) {
        let timeText = `Elapsed: ${formatLibraryRegenDuration(elapsedSeconds)}`;
        if (!completed && !failed && safePercent > 2 && safePercent < 100) {
            const estimatedRemaining = elapsedSeconds * ((100 - safePercent) / safePercent);
            timeText += ` · About ${formatLibraryRegenDuration(estimatedRemaining)} remaining`;
        } else if (!completed && !failed) {
            timeText += ' · Estimating time remaining...';
        }
        time.textContent = timeText;
    }
    if (current) current.textContent = label;
    if (statuses) {
        statuses.innerHTML = failed
            ? '<span class="library-regen-stat error">Recompile failed</span>'
            : (completed
                ? '<span class="library-regen-stat success">New audio files are ready</span>'
                : '<span class="library-regen-stat active">Merging chunks into project audio</span>');
    }
}

function stopLibraryRecompileProgressWatcher() {
    if (libraryRecompileProgressWatcher?.timer) {
        clearTimeout(libraryRecompileProgressWatcher.timer);
    }
    libraryRecompileProgressWatcher = null;
}

function startLibraryRecompileProgressWatcher(jobId) {
    stopLibraryRecompileProgressWatcher();
    const watcher = {
        jobId,
        startedAt: Date.now(),
        failures: 0,
        timer: null,
        lastTotal: 0,
        seenActive: false,
    };
    libraryRecompileProgressWatcher = watcher;
    renderLibraryRecompileProgress();
    pollLibraryRecompileProgress(watcher);
}

async function pollLibraryRecompileProgress(watcher) {
    if (chunkReviewModalJobId !== watcher.jobId || libraryRecompileProgressWatcher !== watcher) return;
    try {
        const payload = await fetchLibraryReviewPayload(watcher.jobId);
        watcher.failures = 0;
        const review = payload.review || {};
        if (review.post_process_active) watcher.seenActive = true;
        const total = Number(review.post_process_total) || 0;
        const done = Number(review.post_process_done) || 0;
        if (total > 0) watcher.lastTotal = total;
        if (watcher.seenActive) {
            renderLibraryRecompileProgress({
                percent: review.post_process_percent || 0,
                done,
                total,
                label: review.post_process_label || 'Preparing audio files...',
                elapsedSeconds: (Date.now() - watcher.startedAt) / 1000,
            });
        }
    } catch (error) {
        console.error('Recompile progress error:', error);
        watcher.failures += 1;
        const current = document.getElementById('library-regen-progress-current');
        if (current) {
            current.textContent = 'Temporarily unable to retrieve recompile progress. Retrying automatically...';
        }
    }
    const retryDelay = Math.min(
        750 * (2 ** Math.min(watcher.failures, 3)),
        LIBRARY_CHUNK_MAX_ERROR_BACKOFF_MS
    );
    watcher.timer = setTimeout(() => pollLibraryRecompileProgress(watcher), retryDelay);
}

async function recompileLibraryAudio() {
    const jobId = chunkReviewModalJobId;
    const button = document.getElementById('chunk-review-recompile-btn');
    if (!jobId || !button) return;
    let reviewStateLoaded = false;
    let hasActiveRegen = true;

    button.dataset.recompileBusy = 'true';
    button.disabled = true;
    button.textContent = 'Recompiling...';

    try {
        await requestLibraryReviewRestore(jobId);
        const reviewPayload = await fetchLibraryReviewPayload(jobId);
        reviewStateLoaded = true;
        hasActiveRegen = Boolean(reviewPayload.review?.has_active_regen);
        if (hasActiveRegen) {
            throw new Error('Wait for all chunk regenerations to finish');
        }

        startLibraryRecompileProgressWatcher(jobId);
        const response = await fetch(`/api/jobs/${jobId}/review/finish`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
        });
        const data = await response.json();
        if (!response.ok || !data.success) {
            throw new Error(data.error || 'Failed to recompile audio');
        }

        const completedTotal = libraryRecompileProgressWatcher?.lastTotal || 1;
        stopLibraryRecompileProgressWatcher();
        renderLibraryRecompileProgress({
            percent: 100,
            done: completedTotal,
            total: completedTotal,
            label: 'Audio recompiled successfully',
            completed: true,
        });
        button.textContent = 'Recompile complete';
        await new Promise(resolve => setTimeout(resolve, 900));
        closeChunkReviewModal();
        loadLibrary();
    } catch (error) {
        console.error('Recompile error:', error);
        stopLibraryRecompileProgressWatcher();
        renderLibraryRecompileProgress({
            percent: 0,
            label: error.message || 'Failed to recompile audio',
            failed: true,
        });
        alert(error.message || 'Failed to recompile audio');
    } finally {
        button.dataset.recompileBusy = 'false';
        if (chunkReviewModalJobId === jobId) {
            setLibraryRecompileButtonState(!reviewStateLoaded || hasActiveRegen);
        } else {
            button.disabled = true;
            button.textContent = 'Recompile Audio';
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
    const hasChanges = Math.abs(speed - 1.0) > 0.005 || Math.abs(pitch) > 0.1;
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
    const hasChanges = Math.abs(speed - 1.0) > 0.005 || Math.abs(pitch) > 0.1;
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
    if (!button.dataset.originalText) {
        button.dataset.originalText = originalText;
    }
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
            button.textContent = button.dataset.originalText;
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
        previewButton.disabled = false;
        previewButton.textContent = previewButton.dataset.originalText || 'Preview';
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

// ─── Library Alt Word Registry ───────────────────────────────────────────────
// Reuses the full AWR modal from index.html (awr-entry-overlay / awr-modal).
// When _libraryAwrJobId is set, the modal's OK button saves to the backend
// instead of adding a single entry to the main-page registry.

let _libraryAwrJobId = null;
let _libraryAwrList = [];
let _libraryAwrEditIdx = null; // index being edited, or null for new

async function openLibraryAwr(jobId) {
    _libraryAwrJobId = jobId;
    _libraryAwrList = [];
    _libraryAwrEditIdx = null;

    // Load existing replacements from backend
    try {
        const resp = await fetch(`/api/library/${jobId}/word-replacements`);
        const data = await resp.json();
        if (data.success) _libraryAwrList = data.word_replacements || [];
    } catch (e) {
        console.warn('Failed to load library AWR:', e);
    }

    // Reuse the main AWR modal — swap its title and show the registry table view
    _openLibraryAwrMainModal();
}

function _openLibraryAwrMainModal() {
    // We repurpose the existing awr-modal (the main registry modal, not the entry sub-modal)
    // by injecting a library-specific overlay on top of it.
    // Simpler: build a standalone modal using the same CSS classes as the main AWR entry modal.
    let overlay = document.getElementById('lib-awr-registry-overlay');
    if (!overlay) {
        overlay = document.createElement('div');
        overlay.id = 'lib-awr-registry-overlay';
        overlay.className = 'modal-overlay hidden';
        overlay.innerHTML = `
            <div class="modal hidden" id="lib-awr-registry-modal" style="max-width:680px;width:95%;z-index:1300;">
                <div class="modal-header">
                    <h3>Alt Word Registry</h3>
                    <button class="modal-close" id="lib-awr-reg-close">&times;</button>
                </div>
                <div class="modal-body">
                    <p class="awr-description">
                        These replacements are applied whenever audio chunks are regenerated for this job.
                        Use this to replace words the engine mispronounces with phonetic alternatives.
                    </p>
                    <div class="awr-toolbar">
                        <button class="btn btn-primary btn-sm" id="lib-awr-reg-add-btn">＋ Add Entry</button>
                    </div>
                    <div class="awr-table-wrapper">
                        <table class="awr-table">
                            <thead><tr>
                                <th>Original Word / Phrase</th>
                                <th>Replacement</th>
                                <th></th>
                            </tr></thead>
                            <tbody id="lib-awr-reg-tbody">
                                <tr><td colspan="3" class="awr-empty">No entries yet.</td></tr>
                            </tbody>
                        </table>
                    </div>
                </div>
                <div class="modal-footer">
                    <button class="btn btn-secondary" id="lib-awr-reg-cancel">Cancel</button>
                    <button class="btn btn-primary" id="lib-awr-reg-save">Save</button>
                </div>
            </div>`;
        document.body.appendChild(overlay);

        document.getElementById('lib-awr-reg-close').addEventListener('click', closeLibraryAwr);
        document.getElementById('lib-awr-reg-cancel').addEventListener('click', closeLibraryAwr);
        overlay.addEventListener('click', e => { if (e.target === overlay) closeLibraryAwr(); });
        document.getElementById('lib-awr-reg-add-btn').addEventListener('click', () => {
            _libraryAwrEditIdx = null;
            _openLibraryAwrEntryModal(null);
        });
    }

    // Reassign onclick every open so it always captures the current _libraryAwrJobId
    document.getElementById('lib-awr-reg-save').onclick = saveLibraryAwr;

    _renderLibraryAwrRegTable();
    overlay.classList.remove('hidden');
    document.getElementById('lib-awr-registry-modal').classList.remove('hidden');
}

function _renderLibraryAwrRegTable() {
    const tbody = document.getElementById('lib-awr-reg-tbody');
    if (!tbody) return;
    if (_libraryAwrList.length === 0) {
        tbody.innerHTML = '<tr><td colspan="3" class="awr-empty">No entries yet. Click <strong>＋ Add Entry</strong> to get started.</td></tr>';
        return;
    }
    tbody.innerHTML = _libraryAwrList.map((entry, idx) => `
        <tr>
            <td class="awr-original-cell">${escapeHtml(entry.original)}</td>
            <td class="awr-replacement-cell">${escapeHtml(entry.replacement)}</td>
            <td class="awr-actions-cell">
                <button class="awr-edit-btn" data-idx="${idx}" title="Edit">✏️</button>
                <button class="awr-delete-btn" data-idx="${idx}" title="Delete">🗑️</button>
            </td>
        </tr>`).join('');
    tbody.querySelectorAll('.awr-edit-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            _libraryAwrEditIdx = Number(btn.dataset.idx);
            _openLibraryAwrEntryModal(_libraryAwrList[_libraryAwrEditIdx]);
        });
    });
    tbody.querySelectorAll('.awr-delete-btn').forEach(btn => {
        btn.addEventListener('click', () => {
            _libraryAwrList.splice(Number(btn.dataset.idx), 1);
            _renderLibraryAwrRegTable();
        });
    });
}

function _ensureLibraryAwrEntryModal() {
    if (document.getElementById('lib-awr-entry-overlay')) return;

    const overlay = document.createElement('div');
    overlay.id = 'lib-awr-entry-overlay';
    overlay.className = 'modal-overlay hidden';
    overlay.style.zIndex = '1600';
    overlay.innerHTML = `
        <div class="modal" id="lib-awr-entry-modal" style="max-width:520px;width:95%;z-index:1601;">
            <div class="modal-header">
                <h3 id="lib-awr-entry-title">Add Alt Word Entry</h3>
                <button class="modal-close" id="lib-awr-entry-close">&times;</button>
            </div>
            <div class="modal-body">
                <div class="awr-entry-fields">
                    <div class="awr-field-row">
                        <label class="awr-label">Original word / phrase</label>
                        <input type="text" id="lib-awr-original-input" class="awr-text-input" placeholder="e.g. Worcestershire">
                    </div>
                    <div class="awr-field-row">
                        <label class="awr-label">Replacement word / phrase</label>
                        <input type="text" id="lib-awr-replacement-input" class="awr-text-input" placeholder="e.g. Wooster-sher">
                    </div>
                    <div class="awr-preview-section">
                        <div class="awr-preview-row">
                            <div class="awr-preview-field">
                                <label class="awr-label">TTS Engine</label>
                                <select id="lib-awr-preview-engine" class="awr-select">
                                    <option value="kokoro">Kokoro · Local</option>
                                    <option value="kokoro_replicate">Kokoro · Replicate</option>
                                    <option value="chatterbox_turbo_local">Chatterbox · Local</option>
                                    <option value="chatterbox_turbo_replicate">Chatterbox · Replicate</option>
                                    <option value="voxcpm_local">VoxCPM 1.5</option>
                                    <option value="pocket_tts">Pocket TTS · Clone</option>
                                    <option value="pocket_tts_preset">Pocket TTS · Preset</option>
                                    <option value="qwen3_custom">Qwen3-TTS · Custom Voice</option>
                                    <option value="qwen3_clone">Qwen3-TTS · Clone</option>
                                    <option value="omnivoice_clone">OmniVoice · Clone</option>
                                    <option value="kitten_tts">KittenTTS</option>
                                    <option value="index_tts">IndexTTS</option>
                                    <option value="dots_tts">Dot.TTS</option>
                                    <option value="audio8_tts">Audio8 TTS</option>
                                    <option value="azure_speech">Microsoft Azure Speech</option>
                                    <option value="edge_tts">Microsoft Edge TTS</option>
                                    <option value="elevenlabs">ElevenLabs</option>
                                    <option value="openai_tts">OpenAI-compatible TTS</option>
                                    <option value="localai_tts">LocalAI TTS</option>
                                </select>
                            </div>
                            <div class="awr-preview-field awr-preview-field-voice">
                                <label class="awr-label">Voice</label>
                                <select id="lib-awr-preview-voice" class="awr-select">
                                    <option value="">-- Select voice --</option>
                                </select>
                            </div>
                        </div>
                        <div class="awr-preview-buttons">
                            <button class="btn btn-sm btn-secondary" id="lib-awr-play-original" disabled>▶ Play Original</button>
                            <button class="btn btn-sm btn-secondary" id="lib-awr-play-replacement" disabled>▶ Play Replacement</button>
                            <span class="awr-preview-status" id="lib-awr-preview-status"></span>
                        </div>
                    </div>
                </div>
            </div>
            <div class="modal-footer">
                <button class="btn btn-secondary" id="lib-awr-entry-cancel">Cancel</button>
                <button class="btn btn-primary" id="lib-awr-entry-ok">OK</button>
            </div>
        </div>`;
    document.body.appendChild(overlay);

    // Engine change → repopulate voices
    document.getElementById('lib-awr-preview-engine').addEventListener('change', function () {
        _libAwrPopulateVoices(this.value);
    });
    _libAwrPopulateVoices('kokoro');

    // Preview buttons
    let _libAwrPreviewAudio = null;
    const _libAwrStopPreview = () => { if (_libAwrPreviewAudio) { _libAwrPreviewAudio.pause(); _libAwrPreviewAudio = null; } };

    const _libAwrPlayText = async (text) => {
        _libAwrStopPreview();
        const engine = document.getElementById('lib-awr-preview-engine').value;
        const voice = document.getElementById('lib-awr-preview-voice').value;
        const statusEl = document.getElementById('lib-awr-preview-status');
        if (!text) return;
        statusEl.textContent = 'Generating…';
        try {
            const resp = await fetch('/api/preview', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text, tts_engine: engine, voice, lang_code: 'a' }),
            });
            const data = await resp.json();
            if (!data.success) { statusEl.textContent = data.error || 'Error'; return; }
            statusEl.textContent = '';
            const audioSrc = data.audio_url
                ? data.audio_url
                : `data:${data.mime_type || 'audio/wav'};base64,${data.audio_base64}`;
            _libAwrPreviewAudio = new Audio(audioSrc);
            _libAwrPreviewAudio.play();
        } catch (e) {
            statusEl.textContent = 'Error';
        }
    };

    document.getElementById('lib-awr-play-original').addEventListener('click', () => {
        _libAwrPlayText((document.getElementById('lib-awr-original-input').value || '').trim());
    });
    document.getElementById('lib-awr-play-replacement').addEventListener('click', () => {
        _libAwrPlayText((document.getElementById('lib-awr-replacement-input').value || '').trim());
    });

    // Enable/disable play buttons based on input
    const _updatePlayBtns = () => {
        const hasOrig = !!(document.getElementById('lib-awr-original-input').value || '').trim();
        const hasRepl = !!(document.getElementById('lib-awr-replacement-input').value || '').trim();
        document.getElementById('lib-awr-play-original').disabled = !hasOrig;
        document.getElementById('lib-awr-play-replacement').disabled = !hasRepl;
    };
    document.getElementById('lib-awr-original-input').addEventListener('input', _updatePlayBtns);
    document.getElementById('lib-awr-replacement-input').addEventListener('input', _updatePlayBtns);
}

async function _libAwrPopulateVoices(engineName) {
    const select = document.getElementById('lib-awr-preview-voice');
    if (!select) return;
    const prev = select.value;
    select.innerHTML = '<option value="">-- Select voice --</option>';

    const norm = (engineName || '').toLowerCase().replace(/[_-]/g, '');
    const usesPrompts = norm.includes('chatterbox') || norm.includes('voxcpm')
        || (norm.includes('pockettts') && !norm.includes('pocketttspreset'))
        || (norm.includes('qwen3') && norm.includes('clone'))
        || (norm.includes('omnivoice') && norm.includes('clone'))
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
            ['Bella', 'Jasper', 'Luna', 'Bruno', 'Rosie', 'Hugo', 'Kiki', 'Leo'].forEach(voiceName => {
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
        } else if (isEdgeTts || isElevenLabs || isOpenAITts || isLocalAITts) {
            const data = await getLibraryCloudCatalog(engineName);
            if (data.success && data.voices) {
                data.voices.forEach(voice => {
                    const opt = document.createElement('option');
                    opt.value = voice.short_name || voice.voice_id;
                    opt.textContent = `${voice.display_name || opt.value}${voice.locale ? ` (${voice.locale})` : ''}`;
                    opt.disabled = Boolean(voice.disabled);
                    if (voice.disabled_reason) opt.title = voice.disabled_reason;
                    select.appendChild(opt);
                });
            }
        } else {
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
        console.warn('_libAwrPopulateVoices error:', e);
    }
    if (prev) select.value = prev;
}

function _openLibraryAwrEntryModal(entry) {
    _ensureLibraryAwrEntryModal();

    const overlay = document.getElementById('lib-awr-entry-overlay');
    const modal = document.getElementById('lib-awr-entry-modal');

    document.getElementById('lib-awr-entry-title').textContent = entry ? 'Edit Alt Word Entry' : 'Add Alt Word Entry';
    document.getElementById('lib-awr-original-input').value = entry ? entry.original : '';
    document.getElementById('lib-awr-replacement-input').value = entry ? entry.replacement : '';
    document.getElementById('lib-awr-preview-status').textContent = '';
    document.getElementById('lib-awr-play-original').disabled = !entry?.original;
    document.getElementById('lib-awr-play-replacement').disabled = !entry?.replacement;

    overlay.classList.remove('hidden');
    modal.classList.remove('hidden');
    document.getElementById('lib-awr-original-input').focus();

    const closeEntry = () => {
        overlay.classList.add('hidden');
        modal.classList.add('hidden');
        document.getElementById('lib-awr-entry-ok').onclick = null;
        document.getElementById('lib-awr-entry-close').onclick = null;
        document.getElementById('lib-awr-entry-cancel').onclick = null;
    };

    document.getElementById('lib-awr-entry-ok').onclick = () => {
        const orig = (document.getElementById('lib-awr-original-input').value || '').trim();
        const repl = (document.getElementById('lib-awr-replacement-input').value || '').trim();
        if (!orig || !repl) return;
        if (_libraryAwrEditIdx !== null) {
            _libraryAwrList[_libraryAwrEditIdx] = { original: orig, replacement: repl };
            _libraryAwrEditIdx = null;
        } else {
            if (_libraryAwrList.some(r => r.original.toLowerCase() === orig.toLowerCase())) {
                alert('An entry for that word already exists.');
                return;
            }
            _libraryAwrList.push({ original: orig, replacement: repl });
        }
        closeEntry();
        _renderLibraryAwrRegTable();
    };

    document.getElementById('lib-awr-entry-close').onclick = closeEntry;
    document.getElementById('lib-awr-entry-cancel').onclick = closeEntry;
}

function closeLibraryAwr() {
    const overlay = document.getElementById('lib-awr-registry-overlay');
    const modal = document.getElementById('lib-awr-registry-modal');
    if (overlay) overlay.classList.add('hidden');
    if (modal) modal.classList.add('hidden');
    _libraryAwrJobId = null;
    _libraryAwrList = [];
    _libraryAwrEditIdx = null;
}

async function saveLibraryAwr() {
    const jobId = _libraryAwrJobId;
    if (!jobId) { closeLibraryAwr(); return; }
    const saveBtn = document.getElementById('lib-awr-reg-save');
    if (saveBtn) { saveBtn.disabled = true; saveBtn.textContent = 'Saving…'; }
    try {
        const resp = await fetch(`/api/library/${jobId}/word-replacements`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ word_replacements: _libraryAwrList }),
        });
        const data = await resp.json();
        if (!data.success) {
            alert('Failed to save: ' + (data.error || 'Unknown error'));
            return;
        }
        closeLibraryAwr();
    } catch (e) {
        console.error('Save library AWR error:', e);
        alert('Failed to save Alt Word Registry.');
    } finally {
        if (saveBtn) { saveBtn.disabled = false; saveBtn.textContent = 'Save'; }
    }
}

// ─── End Library Alt Word Registry ───────────────────────────────────────────

// ─── Time Codes Modal ─────────────────────────────────────────────────────────

let timeCodesJobId = null;
let timeCodesChapters = null;

function fmtTimecode(totalSeconds) {
    const s = Math.floor(totalSeconds);
    const h = Math.floor(s / 3600);
    const m = Math.floor((s % 3600) / 60);
    const sec = s % 60;
    return `${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:${String(sec).padStart(2, '0')}`;
}

function buildTimeCodesText(chapters, introSeconds, driftPerChapter) {
    // All entries formatted as "HH:MM:SS  CH. XX" — uniform length, no alignment needed.
    const entries = chapters.map((ch, idx) => {
        const ts = Math.floor(ch.start_time + introSeconds + driftPerChapter * idx);
        return `${fmtTimecode(ts)}  CH. ${String(idx).padStart(2, '0')}`;
    });
    const cols = 3;
    const gap = '     '; // 5 spaces between columns
    const rows = [];
    for (let i = 0; i < entries.length; i += cols) {
        const row = [];
        for (let c = 0; c < cols; c++) {
            if (entries[i + c] !== undefined) row.push(entries[i + c]);
        }
        rows.push(row.join(gap));
    }
    return rows.join('\n');
}

function renderTimeCodesResult() {
    if (!timeCodesChapters) return;
    const introInput = document.getElementById('timecodes-intro-seconds');
    const driftInput = document.getElementById('timecodes-drift-adjust');
    const introSecs = Math.max(0, parseFloat(introInput?.value) || 0);
    const driftPerChapter = parseFloat(driftInput?.value) || 0;
    const output = document.getElementById('timecodes-output');
    const resultEl = document.getElementById('timecodes-result');
    if (output) output.textContent = buildTimeCodesText(timeCodesChapters, introSecs, driftPerChapter);
    if (resultEl) resultEl.classList.remove('hidden');
}

async function openTimeCodesModal(jobId, title) {
    timeCodesJobId = jobId;
    timeCodesChapters = null;

    const overlay = document.getElementById('timecodes-modal-overlay');
    const modal = document.getElementById('timecodes-modal');
    const titleEl = document.getElementById('timecodes-modal-title');
    const loadingEl = document.getElementById('timecodes-loading');
    const errorEl = document.getElementById('timecodes-error');
    const resultEl = document.getElementById('timecodes-result');
    const introInput = document.getElementById('timecodes-intro-seconds');
    const output = document.getElementById('timecodes-output');

    if (titleEl) titleEl.textContent = `Time Codes — ${title || 'Untitled'}`;
    if (loadingEl) loadingEl.classList.remove('hidden');
    if (errorEl) { errorEl.classList.add('hidden'); errorEl.textContent = ''; }
    if (resultEl) resultEl.classList.add('hidden');
    if (output) output.textContent = '';
    if (introInput) introInput.value = 0;

    overlay?.classList.remove('hidden');
    modal?.classList.remove('hidden');

    try {
        const response = await fetch(`/api/library/${jobId}/chapter-durations`);
        const data = await response.json();
        if (!data.success) throw new Error(data.error || 'Failed to load chapter data');
        if (!data.chapters || data.chapters.length === 0) throw new Error('No chapters found for this item.');
        timeCodesChapters = data.chapters;
        if (loadingEl) loadingEl.classList.add('hidden');
        renderTimeCodesResult();
    } catch (err) {
        if (loadingEl) loadingEl.classList.add('hidden');
        if (errorEl) { errorEl.textContent = err.message || 'Failed to load chapters.'; errorEl.classList.remove('hidden'); }
    }
}

function closeTimeCodesModal() {
    document.getElementById('timecodes-modal-overlay')?.classList.add('hidden');
    document.getElementById('timecodes-modal')?.classList.add('hidden');
    timeCodesJobId = null;
    timeCodesChapters = null;
}

document.addEventListener('DOMContentLoaded', () => {
    document.addEventListener('click', e => {
        const btn = e.target.closest('.timecodes-open-btn');
        if (btn) {
            e.stopPropagation();
            openTimeCodesModal(btn.dataset.jobId, btn.dataset.title || '');
        }
    });
    document.getElementById('timecodes-modal-close')?.addEventListener('click', closeTimeCodesModal);
    document.getElementById('timecodes-close-btn')?.addEventListener('click', closeTimeCodesModal);
    document.getElementById('timecodes-modal-overlay')?.addEventListener('click', e => {
        if (e.target === document.getElementById('timecodes-modal-overlay')) closeTimeCodesModal();
    });
    document.getElementById('timecodes-calculate-btn')?.addEventListener('click', renderTimeCodesResult);
    document.getElementById('timecodes-intro-seconds')?.addEventListener('keydown', e => {
        if (e.key === 'Enter') renderTimeCodesResult();
    });
    document.getElementById('timecodes-drift-adjust')?.addEventListener('keydown', e => {
        if (e.key === 'Enter') renderTimeCodesResult();
    });
    document.getElementById('timecodes-drift-adjust')?.addEventListener('change', renderTimeCodesResult);
    document.getElementById('timecodes-copy-btn')?.addEventListener('click', () => {
        const text = document.getElementById('timecodes-output')?.textContent || '';
        if (!text) return;
        navigator.clipboard.writeText(text).then(() => {
            const btn = document.getElementById('timecodes-copy-btn');
            if (btn) {
                const orig = btn.textContent;
                btn.textContent = 'Copied!';
                setTimeout(() => { btn.textContent = orig; }, 1800);
            }
        }).catch(() => {
            prompt('Copy the time codes below:', text);
        });
    });
    document.addEventListener('keydown', e => {
        if (e.key === 'Escape') {
            const overlay = document.getElementById('timecodes-modal-overlay');
            if (overlay && !overlay.classList.contains('hidden')) closeTimeCodesModal();
        }
    });
});

// ─── End Time Codes Modal ─────────────────────────────────────────────────────

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
