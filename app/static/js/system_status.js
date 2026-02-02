// System Status Manager
class SystemStatusManager {
    constructor() {
        // Initialize Socket.IO with robust configuration for proxy environments
        // - transports: ['polling', 'websocket'] - Try polling first (more reliable behind proxies)
        // - upgrade: true - Allow upgrade to websocket if possible
        // - reconnection: true - Auto-reconnect on disconnect
        // - reconnectionAttempts: 5 - Limit reconnection attempts
        if (typeof socket === 'undefined') {
            this.socket = io({
                transports: ['websocket', 'polling'], // Try websocket first (more stable)
                upgrade: true,
                reconnection: true,
                reconnectionAttempts: 10,
                reconnectionDelay: 1000,
                reconnectionDelayMax: 5000,
                timeout: 10000
            });

            // Log connection status for debugging
            this.socket.on('connect', () => {
                console.log('✅ Socket.IO connected successfully');
            });

            this.socket.on('connect_error', (error) => {
                console.warn('⚠️ Socket.IO connection error:', error.message);
            });

            this.socket.on('disconnect', (reason) => {
                console.log('🔌 Socket.IO disconnected:', reason);
            });
        } else {
            this.socket = socket;
        }

        this.currentStatus = null;
        this.init();
    }

    init() {
        // Listen for job updates via WebSocket
        this.socket.on('job_update', (status) => {
            // Handle single job update by merging into current list
            if (status && status.id) {
                const updatedJobs = [...(this.currentJobs || [])];
                const index = updatedJobs.findIndex(j => j.id === status.id);
                if (index !== -1) {
                    updatedJobs[index] = status;
                } else {
                    updatedJobs.unshift(status);
                }
                this.updateStatus(updatedJobs);
            } else {
                this.updateStatus(status);
            }
        });

        // Initial load
        this.fetchStatus();

        // Poll every 15 seconds as fallback (and to keep UI fresh if socket misses)
        setInterval(() => this.fetchStatus(), 15000);
    }

    async fetchStatus() {
        try {
            const response = await fetch('/api/system/jobs');
            if (response.ok) {
                const data = await response.json();
                this.updateStatus(data.jobs, data.titledb);
            }
        } catch (error) {
            console.error('Failed to fetch jobs:', error);
        }
    }

    updateStatus(jobs, titledb) {
        if (!jobs) return;

        // If single job object provided, convert to array (legacy fallback)
        const jobsArray = Array.isArray(jobs) ? jobs : [jobs];
        this.currentJobs = jobsArray;

        // Update cached titledb info if provided
        if (titledb) {
            this.currentTitleDB = titledb;
        }

        const active = jobsArray.filter(j => j.status === 'running' || j.status === 'scheduled');
        const history = jobsArray.filter(j => j.status === 'completed' || j.status === 'failed');

        const status = {
            has_active: active.length > 0,
            active: active,
            history: history,
            titledb: this.currentTitleDB
        };

        this.updateIndicator(status);
        this.updateModal(status);
    }

    updateIndicator(status) {
        const indicator = document.getElementById('systemStatusIndicator');
        const icon = document.getElementById('statusIcon');
        const text = document.getElementById('statusText');
        const progressContainer = document.getElementById('statusProgress');
        const progressBar = document.getElementById('progressBar');

        if (!indicator) return;

        if (status.has_active && status.active.length > 0) {
            // Show active job
            const job = status.active[0]; // Primary job

            icon.innerHTML = '<i class="bi bi-arrow-repeat spin has-text-info"></i>';
            if (job.progress && job.progress.message) {
                text.textContent = job.progress.message;
            } else {
                text.textContent = this.getJobLabel(job);
            }

            if (job.progress && job.progress.percent) {
                progressContainer.classList.remove('is-hidden');
                progressBar.value = job.progress.percent;
            } else {
                progressContainer.classList.add('is-hidden');
            }

            indicator.classList.add('is-active');
        } else {
            // Idle state
            icon.innerHTML = '<i class="bi bi-check-circle has-text-success"></i>';
            text.textContent = 'System Idle';
            progressContainer.classList.add('is-hidden');
            indicator.classList.remove('is-active');
        }
    }

