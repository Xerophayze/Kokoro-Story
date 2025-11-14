// Library management

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
        
        itemCard.innerHTML = `
            <div class="library-item-header">
                <div class="library-item-info">
                    <strong>Generated Audio</strong>
                    <span class="library-item-date">${formattedDate}</span>
                </div>
                <div class="library-item-meta">
                    <span class="library-item-size">${fileSizeMB} MB</span>
                    <span class="library-item-format">${item.format.toUpperCase()}</span>
                </div>
            </div>
            <div class="library-item-player">
                <audio controls src="${item.output_file}"></audio>
            </div>
            <div class="library-item-actions">
                <button class="btn btn-primary btn-sm" onclick="downloadLibraryItem('${item.job_id}', '${item.format}')">
                    Download
                </button>
                <button class="btn btn-secondary btn-sm" onclick="deleteLibraryItem('${item.job_id}')">
                    Delete
                </button>
            </div>
        `;
        
        container.appendChild(itemCard);
    });
}

// Download library item
function downloadLibraryItem(jobId, format) {
    window.location.href = `/api/download/${jobId}`;
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
