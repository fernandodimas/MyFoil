"""
System Routes - Endpoints relacionados ao sistema (stats, backups, etc.)
"""

from flask import Blueprint, render_template, request, jsonify, send_from_directory
import socket
from flask_login import current_user
from sqlalchemy import text
from db import (
    db,
    Apps,
    Titles,
    Libraries,
    Files,
    ActivityLog,
    TitleDBCache,
    get_libraries,
    get_all_unidentified_files,
    logger,
    joinedload,
    Webhook,
)
from app.api_responses import (
    success_response,
    error_response,
    handle_api_errors,
    ErrorCode,
    not_found_response,
)
from app.repositories.titles_repository import TitlesRepository
from app.repositories.files_repository import FilesRepository
from app.repositories.apps_repository import AppsRepository
from app.repositories.systemjob_repository import SystemJobRepository
from app.repositories.activitylog_repository import ActivityLogRepository
from app.repositories.webhook_repository import WebhookRepository
from app.repositories.wishlistignore_repository import WishlistIgnoreRepository

from settings import load_settings
from auth import access_required, admin_account_created
import titles
import titledb
import json
import os
from utils import format_size_py, now_utc, ensure_utc
from metrics import generate_latest, CONTENT_TYPE_LATEST
from constants import BUILD_VERSION, TITLEDB_DIR
import redis
import state
from celery_app import celery as celery_app

system_bp = Blueprint("system", __name__, url_prefix="/api")

# Web routes (não-API)
system_web_bp = Blueprint("system_web", __name__)


@system_bp.route("/health", methods=["GET"])
@handle_api_errors
def health_check_api():
    """
    Health check endpoint for monitoring (Phase 7.2).
    """
    import socket

    try:
        import psutil

        psutil_available = True
    except ImportError:
        psutil_available = False

    start_time = now_utc()
    overall_status = "healthy"
    checks = {
        "timestamp": start_time.isoformat(),
        "version": BUILD_VERSION,
        "hostname": socket.gethostname(),
        "database": "unknown",
        "redis": "unknown",
        "celery": "unknown" if os.environ.get("CELERY_ENABLED", "").lower() != "true" else "checking",
        "filewatcher": "unknown",
    }

    # Disk and memory
    if psutil_available:
        try:
            disk = psutil.disk_usage("/")
            checks["disk_free_gb"] = round(disk.free / (1024**3), 2)
            checks["disk_percent"] = disk.percent
            mem = psutil.virtual_memory()
            checks["memory_used_gb"] = round(mem.used / (1024**3), 2)
            checks["memory_percent"] = mem.percent
        except Exception as e:
            checks["psutil"] = f"error: {str(e)}"

    # Check Database connection
    try:
        db.session.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        checks["database"] = f"error: {str(e)}"
        overall_status = "unhealthy"

    # Check Redis connection (if configured)
    try:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(redis_url)
        r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        if "CELERY_REQUIRED" in os.environ and os.environ["CELERY_REQUIRED"].lower() == "true":
            checks["redis"] = f"error: {str(e)}"
            overall_status = "degraded" if overall_status == "healthy" else "unhealthy"
        else:
            checks["redis"] = "not_configured"

    # Check Celery workers (if enabled)
    try:
        if os.environ.get("CELERY_ENABLED", "").lower() == "true":
            from celery_app import celery as celery_app_

            inspect = celery_app_.control.inspect()
            active = inspect.ping()
            if active:
                checks["celery"] = f"ok ({len(active)} workers)"
            else:
                checks["celery"] = "no_active_workers"
                overall_status = "degraded" if overall_status == "healthy" else "unhealthy"
        else:
            checks["celery"] = "disabled"
    except Exception as e:
        checks["celery"] = f"error: {str(e)}"
        overall_status = "degraded" if overall_status == "healthy" else "unhealthy"

    # Check File Watcher status
    try:
        if state.watcher is not None and hasattr(state.watcher, "is_running"):
            checks["filewatcher"] = "running" if state.watcher.is_running else "stopped"
        else:
            checks["filewatcher"] = "not_initialized"
    except Exception as e:
        checks["filewatcher"] = f"error: {str(e)}"

    # Determine HTTP status code
    status_code = 200 if overall_status == "healthy" else 503

    return success_response(data={"status": overall_status, "checks": checks}, status_code=status_code)


@system_bp.route("/health/ready", methods=["GET"])
@handle_api_errors
def health_ready_api():
    """
    Readiness probe - checks if the application is ready to serve requests.
    """
    db.session.execute(text("SELECT 1"))
    return success_response(data={"status": "ready", "timestamp": now_utc().isoformat()})


@system_bp.route("/health/live", methods=["GET"])
@handle_api_errors
def health_live_api():
    """
    Liveness probe - checks if the application is alive.
    """
    return success_response(data={"status": "alive", "timestamp": now_utc().isoformat()})


@system_bp.route("/cache/info", methods=["GET"])
@access_required("admin")
@handle_api_errors
def get_cache_info_api():
    """
    Get cache information (Phase 4.1).
    """
    from redis_cache import get_cache_info

    info = get_cache_info()
    return success_response(data=info)


@system_bp.post("/cache/clear")
@access_required("admin")
@handle_api_errors
def clear_cache_api():
    """
    Clear all cache entries (Phase 4.1).
    """
    from redis_cache import clear_all_cache

    success = clear_all_cache()
    if success:
        return success_response(message="All cache cleared successfully")
    else:
        return error_response(ErrorCode.INTERNAL_ERROR, message="Failed to clear cache", status_code=500)


@system_bp.post("/cache/invalidate/library")
@access_required("admin")
@handle_api_errors
def invalidate_library_cache_api():
    """
    Invalidate library-related cache entries (Phase 4.1).
    """
    from redis_cache import invalidate_library_cache

    success = invalidate_library_cache()
    if success:
        return success_response(message="Library cache invalidated successfully")
    else:
        return error_response(ErrorCode.INTERNAL_ERROR, message="Failed to invalidate library cache", status_code=500)


@system_bp.post("/cache/reset-stats")
@access_required("admin")
@handle_api_errors
def reset_cache_stats_api():
    """
    Reset cache statistics (Phase 4.1).
    """
    from redis_cache import reset_cache_stats

    reset_cache_stats()
    return success_response(message="Cache statistics reset successfully")


@system_web_bp.route("/stats")
@access_required("shop")
def stats_page():
    """Página de estatísticas"""
    return render_template("stats.html", title="Statistics", build_version=BUILD_VERSION)


