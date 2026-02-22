/**
 * MyFoil Shared Modals Logic
 * Consolidates all modal interactions, game details loading, and metadata management.
 */

const openModal = (id) => $(`#${id}`).addClass('is-active');
const closeModal = (id) => $(`#${id}`).removeClass('is-active');

// Generic Confirmation Helper
window.confirmAction = function (options) {
    const { title, message, onConfirm, confirmText, confirmClass } = options;
    $('#confirmTitle').text(title || t('modal.confirm_title'));
    $('#confirmMessage').text(message || t('modal.confirm_msg'));
    $('#btnConfirmAction').text(confirmText || t('modal.confirm_btn'));
    $('#btnConfirmAction').attr('class', `button is-small ${confirmClass || 'is-primary'}`);

    $('#btnConfirmAction').off('click').on('click', function () {
        if (onConfirm) onConfirm();
        closeModal('genericConfirmModal');
    });

    openModal('genericConfirmModal');
};

function showGameDetails(id) {
    $.getJSON(`/api/app_info/${id}`, (game) => {
        // normalize possible envelope responses (e.g. { code, success, data })
        if (typeof unwrap === 'function') {
            game = unwrap(game) || {};
        } else if (game && game.data !== undefined) {
            game = game.data || {};
        } else {
            game = game || {};
        }

        $('#modalTitle').text(game.name);

        // Update screenshot state
        currentScreenshotsList = game.screenshots || [];

        // Set navigation context for keyboard shortcuts
        const navGames = (window.filteredGames && window.filteredGames.length) ? window.filteredGames : (window.games || []);
        window.setModalNavigationContext(id, navGames);

        // Base Files Section
        let filesHtml = game.files && game.files.length > 0 ? `
            <div class="mb-5">
                <p class="heading has-text-weight-bold mb-3 has-text-primary">${t('modal.base_files_found')} (${game.files.length})</p>
                ${game.files.map(f => `
                    <div class="box is-shadowless border p-3 mb-2 bg-light-soft" style="display: flex; flex-direction: row; flex-wrap: nowrap; gap: 0.5rem; align-items: center;">
                        <div class="file-name" style="flex: 1 1 auto; min-width: 0; overflow: hidden;">
                            <p class="is-size-7 has-text-weight-bold" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</p>
                            <p class="is-size-7 opacity-50" style="white-space: nowrap; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(f.filepath)}">${escapeHtml(f.filepath)}</p>
                        </div>
                        <div class="file-version" style="flex: 0 0 auto;">
                            <span class="tag is-info is-light font-mono">v${escapeHtml(f.version || '0')}</span>
                        </div>
                        <div class="file-size" style="flex: 0 0 auto;">
                            <span class="tag is-light font-mono">${escapeHtml(f.size_formatted || '--')}</span>
                        </div>
                        <div class="file-actions buttons is-gap-1" style="flex: 0 0 auto; display: flex; flex-direction: row;">
                            <a href="/api/get_game/${f.id}" class="button is-primary is-small" title="${t('common.download')}">
                                <span class="icon is-small"><i class="bi bi-download"></i></span>
                            </a>
                            <button class="button is-danger is-small is-light" onclick="deleteGameFile(${f.id}, '${escapeHtml(game.id)}')" title="${t('common.delete_file')}">
                                <span class="icon is-small"><i class="bi bi-trash-fill"></i></span>
                            </button>
                        </div>
                    </div>
                `).join('')}
            </div>
        ` : (!game.has_base ? `<p class="notification is-warning is-light p-2 is-size-7" style="border: 1px solid rgba(0,0,0,0.1)">${t('modal.missing_base')}</p>` : '');

        // Updates Section
        const sortedUpdates = [...(game.updates || [])].sort((a, b) => b.version - a.version);
        let updatesHtml = '';

        if (sortedUpdates.length === 0) {
            updatesHtml = `
                <div class="mb-5">
                    <p class="heading has-text-weight-bold mb-3 has-text-link">${t('modal.updates')}</p>
                    <p class="is-size-7 opacity-50 italic">${t('modal.no_updates_dlcs')}</p>
                </div>
            `;
        } else {
            const latest = sortedUpdates[0];
            const others = sortedUpdates.slice(1);

            const renderUpdateRow = (u) => {
                const file = u.files && u.files.length > 0 ? u.files[0] : null;
                const isRedundant = u !== latest && game.updates.length > 1;
                return `
                    <tr>
                        <td class="has-text-weight-bold">v${escapeHtml(u.version)}</td>
                        <td class="opacity-70">${escapeHtml(u.release_date || '--')}</td>
                        <td class="has-text-centered">
                            ${u.owned && file ? `
                                <div class="field is-grouped is-grouped-centered is-align-items-center">
                                    <span class="tag is-light font-mono mr-2 is-hidden-mobile">${escapeHtml(file.size_formatted || '--')}</span>
                                    ${isRedundant ? `<span class="tag tag-redundant mr-1 has-text-weight-bold">${t('common.redundant')}</span>` : ''}
                                    <p class="control">
                                        <a href="/api/get_game/${file.id}" class="button is-primary is-small" title="${t('Download')}">
                                            <i class="bi bi-download"></i>
                                        </a>
                                    </p>
                                    <p class="control">
                                        <button class="button is-danger is-small is-light" onclick="deleteGameFile(${file.id}, '${escapeHtml(game.id)}')" title="${t('Excluir')}">
                                            <i class="bi bi-trash"></i>
                                        </button>
                                    </p>
                                </div>
                            ` : (u.owned ? `<span class="tag is-warning is-light is-small">${t('Erro')}</span>` : `
                                <div class="field is-grouped is-grouped-centered is-align-items-center">
                                    <span class="tag is-danger is-light is-small mr-2">${t('Falta')}</span>
                                </div>
                            `)}
                        </td>
                    </tr>
                `;
            };

            updatesHtml = `
                <div class="mb-5">
                    <div class="is-flex is-justify-content-between is-align-items-center mb-3">
                        <p class="heading has-text-weight-bold has-text-link mb-0">${t('modal.update_history')}</p>
                        ${others.length > 0 ? `<button class="button is-ghost is-small p-0" onclick="$('#otherUpdates').toggleClass('is-hidden'); $(this).find('i').toggleClass('bi-chevron-down bi-chevron-up')">
                            <span class="is-size-7 mr-1 text-primary">${others.length} ${t('common.more')}</span>
                            <i class="bi bi-chevron-down text-primary"></i>
                        </button>` : ''}
                    </div>
                    <div class="table-container">
                        <table class="table is-narrow is-fullwidth is-size-7">
                            <thead>
                                <tr>
                                    <th>${t('common.version')}</th>
                                    <th>${t('common.release_date')}</th>
                                    <th class="has-text-centered">${t('common.status')}</th>
                                </tr>
                            </thead>
                            <tbody>
                                ${renderUpdateRow(latest)}
                            </tbody>
                            <tbody id="otherUpdates" class="is-hidden">
                                ${others.map(u => renderUpdateRow(u)).join('')}
                            </tbody>
                        </table>
                    </div>
                </div>
            `;
        }

        // DLCs Section
        let dlcsHtml = game.dlcs && game.dlcs.length > 0 ? `
            <div class="mb-5">
                <p class="heading has-text-weight-bold mb-3 has-text-success">${t('modal.dlcs_found')}</p>
                <div class="table-container">
                <table class="table is-narrow is-fullwidth is-size-7">
                    <thead>
                        <tr>
                            <th>${t('common.name')}</th>
                            <th class="has-text-centered">${t('common.release_date')}</th>
                            <th class="has-text-centered">${t('common.status')}</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${game.dlcs.map(d => {
            const file = d.files && d.files.length > 0 ? d.files[0] : null;
            const ignoreId = `ignore-dlc-${d.app_id}`;
            return `
                                    <tr>
                                        <td class="has-text-weight-bold" onclick="showDlcDetails('${escapeHtml(d.app_id)}')" style="cursor: pointer; color: inherit;" title="${t('modal.view_dlc_details')}">${escapeHtml(d.name)}</td>
                                        <td class="opacity-50 font-mono has-text-centered">${escapeHtml(d.release_date || d.releaseDate || '--')}</td>
                                        <td class="has-text-centered">
                                            ${d.owned && file ? `
                                                <div class="field is-grouped is-grouped-centered is-align-items-center">
                                                    <span class="tag is-light font-mono mr-2 is-hidden-mobile">${escapeHtml(file.size_formatted || '--')}</span>
                                                    <p class="control">
                                                        <a href="/api/get_game/${file.id}" class="button is-primary is-light is-small" title="${t('common.download')}">
                                                            <i class="bi bi-download"></i>
                                                        </a>
                                                    </p>
                                                    <p class="control">
                                                        <button class="button is-danger is-small is-light" onclick="deleteGameFile(${file.id}, '${escapeHtml(game.id)}')" title="${t('common.delete_file')}">
                                                            <i class="bi bi-trash"></i>
                                                        </button>
                                                    </p>
                                                </div>
                                            ` : (d.owned ? `<span class="tag is-warning is-light is-small">${t('common.error')}</span>` : `
                                                <div class="field is-grouped is-grouped-centered is-align-items-center">
                                                    <span class="tag is-danger is-light is-small mr-2">${t('common.missing')}</span>
                                                    <input type="checkbox" class="is-small"
                                                        id="${ignoreId}"
                                                        title="${t('modal.ignore_dlc')}"
                                                        onchange="toggleItemIgnore('${escapeHtml(game.id)}', 'dlc', '${escapeHtml(d.app_id)}', this.checked)">
                                                </div>
                                            `)}
                                        </td>
                                    </tr>
                                    `;
        }).join('')}
                    </tbody>
                </table>
            </div>
        </div>
        ` : '';

        let content = `
            <div class="modal-banner-container" style="position: relative; height: 240px; overflow: hidden; background: #000;">
                <img src="${escapeHtml(game.bannerUrl || game.iconUrl || '/static/img/no-icon.png')}" style="width: 100%; height: 100%; object-fit: cover; opacity: 0.5;">
                <div style="position: absolute; bottom: 0; left: 0; right: 0; height: 80%; background: linear-gradient(transparent, var(--bulma-modal-card-body-background-color));"></div>
                <button class="delete is-large" aria-label="close" onclick="closeModal('gameDetailsModal')" style="position: absolute; top: 1.5rem; right: 1.5rem; background-color: rgba(255,255,255,0.2); backdrop-filter: blur(8px); z-index: 20; border: 1px solid rgba(255,255,255,0.1);"></button>
            </div>
            <div class="p-6">
                <div class="columns is-variable is-6">
                    <div class="column is-4">
                        <figure class="image is-square box p-0 shadow-lg overflow-hidden mb-5" style="margin-top: -100px; position: relative; z-index: 15; border: 4px solid var(--bulma-card-background); border-radius: 12px; transition: transform 0.3s ease;">
                            <img src="${escapeHtml(game.iconUrl || '/static/img/no-icon.png')}" alt="Icon" style="height: 100%; width: 100%; object-fit: cover;">
                        </figure>
                        <div class="box p-4 is-shadowless border bg-light-soft" style="border-radius: 12px;">
                            <div class="mb-3">
                                <p class="is-size-7 heading mb-1 opacity-50">${t('common.publisher')}</p>
                                <p class="is-size-6 has-text-weight-bold">${escapeHtml(game.publisher || '--')}</p>
                            </div>
                            <div class="mb-3">
                                <p class="is-size-7 heading mb-1 opacity-50">${t('common.release_date')}</p>
                                <p class="is-size-6">${escapeHtml(game.release_date || '--')}</p>
                            </div>
                            <div class="mb-3">
                                <p class="is-size-7 heading mb-1 opacity-50">${t('common.version')}</p>
                                <p class="is-size-6"><span class="tag is-info is-light has-text-weight-bold">v${escapeHtml(game.display_version)}</span></p>
                            </div>
                            <div class="mb-3">
                                <p class="is-size-7 heading mb-1 opacity-50">${t('common.total_size')}</p>
                                <p class="is-size-6 has-text-weight-bold font-mono">${escapeHtml(game.size_formatted || '--')}</p>
                            </div>
                            ${game.added_at ? `
                            <div class="mb-3">
                                <p class="is-size-7 heading mb-1 opacity-30">${t('common.added_at')}</p>
                                <p class="is-size-7 opacity-40 font-mono">${new Date(game.added_at).toLocaleDateString()}</p>
                            </div>
                            ` : ''}
                            <div>
                                <p class="is-size-7 heading mb-1 opacity-50">${t('common.genre')}</p>
                                <div class="tags">
                                    ${Array.isArray(game.category) ? game.category.map(c => `<span class="tag is-small is-light">${escapeHtml(c)}</span>`).join('') : `<span class="tag is-small is-light">${escapeHtml(game.category || '--')}</span>`}
                                </div>
                            </div>
                            <div class="mt-3">
                                <a href="${game.nsuid ? 'https://ec.nintendo.com/apps/' + game.nsuid + '/US' : (window.currentLocale === 'pt_BR' ? 'https://www.nintendo.com/pt-br/search/#q=' + encodeURIComponent(game.name) : 'https://www.nintendo.com/us/search/#q=' + encodeURIComponent(game.name))}" target="_blank" class="button is-small is-light is-fullwidth" style="border-color: #e60012; color: #e60012; --bulma-text: #e60012;">
                                    <span class="icon"><i class="bi bi-shop"></i></span>
                                    <span>eShop</span>
                                </a>
                            </div>
                            <hr class="my-4 opacity-5">
                            <div class="mb-3">
                                <p class="is-size-7 heading mb-1 opacity-50">${t('common.custom_tags')}</p>
                                <div id="gameModalTags" class="tags mb-2">
                                    <!-- Tags will be loaded here -->
                                </div>
                                <div class="field has-addons">
                                    <div class="control is-expanded">
                                        <div class="select is-small is-fullwidth">
                                            <select id="modalAddTagSelect">
                                                <option value="">${t('modal.add_tag_placeholder')}</option>
                                            </select>
                                        </div>
                                    </div>
                                    <div class="control">
                                        <button class="button is-small is-primary" onclick="addTagToGame('${escapeHtml(game.id)}')">
                                            <i class="bi bi-plus"></i>
                                        </button>
                                    </div>
                                </div>
                            </div>
                            <hr class="my-4 opacity-5"/>
                            ${!game.owned ? `
                            <div class="wishlist-section mb-2">
                                <button id="btnWishlist" class="button is-fullwidth is-small is-light" onclick="toggleWishlist('${escapeHtml(game.id)}')">
                                    <span class="icon"><i class="bi bi-heart"></i></span>
                                    <span>${t('common.wishlist')}</span>
                                </button>
                            </div>
                            ` : ''}

                            ${game.owned ? `
                            <div class="mt-2">
                                <button class="button is-fullwidth is-small is-ghost opacity-70" onclick="refreshSingleGameMetadata('${escapeHtml(game.id)}')">
                                    <i class="bi bi-arrow-repeat mr-1"></i> ${t('modal.refresh_ratings')}
                                </button>
                            </div>
                            ` : ''}

                            <div class="edit-section">
                                <button class="button is-fullwidth is-small is-ghost has-text-grey" 
                                        onclick="editGameMetadata('${escapeHtml(game.id)}')"
                                        ${!game.owned ? `disabled title="${t('modal.game_not_in_library')}"` : ''}>
                                    <span class="icon"><i class="bi bi-pencil"></i></span>
                                    <span>${t('modal.edit_metadata')}</span>
                                </button>
                            </div>
                        </div>
                    </div>
                    <div class="column is-8">
                        <div class="mb-6">
                            <h2 class="title is-3 mb-4" style="font-weight: 800; letter-spacing: -0.5px;">${escapeHtml(game.name)}</h2>
                            <p class="is-size-7 font-mono opacity-50 mb-4">${escapeHtml(game.id)}</p>
                            
                            <!-- Ratings & Stats Section -->
                            ${(game.metacritic_score || game.rawg_rating || game.playtime_main) ? `
                                <div class="box is-shadowless border p-4 mb-5 bg-light-soft" style="border-radius: 12px; border-left: 4px solid var(--color-primary) !important;">
                                    <div class="columns is-mobile is-vcentered">
                                        ${game.metacritic_score ? `
                                            <div class="column has-text-centered">
                                                <p class="is-size-7 heading mb-1 opacity-50">Metacritic</p>
                                                <div class="${game.metacritic_score >= 75 ? 'has-text-success' : (game.metacritic_score >= 50 ? 'has-text-warning' : 'has-text-danger')}">
                                                    <span class="is-size-4 has-text-weight-black">${game.metacritic_score}</span>
                                                </div>
                                            </div>
                                        ` : ''}
                                        ${game.rawg_rating ? `
                                            <div class="column has-text-centered">
                                                <p class="is-size-7 heading mb-1 opacity-50">RAWG</p>
                                                <div class="has-text-info">
                                                    <span class="is-size-4 has-text-weight-black">${game.rawg_rating.toFixed(1)}</span>
                                                    <span class="is-size-7 opacity-50">/ 5</span>
                                                </div>
                                            </div>
                                        ` : ''}
                                        ${game.playtime_main ? `
                                            <div class="column has-text-centered">
                                                <p class="is-size-7 heading mb-1 opacity-50">Playtime</p>
                                                <div class="has-text-primary">
                                                    <span class="is-size-4 has-text-weight-black">${game.playtime_main}</span>
                                                    <span class="is-size-7">h</span>
                                                </div>
                                            </div>
                                        ` : ''}
                                    </div>
                                </div>
                            ` : ''}

                            <div class="content is-size-6 opacity-80" style="line-height: 1.7;">
                                ${game.description ? game.description : `<p class="italic opacity-50">${t('No description available')}</p>`}
                            </div>
                        </div>
                        
                        ${(filesHtml || updatesHtml || dlcsHtml) ? `
                        <hr class="my-5 opacity-10">
                        <div class="details-sections mt-4">
                            ${filesHtml}
                            ${updatesHtml}
                            ${dlcsHtml}
                        </div>
                        ` : ''}
                        
                        ${game.screenshots && game.screenshots.length > 0 ? `
                        <div class="screenshot-carousel mt-5">
                            <p class="heading has-text-weight-bold mb-3">${t('Screenshots')}</p>
                            <div class="swiper swiper-screenshots" id="gameScreenshotsSwiper">
                                <div class="swiper-wrapper">
                                    ${game.screenshots.map((s, idx) => {
            const url = typeof s === 'string' ? s : (s.url || s.image);
            if (!url) return '';
            return `
                                            <div class="swiper-slide" style="width: auto;">
                                                <img src="${escapeHtml(url)}" alt="Screenshot ${idx + 1}" loading="lazy" onclick="openScreenshotGallery(${idx})" style="cursor: pointer; width: 320px; height: 180px; object-fit: cover; border-radius: 8px; display: block;">
                                            </div>
                                        `;
        }).join('')}
                                </div>
                                <div class="swiper-pagination"></div>
                                <div class="swiper-button-prev"></div>
                                <div class="swiper-button-next"></div>
                            </div>
                        </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
        $('#modalContent').html(content);
        loadGameTagsAndWishlist(game.id);
        openModal('gameDetailsModal');

        // Adjust modal for mobile
        adjustModalForMobile('gameDetailsCard');

        // Initialize Swiper carousel
        setTimeout(() => {
            const swiperEl = document.querySelector('.swiper-screenshots');
            if (swiperEl && !swiperEl.swiper) {
                new Swiper('.swiper-screenshots', {
                    slidesPerView: 'auto',
                    spaceBetween: 12,
                    centeredSlides: true,
                    loop: true,
                    pagination: {
                        el: '.swiper-pagination',
                        clickable: true,
                    },
                    navigation: {
                        nextEl: '.swiper-button-next',
                        prevEl: '.swiper-button-prev',
                    },
                });
            }
        }, 100);
    });
}

