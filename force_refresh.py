import sys
import os

# Add app to sys.path
sys.path.append(os.path.join(os.getcwd(), 'app'))

import app
from library import generate_library

def force_refresh():
    with app.app.app_context():
        print("Forcing library generation...")
        generate_library(force=True)
        print("Done.")

if __name__ == "__main__":
    force_refresh()
