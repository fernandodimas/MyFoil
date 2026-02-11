let allWishlistItems = [];
let currentWishlistView = localStorage.getItem('wishlistViewMode') || 'list';

document.addEventListener('DOMContentLoaded', () => {
    initWishlistControls();
    loadWishlist();

    // Check for search parameter to auto-open add modal
    const urlParams = new URLSearchParams(window.location.search);
    const searchQuery = urlParams.get('search');
    if (searchQuery) {
        setTimeout(() => {
            openAddToWishlistModal();
            $('#wishlistSearchInput').val(searchQuery);
            searchTitleDBForWishlist();
        }, 500);
    }
});

function initWishlistControls() {
    const gridZoom = document.getElementById('gridZoom');
    if (gridZoom) {
        gridZoom.addEventListener('input', function () {
            updateWishlistGridZoom(this.value);
        });
        const savedZoom = localStorage.getItem('wishlistGridZoom') || 200;
        gridZoom.value = savedZoom;
        updateWishlistGridZoom(savedZoom);
    }
    updateViewButtons();
}

function updateWishlistGridZoom(value) {
    document.documentElement.style.setProperty('--card-width', value + 'px');
    localStorage.setItem('wishlistGridZoom', value);
}

function updateViewButtons() {
    const buttons = document.querySelectorAll('#viewToggleButtons .button');
    buttons.forEach(btn => btn.classList.remove('is-primary'));

    const viewName = (currentWishlistView && currentWishlistView.charAt) ? currentWishlistView.charAt(0).toUpperCase() + currentWishlistView.slice(1) : '';
    const activeBtn = document.getElementById(`btnView${viewName}`);
    if (activeBtn) activeBtn.classList.add('is-primary');
}

function setView(view) {
    currentWishlistView = view;
    localStorage.setItem('wishlistViewMode', view);
    updateViewButtons();
    renderWishlist();
}

async function loadWishlist() {
    const loading = document.getElementById('wishlistLoading');
    const empty = document.getElementById('wishlistEmpty');
    const container = document.getElementById('wishlistContainer');

    if (loading) loading.classList.remove('is-hidden');
    if (empty) empty.classList.add('is-hidden');
    if (container) container.innerHTML = '';

    try {
        const res = await window.safeFetch('/api/wishlist');
        allWishlistItems = await res.json();

        if (loading) loading.classList.add('is-hidden');

        if (allWishlistItems.length === 0) {
            if (empty) empty.classList.remove('is-hidden');
            return;
        }

        // Update count
        const countEl = document.getElementById('totalItemsCount');
        if (countEl) countEl.innerText = `${allWishlistItems.length} itens`;

        renderWishlist();
    } catch (e) {
        console.error(e);
        if (loading) loading.classList.add('is-hidden');
        if (container) container.innerHTML = `<div class="notification is-danger">${t('Erro ao carregar wishlist')}</div>`;
    }
}

function renderWishlist() {
    const container = document.getElementById('wishlistContainer');
    if (!container) return;

    container.innerHTML = '';

    if (currentWishlistView === 'list') {
        container.classList.add('is-list-view');
        renderListView(allWishlistItems, container);
    } else {
        container.classList.remove('is-list-view');
        if (currentWishlistView === 'card') renderCardView(allWishlistItems, container);
        else renderIconView(allWishlistItems, container);
    }
}