function showDlcDetails(id) {
    $.getJSON(`/ api / app_info / ${id} `, (dlc) => {
        $('#dlcModalTitle').text(dlc.name);
        let content = `
            < div class="p-6" >
                <div class="columns">
                    <div class="column is-4">
                        <figure class="image is-square box p-0 shadow-sm overflow-hidden mb-4">
                            <img src="${escapeHtml(dlc.iconUrl || '/static/img/no-icon.png')}" style="height: 100%; width: 100%; object-fit: cover;">
                        </figure>
                    </div>
                    <div class="column is-8">
                        <h3 class="title is-4 mb-2">${escapeHtml(dlc.name)}</h3>
                        <p class="is-size-7 font-mono opacity-50 mb-4">${escapeHtml(dlc.id)}</p>
                        <div class="columns is-mobile mb-4">
                            <div class="column">
                                <p class="is-size-7 heading mb-1 opacity-50">${t('Data de Lançamento')}</p>
                                <p class="is-size-6">${escapeHtml(dlc.release_date || dlc.releaseDate || '--')}</p>
                            </div>
                            <div class="column">
                                <p class="is-size-7 heading mb-1 opacity-50">${t('Status')}</p>
                                <p class="is-size-6">${dlc.owned ? `<span class="has-text-success"><i class="bi bi-check-circle-fill"></i> ${t('Sim')}</span>` : `<span class="has-text-danger"><i class="bi bi-x-circle-fill"></i> ${t('Não')}</span>`}</p>
                            </div>
                        </div>
                        <div class="content is-size-7 opacity-80 mb-4">
                            ${dlc.description || t('Nenhuma descrição disponível para esta DLC.')}
                        </div>
                        
                        ${dlc.files && dlc.files.length > 0 ? `
                            <div class="box has-background-light-soft p-3">
                                <p class="is-size-7 heading mb-2 opacity-50">${t('Arquivos Identificados')}</p>
                                ${dlc.files.map(f => `
                                    <div class="mb-2 pb-2" style="border-bottom: 1px solid rgba(0,0,0,0.05)">
                                        <p class="is-size-7 has-text-weight-bold truncate" title="${escapeHtml(f.filename)}">${escapeHtml(f.filename)}</p>
                                        <p class="is-size-7 opacity-50 font-mono truncate" style="font-size: 0.65rem !important;" title="${escapeHtml(f.filepath)}">${escapeHtml(f.filepath)}</p>
                                        <p class="is-size-7 opacity-50">${t('Tamanho')}: ${escapeHtml(f.size_formatted)}</p>
                                    </div>
                                `).join('')}
                            </div>
                        ` : ''}
                    </div>
                </div>
                <hr class="my-4 opacity-10">
                <div class="buttons is-right">
                    <button class="button is-small" onclick="closeModal('dlcDetailsModal')">${t('common.close')}</button>
                </div>
            </div>
        `;
        $('#dlcModalContent').html(content);
        openModal('dlcDetailsModal');
    });
}

