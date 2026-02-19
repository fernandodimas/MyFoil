import json
import os

files = [
    '/Users/fernandosouza/Documents/Projetos/MyFoil/app/translations/en.json',
    '/Users/fernandosouza/Documents/Projetos/MyFoil/app/translations/pt_BR.json',
    '/Users/fernandosouza/Documents/Projetos/MyFoil/app/translations/es.json'
]

for file_path in files:
    if os.path.exists(file_path):
        print(f"Processing {file_path}...")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                # json.load handles duplicates by keeping the last occurrence
                data = json.load(f)
            
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"Fixed {file_path}")
        except Exception as e:
            print(f"Error processing {file_path}: {e}")
