/**
 * MyFoil Library Index Logic
 * Handles library loading, filtering, sorting, and infinite scroll.
 */

let games = [];
window.filteredGames = [];
let currentSort = localStorage.getItem('myfoil_library_sort') || 'name-asc';
let currentView = localStorage.getItem('viewMode') || 'card';
let ignorePreferences = {};  // Cache for ignore preferences per title_id

// Fetch all ignore preferences on load
function loadIgnorePreferences() {
    return $.getJSON('/api/wishlist/ignore', (data) => {
        ignorePreferences = data || {};
        debugLog('Ignore preferences loaded:', ignorePreferences);
    }).fail(() => {
        debugWarn('Failed to load ignore preferences');
        showToast(t('Failed to load ignore preferences'), 'danger');
        ignorePreferences = {};
    });
}

// Lazy Loading Images
function observeImages() {
    if ('IntersectionObserver' in window) {
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    const src = img.getAttribute('data-src');
                    if (src) {
                        img.src = src;
                        img.onload = () => {
                            img.style.opacity = 1;
                        };
                        img.removeAttribute('data-src');
                    }
                    observer.unobserve(img);
                }
            });
        });

        document.querySelectorAll('img.lazy-image').forEach(img => {
            imageObserver.observe(img);
        });
    } else {
        // Fallback for older browsers
        document.querySelectorAll('img.lazy-image').forEach(img => {
            const src = img.getAttribute('data-src');
            if (src) {
                img.src = src;
                img.style.opacity = 1;
            }
        });
    }
}

// Local fallback for debounce to avoid cache/loading issues
const _debounce = (func, wait) => {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
};

function initGenders(gamesList) {
    const genders = new Set();
    gamesList.forEach(g => {
        if (g && g.category && Array.isArray(g.category)) {
            g.category.forEach(c => genders.add(c));
        }
    });

    const currentVal = $('#filterGender').val();
    const genderSelect = $('#filterGender').empty().append(`<option value="">${t('All Genres')}</option>`);
    Array.from(genders).sort().forEach(g => genderSelect.append(new Option(g, g)));
    if (currentVal) $('#filterGender').val(currentVal);
}

function initTags(gamesList) {
    const tags = new Set();
    gamesList.forEach(g => {
        if (g && g.tags && Array.isArray(g.tags)) {
            g.tags.forEach(t => tags.add(t));
        }
    });

    const currentVal = $('#filterTag').val();
    const tagSelect = $('#filterTag').empty().append(`<option value="">${t('All Tags')}</option>`);
    Array.from(tags).sort().forEach(t => tagSelect.append(new Option(t, t)));
    if (currentVal) $('#filterTag').val(currentVal);
}

// Keyboard Shortcuts
document.addEventListener('keydown', (e) => {
    // Ctrl/Cmd + K: Focus search
    if ((e.ctrlKey || e.metaKey) && e.key === 'k') {
        e.preventDefault();
        $('#navbarSearch').focus();
    }

    // ESC: Clear search and close all modals
    if (e.key === 'Escape') {
        const searchValue = $('#navbarSearch').val();
        if (searchValue) {
            clearSearch();
        }
        $('.modal').removeClass('is-active');
    }
});

function setView(view) {
    currentView = view;
    localStorage.setItem('viewMode', view);
    $('#viewToggleButtons .button').removeClass('is-primary');
    $(`#btnView${view.charAt(0).toUpperCase() + view.slice(1)}`).addClass('is-primary');
    renderLibrary();
}

// Grid zoom logic moved to base.js for global availability

function renderLibrary() {
    const container = $('#libraryContainer');
    const paged = window.filteredGames;
    const totalItems = paged.length;

    // Clear container and reset scroll
    container.empty();

    // Show item count
    $('#totalItemsCount, #totalItemsCountMobile').text(`${totalItems} ${t('Jogos')}`);

    // Handle list view width
    if (currentView === 'list') {
        container.addClass('is-list-view');
    } else {
        container.removeClass('is-list-view');
    }

    // Use infinite scroll instead of pagination
    resetInfiniteScroll();
    setupInfiniteScroll();
}

