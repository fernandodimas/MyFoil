
import os
import sys
from flask import Flask

# Add app directory to path
sys.path.append(os.path.join(os.getcwd(), 'app'))

from db import db, User
from constants import MYFOIL_DB

def wipe_users():
    print(f"--- LIMPANDO TODOS OS USUÁRIOS (Banco: {MYFOIL_DB}) ---")
    
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    
    with app.app_context():
        try:
            count = User.query.count()
            db.session.query(User).delete()
            db.session.commit()
            print(f"✅ {count} usuário(s) removido(s) com sucesso!")
            print("O sistema agora está sem nenhum usuário. Você pode testar o primeiro cadastro.")
        except Exception as e:
            print(f"\n❌ Erro: {e}")

if __name__ == "__main__":
    wipe_users()
