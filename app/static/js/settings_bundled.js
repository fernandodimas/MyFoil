console.log('MyFoil: settings.js loaded (Version: BUNDLED_FIX)');
window.DEBUG_MODE && console.log('Checking window.debounce:', typeof window.debounce);
let allUsernames = [];

// Helper functions
const getInputVal = (id) => $(`#${id}`).val();
const getCheckboxStatus = (id) => $(`#${id}`).is(":checked");
// openModal and closeModal are defined in modals_shared.html (included globally)

// --- External API Settings ---
window.saveAPISettings = function () {
    const rawg_api_key = $('#rawgApiKey').val();
    const igdb_client_id = $('#igdbClientId').val();
    const igdb_client_secret = $('#igdbClientSecret').val();
    const upcoming_days_ahead = $('#upcomingDaysAhead').val();
    $.ajax({
        url: '/api/settings/apis',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            rawg_api_key,
            igdb_client_id,
            igdb_client_secret,
            upcoming_days_ahead
        }),
        success: (res) => {
            if (res.success) {
                showToast(t('Configurações de API salvas'));
                if (typeof fillMetadataStats === 'function') fillMetadataStats();
            }
            else showToast(t('Erro ao salvar configurações'), 'error');
        },
        error: () => showToast(t('Erro de comunicação'), 'error')
    });
};

window.fillMetadataStats = function () {
    $.getJSON('/api/stats', (stats) => {
        $('#statMetadataGames').text(stats.metadata_games || 0);
        // RAWG status
        if ($('#rawgApiKey').val()) {
            $('#statusRAWG').removeClass('is-danger').addClass('is-success').text(t('Ativa'));
        } else {
            $('#statusRAWG').removeClass('is-success').addClass('is-danger').text(t('Inativa'));
        }
        // IGDB status
        if ($('#igdbClientId').val() && $('#igdbClientSecret').val()) {
            $('#statusIGDB').removeClass('is-danger').addClass('is-success').text(t('Ativa'));
        } else {
            $('#statusIGDB').removeClass('is-success').addClass('is-danger').text(t('Inativa'));
        }
    });
};

window.testRAWGConnection = function () {
    const btn = $(event.currentTarget);
    btn.addClass('is-loading');
    $.getJSON('/api/library/search-rawg?q=zelda', (res) => {
        btn.removeClass('is-loading');
        if (res && res.name) {
            showToast(t('Conexão OK! Encontrado: ') + res.name);
        } else {
            showToast(t('Nenhum resultado encontrado. Verifique sua chave.'), 'warning');
        }
    }).fail((err) => {
        btn.removeClass('is-loading');
        showToast(t('Erro ao testar conexão: ') + (err.responseJSON?.error || t('Erro desconhecido')), 'error');
    });
};

window.testIGDBConnection = function () {
    const btn = $(event.currentTarget);
    btn.addClass('is-loading');
    $.getJSON('/api/library/search-igdb?q=zelda', (res) => {
        btn.removeClass('is-loading');
        if (Array.isArray(res) && res.length > 0) {
            showToast(t('Conexão OK! Encontrado: ') + res[0].name);
        } else if (res && res.name) {
            showToast(t('Conexão OK! Encontrado: ') + res.name);
        } else {
            showToast(t('Nenhum resultado encontrado. Verifique seu ID/Secret.'), 'warning');
        }
    }).fail((err) => {
        btn.removeClass('is-loading');
        showToast(t('Erro ao testar conexão: ') + (err.responseJSON?.error || t('Erro desconhecido')), 'error');
    });
};

window.refreshAllMetadata = function () {
    confirmAction({
        title: t('Atualizar Metadados'),
        message: t('Isso buscará notas, tempo de jogo e screenshots para TODOS os itens identificados. Pode levar vários minutos. Deseja continuar?'),
        confirmText: t('Atualizar Todos'),
        confirmClass: 'is-info',
        onConfirm: () => {
            const btn = $('#btnRefreshAllMetadata');
            btn.addClass('is-loading');
            $.post('/api/library/metadata/refresh-all', (res) => {
                showToast(t('Atualização em massa iniciada em segundo plano.'));
                setTimeout(() => btn.removeClass('is-loading'), 3000);
            }).fail(() => {
                btn.removeClass('is-loading');
                showToast(t('Erro ao iniciar atualização'), 'error');
            });
        }
    });
};

function createTag() {
    const name = $('#tagNameInput').val();
    const color = $('#tagColorInput').val();
    const icon = $('#tagIconInput').val();
    if (!name) return showToast(t('Nome da tag é obrigatório'), 'error');

    $.ajax({
        url: '/api/tags',
        type: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ name, color, icon }),
        success: (res) => {
            showToast(t('Tag criada com sucesso'));
            $('#tagNameInput').val('');
            fillTagsTable();
        },
        error: (err) => showToast(t('Erro ao criar tag: ') + (err.responseJSON?.error || t('Erro desconhecido')), 'error')
    });
}

function fillTagsTable() {
    $.getJSON('/api/tags', (tags) => {
        const tbody = $('#tagsTable tbody').empty();
        tags.forEach(t => {
            const iconHtml = t.icon.startsWith('bi-') ? `<i class="bi ${t.icon} mr-1"></i>` : `<i class="fas ${t.icon} mr-1"></i>`;
            tbody.append(`
                <tr>
                    <td><strong>${escapeHtml(t.name)}</strong></td>
                    <td>
                        <span class="tag" style="background-color: ${t.color}; color: #fff;">
                            ${iconHtml} ${escapeHtml(t.name)}
                        </span>
                    </td>
                    <td class="has-text-right">
                        <button class="button is-small is-ghost has-text-danger" onclick="deleteTag(${t.id})">
                            <i class="bi bi-trash3"></i>
                        </button>
                    </td>
                </tr>
            `);
        });
    }).fail(() => debugWarn('Failed to load tags'));
}

function deleteTag(id) {
    confirmAction({
        title: t('Excluir Tag'),
        message: t('Deseja realmente excluir esta tag? Esta ação removerá a tag de todos os jogos associados.'),
        confirmText: t('Excluir'),
        confirmClass: 'is-danger',
        onConfirm: () => {
            $.ajax({
                url: `/api/tags/${id}`,
                type: 'DELETE',
                success: () => {
                    showToast(t('Tag excluída'));
                    fillTagsTable();
                },
                error: (err) => showToast(t('Erro ao excluir tag'), 'error')
            });
        }
    });
}

