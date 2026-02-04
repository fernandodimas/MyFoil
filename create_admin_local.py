
import os
import sys
from flask import Flask
from werkzeug.security import generate_password_hash

# Add app directory to path
sys.path.append(os.path.join(os.getcwd(), 'app'))

from db import db, User
from constants import MYFOIL_DB

def create_admin(username, password):
    print(f"Configurando usuário ADMIN no banco: {MYFOIL_DB}")
    
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    db.init_app(app)
    
    with app.app_context():
        try:
            # Check if user exists
            user = User.query.filter_by(user=username).first()
            
            hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
            
            if user:
                print(f"Usuário '{username}' já existe. Atualizando para ADMIN e resetando senha...")
                user.password = hashed_pw
                user.admin_access = True
                user.shop_access = True
                user.backup_access = True
            else:
                print(f"Criando novo usuário ADMIN '{username}'...")
                new_user = User(
                    user=username, 
                    password=hashed_pw, 
                    admin_access=True, 
                    shop_access=True, 
                    backup_access=True
                )
                db.session.add(new_user)
            
            db.session.commit()
            print(f"\n✅ Usuário '{username}' agora é ADMIN e a senha foi definida!")
            print("Você já pode fazer o login no sistema.")
        except Exception as e:
            print(f"\n❌ Erro: {e}")

if __name__ == "__main__":
    if len(sys.argv) < 3:
        print("Uso: python create_admin_direct.py <usuario> <senha>")
    else:
        create_admin(sys.argv[1], sys.argv[2])