@system_web_bp.route("/settings")
@access_required("admin")
def settings_page():
    """Página de configurações"""
    languages = {}
    try:
        languages_path = os.path.join(TITLEDB_DIR, "languages.json")
        if os.path.exists(languages_path):
            with open(languages_path) as f:
                languages = json.load(f)
                languages = dict(sorted(languages.items()))
    except Exception as e:
        logger.warning(f"Could not load languages.json: {e}")

    return render_template(
        "settings.html",
        title="Settings",
        languages_from_titledb=languages,
        admin_account_created=admin_account_created(),
        valid_keys=load_settings()["titles"]["valid_keys"],
        active_source=titledb.get_active_source_info(),
        build_version=BUILD_VERSION,
    )


@system_bp.route("/debug/inspect/<title_id>")
@access_required("admin")
@handle_api_errors
def debug_inspect_title(title_id):
    """Debug endpoint to inspect title/apps/files in DB"""
    title = TitlesRepository.get_by_title_id(title_id)
    if not title:
        return not_found_response("Title", title_id)

    result = {"title": title.name, "id": title.title_id, "apps": []}

    # Use title.apps relationship if available, or repository
    for a in title.apps:
        app_data = {"id": a.app_id, "type": a.app_type, "version": a.app_version, "owned": a.owned, "files": []}

        for f in a.files:
            app_data["files"].append(
                {
                    "filename": f.filename,
                    "filepath": f.filepath,
                    "identified": f.identified,
                    "error": f.identification_error,
                    "size": f.size,
                }
            )
        result["apps"].append(app_data)

    return success_response(data=result)


@system_bp.route("/system/info")
@handle_api_errors
def system_info_api():
    """Informações do sistema (Phase 4.1: Added Redis caching - 1 min TTL)"""
    # Try to get from cache (Phase 4.1)
    try:
        import redis_cache

        if redis_cache.is_cache_enabled():
            cache_key = "system_info"
            cached_data = redis_cache.cache_get(cache_key)
            if cached_data:
                logger.debug("Cache HIT for system_info")
                data = json.loads(cached_data)
                return success_response(data=data)
    except ImportError:
        pass

    # Get system info
    settings = load_settings()

    # Get detailed source info
    source_info = titledb.get_active_source_info()
    source_name = source_info.get("name", "TitleDB") if source_info else "TitleDB"

    titledb_file = titles.get_loaded_titles_file()

    # Check what update source we are using
    update_src = "TitleDB (versions.json)"

    # Identification source - show Source Name + Region File
    if titledb_file != "None":
        id_src = f"{source_name} ({titledb_file})"
    else:
        id_src = f"{source_name} (Não carregado)"

    response_data = {
        "build_version": BUILD_VERSION,
        "id_source": id_src,
        "update_source": update_src,
        "titledb_region": settings.get("titles/region", "US"),
        "titledb_language": settings.get("titles/language", "en"),
        "titledb_file": titledb_file,
    }

    # Cache the response (Phase 4.1)
    try:
        import redis_cache

        if redis_cache.is_cache_enabled():
            redis_cache.cache_set("system_info", response_data, ttl=60)  # 1 min cache
    except ImportError:
        pass

    return success_response(data=response_data)


@system_bp.route("/system/fs/list", methods=["POST"])
@access_required("admin")
@handle_api_errors
def list_filesystem():
    """List local filesystem directories for browser"""
    data = request.get_json() or {}
    path = data.get("path")

    if not path:
        path = os.getcwd()
        if os.name == "posix":
            path = "/"
        else:
            path = "C:\\"

    if not os.path.exists(path):
        return not_found_response("Path", path)

    items = []
    # Parent directory
    parent = os.path.dirname(os.path.abspath(path))
    if parent != path:
        items.append({"name": "..", "path": parent, "type": "dir"})

    with os.scandir(path) as it:
        for entry in it:
            if entry.is_dir() and not entry.name.startswith("."):
                try:
                    items.append({"name": entry.name, "path": entry.path, "type": "dir"})
                except OSError:
                    pass  # Permission denied etc

    # Sort by name
    items.sort(key=lambda x: x["name"])

    return success_response(data={"current_path": os.path.abspath(path), "items": items})


@system_bp.route("/stats")
@access_required("shop")
@handle_api_errors
def get_stats():
    """Retorna estatísticas gerais para o painel"""
    metadata_games = TitlesRepository.count_with_metadata()
    return success_response(data={"metadata_games": metadata_games})


@system_bp.route("/set_language/<lang>", methods=["POST"])
@handle_api_errors
def set_language(lang):
    """Definir idioma da interface"""
    if lang in ["en", "pt_BR"]:
        resp, status = success_response(data={"success": True})
        # Set cookie for 1 year
        resp.set_cookie("language", lang, max_age=31536000)
        return resp, status
    return error_response(ErrorCode.VALIDATION_ERROR, message="Invalid language", status_code=400)


@system_bp.route("/jobs/reset", methods=["POST"])
@access_required("admin")
@handle_api_errors
def reset_jobs_api():
    """Reset manual de todos os jobs travados"""
    from job_tracker import job_tracker

    job_tracker.cleanup_stale_jobs()
    # Reset memory flags
    state.is_titledb_update_running = False
    state.scan_in_progress = False
    return success_response(message="Todos os jobs e flags de memória foram resetados com sucesso.")


@system_bp.route("/system/redis/reset", methods=["POST"])
@access_required("admin")
@handle_api_errors
def reset_redis_api():
    """Flush Redis database and purge Celery tasks"""
    redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    r = redis.from_url(redis_url)
    r.flushdb()

    # Also purge Celery tasks
    count = celery_app.control.purge()

    return success_response(
        data={"purged_count": count},
        message=f"Redis resetado e {count} tarefas removidas da fila Celery.",
    )


@system_bp.route("/system/queue", methods=["GET"])
@handle_api_errors
def get_queue_status_api():
    """Get Celery queue status and active tasks"""
    i = celery_app.control.inspect()
    active = i.active() or {}
    reserved = i.reserved() or {}
    scheduled = i.scheduled() or {}

    # Check registered tasks
    registered_tasks = list(celery_app.tasks.keys())

    return success_response(
        data={
            "active": active,
            "reserved": reserved,
            "scheduled": scheduled,
            "broker": celery_app.connection().as_uri(),
            "registered_tasks": {
                "total": len(registered_tasks),
                "important_tasks": [t for t in registered_tasks if t.startswith("tasks.")],
            },
        }
    )


