/**
 * MyFoil Wishlist Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    loadWishlist();

    // Check for search parameter to auto-open add modal
    const urlParams = new URLSearchParams(window.location.search);
    const searchQuery = urlParams.get('search');
    if (searchQuery) {
        setTimeout(() => {
            openAddToWishlistModal();
            $('#wishlistSearchInput').val(searchQuery);
            searchTitleDBForWishlist();
        }, 500); // Small delay to ensure everything is ready
    }
});

function getPriorityLabel(level) {
    switch (parseInt(level)) {
        case 3: return `<span class="tag is-danger is-light">${t('Alta')}</span>`;
        case 2: return `<span class="tag is-warning is-light">${t('Média')}</span>`;
        case 1: return `<span class="tag is-info is-light">${t('Baixa')}</span>`;
        default: return `<span class="tag is-light">${t('Normal')}</span>`;
    }
}

async function loadWishlist() {
    try {
        const res = await fetch('/api/wishlist');
        const items = await res.json();
        const tbody = document.getElementById('wishlistBody');
        if (!tbody) return;

        if (items.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="has-text-centered p-6 opacity-50 italic">${t("Sua wishlist está vazia")}</td></tr>`;
            return;
        }

        tbody.innerHTML = '';

        for (const item of items) {
            let statusHtml = t('Desconhecido');
            let statusClass = 'has-text-grey';

            const rawDate = String(item.release_date || '');
            const releaseDateStr = rawDate.replace(/-/g, '').slice(0, 8);
            const todayStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');

            if (releaseDateStr && releaseDateStr > todayStr) {
                statusHtml = t('Em Breve');
                statusClass = 'has-text-info';
            } else if (releaseDateStr) {
                statusHtml = t('Lançado');
                statusClass = 'has-text-success';
            }

            const row = document.createElement('tr');
            row.innerHTML = `
                <td class="p-1 has-text-centered is-vcentered">
                    <img src="${item.iconUrl || '/static/img/no-icon.png'}" style="width: 32px; height: 32px; border-radius: 4px; object-fit: cover;" onerror="this.src='/static/img/no-icon.png'">
                </td>
                <td class="is-vcentered">
                    <strong class="is-size-7-mobile is-clickable" onclick="showGameDetails('${item.title_id}')">${escapeHtml(item.name || 'Unknown')}</strong>
                </td>
                <td class="is-vcentered font-mono is-size-7 opacity-70">
                    ${new Date(item.added_date).toLocaleDateString()}
                </td>
                <td class="is-vcentered ${statusClass} has-text-weight-bold is-size-7">
                    ${statusHtml}
                </td>
                <td class="is-vcentered has-text-right">
                    <div class="buttons is-justify-content-flex-end">
                        <button class="button is-small is-ghost has-text-danger" onclick="removeFromWishlist(${item.id})" title="${t('Remover')}">
                            <i class="bi bi-trash"></i>
                        </button>
                    </div>
                </td>
            `;
            tbody.appendChild(row);
        }
    } catch (e) {
        console.error(e);
        const tbody = document.getElementById('wishlistBody');
        if (tbody) tbody.innerHTML = `<tr><td colspan="6" class="has-text-centered has-text-danger p-6">${t('Erro ao carregar wishlist')}</td></tr>`;
    }
}

function removeFromWishlist(itemId) {
    confirmAction({
        title: t('Remover da Wishlist'),
        message: t('Deseja realmente remover este item da sua lista de desejos?'),
        confirmText: t('Remover'),
        confirmClass: 'is-danger',
        onConfirm: async () => {
            try {
                const res = await fetch(`/api/wishlist/${itemId}`, { method: 'DELETE' });
                if (res.ok) {
                    showToast(t('Item removido da wishlist'), 'success');
                    loadWishlist();
                }
            } catch (e) {
                showToast(t('Erro ao remover item'), 'error');
            }
        }
    });
}

async function changePriority(tid, newPriority) {
    if (newPriority < 0 || newPriority > 3) return;

    try {
        const res = await fetch(`/api/wishlist/${tid}`, {
            method: 'PUT',
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

            let html = '<div class="list">';
            results.slice(0, 10).forEach(game => {
                const safeName = escapeHtml(game.name);
                const gameData = JSON.stringify({
                    title_id: game.id,
                    name: game.name,
                    icon_url: game.iconUrl,
                    banner_url: game.bannerUrl
                }).replace(/'/g, "\\'");

                html += `
                    <div class="list-item is-clickable" onclick='addGameToWishlistWithData(${gameData})'>
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