function fillActivityLogs() {
    $.getJSON('/api/activity', (logs) => {
        const list = $('#activityLogsList').empty();
        if (!logs.length) {
            list.append(`<p class="has-text-centered py-6 opacity-40 italic">${t('Nenhuma atividade registrada.')}</p>`);
            return;
        }
        logs.forEach(log => {
            const date = new Date(log.timestamp).toLocaleString();
            let iconClass = 'bi-info-circle';
            let color = '#7c3aed';

            if (log.action.includes('error') || log.action.includes('failed')) {
                iconClass = 'bi-exclamation-circle-fill';
                color = '#ef4444';
            } else if (log.action.includes('file_added')) {
                iconClass = 'bi-file-earmark-plus';
                color = '#10b981';
            } else if (log.action.includes('scan')) {
                iconClass = 'bi-search';
            } else if (log.action.includes('backup')) {
                iconClass = 'bi-safe';
            }

            list.append(`
                <div class="activity-item">
                    <div class="activity-dot" style="border-color: ${color}"></div>
                    <div class="activity-content">
                        <span class="activity-meta">${date}</span>
                        <p class="has-text-weight-bold mb-1">
                            <i class="bi ${iconClass} mr-2" style="color: ${color}"></i>
                            ${escapeHtml(log.action.toUpperCase().replace(/_/g, ' '))}
                        </p>
                        <div class="is-size-7 opacity-70">
                            ${log.title_id ? `<span class="tag is-info is-light is-small mr-2">${log.title_id}</span>` : ''}
                            ${escapeHtml(JSON.stringify(log.details).replace(/[{}"]/g, '').replace(/:/g, ': ').replace(/,/g, ' | '))}
                        </div>
                    </div>
                </div>
            `);
        });
    }).fail(() => debugWarn('Failed to load activity logs'));
}

// Tab Navigation Logic
$('#settingsNav a').on('click', function () {
    const target = $(this).data('target');
    $('#settingsNav a').removeClass('is-active');
    $(this).addClass('is-active');
    $('.settings-section').addClass('is-hidden');
    $(`#section-${target}`).removeClass('is-hidden');
    sessionStorage.setItem('lastSettingsTab', target);

    // Initial load for specific tabs
    if (target === 'Tags') fillTagsTable();
    if (target === 'Activity') fillActivityLogs();
    if (target === 'Library') fillLibraryTable();
});

// File Input Helper
$('#consoleKeysInput').on('change', function () {
    const file = this.files[0];
    $('#fileNameDisplay').text(file ? file.name : t("No file chosen"));
});

// Toggle Add Source Form
$('#toggleAddSource').on('click', function () {
    $('#addSourceForm').toggleClass('is-hidden');
});

// Populate Functions
function fillLibraryTable() {
    $.getJSON("/api/settings/library/paths", (result) => {
        const tbody = $('#pathsTable tbody').empty();
        if (!result.paths?.length) {
            tbody.append(`<tr><td colspan="6" class="has-text-centered py-6 opacity-40 italic">${t("No paths configured")}</td></tr>`);
        } else {
            result.paths.forEach(p => {
                tbody.append(`
                    <tr>
                        <td>
                            <p class="font-mono is-size-7 mb-0">${escapeHtml(p.path)}</p>
                        </td>
                        <td class="has-text-centered"><span class="tag is-light">${p.titles_count}</span></td>
                        <td class="has-text-centered"><span class="tag is-light">${p.files_count}</span></td>
                        <td class="has-text-centered"><span class="tag is-primary is-light font-mono">${p.total_size_formatted}</span></td>
                        <td class="has-text-centered"><span class="is-size-7 opacity-50">${p.last_scan || '--'}</span></td>
                        <td class="has-text-right">
                            <div class="buttons is-right">
                                <button class="button is-small is-ghost has-text-info" onclick="scanLibrary('${p.path}')" title="${t('Escanear esta pasta')}"><i class="bi bi-arrow-clockwise"></i></button>
                                <button class="button is-small is-ghost has-text-danger" onclick="showDeletePathModal('${p.path}')" title="${t('Remover caminho')}"><i class="bi bi-trash3"></i></button>
                            </div>
                        </td>
                    </tr>
                `);
            });
        }
    }).fail(() => debugWarn('Failed to load library paths'));
}

// Check watchdog status
function checkWatchdogStatus() {
    $.getJSON("/api/status", (status) => {
        const banner = $('#watchdogStatusBanner');
        const text = $('#watchdogStatusText');
        const headerStatus = $('#watchdogStatus');

        if (status && status.watching !== undefined) {
            banner.removeClass('is-info is-warning is-danger').addClass(status.watching ? 'is-success' : 'is-warning');
            headerStatus.find('.icon i').removeClass('bi-check-circle bi-pause-circle').addClass(status.watching ? 'bi-check-circle' : 'bi-pause-circle');
            headerStatus.find('span:last-child').text(`Watchdog: ${status.watching ? t("Monitoring") : t("Not monitoring")}`);

            const icon = status.watching ? 'bi-broadcast' : 'bi-pause-circle';
            const count = status.libraries || 0;
            const libText = count === 1 ? t("library") : t("libraries");

            text.html(`<span class="icon mr-2"><i class="bi ${icon}"></i></span>
                Watchdog: ${status.watching ? t("Monitoring") : t("Not monitoring")} | 
                ${count} ${libText}`);
        } else {
            $.getJSON("/api/settings/library/paths", (paths) => {
                const hasPaths = paths.paths && paths.paths.length > 0;
                banner.removeClass('is-info is-warning is-danger').addClass(hasPaths ? 'is-success' : 'is-warning');
                headerStatus.find('span:last-child').text(`Watchdog: ${hasPaths ? t("Monitoring") : t("No libraries configured")}`);

                const icon = hasPaths ? 'bi-broadcast' : 'bi-pause-circle';
                text.html(`<span class="icon mr-2"><i class="bi ${icon}"></i></span>
                    Watchdog: ${hasPaths ? t("Monitoring") : t("No libraries configured")}`);
            });
        }
    }).fail(() => {
        $.getJSON("/api/settings/library/paths", (paths) => {
            const hasPaths = paths.paths && paths.paths.length > 0;
            const banner = $('#watchdogStatusBanner');
            const text = $('#watchdogStatusText');
            const headerStatus = $('#watchdogStatus');

            banner.removeClass('is-info is-warning is-danger').addClass(hasPaths ? 'is-success' : 'is-warning');
            headerStatus.find('span:last-child').text(`Watchdog: ${hasPaths ? t("Monitoring") : t("No libraries configured")}`);

            const icon = hasPaths ? 'bi-broadcast' : 'bi-pause-circle';
            text.html(`<span class="icon mr-2"><i class="bi ${icon}"></i></span>
                Watchdog: ${hasPaths ? t("Monitoring") : t("No libraries configured")}`);
        });
    });
}

function fillUserTable() {
    $.getJSON("/api/users", (result) => {
        const tbody = $('#userTable tbody').empty();
        allUsernames = result.map(u => u.user);
        if (!result.length) {
            tbody.append(`<tr><td colspan="3" class="has-text-centered py-6 opacity-40 italic">${t("No users found")}</td></tr>`);
        } else {
            result.forEach(user => {
                const self = user.user === window.currentUser;
                tbody.append(`
                    <tr>
                        <td class="has-text-weight-bold">
                            <i class="bi bi-person-circle mr-2 opacity-50"></i> ${escapeHtml(user.user)} ${self ? `<span class="tag is-info is-light is-small ml-2">${t('You')}</span>` : ''}
                        </td>
                        <td>
                            <div class="tags">
                                <span class="tag ${user.shop_access ? 'is-success' : 'is-light'} is-small">${t('Shop')}</span>
                                <span class="tag ${user.backup_access ? 'is-success' : 'is-light'} is-small">${t('Backup')}</span>
                                <span class="tag ${user.admin_access ? 'is-primary' : 'is-light'} is-small">${t('Admin')}</span>
                            </div>
                        </td>
                        <td class="has-text-right">
                            ${!self ? `
                                <button class="button is-small is-ghost has-text-danger" onclick="showDeleteUserModal(${user.id}, '${user.user}')">
                                    <i class="bi bi-trash3"></i>
                                </button>
                            ` : ''}
                        </td>
                    </tr>
                `);
            });
        }
    }).fail(() => debugWarn('Failed to load users'));
}