@system_bp.route("/system/celery/diagnose", methods=["GET"])
@handle_api_errors
def diagnose_celery_api():
    """
    Diagnostic endpoint for Celery worker status.
    """
    diagnosis = {"timestamp": now_utc().isoformat(), "checks": {}}

    # 1. Check CELERY_ENABLED flag
    from app import CELERY_ENABLED

    diagnosis["checks"]["celery_enabled"] = CELERY_ENABLED

    # 2. Check Redis connection
    try:
        redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        r = redis.from_url(redis_url)
        r.ping()
        diagnosis["checks"]["redis_connection"] = "ok"
    except Exception as e:
        diagnosis["checks"]["redis_connection"] = f"error: {str(e)}"

    # 3. Check Celery broker connection
    try:
        inspect = celery_app.control.inspect()
        stats = inspect.stats()
        diagnosis["checks"]["broker_connection"] = "ok"
        diagnosis["checks"]["workers"] = list(stats.keys()) if stats else []
    except Exception as e:
        diagnosis["checks"]["broker_connection"] = f"error: {str(e)}"
        diagnosis["checks"]["workers"] = []

    # 4. Check task registration
    try:
        registered_tasks = list(celery_app.tasks.keys())
        important_tasks = ["tasks.scan_all_libraries_async", "tasks.scan_library_async"]
        task_status = {}
        for task_name in important_tasks:
            task_status[task_name] = task_name in registered_tasks
        diagnosis["checks"]["task_registration"] = task_status
        diagnosis["checks"]["total_registered_tasks"] = len(registered_tasks)
    except Exception as e:
        diagnosis["checks"]["task_registration"] = f"error: {str(e)}"

    # 5. Check for active tasks
    try:
        inspect = celery_app.control.inspect()
        active = inspect.active() or {}
        active_count = sum(len(tasks) for tasks in active.values())
        diagnosis["checks"]["active_tasks"] = active_count
    except Exception as e:
        diagnosis["checks"]["active_tasks"] = f"error: {str(e)}"

    # 6. Check for queued tasks
    try:
        inspect = celery_app.control.inspect()
        reserved = inspect.reserved() or {}
        queued_count = sum(len(tasks) for tasks in reserved.values())
        diagnosis["checks"]["queued_tasks"] = queued_count
    except Exception as e:
        diagnosis["checks"]["queued_tasks"] = f"error: {str(e)}"

    # Determine overall status
    all_ok = True
    for check_name, check_value in diagnosis["checks"].items():
        if isinstance(check_value, str) and check_value.startswith("error"):
            all_ok = False
            break
        if isinstance(check_value, dict) and any(
            v is False or isinstance(v, str) and v.startswith("error") for v in check_value.values()
        ):
            all_ok = False
            break

    diagnosis["overall_status"] = "healthy" if all_ok else "unhealthy"

    return success_response(data={"diagnosis": diagnosis})


@system_bp.route("/system/titledb/test", methods=["POST"])
@access_required("admin")
@handle_api_errors
def test_titledb_sync_api():
    """Run TitleDB update synchronously and return detailed results"""
    from titledb import update_titledb

    settings = load_settings()
    # Run synchronously
    success = update_titledb(settings, force=True)

    # Check cache count
    count = TitlesRepository.count()
    cache_count = TitleDBCache.query.count()

    return success_response(
        data={
            "success": success,
            "titles_in_db": count,
            "titledb_cache_count": cache_count,
        },
        message="Sincronização do TitleDB concluída (Sync)." if success else "Sincronização falhou ou foi parcial.",
    )


@system_bp.route("/system/watchdog/status", methods=["GET"])
@access_required("admin")
@handle_api_errors
def watchdog_status_api():
    """Get watchdog status and health information"""
    if hasattr(state, "watcher") and state.watcher:
        status = state.watcher.get_status()
        return success_response(data=status)
    else:
        return success_response(data={"running": False}, message="Watchdog not initialized")


@system_bp.route("/system/watchdog/restart", methods=["POST"])
@access_required("admin")
@handle_api_errors
def restart_watchdog_api():
    """Manually restart the watchdog observer"""
    if hasattr(state, "watcher") and state.watcher:
        success = state.watcher.restart()
        if success:
            return success_response(message="Watchdog reiniciado com sucesso.")
        else:
            return error_response(ErrorCode.INTERNAL_ERROR, message="Falha ao reiniciar watchdog.", status_code=500)
    else:
        return error_response(ErrorCode.VALIDATION_ERROR, message="Watchdog not initialized", status_code=400)


@system_bp.route("/library/scan", methods=["POST"])
@access_required("admin")
@handle_api_errors
def scan_library_api():
    """Iniciar scan da biblioteca"""
    data = request.json or {}
    path = data.get("path")

    from app import CELERY_ENABLED
    from tasks import scan_library_async, scan_all_libraries_async
    from job_tracker import job_tracker

    active_jobs = job_tracker.get_active_jobs()
    active_scans = [j for j in active_jobs if j.get("type") in ["library_scan", "aggregate_scan"]]

    if active_scans:
        logger.info(f"Skipping scan_library_api call: Scan already in progress (job {active_scans[0]['id']})")
        return error_response(ErrorCode.CONFLICT, message="A scan is already in progress")

    # TitleDB Lock Check
    import state

    with state.titledb_update_lock:
        if state.is_titledb_update_running:
            active_titledb_jobs = [j for j in active_jobs if j.get("type") == "titledb_update"]
            if not active_titledb_jobs:
                logger.warning(
                    "scan_library_api: state.is_titledb_update_running was True but no active job found. Resetting flag."
                )
                state.is_titledb_update_running = False
            else:
                logger.info(
                    f"Skipping scan_library_api: TitleDB update job {active_titledb_jobs[0]['id']} is in progress."
                )
                return error_response(ErrorCode.CONFLICT, message="TitleDB update in progress")

    # Use force_sync for emergencies (e.g. worker down)
    force_sync = data.get("force_sync", False)

    if CELERY_ENABLED and not force_sync:
        if path is None:
            logger.info("Applying scan_all_libraries_async task to Celery...")
            result = scan_all_libraries_async.apply_async()
            logger.info(f"Task queued to Celery. Task ID: {result.id}. Result: {result}")
            from db import log_activity

            log_activity("library_scan_queued", details={"path": "all", "source": "api", "task_id": result.id})
        else:
            logger.info(f"Applying scan_library_async task for path: {path}")
            result = scan_library_async.apply_async(args=[path])
            logger.info(f"Task queued to Celery. Task ID: {result.id}. Result: {result}")
            from db import log_activity

            log_activity("library_scan_queued", details={"path": path, "source": "api", "task_id": result.id})
        return success_response(data={"async": True, "task_id": result.id})
    else:
        # Synchronous mode - Use daemon thread to avoid worker timeout
        import threading
        import state
        from flask import current_app
        from library import scan_library_path, identify_library_files, post_library_change

        # Capture app instance BEFORE creating thread
        app_instance = current_app._get_current_object()

        logger.info(f"Preparing background scan thread (path={path})")

        def run_scan_background():
            """Background scan thread with proper app context"""
            from job_tracker import job_tracker, JobType
            import time

            job_id = f"manual_scan_{int(time.time())}"

            try:
                logger.info(f"Background thread started - creating app context (job_id={job_id})")
                with app_instance.app_context():
                    job_tracker.start_job(job_id, JobType.LIBRARY_SCAN, f"Starting manual scan...")

                    if path is None:
                        # Scan all libraries
                        from db import get_libraries

                        libraries = get_libraries()
                        logger.info(f"Scanning {len(libraries)} libraries")
                        for lib in libraries:
                            logger.debug(f"Scanning library: {lib.path}")
                            scan_library_path(lib.path, job_id=job_id)
                            identify_library_files(lib.path)
                    else:
                        logger.info(f"Scanning single library: {path}")
                        scan_library_path(path, job_id=job_id)
                        identify_library_files(path)

                    logger.info("Running post_library_change...")
                    post_library_change()

                    job_tracker.complete_job(job_id, "Manual scan completed")
                    logger.info(f"Background thread finished successfully (job_id={job_id})")
            except Exception as e:
                logger.exception(f"Background thread failed: {e}")
                with app_instance.app_context():
                    job_tracker.fail_job(job_id, str(e))
            finally:
                with state.scan_lock:
                    state.scan_in_progress = False
                logger.info("Background scan thread exiting")

        with state.scan_lock:
            state.scan_in_progress = True

        scan_thread = threading.Thread(target=run_scan_background, daemon=True, name="LibraryScan")
        scan_thread.start()
        logger.info(f"Background scan thread launched successfully (daemonized)")

        return success_response(
            message=f"Scan started in background thread {'(all)' if path is None else '(path=' + path + ')'}",
            data={"async": False},
        )


