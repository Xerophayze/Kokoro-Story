// Library management

const currentChapterSelection = {};

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

        itemCard.innerHTML = `
            <div class="library-item-header">
                <div class="library-item-info">
                    <strong>${item.chapter_mode ? 'Chapter Collection' : 'Generated Audio'}</strong>
                    <span class="library-item-date">${formattedDate}</span>
                </div>
                <div class="library-item-meta">
                    <span class="library-item-size">${fileSizeMB} MB</span>
                    <span class="library-item-format">${item.format.toUpperCase()}</span>
                </div>
            </div>
            <div class="library-item-player">
                <audio controls id="player-${item.job_id}"></audio>
            </div>
            ${renderChapterControls(item)}
            <div class="library-item-actions">
                <button class="btn btn-primary btn-sm" onclick="downloadLibraryItem('${item.job_id}')">
                    Download ${item.chapter_mode ? 'Selected Chapter' : ''}
                </button>
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
