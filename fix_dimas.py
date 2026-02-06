
import os
import sys

sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import app
from db import db, User
from werkzeug.security import generate_password_hash

def try_change_password(username, new_password):
    urls = [
        os.environ.get("DATABASE_URL"),
        "postgresql://myfoil:myfoilpassword@192.168.16.250:5432/myfoillocal",
        "postgresql://myfoil:myfoilpassword@localhost:5432/myfoil",
        "sqlite:///app/config/myfoil.db",
        "sqlite:///app/myfoil.db"
    ]
    
    for url in urls:
        if not url: continue
        print(f"Tentando URL: {url}")
        os.environ["DATABASE_URL"] = url
        try:
            with app.app_context():
                # Re-bind engine if necessary (Flask-SQLAlchemy handles this usually if we change config, 
                # but here we might need to be careful)
                app.config["SQLALCHEMY_DATABASE_URI"] = url
                # In some versions we might need to call init_app again or just use a new engine
                
                user = User.query.filter_by(user=username).first()
                if user:
                    print(f"Usuário '{username}' encontrado em {url}!")
                    user.password = generate_password_hash(new_password, method='pbkdf2:sha256')
                    db.session.commit()
                    print("Senha alterada com sucesso!")
                    return True
                else:
                    print(f"Usuário não encontrado em {url}")
        except Exception as e:
            print(f"Erro ao tentar {url}: {e}")
    return False

if __name__ == "__main__":
    try_change_password("dimas", "dims3410")
