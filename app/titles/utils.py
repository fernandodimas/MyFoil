import os
import re
import json
import time
import logging
from datetime import datetime
from constants import ALLOWED_EXTENSIONS as _ALLOWED_EXTENSIONS

app_id_regex = r"\[([0-9A-Fa-f]{16})\]"
version_regex = r"\[v(\d+)\]"

logger = logging.getLogger("main")

try:
    import gevent
except ImportError:
    gevent = None


def format_release_date(date_input):
    try:
        if not date_input:
            return ""

        date_str = str(date_input).strip()

        if re.match(r"^\d{4}-\d{2}-\d{2}$", date_str):
            return date_str

        if re.match(r"^\d{8}$", date_str):
            return f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"

        for fmt in ["%Y/%m/%d", "%d/%m/%Y", "%m/%d/%Y", "%Y%m%d"]:
            try:
                parsed = datetime.strptime(date_str, fmt)
                return parsed.strftime("%Y-%m-%d")
            except Exception:
                continue

        return date_str
    except Exception as e:
        logger.debug(f"format_release_date error for {date_input}: {e}")
        return str(date_input) if date_input else ""


def yield_to_event_loop():
    try:
        if gevent:
            gevent.sleep(0.001)
        else:
            time.sleep(0.001)
    except Exception:
        pass


def robust_json_load(filepath):
    if not os.path.exists(filepath):
        return None

    clean_filepath = filepath + ".clean"
    if os.path.exists(clean_filepath):
        if os.path.getmtime(clean_filepath) >= os.path.getmtime(filepath):
            try:
                with open(clean_filepath, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                logger.warning(f"Failed to load cached clean file {clean_filepath}: {e}")

    try:
        filesize = os.path.getsize(filepath)
        if filesize < 500 * 1024 * 1024:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                data = json.load(f)
                return data
    except Exception as e:
        logger.warning(f"Fast JSON load failed for {os.path.basename(filepath)}: {e}. Attempting regex sanitization...")
        try:
            with open(filepath, "r", encoding="utf-8", errors="replace") as f:
                content = f.read()

            pattern = re.compile(r"(\\([\"\\/bfnrt]|u[0-9a-fA-F]{4}))|(\\)")

            def replace_func(m):
                return m.group(1) if m.group(1) else r"\\"

            content = pattern.sub(replace_func, content)
            data = json.loads(content, strict=False)
            if data:
                logger.info(f"Sanitized {os.path.basename(filepath)} successfully. Saving to cache...")
                try:
                    with open(clean_filepath, "w", encoding="utf-8") as f:
                        json.dump(data, f)
                    now = time.time()
                    os.utime(clean_filepath, (now, now))
                except Exception as save_err:
                    logger.warning(f"Failed to save auto-repaired JSON: {save_err}")
            return data
        except Exception as e2:
            logger.warning(f"Regex sanitization failed: {e2}. Falling back to slow robust recovery...")

    try:
        filesize = os.path.getsize(filepath)
        if filesize > 10 * 1024 * 1024:
            logger.info(f"File {filepath} is large ({filesize / 1024 / 1024:.2f} MB). Attempting stream recovery...")
            try:
                from large_json_sanitizer import sanitize_large_json_file
                sanitized = sanitize_large_json_file(filepath)
                if sanitized and len(sanitized) > 0:
                    logger.info(f"Stream recovery successful! Recovered {len(sanitized)} entries.")
                    try:
                        with open(filepath, "w", encoding="utf-8") as f:
                            json.dump(sanitized, f)
                    except Exception as save_err:
                        logger.warning(f"Failed to save auto-repaired JSON after stream recovery: {save_err}")
                    return sanitized
            except Exception as e:
                logger.error(f"Error in stream recovery: {e}")
    except Exception:
        pass

    return None


def getDirsAndFiles(path):
    allFiles = []
    allDirs = []

    try:
        if gevent:
            gevent.sleep(0.001)

        with os.scandir(path) as it:
            for i, entry in enumerate(it):
                if gevent and i % 50 == 0:
                    gevent.sleep(0.001)

                if entry.name == ".DS_Store":
                    try:
                        os.remove(entry.path)
                        logger.info(f"Deleted .DS_Store: {entry.path}")
                    except OSError:
                        pass
                    continue

                if entry.name.startswith("._"):
                    continue

                if entry.is_dir(follow_symlinks=False):
                    fullPath = entry.path
                    allDirs.append(fullPath)
                    dirs, files = getDirsAndFiles(fullPath)
                    allDirs += dirs
                    allFiles += files
                elif entry.is_file():
                    ext = "." + entry.name.split(".")[-1].lower()
                    if ext in _ALLOWED_EXTENSIONS:
                        allFiles.append(entry.path)
    except Exception as e:
        logger.error(f"Error scanning directory {path}: {e}")

    return allDirs, allFiles


def get_app_id_from_filename(filename):
    app_id_match = re.search(app_id_regex, filename)
    return app_id_match[1] if app_id_match is not None else None


def get_version_from_filename(filename):
    version_match = re.search(version_regex, filename)
    return version_match[1] if version_match is not None else None


def get_file_size(filepath):
    return os.path.getsize(filepath)


def get_file_info(filepath):
    filedir, filename = os.path.split(filepath)
    extension = filename.split(".")[-1]

    compressed = False
    if extension in ["nsz", "xcz"]:
        compressed = True

    return {
        "filepath": filepath,
        "filedir": filedir,
        "filename": filename,
        "extension": extension,
        "compressed": compressed,
        "size": get_file_size(filepath),
    }
