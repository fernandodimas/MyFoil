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
                transports: ['polling', 'websocket'],
                upgrade: true,
                reconnection: true,
                reconnectionAttempts: 5,
                reconnectionDelay: 1000,
                timeout: 20000
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
            this.updateStatus(status);
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
                this.updateStatus(data.jobs);
            }
        } catch (error) {
            console.error('Failed to fetch jobs:', error);
        }
    }

    updateStatus(jobs) {
        if (!Array.isArray(jobs)) return;
        this.currentJobs = jobs;

        const active = jobs.filter(j => j.status === 'running' || j.status === 'scheduled');
        const history = jobs.filter(j => j.status === 'completed' || j.status === 'failed');

        const status = {
            has_active: active.length > 0,
            active: active,
            history: history
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
            text.textContent = this.getJobLabel(job);

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
    }

    renderActiveJob(job) {
        const icon = this.getJobIcon(job.type);
        const statusColor = job.status === 'failed' ? 'danger' : 'info';
        const progress = (job.progress && job.progress.percent) || 0;
        const message = (job.progress && job.progress.message) || 'Initializing...';
        const current = (job.progress && job.progress.current);
        const total = (job.progress && job.progress.total);

        return `
            <div class="box is-shadowless border mb-3" style="border-left: 4px solid var(--bulma-info) !important;">
                <div class="is-flex is-justify-content-space-between is-align-items-center mb-2">
                    <div>
                        <span class="icon-text">
                            <span class="icon">${icon}</span>
                            <span class="has-text-weight-bold">${this.getJobLabel(job)}</span>
                        </span>
                    </div>
                    <span class="tag is-${statusColor} is-light">${job.status}</span>
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

async function clearAllJobs() {
    if (!confirm('Are you sure you want to clear all active operations? This won\'t stop the background processes but will remove them from the UI tracking.')) {
        return;
    }

    try {
        const response = await fetch('/api/system/jobs/cleanup', { method: 'POST' });
        if (response.ok) {
            if (statusManager) statusManager.fetchStatus();
            alert('Active operations cleared from tracking.');
        } else {
            console.error('Failed to clear jobs');
            alert('Failed to clear operations.');
        }
    } catch (error) {
        console.error('Error clearing jobs:', error);
        alert('Error communicating with server.');
    }
}
