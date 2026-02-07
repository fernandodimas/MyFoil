
import os
import sys
from flask import Flask
from sqlalchemy import create_engine, text

# Add app directory to path
sys.path.append(os.path.join(os.getcwd(), 'app'))

from constants import MYFOIL_DB
from db import db

def clear_database():
    print(f"Limpando o banco de dados: {MYFOIL_DB}")
    
    # Minimal Flask app for SQLAlchemy/Flask-SQLAlchemy to work
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    
    # Initialize only the DB extension
    db.init_app(app)
    
    with app.app_context():
        try:
            # Import models to register them with metadata
            import db as db_module
            
            print("Removendo todas as tabelas...")
            # Using raw engine for drop_all to avoid any potential app-level hooks
            db.reflect() # Reflect all existing tables
            db.drop_all()
            
            print("Recriando estrutura do banco (vazia)...")
            db.create_all()
            
            # Stamp alembic if possible
            try:
                from db import get_alembic_cfg
                from alembic import command
                command.stamp(get_alembic_cfg(), "head")
                print("Alembic head stampado.")
            except Exception as ae:
                print(f"Alembic stamp skipped: {ae}")
                
            print("\n✅ Banco de dados 'myfoil' foi limpo com sucesso!")
        except Exception as e:
            print(f"\n❌ Erro: {e}")

if __name__ == "__main__":
    clear_database()
