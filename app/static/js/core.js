/**
 * MyFoil Core Bundle
 * base.js + system_status.js
 * DO NOT EDIT - run: python scripts/build_js.py
 */

// ============================================================
// base.js
// ============================================================
/**
 * MyFoil Global Utilities & Initialization
 */


// Debug logging
window.debugLog = function (...args) {
    if (window.DEBUG_MODE) {
        console.log(...args);
    }
};
window.debugWarn = function (...args) {
    if (window.DEBUG_MODE) {
        console.warn(...args);
    }
};
window.debugError = function (...args) {
    console.error(...args);
};

window.safeFetch = function (url, options = {}) {
    // Force URL to be relative to origin without credentials
    if (typeof url === 'string' && url.startsWith('/')) {
        url = window.location.origin + url;
    }
    return fetch(url, options);
};

// Configure jQuery globally to avoid credential issues with relative URLs
if (typeof $ !== 'undefined') {
    $.ajaxSetup({
        beforeSend: function (xhr, settings) {
            if (settings && settings.url && typeof settings.url === 'string' && settings.url.startsWith('/')) {
                settings.url = window.location.origin + settings.url;
            }
        }
    });
}

/**
 * Global Translation Helper
 * @param {string} key 
 * @returns {string}
 */
window.t = function (key) {
    return (window.translations && window.translations[key]) || key;
};

/**
 * Show a toast notification
 * @param {string} message 
 * @param {string} type 'success' | 'danger'
 */
function showToast(message, type = 'success') {
    const container = document.getElementById('toastContainer');
    if (!container) return;
    const notification = document.createElement('div');
    const colorClass = type === 'success' ? 'is-success' : 'is-danger';

    notification.className = `notification ${colorClass} is-toast`;
    notification.innerHTML = `
        <button class="delete" onclick="this.parentElement.remove()"></button>
        <div class="is-flex is-align-items-center gap-2">
            <i class="bi bi-${type === 'success' ? 'check-circle' : 'exclamation-circle'}"></i>
            <strong></strong>
        </div>
    `;
    notification.querySelector('strong').textContent = message;

    container.appendChild(notification);
    setTimeout(() => {
        notification.style.opacity = '0';
        notification.style.transition = 'opacity 0.5s';
        setTimeout(() => notification.remove(), 500);
    }, 3000);
}

/**
 * Global HTML Sanitization
 * @param {string} text 
 * @returns {string}
 */
window.escapeHtml = function (text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
};

/**
 * Normalize envelope-style API responses: { code, success, data } or direct payload
 */
window.unwrap = function (res) {
    try {
        if (res && res.data !== undefined) return res.data;
    } catch (e) {}
    return res;
};

/**
 * Coerce various API shapes into an array for safe iteration
 */
window.coerceArray = function (res) {
    const payload = unwrap(res);
    if (Array.isArray(payload)) return payload;
    if (!payload || typeof payload !== 'object') return [];
    const keys = ['plugins', 'paths', 'sources', 'backups', 'tokens', 'users', 'webhooks', 'files', 'results'];
    for (let k of keys) if (Array.isArray(payload[k])) return payload[k];
    for (let k of Object.keys(payload)) if (Array.isArray(payload[k])) return payload[k];
    return [];
};

/**
 * Toggle between light and dark themes
 */
function toggleTheme() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';
    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);
}

/**
 * Update Grid Zoom for the library cards
 * @param {string|number} val 
 */
window.updateGridZoom = function (val) {
    const zoomVal = parseInt(val);
    if (isNaN(zoomVal)) return;

    // Set variable on root so it can be used anywhere
    document.documentElement.style.setProperty('--card-width', `${zoomVal}px`);

    // Force update on container if it exists
    const container = document.getElementById('libraryContainer');
    if (container) {
        container.style.setProperty('--card-width', `${zoomVal}px`);
    }
    const upcomingContainer = document.getElementById('upcomingContainer');
    if (upcomingContainer) {
        upcomingContainer.style.setProperty('--card-width', `${zoomVal}px`);
    }

    localStorage.setItem('gridZoom', zoomVal);
};

/**
 * Debounce function to limit the rate at which a function is executed
 * @param {Function} func 
 * @param {number} wait 
 * @returns 
 */
window.debounce = function (func, wait) {
    let timeout;
    return function (...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), wait);
    };
};

