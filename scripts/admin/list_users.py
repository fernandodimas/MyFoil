
import os
import sys

sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import app
from db import User

def list_users():
    with app.app_context():
        users = User.query.all()
        if not users:
            print("Nenhum usuário encontrado no banco de dados.")
            return
        
        print("Usuários encontrados:")
        for u in users:
            print(f"- {u.user} (ID: {u.id})")

if __name__ == "__main__":
    list_users()
