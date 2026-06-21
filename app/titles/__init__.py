import os
import re
import json
import time
import fcntl

try:
    import gevent
except ImportError:
    gevent = None

from constants import (
    APP_TYPE_BASE,
    APP_TYPE_UPD,
    APP_TYPE_DLC,
    TITLEDB_DIR,
    ALLOWED_EXTENSIONS,
    CONFIG_DIR,
)
from utils import now_utc
from settings import load_settings
from pathlib import Path
from binascii import hexlify as hx
import logging

from nstools.Fs import Pfs0, Nca, Type, factory
from nstools.lib import FsTools
from nstools.nut import Keys

Pfs0.Print.silent = True

from titles._state import (
    logger,
    identification_in_progress_count,
    _titles_db_loaded,
    _cnmts_db,
    _titles_db,
    _versions_db,
    _versions_txt_db,
    _dlc_map,
    _dlcs_by_base_id,
    _loaded_titles_file,
    _titledb_cache_timestamp,
    _titledb_cache_ttl,
    _game_info_cache,
)

from titles.utils import (
    format_release_date,
    yield_to_event_loop,
    robust_json_load,
    getDirsAndFiles,
    get_app_id_from_filename,
    get_version_from_filename,
    get_file_size,
    get_file_info,
)

from titles.titledb_cache import (
    get_titles_count,
    load_titledb_from_db,
    save_titledb_to_db,
    is_db_cache_valid,
    get_titledb_cache_timestamp,
    set_titledb_cache_timestamp,
    load_titledb_from_disk_fallback,
    load_titledb,
    unload_titledb,
    _enrich_dlc_map_from_titles,
)

from titles.identification import (
    get_title_id_from_app_id,
    identify_appId,
    identify_file_from_filename,
    identify_file_from_cnmt,
    identify_file,
)

from titles.game_info import (
    get_game_info,
    get_update_number,
    get_game_latest_version,
    get_all_existing_versions,
    get_all_app_existing_versions,
    get_app_id_version_from_versions_txt,
    get_all_existing_dlc,
    get_loaded_titles_file,
    get_custom_title_info,
    search_titledb_by_name,
    save_custom_title_info,
    sync_titles_to_db,
)