function refreshLibrary() {
    console.log("Refreshing library data...");

    // Show loading indicator
    $('#loadingIndicator').removeClass('is-hidden');
    $('#libraryContainer').empty();

    $.getJSON('/api/library', function (data) {
        games = (data && data.items) ? data.items : (Array.isArray(data) ? data : []);
        localStorage.setItem('myfoil_library_cache', JSON.stringify(games));
        localStorage.setItem('myfoil_library_cache_time', Date.now().toString());
        initGenders(games);
        initTags(games);

        // Hide loading indicator
        $('#loadingIndicator').addClass('is-hidden');

        // Reset and apply filters
        applyFilters();
        showToast(t('Library updated!'), 'success');
    }).fail(() => {
        $('#loadingIndicator').addClass('is-hidden');
        showToast(t('Failed to refresh library'), 'error');
    });
}

function renderCardView(items) {
    items.forEach((game, index) => {
        const statusDotClass = game.status_color === 'orange' ? 'bg-orange' : (game.status_color === 'green' ? 'bg-green' : 'bg-gray');
        const safeName = escapeHtml(game.name);
        const safeId = escapeHtml(game.id);

        const card = $(`
            <div class="grid-item" data-index="${index}" data-game-id="${safeId}" tabindex="0" role="button" aria-label="${safeName}" onclick="focusAndOpenGame('${safeId}')">
                <div class="card game-card is-paddingless">
                    <div class="card-image">
                        <figure class="image is-16by9 bg-light-soft">
                            <img src="/static/img/no-icon.png" 
                                 data-src="${game.bannerUrl || game.iconUrl || '/static/img/no-icon.png'}" 
                                 alt="${safeName}" 
                                 loading="lazy"
                                 class="lazy-image"
                                 style="object-fit: cover; opacity: 0; transition: opacity 0.3s;">
                        </figure>
                    </div>
                    <div class="card-content">
                        <div class="is-flex is-justify-content-end is-align-items-center mb-1">
                            <span class="font-mono is-size-7 has-text-weight-bold">v${game.display_version}</span>
                        </div>
                        
                        <div class="is-flex is-align-items-center mb-2">
                            ${game.metacritic_score ? `
                                <span class="tag is-small is-light ${game.metacritic_score >= 75 ? 'is-success' : (game.metacritic_score >= 50 ? 'is-warning' : 'is-danger')} mr-1" title="Metacritic">
                                    <i class="bi bi-trophy-fill mr-1"></i>${game.metacritic_score}
                                </span>
                            ` : ''}
                            ${game.playtime_main ? `
                                <span class="tag is-small is-light is-info" title="Playtime">
                                    <i class="bi bi-clock-history mr-1"></i>${game.playtime_main}h
                                </span>
                            ` : ''}
                        </div>
                        
                        <h3 class="game-title title is-6 has-text-weight-bold mb-3 line-clamp-2" title="${safeName}">${safeName}</h3>
                        
                        <div class="is-flex is-justify-content-between is-align-items-center mt-auto pt-2">
                            <div class="is-flex is-align-items-center gap-1">
                                <span class="status-dot ${statusDotClass}"></span>
                                <span class="is-size-7 opacity-70 font-mono">${game.size_formatted || '--'}</span>
                            </div>
                            <div class="is-flex gap-1 is-justify-content-end">
                                ${game.has_non_ignored_updates ? `<span class="tag tag-update has-text-weight-bold is-small">${t('UPDATE')}</span>` : ''}
                                ${game.has_non_ignored_dlcs ? `<span class="tag tag-dlc has-text-weight-bold is-small">${t('DLC')}</span>` : ''}
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `);
        $('#libraryContainer').append(card);
    });

    observeImages();
}

// Socket listener for library updates
if (typeof socket !== 'undefined' || (statusManager && statusManager.socket)) {
    const s = socket || statusManager.socket;
    s.on('library_updated', () => {
        console.log('🔄 Library update event received from socket');
        refreshLibrary();
    });
}

