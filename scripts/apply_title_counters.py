#!/usr/bin/env python3
"""
Script para aplicar as colunas materializadas e índices de forma idempotente.

Uso:
  python scripts/apply_title_counters.py

Observações:
- Executa dentro do contexto da Flask app (usa create_app()).
- Requer que a variável de ambiente DATABASE_URL / configuração de DB esteja correta no ambiente.
"""

import sys
from sqlalchemy import text

try:
    # Import local app factory and db
    from app.app import create_app
    from db import db
except Exception as e:
    print("Falha ao importar a aplicação/local DB. Execute este script no ambiente do projeto:", e)
    sys.exit(2)


def main():
    app = create_app()
    with app.app_context():
        conn = db.engine.connect()
        try:
            stmts = [
                "ALTER TABLE titles ADD COLUMN IF NOT EXISTS redundant_updates_count INTEGER DEFAULT 0;",
                "ALTER TABLE titles ADD COLUMN IF NOT EXISTS missing_dlcs_count INTEGER DEFAULT 0;",
                "CREATE INDEX IF NOT EXISTS idx_titles_redundant_updates_count ON titles(redundant_updates_count);",
                "CREATE INDEX IF NOT EXISTS idx_titles_missing_dlcs_count ON titles(missing_dlcs_count);",
            ]

            print("Aplicando alterações no banco (idempotente)...")
            for s in stmts:
                print("-> Executando:", s)
                conn.execute(text(s))

            print("Alterações aplicadas com sucesso. Recomendado: reiniciar o serviço web (Gunicorn/container).")
        except Exception as err:
            print("Erro ao aplicar alterações:", err)
            sys.exit(1)
        finally:
            conn.close()


if __name__ == "__main__":
    main()
