"""
Large JSON File Sanitizer - Stream-based recovery for corrupted files
"""

import os
import re
import logging
import json

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
    Sanitize large corrupted JSON files (10MB+) by streaming and manual parsing.
    Recovers as many valid entries as possible from partially corrupted files.
    Uses database cache as fallback.

    IMPORTANT: This function is designed to be non-blocking with aggressive yielding
    to prevent Gunicorn worker timeout. It yields control after every operation.

    Args:
        filepath: Path to the JSON file

    Returns:
        dict: Recovered title entries, or None if file doesn't exist
    """
    if not os.path.exists(filepath):
        return None

    import time

    start_time = time.time()

    try:
        # Try to use cached data first if available
        from db import TitleDBCache

        cached_entries = {}
        try:
            # Extract file identifier from path
            filename = os.path.basename(filepath)
            identifier = filename.replace("titles.", "").replace(".json", "").lower().replace(".", "_")

            # Yield after setting up identifiers
            yield_to_event_loop()

            # Try to get cached entries from DB
            cached = (
                TitleDBCache.query.filter(db.or_(TitleDBCache.source == filename, TitleDBCache.source == identifier))
                .limit(50000)
                .all()
            )

            if cached and len(cached) > 0:
                cached_entries = {entry.title_id: entry.data for entry in cached if entry.data}
                logger.info(f"Using {len(cached_entries)} cached entries from database for {filename}")
        except Exception as e:
            logger.debug(f"Could not load cached data: {e}")
            # Yield after cache attempt fails
            yield_to_event_loop()

        # Try stream-based recovery for large files
        logger.info(f"Attempting stream-based recovery for large file: {filepath}")

        try:
            # Read file in chunks to avoid loading entire file into memory
            chunk_size = 1024 * 1024  # 1MB chunks
            recovered = {}

            # Pattern to find complete JSON objects: "TitleID": { ... }
            object_pattern = re.compile(r'"([0-9A-Fa-f]{16})"\s*:\s*\{')

            # Yield before opening file
            yield_to_event_loop()

            with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
                buffer = ""
                total_found = 0
                batch_size = 1000
                current_batch = 0
                chunk_count = 0

                logger.info(f"Starting stream recovery (chunk_size={chunk_size}MB)...")

                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break

                    chunk_count += 1

                    # Log every 10MB processed for debugging
                    if chunk_count % 10 == 0:
                        elapsed = time.time() - start_time
                        logger.info(
                            f"Progress: {chunk_count}MB processed, {total_found} entries found, {elapsed:.1f}s elapsed"
                        )
                        yield_to_event_loop()

                    buffer += chunk

                    # Yield after each chunk read to prevent blocking
                    yield_to_event_loop()

                    # Find and extract complete objects
                    matches = list(object_pattern.finditer(buffer))

                    for match in matches:
                        title_id = match.group(1)
                        start_pos = match.start()

                        # Try to find the end of this object
                        brace_depth = 0
                        in_string = False
                        escape_next = False
                        end_pos = start_pos + len(match.group(0)) - 1  # Start at the first {

                        # Find matching closing brace
                        i = end_pos
                        valid_end = None

                        while i < len(buffer):
                            char = buffer[i]

                            if escape_next:
                                escape_next = False
                            elif char == "\\":
                                escape_next = True
                            elif char == '"':
                                in_string = not in_string
                            elif not in_string:
                                if char == "{":
                                    brace_depth += 1
                                elif char == "}":
                                    if brace_depth == 0:
                                        valid_end = i + 1
                                        break
                                    brace_depth -= 1

                            i += 1
                            # Yield after every 1000 characters parsed to prevent tight loops
                            if i % 1000 == 0:
                                yield_to_event_loop()

                        if valid_end:
                            # Extract the object JSON
                            object_str = buffer[start_pos:valid_end]

                            try:
                                obj_data = json.loads(object_str)

                                if obj_data and isinstance(obj_data, dict):
                                    recovered[title_id.upper()] = obj_data
                                    current_batch += 1
                                    total_found += 1

                                    # Clear used portion of buffer periodically
                                    if current_batch >= batch_size:
                                        buffer = buffer[valid_end:]
                                        break

                                    # Yield more frequently during processing
                                    if total_found % 100 == 0:
                                        yield_to_event_loop()

                            except json.JSONDecodeError:
                                pass

                    # Yield periodically while processing objects
                    if total_found > 0 and total_found % 500 == 0:
                        percent_complete = min(100, (total_found / 10000) * 5)  # Rough estimate for logging
                        logger.info(f"Stream recovery progress: {total_found} entries recovered")
                        yield_to_event_loop()

                # Also yield after processing each chunk
                yield_to_event_loop()

                elapsed = time.time() - start_time
                logger.info(
                    f"Stream recovery completed in {elapsed:.2f}s: {total_found} entries from {chunk_count} chunks"
                )

                # Merge recovered data with cached data (recovered takes priority)
                if recovered:
                    if cached_entries:
                        cached_entries.update(recovered)
                        logger.info(
                            f"Recovered {len(recovered)} entries from file, total with cache: {len(cached_entries)}"
                        )
                        return cached_entries
                    else:
                        logger.info(f"Successfully recovered {len(recovered)} entries from large file via streaming")
                        return recovered
                elif cached_entries:
                    logger.info(f"Using only cached data: {len(cached_entries)} entries (file recovery failed)")
                    return cached_entries
                else:
                    logger.warning("Stream recovery returned no entries and no cache available")
                    return None

        except Exception as e:
            logger.error(f"Stream-based recovery failed for {filepath}: {e}")
            # Fall back to cached data only
            if cached_entries:
                logger.info(f"Falling back to cached data: {len(cached_entries)} entries")
                yield_to_event_loop()
                return cached_entries
            return None

    except Exception as e:
        logger.error(f"Error sanitizing large file {filepath}: {e}")
        return None, start_time