function deleteGameFile(fileId, titleId) {
    confirmAction({
        title: t('Confirmar Exclusão'),
        message: t('Tem certeza que deseja excluir este arquivo? Esta ação não pode ser desfeita.'),
        confirmText: t('Excluir'),
        confirmClass: 'is-danger',
        onConfirm: () => {
            const btn = $(event.target).closest('.button');
            btn.addClass('is-loading');

            $.post(`/api/files/delete/${fileId}`, (res) => {
                btn.removeClass('is-loading');
                if (res.success) {
                    showGameDetails(titleId);
                    if (typeof applyFilters === 'function') {
                        $.getJSON(`/api/app_info/${titleId}`, (updatedGame) => {
                            if (!updatedGame || !updatedGame.id) return;
                            const idx = games.findIndex(g => g && g.id === titleId);
                            if (idx !== -1) {
                                games[idx] = updatedGame;
                                localStorage.setItem('myfoil_library_cache', JSON.stringify(games));
                                applyFilters();
                            }
                        });
                    }
                    if (typeof loadWishlist === 'function') loadWishlist();
                    showToast(t('Arquivo excluído com sucesso'), 'success');
                } else {
                    showToast(res.error || t('Erro ao excluir'), 'error');
                }
            }).fail((xhr) => {
                btn.removeClass('is-loading');
                showToast(t('Erro de comunicação'), 'error');
            });
        }
    });
}