function renderIconView(items) {
    items.forEach((game, index) => {
        const statusDotClass = game.status_color === 'orange' ? 'bg-orange' : (game.status_color === 'green' ? 'bg-green' : 'bg-gray');
        const safeName = escapeHtml(game.name);
        const safeId = escapeHtml(game.id);

        const card = $(`
            <div class="grid-item" data-index="${index}" data-game-id="${safeId}" tabindex="0" role="button" aria-label="${safeName}" onclick="focusAndOpenGame('${safeId}')" title="${safeName}">
                <div class="card game-card is-paddingless is-shadowless">
                    <div class="card-image">
                        <figure class="image is-square bg-light relative">
                            <img src="/static/img/no-icon.png" 
                                 data-src="${game.iconUrl || '/static/img/no-icon.png'}" 
                                 alt="${safeName}" 
                                 loading="lazy"
                                 class="lazy-image p-0" 
                                 style="object-fit: cover; width: 100%; height: 100%; opacity: 0; transition: opacity 0.3s;">
                            <div class="status-indicator position-absolute">
                                <span class="status-dot ${statusDotClass}"></span>
                            </div>
                        </figure>
                    </div>
                </div>
            </div>
        `);
        $('#libraryContainer').append(card);
    });

    observeImages();
}

function renderListView(items) {
    const table = $(`
        <div class="column is-12" style="width: 100%;">
            <div class="table-container box is-paddingless shadow-sm overflow-hidden border-none">
                <table class="table is-fullwidth is-hoverable game-list-table mb-0">
                    <thead>
                        <tr class="has-background-light-soft" style="border-bottom: 2px solid var(--primary)">
                            <th width="65" class="has-text-centered p-1">${t('Ícone')}</th>
                            <th>${t('Título do Jogo')}</th>
                            <th width="140">${t('Title ID')}</th>
                            <th width="80" class="has-text-centered">${t('Versão')}</th>
                            <th class="is-hidden-mobile" width="80">${t('Ratings')}</th>
                            <th class="is-hidden-mobile" width="100">${t('Tamanho')}</th>
                            <th class="is-hidden-mobile" width="100">${t('Status')}</th>
                        </tr>
                    </thead>
                    <tbody></tbody>
                </table>
            </div>
        </div>
    `);
    items.forEach((game, index) => {
        const statusColor = game.status_color === 'orange' ? 'has-text-warning' : (game.status_color === 'green' ? 'has-text-success' : 'has-text-grey');
        const statusText = game.status_color === 'orange' ? t('Missing') : (game.status_color === 'green' ? t('Owned') : t('Incomplete'));

        table.find('tbody').append(`
            <tr data-index="${index}" data-game-id="${game.id}" tabindex="0" role="button" onclick="focusAndOpenGame('${game.id}')">
                <td class="p-1 has-text-centered"><img src="${game.iconUrl || '/static/img/no-icon.png'}" style="width: 32px; height: 32px; border-radius: 4px; object-fit: cover;"></td>
                <td class="is-vcentered">
                    <strong class="is-size-7-mobile">${game.name || 'Unknown'}</strong>
                    ${game.has_redundant_updates ? `<span class="tag tag-redundant ml-2 has-text-weight-bold">${t('X-UPD')}</span>` : ''}
                </td>
                <td class="font-mono is-size-7 is-vcentered">${game.id || '--'}</td>
                <td class="is-vcentered has-text-centered"><span class="tag is-light is-small">v${game.display_version || '0'}</span></td>
                <td class="is-hidden-mobile is-vcentered">
                    ${game.metacritic_score ? `<span class="tag is-small is-light ${game.metacritic_score >= 75 ? 'is-success' : (game.metacritic_score >= 50 ? 'is-warning' : 'is-danger')}" title="Metacritic">${game.metacritic_score}</span>` : '--'}
                </td>
                <td class="is-hidden-mobile is-vcentered font-mono is-size-7">${game.size_formatted || '--'}</td>
                <td class="is-hidden-mobile ${statusColor} has-text-weight-bold is-size-7 is-vcentered">${statusText}</td>
            </tr>
        `);
    });
    $('#libraryContainer').append(table);
}

