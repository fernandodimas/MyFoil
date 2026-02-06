import sys
import os
import logging

# Configure logging to stdout
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger("main")

sys.path.append(os.path.join(os.getcwd(), 'app'))

from app import create_app
from db import get_libraries
from library import scan_library_path, identify_library_files, update_titles, generate_library

def run_manual_scan():
    app = create_app()
    with app.app_context():
        print("--- Starting Manual Scan ---")
        libraries = get_libraries()
        if not libraries:
            print("No libraries found in DB.")
            return

        for lib in libraries:
            print(f"Scanning library: {lib.path}")
            try:
                scan_library_path(lib.path)
                print(f"Scan complete for {lib.path}. Starting identification...")
                identify_library_files(lib.path)
                print(f"Identification complete for {lib.path}")
            except Exception as e:
                logger.exception(f"Error processing {lib.path}: {e}")

        print("Updating titles...")
        update_titles()
        print("Generating library cache...")
        generate_library(force=True)
        print("--- Manual Scan Complete ---")

if __name__ == "__main__":
    run_manual_scan()