function loadGameTagsAndWishlist(titleId) {
    // Defensive handling for titleId (may be undefined/null)
    if (titleId && typeof titleId === 'string') {
        titleId = titleId.toUpperCase();
    } else if (typeof titleId === 'string') {
        // empty string -> treat as null
        titleId = null;
    } else {
        titleId = null;
    }

    // Load all available tags for the select
    $.getJSON('/api/tags', (tagsRes) => {
        let tags = tagsRes;
        if (typeof unwrap === 'function') tags = unwrap(tagsRes) || tagsRes;
        if (typeof coerceArray === 'function') tags = coerceArray(tags);
        if (!Array.isArray(tags)) tags = [];

        const select = $('#modalAddTagSelect');
        if (select.length) {
            select.find('option:not(:first)').remove();
            tags.forEach(tag => {
                const id = tag && (tag.id || tag.tag_id) ? (tag.id || tag.tag_id) : (typeof tag === 'string' ? tag : '');
                const name = tag && (tag.name || tag.label) ? (tag.name || tag.label) : (typeof tag === 'string' ? tag : '');
                select.append(`<option value="${escapeHtml(id)}">${escapeHtml(name)}</option>`);
            });
        }
    });

    // Load tags for this specific title (if we have an id)
    if (titleId) {
        $.getJSON(`/api/titles/${titleId}/tags`, (tagsRes) => {
            let tags = tagsRes;
            if (typeof unwrap === 'function') tags = unwrap(tagsRes) || tagsRes;
            if (typeof coerceArray === 'function') tags = coerceArray(tags);
            if (!Array.isArray(tags)) tags = [];

            const container = $('#gameModalTags').empty();
            tags.forEach(tag => {
                const color = tag && tag.color ? tag.color : '#888';
                const name = tag && (tag.name || tag.label) ? (tag.name || tag.label) : (typeof tag === 'string' ? tag : '');
                const id = tag && (tag.id || tag.tag_id) ? (tag.id || tag.tag_id) : '';
                container.append(`
                    <span class="tag" style="background-color: ${escapeHtml(color)}; color: #fff;">
                        ${escapeHtml(name)}
                        <button class="delete is-small" onclick="removeTagFromGame('${escapeHtml(titleId)}', ${id})"></button>
                    </span>
                `);
            });
        });
    } else {
        $('#gameModalTags').empty();
    }

    // Wishlist handling - normalize response shapes
    $.getJSON('/api/wishlist', (wishlistRes) => {
        let wishlist = wishlistRes;
        if (typeof unwrap === 'function') wishlist = unwrap(wishlistRes) || wishlistRes;
        if (typeof coerceArray === 'function') wishlist = coerceArray(wishlist);
        if (!Array.isArray(wishlist)) wishlist = [];

        const btn = $('#btnWishlist');
        if (!btn.length) return;

        if (titleId) {
            const inWishlist = wishlist.find(i => (i.title_id || i.titleId || i.title) === titleId);
            if (inWishlist) {
                btn.removeClass('is-light').addClass('is-danger is-light')
                    .find('i').removeClass('bi-heart').addClass('bi-heart-fill');
            } else {
                btn.removeClass('is-danger').addClass('is-light')
                    .find('i').removeClass('bi-heart-fill').addClass('bi-heart');
            }
        } else {
            // Reset to default if we don't have an id
            btn.removeClass('is-danger').addClass('is-light')
                .find('i').removeClass('bi-heart-fill').addClass('bi-heart');
        }
    });

    // Load ignore preferences for DLCs and Updates (only if we have a titleId)
    if (titleId) {
        $.getJSON(`/api/library/ignore/${titleId}`, (dataRes) => {

            let data = dataRes;
            if (typeof unwrap === 'function') data = unwrap(dataRes) || dataRes;
            // Handle nested data structure from API
            if (data.data) data = data.data;
            data = data || {};

            // Sincronizar com a variável global
            if (titleId) {
                ignorePreferences[titleId] = {
                    dlcs: data.dlcs || {},
                    updates: data.updates || {}
                };
            }

            if (data.dlcs && Object.keys(data.dlcs).length > 0) {
                Object.entries(data.dlcs).forEach(([app_id, ignored]) => {
                    const cb = document.getElementById(`ignore-dlc-${app_id}`);
                    if (cb) cb.checked = ignored;
                });
            }
        }).fail((xhr, status, error) => {
            console.error('Failed to load ignore preferences:', status, error);
            // Clear all checkboxes on error
            $('input[id^="ignore-dlc-"]').prop('checked', false);
        });
    } else {
        // No titleId -> clear checkboxes
        $('input[id^="ignore-dlc-"]').prop('checked', false);
    }
}