function fillTitleDBSourcesTable() {
    $.getJSON("/api/settings/titledb/sources", (result) => {
        if (!result.success) return;
        const tbody = $('#titledbSourcesTable tbody').empty();
        if (!tbody.data('sortable-init')) {
            const sortableEl = document.getElementById('titledbSourcesTable').querySelector('tbody');
            if (sortableEl) {
                new Sortable(sortableEl, {
                    handle: '.drag-handle',
                    animation: 150,
                    onEnd: function (evt) {
                        const priorities = {};
                        $('#titledbSourcesTable tbody tr').each((index, row) => {
                            const name = $(row).find('p.has-text-weight-bold').text();
                            priorities[name] = index * 10;
                            $(row).find('input[type="number"]').val(index * 10);
                        });

                        $.ajax({
                            url: '/api/settings/titledb/sources/reorder',
                            type: 'POST',
                            contentType: 'application/json',
                            data: JSON.stringify(priorities),
                            success: function (res) {
                                if (res.success) showToast(t('Priorities updated'));
                                else showToast(t('Failed to update priorities'), 'error');
                            }
                        });
                    }
                });
                tbody.data('sortable-init', true);
            }
        }

        result.sources.forEach(source => {
            let remoteDateHtml = '';
            if (source.is_fetching) {
                remoteDateHtml = `<span class="is-size-7 italic opacity-50"><i class="bi bi-arrow-repeat spin mr-1"></i> ${t('Carregando...')}</span>`;
            } else if (source.remote_date) {
                remoteDateHtml = `<span class="is-size-7">${new Date(source.remote_date).toLocaleString()}</span>`;
            } else {
                const errorMsg = source.last_error ? `${t('Erro')}: ${source.last_error}` : t('Nenhuma data encontrada para os arquivos esperados.');
                remoteDateHtml = `<span class="is-size-7 has-text-danger italic opacity-50" title="${errorMsg}" style="cursor: help;">${t('Não encontrado')} <i class="bi bi-question-circle"></i></span>`;
            }

            const localDate = source.last_success ? new Date(source.last_success).toLocaleString() : t('Never');

            tbody.append(`
                <tr>
                    <td>
                        <div class="is-flex is-align-items-center">
                            <i class="bi ${source.source_type === 'json' ? 'bi-filetype-json' : 'bi-file-zip'} mr-2 opacity-40"></i>
                            <div>
                                <p class="has-text-weight-bold has-text-primary is-size-6 m-0">${escapeHtml(source.name)}</p>
                                <p class="is-family-monospace is-size-7 opacity-40" style="word-break: break-all;">${escapeHtml(source.base_url)}</p>
                            </div>
                        </div>
                    </td>
                    <td>
                        <div class="is-flex is-align-items-center">
                            <i class="bi bi-cloud-check mr-2 has-text-info"></i>
                            ${remoteDateHtml}
                        </div>
                    </td>
                    <td>
                        <div class="is-flex is-align-items-center">
                            <i class="bi bi-download mr-2 opacity-50"></i>
                            <span class="is-size-7">${localDate}</span>
                        </div>
                    </td>
                    <td><input type="number" class="input is-small" value="${source.priority}" style="width: 70px" onchange="updateSourcePriority('${source.name}', this.value)" /></td>
                    <td>
                        <span class="tag ${source.enabled ? 'is-success' : 'is-light'} is-small">
                            ${source.enabled ? t('Enabled') : t('Disabled')}
                        </span>
                    </td>
                    <td class="has-text-right">
                        <div class="buttons is-right">
                            <button class="button is-small is-ghost has-text-${source.enabled ? 'warning' : 'success'}" onclick="toggleSource('${source.name}', ${!source.enabled})">
                                <i class="bi bi-${source.enabled ? 'pause-fill' : 'play-fill'}"></i>
                            </button>
                            <button class="button is-small is-ghost has-text-danger" onclick="deleteSource('${source.name}')">
                                <i class="bi bi-trash3"></i>
                            </button>
                            <button class="button is-small is-ghost drag-handle" style="cursor: move">
                                <i class="bi bi-grip-vertical"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `);
        });
    }).fail(() => debugWarn('Failed to load titledb sources'));
}

function fillErrorsTable() {
    $('#bulkActionsBar').addClass('is-hidden');
    $('#selectAllErrors').prop('checked', false);

    $.getJSON("/api/files/unidentified", (result) => {
        const tbody = $('#errorsTable tbody').empty();
        if (!result || !result.length) {
            tbody.append(`<tr><td colspan="4" class="has-text-centered py-6 opacity-40 italic">${t('Nenhum erro de identificação encontrado.')}</td></tr>`);
        } else {
            result.forEach(file => {
                const isRecognitionError = file.error && file.error.includes('Banco de Dados');
                const tidMatch = isRecognitionError ? file.error.match(/\((0100[0-9A-F]+)\)/) : null;
                const tid = tidMatch ? tidMatch[1] : null;

                tbody.append(`
                    <tr>
                        <td><input type="checkbox" class="error-checkbox" data-id="${file.id}" onclick="updateBulkBar()"></td>
                        <td>
                            <p class="has-text-weight-bold is-size-7 break-word">${escapeHtml(file.filename)}</p>
                            <p class="is-family-monospace is-size-7 opacity-40 break-word">${escapeHtml(file.filepath)}</p>
                        </td>
                        <td>
                            <span class="is-size-7 ${isRecognitionError ? 'has-text-warning' : 'has-text-danger'}">
                                <i class="bi ${isRecognitionError ? 'bi-question-circle' : 'bi-exclamation-triangle'} mr-1"></i>
                                ${escapeHtml(file.error || t('Erro desconhecido'))}
                            </span>
                        </td>
                        <td class="has-text-right">
                            <div class="buttons is-right">
                                ${tid ? `
                                    <button class="button is-small is-info is-light" onclick="openEditModalFromError('${tid}')" title="${t('Identificar Manualmente')}">
                                        <i class="bi bi-pencil-square mr-1"></i> ${t('Reconhecer')}
                                    </button>
                                ` : ''}
                                <button class="button is-small is-ghost has-text-danger" onclick="deleteErrorFile(${file.id})" title="${t('Excluir Arquivo')}">
                                    <i class="bi bi-trash3"></i>
                                </button>
                            </div>
                        </td>
                    </tr>
                `);
            });
        }
    }).fail(() => debugWarn('Failed to load unidentified files'));
}

