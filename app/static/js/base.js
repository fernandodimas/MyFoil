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
            <strong>${message}</strong>
        </div>
    `;

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
    $.getJSON('/api/system/info', function (data) {
        const idSource = document.getElementById('idSource');
        const buildDisplay = document.getElementById('buildVersionDisplay');
        if (idSource) idSource.innerText = data.id_source || 'N/A';
        if (buildDisplay) buildDisplay.innerText = data.build_version || 'Unknown';
    }).fail(function () {
        const idSource = document.getElementById('idSource');
        const buildDisplay = document.getElementById('buildVersionDisplay');
        if (idSource) idSource.innerText = 'N/A';
        if (buildDisplay) buildDisplay.innerText = 'Unknown';
    });

    // WebSocket Global Listener
    if (typeof io !== 'undefined') {
        const socket = io({
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
