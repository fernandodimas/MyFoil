/**
 * Upcoming Games Logic - Mimics Dashboard behavior
 */

let allGames = [];
let filteredGames = [];
let currentView = localStorage.getItem('upcomingViewMode') || 'card';

document.addEventListener('DOMContentLoaded', () => {
    initControls();
    loadUpcomingGames();
});

function initControls() {
    // Search control
    const searchInput = document.getElementById('upcomingSearch');
    if (searchInput) {
        searchInput.addEventListener('input', debounce(() => {
            applyFilters();
        }, 300));
    }

    // Grid Zoom Listener
    const gridZoom = document.getElementById('gridZoom');
    if (gridZoom) {
        gridZoom.addEventListener('input', function () {
            if (typeof updateGridZoom === 'function') {
                updateGridZoom(this.value);
            }
        });

        // Load saved zoom
        const savedZoom = localStorage.getItem('gridZoom') || 240;
        gridZoom.value = savedZoom;
        if (typeof updateGridZoom === 'function') {
            updateGridZoom(savedZoom);
        }
    }

    // Set initial view button state
    updateViewButtons();
}

function updateViewButtons() {
    const buttons = document.querySelectorAll('#viewToggleButtons .button');
    buttons.forEach(btn => btn.classList.remove('is-primary'));

    const viewName = (currentView && currentView.charAt) ? currentView.charAt(0).toUpperCase() + currentView.slice(1) : '';
    const activeBtn = document.getElementById(`btnView${viewName}`);
    if (activeBtn) activeBtn.classList.add('is-primary');
}

function setView(view) {
    currentView = view;
    localStorage.setItem('upcomingViewMode', view);
    updateViewButtons();
    renderUpcoming();
}

async function loadUpcomingGames() {
    const loading = document.getElementById('upcomingLoading');
    const empty = document.getElementById('upcomingEmpty');
    const apiMessage = document.getElementById('apiMessage');
    const apiMessageText = document.getElementById('apiMessageText');

    try {
        const response = await window.safeFetch('/api/upcoming');
        const data = await response.json();

        if (loading) loading.classList.add('is-hidden');

        if (response.status === 400) {
            if (apiMessage) apiMessage.classList.remove('is-hidden');
            if (apiMessageText) apiMessageText.innerText = data.message || 'Erro ao configurar API.';
            return;
        }

        allGames = data.games || [];

        if (allGames.length === 0) {
            if (empty) empty.classList.remove('is-hidden');
            return;
        }

        applyFilters();
    } catch (error) {
        console.error('Error fetching upcoming games:', error);
        if (loading) loading.classList.add('is-hidden');
        if (empty) empty.classList.remove('is-hidden');
    }
}

function applyFilters() {
    const query = (document.getElementById('upcomingSearch')?.value || '').toLowerCase();

    filteredGames = allGames.filter(game => {
        const nameMatch = (game.name || '').toLowerCase().includes(query);
        const summaryMatch = (game.summary || '').toLowerCase().includes(query);
        const genreMatch = (game.genres || []).some(g => (g.name || '').toLowerCase().includes(query));
        return nameMatch || summaryMatch || genreMatch;
    });

    // Update count
    const countEl = document.getElementById('totalItemsCount');
    if (countEl) countEl.innerText = `${filteredGames.length} itens`;

    // Show/hide empty state
    const empty = document.getElementById('upcomingEmpty');
    if (filteredGames.length === 0) {
        if (empty) empty.classList.remove('is-hidden');
    } else {
        if (empty) empty.classList.add('is-hidden');
    }

    renderUpcoming();
}

function renderUpcoming() {
    const container = document.getElementById('upcomingContainer');
    if (!container) return;

    container.innerHTML = '';

    if (currentView === 'list') {
        container.classList.add('is-list-view');
    } else {
        container.classList.remove('is-list-view');
    }

    if (currentView === 'card') renderCardView(filteredGames, container);
    else if (currentView === 'icon') renderIconView(filteredGames, container);
    else renderListView(filteredGames, container);
}

