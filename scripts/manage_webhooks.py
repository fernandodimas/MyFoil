#!/usr/bin/env python3
"""
Webhook Manager - Gerencia webhooks que podem estar causando polling excessivo

Requisições curl a cada 30s podem ser de webhooks configurados.
Este script permite verificar e desativar webhooks suspeitos.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from utils import now_utc


def list_webhooks(app):
    """Lista todos os webhooks configurados"""
    from db import Webhook

    with app.app_context():
        webhooks = Webhook.query.all()

        print("=" * 80)
        print("WEBHOOKS CONFIGURADOS")
        print("=" * 80)
        print()

        if not webhooks:
            print("✓ Nenhum webhook configurado")
            print()
            print("As requisições curl podem ser de:")
            print("  - Processo externo (Tinfoil, etc)")
            print("  - Outro serviço fazendo polling")
            print("  - Navegador com extensão")
            return

        print(f"Encontrados {len(webhooks)} webhooks:")
        print()

        for webhook in webhooks:
            print(f"[{webhook.id}] Webhook:")
            print(f"  URL: {webhook.url}")
            print(f"  Ativo: {webhook.active}")
            print(f"  Eventos: {webhook.events}")
            print(f"  Secret: {'Configurado' if webhook.secret else 'Nenhum'}")
            print()


def deactivate_all_webhooks(app):
    """Desativa todos os webhooks"""
    from db import Webhook, db

    with app.app_context():
        webhooks = Webhook.query.filter_by(active=True).all()

        if not webhooks:
            print("✓ Nenhum webhook ativo para desativar")
            return

        print(f"Desativando {len(webhooks)} webhooks...")

        for webhook in webhooks:
            webhook.active = False

        db.session.commit()
        print(f"✓ {len(webhooks)} webhooks desativados")


def delete_webhooks_by_url_pattern(app, pattern):
    """Deleta webhooks com URL contendo padrão específico"""
    from db import Webhook, db

    with app.app_context():
        webhooks = Webhook.query.filter(Webhook.url.like(f"%{pattern}%")).all()

        if not webhooks:
            print(f"✓ Nenhum webhook encontrado com padrão '{pattern}'")
            return

        print(f"Deletando {len(webhooks)} webhooks...")

        for webhook in webhooks:
            print(f"  - ID {webhook.id}: {webhook.url}")
            db.session.delete(webhook)

        db.session.commit()
        print(f"✓ {len(webhooks)} webhooks deletados")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Gerencia Webhooks")
    parser.add_argument("--list", action="store_true", help="Lista todos os webhooks")
    parser.add_argument("--deactivate-all", action="store_true", help="Desativa todos os webhooks ativos")
    parser.add_argument("--delete-pattern", type=str, help="Deleta webhooks com URL contendo padrão")

    args = parser.parse_args()

    from app import create_app

    app = create_app()

    if not any([args.list, args.deactivate_all, args.delete_pattern]):
        # Default: list webhooks
        list_webhooks(app)
    else:
        if args.list:
            list_webhooks(app)

        if args.deactivate_all:
            deactivate_all_webhooks(app)

        if args.delete_pattern:
            delete_webhooks_by_url_pattern(app, args.delete_pattern)


if __name__ == "__main__":
    main()
