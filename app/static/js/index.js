/**
 * MyFoil Library Index Logic
 * Handles library loading, filtering, sorting, and infinite scroll.
 * Phase 2.2: Server-side pagination for improved performance.
 * Phase 3.3: UX Improvements with visible loading indicators.
 */

let games = [];
window.filteredGames = [];
let currentSort = localStorage.getItem('myfoil_library_sort') || 'name-asc';
let currentView = localStorage.getItem('viewMode') || 'card';
let ignorePreferences = {};  // Cache for ignore preferences per title_id
let allGamesLoaded = false;  // Track if all games have been loaded
let currentPage = 1;  // Current page for pagination
let isLoadingMore = false;  // Track loading state
let totalItems = 0;  // Total number of games in library
let isNewRender = true;  // Track if we need a full re-render
let scrollOffset = 0;  // Track which filtered items have been rendered
let hasMoreItems = true;  // Track if there are more items to render
let isServerSideFiltered = false; // Track if current games list is a filtered subset
const PER_PAGE = 75;  // Items per page (optimized for performance - 75 is sweet spot)
const SCROLL_BATCH_SIZE = 30;  // Render 30 items at a time for smoothness

// Ensure we prefer the server-side paged endpoint by default.
// Clear any legacy fallback toggles that may be stored in localStorage
// (this prevents old clients or cached state from forcing the legacy endpoint).
try {
    localStorage.removeItem('myfoil_use_legacy_endpoint');
} catch (e) {
    // localStorage may be disabled in some privacy contexts; fail silently
    console.warn('Failed to clear myfoil_use_legacy_endpoint from localStorage', e);
}

// Fetch all ignore preferences on load
function loadAllIgnorePreferences() {
    return $.getJSON('/api/wishlist/ignore', (res) => {
        const data = (res && res.data) ? res.data : res;
        ignorePreferences = data || {};
        debugLog('Ignore preferences loaded:', ignorePreferences);
    }).fail(() => {
        debugWarn('Failed to load ignore preferences');
        showToast(t('Failed to load ignore preferences'), 'danger');
        ignorePreferences = {};
    });
}