function openEditModalFromError(titleId) {
    if (!titleId) return;
    $('#editMetaId').val(titleId);
    $('#editMetaName').val(t('Unknown') + ' (' + titleId + ')');
    $('#editMetaPublisher, #editMetaDescription, #editMetaIcon, #editMetaBanner, #editMetaGenre, #editMetaRelease').val('');
    $('#titleDBSearchResults').empty();
    $('#searchTitleDBInput').val('');

    $.get(`/api/games/${titleId}/custom`, function (d) {
        if (d && !d.error) {
            if (d.name) $('#editMetaName').val(d.name);
            if (d.publisher) $('#editMetaPublisher').val(d.publisher);
            if (d.description) $('#editMetaDescription').val(d.description);
            if (d.iconUrl) $('#editMetaIcon').val(d.iconUrl);
            if (d.bannerUrl) $('#editMetaBanner').val(d.bannerUrl);
            if (d.genre || d.category) $('#editMetaGenre').val(d.genre || d.category);
            if (d.release_date || d.releaseDate) $('#editMetaRelease').val(d.release_date || d.releaseDate);
        }
    });

    openModal('editMetadataModal');
}

function deleteErrorFile(id) {
    confirmAction({
        title: t('Excluir Arquivo'),
        message: t('Deseja realmente excluir este arquivo do DISCO? Esta ação não pode ser desfeita.'),
        confirmText: t('Excluir'),
        confirmClass: 'is-danger',
        onConfirm: () => {
            $.post(`/api/files/delete/${id}`, (res) => {
                if (res.success) {
                    showToast(t('Arquivo excluído'));
                    fillErrorsTable();
                    if (currentExplorerPath !== undefined) fillFilesExplorer();
                } else {
                    showToast(t('Erro ao excluir: ') + res.error, 'error');
                }
            });
        }
    });
}

function toggleAllErrors(checkbox) {
    $('.error-checkbox').prop('checked', checkbox.checked);
    updateBulkBar();
}

function updateBulkBar() {
    const selected = $('.error-checkbox:checked').length;
    $('#selectedCountText').text(`${selected} ${selected === 1 ? t('item selecionado') : t('itens selecionados')}`);
    if (selected > 0) $('#bulkActionsBar').removeClass('is-hidden');
    else $('#bulkActionsBar').addClass('is-hidden');
}

function bulkDeleteFiles() {
    const selectedIds = $('.error-checkbox:checked').map(function () {
        return $(this).data('id');
    }).get();

    if (selectedIds.length === 0) {
        showToast(t('Nenhum arquivo selecionado'), 'error');
        return;
    }

    confirmAction({
        title: t('Excluir Arquivos'),
        message: t('Deseja realmente excluir ') + selectedIds.length + t(' arquivo(s) do DISCO? Esta ação não pode ser desfeita.'),
        confirmText: t('Excluir'),
        confirmClass: 'is-danger',
        onConfirm: () => {
            let deleted = 0;
            let errors = 0;

            selectedIds.forEach((id, index) => {
                $.post(`/api/files/delete/${id}`, (res) => {
                    if (res.success) deleted++;
                    else errors++;

                    if (index === selectedIds.length - 1) {
                        setTimeout(() => {
                            if (deleted > 0) showToast(deleted + t(' arquivo(s) excluído(s) com sucesso'));
                            if (errors > 0) showToast(errors + t(' erro(s) ao excluir'), 'error');
                            fillErrorsTable();
                        }, 500);
                    }
                }).fail(() => {
                    errors++;
                    if (index === selectedIds.length - 1) {
                        setTimeout(() => {
                            showToast(errors + t(' erro(s) ao excluir'), 'error');
                            fillErrorsTable();
                        }, 500);
                    }
                });
            });
        }
    });
}

function showDeleteUserModal(id, user) {
    $('#deleteUserModal .modal-text').text(t('Are you sure you want to delete user') + ` "${user}"? ` + t('This action cannot be undone.'));
    $('#deleteUserModal .btn-confirm').off('click').on('click', () => deleteUser(id));
    openModal('deleteUserModal');
}

function showDeletePathModal(path) {
    $('#deletePathModal .modal-text').text(t('Remove path') + ` "${path}"? ` + t('This will not delete your files.'));
    $('#deletePathModal .btn-confirm').off('click').on('click', () => deleteLibraryPath(path));
    openModal('deletePathModal');
}

function deleteUser(id) {
    $.ajax({ url: "/api/user", type: 'DELETE', data: JSON.stringify({ user_id: id }), contentType: "application/json", success: () => { fillUserTable(); closeModal('deleteUserModal'); showToast(t('User deleted')); } });
}

function deleteLibraryPath(path) {
    $.ajax({ url: "/api/settings/library/paths", type: 'DELETE', data: JSON.stringify({ path }), contentType: "application/json", success: () => { fillLibraryTable(); closeModal('deletePathModal'); showToast(t('Path removed')); } });
}

function submitNewUser() {
    const user = getInputVal("inputNewUser");
    const password = getInputVal("inputNewUserPassword");
    if (!user || !password) return showToast(t('Fill all fields'), 'error');

    $.ajax({
        url: "/api/user", type: 'POST',
        data: JSON.stringify({
            user, password,
            shop_access: getCheckboxStatus("checkboxNewUserShopAccess"),
            backup_access: getCheckboxStatus("checkboxNewUserBackupAccess"),
            admin_access: getCheckboxStatus("checkboxNewUserAdminAccess")
        }),
        contentType: "application/json",
        success: (r) => {
            if (r.success) {
                fillUserTable();
                $('#inputNewUser, #inputNewUserPassword').val('');
                showToast(t('User created successfully'));
            } else {
                showToast(r.errors?.[0]?.error || t('Failed to create user'), 'error');
            }
        }
    });
}

function submitNewLibraryPath() {
    const path = getInputVal("libraryPathInput");
    if (!path) return showToast(t('Path is required'), 'warning');
    $.ajax({
        url: "/api/settings/library/paths",
        type: 'POST',
        data: JSON.stringify({ path }),
        contentType: "application/json",
        success: (r) => {
            if (r.success) {
                fillLibraryTable();
                $('#libraryPathInput').val('');
                showToast(t('Path added'));
            } else {
                showToast(r.errors?.[0]?.error || t('Failed to add path'), 'error');
            }
        }
    });
}

function scanLibrary(path = null) {
    $('.scanBtn').addClass('is-loading');
    showToast(t('Scan started...'));
    $.ajax({
        url: '/api/library/scan',
        type: 'POST',
        data: JSON.stringify({ path }),
        contentType: "application/json",
        success: (result) => {
            $('.scanBtn').removeClass('is-loading');
            if (result.success) showToast(t('Scan triggered!'));
        }
    });
}

function loadCleanupStats() {
    $.getJSON('/api/cleanup/stats', (data) => {
        if (data.success && data.has_orphaned) {
            $('#cleanupStats').removeClass('is-hidden');
            $('#cleanupMissingFiles').text(data.missing_files);
            $('#cleanupMissingApps').text(data.missing_apps);
        } else {
            $('#cleanupStats').addClass('is-hidden');
        }
    }).fail(() => $('#cleanupStats').addClass('is-hidden'));
}

function cleanupOrphaned() {
    confirmAction({
        title: t('Limpar Registros Órfãos'),
        message: t('Isso removerá do banco de dados todos os registros de arquivos que não existem mais no disco e todos os apps marcados como owned sem arquivos associados. Esta ação não pode ser desfeita.'),
        confirmText: t('Limpar'),
        confirmClass: 'is-warning',
        onConfirm: () => {
            const btn = $('#btnCleanupOrphaned');
            btn.addClass('is-loading');
            btn.find('span:last').text(t('Limpando...'));

            $.post('/api/cleanup/orphaned', (res) => {
                btn.removeClass('is-loading');
                btn.find('span:last').text(t('Limpar Órfãos'));

                if (res.success) {
                    showToast(res.message, 'success');
                    loadCleanupStats();
                } else {
                    showToast(t('Erro: ') + (res.error || t('Desconhecido')), 'error');
                }
            }).fail((xhr) => {
                btn.removeClass('is-loading');
                btn.find('span:last').text(t('Limpar Órfãos'));
                showToast(t('Erro de comunicação: ') + (xhr.responseJSON?.error || t('Desconhecido')), 'error');
            });
        }
    });
}