function applyFilters() {
    const query = ($('#navbarSearch').val() || '').toLowerCase();
    const gender = $('#filterGender').val();
    const tag = $('#filterTag').val();

    const showOnlyBase = $('#btnFilterPendingBase').hasClass('is-primary');
    const showOnlyUpdates = $('#btnFilterPendingUpd').hasClass('is-primary');
    const showOnlyDlcs = $('#btnFilterPendingDlc').hasClass('is-primary');

    games.forEach(g => {
        if (!g) return;
        const gameIgnore = ignorePreferences[g.id] || {};
        const ignoredDlcs = gameIgnore.dlcs || {};
        const ignoredUpdates = gameIgnore.updates || {};

        let hasNonIgnoredUpdates = false;
        if (g.has_base && !g.has_latest_version) {
            const ownedVersion = parseInt(g.owned_version) || 0;
            const latestVersion = parseInt(g.latest_version_available) || 0;
            let allUpdatesIgnored = true;
            for (let v = ownedVersion + 1; v <= latestVersion; v++) {
                if (!ignoredUpdates[v.toString()]) {
                    allUpdatesIgnored = false;
                    break;
                }
            }
            hasNonIgnoredUpdates = !allUpdatesIgnored;
        }
        g.has_non_ignored_updates = hasNonIgnoredUpdates;

        let hasNonIgnoredDlcs = false;
        if (g.has_base && g.dlcs && Array.isArray(g.dlcs)) {
            hasNonIgnoredDlcs = g.dlcs.some(dlc => {
                const isIgnored = ignoredDlcs[dlc.app_id];
                const isNotOwned = !dlc.owned;
                return isNotOwned && !isIgnored;
            });
        }
        g.has_non_ignored_dlcs = hasNonIgnoredDlcs;

        if (!g.has_base) {
            g.status_color = 'orange';
            g.status_score = 0;
        } else if (g.has_non_ignored_updates || g.has_non_ignored_dlcs) {
            g.status_color = 'orange';
            g.status_score = 1;
        } else {
            g.status_color = 'green';
            g.status_score = 2;
        }
    });

    window.filteredGames = games.filter(g => {
        if (!g) return false;
        const matchesSearch = !query || g.name.toLowerCase().includes(query) || g.id.toLowerCase().includes(query);
        const matchesGender = !gender || (g.category && g.category.includes(gender));
        const matchesTag = !tag || (g.tags && g.tags.includes(tag));

        let matchesStatus = true;
        if (showOnlyBase) matchesStatus = matchesStatus && !g.has_base;
        if (showOnlyUpdates) matchesStatus = matchesStatus && (g.has_base && g.has_non_ignored_updates);
        if (showOnlyDlcs) matchesStatus = matchesStatus && (g.has_base && g.has_non_ignored_dlcs);

        return matchesSearch && matchesGender && matchesTag && matchesStatus;
    });

    window.filteredGames.sort((a, b) => {
        const [field, order] = currentSort.split('-');
        let comparison = 0;

        if (field === 'name') {
            comparison = (a.name || '').localeCompare(b.name || '');
        } else if (field === 'release') {
            const dateA = String(a.release_date || a.latest_release_date || '0000-00-00');
            const dateB = String(b.release_date || b.latest_release_date || '0000-00-00');
            comparison = dateA.localeCompare(dateB);
        } else if (field === 'added') {
            const dateA = a.added_at ? new Date(a.added_at).getTime() : 0;
            const dateB = b.added_at ? new Date(b.added_at).getTime() : 0;
            comparison = dateA - dateB;
        } else if (field === 'id') {
            comparison = (a.id || '').localeCompare(b.id || '');
        } else if (field === 'status') {
            comparison = (a.status_score || 0) - (b.status_score || 0);
        } else if (field === 'size') {
            comparison = (a.size || 0) - (b.size || 0);
        }

        return order === 'asc' ? comparison : -comparison;
    });

    const hasActiveFilters = query || gender || tag || showOnlyBase || showOnlyUpdates || showOnlyDlcs;
    $('#clearFiltersBtn').toggleClass('has-active', !!hasActiveFilters);

    $('#totalItemsCount, #totalItemsCountMobile').text(`${window.filteredGames.length} ${t('Jogos')}`);
    renderLibrary();
}

