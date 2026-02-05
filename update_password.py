
import os
import sys

# Adiciona o diretório app ao path para poder importar os módulos
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import app
from db import db, User
from werkzeug.security import generate_password_hash

def change_password(username, new_password):
    with app.app_context():
        user = User.query.filter_by(user=username).first()
        if not user:
            print(f"Usuário '{username}' não encontrado.")
            return False
        
        user.password = generate_password_hash(new_password, method='pbkdf2:sha256')
        db.session.commit()
        print(f"Senha do usuário '{username}' alterada com sucesso!")
        return True

if __name__ == "__main__":
    change_password("dimas", "dims3410")