function toggleItemIgnore(titleId, type, itemId, value) {
    if (titleId && typeof titleId === 'string') {
        titleId = titleId.toUpperCase();
    }

    $.ajax({
        url: `/api/library/ignore/${titleId}`,
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            type: type,
            item_id: itemId,
            ignored: value
        }),
        success: (res) => {

            if (res.success) {
                const msg = value ? t('{type} {id} será ignorado').replace('{type}', (type || '').toUpperCase()).replace('{id}', itemId) : t('{type} {id} voltará a aparecer').replace('{type}', (type || '').toUpperCase()).replace('{id}', itemId);
                showToast(msg, 'success');

                // NOVO: Assegurar inicialização e atualizar preferências locais
                if (!ignorePreferences[titleId]) {
                    ignorePreferences[titleId] = { dlcs: {} };
                }

                if (type === 'dlc') {
                    ignorePreferences[titleId].dlcs = ignorePreferences[titleId].dlcs || {};
                    ignorePreferences[titleId].dlcs[itemId] = value;
                }

                // Recalcular badges para este jogo na biblioteca
                const game = games.find(g => g.id === titleId);
                if (game) {
                    if (type === 'dlc') {
                        if (game.dlcs) {
                            const dlc = game.dlcs.find(d => (d.app_id === itemId || d.appId === itemId));
                            if (dlc) dlc.ignored = value;
                        }
                    }

                    // Recalcular has_non_ignored_* flags
                    const gameIgnore = ignorePreferences[titleId] || {};
                    const ignoredDlcs = gameIgnore.dlcs || {};

                    let hasNonIgnoredDlcs = false;
                    if (game.has_base && game.dlcs && Array.isArray(game.dlcs)) {
                        hasNonIgnoredDlcs = game.dlcs.some(dlc => {
                            const appIdKey = typeof dlc.app_id === 'string' ? dlc.app_id : (dlc.appId || '');
                            const isIgnored = appIdKey ? (ignoredDlcs[appIdKey.toUpperCase()] || ignoredDlcs[appIdKey.toLowerCase()]) : false;
                            const isNotOwned = !dlc.owned;
                            return isNotOwned && !isIgnored;
                        });
                    }
                    game.has_non_ignored_dlcs = hasNonIgnoredDlcs;

                    // Re-renderizar biblioteca para atualizar badges e status
                    if (typeof applyFilters === 'function') {
                        applyFilters();
                    } else if (typeof renderLibrary === 'function') {
                        renderLibrary();
                    }
                }
            } else {
                showToast(t('Erro ao salvar preferência'), 'error');
            }
        },
        error: () => {
            showToast(t('Erro de conexão'), 'error');
        }
    });
}

