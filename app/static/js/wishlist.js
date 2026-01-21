/**
 * MyFoil Wishlist Logic
 */

document.addEventListener('DOMContentLoaded', () => {
    loadWishlist();
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
            tbody.innerHTML = `<tr><td colspan="7" class="has-text-centered p-6 opacity-50 italic">${t("Sua wishlist está vazia")}</td></tr>`;
            return;
        }

        tbody.innerHTML = '';

        for (const item of items) {
            let gameName = item.title_id;
            let iconUrl = '/static/img/no-icon.png';
            let statusHtml = t('Desconhecido');
            let statusClass = 'has-text-grey';
            let ownedHtml = '--';
            let ownedClass = 'opacity-50';
            let owned = false;

            try {
                const gRes = await fetch(`/api/app_info/${item.title_id}`);
                if (gRes.ok) {
                    const gData = await gRes.json();
                    gameName = gData.name || item.title_id;
                    iconUrl = gData.iconUrl || iconUrl;
                    owned = gData.owned || false;

                    if (owned) {
                        ownedHtml = t('Sim');
                        ownedClass = 'has-text-success';
                    } else {
                        ownedHtml = t('Não');
                        ownedClass = 'has-text-grey-lighter';
                    }

                    const rawDate = String(gData.release_date || '');
                    const releaseDateStr = rawDate.replace(/-/g, '');
                    const todayStr = new Date().toISOString().slice(0, 10).replace(/-/g, '');

                    if (releaseDateStr && releaseDateStr > todayStr) {
                        statusHtml = t('Em Breve');
                        statusClass = 'has-text-info';
                    } else if (releaseDateStr) {
                        statusHtml = t('Lançado');
                        statusClass = 'has-text-success';
                    }
                }
            } catch (e) {
                console.error("Failed to fetch game details", e);
            }

            const row = document.createElement('tr');
            row.innerHTML = `
                <td class="p-1 has-text-centered is-vcentered">
                    <img src="${iconUrl}" style="width: 32px; height: 32px; border-radius: 4px; object-fit: cover;">
                </td>
                <td class="is-vcentered">
                    <strong class="is-size-7-mobile is-clickable" onclick="showGameDetails('${item.title_id}')">${escapeHtml(gameName)}</strong>
                    <p class="is-size-7 font-mono opacity-50">${escapeHtml(item.title_id)}</p>
                </td>
                <td class="is-vcentered">
                    <div class="field has-addons">
                        <div class="control">
                            <button class="button is-small is-rounded is-light py-0 px-2" onclick="changePriority('${item.title_id}', ${item.priority - 1})" ${item.priority <= 0 ? 'disabled' : ''}>
                                <i class="bi bi-chevron-down"></i>
                            </button>
                        </div>
                        <div class="control">
                            <span class="button is-small is-static px-3 is-size-7">${getPriorityLabel(item.priority)}</span>
                        </div>
                        <div class="control">
                            <button class="button is-small is-rounded is-light py-0 px-2" onclick="changePriority('${item.title_id}', ${item.priority + 1})" ${item.priority >= 3 ? 'disabled' : ''}>
                                <i class="bi bi-chevron-up"></i>
                            </button>
                        </div>
                    </div>
                </td>
                <td class="is-vcentered font-mono is-size-7 opacity-70">
                    ${new Date(item.added_date).toLocaleDateString()}
                </td>
                <td class="is-vcentered has-text-centered ${ownedClass} has-text-weight-bold is-size-7">
                    ${ownedHtml}
                </td>
                <td class="is-vcentered ${statusClass} has-text-weight-bold is-size-7">
                    ${statusHtml}
                </td>
                <td class="is-vcentered has-text-right">
                    <div class="buttons is-justify-content-flex-end">
                        ${owned ? `
                            <button class="button is-small is-ghost has-text-grey mr-1" onclick="editGameMetadata('${item.title_id}')" title="${t('Editar Dados')}">
                                <i class="bi bi-pencil"></i>
                            </button>
                        ` : ''}
                        <button class="button is-small is-ghost has-text-danger" onclick="removeFromWishlist('${item.title_id}')" title="${t('Remover')}">
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
        if (tbody) tbody.innerHTML = `<tr><td colspan="7" class="has-text-centered has-text-danger p-6">${t('Erro ao carregar wishlist')}</td></tr>`;
    }
}

function removeFromWishlist(tid) {
    confirmAction({
        title: t('Remover da Wishlist'),
        message: t('Deseja realmente remover este item da sua lista de desejos?'),
        confirmText: t('Remover'),
        confirmClass: 'is-danger',
        onConfirm: async () => {
            try {
                const res = await fetch(`/api/wishlist/${tid}`, { method: 'DELETE' });
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
        $.getJSON(`/api/titledb/search?q=${encodeURIComponent(query)}`, (results) => {
            if (!results || results.length === 0) {
                $('#wishlistSearchResults').html(`<p class="has-text-centered py-4 opacity-50">${t('Nenhum jogo encontrado')}</p>`);
                return;
            }

            let html = '<div class="list">';
            results.slice(0, 10).forEach(game => {
                const safeName = escapeHtml(game.name);
                html += `
                    <div class="list-item is-clickable" onclick="addGameToWishlistFromTitleDB('${game.id}', '${safeName.replace(/'/g, "\\'")}')">
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
        }).fail(() => {
            $('#wishlistSearchResults').html(`<p class="has-text-centered py-4 has-text-danger">${t('Erro ao buscar. Verifique o console.')}</p>`);
        });
    }, 300);
}

function addGameToWishlistFromTitleDB(titleId, titleName) {
    $.ajax({
        url: '/api/wishlist',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ title_id: titleId }),
        success: (res) => {
            if (res.success) {
                showToast(`"${titleName}" ${t('adicionado à wishlist!')}`, 'success');
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
