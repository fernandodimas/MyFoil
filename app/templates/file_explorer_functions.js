
// File Explorer Functions
let allFiles = [];
let filteredFiles = [];

function fillFilesExplorer() {
    $.getJSON('/api/files/all', (files) => {
        console.log('Files loaded:', files.length);
        allFiles = files;
        applyFileFilters();
    }).fail((xhr, status, error) => {
        console.error('Error loading files:', error);
        $('#filesExplorerTable tbody').html('<tr><td colspan="6" class="has-text-centered py-4 has-text-danger">Erro ao carregar arquivos. Verifique o console.</td></tr>');
    });
}

function applyFileFilters() {
    const searchTerm = $('#fileSearchInput').val().toLowerCase();
    const typeFilter = $('#fileTypeFilter').val();
    const statusFilter = $('#fileStatusFilter').val();

    filteredFiles = allFiles.filter(f => {
        // Search filter
        if (searchTerm && !f.filename.toLowerCase().includes(searchTerm) && !f.filepath.toLowerCase().includes(searchTerm)) {
            return false;
        }

        // Type filter
        if (typeFilter && f.extension !== typeFilter) {
            return false;
        }

        // Status filter
        if (statusFilter === 'identified' && !f.identified) {
            return false;
        }
        if (statusFilter === 'error' && (f.identified || !f.identification_error)) {
            return false;
        }

        return true;
    });

    renderFilesExplorer();
}

function renderFilesExplorer() {
    const tbody = $('#filesExplorerTable tbody').empty();

    if (filteredFiles.length === 0) {
        tbody.append('<tr><td colspan="6" class="has-text-centered py-4 opacity-50">Nenhum arquivo encontrado.</td></tr>');
        $('#filesExplorerCount').text('0 arquivos encontrados');
        return;
    }

    filteredFiles.forEach(f => {
        const statusBadge = f.identified
            ? '<span class="tag is-success is-light is-small"><i class="bi bi-check-circle mr-1"></i> Identificado</span>'
            : '<span class="tag is-danger is-light is-small"><i class="bi bi-x-circle mr-1"></i> Erro</span>';

        const typeColor = {
            '.nsp': 'is-info',
            '.nsz': 'is-primary',
            '.xci': 'is-warning',
            '.xcz': 'is-danger'
        }[f.extension] || 'is-light';

        tbody.append(`
                <tr>
                    <td class="truncate" style="max-width: 300px;" title="${f.filename}">
                        <i class="bi bi-file-earmark mr-1 opacity-50"></i>
                        <span class="has-text-weight-bold">${f.filename}</span>
                        ${f.title_name ? `<br><span class="is-size-7 opacity-50">${f.title_name}</span>` : ''}
                    </td>
                    <td class="truncate is-family-monospace is-size-7 opacity-70" style="max-width: 400px;" title="${f.filepath}">
                        ${f.filepath}
                    </td>
                    <td class="has-text-right is-family-monospace">${f.size_formatted}</td>
                    <td>
                        <span class="tag ${typeColor} is-light is-small">${f.extension.toUpperCase().replace('.', '')}</span>
                    </td>
                    <td class="has-text-centered">${statusBadge}</td>
                    <td class="has-text-right">
                        <button class="button is-ghost is-small has-text-danger" onclick="deleteErrorFile(${f.id})" title="Excluir arquivo">
                            <i class="bi bi-trash3"></i>
                        </button>
                    </td>
                </tr>
            `);
    });

    $('#filesExplorerCount').text(`${filteredFiles.length} arquivo${filteredFiles.length !== 1 ? 's' : ''} encontrado${filteredFiles.length !== 1 ? 's' : ''}`);
}

// Attach filter events
$(document).on('input', '#fileSearchInput', applyFileFilters);
$(document).on('change', '#fileTypeFilter, #fileStatusFilter', applyFileFilters);