function toggleWishlist(titleId) {
    const btn = $('#btnWishlist');
    const isCurrentlyActive = btn.hasClass('is-danger');
    if (isCurrentlyActive) {
        $.ajax({
            url: `/api/wishlist/${titleId}`,
            type: 'DELETE',
            success: () => {
                btn.removeClass('is-danger').addClass('is-light')
                    .find('i').removeClass('bi-heart-fill').addClass('bi-heart');
                showToast(t('Removed from Wishlist'));
                if (typeof loadWishlist === 'function') loadWishlist();
            }
        });
    } else {
        $.ajax({
            url: '/api/wishlist',
            type: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({ title_id: titleId }),
            success: () => {
                btn.removeClass('is-light').addClass('is-danger is-light')
                    .find('i').removeClass('bi-heart').addClass('bi-heart-fill');
                showToast(t('Added to Wishlist'), 'success');
                if (typeof loadWishlist === 'function') loadWishlist();
            }
        });
    }
}

function addTagToGame(titleId) {
    const tagId = $('#modalAddTagSelect').val();
    if (!tagId) return;
    $.ajax({
        url: `/api/titles/${titleId}/tags`,
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ tag_id: tagId }),
        success: (res) => {
            if (res.success) loadGameTagsAndWishlist(titleId);
        }
    });
}

function removeTagFromGame(titleId, tagId) {
    $.ajax({
        url: `/api/titles/${titleId}/tags/${tagId}`,
        type: 'DELETE',
        success: (res) => {
            if (res.success) loadGameTagsAndWishlist(titleId);
        }
    });
}