// Global Initialization
document.addEventListener('DOMContentLoaded', function () {
    // Apply saved zoom immediately
    const savedZoom = localStorage.getItem('gridZoom') || 240;
    window.updateGridZoom(savedZoom);

    // Apply saved theme immediately
    const savedTheme = localStorage.getItem('theme') || (window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
    document.documentElement.setAttribute('data-theme', savedTheme);

    // Load system information for footer
    $.getJSON('/api/system/info', function (raw) {
        // Normalize envelope { code, success, data } or direct payload
        const data = (raw && raw.data !== undefined) ? raw.data : raw;
        const idSource = document.getElementById('idSource');
        const buildDisplay = document.getElementById('buildVersionDisplay');
        if (idSource) idSource.innerText = data?.id_source || 'N/A';
        if (buildDisplay) buildDisplay.innerText = data?.build_version || 'Unknown';
    }).fail(function () {
        const idSource = document.getElementById('idSource');
        const buildDisplay = document.getElementById('buildVersionDisplay');
        if (idSource) idSource.innerText = 'N/A';
        if (buildDisplay) buildDisplay.innerText = 'Unknown';
    });

    // WebSocket Global Listener
    if (typeof io !== 'undefined') {
        window.socket = io({
            transports: ['polling'],
            upgrade: false,
            reconnection: true,
            reconnectionAttempts: 10,
            reconnectionDelay: 2000,
            timeout: 20000
        });

        socket.on('library_updated', (data) => {
            window.debugLog('WebSocket: Library update received', data);
            if (typeof refreshLibrary === 'function') {
                refreshLibrary();
            }
        });
    }

    // WebSocket Global Listener
    if (typeof io !== 'undefined') {
        // ... (WebSocket init code remains here or inside DOMContentLoaded is fine, but debounce must be global)
    }

    // Service Worker Registration for PWA
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/static/sw.js')
            .then((registration) => {
                registration.addEventListener('updatefound', () => {
                    const newWorker = registration.installing;
                    if (!newWorker) return;
                    newWorker.addEventListener('statechange', () => {
                        if (newWorker.state === 'installed' && navigator.serviceWorker.controller) {
                            showToast(window.t('Nova versão disponível! Recarregue a página.'), 'success');
                        }
                    });
                });
            })
            .catch((error) => console.error('Service Worker registration failed:', error));
    }

    // PWA Install Prompt
    let deferredPrompt;
    window.addEventListener('beforeinstallprompt', (e) => {
        deferredPrompt = e;
    });
});


// ============================================================
// system_status.js
// ============================================================
// System Status Manager
class SystemStatusManager {
    constructor() {
        // Initialize Socket.IO with robust configuration for proxy environments
        // - transports: ['polling', 'websocket'] - Try polling first (more reliable behind proxies)
        // - upgrade: true - Allow upgrade to websocket if possible
        // - reconnection: true - Auto-reconnect on disconnect
        // - reconnectionAttempts: 5 - Limit reconnection attempts
        // If the Socket.IO client isn't loaded, create a noop socket to avoid runtime errors
        if (typeof io === 'undefined') {
            console.warn('Socket.IO client not loaded; realtime status disabled');
            this.socket = {
                on: function () { },
                off: function () { },
                emit: function () { },
            };
        } else if (typeof socket === 'undefined') {
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
                // console.log('✅ Socket.IO connected successfully');
            });

            this.socket.on('connect_error', (error) => {
                console.warn('⚠️ Socket.IO connection error:', error.message);
            });

