from db import logger

from constants import ALLOWED_EXTENSIONS, LIBRARY_CACHE_FILE
from library._state import LIBRARY_CACHE
from library.validation import validate_file, cleanup_metadata_files

from library.cache import (
    _cached_get_all_existing_dlc,
    _cached_get_all_existing_versions,
    _cached_get_all_app_existing_versions,
    _clear_titledb_caches,
    compute_apps_hash,
    is_library_unchanged,
    save_library_to_disk,
    load_library_from_disk,
    invalidate_library_cache,
    detect_changed_titles,
    get_library_status,
)

from library.scan import (
    add_library_complete,
    remove_library_complete,
    init_libraries,
    add_files_to_library,
    scan_library_path,
    get_files_to_identify,
    identify_single_file,
    identify_library_files,
    update_or_create_app_and_link_file,
    add_missing_apps_to_db,
    trigger_library_update_notification,
    process_library_identification,
    reidentify_all_files_job,
)

from library.generation import (
    update_titles,
    update_single_game_in_cache,
    incremental_library_update,
    get_game_info_item,
    generate_library,
    apply_ignore_preferences_to_game,
    post_library_change,
    version_to_string,
    get_pending_update_info,
)