@system_bp.route("/files/unidentified")
@access_required("admin")
@handle_api_errors
def get_unidentified_files_api():
    """Obter arquivos não identificados ou com erro"""
    import titles

    results = []
    seen_ids = set()

    # 1. Arquivos com erro explícito ou não identificados
    files = FilesRepository.get_unidentified_or_error()
    for f in files:
        if f.id in seen_ids:
            continue
        seen_ids.add(f.id)
        results.append(
            {
                "id": f.id,
                "filename": f.filename,
                "filepath": f.filepath,
                "size": f.size,
                "size_formatted": format_size_py(f.size),
                "error": f.identification_error or "Arquivo não identificado (ID ausente)",
            }
        )

    # 2. Arquivos com TitleID mas sem reconhecimento de nome (Unknown)
    files_unknown = FilesRepository.get_identified_unknown_titles()
    for f in files_unknown:
        if f.id in seen_ids:
            continue
        seen_ids.add(f.id)
        try:
            tid = f.apps[0].title.title_id
            results.append(
                {
                    "id": f.id,
                    "filename": f.filename,
                    "filepath": f.filepath,
                    "size": f.size,
                    "size_formatted": format_size_py(f.size),
                    "error": f"Título não reconhecido no Banco de Dados ({tid})",
                }
            )
        except (IndexError, AttributeError):
            continue

    return success_response(data=results)


@system_bp.route("/files/all")
@access_required("admin")
@handle_api_errors
def get_all_files_api():
    """Obter todos os arquivos"""
    files = FilesRepository.get_all_optimized()

    results = []
    for f in files:
        title_id = None
        title_name = None
        if f.apps and len(f.apps) > 0:
            try:
                app = f.apps[0]
                if app.title:
                    title_id = app.title.title_id
                    title_name = app.title.name
            except (IndexError, AttributeError):
                pass

        if title_id and not title_name:
            title_name = "Unknown"

        ext = ""
        if f.filename:
            parts = f.filename.rsplit(".", 1)
            if len(parts) > 1:
                ext = parts[1].lower()

        results.append(
            {
                "id": f.id,
                "filename": f.filename,
                "filepath": f.filepath,
                "size": f.size,
                "size_formatted": format_size_py(f.size),
                "extension": ext,
                "identified": f.identified,
                "identification_error": f.identification_error,
                "title_id": title_id,
                "title_name": title_name,
            }
        )

    return success_response(data=results)


@system_bp.route("/files/delete/<int:file_id>", methods=["POST"])
@access_required("admin")
@handle_api_errors
def delete_file_api(file_id):
    """Deletar arquivo específico"""
    file_obj = FilesRepository.get_by_id(file_id)
    if not file_obj:
        return not_found_response("File", file_id)

    title_ids = []
    if file_obj.apps:
        title_ids = list(set([a.title.title_id for a in file_obj.apps if a.title]))

    from db import delete_file_from_db_and_disk

    success, error = delete_file_from_db_and_disk(file_id)

    if success:
        logger.info(f"File {file_id} deleted. Updating cache for titles: {title_ids}")
        from library import invalidate_library_cache, generate_library

        invalidate_library_cache()
        try:
            generate_library(force=True)
            logger.info("Library cache regenerated after file deletion")
        except Exception as gen_err:
            logger.error(f"Error regenerating library cache: {gen_err}")

        try:
            from db import remove_missing_files_from_db

            removed_count = remove_missing_files_from_db()
            if removed_count > 0:
                logger.info(f"Cleaned up {removed_count} orphaned file references after deletion")
        except Exception as cleanup_err:
            logger.error(f"Error during orphaned cleanup: {cleanup_err}")
        return success_response(message="File deleted successfully")
    else:
        logger.warning(f"File deletion failed for {file_id}: {error}")
        return error_response(ErrorCode.INTERNAL_ERROR, message=error, status_code=500)


@system_bp.post("/cleanup/orphaned")
@access_required("admin")
@handle_api_errors
def cleanup_orphaned_apps_api():
    """Limpar registros órfãos e arquivos deletados"""
    results = {"deleted_files": 0, "deleted_apps": 0, "errors": []}

    # 1. Find Files records where file doesn't exist on disk
    all_files = FilesRepository.get_all()
    for file_obj in all_files:
        if file_obj.filepath and not os.path.exists(file_obj.filepath):
            try:
                db.session.delete(file_obj)
                results["deleted_files"] += 1
            except Exception as ex:
                results["errors"].append(f"File {file_obj.id}: {str(ex)}")

    db.session.commit()

    # 2. Find all Apps records where owned=True but no files
    orphaned_apps = AppsRepository.get_orphaned_owned()

    for app_obj in orphaned_apps:
        try:
            db.session.delete(app_obj)
            results["deleted_apps"] += 1
        except Exception as ex:
            results["errors"].append(f"App {app_obj.id}: {str(ex)}")

    db.session.commit()

    # 3. Invalidate library cache
    from library import invalidate_library_cache

    invalidate_library_cache()

    msg = f"{results['deleted_files']} arquivos deletados do disco removidos. {results['deleted_apps']} registros órfãos removidos."
    if results["errors"]:
        msg += f" {len(results['errors'])} erros."

    return success_response(data=results, message=msg)


