/**
 * Upcoming Games - JS for MyFoil
 */

document.addEventListener('DOMContentLoaded', function () {
    loadUpcomingGames();
});

async function loadUpcomingGames() {
    const grid = document.getElementById('upcomingGrid');
    const loading = document.getElementById('upcomingLoading');
    const empty = document.getElementById('upcomingEmpty');
    const apiMessage = document.getElementById('apiMessage');
    const apiMessageText = document.getElementById('apiMessageText');

    try {
        const response = await fetch('/api/upcoming');
        const data = await response.json();

        loading.classList.add('is-hidden');

        if (response.status === 400) {
            apiMessage.classList.remove('is-hidden');
            apiMessageText.innerText = data.message || 'Erro ao configurar API.';
            return;
        }

        if (!data.games || data.games.length === 0) {
            empty.classList.remove('is-hidden');
            return;
        }

        renderUpcomingGrid(data.games);
    } catch (error) {
        console.error('Error fetching upcoming games:', error);
        loading.classList.add('is-hidden');
        empty.classList.remove('is-hidden');
    }
}

function renderUpcomingGrid(games) {
    const grid = document.getElementById('upcomingGrid');
    grid.innerHTML = '';

    games.forEach(game => {
        const col = document.createElement('div');
        col.className = 'column is-3-desktop is-4-tablet is-6-mobile';

        const genres = (game.genres || []).map(g => `<span class="tag is-dark is-light is-size-7 mr-1 mb-1">${g.name}</span>`).join('');

        col.innerHTML = `
            <div class="card box p-0 shadow-sm border-none bg-glass upcoming-card">
                <div class="card-image">
                    <figure class="image is-3by4">
                        <img src="${game.cover_url}" alt="${game.name}" style="object-fit: cover; border-radius: 8px 8px 0 0;">
                    </figure>
                    <div class="date-badge">
                        <i class="bi bi-calendar-check mr-1"></i> ${game.release_date_formatted}
                    </div>
                </div>
                <div class="card-content p-4">
                    <h3 class="title is-6 mb-2 has-text-weight-bold" title="${game.name}">${game.name}</h3>
                    <div class="mb-3">
                        ${genres}
                    </div>
                    <p class="summary-text opacity-70 mb-4">
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
        grid.appendChild(col);
    });
}

/**
 * Placeholder for adding to wishlist by name
 * In a real implementation, this would search and add by TitleID
 */
function addToWishlistByName(name) {
    // Navigate to wishlist and open modal with search query
    window.location.href = `/wishlist?search=${encodeURIComponent(name)}`;
}
