"""
Large JSON File Sanitizer - Stream-based recovery for corrupted files
Optimized for high-speed processing of 50MB+ TitleDB files.
"""

import os
import re
import logging
import json
import time

logger = logging.getLogger("main")


def yield_to_event_loop():
    """Yield control to the event loop to prevent blocking"""
    try:
        import gevent

        gevent.sleep(0.001)
    except ImportError:
        import time

        time.sleep(0.001)


def sanitize_large_json_file(filepath):
    """
    Sanitize large corrupted JSON files (10MB+) using a fast block-splitting approach.
    Recovers valid entries by isolating each TitleID block.
    """
    if not os.path.exists(filepath):
        return None

    filename = os.path.basename(filepath)
    start_time = time.time()
    recovered = {}
    total_found = 0

    try:
        # Pattern to find TitleID blocks: "0100000000010000": {
        object_pattern = re.compile(r'"([0-9A-Fa-f]{16})"\s*:\s*\{')

        logger.info(f"Starting FAST block recovery for {filename}...")

        # Read file with errors='ignore' to strip binary junk
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        yield_to_event_loop()

        # Split content by the TitleID pattern
        parts = object_pattern.split(content)
        total_blocks = len(parts) // 2
        
        logger.info(f"Found {total_blocks} potential game blocks in {filename}. Processing...")

        # Iterate over ID/Body pairs
        for i in range(1, len(parts), 2):
            title_id = parts[i].upper()
            body = parts[i+1]
            
            # Find the end of this specific object
            obj_str = "{" + body
            last_brace = obj_str.rfind("}")
            
            if last_brace != -1:
                clean_obj_str = obj_str[:last_brace+1]
                try:
                    # Attempt to parse
                    obj_data = json.loads(clean_obj_str, strict=False)
                    if obj_data and isinstance(obj_data, dict):
                        recovered[title_id] = obj_data
                        total_found += 1
                except:
                    pass

            # Log progress every 5000 entries
            if total_found > 0 and total_found % 5000 == 0:
                elapsed = time.time() - start_time
                logger.info(f"Recovery progress for {filename}: {total_found}/{total_blocks} entries ({elapsed:.1f}s)")
                yield_to_event_loop()

        elapsed = time.time() - start_time
        logger.info(f"Recovery finished for {filename}: {total_found} entries in {elapsed:.2f}s")
        return recovered if recovered else None

    except Exception as e:
        logger.error(f"Critical error during fast recovery of {filename}: {e}")
        return None
