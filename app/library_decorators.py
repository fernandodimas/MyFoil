"""
Decorators for timing library scan and identification operations
Phase 3.1: Add Prometheus metrics for scan/identification duration
"""

import time
import functools


def timed_scan(func):
    """Decorator to time library scan operations and record to Prometheus"""

    @functools.wraps(func)
    def wrapper(library_path, *args, **kwargs):
        from metrics import scan_duration_seconds
        import os

        scan_start = time.time()
        status = "success"

        try:
            result = func(library_path, *args, **kwargs)
            return result
        except Exception as e:
            status = "error"
            raise
        finally:
            try:
                scan_duration = time.time() - scan_start
                lib_label = os.path.basename(library_path) or str(library_path)
                scan_duration_seconds.labels(library=lib_label, status=status).observe(scan_duration)
            except:
                pass

    return wrapper


def timed_identification(func):
    """Decorator to time file identification operations and record to Prometheus"""

    @functools.wraps(func)
    def wrapper(library_or_filepath, *args, **kwargs):
        from metrics import identification_duration_seconds
        import os

        identify_start = time.time()

        # Determine label and type
        if isinstance(library_or_filepath, str) and os.path.isfile(library_or_filepath):
            # Single file identification
            label = os.path.basename(library_or_filepath)
            ident_type = "single"
        else:
            # Batch library identification
            label = os.path.basename(str(library_or_filepath)) or "unknown"
            ident_type = "batch"

        try:
            result = func(library_or_filepath, *args, **kwargs)
            return result
        except Exception as e:
            raise
        finally:
            try:
                identify_duration = time.time() - identify_start
                identification_duration_seconds.labels(library=label, type=ident_type).observe(identify_duration)
            except:
                pass

    return wrapper
