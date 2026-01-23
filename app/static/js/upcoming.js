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

    const activeBtn = document.getElementById(`btnView${currentView.charAt(0).toUpperCase() + currentView.slice(1)}`);
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
        const response = await fetch('/api/upcoming');
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
    games.forEach(game => {
        const genres = (game.genres || []).map(g => `<span class="tag is-dark is-light is-size-7 mr-1 mb-1">${g.name}</span>`).join('');

        const card = document.createElement('div');
        card.className = 'grid-item';
        card.innerHTML = `
            <div class="card box p-0 shadow-sm border-none bg-glass upcoming-card h-100 is-flex is-flex-direction-column">
                <div class="card-image">
                    <figure class="image is-3by4 bg-light-soft">
                        <img src="${game.cover_url}" alt="${game.name}" style="object-fit: cover;">
                    </figure>
                    <div class="date-badge">
                        <i class="bi bi-calendar-check mr-1"></i> ${game.release_date_formatted}
                    </div>
                </div>
                <div class="card-content p-4 is-flex is-flex-direction-column is-flex-grow-1">
                    <h3 class="title is-6 mb-2 has-text-weight-bold line-clamp-2" title="${game.name}">${game.name}</h3>
                    <div class="mb-3">
                        ${genres}
                    </div>
                    <p class="summary-text opacity-70 mb-4 line-clamp-3">
                        ${game.summary || 'Sem resumo disponível.'}
                    </p>
                    <div class="mt-auto pt-3 border-top border-opacity-10 is-flex is-justify-content-space-between is-align-items-center">
                        <button class="button is-small is-primary is-ghost p-0" onclick="window.open('https://www.google.com/search?q=Nintendo+Switch+${encodeURIComponent(game.name)}', '_blank')">
                            <i class="bi bi-info-circle mr-1"></i> Detalhes
                        </button>
                        <button class="button is-small is-light" onclick="addToWishlistByName('${game.name}')" title="Adicionar à Wishlist">
                            <i class="bi bi-heart"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

function renderIconView(games, container) {
    games.forEach(game => {
        const card = document.createElement('div');
        card.className = 'grid-item';
        card.innerHTML = `
            <div class="card shadow-sm border-none bg-glass h-100" style="border-radius: 12px; overflow: hidden; position: relative;" title="${game.name}">
                <figure class="image is-square bg-light-soft">
                    <img src="${game.cover_url}" alt="${game.name}" style="object-fit: cover; cursor: pointer; height: 100%; width: 100%;" onclick="addToWishlistByName('${game.name}')">
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

    let rows = games.map(game => `
        <tr class="list-view-row" onclick="addToWishlistByName('${game.name}')">
            <td width="60" class="p-2"><img src="${game.cover_url}" style="width: 40px; height: 40px; border-radius: 4px; object-fit: cover;"></td>
            <td class="is-vcentered">
                <strong>${game.name}</strong>
                <p class="is-size-7 opacity-70 line-clamp-1">${game.summary || ''}</p>
            </td>
            <td class="is-vcentered has-text-centered font-mono is-size-7">${game.release_date_formatted}</td>
            <td class="is-vcentered has-text-right p-3">
                <button class="button is-small is-primary is-light" onclick="event.stopPropagation(); addToWishlistByName('${game.name}')">
                    <i class="bi bi-heart mr-1"></i> Wishlist
                </button>
            </td>
        </tr>
    `).join('');

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

function addToWishlistByName(name) {
    window.location.href = `/wishlist?search=${encodeURIComponent(name)}`;
}

function debounce(func, wait) {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => func(...args), wait);
    };
}