    updateModal(status) {
        const activeList = document.getElementById('activeJobsList');
        const historyList = document.getElementById('jobHistoryList');

        if (!activeList || !historyList) return;

        // Update active jobs list
        if (status.active.length === 0) {
            activeList.innerHTML = '<p class="has-text-grey-light has-text-centered py-4">No active operations</p>';
        } else {
            activeList.innerHTML = status.active.map(job => this.renderActiveJob(job)).join('');
        }

        // Update history
        if (status.history.length === 0) {
            historyList.innerHTML = '<p class="has-text-grey-light has-text-centered py-4">No recent activity</p>';
        } else {
            historyList.innerHTML = status.history.slice(0, 10).map(job => this.renderHistoryJob(job)).join('');
        }

        // Update TitleDB info
        if (status.titledb) {
            const tdb = status.titledb;
            this.updateElementText('tdbSource', tdb.name);
            this.updateElementText('tdbFile', tdb.loaded_titles_file);
            this.updateElementText('tdbLastDownload', tdb.last_download_date);

            const remoteEl = document.getElementById('tdbRemoteDate');
            const refreshIcon = document.getElementById('refreshRemoteIcon');

            if (refreshIcon) {
                if (tdb.is_fetching) refreshIcon.classList.add('spin');
                else refreshIcon.classList.remove('spin');
            }

            if (remoteEl) {
                let content = tdb.remote_date || 'Unknown';
                if (tdb.update_available) {
                    content += ' <span class="tag is-info is-light is-small ml-2">Update Available</span>';
                }

                if (tdb.last_error) {
                    content += ` <span class="has-text-danger ml-1" title="${tdb.last_error}"><i class="bi bi-exclamation-triangle"></i></span>`;
                }

                remoteEl.innerHTML = content;

                if (tdb.remote_date && tdb.remote_date !== 'Unknown') {
                    remoteEl.classList.add('has-text-info');
                }
            }
        }
    }

    updateElementText(id, text) {
        const el = document.getElementById(id);
        if (el) el.textContent = text || '-';
    }

    renderActiveJob(job) {
        const icon = this.getJobIcon(job.type);
        const statusColor = job.status === 'failed' ? 'danger' : 'info';
        const progress = (job.progress && job.progress.percent) || 0;
        const message = (job.progress && job.progress.message) || 'Initializing...';
        const current = (job.progress && job.progress.current);
        const total = (job.progress && job.progress.total);
        const isStuck = job.is_stuck || false;

        let cancelButton = '';
        if (job.status === 'running' || job.status === 'scheduled') {
            cancelButton = `
                <button class="button is-small is-danger is-light ml-2"
                        onclick="cancelJob('${job.id}')"
                        title="Cancel this job">
                    <span class="icon"><i class="bi bi-x-circle"></i></span>
                </button>
            `;
        }

        return `
            <div class="box is-shadowless border mb-3 ${isStuck ? 'has-background-warning-light' : ''}"
                 style="border-left: 4px solid var(--bulma-info) !important;">
                <div class="is-flex is-justify-content-space-between is-align-items-center mb-2">
                    <div>
                        <span class="icon-text">
                            <span class="icon">${icon}</span>
                            <span class="has-text-weight-bold">${this.getJobLabel(job)}</span>
                            ${isStuck ? '<span class="tag is-warning is-light ml-2">STUCK</span>' : ''}
                        </span>
                    </div>
                    <div class="is-flex is-align-items-center">
                        <span class="tag is-${statusColor} is-light">${job.status}</span>
                        ${cancelButton}
                    </div>
                </div>

                 <progress class="progress is-info is-small mb-2" value="${progress}" max="100">${progress}%</progress>

                 <div class="is-flex is-justify-content-space-between is-size-7 opacity-70">
                    <span>${message}</span>
                    ${current !== undefined ? `<span>${current} / ${total || '?'}</span>` : ''}
                </div>
            </div>
        `;
    }

    renderHistoryJob(job) {
        const icon = this.getJobIcon(job.type);
        const statusClass = job.status === 'completed' ? 'has-text-success' : 'has-text-danger';
        const statusIcon = job.status === 'completed' ? '<i class="bi bi-check-circle"></i>' : '<i class="bi bi-x-circle"></i>';

        let timeStr = 'Unknown';
        if (job.completed_at) {
            timeStr = new Date(job.completed_at).toLocaleTimeString();
        }

        // Preview of results
        let resultPreview = '';
        if (job.result && Object.keys(job.result).length > 0) {
            const items = Object.entries(job.result)
                .map(([k, v]) => `<strong>${k}:</strong> ${v}`)
                .join(' | ');
            resultPreview = `<div class="mt-1 is-size-7 has-text-grey">${items}</div>`;
        } else if (job.error) {
            resultPreview = `<div class="mt-1 is-size-7 has-text-danger">Error: ${job.error}</div>`;
        }

        return `
            <div class="py-2 border-bottom">
                <div class="is-flex is-justify-content-space-between is-align-items-center">
                    <div class="is-flex is-align-items-center">
                        <span class="mr-2 ${statusClass}">${statusIcon}</span>
                        <span class="icon mr-2">${icon}</span>
                        <span class="is-size-6">${this.getJobLabel(job)}</span>
                    </div>
                    <span class="is-size-7 has-text-grey">${timeStr}</span>
                </div>
                ${resultPreview}
            </div>
        `;
    }

