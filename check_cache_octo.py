import json
import os

CACHE_FILE = "app/data/cache/library.json"

def check_cache():
    if not os.path.exists(CACHE_FILE):
        print("Cache file not found.")
        return

    with open(CACHE_FILE, 'r') as f:
        data = json.load(f)

    # data can be a list or a dict with "library" key
    items = data["library"] if isinstance(data, dict) and "library" in data else data
    
    for item in items:
        if "OCTOPATH" in item.get("name", "").upper():
            print(f"Name: {item.get('name')}")
            print(f"  ID: {item.get('id')}")
            print(f"  Owned Version: {item.get('owned_version')}")
            print(f"  Latest Version: {item.get('latest_version_available')}")
            print(f"  Has Latest: {item.get('has_latest_version')}")
            print(f"  Has Base: {item.get('has_base')}")
            print(f"  Status Color: {item.get('status_color')}")
            print(f"  Display Version: {item.get('display_version')}")
            print("-" * 20)

if __name__ == "__main__":
    check_cache()
