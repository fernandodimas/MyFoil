import logging

logger = logging.getLogger("main")

identification_in_progress_count = 0
_titles_db_loaded = False
_cnmts_db = None
_titles_db = None
_versions_db = None
_versions_txt_db = None
_dlc_map = {}
_dlcs_by_base_id = {}
_loaded_titles_file = None
_titledb_cache_timestamp = None
_titledb_cache_ttl = 3600
_game_info_cache = {}
