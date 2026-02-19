/**
 * MyFoil Navbar Logic
 * Handles the mobile burger menu and process status polling.
 */

document.addEventListener('DOMContentLoaded', () => {
    // Navbar Burger Logic
    const $navbarBurgers = Array.prototype.slice.call(document.querySelectorAll('.navbar-burger'), 0);
    if ($navbarBurgers.length > 0) {
        $navbarBurgers.forEach(el => {
            el.addEventListener('click', () => {
                const target = el.dataset.target;
                const $target = document.getElementById(target);
                el.classList.toggle('is-active');
                if ($target) $target.classList.toggle('is-active');
            });
        });
    }

    // Initial check for process status
    checkProcessStatus();
    // Check every 30 seconds (increased from 10s for resource efficiency)
    // Skip if tab is not visible
    setInterval(() => {
        if (document.visibilityState === 'visible') {
            checkProcessStatus();
        }
    }, 30000);
});

function checkProcessStatus() {
    $.getJSON('/api/status', function (data) {
        const indicator = $('#systemStatusIndicator');
        const text = $('#statusText');
        const icon = $('#statusIcon');

        if (!indicator.length || !text.length) return;

        if (data.scanning || data.updating_titledb || data.fetching_metadata) {
            indicator.addClass('is-active');
            if (data.updating_titledb) {
                text.text(t('Atualizando TitleDB...'));
                icon.html('<i class="bi bi-arrow-repeat spin has-text-primary"></i>');
            } else if (data.scanning) {
                text.text(t('Escaneando Biblioteca...'));
                icon.html('<i class="bi bi-arrow-repeat spin has-text-info"></i>');
            } else if (data.fetching_metadata) {
                text.text(t('Buscando Metadados...'));
                icon.html('<i class="bi bi-stars spin has-text-warning"></i>');
            }
        } else {
            indicator.removeClass('is-active');
            text.text(t('status.system_idle'));
            icon.html('<i class="bi bi-check-circle has-text-success"></i>');
        }
    });
}
