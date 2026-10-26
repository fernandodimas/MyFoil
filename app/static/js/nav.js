/**
 * MyFoil Navbar Logic
 * Handles the mobile burger menu.
 * Process status updates are managed by SystemStatusManager (system_status.js / core.js).
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
});
