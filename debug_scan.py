import sys
import os
sys.path.append('app')
import titles
from constants import ALLOWED_EXTENSIONS

def check_path(path):
    print(f"\nChecking Path: {path}")
    if not os.path.exists(path):
        print(f"FAILED: {path} does not exist!")
        return
    
    print(f"Exists? Yes. Is Dir? {os.path.isdir(path)}")
    
    try:
        items = os.listdir(path)
        print(f"Total items in root: {len(items)}")
        for item in items[:10]:
            full = os.path.join(path, item)
            is_f = os.path.isfile(full)
            is_d = os.path.isdir(full)
            print(f"  - {item} [{'FILE' if is_f else 'DIR' if is_d else 'OTHER'}]")
    except Exception as e:
        print(f"Error listing {path}: {e}")

    print("\nRunning getDirsAndFiles recursion...")
    dirs, files = titles.getDirsAndFiles(path)
    print(f"Found {len(dirs)} directories and {len(files)} files.")
    if files:
        print("First 5 files found:")
        for f in files[:5]:
            print(f"  {f}")
    else:
        print("NO FILES FOUND with allowed extensions:", ALLOWED_EXTENSIONS)

check_path('/externo')
check_path('/games')