@system_bp.route("/cleanup/stats")
@access_required("admin")
@handle_api_errors
def cleanup_stats_api():
    """Mostrar estatísticas de itens órfãos"""
    # Count files that don't exist on disk
    missing_files = 0
    all_files = FilesRepository.get_all()
    for file_obj in all_files:
        if file_obj.filepath and not os.path.exists(file_obj.filepath):
            missing_files += 1

    # Count apps with owned=True but no files
    orphaned_apps = AppsRepository.get_orphaned_owned()
    missing_apps = len(orphaned_apps)

    return success_response(
        data={
            "missing_files": missing_files,
            "missing_apps": missing_apps,
            "has_orphaned": missing_files > 0 or missing_apps > 0,
        }
    )


@system_bp.route("/titledb/search")
@access_required("shop")
@handle_api_errors
def search_titledb_api():
    """Buscar no TitleDB"""
    query = request.args.get("q", "").lower()
    if not query or len(query) < 2:
        return success_response(data=[])

    results = titles.search_titledb_by_name(query)
    return success_response(data=results[:20])  # Limit to 20 results


@system_bp.route("/status")
@handle_api_errors
def process_status_api():
    """Status do sistema"""
    # Get status from state module safely (avoid circular import)
    import state

    watching = 0
    if state.watcher is not None:
        try:
            watching = len(getattr(state.watcher, "directories", set()))
        except:
            pass

    # Also check DB for active jobs to support Celery workers report
    has_active_scan = SystemJobRepository.is_job_type_running("library_scan")
    has_active_tdb = SystemJobRepository.is_job_type_running("titledb_update")
    has_active_metadata = SystemJobRepository.is_metadata_job_running()

    return success_response(
        data={
            "scanning": state.scan_in_progress or has_active_scan,
            "updating_titledb": state.is_titledb_update_running or has_active_tdb,
            "fetching_metadata": has_active_metadata,
            "watching": watching > 0,
            "libraries": watching,
        }
    )


@system_bp.post("/settings/titledb/update")
@access_required("admin")
@handle_api_errors
def force_titledb_update_api():
    """Forçar atualização do TitleDB"""
    from app import update_titledb_job
    import threading

    threading.Thread(target=update_titledb_job, args=(True,)).start()
    return success_response(message="Update started in background")


@system_bp.post("/system/reidentify-all")
@access_required("admin")
@handle_api_errors
def reidentify_all_api():
    """Trigger complete re-identification of all files"""
    from library import reidentify_all_files_job
    import threading

    # Run in background thread (although it uses gevent inside, we need to spawn it)
    threading.Thread(target=reidentify_all_files_job).start()

    return success_response(message="Re-identification job started")


@system_bp.post("/settings/titledb/sources/refresh-dates")
@access_required("admin")
@handle_api_errors
def refresh_titledb_sources_dates_api():
    """Atualizar datas remotas das fontes TitleDB"""
    from settings import CONFIG_DIR
    import titledb_sources

    manager = titledb_sources.TitleDBSourceManager(CONFIG_DIR)
    manager.refresh_remote_dates()
    return success_response(message="Datas das fontes TitleDB atualizadas")


@system_bp.route("/titles", methods=["GET"])
@access_required("shop")
@handle_api_errors
def get_all_titles_api():
    """Obter todos os títulos"""
    from library import generate_library

    titles_library = generate_library()

    return success_response(data={"total": len(titles_library), "games": titles_library})


@system_bp.route("/games/<tid>/custom", methods=["GET"])
@access_required("shop")
@handle_api_errors
def get_game_custom_info(tid):
    """Obter informações customizadas do jogo"""
    if not tid:
        return error_response(ErrorCode.VALIDATION_ERROR, message="TitleID missing", status_code=400)

    info = titles.get_custom_title_info(tid)
    return success_response(data=info)


@system_bp.route("/games/<tid>/custom", methods=["POST"])
@access_required("shop")
@handle_api_errors
def update_game_custom_info(tid):
    """Atualizar informações customizadas do jogo"""
    data = request.json
    success, error = titles.save_custom_title_info(tid, data)

    if success:
        # Invalidate library cache so the new info appears immediately
        from library import invalidate_library_cache

        invalidate_library_cache()
        return success_response(message="Custom info updated successfully")
    else:
        return error_response(ErrorCode.INTERNAL_ERROR, message=error, status_code=500)


@system_bp.route("/webhooks")
@access_required("admin")
@handle_api_errors
def get_webhooks_api():
    """Obter webhooks configurados"""
    webhooks = WebhookRepository.get_all()
    return success_response(data=[w.to_dict() for w in webhooks])


@system_bp.post("/webhooks")
@access_required("admin")
@handle_api_errors
def add_webhook_api():
    """Adicionar webhook"""
    data = request.json
    import json

    webhook = WebhookRepository.create(
        url=data["url"],
        events=json.dumps(data.get("events", ["library_updated"])),
        secret=data.get("secret"),
        active=data.get("active", True),
    )

    from app import log_activity

    log_activity("webhook_created", details={"url": webhook.url}, user_id=current_user.id)
    return success_response(data=webhook.to_dict(), message="Webhook added successfully")


@system_bp.delete("/webhooks/<int:id>")
@access_required("admin")
@handle_api_errors
def delete_webhook_api(id):
    """Remover webhook"""
    success = WebhookRepository.delete(id)
    if success:
        return success_response(message="Webhook deleted successfully")
    return not_found_response("Webhook", id)


@system_bp.post("/backup/create")
@access_required("admin")
@handle_api_errors
def create_backup_api():
    """Criar backup manual"""
    from app import backup_manager
    from job_tracker import job_tracker, JobType
    from socket_helper import get_socketio_emitter
    import time

    job_tracker.set_emitter(get_socketio_emitter())

    if not backup_manager:
        return error_response(ErrorCode.INTERNAL_ERROR, message="Backup manager not initialized", status_code=500)

    job_id = f"backup_{int(time.time())}"
    job_tracker.start_job(job_id, JobType.BACKUP, "Creating manual backup")

    success, timestamp = backup_manager.create_backup()
    if success:
        job_tracker.complete_job(job_id, f"Backup created: {timestamp}")
        return success_response(data={"timestamp": timestamp}, message="Backup created successfully")
    else:
        job_tracker.fail_job(job_id, "Backup creation failed")
        return error_response(ErrorCode.INTERNAL_ERROR, message="Backup failed", status_code=500)


@system_bp.get("/backup/list")
@access_required("admin")
@handle_api_errors
def list_backups_api():
    """Listar backups disponíveis"""
    from app import backup_manager

    if not backup_manager:
        return error_response(ErrorCode.INTERNAL_ERROR, message="Backup manager not initialized", status_code=500)

    backups = backup_manager.list_backups()
    return success_response(data={"backups": backups})


