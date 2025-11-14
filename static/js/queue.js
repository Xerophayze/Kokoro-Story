// Job Queue Management

const QUEUE_REFRESH_INTERVAL_MS = 3000;
let queueRefreshTimer = null;
let queueTabButton = null;

document.addEventListener('DOMContentLoaded', () => {
    queueTabButton = document.querySelector('.tab-button[data-tab="queue"]');
    initQueue();

    if (queueTabButton) {
        queueTabButton.addEventListener('click', () => {
            loadQueue();
            startQueueAutoRefresh();
        });
    }

    document.querySelectorAll('.tab-button').forEach(btn => {
        if (btn.dataset.tab !== 'queue') {
            btn.addEventListener('click', stopQueueAutoRefresh);
        }
    });

    document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
            stopQueueAutoRefresh();
        } else if (isQueueTabActive()) {
            startQueueAutoRefresh();
            loadQueue();
        }
    });

    if (isQueueTabActive()) {
        startQueueAutoRefresh();
    }
});

function initQueue() {
    const refreshBtn = document.getElementById('refresh-queue-btn');
    if (refreshBtn) {
        refreshBtn.addEventListener('click', loadQueue);
    }

    loadQueue();
}

function isQueueTabActive() {
    const queueTab = document.getElementById('queue-tab');
    return queueTab && queueTab.classList.contains('active');
}

function startQueueAutoRefresh() {
    stopQueueAutoRefresh();
    queueRefreshTimer = setInterval(loadQueue, QUEUE_REFRESH_INTERVAL_MS);
}

function stopQueueAutoRefresh() {
    if (queueRefreshTimer) {
        clearInterval(queueRefreshTimer);
        queueRefreshTimer = null;
    }
}

async function loadQueue() {
    try {
        const response = await fetch('/api/queue');
        const data = await response.json();

        if (data.success) {
            displayQueue(data);
        } else {
            console.error('Error loading queue:', data.error);
        }
    } catch (error) {
        console.error('Error loading queue:', error);
    }
}

function displayQueue(data) {
    const container = document.getElementById('queue-list');
    if (!container) return;

    if (!data.jobs || data.jobs.length === 0) {
        container.innerHTML = '<p><em>No jobs in queue</em></p>';
        return;
    }

    let html = `
        <div style="margin-bottom: 15px;">
            <strong>Queue Size:</strong> ${data.queue_size} pending |
            <strong>Current Job:</strong> ${data.current_job || 'None'}
        </div>
        <table class="queue-table">
            <thead>
                <tr>
                    <th>Status</th>
                    <th>Job ID</th>
                    <th>Text Preview</th>
                    <th>Created</th>
                    <th>Actions</th>
                </tr>
            </thead>
            <tbody>
    `;

    data.jobs.forEach(job => {
        const statusClass = getStatusClass(job.status);
        const statusIcon = getStatusIcon(job.status);
        const createdTime = job.created_at ? new Date(job.created_at).toLocaleString() : '';
        const isCurrentJob = job.job_id === data.current_job;

        html += `
            <tr class="${isCurrentJob ? 'current-job' : ''}">
                <td><span class="status-badge ${statusClass}">${statusIcon} ${job.status}</span></td>
                <td><code>${job.job_id.substring(0, 8)}</code></td>
                <td class="text-preview">${job.text_preview || 'N/A'}</td>
                <td>${createdTime}</td>
                <td>
                    ${job.status === 'completed' ?
                        `<button class="btn-small btn-primary" onclick="downloadJobAudio('${job.job_id}')">Download</button>` :
                        ''}
                    ${(job.status === 'queued' || job.status === 'processing') ?
                        `<button class="btn-small btn-danger" onclick="cancelQueueJob('${job.job_id}')">Cancel</button>` :
                        ''}
                    ${job.status === 'failed' ?
                        `<span class="error-text" title="${job.error || 'Unknown error'}"> Failed</span>` :
                        ''}
                </td>
            </tr>
        `;
    });

    html += `
            </tbody>
        </table>
    `;

    container.innerHTML = html;
}

function getStatusClass(status) {
    switch (status) {
        case 'queued':
            return 'status-queued';
        case 'processing':
            return 'status-processing';
        case 'completed':
            return 'status-completed';
        case 'failed':
            return 'status-failed';
        case 'cancelled':
            return 'status-cancelled';
        default:
            return '';
    }
}

function getStatusIcon(status) {
    switch (status) {
        case 'queued':
            return '';
        case 'processing':
            return '';
        case 'completed':
            return '';
        case 'failed':
            return '';
        case 'cancelled':
            return '';
        default:
            return '';
    }
}

async function cancelQueueJob(jobId) {
    if (!confirm('Are you sure you want to cancel this job?')) {
        return;
    }

    try {
        const response = await fetch(`/api/cancel/${jobId}`, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            loadQueue();
        } else {
            alert('Failed to cancel job: ' + data.error);
        }
    } catch (error) {
        console.error('Error cancelling job:', error);
        alert('Error cancelling job');
    }
}

function downloadJobAudio(jobId) {
    window.location.href = `/api/download/${jobId}`;
}
