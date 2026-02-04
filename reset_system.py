
import os
import sys
import yaml
from flask import Flask

# Add app directory to path
sys.path.append(os.path.join(os.getcwd(), 'app'))

from db import db
from constants import MYFOIL_DB, CONFIG_FILE

def reset_entire_system():
    print(f"--- RESET TOTAL DO SISTEMA (Banco: {MYFOIL_DB}) ---")
    
    # 1. Limpar caminhos no settings.yaml
    if os.path.exists(CONFIG_FILE):
        print(f"Limpando caminhos em {CONFIG_FILE}...")
        with open(CONFIG_FILE, 'r') as f:
            settings = yaml.safe_load(f) or {}
        
        if 'library' in settings:
            settings['library']['paths'] = []
            with open(CONFIG_FILE, 'w') as f:
                yaml.dump(settings, f)
            print("Caminhos de biblioteca removidos do settings.yaml.")

    # 2. Limpar o banco de dados
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    
    with app.app_context():
        try:
            # Import models
            import db as db_module
            
            print("Limpando todas as tabelas do banco de dados...")
            db.drop_all()
            db.create_all()
            
            # 3. Recriar usuário ADMIN padrão (dimas / *Dims3410)
            from werkzeug.security import generate_password_hash
            from db import User
            
            hashed_pw = generate_password_hash("*Dims3410", method='pbkdf2:sha256')
            admin = User(
                user="dimas", 
                password=hashed_pw, 
                admin_access=True, 
                shop_access=True, 
                backup_access=True
            )
            db.session.add(admin)
            db.session.commit()
            
            # Stamp alembic
            from db import get_alembic_cfg
            from alembic import command
            try:
                command.stamp(get_alembic_cfg(), "head")
            except:
                pass
                
            print("\n✅ TUDO LIMPO! Banco resetado, configurações de caminhos removidas e usuário 'dimas' recriado.")
            print("Agora você pode adicionar novas bibliotecas pela interface sem erros de 'já configurado'.")
        except Exception as e:
            print(f"\n❌ Erro durante o reset: {e}")

if __name__ == "__main__":
    reset_entire_system()
