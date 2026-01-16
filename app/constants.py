import os

APP_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(APP_DIR, 'data')
CONFIG_DIR = os.path.join(APP_DIR, 'config')
DB_FILE = os.path.join(CONFIG_DIR, 'myfoil.db')
CONFIG_FILE = os.path.join(CONFIG_DIR, 'settings.yaml')
KEYS_FILE = os.path.join(CONFIG_DIR, 'keys.txt')
CACHE_DIR = os.path.join(DATA_DIR, 'cache')
LIBRARY_CACHE_FILE = os.path.join(CACHE_DIR, 'library.json')
ALEMBIC_DIR = os.path.join(APP_DIR, 'migrations')
ALEMBIC_CONF = os.path.join(ALEMBIC_DIR, 'alembic.ini')
TITLEDB_DIR = os.path.join(DATA_DIR, 'titledb')
PLUGINS_DIR = os.path.join(APP_DIR, 'plugins')

# Legacy constants kept for reference
# TITLEDB_URL = 'https://github.com/blawar/titledb.git'
# TITLEDB_ARTEFACTS_URL = 'https://nightly.link/a1ex4/ownfoil/workflows/region_titles/master/titledb.zip'

TITLEDB_DEFAULT_FILES = [
    'cnmts.json',
    'versions.json',
    'versions.txt',
    'languages.json',
]

MYFOIL_DB = 'sqlite:///' + DB_FILE

BUILD_VERSION = '20260116_1624'

DEFAULT_SETTINGS = {
    "library": {
        "paths": ["/games"],
    },
    "titles": {
        "language": "en",
        "region": "US",
        "valid_keys": False,
        "dbi_versions": False,
    },
    "renaming": {
        "enabled": False,
        "pattern_base": "{Name} [{TitleID}] [v{Version}]",
        "pattern_upd": "{Name} [UPD] [{TitleID}] [v{Version}]",
        "pattern_dlc": "{Name} [DLC] [{TitleID}] [v{Version}]",
    },
    "shop": {
        "motd": "Welcome to your own shop!",
        "public": False,
        "public_profile": False,
        "encrypt": True,
        "clientCertPub": "-----BEGIN PUBLIC KEY-----",
        "clientCertKey": "-----BEGIN PRIVATE KEY-----",
        "host": "",
        "hauth": "",
    }
}

TINFOIL_HEADERS = [
    'Theme',
    'Uid',
    'Version',
    'Revision',
    'Language',
    'Hauth',
    'Uauth'
]

ALLOWED_EXTENSIONS = [
    'nsp',
    'nsz',
    'xci',
    'xcz',
]

APP_TYPE_BASE = 'BASE'
APP_TYPE_UPD = 'UPDATE'
APP_TYPE_DLC = 'DLC'
