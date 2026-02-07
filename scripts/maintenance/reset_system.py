
import os
import sys
import yaml
import shutil
from flask import Flask
from sqlalchemy import text

# Add app directory to path
sys.path.append(os.path.join(os.getcwd(), 'app'))

from db import db, init_db, User
from constants import MYFOIL_DB, CONFIG_FILE, TITLEDB_DIR, CONFIG_DIR

def reset_entire_system():
    print(f"--- RESET TOTAL E CORREÇÃO DE TABELAS (Banco: {MYFOIL_DB}) ---")
    
    # 1. Limpar caminhos no settings.yaml
    if os.path.exists(CONFIG_FILE):
        print(f"Limpando caminhos em {CONFIG_FILE}...")
        with open(CONFIG_FILE, 'r') as f:
            settings = yaml.safe_load(f) or {}
        
        if 'library' in settings:
            settings['library']['paths'] = []
            with open(CONFIG_FILE, 'w') as f:
                yaml.dump(settings, f)
            print("Caminhos de biblioteca removidos.")

    # 2. Limpar arquivos físicos do TitleDB
    if os.path.exists(TITLEDB_DIR):
        print(f"Limpando diretório {TITLEDB_DIR}...")
        shutil.rmtree(TITLEDB_DIR, ignore_errors=True)
        os.makedirs(TITLEDB_DIR, exist_ok=True)
        print("Arquivos TitleDB removidos.")

    # 3. Limpar e Recriar o Banco de Dados com TODAS as tabelas
    app = Flask(__name__)
    app.config["SQLALCHEMY_DATABASE_URI"] = MYFOIL_DB
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    db.init_app(app)
    
    with app.app_context():
        try:
            print("Derrubando todas as tabelas existentes...")
            db.drop_all()
            
            print("Criando tabelas base...")
            db.create_all()
            
            print("Executando inicialização forçada (tabelas de jobs, cache e metadados)...")
            # Forçamos o init_db a rodar a lógica de criação manual de tabelas
            # Removemos 'db' do argv temporariamente se estiver lá para garantir que o init_db rode
            old_argv = sys.argv
            sys.argv = [a for a in sys.argv if a != 'db']
            init_db(app)
            sys.argv = old_argv
            
            print("\n✅ BANCO DE DADOS RESTAURADO!")
            print("Todas as tabelas (system_jobs, titledb_cache, etc) foram criadas.")
            print("Sistema limpo e sem usuários. Pronto para testar o cadastro.")
            
        except Exception as e:
            print(f"\n❌ Erro crítico no reset: {e}")
            import traceback
            traceback.print_exc()

if __name__ == "__main__":
    reset_entire_system()
