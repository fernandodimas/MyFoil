from constants import *
import yaml
import os

from nstools.nut import Keys

import logging

# Retrieve main logger
logger = logging.getLogger("main")


def load_keys(key_file=KEYS_FILE):
    valid = False
    try:
        if os.path.isfile(key_file):
            valid = Keys.load(key_file)
            return valid
        else:
            logger.debug(f"Keys file {key_file} does not exist.")

    except:
        logger.error(f"Provided keys file {key_file} is invalid.")
    return valid


# Cache variable
_cached_settings = None


def load_settings(force=False):
    global _cached_settings

    if _cached_settings and not force:
        return _cached_settings

    if os.path.exists(CONFIG_FILE):
        logger.debug(f"Reading configuration file: {CONFIG_FILE}")
        with open(CONFIG_FILE, "r") as yaml_file:
            settings = yaml.safe_load(yaml_file) or {}

        # Deep merge with defaults to ensure new keys (like apis) are present
        merged_settings = DEFAULT_SETTINGS.copy()
        for section, values in settings.items():
            if isinstance(values, dict) and section in merged_settings and isinstance(merged_settings[section], dict):
                merged_settings[section].update(values)
            else:
                merged_settings[section] = values
        settings = merged_settings

        valid_keys = load_keys()
        settings["titles"]["valid_keys"] = valid_keys

    else:
        settings = DEFAULT_SETTINGS
        with open(CONFIG_FILE, "w") as yaml_file:
            yaml.dump(settings, yaml_file)

    _cached_settings = settings
    return settings


def verify_settings(section, data):
    success = True
    errors = []
    if section == "library":
        # Check that paths exist
        for dir in data["paths"]:
            if not os.path.exists(dir):
                success = False
                errors.append({"path": "library/path", "error": f"Path {dir} does not exists."})
                break
    return success, errors


def add_library_path_to_settings(path):
    success = True
    errors = []
    if not os.path.exists(path):
        success = False
        errors.append({"path": "library/paths", "error": f"Path {path} does not exists."})
        return success, errors

    settings = load_settings()
    library_paths = settings["library"]["paths"]
    if library_paths:
        if path in library_paths:
            success = False
            errors.append({"path": "library/paths", "error": f"Path {path} already configured."})
            return success, errors
        library_paths.append(path)
    else:
        library_paths = [path]
    settings["library"]["paths"] = library_paths
    with open(CONFIG_FILE, "w") as yaml_file:
        yaml.dump(settings, yaml_file)
    reload_conf()
    return success, errors



def delete_library_path_from_settings(path):
    success = True
    errors = []
    settings = load_settings()
    library_paths = settings["library"]["paths"]
    if library_paths:
        if path in library_paths:
            library_paths.remove(path)
            settings["library"]["paths"] = library_paths
            with open(CONFIG_FILE, "w") as yaml_file:
                yaml.dump(settings, yaml_file)
            reload_conf()
        else:
            success = False
            errors.append({"path": "library/paths", "error": f"Path {path} not configured."})
    return success, errors



def set_titles_settings(region, language, dbi_versions=None, auto_use_latest=None):
    settings = load_settings()
    settings["titles"]["region"] = region
    settings["titles"]["language"] = language
    if dbi_versions is not None:
        settings["titles"]["dbi_versions"] = dbi_versions
    if auto_use_latest is not None:
        settings["titles"]["auto_use_latest"] = auto_use_latest
    with open(CONFIG_FILE, "w") as yaml_file:
        yaml.dump(settings, yaml_file)
    reload_conf()



def set_shop_settings(data):
    settings = load_settings()
    shop_host = data["host"]
    if "://" in shop_host:
        data["host"] = shop_host.split("://")[-1]
    settings["shop"].update(data)
    with open(CONFIG_FILE, "w") as yaml_file:
        yaml.dump(settings, yaml_file)
    reload_conf()



def toggle_plugin_settings(plugin_id, enabled):
    settings = load_settings()
    if "plugins" not in settings:
        settings["plugins"] = {"disabled": []}

    disabled_list = settings["plugins"].get("disabled", [])

    if enabled:
        if plugin_id in disabled_list:
            disabled_list.remove(plugin_id)
    else:
        if plugin_id not in disabled_list:
            disabled_list.append(plugin_id)

    settings["plugins"]["disabled"] = disabled_list
    with open(CONFIG_FILE, "w") as yaml_file:
        yaml.dump(settings, yaml_file)
    reload_conf()
    return True



def reload_conf():
    """Reload application settings cache"""
    global _cached_settings
    _cached_settings = None
    return load_settings(force=True)
