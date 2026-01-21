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
    // Check every 10 seconds
    setInterval(checkProcessStatus, 10000);
});

function checkProcessStatus() {
    $.getJSON('/api/status', function (data) {
        const indicator = $('#processIndicator');
        const text = $('#processText');
        if (!indicator.length || !text.length) return;

        if (data.scanning || data.updating_titledb) {
            indicator.removeClass('is-hidden');
            if (data.updating_titledb) {
                text.text(t('Atualizando TitleDB...'));
            } else if (data.scanning) {
                text.text(t('Escaneando Biblioteca...'));
            }
        } else {
            indicator.addClass('is-hidden');
        }
    });
}
