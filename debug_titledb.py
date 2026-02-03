
import sys
import os

# Adiciona diretório app ao path
sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import titles
import logging

# Configura logger básico
logging.basicConfig(level=logging.INFO)

print("--- DIAGNÓSTICO TITLEDB ---")

try:
    # 1. Tenta carregar
    print("Carregando TitleDB...")
    titles.load_titledb()
    
    # 2. Verifica contagem
    t_count = len(titles._titles_db) if titles._titles_db else 0
    v_count = len(titles._versions_db) if titles._versions_db else 0
    
    print(f"Titles: {t_count}")
    print(f"Versions: {v_count}")
    
    if t_count < 100:
        print("ERRO: TitleDB parece vazio ou muito pequeno!")
    else:
        print("OK: TitleDB carregado com dados.")

    # 3. Verifica arquivo de cache
    cache_file = os.path.join('app', 'data', 'titledb_cache.json.gz')
    if os.path.exists(cache_file):
        size = os.path.getsize(cache_file) / 1024 / 1024
        print(f"Arquivo de Cache: {cache_file} ({size:.2f} MB)")
    else:
        print(f"Arquivo de Cache NÃO ENCONTRADO: {cache_file}")

except Exception as e:
    print(f"ERRO CRÍTICO: {e}")