function editGameMetadata(titleId) {
    $.get(`/api/games/${titleId}/custom`, function (response) {
        if (response.success) {
            const d = response.data || {};
            const game = (typeof games !== 'undefined') ? games.find(g => g.id === titleId) : d;

            if (!game && !d.name) {
                showToast(t('Dados do jogo não encontrados.'), 'error');
                return;
            }

            $('#editMetaId').val(titleId);
            $('#editMetaName').val(d.name || (game ? game.name : ''));
            $('#editMetaPublisher').val(d.publisher || (game ? game.publisher : ''));
            $('#editMetaDescription').val(d.description || (game ? game.description : ''));
            $('#editMetaIcon').val(d.iconUrl || (game ? game.iconUrl : ''));
            $('#editMetaBanner').val(d.bannerUrl || (game ? game.bannerUrl : ''));
            $('#editMetaGenre').val(d.genre || (game ? (Array.isArray(game.category) ? game.category.join(', ') : game.category) : ''));
            $('#editMetaRelease').val(d.release_date || (game ? (game.release_date || game.releaseDate) : ''));

            openModal('editMetadataModal');
        }
    });
}

function saveGameMetadata() {
    const titleId = $('#editMetaId').val();

    const data = {
        name: $('#editMetaName').val(),
        publisher: $('#editMetaPublisher').val(),
        description: $('#editMetaDescription').val(),
        iconUrl: $('#editMetaIcon').val(),
        bannerUrl: $('#editMetaBanner').val(),
        genre: $('#editMetaGenre').val(),
        release_date: $('#editMetaRelease').val()
    };

    const fullDataStr = $('#editMetaFullData').val();
    if (fullDataStr) {
        try {
            const fullData = JSON.parse(fullDataStr);
            Object.keys(fullData).forEach(key => {
                if (data[key] !== undefined && data[key] !== '') {
                    fullData[key] = data[key];
                }
            });
            Object.assign(data, fullData);
        } catch (e) {
            console.error('Error parsing full metadata:', e);
        }
    }

    $('#btnSaveMetadata').addClass('is-loading');

    $.ajax({
        url: `/api/games/${titleId}/custom`,
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: function (res) {
            $('#btnSaveMetadata').removeClass('is-loading');
            if (res.success) {
                closeModal('editMetadataModal');
                showToast(t('Dados atualizados com sucesso!'));
                if (typeof refreshLibrary === 'function') refreshLibrary();
                if (typeof fillErrorsTable === 'function') fillErrorsTable();
                showGameDetails(titleId);
            } else {
                showToast(t('Erro ao salvar: ') + res.error, 'error');
            }
        },
        error: function () {
            $('#btnSaveMetadata').removeClass('is-loading');
            showToast(t('Erro de conexão ao salvar.'), 'error');
        }
    });
}

function searchTitleDB() {
    const query = $('#searchTitleDBInput').val();
    if (!query || query.length < 2) return;
    const resultsContainer = $('#titleDBSearchResults');
    resultsContainer.html(`<p class="is-size-7 p-2">${t('Buscando...')}</p>`);

    $.getJSON(`/api/titledb/search?q=${encodeURIComponent(query)}`, (results) => {
        if (!results || results.length === 0) {
            resultsContainer.html(`<p class="is-size-7 p-2">${t('Nenhum resultado.')}</p>`);
            return;
        }
        let html = '<div class="list is-hoverable">';
        results.forEach((item, index) => {
            const itemId = `titleDBResult_${index}`;
            window.__titleDBResults = window.__titleDBResults || {};
            window.__titleDBResults[itemId] = item;
            html += `
                <a class="list-item" onclick="useMetadataFromDataAttr('${itemId}')">
                    <div class="media is-align-items-center">
                        <div class="media-left">
                            <figure class="image is-32x32"><img src="${escapeHtml(item.iconUrl || '/static/img/no-icon.png')}" class="is-rounded"></figure>
                        </div>
                        <div class="media-content">
                            <p class="is-size-7 has-text-weight-bold">${escapeHtml(item.name)}</p>
                            <p class="is-size-7 opacity-50">${escapeHtml(item.id)}</p>
                        </div>
                    </div>
                </a>`;
        });
        html += '</div>';
        resultsContainer.html(html);
    });
}

function useMetadataFromDataAttr(elementId) {
    const item = window.__titleDBResults && window.__titleDBResults[elementId];
    if (!item) {
        console.error('useMetadataFromDataAttr: item not found for id:', elementId);
        return;
    }
    useMetadata(item);
}

function useMetadata(item) {
    if (!item) return;

    // Store full original data for merging during save
    $('#editMetaFullData').val(JSON.stringify(item));

    // Basic fields
    const setVal = (id, val) => {
        if (val !== undefined && val !== null) $(id).val(val);
    };

    setVal('#editMetaName', item.name);
    setVal('#editMetaPublisher', item.publisher);
    setVal('#editMetaDescription', item.description);
    setVal('#editMetaIcon', item.iconUrl || item.icon_url);
    setVal('#editMetaBanner', item.bannerUrl || item.banner_url);

    // Genre/Category handling
    const category = item.category || item.genre || [];
    setVal('#editMetaGenre', Array.isArray(category) ? category.join(', ') : category);

    // Release Date handling
    const relDate = item.releaseDate || item.release_date;
    setVal('#editMetaRelease', relDate);

    // NSUID and Size
    setVal('#editMetaNsuid', item.nsuId || item.nsuid);
    setVal('#editMetaSize', item.size);

    showToast(t('Metadados carregados! Todos os campos foram preenchidos.'), 'info');
}

// Keyboard Navigation for Game Details Modal
let currentGameId = null;
let availableGames = [];
// Screenshot Gallery State
let currentScreenshotIndex = 0;
let currentScreenshotsList = [];

window.setModalNavigationContext = function (gameId, gamesList) {
    currentGameId = gameId;
    availableGames = gamesList || [];
};