function loadLibraryPaginated(page = 1, append = false) {
    // Try paged endpoint first, fall back to legacy endpoint if it fails
    let API_ENDPOINT = '/api/library/paged';
    let useLegacyFallback = false;

    // Check if we've already tried and failed with paged endpoint
    if (localStorage.getItem('myfoil_use_legacy_endpoint') === 'true') {
        API_ENDPOINT = '/api/library';
        useLegacyFallback = true;
    }

    // If page 1 and not appending, clear games
    if (page === 1 && !append) {
        games = [];
        filteredGames = [];
        allGamesLoaded = false;
        currentPage = 1;
        scrollOffset = 0;
        isLoadingMore = false;
        totalItems = 0;
    }

    // Skip if already loading
    if (isLoadingMore && append) {
        return;
    }

    isLoadingMore = true;

    // Show appropriate loading indicator
    if (append) {
        // Show pagination loader at bottom
        $('#paginationLoader').removeClass('is-hidden');
    } else {
        // Show main loader with progress
        $('#loadingIndicator').removeClass('is-hidden');
        $('#loadingProgress').val(0);
        $('#loadingProgress').attr('max', 100);

        // Update loading text based on page
        let loadingText = page === 1
            ? t('Carregando Biblioteca...')
            : t('Carregando página') + ` ${page}...`;
        $('#loadingText').text(loadingText);
    }

    // Build URL parameters
    let url = `${API_ENDPOINT}?page=${page}&per_page=${PER_PAGE}`;

    // Parse sort preference (for paged endpoint)
    let sort_by = 'name';
    let order = 'asc';
    if (currentSort && currentSort.includes('-')) {
        const parts = currentSort.split('-');
        sort_by = parts[0];
        order = parts[1];
    }

    // Add pagination/sort parameters
    if (!useLegacyFallback) {
        url += `&sort_by=${sort_by}&order=${order}`;
    }

    // Update progress bar to 50% (loading started)
    $('#loadingProgress').val(50);

    $.getJSON(url, function (data) {
        // Update progress bar to 80% (data received)
        $('#loadingProgress').val(80);

        isServerSideFiltered = false;

        // Normalize response: support both envelope { code, data: { items } } and direct responses
        const payload = (data && data.data) ? data.data : data;

        // Check response format
        let newGames = [];

        if (useLegacyFallback) {
            newGames = (payload && payload.items) ? payload.items : (Array.isArray(payload) ? payload : []);
        } else {
            if (payload && payload.items && Array.isArray(payload.items)) {
                newGames = payload.items;
            } else if (Array.isArray(payload)) {
                newGames = payload;
            }
        }

        if (append) {
            games = [...games, ...newGames];
        } else {
            games = newGames;
        }

        // Initialize filter dropdowns (genres/tags) based on loaded games
        try {
            initGenders(games);
            initTags(games);
        } catch (e) {
            console.warn('Failed to init genders/tags from loaded games', e);
        }

        // Update total count from server
        const paginationSource = (payload && payload.pagination) ? payload.pagination : (data && data.pagination ? data.pagination : null);
        if (paginationSource) {
            totalItems = paginationSource.total_items || paginationSource.total || 0;
            // Support both has_next and hasMore naming
            allGamesLoaded = paginationSource.has_next !== undefined ? !paginationSource.has_next : !paginationSource.has_more;
            currentPage = paginationSource.page || page;

            // Update progress calculation
            if (totalItems > 0) {
                const loadedCount = games.length;
                const progress = Math.min(100, Math.round((loadedCount / totalItems) * 100));
                $('#loadingProgress').val(100);
            }
        } else if (Array.isArray(payload)) {
            totalItems = payload.length;
            allGamesLoaded = true;
            $('#loadingProgress').val(100);
        }

        // Apply filters after data is loaded
        applyFilters();

        // Hide loading indicators
        $('#loadingIndicator').addClass('is-hidden');
        $('#paginationLoader').addClass('is-hidden');
        isLoadingMore = false;

        if (!append) {
            const loadedPercent = totalItems > 0
                ? `${Math.round((Math.min(PER_PAGE, totalItems) / totalItems) * 100)}%`
                : '100%';
            showToast(t('Library updated!') + ` (${loadedPercent})`, 'success');
        }

        // Setup infinite scroll observer
        setupInfiniteScroll();

    }).fail((jqXHR, textStatus, errorThrown) => {
        $('#loadingIndicator').addClass('is-hidden');
        $('#paginationLoader').addClass('is-hidden');
        isLoadingMore = false;

        console.error('Failed to load library:', textStatus, errorThrown);
        console.error('Response:', jqXHR.responseText);

        // If this was the first attempt with paged endpoint, try legacy fallback
        if (!useLegacyFallback && page === 1 && !append) {
            console.log('Paged endpoint failed, falling back to legacy endpoint...');
            localStorage.setItem('myfoil_use_legacy_endpoint', 'true');
            $('#loadingText').text(t('Mudando para endpoint legado...'));
            $('#loadingIndicator').removeClass('is-hidden');

            setTimeout(() => {
                loadLibraryPaginated(page, false);
            }, 500);
        } else {
            $('#loadingProgress').removeClass('is-primary').addClass('is-danger');
            showToast(t('Failed to refresh library: ') + (errorThrown || textStatus), 'error');
        }
    });
}


