import sys
import os

sys.path.append("/Users/fernandosouza/Documents/Projetos/MyFoil")
sys.path.append("/Users/fernandosouza/Documents/Projetos/MyFoil/app")

from app.app import create_app
from db import get_shop_files

app = create_app()
with app.app_context():
    files = get_shop_files()
    print(f"Total files in shop: {len(files)}")
    for f in files[:20]:
        print(f)