@system_bp.post("/backup/restore")
@access_required("admin")
@handle_api_errors
def restore_backup_api():
    """Restaurar backup"""
    from app import backup_manager
    from job_tracker import job_tracker, JobType
    from socket_helper import get_socketio_emitter
    import time

    job_tracker.set_emitter(get_socketio_emitter())

    if not backup_manager:
        return error_response(ErrorCode.INTERNAL_ERROR, message="Backup manager not initialized", status_code=500)

    data = request.json
    filename = data.get("filename")

    if not filename:
        return error_response(ErrorCode.VALIDATION_ERROR, message="Filename required", status_code=400)

    job_id = f"restore_{int(time.time())}"
    job_tracker.start_job(job_id, JobType.BACKUP, f"Restoring {filename}")

    success = backup_manager.restore_backup(filename)
    if success:
        job_tracker.complete_job(job_id, "Restore successful. Restart recommended.")
        return success_response(message=f"Restored from {filename}. Please restart the application.")
    else:
        job_tracker.fail_job(job_id, "Restore failed")
        return error_response(ErrorCode.INTERNAL_ERROR, message="Restore failed", status_code=500)


@system_bp.route("/backup/download/<filename>")
@access_required("admin")
@handle_api_errors
def download_backup_api(filename):
    """Download a backup file"""
    from app import backup_manager

    if not backup_manager:
        return error_response(ErrorCode.INTERNAL_ERROR, message="Backup manager not initialized", status_code=500)

    return send_from_directory(backup_manager.backup_dir, filename, as_attachment=True, download_name=filename)


@system_bp.delete("/backup/<filename>")
@access_required("admin")
@handle_api_errors
def delete_backup_api(filename):
    """Delete a backup file"""
    from app import backup_manager

    if not backup_manager:
        return error_response(ErrorCode.INTERNAL_ERROR, message="Backup manager not initialized", status_code=500)

    success = backup_manager.delete_backup(filename)
    if success:
        return success_response(message="Backup deleted successfully")
    else:
        return error_response(ErrorCode.INTERNAL_ERROR, message="Delete failed", status_code=500)


@system_bp.route("/activity", methods=["GET"])
@access_required("admin")
@handle_api_errors
def activity_api():
    """Obter log de atividades"""
    limit = request.args.get("limit", 50, type=int)
    logs = ActivityLogRepository.get_recent(limit=limit)

    import json

    results = []
    for l in logs:
        results.append(
            {
                "timestamp": l.timestamp.isoformat(),
                "action": l.action_type,
                "title_id": l.title_id,
                "user": l.user_id,  # Simplified
                "details": json.loads(l.details) if l.details else {},
            }
        )
    return success_response(data=results)


@system_bp.route("/plugins", methods=["GET"])
@access_required("admin")
@handle_api_errors
def plugins_api():
    """Obter lista de plugins"""
    from app import plugin_manager

    if not plugin_manager:
        return success_response(data=[])

    # Return all discovered plugins with their enabled status
    return success_response(data=plugin_manager.discovered_plugins)


@system_bp.post("/plugins/toggle")
@access_required("admin")
@handle_api_errors
def toggle_plugin_api():
    """Alternar status do plugin"""
    data = request.json
    plugin_id = data.get("id")
    enabled = data.get("enabled", True)

    if not plugin_id:
        return error_response(ErrorCode.VALIDATION_ERROR, message="Plugin ID required", status_code=400)

    # 1. Update settings file
    import settings

    settings.toggle_plugin_settings(plugin_id, enabled)

    # 2. Reload plugins in the manager to reflect changes
    from app import plugin_manager

    disabled_plugins = load_settings(force=True).get("plugins", {}).get("disabled", [])
    plugin_manager.load_plugins(disabled_plugins)

    return success_response(message=f"Plugin {'enabled' if enabled else 'disabled'} successfully")


@system_bp.route("/system/jobs", methods=["GET"])
@handle_api_errors
def get_all_jobs_api():
    """Retorna status de todos os jobs recentes"""
    from job_tracker import job_tracker

    # job_tracker now returns list of dicts from DB
    jobs = job_tracker.get_all_jobs()

    # Add TitleDB status info
    titledb_status = titledb.get_active_source_info()

    return success_response(
        data={
            "jobs": jobs,  # Now already in dict format with to_dict()
            "titledb": titledb_status,
        }
    )


@system_bp.route("/system/metadata/fetch", methods=["POST"])
@access_required("admin")
@handle_api_errors
def trigger_metadata_fetch():
    """Trigger manual metadata fetch for all games"""
    from metadata_service import metadata_fetcher
    import threading
    from flask import current_app, request
    from app import CELERY_ENABLED

    data = request.json or {}
    force = data.get("force", False)

    if CELERY_ENABLED:
        from tasks import fetch_all_metadata_async

        fetch_all_metadata_async.apply_async(args=[force])
        logger.info("Queued async metadata fetch (Celery)")
        return success_response(message="Metadata fetch queued in background (Celery)")
    else:
        app_instance = current_app._get_current_object()

        def run_metadata_fetch():
            with app_instance.app_context():
                try:
                    metadata_fetcher.fetch_all_metadata(force=force)
                except Exception as e:
                    logger.error(f"Background metadata fetch failed: {e}")
                finally:
                    from db import db

                    db.session.remove()

        thread = threading.Thread(target=run_metadata_fetch, name="MetadataFetch")
        thread.daemon = True
        thread.start()
        logger.info("Background metadata fetch thread started (no Celery)")

        return success_response(message="Metadata fetch started in background thread")


@system_bp.route("/system/metadata/status", methods=["GET"])
@handle_api_errors
def get_metadata_status():
    """Get summarized status of metadata fetch service"""
    from db import MetadataFetchLog

    last_fetch = MetadataFetchLog.query.order_by(MetadataFetchLog.started_at.desc()).first()

    status_data = {
        "has_run": last_fetch is not None,
        "last_fetch": {
            "started_at": last_fetch.started_at.isoformat() if last_fetch else None,
            "completed_at": last_fetch.completed_at.isoformat() if last_fetch and last_fetch.completed_at else None,
            "status": last_fetch.status if last_fetch else None,
            "processed": last_fetch.titles_processed if last_fetch else 0,
            "updated": last_fetch.titles_updated if last_fetch else 0,
            "failed": last_fetch.titles_failed if last_fetch else 0,
        }
        if last_fetch
        else None,
    }
    return success_response(data=status_data)


@system_bp.route("/system/jobs/<job_id>/cancel", methods=["POST"])
@access_required("admin")
@handle_api_errors
def cancel_job(job_id):
    """Cancela um job em execução marcando-o como failed no banco de dados"""
    from job_tracker import job_tracker

    # This will update DB and handle in-memory cancellation set
    job_tracker.cancel_job(job_id)

    return success_response(message="Job cancelled")


@system_bp.route("/files/debug", methods=["GET"])
@access_required("admin")
@handle_api_errors
def debug_files_api():
    """Diagnostic endpoint to see what's in the files table"""
    count = FilesRepository.count()
    last_files = FilesRepository.get_all_optimized()[:20]  # Just use the first 20 for debug

    files_data = []
    for f in last_files:
        files_data.append(
            {
                "id": f.id,
                "filename": f.filename,
                "filepath": f.filepath,
                "folder": f.folder,
                "identified": f.identified,
                "size": f.size,
                "error": f.identification_error,
                "attempts": f.identification_attempts,
            }
        )

    return success_response(data={"total_count": count, "last_20_files": files_data})