function refreshTitleDBDates() {
    $.post('/api/settings/titledb/sources/refresh-dates', () => {
        showToast(t('Buscando datas remotas em segundo plano...'));
        let checks = 0;
        const interval = setInterval(() => {
            fillTitleDBSourcesTable();
            checks++;
            if (checks > 10) clearInterval(interval);
        }, 2000);
    });
}

function toggleSource(name, enabled) {
    $.ajax({ url: "/api/settings/titledb/sources", type: 'PUT', data: JSON.stringify({ name, enabled }), contentType: "application/json", success: fillTitleDBSourcesTable });
}

function updateSourcePriority(name, priority) {
    $.ajax({ url: "/api/settings/titledb/sources", type: 'PUT', data: JSON.stringify({ name, priority: parseInt(priority) }), contentType: "application/json", success: fillTitleDBSourcesTable });
}

function deleteSource(name) {
    confirmAction({
        title: t('Excluir Fonte'),
        message: t('Deseja realmente excluir a fonte ') + `"${name}"?`,
        confirmText: t('Excluir'),
        confirmClass: 'is-danger',
        onConfirm: () => {
            $.ajax({ url: "/api/settings/titledb/sources", type: 'DELETE', data: JSON.stringify({ name }), contentType: "application/json", success: () => { showToast(t('Fonte excluída')); fillTitleDBSourcesTable(); } });
        }
    });
}

function submitNewSource() {
    const name = getInputVal('inputSourceName');
    const url = getInputVal('inputSourceUrl');
    if (!name || !url) return showToast(t('Name and URL required'), 'error');

    const data = {
        name, base_url: url,
        priority: parseInt(getInputVal('inputSourcePriority')),
        source_type: $('#inputSourceType').val(),
        enabled: true
    };
    $.ajax({
        url: "/api/settings/titledb/sources", type: 'POST', data: JSON.stringify(data), contentType: "application/json",
        success: () => {
            fillTitleDBSourcesTable();
            $('#inputSourceName, #inputSourceUrl').val('');
            $('#addSourceForm').addClass('is-hidden');
            showToast(t('Source added'));
        }
    });
}

function forceTitleDBUpdate() {
    const btn = $('.updateTitleDBBtn');
    btn.addClass('is-loading');
    $.post("/api/settings/titledb/update", (r) => {
        if (r.success) showToast(t('Update started in background!'));
        else showToast(t('Update failed!'), 'error');
        setTimeout(() => { btn.removeClass('is-loading'); fillTitleDBSourcesTable(); }, 2000);
    });
}

function saveTitleDBSettings() {
    $.ajax({
        url: "/api/settings/titles", type: 'POST', data: JSON.stringify({ auto_use_latest: $('#autoUseLatest').is(':checked') }), contentType: "application/json",
        success: (r) => { if (!r.success) showToast(r.errors?.[0]?.error, 'error'); else showToast(t('Settings saved')); }
    });
}

function submitTitlesSettings() {
    const data = {
        region: $('#selectRegion').val(),
        language: $('#selectLanguage').val(),
        auto_use_latest: $('#autoUseLatest').is(':checked')
    };
    $.ajax({ url: "/api/settings/titles", type: 'POST', data: JSON.stringify(data), contentType: "application/json", success: (r) => { if (!r.success) showToast(r.errors?.[0]?.error, 'error'); else showToast(t('Settings saved')); } });

    const keysFile = $('#consoleKeysInput')[0].files[0];
    if (keysFile) {
        const formData = new FormData();
        formData.append('file', keysFile);
        showToast(t('Uploading keys...'));
        $.ajax({
            url: "/api/settings/keys", type: 'POST', data: formData, processData: false, contentType: false,
            success: (r) => {
                if (r.success) { showToast(t('Keys updated! Reloading...')); setTimeout(() => window.location.reload(), 1500); }
                else showToast(t('Invalid keys file!'), 'error');
            }
        });
    }
}

function submitShopSettings() {
    const data = {
        host: getInputVal('shopHostInput'),
        public: getCheckboxStatus('publicShopCheck'),
        public_profile: getCheckboxStatus('publicProfileCheck'),
        encrypt: getCheckboxStatus('encryptShopCheck'),
        motd: getInputVal('motdTextArea')
    };
    $.ajax({ url: "/api/settings/shop", type: 'POST', data: JSON.stringify(data), contentType: "application/json", success: () => showToast(t('Shop settings saved')) });
}

function changeLanguage(lang) {
    document.cookie = "language=" + lang + ";path=/;max-age=31536000";
    window.location.reload();
}

function connectCloud(provider) {
    $.getJSON(`/api/cloud/auth/${provider}`, (data) => { if (data.auth_url) window.open(data.auth_url, '_blank'); }).fail((err) => showToast(err.responseJSON?.error || t('Erro ao iniciar autenticação'), 'error'));
}

function fillCloudStatus() {
    $.getJSON('/api/cloud/status', (status) => {
        ['gdrive', 'dropbox'].forEach(p => {
            const box = $(`#cloud-${p}`);
            const s = status[p];
            if (s) {
                box.find('.btn-connect').prop('disabled', false).text(s.authenticated ? t('Reconectar') : t('Conectar'));
                if (s.authenticated) box.find('.cloud-status').removeClass('is-hidden');
                box.find('.btn-config-needed').addClass('is-hidden');
            } else {
                box.find('.btn-connect').addClass('is-hidden');
                box.find('.btn-config-needed').removeClass('is-hidden');
            }
        });
    });
}

function fillPluginsList() {
    $.getJSON('/api/plugins', (plugins) => {
        const container = $('#pluginsList').empty();
        if (plugins.length === 0) { container.append(`<p class="is-size-7 opacity-50 has-text-centered py-4">${t('Nenhum plugin encontrado.')}</p>`); return; }
        plugins.forEach(p => {
            const isEnabled = p.enabled !== false;
            container.append(`
                <div class="box is-shadowless border p-4 mb-3" style="border: 1px solid rgba(0,0,0,0.05);">
                    <div class="columns is-vcentered">
                        <div class="column">
                            <p class="is-size-6 has-text-weight-bold ${isEnabled ? 'has-text-primary' : 'opacity-40'} mb-1">
                                ${escapeHtml(p.name)} <span class="tag is-light is-rounded ml-2">v${p.version}</span>
                            </p>
                            <p class="is-size-7 opacity-70">${escapeHtml(p.description)}</p>
                        </div>
                        <div class="column is-narrow">
                            <div class="field">
                                <input id="plugin_${p.id}" type="checkbox" class="switch is-rounded is-primary is-small" ${isEnabled ? 'checked' : ''} onchange="togglePlugin('${p.id}', this.checked)">
                                <label for="plugin_${p.id}" class="is-size-7 has-text-weight-semibold">${isEnabled ? t('Ativo') : t('Desativado')}</label>
                            </div>
                        </div>
                    </div>
                </div>
            `);
        });
    });
}

