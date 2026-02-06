/**
 * API Tokens Manager
 * Handles frontend logic for managing API tokens in Settings
 */

const tokensManager = {
    init: function () {
        // Only load if on settings page and user is admin
        const tokensSection = document.getElementById('section-ApiTokens');
        if (tokensSection) {
            this.loadTokens();

            // Add event listener to refresh when checking tab
            document.querySelectorAll('.menu-list a').forEach(el => {
                el.addEventListener('click', (e) => {
                    if (e.currentTarget.getAttribute('data-target') === 'ApiTokens') {
                        this.loadTokens();
                    }
                });
            });
        }
    },

    loadTokens: async function () {
        const tbody = document.getElementById('tokensTableBody');
        if (!tbody) return;

        tbody.innerHTML = '<tr><td colspan="5" class="has-text-centered"><i class="fas fa-spinner fa-spin"></i> Carregando...</td></tr>';

        try {
            const response = await window.safeFetch('/api/settings/tokens');
            const tokens = await response.json();

            if (tokens.length === 0) {
                tbody.innerHTML = '<tr><td colspan="5" class="has-text-centered has-text-grey">Nenhum token encontrado.</td></tr>';
                return;
            }

            tbody.innerHTML = tokens.map(t => `
                <tr>
                    <td><strong>${this.escape(t.name)}</strong></td>
                    <td><code class="is-size-7">${t.prefix}</code></td>
                    <td class="is-size-7">${t.created_at}</td>
                    <td class="is-size-7">${t.last_used || 'Nunca'}</td>
                    <td class="has-text-right">
                        <button class="button is-small is-danger is-light" onclick="tokensManager.deleteToken(${t.id})">
                            <i class="bi bi-trash"></i>
                        </button>
                    </td>
                </tr>
            `).join('');
        } catch (error) {
            console.error('Error loading tokens:', error);
            tbody.innerHTML = `<tr><td colspan="5" class="has-text-danger">Erro ao carregar tokens: ${error.message}</td></tr>`;
        }
    },

    openCreateModal: function () {
        document.getElementById('newTokenName').value = '';
        document.getElementById('generatedTokenContainer').classList.add('is-hidden');
        document.getElementById('btnGenerateToken').disabled = false;
        document.getElementById('createTokenModal').classList.add('is-active');
        document.getElementById('newTokenName').focus();
    },

    closeCreateModal: function () {
        document.getElementById('createTokenModal').classList.remove('is-active');
        this.loadTokens(); // Refresh list
    },

    generateToken: async function () {
        const nameInput = document.getElementById('newTokenName');
        const name = nameInput.value.trim();

        if (!name) {
            alert('Por favor, digite um nome para o token.');
            nameInput.focus();
            return;
        }

        const btn = document.getElementById('btnGenerateToken');
        btn.classList.add('is-loading');

        try {
            const response = await window.safeFetch('/api/settings/tokens', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ name: name })
            });

            const result = await response.json();

            if (result.success) {
                document.getElementById('generatedTokenValue').value = result.token;
                document.getElementById('generatedTokenContainer').classList.remove('is-hidden');
                btn.disabled = true;
                // Don't close immediately, let user copy
            } else {
                alert('Erro ao gerar token: ' + (result.error || 'Erro desconhecido'));
            }
        } catch (error) {
            console.error('Error generating token:', error);
            alert('Erro ao gerar token: ' + error.message);
        } finally {
            btn.classList.remove('is-loading');
        }
    },

    deleteToken: async function (id) {
        if (!confirm('Tem certeza que deseja revogar este token? Aplicações usando ele perderão acesso.')) {
            return;
        }

        try {
            const response = await window.safeFetch(`/api/settings/tokens/${id}`, {
                method: 'DELETE'
            });

            const result = await response.json();

            if (result.success) {
                this.loadTokens();
            } else {
                alert('Erro ao apagar token: ' + (result.error || 'Erro desconhecido'));
            }
        } catch (error) {
            console.error('Error deleting token:', error);
        }
    },

    copyToken: function () {
        const tokenInput = document.getElementById('generatedTokenValue');
        tokenInput.select();
        document.execCommand('copy'); // Fallback

        if (navigator.clipboard) {
            navigator.clipboard.writeText(tokenInput.value).then(() => {
                const btn = document.querySelector('#generatedTokenContainer .button.is-info');
                const originalIcon = btn.innerHTML;
                btn.innerHTML = '<i class="bi bi-check"></i>';
                setTimeout(() => btn.innerHTML = originalIcon, 2000);
            });
        }
    },

    escape: function (str) {
        if (!str) return '';
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }
};

// Initialize on load
document.addEventListener('DOMContentLoaded', () => {
    tokensManager.init();
});