@system_bp.route("/system/jobs/cleanup", methods=["POST"])
@access_required("admin")
@handle_api_errors
def cleanup_jobs_api():
    """Limpa jobs antigos (>24h) ou todos os jobs completados e cancela jobs presos"""
    from job_tracker import job_tracker
    from db import SystemJob

    # 1. Cancel ALL currently running jobs
    running_jobs = SystemJob.query.filter(SystemJob.status == "running").all()
    for job in running_jobs:
        logger.warning(f"Forcing cancellation of job {job.job_id} during cleanup")
        job_tracker.cancel_job(job.job_id)

    # 2. History cleanup
    job_tracker.cleanup_old_jobs(max_age_hours=24)

    return success_response(message=f"Cancelled {len(running_jobs)} running jobs and cleaned history")


@system_bp.route("/system/diagnostic", methods=["GET"])
@access_required("admin")
@handle_api_errors
def diagnostic_info():
    """Comprehensive system diagnostic for debugging job tracking issues"""
    from job_tracker import job_tracker
    from app import socketio
    import sys

    diagnostic = {
        "process": {
            "pid": os.getpid(),
            "argv": sys.argv,
        },
        "environment": {
            "redis_url": os.environ.get("REDIS_URL"),
            "redis_url_configured": os.environ.get("REDIS_URL") is not None,
        },
        "job_tracker": {
            "redis_connected": job_tracker.use_redis,
            "redis_url_actual": job_tracker.redis_url,
            "emitter_configured": job_tracker._emitter is not None,
        },
        "socketio": {
            "initialized": socketio is not None,
            "message_queue": os.environ.get("REDIS_URL"),
        },
        "jobs": job_tracker.get_status(),
    }

    # Test Redis connection
    if job_tracker.use_redis:
        try:
            job_tracker.redis.ping()
            diagnostic["redis_test"] = "✅ PING successful"
        except Exception as e:
            diagnostic["redis_test"] = f"❌ PING failed: {str(e)}"
    else:
        diagnostic["redis_test"] = "⚠️ Not using Redis"

    return success_response(data=diagnostic)


# === Cloud Sync Placeholders (Feature Removed) ===
# The cloud sync feature has been removed in v2.2.0 due to obsolescence and maintenance burden.
# These placeholder endpoints prevent 404 errors in the frontend that still references them.


@system_bp.route("/cloud/status", methods=["GET"])
@handle_api_errors
def cloud_status_placeholder():
    """
    Placeholder endpoint for cloud status.
    Returns disabled status to prevent errors in frontend.
    """
    return success_response(
        data={
            "gdrive": {"authenticated": False, "enabled": False, "message": "Cloud sync feature removed in v2.2.0"},
            "dropbox": {"authenticated": False, "enabled": False, "message": "Cloud sync feature removed in v2.2.0"},
        }
    )