function togglePlugin(pluginId, enabled) {
    $.ajax({
        url: '/api/plugins/toggle', type: 'POST', contentType: 'application/json', data: JSON.stringify({ id: pluginId, enabled }),
        success: (res) => { if (res.success) { showToast(t('Plugin ') + (enabled ? t('ativado') : t('desativado')) + t(' com sucesso!')); fillPluginsList(); } else showToast(t('Erro ao alterar status: ') + res.error, 'error'); },
        error: () => showToast(t('Erro de comunicação com o servidor.'), 'error')
    });
}

let allFiles = [];
let explorerLibraries = [];
let currentExplorerPath = '';

function setExplorerPath(path) {
    currentExplorerPath = path;
    renderFilesExplorer();
    updateExplorerBreadcrumb();
}

function updateExplorerBreadcrumb() {
    const breadcrumb = $('#fileExplorerBreadcrumb').empty();
    const rootLi = $(`<li class="${currentExplorerPath === '' ? 'is-active' : ''}"></li>`);
    rootLi.append($(`<a href="javascript:void(0)" onclick="setExplorerPath('')"><i class="bi bi-hdd-fill mr-1"></i> ${t('Root')}</a>`));
    breadcrumb.append(rootLi);

    if (currentExplorerPath) {
        const parts = currentExplorerPath.split('/').filter(p => p !== '');
        let acc = '';
        parts.forEach((p, i) => {
            acc += '/' + p;
            const li = $(`<li class="${i === parts.length - 1 ? 'is-active' : ''}"></li>`);
            li.append($(`<a href="javascript:void(0)" onclick="setExplorerPath('${acc}')">${p}</a>`));
            breadcrumb.append(li);
        });
    }
}

function fillFilesExplorer() {
    $.getJSON('/api/settings/library/paths', (res) => {
        explorerLibraries = res.paths || [];
        $.getJSON('/api/files/all', (files) => { allFiles = files; renderFilesExplorer(); updateExplorerBreadcrumb(); }).fail(() => $('#filesExplorerTable tbody').html(`<tr><td colspan="6" class="has-text-centered py-4 has-text-danger">${t('Erro ao carregar arquivos.')}</td></tr>`));
    });
}

function renderFilesExplorer() {
    const tbody = $('#filesExplorerTable tbody').empty();
    const search = $('#fileSearchInput').val().toLowerCase();
    const typeF = $('#fileTypeFilter').val();
    const statusF = $('#fileStatusFilter').val();

    if (search) {
        $('.breadcrumb').addClass('is-hidden');
        const filtered = allFiles.filter(f => {
            if (!f.filename.toLowerCase().includes(search) && !f.filepath.toLowerCase().includes(search)) return false;
            if (typeF && f.extension !== typeF) return false;
            if (statusF === 'identified' && !f.identified) return false;
            if (statusF === 'error' && (f.identified || !f.identification_error)) return false;
            return true;
        });
        if (filtered.length === 0) tbody.append(`<tr><td colspan="6" class="has-text-centered py-4 opacity-50">${t('Nenhum arquivo encontrado para a busca.')}</td></tr>`);
        else renderFileList(tbody, filtered, true);
        $('#filesExplorerCount').text(filtered.length + t(' arquivos encontrados'));
        return;
    }

    $('.breadcrumb').removeClass('is-hidden');
    if (currentExplorerPath === '') {
        explorerLibraries.forEach(lib => tbody.append(`<tr class="is-clickable" onclick="setExplorerPath('${lib.path}')"><td colspan="6" class="table-cell-full"><div class="folder-item"><i class="bi bi-folder-fill has-text-warning mr-2"></i><span class="has-text-weight-bold">${escapeHtml(lib.path)}</span><span class="tag is-light ml-2">${lib.files_count} ${t('arquivos')}</span></div></td></tr>`));
        $('#filesExplorerCount').text(explorerLibraries.length + t(' bibliotecas configuradas'));
    } else {
        const items = [], folders = new Set();
        allFiles.forEach(f => {
            if (f.filepath.startsWith(currentExplorerPath)) {
                let rel = f.filepath.substring(currentExplorerPath.length);
                if (rel.startsWith('/')) rel = rel.substring(1);
                if (!rel) return;
                const parts = rel.split('/');
                if (parts.length > 1) folders.add(parts[0]);
                else {
                    if (typeF && f.extension !== typeF) return;
                    if (statusF === 'identified' && !f.identified) return;
                    if (statusF === 'error' && (f.identified || !f.identification_error)) return;
                    items.push(f);
                }
            }
        });

        let par = '';
        if (!explorerLibraries.some(l => l.path === currentExplorerPath)) {
            const last = currentExplorerPath.lastIndexOf('/');
            par = last > 0 ? currentExplorerPath.substring(0, last) : '';
        }

        tbody.append(`<tr class="is-clickable" onclick="setExplorerPath('${par}')"><td colspan="6" class="table-cell-full"><div class="folder-item"><i class="bi bi-arrow-up-circle mr-2 opacity-50"></i><span class="has-text-weight-bold">..</span></div></td></tr>`);
        Array.from(folders).sort().forEach(f => tbody.append(`<tr class="is-clickable" onclick="setExplorerPath('${currentExplorerPath.endsWith('/') ? currentExplorerPath + f : currentExplorerPath + '/' + f}')"><td colspan="6" class="table-cell-full"><div class="folder-item"><i class="bi bi-folder-fill has-text-warning mr-2"></i><span class="has-text-weight-bold">${escapeHtml(f)}</span></div></td></tr>`));
        renderFileList(tbody, items, false);
        $('#filesExplorerCount').text(folders.size + t(' pastas, ') + items.length + t(' arquivos nesta pasta'));
    }
}

function renderFileList(tbody, files, showPath) {
    files.forEach(f => {
        const badge = f.identified ? `<span class="tag is-success is-light is-small"><i class="bi bi-check-circle mr-1"></i> ${t('Identificado')}</span>` : `<span class="tag is-danger is-light is-small"><i class="bi bi-x-circle mr-1"></i> ${t('Erro')}</span>`;
        const tColor = { '.nsp': 'is-info', '.nsz': 'is-primary', '.xci': 'is-warning', '.xcz': 'is-danger' }[f.extension] || 'is-light';
        const iconClass = { '.nsp': 'bi-filetype-exe', '.nsz': 'bi-file-zip', '.xci': 'bi-disc', '.xcz': 'bi-disc-fill' }[f.extension] || 'bi-file-earmark';

        const filenameCell = `
            <div class="is-flex is-align-items-center">
                <i class="bi ${iconClass} mr-2 opacity-40 is-size-5"></i>
                <div style="min-width: 0;">
                    <p class="has-text-weight-bold has-text-primary is-size-7 m-0 truncate">${escapeHtml(f.filename)}</p>
                    <p class="is-family-monospace is-size-7 opacity-40 truncate">${escapeHtml(f.filepath)}</p>
                </div>
            </div>
        `;

        const metadataCell = f.title_name ? `
            <div class="is-flex is-align-items-center">
                <i class="bi bi-link-45deg mr-2 has-text-info"></i>
                <div style="min-width: 0;">
                    <span class="has-text-weight-semibold is-size-7 truncate">${escapeHtml(f.title_name)}</span>
                    <span class="is-size-7 opacity-50 block">${f.title_id || ''}</span>
                </div>
            </div>
        ` : `
            <div class="is-flex is-align-items-center opacity-40 italic">
                <i class="bi bi-link-45deg mr-2"></i>
                <span class="is-size-7">${t('Desconhecido')}</span>
            </div>
        `;

        tbody.append(`
            <tr>
                <td>${filenameCell}</td>
                <td>${metadataCell}</td>
                <td>
                    <div class="is-flex is-align-items-center">
                        <i class="bi bi-hdd mr-2 opacity-50"></i>
                        <span class="is-size-7">${f.size_formatted}</span>
                    </div>
                </td>
                <td><span class="tag ${tColor} is-light is-small">${f.extension.toUpperCase().replace('.', '')}</span></td>
                <td>${badge}</td>
                <td class="has-text-right">
                    <div class="buttons is-right">
                        <button class="button is-small is-ghost has-text-danger" onclick="deleteErrorFile(${f.id})" title="${t('Excluir arquivo')}">
                            <i class="bi bi-trash3"></i>
                        </button>
                    </div>
                </td>
            </tr>
        `);
    });
}