function clearFilters() {
    $('#navbarSearch').val('');
    $('#filterGender').val('');
    $('#filterTag').val('');
    $('#btnFilterPendingBase, #btnFilterPendingUpd, #btnFilterPendingDlc').removeClass('is-primary').addClass('is-light');
    $('#searchClearBtn').hide();
    $('#searchIcon').show();

    currentSort = 'name-asc';
    localStorage.setItem('myfoil_library_sort', currentSort);
    $('.sort-option').removeClass('is-active has-text-weight-bold');
    $(`.sort-option[data-sort="${currentSort}"]`).addClass('is-active has-text-weight-bold');

    applyFilters();
}

function clearSearch() {
    $('#navbarSearch').val('');
    $('#searchClearBtn').hide();
    $('#searchIcon').show();
    applyFilters();
}

// ========== INFINITE SCROLL ==========
let scrollOffset = 0;
let isLoadingMore = false;
let hasMoreItems = true;
const SCROLL_BATCH_SIZE = 48;

function setupInfiniteScroll() {
    const sentinel = document.getElementById('scrollSentinel');
    if (!sentinel) return;

    const observer = new IntersectionObserver((entries) => {
        const entry = entries[0];
        if (entry.isIntersecting && !isLoadingMore && hasMoreItems && window.filteredGames.length > scrollOffset) {
            loadMoreItems();
        }
    }, {
        rootMargin: '200px'
    });

    observer.observe(sentinel);
}

function loadMoreItems() {
    if (isLoadingMore) return;
    isLoadingMore = true;

    const currentBatch = window.filteredGames.slice(scrollOffset, scrollOffset + SCROLL_BATCH_SIZE);

    if (currentBatch.length === 0) {
        hasMoreItems = false;
        isLoadingMore = false;
        return;
    }

    if (currentView === 'card') renderCardView(currentBatch);
    else if (currentView === 'icon') renderIconView(currentBatch);
    else renderListView(currentBatch);

    setupKeyboardNavigation();

    scrollOffset += currentBatch.length;
    hasMoreItems = scrollOffset < window.filteredGames.length;
    isLoadingMore = false;

    const sentinel = document.getElementById('scrollSentinel');
    if (sentinel) sentinel.style.display = hasMoreItems ? 'block' : 'none';
}

function resetInfiniteScroll() {
    scrollOffset = 0;
    hasMoreItems = true;
    isLoadingMore = false;
    $('#libraryContainer').empty();
    $('#scrollSentinel').remove();
    $('#libraryContainer').after('<div id="scrollSentinel" style="height: 20px; width: 100%;"></div>');
    loadMoreItems();
}

// ========== KEYBOARD NAVIGATION ==========
let currentlyFocusedIndex = -1;

function setupKeyboardNavigation() {
    const container = document.getElementById('libraryContainer');
    if (!container) return;

    container.removeEventListener('keydown', handleKeyDown);
    container.removeEventListener('focus', handleFocus, true);
    container.addEventListener('keydown', handleKeyDown);
    container.addEventListener('focus', handleFocus, true);
}

function handleKeyDown(e) {
    const target = e.target.closest('[data-game-id]');
    if (!target) return;

    const currentGameId = target.dataset.gameId;
    let currentIndex = window.filteredGames.findIndex(g => g && g.id === currentGameId);

    if (currentIndex === -1) {
        const items = Array.from(document.querySelectorAll('#libraryContainer .grid-item, tbody tr'));
        currentIndex = items.indexOf(target);
        if (currentIndex === -1) return;
    }

    const totalItems = window.filteredGames.length;
    if (totalItems === 0) return;

    const container = document.getElementById('libraryContainer');
    let columns = 1;
    if (currentView === 'card' || currentView === 'icon') {
        const gridStyle = window.getComputedStyle(container);
        columns = gridStyle.gridTemplateColumns.split(' ').length || 1;
    }

    let nextIndex = currentIndex;

    switch (e.key) {
        case 'ArrowRight': e.preventDefault(); nextIndex = Math.min(currentIndex + 1, totalItems - 1); break;
        case 'ArrowLeft': e.preventDefault(); nextIndex = Math.max(currentIndex - 1, 0); break;
        case 'ArrowDown': e.preventDefault(); nextIndex = Math.min(currentIndex + columns, totalItems - 1); break;
        case 'ArrowUp': e.preventDefault(); nextIndex = Math.max(currentIndex - columns, 0); break;
        case 'Home': e.preventDefault(); nextIndex = 0; break;
        case 'End': e.preventDefault(); nextIndex = totalItems - 1; break;
        case 'Enter':
        case ' ':
            e.preventDefault();
            if (currentGameId) showGameDetails(currentGameId);
            return;
        default: return;
    }

    if (nextIndex !== currentIndex) {
        const nextGame = window.filteredGames[nextIndex];
        if (nextGame) {
            const nextElement = container.querySelector(`[data-game-id="${nextGame.id}"]`);
            if (nextElement) {
                nextElement.focus();
                currentlyFocusedIndex = nextIndex;
                nextElement.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            }
        }
    }
}