function formatDateDisplay(rawDate) {
    if (!rawDate || rawDate === 'Unknown' || rawDate === '--') return { text: t('Desconhecida'), class: 'has-text-grey', icon: '' };

    let dateObj;
    let text = '';

    // Normalize separators
    const cleanDateStr = String(rawDate).trim().replace(/-/g, '/');

    // Case 1: DD/MM/YYYY
    if (cleanDateStr.includes('/') && cleanDateStr.split('/').length === 3) {
        const parts = cleanDateStr.split('/');
        if (parts[0].length <= 2) {
            // DD/MM/YYYY
            dateObj = new Date(parts[2], parts[1] - 1, parts[0]);
        } else {
            // YYYY/MM/DD
            dateObj = new Date(parts[0], parts[1] - 1, parts[2]);
        }
    } else {
        // Case 2: YYYY-MM-DD (ISO) - already handled by replace above, but just in case
        dateObj = new Date(rawDate);

        if (isNaN(dateObj.getTime())) {
            // Case 3: YYYYMMDD
            const clean = String(rawDate).replace(/[^0-9]/g, '');
            if (clean.length === 8) {
                const y = clean.slice(0, 4);
                const m = clean.slice(4, 6);
                const d = clean.slice(6, 8);
                dateObj = new Date(y, m - 1, d);
            }
        }
    }

    if (!dateObj || isNaN(dateObj.getTime())) {
        return { text: rawDate, class: 'has-text-grey', icon: '' };
    }

    const d = String(dateObj.getDate()).padStart(2, '0');
    const m = String(dateObj.getMonth() + 1).padStart(2, '0');
    const y = dateObj.getFullYear();
    text = `${d}/${m}/${y}`;

    const today = new Date();
    today.setHours(0, 0, 0, 0);

    if (dateObj > today) {
        return { text, class: 'has-text-warning', icon: '<i class="bi bi-clock-fill mr-1"></i>' };
    } else {
        return { text, class: 'has-text-success', icon: '<i class="bi bi-check-circle-fill mr-1"></i>' };
    }
}

function renderCardView(items, container) {
    items.forEach((item, index) => {
        const date = formatDateDisplay(item.release_date);
        const card = document.createElement('div');
        card.className = 'wishlist-card-wrapper';
        card.innerHTML = `
            <div class="card box p-0 shadow-sm border-none bg-glass wishlist-card h-100 is-flex is-flex-direction-column" onclick="showGameDetails('${item.title_id}')">
                <div class="card-image is-relative">
                    <figure class="image is-square bg-light-soft">
                        <img src="${item.iconUrl || '/static/img/no-icon.png'}" alt="${item.name}" onerror="this.src='/static/img/no-icon.png'">
                    </figure>
                    <div class="date-badge-wish ${date.class}">
                        ${date.icon}${date.text}
                    </div>
                    <button class="button is-small is-danger is-light is-rounded" style="position: absolute; top: 8px; right: 8px; z-index: 10; opacity: 0.8;" onclick="event.stopPropagation(); removeFromWishlist(${item.id})" title="${t('Remover')}">
                        <i class="bi bi-trash"></i>
                    </button>
                </div>
                <div class="card-content p-3 is-flex is-flex-direction-column is-flex-grow-1">
                    <h3 class="is-size-7 has-text-weight-bold line-clamp-2" style="height: 2.8em;" title="${item.name}">${escapeHtml(item.name || 'Unknown')}</h3>
                    <p class="is-size-7 opacity-50 mt-1">${new Date(item.added_date).toLocaleDateString()}</p>
                </div>
            </div>
        `;
        container.appendChild(card);
    });
}

function renderIconView(items, container) {
    items.forEach((item, index) => {
        const date = formatDateDisplay(item.release_date);
        const card = document.createElement('div');
        card.className = 'wishlist-card-wrapper';
        card.innerHTML = `
            <div class="card shadow-sm border-none bg-glass h-100 wishlist-card" style="border-radius: 12px; overflow: hidden; position: relative;" title="${item.name}" onclick="showGameDetails('${item.title_id}')">
                <figure class="image is-square bg-light-soft">
                    <img src="${item.iconUrl || '/static/img/no-icon.png'}" alt="${item.name}" style="object-fit: cover; height: 100%; width: 100%; border-radius: 0;" onerror="this.src='/static/img/no-icon.png'">
                </figure>
                <div style="position: absolute; bottom: 0; left: 0; right: 0; background: rgba(0,0,0,0.6); color: white; padding: 2px 5px; font-size: 0.65rem; text-align: center;">
                    ${date.text}
                </div>
                <button class="button is-small is-danger shadow-sm" style="position: absolute; top: 2px; right: 2px; height: 20px; width: 20px; padding: 0; opacity: 0; transition: opacity 0.2s;" onmouseover="this.style.opacity=1" onmouseout="this.style.opacity=0" onclick="event.stopPropagation(); removeFromWishlist(${item.id})">
                    <i class="bi bi-x"></i>
                </button>
            </div>
        `;
        // Allow removing from icon view via hover delete button
        card.querySelector('.wishlist-card').onmouseover = function () { this.querySelector('button').style.opacity = 1; };
        card.querySelector('.wishlist-card').onmouseout = function () { this.querySelector('button').style.opacity = 0; };
        container.appendChild(card);
    });
}