            this.socket.on('disconnect', (reason) => {
                // console.log('🔌 Socket.IO disconnected:', reason);
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

        // Poll every 60 seconds as fallback (increased from 15s for resource efficiency)
        // Skip if tab is not visible to save server resources
        setInterval(() => {
            if (document.visibilityState === 'visible') {
                this.fetchStatus();
            }
        }, 60000);
    }

    async fetchStatus() {
        try {
            // Using safeFetch to strip any credentials from current URL
            const response = await window.safeFetch('/api/system/jobs');
            if (response.ok) {
                const raw = await response.json();
                // Support both envelope-style responses { code, success, data } and raw payloads
                const payload = raw && raw.data !== undefined ? raw.data : raw;
                this.updateStatus(payload.jobs, payload.titledb);
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
            text.textContent = t('status.system_idle');
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
            activeList.innerHTML = `<p class="has-text-grey-light has-text-centered py-4">${t('status.no_active_ops')}</p>`;
        } else {
            activeList.innerHTML = status.active.map(job => this.renderActiveJob(job)).join('');
        }

        // Update history
        if (status.history.length === 0) {
            historyList.innerHTML = `<p class="has-text-grey-light has-text-centered py-4">${t('status.no_recent_activity')}</p>`;
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
                        onclick="cancelJob('${job.id}', this)"
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
            'library_scan': t('job.library_scan'),
            'titledb_update': t('job.titledb_update'),
            'metadata_fetch': t('job.metadata_fetch'),
            'metadata_fetch_all': t('job.metadata_fetch'),
            'file_identification': t('job.file_identification'),
            'backup': t('job.backup'),
            'cleanup': t('job.cleanup'),
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
    if (clearAllJobsRunning) return;

    const button = document.querySelector('[onclick="clearAllJobs()"]');

    // Check if confirming
    if (button && button.dataset.confirming !== "true") {
        button.dataset.confirming = "true";
        const originalText = button.textContent;
        button.textContent = "Confirm Clear?";
        button.classList.add('is-warning');

        // Reset after 3 seconds
        setTimeout(() => {
            if (button && button.dataset.confirming === "true") {
                button.dataset.confirming = "false";
                button.textContent = originalText;
                button.classList.remove('is-warning');
            }
        }, 3000);
        return;
    }

    clearAllJobsRunning = true;
    const originalText = button ? (button.getAttribute('data-original-text') || 'Clear All') : 'Clear';

    // Show loading state
    if (button) {
        button.textContent = 'Clearing...';
        button.disabled = true;
    }

    // Use setTimeout to allow UI to update before making the request
    setTimeout(async () => {
        try {
            const response = await fetch(window.location.origin + '/api/system/jobs/cleanup', { method: 'POST' });

            if (response.ok) {
                if (statusManager) statusManager.fetchStatus();
                showToast(t('toast.cleared_success'), 'success');
            } else {
                console.error('Failed to clear jobs');
                showToast(t('toast.cleared_error'), 'danger');
            }
        } catch (error) {
            console.error('Error clearing jobs:', error);
            showToast(t('toast.comm_error'), 'danger');
        } finally {
            clearAllJobsRunning = false;
            // Reset button
            if (button) {
                button.textContent = originalText;
                button.disabled = false;
                button.dataset.confirming = "false";
                button.classList.remove('is-warning');
            }
        }
    }, 10);

}

async function cancelJob(jobId, btnElement) {
    // Confirmation logic using button state
    if (btnElement && btnElement.dataset.confirming !== "true") {
        btnElement.dataset.confirming = "true";
        btnElement.classList.remove('is-light');
        btnElement.classList.add('is-warning'); // Highlight button

        // Reset after 3 seconds
        setTimeout(() => {
            if (btnElement && btnElement.dataset.confirming === "true") {
                btnElement.dataset.confirming = "false";
                btnElement.classList.remove('is-warning');
                btnElement.classList.add('is-light');
            }
        }, 3000);
        return;
    }

    // Execution logic
    if (btnElement) {
        btnElement.classList.add('is-loading');
        btnElement.disabled = true;
    }

    try {
        const response = await fetch(window.location.origin + `/api/system/jobs/${jobId}/cancel`, { method: 'POST' });

        if (response.ok) {
            const data = await response.json();
            if (statusManager) statusManager.fetchStatus();
            if (!data.success) {
                console.error(`Failed to cancel job: ${data.error}`);
                showToast(`${t('toast.cancel_error')}: ${data.error}`, 'danger');
            } else {
                showToast(t('toast.cancel_success'), 'success');
            }
        } else {
            console.error('Failed to cancel job - HTTP error');
            showToast(t('toast.cancel_error'), 'danger');
        }
    } catch (error) {
        console.error('Error cancelling job:', error);
        showToast(t('toast.comm_error'), 'danger');
    } finally {
        if (btnElement) {
            btnElement.classList.remove('is-loading');
            btnElement.disabled = false;
            // Also reset confirmation state
            btnElement.dataset.confirming = "false";
            btnElement.classList.remove('is-warning');
            btnElement.classList.add('is-light');
        }
    }
}

async function refreshTdbRemote() {
    try {
        const icon = document.getElementById('refreshRemoteIcon');
        if (icon) icon.classList.add('spin');

        // Correct endpoint to refresh remote dates for TitleDB sources
        const response = await fetch('/api/settings/titledb/sources/refresh-dates', { method: 'POST' });
        if (response.ok) {
            // Wait a bit then fetch status
            setTimeout(() => {
                if (statusManager) statusManager.fetchStatus();
            }, 1000);
        }
    } catch (error) {
        console.error('Error refreshing TDB remote:', error);
    } finally {
        const icon = document.getElementById('refreshRemoteIcon');
        if (icon) icon.classList.remove('spin');
    }
}