// Local fallback for debounce to avoid cache/loading issues
const _debounce = (func, wait) => {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), wait);
    };
};

$(document).on('input', '#fileSearchInput', _debounce(renderFilesExplorer, 300));
$(document).on('change', '#fileTypeFilter, #fileStatusFilter', renderFilesExplorer);

function fillWebhooksList() {
    $.getJSON('/api/settings/webhooks', (ws) => {
        const c = $('#webhooksList').empty();
        if (!ws || ws.length === 0) { c.append(`<p class="is-size-7 opacity-50 has-text-centered py-4">${t('Nenhum webhook configurado.')}</p>`); return; }
        ws.forEach(w => {
            const icon = w.active ? '<i class="bi bi-check-circle-fill has-text-success mr-2"></i>' : '<i class="bi bi-x-circle-fill has-text-danger mr-2"></i>';
            c.append(`<div class="box is-shadowless border p-3 mb-2" style="border-left: 4px solid var(--color-info) !important;"><div class="columns is-vcentered is-mobile"><div class="column"><div class="is-flex is-align-items-center mb-1">${icon}<span class="tag is-small ${w.active ? 'is-success' : 'is-light'} is-light">${w.active ? t('Ativo') : t('Inativo')}</span></div><p class="is-size-7 has-text-weight-bold truncate" title="${escapeHtml(w.url)}">${escapeHtml(w.url)}</p><p class="is-size-7 opacity-50">${t('Eventos')}: ${escapeHtml(w.events.join(', '))}</p></div><div class="column is-narrow"><button class="button is-danger is-small is-light" onclick="deleteWebhook(${w.id})" title="${t('Excluir webhook')}"><i class="bi bi-trash3"></i></button></div></div></div>`);
        });
    }).fail(() => $('#webhooksList').html(`<p class="is-size-7 has-text-danger has-text-centered py-4">${t('Erro ao carregar webhooks.')}</p>`));
}

function addWebhook() {
    const url = $('#webhookUrl').val(), secret = $('#webhookSecret').val(), events = [];
    if ($('#eventLibraryUpdated').is(':checked')) events.push('library_updated');
    if (!url) return showToast(t('URL é obrigatória'), 'error');
    $.ajax({ url: "/api/settings/webhooks", type: 'POST', data: JSON.stringify({ url, secret, events }), contentType: "application/json", success: () => { showToast(t('Webhook adicionado!')); $('#webhookUrl, #webhookSecret').val(''); fillWebhooksList(); } });
}

function deleteWebhook(id) {
    confirmAction({ title: t('Excluir Webhook'), message: t('Deseja realmente excluir este webhook?'), confirmText: t('Excluir'), confirmClass: 'is-danger', onConfirm: () => $.ajax({ url: `/api/settings/webhooks/${id}`, type: 'DELETE', success: () => { showToast(t('Webhook removido')); fillWebhooksList(); } }) });
}

function loadRenamingSettings() {
    $.getJSON('/api/settings/renaming', (r) => { if (r.success && r.settings) { $('#patternBase').val(r.settings.pattern_base); $('#patternUpd').val(r.settings.pattern_upd); $('#patternDlc').val(r.settings.pattern_dlc); } });
}

function saveRenamingSettings() {
    const data = { pattern_base: $('#patternBase').val(), pattern_upd: $('#patternUpd').val(), pattern_dlc: $('#patternDlc').val(), enabled: true };
    $.ajax({ url: '/api/settings/renaming', type: 'POST', contentType: 'application/json', data: JSON.stringify(data), success: (r) => { if (r.success) showToast(t('Padrões de renomeação salvos com sucesso!')); else showToast(t('Erro ao salvar padrões.'), 'error'); } });
}

function insertTag(tag) {
    const f = document.activeElement;
    if (f && f.id.startsWith('pattern')) {
        const s = f.selectionStart, e = f.selectionEnd, v = f.value;
        f.value = v.substring(0, s) + tag + v.substring(e);
        f.focus();
        f.selectionStart = f.selectionEnd = s + tag.length;
    } else $('#patternBase').val($('#patternBase').val() + tag);
}

function previewRenaming() {
    const data = { pattern_base: $('#patternBase').val(), pattern_upd: $('#patternUpd').val(), pattern_dlc: $('#patternDlc').val() };
    $.ajax({
        url: '/api/renaming/preview', type: 'POST', contentType: 'application/json', data: JSON.stringify(data), success: (r) => {
            if (r.success) {
                let h = '';
                r.preview.forEach(p => h += `<div class="mb-2"><span class="tag is-white border mr-2">${p.type}</span><span class="has-text-grey-light strikethrough mr-2">${escapeHtml(p.original)}</span><i class="bi bi-arrow-right mr-2 opacity-50"></i><span class="has-text-success has-text-weight-bold">${escapeHtml(p.new)}</span></div>`);
                $('#previewContent').html(h || t('Nenhum arquivo encontrado para pré-visualização.'));
                $('#renamingPreview').removeClass('is-hidden');
            }
        }
    });
}

function runRenamingJob() {
    confirmAction({ title: t('Renomeação em Massa'), message: t('Isso irá renomear fisicamente os arquivos no seu disco. Tem certeza?'), confirmText: t('Iniciar Renomeação'), confirmClass: 'is-warning', onConfirm: () => { saveRenamingSettings(); $.post('/api/renaming/run', (r) => { if (r.success) showToast(t('Job de renomeação iniciado em segundo plano.')); }); } });
}

