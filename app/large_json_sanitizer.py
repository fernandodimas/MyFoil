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

    start_time = time.time()
    recovered = {}
    total_found = 0

    try:
        # Pattern to find TitleID blocks: "0100000000010000": {
        # Using a regex that matches the standard TitleDB entry start
        object_pattern = re.compile(r'"([0-9A-Fa-f]{16})"\s*:\s*\{')

        logger.info(f"Starting FAST block recovery for {os.path.basename(filepath)}...")

        # Read the whole file. For 60-100MB this is safe in most Docker envs (uses ~200-300MB RAM peak)
        with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
            content = f.read()

        yield_to_event_loop()

        # Split content by the TitleID pattern
        # The split will return [prefix, ID1, Body1, ID2, Body2, ...]
        parts = object_pattern.split(content)
        
        prefix = parts[0]
        # Iterate over ID/Body pairs (skipping the prefix)
        for i in range(1, len(parts), 2):
            title_id = parts[i].upper()
            body = parts[i+1]
            
            # Find the end of this specific object (the last closing brace before the next match)
            # We add back the opening brace { that was consumed by the regex
            obj_str = "{" + body
            
            # Find last closing brace
            last_brace = obj_str.rfind("}")
            if last_brace != -1:
                clean_obj_str = obj_str[:last_brace+1]
                
                try:
                    # Attempt to parse this individual game object
                    # strict=False allows control characters and some minor syntax issues
                    obj_data = json.loads(clean_obj_str, strict=False)
                    if obj_data and isinstance(obj_data, dict):
                        recovered[title_id] = obj_data
                        total_found += 1
                except:
                    # If this specific game is corrupt, skip it and continue
                    pass

            # Yield control periodically to prevent worker timeout
            if total_found % 2000 == 0:
                yield_to_event_loop()

        elapsed = time.time() - start_time
        logger.info(f"Recovery finished: {total_found} entries recovered in {elapsed:.2f}s")
        return recovered if recovered else None

    except Exception as e:
        logger.error(f"Critical error during fast recovery: {e}")
        return None