function renderCardView(games, container) {
    games.forEach((game, index) => {
        const genres = (game.genres || []).map(g => `<span class="tag is-dark is-light is-size-7 mr-1 mb-1">${g.name}</span>`).join('');

        const safeNameJs = game.name.replace(/'/g, "\\'");
        const releaseDate = game.release_date || game.release_date_formatted || "";
        const card = document.createElement('div');
        card.className = 'grid-item';
        card.innerHTML = `
            <div class="card box p-0 shadow-sm border-none bg-glass upcoming-card h-100 is-flex is-flex-direction-column" onclick="showUpcomingDetails(${index})">
                <div class="card-image is-relative">
                    <figure class="image is-square bg-light-soft">
                        <img src="${game.cover_url}" alt="${game.name}">
                    </figure>
                    <div class="date-badge">
                        <i class="bi bi-calendar-check mr-1"></i> ${game.release_date_formatted}
                    </div>
                    <button class="button is-small is-dark is-rounded border-none shadow-sm" style="position: absolute; top: 8px; right: 8px; z-index: 10; opacity: 0.8;" onclick="event.stopPropagation(); addToWishlistFromObject(${index})" title="Adicionar à Wishlist">
                        <i class="bi bi-heart"></i>
                    </button>
                </div>
                <div class="card-content p-4 is-flex is-flex-direction-column is-flex-grow-1">
                    <h3 class="title is-6 mb-0 has-text-weight-bold line-clamp-2" style="height: 3em; overflow: hidden;" title="${game.name}">${game.name}</h3>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

function renderIconView(games, container) {
    games.forEach((game, index) => {
        const card = document.createElement('div');
        card.className = 'grid-item';
        card.innerHTML = `
            <div class="card shadow-sm border-none bg-glass h-100 upcoming-card" style="border-radius: 12px; overflow: hidden; position: relative;" title="${game.name}" onclick="showUpcomingDetails(${index})">
                <figure class="image is-square bg-light-soft">
                    <img src="${game.cover_url}" alt="${game.name}" style="object-fit: cover; height: 100%; width: 100%; border-radius: 0;">
                </figure>
                <div style="position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.6); color: white; padding: 2px 5px; font-size: 0.65rem; text-align: center;">
                    ${game.release_date_formatted}
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

function renderListView(games, container) {
    const tableContainer = document.createElement('div');
    tableContainer.className = 'box is-paddingless shadow-sm overflow-hidden border-none bg-glass';

    let rows = games.map((game, index) => {
        const releaseDate = game.release_date || game.release_date_formatted || "";
        return `
        <tr class="list-view-row" onclick="showUpcomingDetails(${index})">
            <td width="60" class="p-2"><img src="${game.cover_url}" style="width: 40px; height: 40px; border-radius: 4px; object-fit: cover;"></td>
            <td class="is-vcentered">
                <strong>${game.name}</strong>
            </td>
            <td class="is-vcentered has-text-centered font-mono is-size-7">${game.release_date_formatted}</td>
            <td class="is-vcentered has-text-right p-3">
                <button class="button is-small is-light" onclick="event.stopPropagation(); addToWishlistFromObject(${index})">
                    <i class="bi bi-heart mr-1"></i> Wishlist
                </button>
            </td>
        </tr>
    `}).join('');

    tableContainer.innerHTML = `
        <table class="table is-fullwidth is-hoverable mb-0 bg-transparent">
            <thead>
                <tr style="border-bottom: 2px solid var(--primary)">
                    <th class="p-2">Capa</th>
                    <th>Título</th>
                    <th class="has-text-centered">Lançamento</th>
                    <th class="has-text-right p-3">Ações</th>
                </tr>
            </thead>
            <tbody>
                ${rows}
            </tbody>
        </table>
    `;
    container.appendChild(tableContainer);
}

function showUpcomingDetails(index) {
    const game = filteredGames[index];
    if (!game) return;

    $('#upModalTitle').text(game.name);
    const bgUrl = game.screenshots && game.screenshots.length > 0 ? `https:${game.screenshots[0].url.replace('t_thumb', 't_1080p')}` : game.cover_url;

    // Prepare screenshots for the gallery (standardizing format for modals.js)
    if (game.screenshots) {
        window.currentScreenshotsList = game.screenshots.map(s => {
            const url = typeof s === 'string' ? s : (s.url || s.image || '');
            // Convert IGDB specific URLs to highres if needed (already handled by t_replace usually, but safer)
            return url.includes('igdb.com') ? `https:${url.replace('t_thumb', 't_1080p')}` : url;
        });
    }

    let content = `
        <div class="modal-banner-container" style="position: relative; height: 200px; overflow: hidden; background: #000;">
            <img src="${bgUrl}" style="width: 100%; height: 100%; object-fit: cover; opacity: 0.5;">
            <div style="position: absolute; bottom: 0; left: 0; right: 0; height: 50%; background: linear-gradient(transparent, var(--bulma-modal-card-body-background-color));"></div>
        </div>
        <div class="px-6 pb-6">
            <div class="columns">
                <div class="column is-4">
                    <figure class="image is-square shadow-lg" style="margin-top: -80px; position: relative; z-index: 10; border-radius: 12px; overflow: hidden; border: 4px solid var(--bulma-modal-card-body-background-color);">
                        <img src="${game.cover_url}" style="height: 100%; width: 100%; object-fit: cover;">
                    </figure>
                    <div class="mt-4 box is-shadowless border bg-light-soft">
                        <p class="heading mb-1 opacity-50">Lançamento</p>
                        <p class="is-size-6 has-text-weight-bold mb-3">${game.release_date_formatted}</p>
                        
                        <p class="heading mb-1 opacity-50">Gêneros</p>
                        <div class="tags">
                            ${(game.genres || []).map(g => `<span class="tag is-small">${g.name}</span>`).join('')}
                        </div>
                        
                        <hr class="my-4 opacity-10">
                        
                        <button class="button is-primary is-fullwidth" onclick="addToWishlistFromObject(${index})">
                            <i class="bi bi-heart-fill mr-1"></i> Wishlist
                        </button>
                    </div>
                </div>
                <div class="column is-8">
                    <h3 class="title is-3 mb-2" style="margin-top: 10px;">${game.name}</h3>
                    <p class="subtitle is-6 opacity-60 mb-5">${game.involved_companies?.[0]?.company?.name || ''}</p>
                    
                    <div class="content opacity-80" style="font-size: 0.95rem; line-height: 1.6;">
                        ${game.summary || 'Sem descrição disponível.'}
                    </div>
                    
                    ${game.screenshots && game.screenshots.length > 0 ? `
                        <div class="mt-5">
                            <p class="heading mb-3">Screenshots</p>
                            <div class="columns is-multiline is-mobile">
                                ${game.screenshots.slice(0, 6).map((s, sIdx) => `
                                    <div class="column is-half" onclick="openScreenshotGallery(${sIdx})">
                                        <figure class="image is-16by9 overflow-hidden" style="border-radius: 8px; cursor: pointer; border: 1px solid rgba(255,255,255,0.1);">
                                            <img src="https:${s.url.replace('t_thumb', 't_cover_big')}" style="object-fit: cover; transition: transform 0.3s;" onmouseover="this.style.transform='scale(1.05)'" onmouseout="this.style.transform='scale(1)'">
                                        </figure>
                                    </div>
                                `).join('')}
                            </div>
                        </div>
                    ` : ''}
                </div>
            </div>
        </div>
    `;

    $('#upModalContent').html(content);
    openModal('upcomingDetailsModal');
}

function addToWishlistFromObject(index) {
    const game = filteredGames[index];
    if (!game) return;

    // Normalize screenshot URLs to have https: prefix
    const normalizedScreenshots = (game.screenshots || []).map(s => {
        let url = s.url || s.image || "";
        if (typeof url === 'string' && url.startsWith('//')) url = 'https:' + url;
        // Upgrade to better quality
        if (typeof url === 'string') url = url.replace('t_thumb', 't_1080p');
        return url;
    });

    addToWishlistByName(game.name, {
        id: game.id,
        release_date: game.release_date || game.release_date_formatted || "",
        icon_url: game.cover_url,
        banner_url: game.screenshots && game.screenshots.length > 0 ?
            (game.screenshots[0].url.startsWith('//') ? 'https:' + game.screenshots[0].url : game.screenshots[0].url).replace('t_thumb', 't_1080p')
            : game.cover_url,
        description: game.summary,
        genres: (game.genres || []).map(g => g.name).join(","),
        screenshots: JSON.stringify(normalizedScreenshots)
    });
}

function addToWishlistByName(name, fallbackData = null) {
    const btn = $(event.currentTarget);
    btn.addClass('is-loading');

    const addViaApi = (postData, successMsg) => {
        $.ajax({
            url: '/api/wishlist',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(postData),
            success: (res) => {
                btn.removeClass('is-loading');
                if (res.success) {
                    showToast(successMsg, 'success');
                    btn.removeClass('is-dark').addClass('is-danger').html('<i class="bi bi-heart-fill"></i>');
                } else {
                    showToast(res.error || t('Erro ao adicionar'), 'error');
                }
            },
            error: (xhr) => {
                btn.removeClass('is-loading');
                const error = xhr.responseJSON?.error || t('Erro ao adicionar');
                showToast(error, 'error');
            }
        });
    };

    if (fallbackData) {
        // Para a página de Upcoming, enviamos os dados diretamente sem buscar no TitleDB
        const postData = {
            title_id: fallbackData.id && fallbackData.id.toString().startsWith('UPCOMING_') ? fallbackData.id : `UPCOMING_${fallbackData.id || Date.now()}`,
            name: name,
            release_date: fallbackData.release_date || "",
            icon_url: fallbackData.icon_url || "",
            banner_url: fallbackData.banner_url || "",
            description: fallbackData.description || "",
            genres: fallbackData.genres || "",
            screenshots: fallbackData.screenshots || ""
        };
        addViaApi(postData, `"${name}" ${t('adicionado à wishlist!')}`);
        return;
    }

    // Fallback para outros lugares que usem apenas o nome
    const trySearch = (query) => {
        return $.getJSON(`/api/titledb/search?q=${encodeURIComponent(query)}`);
    };

    const proceedToAdd = (results) => {
        const match = results.find(r => r.name.toLowerCase() === name.toLowerCase()) || results[0];
        addViaApi({
            title_id: match.id,
            name: match.name,
            icon_url: match.iconUrl,
            banner_url: match.bannerUrl
        }, `"${match.name}" ${t('adicionado à wishlist!')}`);
    };

    trySearch(name).done(results => {
        if (results && results.length > 0) {
            proceedToAdd(results);
        } else {
            const parts = name.split(/[:\-|]/);
            if (parts.length > 1 && parts[0].trim().length >= 3) {
                const shorterName = parts[0].trim();
                trySearch(shorterName).done(fallbackResults => {
                    if (fallbackResults && fallbackResults.length > 0) {
                        proceedToAdd(fallbackResults);
                    } else {
                        btn.removeClass('is-loading');
                        showToast(t('Jogo não encontrado no TitleDB'), 'info');
                    }
                }).fail(() => {
                    btn.removeClass('is-loading');
                });
            } else {
                btn.removeClass('is-loading');
                showToast(t('Jogo não encontrado no TitleDB'), 'info');
            }
        }
    }).fail(() => {
        btn.removeClass('is-loading');
    });
}

function debounce(func, wait) {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => func(...args), wait);
    };
}