// --- Backup Management ---
function fillBackupsTable() {
    $.getJSON('/api/backup/list', (res) => {
        if (!res.success) return;
        const tbody = $('#backupsTable tbody').empty();
        res.backups.forEach(b => {
            const date = b.created.replace('T', ' ').split('.')[0];
            const size = (b.size / 1024 / 1024).toFixed(2) + ' MB';
            let typeColor = 'is-info';
            if (b.type === 'settings') typeColor = 'is-warning';
            if (b.type === 'keys') typeColor = 'is-success';

            tbody.append(`
                <tr>
                    <td class="font-mono is-size-7">${b.filename}</td>
                    <td><span class="tag ${typeColor} is-light">${b.type}</span></td>
                    <td>${size}</td>
                    <td>${date}</td>
                    <td class="has-text-right">
                        <div class="buttons is-right">
                            <a href="/api/backup/download/${b.filename}" class="button is-small is-ghost" title="Download">
                                <i class="bi bi-download"></i>
                            </a>
                            <button class="button is-small is-warning is-light" onclick="restoreBackup('${b.filename}')" title="Restaurar">
                                <i class="bi bi-arrow-counterclockwise"></i>
                            </button>
                            <button class="button is-small is-danger is-light" onclick="deleteBackup('${b.filename}')" title="Excluir">
                                <i class="bi bi-trash"></i>
                            </button>
                        </div>
                    </td>
                </tr>
            `);
        });
    });
}

function createManualBackup() {
    const btn = $('#btnCreateBackup');
    btn.addClass('is-loading');
    $.post('/api/backup/create', (res) => {
        btn.removeClass('is-loading');
        if (res.success) {
            showToast(t('Backup criado com sucesso!'));
            fillBackupsTable();
        } else {
            showToast(t('Erro ao criar backup'), 'error');
        }
    });
}

function restoreBackup(filename) {
    confirmAction({
        title: t('Restaurar Backup'),
        message: t('ATENÇÃO: Isso irá substituir o arquivo atual pelo conteúdo do backup. O sistema pode precisar ser reiniciado. Deseja continuar?'),
        confirmText: t('Restaurar Agora'),
        confirmClass: 'is-danger',
        onConfirm: () => {
            $.ajax({
                url: '/api/backup/restore',
                type: 'POST',
                contentType: 'application/json',
                data: JSON.stringify({ filename }),
                success: (res) => {
                    if (res.success) showToast(res.message, 'success');
                    else showToast(t('Erro na restauração'), 'error');
                }
            });
        }
    });
}

function deleteBackup(filename) {
    confirmAction({
        title: t('Excluir Backup'),
        message: t('Tem certeza que deseja remover permanentemente este arquivo de backup?'),
        confirmText: t('Excluir'),
        confirmClass: 'is-danger',
        onConfirm: () => {
            $.ajax({
                url: `/api/backup/${filename}`,
                type: 'DELETE',
                success: (res) => {
                    if (res.success) {
                        showToast(t('Backup excluído'));
                        fillBackupsTable();
                    }
                }
            });
        }
    });
}

$(document).ready(async () => {
    const lastTab = sessionStorage.getItem('lastSettingsTab') || 'General';
    $(`#settingsNav a[data-target="${lastTab}"]`).click();

    $('a[data-target="Renaming"]').click(() => loadRenamingSettings());
    $('a[data-target="Backups"]').click(() => fillBackupsTable());

    fillUserTable();
    fillLibraryTable();
    checkWatchdogStatus();
    loadCleanupStats();
    fillTitleDBSourcesTable();
    fillErrorsTable();
    fillFilesExplorer();
    fillWebhooksList();
    fillPluginsList();
    fillCloudStatus();
    fillBackupsTable();

    try {
        const [reg, lang, set] = await Promise.all([
            $.getJSON("/api/settings/regions").catch(e => { debugWarn("Failed to load regions"); return { regions: [] }; }),
            $.getJSON("/api/settings/languages").catch(e => { debugWarn("Failed to load languages"); return { languages: [] }; }),
            $.getJSON("/api/settings").catch(e => { throw e; }) // Critical
        ]);

        const selR = $('#selectRegion').empty();
        reg.regions.forEach(r => selR.append(new Option(r, r)));
        if (set['titles/region']) selR.val(set['titles/region']);

        const selL = $('#selectLanguage').empty();
        lang.languages.forEach(l => selL.append(new Option(l, l)));
        if (set['titles/language']) selL.val(set['titles/language']);

        $('#autoUseLatest').prop('checked', set['titles/auto_use_latest'] === true);
        $('#languageSelect').val(document.cookie.match(/language=([^;]+)/)?.[1] || 'en');
        $('#shopHostInput').val(set['shop/host']);
        $('#publicShopCheck').prop('checked', set['shop/public']);
        $('#publicProfileCheck').prop('checked', set['shop/public_profile']);
        $('#encryptShopCheck').prop('checked', set['shop/encrypt']);
        if (set['shop/motd']) $('#motdTextArea').val(set['shop/motd']);
        if (set['apis/rawg_api_key']) $('#rawgApiKey').val(set['apis/rawg_api_key']);
        if (set['apis/igdb_client_id']) $('#igdbClientId').val(set['apis/igdb_client_id']);
        if (set['apis/igdb_client_secret']) $('#igdbClientSecret').val(set['apis/igdb_client_secret']);
        if (set['apis/upcoming_days_ahead']) $('#upcomingDaysAhead').val(set['apis/upcoming_days_ahead']);
        if (typeof fillMetadataStats === 'function') fillMetadataStats();
    } catch (e) {
        console.error("Failed to load critical settings:", e);
        showToast(t('Failed to load settings from server'), 'error');
    } finally {
        $('#settingsLoading').addClass('is-hidden');
        $('#settingsContent').removeClass('is-hidden');
    }
});

$('.modal-background').on('click', function () { closeModal($(this).parent().attr('id')); });

// Metadata Fetch Logic
async function triggerMetadataFetch(force = false) {
    try {
        const response = await fetch('/api/system/metadata/fetch', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ force: force })
        });

        if (response.ok) {
            if (typeof showToast === 'function') showToast('Busca de metadados iniciada', 'success');
            else if (typeof showNotification === 'function') showNotification('Busca de metadados iniciada', 'success');

            // Refresh status after a short delay
            setTimeout(updateMetadataStatus, 2000);
        } else {
            if (typeof showToast === 'function') showToast('Falha ao iniciar busca', 'error');
        }
    } catch (error) {
        console.error('Error triggering metadata fetch:', error);
    }
}

async function updateMetadataStatus() {
    const timeEl = document.getElementById('last-metadata-fetch-time');
    if (!timeEl) return;

    try {
        const response = await fetch('/api/system/metadata/status');
        if (response.ok) {
            const data = await response.json();

            if (data.has_run && data.last_fetch) {
                const last = data.last_fetch;
                const date = new Date(last.started_at).toLocaleString();
                let statusHtml = `<strong>${date}</strong><br>`;

                if (last.status === 'running') {
                    statusHtml += '<span class="has-text-info">Em execução...</span>';
                } else if (last.status === 'completed') {
                    statusHtml += `<span class="has-text-success">Sucesso: ${last.updated} atualizados / ${last.processed} total</span>`;
                } else {
                    statusHtml += '<span class="has-text-danger">Falha na última execução</span>';
                }

                timeEl.innerHTML = statusHtml;
            }
        }
    } catch (error) {
        console.error('Error updating metadata status:', error);
    }
}

// Initialize metadata status check
$(document).ready(function () {
    if (document.getElementById('metadata-fetch-status-container')) {
        updateMetadataStatus();
        // Periodically refresh if on the page
        setInterval(updateMetadataStatus, 60000);
    }
});