function navigateGameModal(direction) {
    if (!currentGameId || !availableGames.length) return;

    const currentIndex = availableGames.findIndex(g => g.id === currentGameId);
    if (currentIndex === -1) return;

    let newIndex = direction === 'next' ? currentIndex + 1 : currentIndex - 1;

    if (newIndex < 0) newIndex = availableGames.length - 1;
    if (newIndex >= availableGames.length) newIndex = 0;

    const newGame = availableGames[newIndex];
    if (newGame) {
        showGameDetails(newGame.id);
    }
}

// Global keyboard event handler
$(document).on('keydown', function (e) {
    // Screenshot Gallery Navigation
    if ($('#screenshotModal').hasClass('is-active')) {
        switch (e.key) {
            case 'ArrowLeft':
                e.preventDefault();
                navigateScreenshotGallery('prev');
                break;
            case 'ArrowRight':
                e.preventDefault();
                navigateScreenshotGallery('next');
                break;
            case 'Escape':
                e.preventDefault();
                closeModal('screenshotModal');
                break;
        }
        return;
    }

    if (!$('#gameDetailsModal').hasClass('is-active')) return;
    if ($(e.target).is('input, textarea')) return;

    switch (e.key) {
        case 'ArrowLeft':
        case 'ArrowUp':
            e.preventDefault();
            navigateGameModal('prev');
            break;
        case 'ArrowRight':
        case 'ArrowDown':
            e.preventDefault();
            navigateGameModal('next');
            break;
        case 'Escape':
            e.preventDefault();
            closeModal('gameDetailsModal');
            break;
        case 'e':
        case 'E':
            e.preventDefault();
            if (currentGameId) editGameMetadata(currentGameId);
            break;
        case 'f':
        case 'F':
            e.preventDefault();
            if (currentGameId) toggleWishlist(currentGameId);
            break;
    }
});

function openScreenshotGallery(index) {
    if (!currentScreenshotsList || currentScreenshotsList.length === 0) return;

    currentScreenshotIndex = index;
    if (currentScreenshotIndex < 0) currentScreenshotIndex = 0;
    if (currentScreenshotIndex >= currentScreenshotsList.length) currentScreenshotIndex = currentScreenshotsList.length - 1;

    updateScreenshotModalImage();
    openModal('screenshotModal');
}

function navigateScreenshotGallery(direction) {
    if (!currentScreenshotsList || currentScreenshotsList.length === 0) return;

    if (direction === 'next') {
        currentScreenshotIndex++;
        if (currentScreenshotIndex >= currentScreenshotsList.length) currentScreenshotIndex = 0;
    } else {
        currentScreenshotIndex--;
        if (currentScreenshotIndex < 0) currentScreenshotIndex = currentScreenshotsList.length - 1;
    }
    updateScreenshotModalImage();
}

function updateScreenshotModalImage() {
    const s = currentScreenshotsList[currentScreenshotIndex];
    const url = typeof s === 'string' ? s : (s.url || s.image);

    // Add navigation arrows to the modal if not present
    const modalContent = $('#screenshotModal .modal-content');
    if (modalContent.find('.screenshot-nav').length === 0) {
        modalContent.append(`
            <button class="button is-ghost screenshot-nav prev" style="position: absolute; left: 10px; top: 50%; transform: translateY(-50%); color: white; border: none; background: rgba(0,0,0,0.5); z-index: 10" onclick="navigateScreenshotGallery('prev')">
                <i class="bi bi-chevron-left is-size-3"></i>
            </button>
            <button class="button is-ghost screenshot-nav next" style="position: absolute; right: 10px; top: 50%; transform: translateY(-50%); color: white; border: none; background: rgba(0,0,0,0.5); z-index: 10" onclick="navigateScreenshotGallery('next')">
                <i class="bi bi-chevron-right is-size-3"></i>
            </button>
            <p class="screenshot-counter" style="position: absolute; bottom: 20px; left: 50%; transform: translateX(-50%); color: white; background: rgba(0,0,0,0.5); padding: 5px 10px; border-radius: 12px; z-index: 10"></p>
        `);
    }

    // Update counter
    modalContent.find('.screenshot-counter').text(`${currentScreenshotIndex + 1} / ${currentScreenshotsList.length}`);

    $('#screenshotModalImage').attr('src', url);
}

// Replaces original openScreenshotModal
function openScreenshotModal(url) {
    // Legacy fallback
    $('#screenshotModalImage').attr('src', url);
    openModal('screenshotModal');
}

function adjustModalForMobile(cardId) {
    const card = document.getElementById(cardId);
    if (!card) return;

    const isMobile = window.innerWidth <= 768;
    if (isMobile) {
        Object.assign(card.style, {
            width: '100%',
            maxWidth: '100%',
            height: '100%',
            maxHeight: '100%',
            borderRadius: '0',
            margin: '0',
            position: 'fixed',
            top: '0',
            left: '0'
        });
    }
}

// Initialize screenshot carousel when modal opens
$(document).on('shown.bs.modal', '#gameDetailsModal', function () {
    const viewport = document.querySelector('#gameScreenshotsCarousel .carousel-viewport');
    if (viewport) {
        viewport.scrollLeft = 0;
    }
});

function refreshSingleGameMetadata(titleId) {
    const btn = $(event.currentTarget);
    btn.addClass('is-loading');
    $.post(`/api/library/metadata/refresh/${titleId}`, (res) => {
        showToast(t('Atualização de metadados iniciada em background.'));
        // Wait a few seconds then reload modal to show new data
        setTimeout(() => {
            btn.removeClass('is-loading');
            showGameDetails(titleId);
        }, 5000);
    }).fail(() => {
        btn.removeClass('is-loading');
        showToast(t('Erro ao solicitar atualização'), 'error');
    });
}