function renderListView(items, container) {
    const tableContainer = document.createElement('div');
    tableContainer.className = 'box is-paddingless shadow-sm overflow-hidden border-none bg-glass';

    let rows = items.map(item => {
        const date = formatDateDisplay(item.release_date);
        return `
            <tr class="list-view-row" onclick="showGameDetails('${item.title_id}')">
                <td width="60" class="p-2 has-text-centered">
                    <img src="${item.iconUrl || '/static/img/no-icon.png'}" style="width: 40px; height: 40px; border-radius: 4px; object-fit: cover;" onerror="this.src='/static/img/no-icon.png'">
                </td>
                <td class="is-vcentered">
                    <strong class="is-size-7-mobile">${escapeHtml(item.name || 'Unknown')}</strong>
                </td>
                <td class="is-vcentered opacity-50 is-size-7 font-mono is-hidden-mobile">
                    ${new Date(item.added_date).toLocaleDateString()}
                </td>
                <td class="is-vcentered ${date.class} is-size-7 has-text-weight-semibold">
                    ${date.icon}${date.text}
                </td>
                <td class="is-vcentered has-text-right p-3">
                    <button class="button is-small is-ghost has-text-danger" onclick="event.stopPropagation(); removeFromWishlist(${item.id})" title="${t('Remover')}">
                        <i class="bi bi-trash"></i>
                    </button>
                </td>
            </tr>
        `;
    }).join('');

    tableContainer.innerHTML = `
        <table class="table is-fullwidth is-hoverable mb-0 bg-transparent">
            <thead>
                <tr style="border-bottom: 2px solid var(--primary)">
                    <th class="p-2">Capa</th>
                    <th>Título</th>
                    <th class="is-hidden-mobile">Adicionado em</th>
                    <th>Lançamento</th>
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

function removeFromWishlist(itemId) {
    console.log(`[WISHLIST] Attempting to remove item: ${itemId}`);
    
    confirmAction({
        title: t('Remover da Wishlist'),
        message: t('Deseja realmente remover este item da sua lista de desejos?'),
        confirmText: t('Remover'),
        confirmClass: 'is-danger',
        onConfirm: async () => {
            try {
                console.log(`[WISHLIST] Sending DELETE request to /api/wishlist/${itemId}`);
                const res = await window.safeFetch(`/api/wishlist/${itemId}`, { 
                    method: 'DELETE',
                    credentials: 'same-origin',
                    headers: {
                        'Content-Type': 'application/json'
                    }
                });
                console.log(`[WISHLIST] DELETE response status: ${res.status}`);
                
                const data = await res.json();
                console.log(`[WISHLIST] DELETE response data:`, data);
                
                if (res.ok) {
                    showToast(t('Item removido da wishlist'), 'success');
                    loadWishlist();
                } else {
                    console.error(`[WISHLIST] Error response: ${data.error}`);
                    showToast(`${t('Erro ao remover item')}: ${data.error || t('Erro desconhecido')}`, 'error');
                }
            } catch (e) {
                console.error(`[WISHLIST] Network error:`, e);
                showToast(`${t('Erro ao remover item')}: ${e.message}`, 'error');
            }
        }
    });
}

async function changePriority(tid, newPriority) {
    if (newPriority < 0 || newPriority > 3) return;

    try {
        const res = await window.safeFetch(`/api/wishlist/${tid}`, {
            method: 'PUT',
            credentials: 'same-origin',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ priority: newPriority })
        });
        if (res.ok) {
            loadWishlist();
        } else {
            showToast(t('Erro ao atualizar prioridade'), 'error');
        }
    } catch (e) {
        console.error(e);
        showToast(t('Erro de conexão'), 'error');
    }
}

function openAddToWishlistModal() {
    openModal('addToWishlistModal');
    $('#wishlistSearchInput').val('').focus();
    $('#wishlistSearchResults').html(`<p class="has-text-centered py-4 opacity-50">${t('Digite para buscar jogos no TitleDB...')}</p>`);
}

let wishlistSearchTimeout;
function searchTitleDBForWishlist() {
    const query = $('#wishlistSearchInput').val();

    if (!query || query.length < 3) {
        $('#wishlistSearchResults').html(`<p class="has-text-centered py-4 opacity-50">${t('Digite ao menos 3 caracteres...')}</p>`);
        return;
    }

    clearTimeout(wishlistSearchTimeout);
    wishlistSearchTimeout = setTimeout(() => {
        const trySearch = (q) => $.getJSON(`/api/titledb/search?q=${encodeURIComponent(q)}`);

        const renderResults = (results) => {
            if (!results || results.length === 0) return false;

            // Store results in global variable to avoid syntax errors with inline JSON
            window.__wishlistSearchResults = results;

            let html = '<div class="list">';
            results.slice(0, 20).forEach((game, index) => {
                const safeName = escapeHtml(game.name);

                html += `
                    <div class="list-item is-clickable" onclick="addGameFromSearchRequest(${index})">
                        <div class="media">
                            ${game.iconUrl ? `<div class="media-left"><figure class="image is-48x48"><img src="${game.iconUrl}" style="border-radius: 8px;"></figure></div>` : ''}
                            <div class="media-content">
                                <p class="is-size-7 has-text-weight-bold">${safeName}</p>
                                <p class="is-size-7 opacity-50">${escapeHtml(game.id)}</p>
                            </div>
                        </div>
                    </div>
                `;
            });
            html += '</div>';
            $('#wishlistSearchResults').html(html);
            return true;
        };

        trySearch(query).done(results => {
            if (!renderResults(results)) {
                // Fallback: try shorter query if it contains delimiters
                const parts = query.split(/[:\-|]/);
                if (parts.length > 1 && parts[0].trim().length >= 3) {
                    const shorter = parts[0].trim();
                    trySearch(shorter).done(fallbackResults => {
                        if (!renderResults(fallbackResults)) {
                            $('#wishlistSearchResults').html(`<p class="has-text-centered py-4 opacity-50">${t('Nenhum jogo encontrado')}</p>`);
                        }
                    });
                } else {
                    $('#wishlistSearchResults').html(`<p class="has-text-centered py-4 opacity-50">${t('Nenhum jogo encontrado')}</p>`);
                }
            }
        }).fail(() => {
            $('#wishlistSearchResults').html(`<p class="has-text-centered py-4 has-text-danger">${t('Erro ao buscar. Verifique o console.')}</p>`);
        });
    }, 300);
}

function addGameFromSearchRequest(index) {
    if (!window.__wishlistSearchResults || !window.__wishlistSearchResults[index]) return;
    const game = window.__wishlistSearchResults[index];

    const data = {
        title_id: game.id,
        name: game.name,
        icon_url: game.iconUrl,
        banner_url: game.bannerUrl,
        release_date: game.releaseDate || game.release_date // Ensure date is passed
    };

    addGameToWishlistWithData(data);
}

function addGameToWishlistWithData(data) {
    $.ajax({
        url: '/api/wishlist',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: (res) => {
            if (res.success) {
                showToast(`"${data.name}" ${t('adicionado à wishlist!')}`, 'success');
                closeModal('addToWishlistModal');
                loadWishlist();
            } else {
                showToast(res.error || t('Erro ao adicionar'), 'error');
            }
        },
        error: () => {
            showToast(t('Erro ao adicionar à wishlist'), 'error');
        }
    });
}