    getJobIcon(type) {
        const icons = {
            'library_scan': '<i class="bi bi-folder-open has-text-info"></i>',
            'titledb_update': '<i class="bi bi-cloud-download has-text-primary"></i>',
            'metadata_fetch': '<i class="bi bi-stars has-text-warning"></i>',
            'metadata_fetch_all': '<i class="bi bi-stars has-text-warning"></i>',
            'file_identification': '<i class="bi bi-fingerprint has-text-success"></i>',
            'backup': '<i class="bi bi-shield-check has-text-link"></i>',
            'cleanup': '<i class="bi bi-trash has-text-danger"></i>',
        };
        return icons[type] || '<i class="bi bi-gear"></i>';
    }

    getJobLabel(job) {
        const labels = {
            'library_scan': 'Library Scan',
            'titledb_update': 'TitleDB Update',
            'metadata_fetch': 'Metadata Fetch',
            'metadata_fetch_all': 'Full Metadata Fetch',
            'file_identification': 'File Identification',
            'backup': 'Backup',
            'cleanup': 'Cleanup',
        };
        return labels[job.type] || job.type;
    }
}

// Initialize
let statusManager;
document.addEventListener('DOMContentLoaded', () => {
    statusManager = new SystemStatusManager();
});

function openStatusModal() {
    const modal = document.getElementById('statusModal');
    if (modal) {
        modal.classList.add('is-active');
        // Refresh when opening
        if (statusManager) statusManager.fetchStatus();
    }
}

function closeStatusModal() {
    const modal = document.getElementById('statusModal');
    if (modal) modal.classList.remove('is-active');
}

function refreshJobStatus() {
    if (statusManager) statusManager.fetchStatus();
}

let clearAllJobsRunning = false;

async function clearAllJobs() {
    // Prevent multiple simultaneous clicks
    if (clearAllJobsRunning) {
        console.warn('Clear jobs already running...');
        return;
    }

    if (!confirm('Are you sure you want to clear all active operations? Stuck jobs (> 1h) will be marked as failed.')) {
        return;
    }

    clearAllJobsRunning = true;

    // Show loading state
    const button = document.querySelector('[onclick="clearAllJobs()"]');
    const originalText = button ? button.textContent : '';
    if (button) {
        button.textContent = 'Clearing...';
        button.disabled = true;
    }

    // Use setTimeout to allow UI to update before making the request
    setTimeout(async () => {
        try {
            const response = await fetch('/api/system/jobs/cleanup', { method: 'POST' });

            if (response.ok) {
                if (statusManager) statusManager.fetchStatus();
                alert('Active operations cleared. Stuck jobs have been cancelled.');
            } else {
                console.error('Failed to clear jobs');
                alert('Failed to clear operations.');
            }
        } catch (error) {
            console.error('Error clearing jobs:', error);
            alert('Error communicating with server.');
        } finally {
            clearAllJobsRunning = false;
            if (button) {
                button.textContent = originalText;
                button.disabled = false;
            }
        }
    }, 10); // Small delay to allow UI update
}

async function cancelJob(jobId) {
    if (!confirm('Cancel this job? It will be marked as failed.')) {
        return;
    }

    try {
        const response = await fetch(`/api/system/jobs/${jobId}/cancel`, { method: 'POST' });

        if (response.ok) {
            const data = await response.json();
            if (statusManager) statusManager.fetchStatus();
            if (!data.success) {
                console.error(`Failed to cancel job: ${data.error}`);
            }
        } else {
            console.error('Failed to cancel job - HTTP error');
        }
    } catch (error) {
        console.error('Error cancelling job:', error);
    }
}

async function refreshTdbRemote() {
    try {
        const icon = document.getElementById('refreshRemoteIcon');
        if (icon) icon.classList.add('spin');

        const response = await fetch('/api/settings/titledb/refresh_remote', { method: 'POST' });
        if (response.ok) {
            // Wait a bit then fetch status
            setTimeout(() => {
                if (statusManager) statusManager.fetchStatus();
            }, 1000);
        }
    } catch (error) {
        console.error('Error refreshing TDB remote:', error);
    }
}