@system_bp.route("/cloud/auth/<provider>", methods=["GET"])
@handle_api_errors
def cloud_auth_placeholder(provider):
    """
    Placeholder endpoint for cloud authentication.
    """
    return success_response(message=f"Cloud sync feature removed. Provider {provider} is no longer supported.")

    Returns error indicating feature has been removed.
    """
    return jsonify(
        {
            "error": f"Cloud sync for {provider} has been removed in MyFoil v2.2.0",
            "message": "The cloud sync feature was removed due to obsolescence and maintenance burden. Please use local backups and file transfers instead.",
        }
    ), 503


# === Database Migration Endpoints (Phase 2.1 & 2.3) ===
# Endpoints to apply database migrations for performance optimization


@system_bp.route("/system/migrate/status", methods=["GET"])
@access_required("admin")
def migration_status():
    """
    Get current database migration status.
    Returns the current revision and available migrations.
    """
    from flask_migrate import current
    from flask import current_app

    try:
        with current_app.app_context():
            current_rev = current()
            return jsonify(
                {"success": True, "current_revision": current_rev or "None", "message": "Migration status retrieved"}
            )
    except Exception as e:
        logger.error(f"Error getting migration status: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route("/system/migrate/upgrade", methods=["POST"])
@access_required("admin")
def migrate_database():
    """
    Apply pending database migrations.
    This endpoint upgrades the database schema to the latest version.

    Optional query parameters:
    - revision: Target migration revision (defaults to 'head')
    """
    from flask_migrate import upgrade
    from flask import current_app

    try:
        revision = request.args.get("revision", "head")

        with current_app.app_context():
            logger.info(f"Initiating database migration to revision: {revision}")
            upgrade(revision=revision)

            return jsonify(
                {
                    "success": True,
                    "message": f"Database migrated to revision: {revision}",
                    "details": "Migration applied successfully. Check application logs for details.",
                }
            )
    except Exception as e:
        logger.error(f"Error during migration: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route("/system/migrate/stamp", methods=["POST"])
@access_required("admin")
def migrate_stamp():
    """
    Stamp the database with a specific revision without running it.
    Useful for fixing migration history on existing databases.
    """
    from flask_migrate import stamp
    from flask import current_app, request

    revision = request.args.get("revision", "head")

    try:
        with current_app.app_context():
            logger.info(f"Stamping database with revision: {revision}")
            stamp(revision=revision)
            return jsonify({"success": True, "message": f"Database stamped with revision: {revision}"})
    except Exception as e:
        logger.error(f"Error stamping database: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route("/system/migrate/phase-2-1", methods=["POST"])
@access_required("admin")
def migrate_phase_2_1():
    """
    Apply Phase 2.1 migration: Composite indexes for performance optimization.

    This migration adds indexes to optimize:
    - Stats queries (5-10x faster)
    - Outdated games query (3-5x faster)
    - File size queries (2-3x faster)

    No authentication required for migration operations (access_required only).
    """
    from flask_migrate import upgrade
    from flask import current_app

    try:
        with current_app.app_context():
            logger.info("Applying Phase 2.1 migration: Composite indexes (b2c3d4e5f9g1)")
            upgrade(revision="b2c3d4e5f9g1")

            logger.info("Phase 2.1 migration applied successfully")

            return jsonify(
                {
                    "success": True,
                    "message": "Phase 2.1 migration applied: Composite indexes created",
                    "revision": "b2c3d4e5f9g1",
                    "indexes": [
                        "idx_files_library_id",
                        "idx_files_identified",
                        "idx_files_size",
                        "idx_titles_up_to_date_have_base",
                        "idx_titles_have_base",
                        "idx_titles_up_to_date",
                        "idx_titles_have_base_added_at",
                        "idx_apps_title_id_owned",
                        "idx_apps_title_id_type_owned",
                    ],
                    "performance_improvements": {
                        "stats_queries": "5-10x faster",
                        "outdated_games": "3-5x faster",
                        "file_size": "2-3x faster",
                    },
                }
            )
    except Exception as e:
        logger.error(f"Error during Phase 2.1 migration: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# === Celery Worker Testing (Phase 2.1) ===
# Endpoints to test Celery worker connectivity and task execution


@system_bp.route("/system/celery/test", methods=["POST"])
@access_required("admin")
def test_celery_worker():
    """
    Test Celery worker functionality.

    This endpoint:
    1. Checks if Celery is enabled
    2. Pings active workers
    3. Executes a simple test task
    4. Returns worker statistics

    Returns diagnostic information about worker health.
    """
    from celery_app import celery as celery_app

    try:
        if os.environ.get("CELERY_ENABLED", "").lower() != "true":
            return jsonify(
                {"success": False, "message": "Celery is not enabled in this environment", "celery_enabled": False}
            ), 400

        logger.info("Testing Celery worker connectivity")

        diagnostic = {
            "success": True,
            "celery_enabled": True,
            "worker_status": "unknown",
            "test_task_result": "not_executed",
            "active_workers": 0,
            "queued_tasks": 0,
            "running_tasks": 0,
        }

        # 1. Inspect workers
        inspect = celery_app.control.inspect()
        stats = inspect.stats()

        if stats:
            diagnostic["worker_status"] = "ok"
            diagnostic["active_workers"] = len(stats)
            diagnostic["worker_details"] = stats

        # 2. Check active tasks
        active = inspect.active()
        if active:
            total_running = sum(len(tasks) for tasks in active.values())
            diagnostic["running_tasks"] = total_running

        # 3. Check scheduled tasks
        scheduled = inspect.scheduled()
        if scheduled:
            total_scheduled = sum(len(tasks) for tasks in scheduled.values())
            diagnostic["queued_tasks"] += total_scheduled

        # 4. Check reserved tasks
        reserved = inspect.reserved()
        if reserved:
            total_reserved = sum(len(tasks) for tasks in reserved.values())
            diagnostic["queued_tasks"] += total_reserved

        return jsonify({"success": True, "message": "Celery worker is functioning normally", "diagnostic": diagnostic})

    except Exception as e:
        logger.error(f"Error testing Celery worker: {e}")
        return jsonify(
            {
                "success": False,
                "error": str(e),
                "celery_enabled": os.environ.get("CELERY_ENABLED", "").lower() == "true",
            }
        ), 500


@system_bp.route("/system/celery/scan-test", methods=["POST"])
@access_required("admin")
def test_scan_task():
    """
    Test Celery scan task execution.

    This endpoint triggers a simple scan task to verify:
    1. Worker can receive tasks
    2. Task execution completes successfully
    3. Job tracking works correctly

    Returns job ID for tracking task progress.
    """
    from tasks import scan_all_libraries_async
    from job_tracker import job_tracker

    try:
        if os.environ.get("CELERY_ENABLED", "").lower() != "true":
            return jsonify({"success": False, "message": "Celery is not enabled in this environment"}), 400

        logger.info("Triggering test scan task")

        # Queue the task
        result = scan_all_libraries_async.delay()

        logger.info(f"Test scan task queued: {result.id}")

        return jsonify(
            {
                "success": True,
                "message": "Test scan task queued successfully",
                "task_id": result.id,
                "job_url": f"/api/system/jobs/{result.id}",
            }
        )

    except Exception as e:
        logger.error(f"Error queuing test scan task: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


# === PROMETHEUS METRICS (Phase 3.2: Metrics & Monitoring) ===
@system_bp.route("/metrics")
@access_required("admin")
def prometheus_metrics():
    """
    Prometheus metrics endpoint for application monitoring.

    Exposes metrics in Prometheus format for monitoring:
    - Database counts (files, titles, apps, libraries)
    - Performance metrics (library load time, query time)
    - System metrics (disk usage, connections)
    - Task metrics (identification, Celery)

    Metrics available:
    - myfoil_files_total: Total number of files
    - myfoil_titles_total: Total number of titles
    - myfoil_apps_total: Total number of apps
    - myfoil_libraries_total: Total number of libraries
    - myfoil_files_identified_total: Successfully identified files
    - myfoil_files_unidentified_total: Files not yet identified
    - myfoil_files_with_errors_total: Files with identification errors
    - myfoil_library_load_duration_seconds: Histogram of library load times
    - myfoil_identification_duration_seconds: Histogram of identification times
    - myfoil_api_request_duration_seconds: Histogram of API request times
    - myfoil_system_disk_total_bytes: Total disk space per library
    - myfoil_system_disk_free_bytes: Free disk space per library
    """
    from app.metrics import get_metrics_export

    # Refresh metrics before export
    try:
        from app.metrics import update_db_metrics, update_library_metrics, update_system_metrics

        update_db_metrics()
        update_library_metrics()
        update_system_metrics()
    except Exception as e:
        logger.error(f"Error refreshing metrics: {e}")

    return get_metrics_export()


@system_bp.route("/metrics/health")
def health_check():
    """
    Health check endpoint for monitoring services.

    Returns service health status for monitoring:
    - Database connection
    - Library cache
    - Celery worker (if enabled)

    Example response:
    {
        "status": "healthy",
        "timestamp": "2024-02-09T17:00:00Z",
        "database": "connected",
        "cache": "working",
        "celery": "running"
    }
    """
    from flask import current_app, jsonify
    from sqlalchemy import text
    import datetime

    health_status = {
        "status": "healthy",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z",
        "database": "disconnected",
        "cache": "unknown",
        "metrics": "disabled",
    }

    try:
        with current_app.app_context():
            # Check database
            with db.engine.connect() as conn:
                conn.execute(text("SELECT 1"))
                health_status["database"] = "connected"
    except Exception as e:
        health_status["database"] = f"error: {e}"
        health_status["status"] = "degraded"

    # Check library cache
    try:
        from app.library import load_library_from_disk

        cache = load_library_from_disk()
        if cache and "hash" in cache:
            health_status["cache"] = "working"
        else:
            health_status["cache"] = "not generated"
    except Exception as e:
        health_status["cache"] = f"error: {e}"

    # Check Celery (if enabled)
    try:
        import os

        if os.environ.get("CELERY_ENABLED", "").lower() == "true":
            health_status["celery"] = "enabled"
        else:
            health_status["celery"] = "disabled"
    except:
        health_status["celery"] = "disabled"

    # Check metrics
    try:
        from app.metrics import get_metrics_export

        health_status["metrics"] = "enabled"
    except:
        health_status["metrics"] = "disabled"

    status_code = 200 if health_status["status"] == "healthy" else 503
    return jsonify(health_status), status_code
