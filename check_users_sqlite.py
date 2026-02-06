
import sqlite3
import os

db_paths = [
    "app/config/myfoil.db",
    "app/myfoil.db",
    "db.sqlite"
]

for path in db_paths:
    if os.path.exists(path):
        print(f"\n--- Banco: {path} ---")
        try:
            conn = sqlite3.connect(path)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cursor.fetchall()
            print(f"Tabelas: {tables}")
            
            if ('user',) in tables:
                cursor.execute("SELECT id, user, admin_access FROM user;")
                users = cursor.fetchall()
                print(f"Usuários: {users}")
            else:
                print("Tabela 'user' não encontrada.")
            conn.close()
        except Exception as e:
            print(f"Erro: {e}")
