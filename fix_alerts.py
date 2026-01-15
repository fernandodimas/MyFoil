import os
import re

def replace_confirm_alert(file_path):
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Generic Replacement for confirm in common patterns
    def replace_confirm(match):
        message = match.group(1)
        # This is tricky because confirm is often inside a if
        return match.group(0)

    # Manual replacements for known cases
    # Settings: deleteTag
    content = content.replace(
        "if (!confirm('Excluir esta tag?')) return;",
        "confirmAction({ title: 'Excluir Tag', message: 'Excluir esta tag?', confirmClass: 'is-danger', onConfirm: () => {"
    )
    # Settings: deleteErrorFile
    content = content.replace(
        "if (!confirm('Deseja realmente excluir este arquivo do DISCO?')) return;",
        "confirmAction({ title: 'Excluir Arquivo', message: 'Deseja realmente excluir este arquivo do DISCO?', confirmClass: 'is-danger', onConfirm: () => {"
    )
    # Settings: bulkDeleteFiles
    content = content.replace(
        "if (!confirm(`Deseja realmente excluir ${selectedIds.length} arquivo(s) do DISCO? Esta ação não pode ser desfeita.`)) {\n            return;\n        }",
        "confirmAction({ title: 'Exclusão em Massa', message: `Deseja realmente excluir ${selectedIds.length} arquivo(s) do DISCO?`, confirmClass: 'is-danger', onConfirm: () => {"
    )
    # Settings: deleteSource
    content = content.replace(
        "if (confirm(`Delete source ${name}?`)) $.ajax({",
        "confirmAction({ title: 'Delete Source', message: `Delete source ${name}?`, confirmClass: 'is-danger', onConfirm: () => $.ajax({"
    )
    # Settings: deleteWebhook
    content = content.replace(
        "if (!confirm('Deseja realmente excluir este webhook?')) return;",
        "confirmAction({ title: 'Excluir Webhook', message: 'Deseja realmente excluir este webhook?', confirmClass: 'is-danger', onConfirm: () => {"
    )
    # Settings: runRenamingJob
    content = content.replace(
        "if (!confirm('Isso irá renomear fisicamente os arquivos no seu disco. Tem certeza?')) return;",
        "confirmAction({ title: 'Renomear Arquivos', message: 'Isso irá renomear fisicamente os arquivos no seu disco. Tem certeza?', confirmClass: 'is-warning', onConfirm: () => {"
    )
    
    # Needs to add closing braces for onConfirm
    # This script is risky if not precise. Let's do it better.

if __name__ == "__main__":
    pass