function handleFocus(e) {
    const target = e.target.closest('[data-game-id]');
    if (!target) return;
    const index = window.filteredGames.findIndex(g => g && g.id === target.dataset.gameId);
    if (index !== -1) currentlyFocusedIndex = index;
}

function toggleSearchClearBtn() {
    const searchValue = $('#navbarSearch').val();
    if (searchValue.length > 0) {
        $('#searchClearBtn').show();
        $('#searchIcon').hide();
    } else {
        $('#searchClearBtn').hide();
        $('#searchIcon').show();
    }
}

function focusAndOpenGame(gameId) {
    const gridItem = document.querySelector(`[data-game-id="${gameId}"]`);
    if (gridItem) gridItem.focus();
    showGameDetails(gameId);
}

// Event Listeners Initialization
$(document).ready(() => {
    // Initial State
    games = [];
    window.filteredGames = [];

    // Filter Buttons
    $('#btnFilterPendingBase').on('click', function () {
        $(this).toggleClass('is-primary is-light');
        if ($(this).hasClass('is-primary')) $('#btnFilterPendingUpd, #btnFilterPendingDlc').removeClass('is-primary').addClass('is-light');
        applyFilters();
    });

    $('#btnFilterPendingUpd').on('click', function () {
        $(this).toggleClass('is-primary is-light');
        if ($(this).hasClass('is-primary')) $('#btnFilterPendingBase, #btnFilterPendingDlc').removeClass('is-primary').addClass('is-light');
        applyFilters();
    });

    $('#btnFilterPendingDlc').on('click', function () {
        $(this).toggleClass('is-primary is-light');
        if ($(this).hasClass('is-primary')) $('#btnFilterPendingBase, #btnFilterPendingUpd').removeClass('is-primary').addClass('is-light');
        applyFilters();
    });

    $('.filterInput').on('change', applyFilters);
    $('#navbarSearch').on('input', _debounce(() => {
        applyFilters();
        toggleSearchClearBtn();
    }, 300));

    $('#sortDropdown .dropdown-trigger button').on('click', function (e) {
        e.stopPropagation();
        $('#sortDropdown').toggleClass('is-active');
        $('#filterDropdown').removeClass('is-active');
    });

    $('#filterDropdown .dropdown-trigger button').on('click', function (e) {
        e.stopPropagation();
        $('#filterDropdown').toggleClass('is-active');
        $('#sortDropdown').removeClass('is-active');
    });

    $(document).on('click', () => {
        $('#filterDropdown, #sortDropdown').removeClass('is-active');
    });

    $('.dropdown-content').on('click', (e) => e.stopPropagation());

    $('.sort-option').on('click', function () {
        currentSort = $(this).data('sort');
        localStorage.setItem('myfoil_library_sort', currentSort);
        $('.sort-option').removeClass('is-active has-text-weight-bold');
        $(this).addClass('is-active has-text-weight-bold');
        $('#sortDropdown').removeClass('is-active');
        applyFilters();
    });

    // Initial Load
    loadIgnorePreferences().then(() => {
        refreshLibrary();
    });

    // Grid Zoom Listener
    $('#gridZoom').on('input', function () {
        if (typeof updateGridZoom === 'function') {
            updateGridZoom($(this).val());
        }
    });

    const savedZoom = localStorage.getItem('gridZoom') || 240;
    $('#gridZoom').val(savedZoom);
    if (typeof updateGridZoom === 'function') {
        updateGridZoom(savedZoom);
    }

    $(`.sort-option[data-sort="${currentSort}"]`).addClass('is-active has-text-weight-bold');
    setView(currentView);
});
