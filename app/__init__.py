# Makes `app` a Python package so imports like `from metrics import ...` work.
"""
Package-level attribute resolution for backward compatibility with older imports
referencing symbols from `app.py` or `app_factory.py`.
"""

def __getattr__(name):
    # Try importing from app.app first
    try:
        import app.app as _app_module
        if hasattr(_app_module, name):
            val = getattr(_app_module, name)
            globals()[name] = val
            return val
    except Exception:
        pass

    # Try importing from app.app_factory next
    try:
        import app.app_factory as _factory_module
        if hasattr(_factory_module, name):
            val = getattr(_factory_module, name)
            globals()[name] = val
            return val
    except Exception:
        pass

    raise AttributeError(f"module 'app' has no attribute '{name}'")
