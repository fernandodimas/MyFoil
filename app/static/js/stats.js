/**
 * MyFoil Stats Dashboard Logic
 */

let genreChart = null;

// Normalize envelope-style API responses: { code, success, data } or direct payload
const unwrap = (res) => {
    try {
        if (res && res.data !== undefined) return res.data;
    } catch (e) {
        // ignore
    }
    return res;
}

$(document).ready(() => {
    loadStats(true); // Initial load with library list population
});

function loadStats(initFilter = false) {
    const libId = $('#libraryFilter').val();
    const url = `/api/stats/overview${libId ? '?library_id=' + libId : ''}`;

    $.getJSON(url, (raw) => {
        const data = unwrap(raw) || {};
        if (initFilter) {
            populateLibraryFilter(data.libraries || []);
        }

        // Safe accessor helpers
        const lib = data.library || {};
        const id = data.identification || {};
        const tdb = data.titledb || {};

        // Fill quick cards
        $('#stat-total-games').text(lib.total_titles || 0);
        $('#stat-total-files-top').text((id.total_files || 0) + ' ' + t('common.files'));
        $('#stat-total-size').text(lib.total_size_formatted || '0 B');

        // Breakdown
        $('#stat-total-bases').text(lib.total_bases || 0);
        $('#stat-total-updates').text(lib.total_updates || 0);
        $('#stat-total-dlcs').text(lib.total_dlcs || 0);

        $('#stat-up-to-date-pct').text((lib.completion_rate || 0) + '%');
        $('#stat-up-to-date-count').text((lib.up_to_date || 0) + ' ' + t('common.updated_plural'));
        $('#stat-pending-count').text(lib.pending || 0);

        $('#stat-coverage-pct').text((tdb.coverage_pct || 0) + '%');
        $('#stat-source-name').text(tdb.source_name || '--');
        $('#stat-total-available').text((tdb.total_available || 0).toLocaleString());

        // Identification Stats
        $('#stat-id-rate').text(id.identified_pct || 0);
        $('#stat-recognition-pct').text(id.recognition_pct || 0);
        $('#stat-unidentified-files').text(id.unidentified_count || 0);
        $('#stat-unrecognized-count').text(id.unrecognized_count || 0);

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
    const total = values.reduce((sum, val) => sum + val, 0);

    genreChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: t('stats.games_by_genre'),
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
                legend: { display: false },
                tooltip: {
                    callbacks: {
                        label: function (tooltipItem) {
                            const count = tooltipItem.raw;
                            const pct = total > 0 ? ((count / total) * 100).toFixed(1) : 0;
                            return `${tooltipItem.label}: ${count} ${t('common.files')} (${pct}%)`;
                        }
                    }
                }
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
        container.append(`<div class="column is-12 has-text-centered py-6 opacity-40">${t('stats.no_games_found')}</div>`);
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
