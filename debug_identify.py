
import sys
import os
import logging

# Setup path
sys.path.append(os.path.join(os.getcwd(), 'app'))

# Setup logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger("main")

from app import titles
from app import titledb
from nstools.nut import Keys

print(f"Keys Loaded: {Keys.keys_loaded}")

print("Loading TitleDB...")
titles.load_titledb()

print(f"Titles DB Size: {len(titles._titles_db) if titles._titles_db else 0}")

# Test identification with a fake filename
# Assuming we have titles.json loaded
test_id = "0100000000010000" # Super Mario Odyssey (Example)
if titles._titles_db and test_id in titles._titles_db:
    print(f"Test match: {titles._titles_db[test_id].get('name')}")
else:
    print("Test match failed or DB empty")

