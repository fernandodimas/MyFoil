/**
 * MyFoil Stats Dashboard Logic
 */

let genreChart = null;

$(document).ready(() => {
    loadStats(true); // Initial load with library list population
});

function loadStats(initFilter = false) {
    const libId = $('#libraryFilter').val();
    const url = `/api/stats/overview${libId ? '?library_id=' + libId : ''}`;

    $.getJSON(url, (data) => {
        if (initFilter) {
            populateLibraryFilter(data.libraries || []);
        }

        // Fill quick cards
        $('#stat-total-games').text(data.library.total_titles || 0);
        $('#stat-total-files-top').text((data.identification.total_files || 0) + ' ' + t('Arquivos'));
        $('#stat-total-size').text(data.library.total_size_formatted || '0 B');

        // Breakdown
        $('#stat-total-bases').text(data.library.total_bases || 0);
        $('#stat-total-updates').text(data.library.total_updates || 0);
        $('#stat-total-dlcs').text(data.library.total_dlcs || 0);

        $('#stat-up-to-date-pct').text((data.library.completion_rate || 0) + '%');
        $('#stat-up-to-date-count').text((data.library.up_to_date || 0) + ' ' + t('atualizados'));
        $('#stat-pending-count').text(data.library.pending || 0);

        $('#stat-coverage-pct').text((data.titledb.coverage_pct || 0) + '%');
        $('#stat-source-name').text(data.titledb.source_name || '--');
        $('#stat-total-available').text((data.titledb.total_available || 0).toLocaleString());

        // Identification Stats
        $('#stat-id-rate').text(data.identification.identified_pct || 0);
        $('#stat-recognition-pct').text(data.identification.recognition_pct || 0);
        $('#stat-unidentified-files').text(data.identification.unidentified_count || 0);
        $('#stat-unrecognized-count').text(data.identification.unrecognized_count || 0);

        // Render Genre Chart
        renderGenreChart(data.genres || {});

        // Render Recent Games
        renderRecentGames(data.recent || []);
    });
}

function populateLibraryFilter(libs) {
    const select = $('#libraryFilter');
    if (!select.length) return;

    // Clear except first option
    select.find('option:not(:first)').remove();

    libs.forEach(lib => {
        select.append(`<option value="${lib.id}">${escapeHtml(lib.path)}</option>`);
    });
}

function renderGenreChart(genreData) {
    const chartCanvas = document.getElementById('genreChart');
    if (!chartCanvas) return;

    if (genreChart) {
        genreChart.destroy();
    }

    const ctx = chartCanvas.getContext('2d');
    const labels = Object.keys(genreData);
    const values = Object.values(genreData);

    genreChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: t('Jogos por Gênero'),
                data: values,
                backgroundColor: 'rgba(124, 58, 237, 0.7)',
                borderColor: '#7c3aed',
                borderWidth: 1,
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            indexAxis: 'y',
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: { grid: { display: false } },
                y: { grid: { display: false } }
            }
        }
    });
}

function renderRecentGames(games) {
    const container = $('#recentGamesList');
    if (!container.length) return;

    container.empty();
    if (!games.length) {
        container.append(`<div class="column is-12 has-text-centered py-6 opacity-40">${t('Nenhum jogo encontrado.')}</div>`);
        return;
    }

    games.forEach(game => {
        const safeName = escapeHtml(game.name);
        container.append(`
            <div class="column is-3-tablet is-2-desktop">
                <div class="card box p-0 shadow-sm border-none overflow-hidden h-100 hover-scale" style="cursor: pointer;" onclick="showGameDetails('${game.id}')">
                    <figure class="image is-square">
                        <img src="${game.iconUrl || '/static/img/no-icon.png'}" style="object-fit: cover;" alt="${safeName}">
                    </figure>
                    <div class="p-3">
                        <p class="is-size-7 has-text-weight-bold line-clamp-2" title="${safeName}">${safeName}</p>
                        <p class="is-size-7 opacity-50 font-mono">${escapeHtml(game.id)}</p>
                    </div>
                </div>
            </div>
        `);
    });
}