// Lazy Loading Images - Phase 3.3 Improved with aggressive thresholds
function observeImages() {
    if ('IntersectionObserver' in window) {
        // Use more aggressive threshold for better performance
        // Load images when they're 400px below viewport instead of waiting for intersection
        const imageObserver = new IntersectionObserver((entries, observer) => {
            entries.forEach(entry => {
                if (entry.isIntersecting) {
                    const img = entry.target;
                    const src = img.getAttribute('data-src');
                    if (src) {
                        // Add smooth fade-in effect
                        img.style.transition = 'opacity 0.3s ease-in-out';
                        img.style.opacity = '0.3';

                        img.src = src;
                        img.onload = () => {
                            img.style.opacity = '1';
                        };
                        img.onerror = () => {
                            // Fallback to no-icon if image fails to load
                            img.src = '/static/img/no-icon.png';
                            img.style.opacity = '1';
                        };
                        img.removeAttribute('data-src');
                    }
                    observer.unobserve(img);
                }
            });
        }, {
            // Load images earlier for smoother UX (400px before they enter viewport)
            rootMargin: '400px 0px 400px 0px',
            threshold: 0.01  // Trigger when 1% of image is visible
        });

        document.querySelectorAll('img.lazy-image').forEach(img => {
            imageObserver.observe(img);
        });
    } else {
        // Fallback for older browsers - still load images but without lazy loading
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
    const viewBtnId = `#btnView${(view && view.charAt ? view.charAt(0).toUpperCase() + view.slice(1) : '')}`;
    if ($(viewBtnId).length) $(viewBtnId).addClass('is-primary');
    renderLibrary();
}

// Grid zoom logic moved to base.js for global availability

function renderLibrary() {
    const container = $('#libraryContainer');

    // Only re-render if we're on a new filter or view change
    // Don't re-render on infinite scroll append (that's handled separately)
    if (!isNewRender && scrollOffset > 0) {
        return;
    }

    isNewRender = false;

    // Clear container
    container.empty();

    // Handle list view width
    if (currentView === 'list') {
        container.addClass('is-list-view');
    } else {
        container.removeClass('is-list-view');
    }

    // Use infinite scroll to render filtered games
    // Note: We're using client-side infinite scroll on filteredGames
    // for flexibility with various filter combinations
    resetInfiniteScroll();
}

function refreshLibrary() {
    console.log("Refreshing library data...");

    // Check for build version change to clear cache
    const currentBuild = window.BUILD_VERSION || '';
    const lastBuild = localStorage.getItem('myfoil_last_version');
    if (lastBuild && lastBuild !== currentBuild) {
        console.log("Build version changed, clearing local cache...");
        localStorage.removeItem('myfoil_library_cache');
    }
    localStorage.setItem('myfoil_last_version', currentBuild);

    // Use paginated loading from Phase 2.2
    loadLibraryPaginated(1, false);
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
                        <figure class="image is-16by9 bg-light-soft" style="position: relative;">
                            <img src="/static/img/no-icon.png" 
                                 data-src="${game.bannerUrl || game.iconUrl || '/static/img/no-icon.png'}" 
                                 alt="${safeName}" 
                                 loading="lazy"
                                 class="lazy-image"
                                 style="object-fit: cover; opacity: 0; transition: opacity 0.3s;">
                        </figure>
                    </div>
                    <div class="card-content">
                        <div class="is-flex is-justify-content-between is-align-items-center mb-1" style="width: 100%;">
                            <span class="font-mono is-size-7 opacity-40">${safeId}</span>
                            <span class="font-mono is-size-7 has-text-weight-bold ml-auto">v${game.display_version}</span>
                        </div>
                        
                         <h3 class="game-title title is-6 has-text-weight-bold mb-3 line-clamp-2" title="${safeName}">${safeName}</h3>
                         
                        <div class="is-flex is-justify-content-between is-align-items-center mt-auto pt-2" style="width: 100%;">
                            <div class="is-flex is-align-items-center">
                                <span class="status-dot ${statusDotClass}"></span>
                                <span class="is-size-7 opacity-70 font-mono">&nbsp; ${game.size_formatted || '--'}</span>
                            </div>
                            <div class="is-flex gap-1 is-justify-content-end ml-auto">
                                ${game.has_non_ignored_redundant ? `<span class="tag tag-redundant has-text-weight-bold is-small">${t('REDUNDANT')}</span>` : ''}
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
// Socket listener for library updates
if (typeof window.socket !== 'undefined' || (typeof socket !== 'undefined') || (window.statusManager && window.statusManager.socket)) {
    const s = window.socket || socket || window.statusManager.socket;
    if (s) {
        s.on('library_updated', () => {
            console.log('🔄 Library update event received from socket');
            refreshLibrary();
        });
    }
}

function renderIconView(items) {
    items.forEach((game, index) => {
        const statusDotClass = game.status_color === 'orange' ? 'bg-orange' : (game.status_color === 'green' ? 'bg-green' : 'bg-gray');
        const safeName = escapeHtml(game.name);
        const safeId = escapeHtml(game.id);

        const metacriticScore = game.metacritic_score;
        let ratingBadge = '';
        if (metacriticScore) {
            const scoreClass = metacriticScore >= 75 ? 'high-score' : (metacriticScore >= 50 ? 'mid-score' : 'low-score');
            ratingBadge = `<div class="rating-badge ${scoreClass}" style="top: 0.5rem; right: 0.5rem; padding: 1px 6px; font-size: 0.65rem;" title="Metacritic: ${metacriticScore}">
                <i class="bi bi-star-fill"></i>
                <span>${metacriticScore}</span>
            </div>`;
        }

        const card = $(`
            <div class="grid-item" data-index="${index}" data-game-id="${safeId}" tabindex="0" role="button" aria-label="${safeName}" onclick="focusAndOpenGame('${safeId}')" title="${safeName}">
                <div class="card game-card is-paddingless is-shadowless">
                    <div class="card-image">
                         <figure class="image is-square bg-light relative">
                            ${ratingBadge}
                              ${game.metacritic_score ? `<div class="metacritic-badge" title="Metacritic: ${game.metacritic_score}">${game.metacritic_score}</div>` : ''}
                            <img src="/static/img/no-icon.png" 
                                 data-src="${game.iconUrl || '/static/img/no-icon.png'}" 
                                 alt="${safeName}" 
                                 loading="lazy"
                                 class="lazy-image p-0" 
                                 style="object-fit: cover; width: 100%; height: 100%; opacity: 0; transition: opacity 0.3s;">
                             <div class="status-indicator position-absolute">
                                ${game.has_non_ignored_redundant ? `<span class="tag tag-redundant is-tiny" style="position: absolute; top: -35px; right: -5px; font-size: 0.5rem; padding: 0 4px; border-radius: 4px;">${t('R')}</span>` : ''}
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
                    ${game.has_non_ignored_redundant ? `<span class="tag tag-redundant ml-2 has-text-weight-bold">${t('REDUNDANT')}</span>` : ''}
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
    const query = ($('#navbarSearch').val() || '').trim();
    const gender = $('#filterGender').val();
    const tag = $('#filterTag').val();

    const showOnlyBase = $('#btnFilterPendingBase').hasClass('is-primary');
    const showOnlyUpdates = $('#btnFilterPendingUpd').hasClass('is-primary');
    const showOnlyDlcs = $('#btnFilterPendingDlc').hasClass('is-primary');
    const showOnlyRedundant = $('#btnFilterRedundant').hasClass('is-primary');

    // Mark for full re-render
    isNewRender = true;

    const hasActiveFilters = !!(query || gender || tag || showOnlyBase || showOnlyUpdates || showOnlyDlcs || showOnlyRedundant);
    $('#clearFiltersBtn').toggleClass('has-active', !!hasActiveFilters);

    // If the user has active filters or a search query, use the server-side SEARCH (full results)
    // The paged endpoint doesn't support negative filters like 'pending', so use /api/library/search
    if (hasActiveFilters) {
        searchLibraryServer(1, false);
        return;
    }

    // If we were previously in a filtered state (server-side search), we need to reload the full library
    if (isServerSideFiltered) {
        loadLibraryPaginated(1, false);
        return;
    }

    // No active filters: fall back to client-side filtering on already-loaded pages
    // Compute status flags based on ignore preferences
    games.forEach(g => {
        if (!g) return;
        const titleId = (g.id || '').toUpperCase();
        const gameIgnore = ignorePreferences[titleId] || {};
        const ignoredDlcs = gameIgnore.dlcs || {};

        let hasNonIgnoredUpdates = false;
        if (g.has_base && !g.has_latest_version) {
            if (g.updates && Array.isArray(g.updates)) {
                const ownedVersion = parseInt(g.owned_version) || 0;
                hasNonIgnoredUpdates = g.updates.some(u => {
                    const v = parseInt(u.version);
                    return v > ownedVersion && !u.owned;
                });
            } else {
                hasNonIgnoredUpdates = !!g.has_non_ignored_updates;
            }
        }
        g.has_non_ignored_updates = hasNonIgnoredUpdates;

        if (g.has_base) {
            if (g.dlcs && Array.isArray(g.dlcs)) {
                hasNonIgnoredDlcs = g.dlcs.some(dlc => {
                    const appIdKey = typeof dlc.app_id === 'string' ? dlc.app_id : (dlc.appId || '');
                    const isIgnored = appIdKey ? (
                        ignoredDlcs[appIdKey] ||
                        ignoredDlcs[appIdKey.toUpperCase()] ||
                        ignoredDlcs[appIdKey.toLowerCase()]
                    ) : false;
                    const isNotOwned = !dlc.owned;

                    return isNotOwned && !isIgnored;
                });
            } else {
                // Fallback to backend-computed value if dlcs array is not available
                hasNonIgnoredDlcs = !!g.has_non_ignored_dlcs;
            }
        }
        g.has_non_ignored_dlcs = hasNonIgnoredDlcs;

        let hasNonIgnoredRedundant = false;
        if (g.has_redundant_updates) {
            if (g.updates && Array.isArray(g.updates)) {
                const ownedUpdates = g.updates.filter(u => u.owned).sort((a, b) => (parseInt(b.version) || 0) - (parseInt(a.version) || 0));
                if (ownedUpdates.length > 1) {
                    hasNonIgnoredRedundant = true;
                }
            } else {
                hasNonIgnoredRedundant = !!g.has_non_ignored_redundant;
            }
        }
        g.has_non_ignored_redundant = hasNonIgnoredRedundant;



        // Determine status color for UI
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

    window.filteredGames = games.slice();

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

    // Update item count - show filtered count vs total loaded
    const loadedCount = totalItems || games.length;
    const filteredCount = window.filteredGames.length;
    const countText = `${loadedCount}`;
    $('#totalItemsCount, #totalItemsCountMobile').text(`${countText} ${t('Jogos')}`);

    // Show/hide empty state
    if (window.filteredGames.length === 0) {
        $('#noResults').removeClass('is-hidden');
        $('#libraryContainer').addClass('is-hidden');
    } else {
        $('#noResults').addClass('is-hidden');
        $('#libraryContainer').removeClass('is-hidden');
    }

    renderLibrary();
}

function clearFilters() {
    $('#navbarSearch').val('');
    $('#filterGender').val('');
    $('#filterTag').val('');
    $('#btnFilterPendingBase, #btnFilterPendingUpd, #btnFilterPendingDlc, #btnFilterRedundant').removeClass('is-primary').addClass('is-light');
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

// Server-side search helper to query the entire library (paged) when filters/search are active
function searchLibraryServer(page = 1, append = false) {
    const query = ($('#navbarSearch').val() || '').trim();
    const genre = $('#filterGender').val();
    const tag = $('#filterTag').val();
    const showOnlyBase = $('#btnFilterPendingBase').hasClass('is-primary');
    const showOnlyUpdates = $('#btnFilterPendingUpd').hasClass('is-primary');
    const showOnlyDlcs = $('#btnFilterPendingDlc').hasClass('is-primary');
    const showOnlyRedundant = $('#btnFilterRedundant').hasClass('is-primary');

    // Build params for server-side paged search. Use /api/library/search/paged which supports q, genre, owned, up_to_date
    let url = `/api/library/search/paged?page=${page}&per_page=${PER_PAGE}`;
    if (query) url += `&q=${encodeURIComponent(query)}`;
    if (genre) url += `&genre=${encodeURIComponent(genre)}`;
    if (tag) url += `&tag=${encodeURIComponent(tag)}`;
    // Map some UI flags to server params where possible
    // showOnlyBase means "missing base" in UI, map to missing=true
    if (showOnlyBase) url += `&missing=true`;
    // showOnlyUpdates -> pending (owned && not up_to_date)
    if (showOnlyUpdates) url += `&pending=true`;
    // owned_only mapping: if user explicitly selects owned-only behavior, send owned=true
    if (!showOnlyBase && !showOnlyUpdates && showOnlyDlcs === false) {
        // no-op; keep default
    }

    if (showOnlyDlcs) url += `&dlc=true`;
    if (showOnlyRedundant) url += `&redundant=true`;

    // Show loading UI
    if (page === 1 && !append) {
        $('#loadingIndicator').removeClass('is-hidden');
        $('#loadingProgress').val(50);
    } else {
        $('#paginationLoader').removeClass('is-hidden');
    }

    $.getJSON(url, function (res) {
        const payload = (res && res.data) ? res.data : res;
        const items = (payload && payload.items && Array.isArray(payload.items)) ? payload.items : (payload.items || []);

        isServerSideFiltered = true;

        if (append) {
            games = [...games, ...items];
        } else {
            games = items;
        }

        // Update pagination / total
        const pagination = payload && payload.pagination ? payload.pagination : (res && res.pagination ? res.pagination : null);
        if (pagination) {
            totalItems = pagination.total_items || pagination.total || games.length;
            allGamesLoaded = pagination.has_next !== undefined ? !pagination.has_next : !pagination.has_more;
            currentPage = pagination.page || page;
        } else {
            totalItems = games.length;
            allGamesLoaded = true;
        }

        // For status/dlc/update tags we still need to compute client-side using ignorePreferences
        games.forEach(g => {
            const gameIgnore = ignorePreferences[g.id] || {};
            const ignoredDlcs = gameIgnore.dlcs || {};
            const ignoredUpdates = gameIgnore.updates || {};

            let hasNonIgnoredUpdates = false;
            if (g.has_base && g.updates && Array.isArray(g.updates)) {
                const ownedVersion = parseInt(g.owned_version) || 0;
                hasNonIgnoredUpdates = g.updates.some(u => {
                    const v = parseInt(u.version);
                    return v > ownedVersion && !u.owned && !ignoredUpdates[v.toString()];
                });
            }
            g.has_non_ignored_updates = hasNonIgnoredUpdates;

            let hasNonIgnoredDlcs = false;
            if (g.has_base && g.dlcs && Array.isArray(g.dlcs)) {
                hasNonIgnoredDlcs = g.dlcs.some(dlc => {
                    const appIdKey = typeof dlc.app_id === 'string' ? dlc.app_id : (dlc.appId || '');
                    const isIgnored = appIdKey ? (ignoredDlcs[appIdKey.toUpperCase()] || ignoredDlcs[appIdKey.toLowerCase()]) : false;
                    const isNotOwned = !dlc.owned;
                    return isNotOwned && !isIgnored;
                });
            }
            g.has_non_ignored_dlcs = hasNonIgnoredDlcs;

            let hasNonIgnoredRedundant = false;
            if (g.has_redundant_updates && g.updates && Array.isArray(g.updates)) {
                const ownedUpdates = g.updates.filter(u => u.owned).sort((a, b) => (parseInt(b.version) || 0) - (parseInt(a.version) || 0));
                if (ownedUpdates.length > 1) {
                    hasNonIgnoredRedundant = ownedUpdates.slice(1).some(u => {
                        const v = (u.version || 0).toString();
                        return !ignoredUpdates[v];
                    });
                }
            }
            g.has_non_ignored_redundant = hasNonIgnoredRedundant;

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

        // Filter out games where all missing DLCs are ignored (when DLC filter is active)
        if (showOnlyDlcs) {
            games = games.filter(g => g.has_non_ignored_dlcs);
            totalItems = games.length;
        }

        // Use server results as filteredGames
        window.filteredGames = games.slice();

        // Update UI counts
        $('#totalItemsCount, #totalItemsCountMobile').text(`${totalItems} ${t('Jogos')}`);

        // Render results
        resetInfiniteScroll();

        $('#loadingIndicator').addClass('is-hidden');
        $('#paginationLoader').addClass('is-hidden');
    }).fail((jqXHR, textStatus, err) => {
        console.error('Server search failed:', textStatus, err, jqXHR.responseText);
        $('#loadingIndicator').addClass('is-hidden');
        $('#paginationLoader').addClass('is-hidden');
    });
}

// ========== INFINITE SCROLL ==========

function setupInfiniteScroll() {
    const sentinel = document.getElementById('scrollSentinel');
    if (!sentinel) return;

    const observer = new IntersectionObserver((entries) => {
        const entry = entries[0];
        // Load more when user scrolls near bottom
        // Load from server if we haven't loaded everything yet
        if (entry.isIntersecting && !allGamesLoaded && !isLoadingMore) {
            loadLibraryPaginated(currentPage + 1, true);
        }
        // Also render more of the already loaded but filtered items
        renderMoreFilteredItems();
    }, {
        rootMargin: '200px'
    });

    observer.observe(sentinel);
}

function renderMoreFilteredItems() {
    // Get next batch of filtered games that haven't been rendered yet
    const filtered = window.filteredGames;
    const renderedCount = document.querySelectorAll('.grid-item').length;

    // Skip if we've already rendered all filtered games
    if (renderedCount >= filtered.length) {
        $('#paginationLoader').addClass('is-hidden');
        return;
    }

    // Show pagination loader
    $('#paginationLoader').removeClass('is-hidden');

    // Get next batch
    const startIdx = renderedCount;
    const endIdx = Math.min(startIdx + SCROLL_BATCH_SIZE, filtered.length);  // Render 30 at a time
    const batch = filtered.slice(startIdx, endIdx);

    if (batch.length === 0) {
        $('#paginationLoader').addClass('is-hidden');
        return;
    }

    // Render the batch
    if (currentView === 'card') renderCardView(batch);
    else if (currentView === 'icon') renderIconView(batch);
    else renderListView(batch);

    setupKeyboardNavigation();
    observeImages();

    // Hide loader after a brief delay
    setTimeout(() => {
        $('#paginationLoader').addClass('is-hidden');
    }, 300);
}

function loadMoreItems() {
    // Initial render - show first batch
    const filtered = window.filteredGames;
    if (filtered.length === 0) {
        $('#loadingIndicator').addClass('is-hidden');
        $('#scrollSentinel').hide();
        return;
    }

    // Render first batch
    const firstBatch = filtered.slice(0, SCROLL_BATCH_SIZE);
    if (currentView === 'card') renderCardView(firstBatch);
    else if (currentView === 'icon') renderIconView(firstBatch);
    else renderListView(firstBatch);

    setupKeyboardNavigation();
    observeImages();
    $('#loadingIndicator').addClass('is-hidden');

    // Show sentinel for lazy loading if there are more items
    hasMoreItems = filtered.length > firstBatch.length;
    $('#scrollSentinel').toggle(hasMoreItems);
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
        if ($(this).hasClass('is-primary')) {
            // DESATIVAR OUTROS FILTROS quando Pending Base for ativado
            $('#btnFilterPendingUpd, #btnFilterPendingDlc, #btnFilterRedundant')
                .removeClass('is-primary').addClass('is-light');
        }
        applyFilters();
    });

    $('#btnFilterPendingUpd').on('click', function () {
        $(this).toggleClass('is-primary is-light');
        if ($(this).hasClass('is-primary')) {
            // DESATIVAR OUTROS FILTROS quando Pending Updates for ativado
            $('#btnFilterPendingBase, #btnFilterPendingDlc, #btnFilterRedundant')
                .removeClass('is-primary').addClass('is-light');
        }
        applyFilters();
    });

    $('#btnFilterPendingDlc').on('click', function () {
        $(this).toggleClass('is-primary is-light');
        if ($(this).hasClass('is-primary')) {
            // DESATIVAR OUTROS FILTROS quando Pending DLC for ativado
            $('#btnFilterPendingBase, #btnFilterPendingUpd, #btnFilterRedundant')
                .removeClass('is-primary').addClass('is-light');
        }
        applyFilters();
    });

    $('#btnFilterRedundant').on('click', function () {
        $(this).toggleClass('is-primary is-light');
        if ($(this).hasClass('is-primary')) {
            // DESATIVAR OUTROS FILTROS quando Redundante for ativado
            $('#btnFilterPendingBase, #btnFilterPendingUpd, #btnFilterPendingDlc')
                .removeClass('is-primary').addClass('is-light');
        }
        applyFilters();
    });

    $('#clearFiltersBtn').on('click', function () {
        clearFilters();
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
    loadAllIgnorePreferences().then(() => {
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
