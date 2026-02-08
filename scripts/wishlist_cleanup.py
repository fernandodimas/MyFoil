#!/usr/bin/env python3
"""
Wishlist Cleanup - Remove itens problemáticos da wishlist manualmente

Script para remover itens da wishlist quando a UI não funciona.
Verifica e remove dependências problemáticas antes de deletar.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "app"))

from utils import now_utc


def list_wishlist_items(app):
    """Lista todos os itens na wishlist"""
    from db import Wishlist, User

    with app.app_context():
        users = User.query.all()

        print("=" * 80)
        print("WISHLIST ITEMS")
        print("=" * 80)
        print()

        total_items = 0
        for user in users:
            items = Wishlist.query.filter_by(user_id=user.id).all()
            if items:
                print(f"Usuário {user.username} (ID: {user.id}):")
                for item in items:
                    total_items += 1
                    print(f"  [{item.id}] {item.name or item.title_id}")
                    print(f"      title_id: {item.title_id}")
                    print(f"      prioridade: {item.priority}")
                    print()

        if total_items == 0:
            print("✓ Wishlist vazia")

        print(f"Total de itens: {total_items}")
        print()


def add_wishlist_item_manually(app, title_id, user_id, name=None):
    """Adiciona item à wishlist manualmente"""
    from db import Wishlist, db, User

    with app.app_context():
        user = User.query.get(user_id)
        if not user:
            print(f"✗ Usuário {user_id} não encontrado")
            return False

        # Verificar se já existe
        existing = Wishlist.query.filter_by(user_id=user_id, title_id=title_id).first()
        if existing:
            print(f"✗ Item já existe na wishlist (ID: {existing.id})")
            return False

        item = Wishlist(user_id=user_id, title_id=title_id, name=name or title_id, priority=0)

        db.session.add(item)
        db.session.commit()

        print(f"✓ Item adicionado à wishlist (ID: {item.id})")
        return True


def remove_wishlist_item_app_id(app, item_id, force=False):
    """Remove item da wishlist pelo ID usando SQLAlchemy direto"""
    from db import Wishlist, db

    with app.app_context():
        item = Wishlist.query.get(item_id)

        if not item:
            print(f"✗ Item não encontrado (ID: {item_id})")
            return False

        item_id_str = str(item_id)
        title_id = item.title_id
        user_id = item.user_id

        print(f"Removendo item da wishlist:")
        print(f"  ID: {item_id}")
        print(f"  title_id: {title_id}")
        print(f"  user_id: {user_id}")
        print(f"  nome: {item.name or 'N/A'}")
        print()

        # Verificar se há dependências
        # (Wishlist não tem dependências complexas, mas vamos ser cuidadosos)

        try:
            # Usamos session.delete() em vez de ORM para evitar issues
            db.session.execute(db.text(f"DELETE FROM wishlist WHERE id = {item_id_str}"))
            db.session.commit()

            print(f"✓ Item {item_id} removido da wishlist")
            return True

        except Exception as e:
            db.session.rollback()
            print(f"✗ Erro ao remover item: {e}")
            import traceback

            traceback.print_exc()
            return False


def cleanup_orphaned_wishlist_items(app):
    """Remove itens da wishlist sem usuário válido"""
    from db import Wishlist, User, db

    with app.app_context():
        # Encontrar itens com user_id não existe (orphans)
        orphaned = db.session.execute(
            db.text("""
                    SELECT w.id, w.title_id, w.name
                    FROM wishlist w
                    LEFT JOIN user u ON w.user_id = u.id
                    WHERE u.id IS NULL
                """)
        ).fetchall()

        if not orphaned:
            print("✓ Nenhum item orphan encontrado")
            return

        print(f"Encontrados {len(orphaned)} itens orphan:")
        for item in orphaned:
            print(f"  - ID {item[0]}: {item[2] or item[1]}")

        print()

        # Remover orphans
        try:
            db.session.execute(
                db.text("""
                    DELETE FROM wishlist
                    WHERE user_id NOT IN (SELECT id FROM user)
                """)
            )
            db.session.commit()
            print(f"✓ {len(orphaned)} itens orphan removidos")

        except Exception as e:
            db.session.rollback()
            print(f"✗ Erro ao remover orphans: {e}")


def main():
    import argparse

    parser = argparse.ArgumentParser(description="Wishlist management")
    parser.add_argument("--list", action="store_true", help="Lista todos os itens da wishlist")
    parser.add_argument("--remove", type=int, help="Remove item da wishlist por ID")
    parser.add_argument("--add", type=str, metavar="title_id", help="Adiciona item à wishlist")
    parser.add_argument("--user-id", type=int, help="ID do usuário para adicionar item")
    parser.add_argument("--name", type=str, help="Nome do item (opcional)")
    parser.add_argument("--cleanup-orphans", action="store_true", help="Remove itens da wishlist sem usuário válido")

    args = parser.parse_args()

    from app import create_app

    app = create_app()

    if args.list:
        list_wishlist_items(app)

    if args.remove:
        print()
        remove_wishlist_item_app_id(app, args.remove, force=True)

    if args.add:
        if not args.user_id:
            print("✗ --user-id é obrigatório para adicionar item")
            sys.exit(1)
        print()
        add_wishlist_item_manually(app, args.add, args.user_id, args.name)

    if args.cleanup_orphans:
        cleanup_orphaned_wishlist_items(app)

    if not any([args.list, args.remove, args.add, args.cleanup_orphans]):
        # Default: list Wishlist
        list_wishlist_items(app)
        print()
        print("Para remover item:")
        print("  python scripts/wishlist_cleanup.py --remove <item_id>")
        print()
        print("Para limpar itens orphans:")
        print("  python scripts/wishlist_cleanup.py --cleanup-orphans")


if __name__ == "__main__":
    main()
