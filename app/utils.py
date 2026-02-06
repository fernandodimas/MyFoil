import logging
import re
import threading
from functools import wraps
import json
import os
import tempfile
from datetime import datetime, timezone

# Global lock for all JSON writes in this process
_json_write_lock = threading.Lock()

# Custom logging formatter to support colors
class ColoredFormatter(logging.Formatter):
    # Define color codes
    COLORS = {
        'DEBUG': '\033[94m',   # Blue
        'INFO': '\033[92m',    # Green
        'WARNING': '\033[93m', # Yellow
        'ERROR': '\033[91m',   # Red
        'CRITICAL': '\033[95m' # Magenta
    }
    RESET = '\033[0m'  # Reset color

    def format(self, record):
        # Add color to the log level name
        levelname = record.levelname
        if levelname in self.COLORS:
            record.levelname = f"{self.COLORS[levelname]}{levelname}{self.RESET}"
        
        return super().format(record)
    
# Filter to remove date from http access logs
class FilterRemoveDateFromWerkzeugLogs(logging.Filter):
    # '192.168.0.102 - - [30/Jun/2024 01:14:03] "%s" %s %s' -> '192.168.0.102 - "%s" %s %s'
    pattern: re.Pattern = re.compile(r' - - \[.+?] "')

    def filter(self, record: logging.LogRecord) -> bool:
        record.msg = self.pattern.sub(' - "', record.msg)
        return True


def get_or_create_secret_key():
    """
    Generate or load a persistent secret key for Flask sessions.
    The key is stored in CONFIG_DIR/.secret_key with restricted permissions.
    
    Returns:
        str: 64-character hex secret key
    """
    import secrets
    from constants import CONFIG_DIR
    
    logger = logging.getLogger('main')
    secret_key_file = os.path.join(CONFIG_DIR, '.secret_key')
    
    # Try to load existing key
    if os.path.exists(secret_key_file):
        try:
            with open(secret_key_file, 'r') as f:
                key = f.read().strip()
                if len(key) == 64:  # Validate key length
                    return key
                logger.warning("Invalid secret key found, generating new one")
        except Exception as e:
            logger.error(f"Error reading secret key: {e}")
    
    # Generate new key
    key = secrets.token_hex(32)  # 32 bytes = 64 hex chars
    
    try:
        # Ensure CONFIG_DIR exists
        os.makedirs(CONFIG_DIR, exist_ok=True)
        
        # Write key with restricted permissions
        with open(secret_key_file, 'w') as f:
            f.write(key)
        
        # Set file permissions to 600 (owner read/write only)
        os.chmod(secret_key_file, 0o600)
        
        logger.info("Generated new secret key and saved to disk")
    except Exception as e:
        logger.error(f"Error saving secret key: {e}")
        logger.warning("Using non-persistent secret key")
    
    return key


def sanitize_sensitive_data(data, sensitive_keys=None):
    """
    Remove or mask sensitive data before logging.
    
    Args:
        data: Dictionary, string, or other data to sanitize
        sensitive_keys: List of keys to mask (default: common sensitive keys)
        
    Returns:
        Sanitized version of the data
    """
    if sensitive_keys is None:
        sensitive_keys = [
            'password', 'passwd', 'pwd',
            'secret', 'secret_key', 'api_key', 'apikey',
            'token', 'access_token', 'refresh_token',
            'key', 'private_key', 'session',
            'authorization', 'auth',
            'credit_card', 'cvv', 'ssn'
        ]
    
    if isinstance(data, dict):
        sanitized = {}
        for k, v in data.items():
            key_lower = k.lower()
            # Check if key contains any sensitive keyword
            is_sensitive = any(sens in key_lower for sens in sensitive_keys)
            
            if is_sensitive:
                # Show only first 2 and last 2 chars if string, else mask completely
                if isinstance(v, str) and len(v) > 4:
                    sanitized[k] = f"{v[:2]}***{v[-2:]}"
                else:
                    sanitized[k] = "***"
            elif isinstance(v, dict):
                sanitized[k] = sanitize_sensitive_data(v, sensitive_keys)
            elif isinstance(v, list):
                sanitized[k] = [sanitize_sensitive_data(item, sensitive_keys) if isinstance(item, (dict, list)) else item for item in v]
            else:
                sanitized[k] = v
        return sanitized
    
    elif isinstance(data, list):
        return [sanitize_sensitive_data(item, sensitive_keys) if isinstance(item, (dict, list)) else item for item in data]
    
    elif isinstance(data, str):
        # Check if string looks like a password/token (heuristic)
        if len(data) > 16 and any(c.isdigit() for c in data) and any(c.isalpha() for c in data):
            return f"{data[:2]}***{data[-2:]}"
        return data
    
    return data


def debounce(wait):
    """Decorator that postpones a function's execution until after `wait` seconds
    have elapsed since the last time it was invoked."""
    def decorator(fn):
        @wraps(fn)
        def debounced(*args, **kwargs):
            def call_it():
                fn(*args, **kwargs)
            if hasattr(debounced, '_timer'):
                debounced._timer.cancel()
            debounced._timer = threading.Timer(wait, call_it)
            debounced._timer.start()
        return debounced
    return decorator

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ['keys', 'txt']

def safe_write_json(path, data, **dump_kwargs):
    with _json_write_lock:
        dirpath = os.path.dirname(path) or "."
        # Default options
        options = {'ensure_ascii': False, 'indent': 2}
        options.update(dump_kwargs)
        
        # Create temporary file in same directory
        with tempfile.NamedTemporaryFile("w", dir=dirpath, delete=False, encoding="utf-8") as tmp:
            tmp_path = tmp.name
            json.dump(data, tmp, **options)
            tmp.flush()
            os.fsync(tmp.fileno())  # flush to disk
        # Atomically replace target file
        os.replace(tmp_path, path)

def format_size_py(size):
    if size is None: return "0 B"
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

def now_utc():
    """Returns current datetime in UTC (aware)"""
    return datetime.now(timezone.utc)

def ensure_utc(dt):
    """
    Ensure a datetime object is aware and in UTC.
    Extremely robust version: handles ISO strings, None, and naive datetimes.
    """
    if dt is None:
        return None
    
    # Handle strings (ISO format)
    if isinstance(dt, str):
        try:
            # Try parsing ISO format
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except (ValueError, TypeError, AttributeError):
            return None

    # Final check: is it a datetime-like object?
    # We use hasattr because some libraries use proxy objects
    if not hasattr(dt, 'tzinfo'):
        return None

    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    
    return dt.astimezone(timezone.utc)


def get_local_timezone():
    """Returns the local timezone of the system"""
    return datetime.now().astimezone().tzinfo


def format_datetime(dt, format="%Y-%m-%d %H:%M:%S"):
    """
    Formats a datetime object to the local timezone.
    If dt is naive, it's assumed to be UTC.
    """
    if dt is None:
        return "Nunca"
    
    if isinstance(dt, str):
        try:
            dt = datetime.fromisoformat(dt.replace('Z', '+00:00'))
        except:
            return dt
            
    # Ensure dt is aware. If naive, assume UTC.
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    
    # Convert to local timezone
    local_dt = dt.astimezone(get_local_timezone())
    return local_dt.strftime(format)