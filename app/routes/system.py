"""
System Routes - Endpoints relacionados ao sistema (stats, backups, etc.)
"""

from flask import Blueprint, render_template, request, jsonify, Response, send_from_directory
from flask_login import current_user
from db import db, Apps, Titles, Libraries, Files, ActivityLog, get_libraries, get_all_unidentified_files, logger, joinedload, Webhook
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


@system_bp.route("/metrics")
def metrics():
    """Endpoint de métricas Prometheus"""
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


@system_bp.route("/system/info")
def system_info_api():
    """Informações do sistema"""
    from settings import load_settings

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

    return jsonify(
        {
            "build_version": BUILD_VERSION,
            "id_source": id_src,
            "update_source": update_src,
            "titledb_region": settings.get("titles/region", "US"),
            "titledb_language": settings.get("titles/language", "en"),
            "titledb_file": titledb_file,
        }
    )



@system_bp.route("/system/fs/list", methods=["POST"])
@access_required("admin")
def list_filesystem():
    """List local filesystem directories for browser"""
    data = request.get_json() or {}
    path = data.get("path")
    
    if not path:
        path = os.getcwd()
        # On macOS/Linux start at root if not specified, or home?
        # Let's start at root if explicitly requested or empty.
        # Actually, let's default to root / on unix
        if os.name == 'posix':
            path = "/"
        else:
            path = "C:\\"

    if not os.path.exists(path):
        return jsonify({"error": "Path does not exist"}), 404
        
    try:
        items = []
        # Parent directory
        parent = os.path.dirname(os.path.abspath(path))
        if parent != path:
             items.append({"name": "..", "path": parent, "type": "dir"})
             
        with os.scandir(path) as it:
            for entry in it:
                if entry.is_dir() and not entry.name.startswith('.'):
                    try:
                        items.append({
                            "name": entry.name,
                            "path": entry.path,
                            "type": "dir"
                        })
                    except OSError:
                        pass # Permission denied etc
        
        # Sort by name
        items.sort(key=lambda x: x["name"])
        
        return jsonify({
            "current_path": os.path.abspath(path),
            "items": items
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500


@system_bp.route("/stats")
@access_required("shop")
def get_stats():
    """Retorna estatísticas gerais para o painel"""
    # Contagem de jogos com metadados enriquecidos
    metadata_games = Titles.query.filter(
        (Titles.metacritic_score.isnot(None)) | (Titles.rawg_rating.isnot(None))
    ).count()

    return jsonify({"metadata_games": metadata_games})


@system_bp.route("/set_language/<lang>", methods=["POST"])
def set_language(lang):
    """Definir idioma da interface"""
    if lang in ["en", "pt_BR"]:
        resp = jsonify({"success": True})
        # Set cookie for 1 year
        resp.set_cookie("language", lang, max_age=31536000)
        return resp
    return jsonify({"success": False, "error": "Invalid language"}), 400


@system_bp.route("/jobs/reset", methods=["POST"])
@access_required("admin")
def reset_jobs_api():
    """Reset manual de todos os jobs travados"""
    from job_tracker import job_tracker
    try:
        job_tracker.cleanup_stale_jobs()
        # Reset memory flags
        state.is_titledb_update_running = False
        state.scan_in_progress = False
        return jsonify({"success": True, "message": "Todos os jobs e flags de memória foram resetados com sucesso."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Erro ao resetar jobs: {e}"}), 500


@system_bp.route("/system/redis/reset", methods=["POST"])
@access_required("admin")
def reset_redis_api():
    """Flush Redis database and purge Celery tasks"""
    try:
        redis_url = os.environ.get('REDIS_URL', 'redis://localhost:6379/0')
        r = redis.from_url(redis_url)
        r.flushdb()
        
        # Also purge Celery tasks
        count = celery_app.control.purge()
        
        return jsonify({
            "success": True, 
            "message": f"Redis resetado e {count} tarefas removidas da fila Celery.",
            "purged_count": count
        })
    except Exception as e:
        logger.error(f"Error resetting Redis: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@system_bp.route("/system/queue", methods=["GET"])
@access_required("admin")
def get_queue_status_api():
    """Get Celery queue status and active tasks"""
    try:
        i = celery_app.control.inspect()
        active = i.active() or {}
        reserved = i.reserved() or {}
        scheduled = i.scheduled() or {}
        
        return jsonify({
            "active": active,
            "reserved": reserved,
            "scheduled": scheduled,
            "broker": celery_app.connection().as_uri()
        })
    except Exception as e:
        logger.error(f"Error fetching queue status: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@system_bp.route("/system/titledb/test", methods=["POST"])
@access_required("admin")
def test_titledb_sync_api():
    """Run TitleDB update synchronously and return detailed results"""
    from titledb import update_titledb
    from settings import load_settings
    
    settings = load_settings()
    try:
        # Run synchronously
        success = update_titledb(settings, force=True)
        
        # Check cache count
        count = Titles.query.count()
        cache_count = TitleDBCache.query.count()
        
        return jsonify({
            "success": success,
            "titles_in_db": count,
            "titledb_cache_count": cache_count,
            "message": "Sincronização do TitleDB concluída (Sync)." if success else "Sincronização falhou ou foi parcial."
        })
    except Exception as e:
        logger.error(f"Error during TitleDB test sync: {e}")
        return jsonify({"success": False, "message": str(e)}), 500


@system_bp.route("/library/scan", methods=["POST"])
@access_required("admin")
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
        return jsonify({"success": False, "message": "A scan is already in progress", "errors": []})

    # TitleDB Lock Check
    import state
    with state.titledb_update_lock:
        if state.is_titledb_update_running:
            active_titledb_jobs = [j for j in active_jobs if j.get('type') == 'titledb_update']
            if not active_titledb_jobs:
                logger.warning("scan_library_api: state.is_titledb_update_running was True but no active job found. Resetting flag.")
                state.is_titledb_update_running = False
            else:
                logger.info(f"Skipping scan_library_api: TitleDB update job {active_titledb_jobs[0]['id']} is in progress.")
                return jsonify({"success": False, "message": "TitleDB update in progress", "errors": []})

    success = True
    errors = []

    try:
        if CELERY_ENABLED:
            if path is None:
                scan_all_libraries_async.delay()
                logger.info("Triggered asynchronous full library scan (Celery).")
                from db import log_activity
                log_activity("library_scan_queued", details={"path": "all", "source": "api"})
            else:
                scan_library_async.delay(path)
                logger.info(f"Triggered asynchronous library scan for: {path} (Celery)")
                from db import log_activity
                log_activity("library_scan_queued", details={"path": path, "source": "api"})
            return jsonify({"success": True, "async": True, "errors": []})
        else:
            # Synchronous mode - Use daemon thread to avoid worker timeout
            import threading
            import state
            from flask import current_app
            from library import scan_library_path, Libraries, identify_library_files, post_library_change
            
            # Capture app instance BEFORE creating thread (current_app won't work in thread)
            app_instance = current_app._get_current_object()
            
            logger.info(f"Preparing background scan thread (path={path})")
            
            def run_scan_background():
                """Background scan thread with proper app context"""
                from job_tracker import job_tracker, JobType
                import time
                
                job_id = f"manual_scan_{int(time.time())}"
                
                try:
                    logger.info(f"Background thread started - creating app context (job_id={job_id})")
                    # Use the captured app instance to create context
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
                        logger.info("Background scan completed successfully")
                        job_tracker.complete_job(job_id, "Manual scan completed")
                        
                except Exception as e:
                    logger.error(f"Background scan failed: {e}", exc_info=True)
                finally:
                    with state.scan_lock:
                        state.scan_in_progress = False
                    logger.info("Background scan thread exiting")
            
            with state.scan_lock:
                state.scan_in_progress = True
            
            scan_thread = threading.Thread(target=run_scan_background, daemon=True, name="LibraryScan")
            scan_thread.start()
            logger.info(f"Background scan thread launched successfully (daemonized)")
            
            return jsonify({"success": True, "async": False, "message": f"Scan started in background thread {'(all)' if path is None else '(path='+path+')'}", "errors": []})
    except Exception as e:
        errors.append(str(e))
        success = False
        from db import log_activity
        log_activity("library_scan_failed", details={"path": path, "error": str(e)})
        logger.error(f"Error during library scan api call: {e}")

    resp = {"success": success, "errors": errors}
    return jsonify(resp)


@system_bp.route("/files/unidentified")
@access_required("admin")
def get_unidentified_files_api():
    """Obter arquivos não identificados"""
    import titles

    # 1. Arquivos sem TitleID (Falha técnica de identificação)
    files = get_all_unidentified_files()
    results = [
        {
            "id": f.id,
            "filename": f.filename,
            "filepath": f.filepath,
            "size": f.size,
            "size_formatted": format_size_py(f.size),
            "error": f.identification_error or "Arquivo não identificado (ID ausente)",
        }
        for f in files
    ]

    # 2. Arquivos com TitleID mas sem reconhecimento de nome (Unknown)
    # Buscamos por arquivos que pertencem a jogos "Unknown" no TitleDB
    identified_files = Files.query.filter(Files.identified == True).all()
    for f in identified_files:
        if not f.apps:
            continue

        # Pega o primeiro app associado (normalmente arquivos NSP/XCI pertencem a 1 app)
        try:
            tid = f.apps[0].title.title_id
            tinfo = titles.get_title_info(tid)
            name = tinfo.get("name", "")

            # Se for desconhecido (começa com Unknown ou vazio)
            if not name or name.startswith("Unknown"):
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

    return jsonify(results)


@system_bp.route("/files/all")
@access_required("admin")
def get_all_files_api():
    """Obter todos os arquivos"""
    # Optimized query with eager loading to avoid N+1 problem (Fixes 524 Timeout)
    files = (
        Files.query.options(joinedload(Files.apps).joinedload(Apps.title))
        .order_by(Files.filename)
        .all()
    )
    
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
        
        # Fallback if name not in DB title
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

    return jsonify(results)


@system_bp.route("/files/delete/<int:file_id>", methods=["POST"])
@access_required("admin")
def delete_file_api(file_id):
    """Deletar arquivo específico"""
    try:
        # Find associated TitleID before deletion for cache update
        file_obj = db.session.get(Files, file_id)
        if not file_obj:
            return jsonify({"success": False, "error": "File not found"}), 404

        title_ids = []
        if file_obj.apps:
            title_ids = list(set([a.title.title_id for a in file_obj.apps if a.title]))

        from library import delete_file_from_db_and_disk

        success, error = delete_file_from_db_and_disk(file_id)

        if success:
            logger.info(f"File {file_id} deleted. Updating cache for titles: {title_ids}")
            # Invalidate full library cache to ensure consistency
            from library import invalidate_library_cache, generate_library

            invalidate_library_cache()
            # Regenerate the library cache
            try:
                generate_library(force=True)
                logger.info("Library cache regenerated after file deletion")
            except Exception as gen_err:
                logger.error(f"Error regenerating library cache: {gen_err}")

            # Run orphaned files cleanup after successful deletion
            try:
                from db import remove_missing_files_from_db

                removed_count = remove_missing_files_from_db()
                if removed_count > 0:
                    logger.info(f"Cleaned up {removed_count} orphaned file references after deletion")
            except Exception as cleanup_err:
                logger.error(f"Error during orphaned cleanup: {cleanup_err}")
        else:
            logger.warning(f"File deletion failed for {file_id}: {error}")

        return jsonify({"success": success, "error": error})
    except Exception as e:
        logger.exception(f"Unhandled error in delete_file_api: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.post("/cleanup/orphaned")
@access_required("admin")
def cleanup_orphaned_apps_api():
    """Limpar registros órfãos e arquivos deletados"""
    try:
        results = {"deleted_files": 0, "deleted_apps": 0, "errors": []}

        # 1. Find Files records where file doesn't exist on disk
        all_files = Files.query.all()
        for file_obj in all_files:
            if file_obj.filepath and not os.path.exists(file_obj.filepath):
                try:
                    db.session.delete(file_obj)
                    results["deleted_files"] += 1
                except Exception as ex:
                    results["errors"].append(f"File {file_obj.id}: {str(ex)}")

        db.session.commit()

        # 2. Find all Apps records where owned=True but no files
        orphaned_apps = []
        all_apps = Apps.query.filter_by(owned=True).all()

        for app in all_apps:
            if not app.files or len(app.files) == 0:
                orphaned_apps.append(
                    {"id": app.id, "title_id": app.title.title_id if app.title else "Unknown", "app_type": app.app_type}
                )

        for orphaned in orphaned_apps:
            try:
                app_obj = db.session.get(Apps, orphaned["id"])
                if app_obj:
                    db.session.delete(app_obj)
                    results["deleted_apps"] += 1
            except Exception as ex:
                results["errors"].append(f"App {orphaned['id']}: {str(ex)}")

        db.session.commit()

        # 3. Invalidate library cache
        from library import invalidate_library_cache

        invalidate_library_cache()

        msg = f"{results['deleted_files']} arquivos deletados do disco removidos. {results['deleted_apps']} registros órfãos removidos."
        if results["errors"]:
            msg += f" {len(results['errors'])} erros."

        return jsonify({"success": True, "results": results, "message": msg})
    except Exception as e:
        db.session.rollback()
        logger.exception(f"Error cleaning orphaned apps: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route("/cleanup/stats")
@access_required("admin")
def cleanup_stats_api():
    """Mostrar estatísticas de itens órfãos"""
    try:
        # Count files that don't exist on disk
        missing_files = 0
        all_files = Files.query.all()
        for file_obj in all_files:
            if file_obj.filepath and not os.path.exists(file_obj.filepath):
                missing_files += 1

        # Count apps with owned=True but no files
        orphaned_apps = Apps.query.filter_by(owned=True).all()
        missing_apps = sum(1 for a in orphaned_apps if not a.files or len(a.files) == 0)

        return jsonify(
            {
                "success": True,
                "missing_files": missing_files,
                "missing_apps": missing_apps,
                "has_orphaned": missing_files > 0 or missing_apps > 0,
            }
        )
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route("/titledb/search")
@access_required("shop")
def search_titledb_api():
    """Buscar no TitleDB"""
    query = request.args.get("q", "").lower()
    if not query or len(query) < 2:
        return jsonify([])

    results = titles.search_titledb_by_name(query)
    return jsonify(results[:20])  # Limit to 20 results


@system_bp.route("/status")
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

    return jsonify(
        {
            "scanning": state.scan_in_progress,
            "updating_titledb": state.is_titledb_update_running,
            "watching": watching > 0,
            "libraries": watching,
        }
    )


@system_bp.post("/settings/titledb/update")
@access_required("admin")
def force_titledb_update_api():
    """Forçar atualização do TitleDB"""
    from app import update_titledb_job
    import threading

    threading.Thread(target=update_titledb_job, args=(True,)).start()
    return jsonify({"success": True, "message": "Update started in background"})


@system_bp.post("/system/reidentify-all")
@access_required("admin")
def reidentify_all_api():
    """Trigger complete re-identification of all files"""
    from library import reidentify_all_files_job
    import threading
    
    # Run in background thread (although it uses gevent inside, we need to spawn it)
    threading.Thread(target=reidentify_all_files_job).start()
    
    return jsonify({"success": True, "message": "Re-identification job started"})



@system_bp.post("/settings/titledb/sources/refresh-dates")
@access_required("admin")
def refresh_titledb_sources_dates_api():
    """Atualizar datas remotas das fontes TitleDB"""
    from settings import CONFIG_DIR
    import titledb_sources

    manager = titledb_sources.TitleDBSourceManager(CONFIG_DIR)
    manager.refresh_remote_dates()
    return jsonify({"success": True})


@system_bp.route("/titles", methods=["GET"])
@access_required("shop")
def get_all_titles_api():
    """Obter todos os títulos"""
    from library import generate_library

    titles_library = generate_library()

    return jsonify({"total": len(titles_library), "games": titles_library})


@system_bp.route("/games/<tid>/custom", methods=["GET"])
@access_required("shop")
def get_game_custom_info(tid):
    """Obter informações customizadas do jogo"""
    info = titles.get_custom_title_info(tid)
    return jsonify({"success": True, "data": info})


@system_bp.route("/games/<tid>/custom", methods=["POST"])
@access_required("shop")
def update_game_custom_info(tid):
    """Atualizar informações customizadas do jogo"""
    data = request.json
    success, error = titles.save_custom_title_info(tid, data)

    if success:
        # Invalidate library cache so the new info appears immediately
        from library import invalidate_library_cache

        invalidate_library_cache()
        return jsonify({"success": True})
    else:
        return jsonify({"success": False, "error": error}), 500


@system_bp.route("/webhooks")
@access_required("admin")
def get_webhooks_api():
    """Obter webhooks configurados"""
    webhooks = Webhook.query.all()
    return jsonify([w.to_dict() for w in webhooks])


@system_bp.post("/webhooks")
@access_required("admin")
def add_webhook_api():
    """Adicionar webhook"""
    data = request.json
    import json

    webhook = Webhook(
        url=data["url"],
        events=json.dumps(data.get("events", ["library_updated"])),
        secret=data.get("secret"),
        active=data.get("active", True),
    )
    db.session.add(webhook)
    try:
        db.session.commit()
        from app import log_activity

        log_activity("webhook_created", details={"url": webhook.url}, user_id=current_user.id)
        return jsonify({"success": True, "webhook": webhook.to_dict()})
    except Exception as e:
        db.session.rollback()
        return jsonify({"error": str(e)}), 400


@system_bp.delete("/webhooks/<int:id>")
@access_required("admin")
def delete_webhook_api(id):
    """Remover webhook"""
    webhook = db.session.get(Webhook, id)
    if webhook:
        db.session.delete(webhook)
        db.session.commit()
        return jsonify({"success": True})
    return jsonify({"success": False, "error": "Webhook not found"}), 404


@system_bp.post("/backup/create")
@access_required("admin")
def create_backup_api():
    """Criar backup manual"""
    from app import backup_manager
    from job_tracker import job_tracker, JobType
    from socket_helper import get_socketio_emitter
    import time

    job_tracker.set_emitter(get_socketio_emitter())

    if not backup_manager:
        return jsonify({"success": False, "error": "Backup manager not initialized"}), 500

    job_id = f"backup_{int(time.time())}"
    job_tracker.start_job(job_id, JobType.BACKUP, "Creating manual backup")

    try:
        success, timestamp = backup_manager.create_backup()
        if success:
            job_tracker.complete_job(job_id, f"Backup created: {timestamp}")
            return jsonify({"success": True, "timestamp": timestamp, "message": "Backup created successfully"})
        else:
            job_tracker.fail_job(job_id, "Backup creation failed")
            return jsonify({"success": False, "error": "Backup failed"}), 500
    except Exception as e:
        job_tracker.fail_job(job_id, str(e))
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.get("/backup/list")
@access_required("admin")
def list_backups_api():
    """Listar backups disponíveis"""
    from app import backup_manager

    if not backup_manager:
        return jsonify({"success": False, "error": "Backup manager not initialized"}), 500

    backups = backup_manager.list_backups()
    return jsonify({"success": True, "backups": backups})


@system_bp.post("/backup/restore")
@access_required("admin")
def restore_backup_api():
    """Restaurar backup"""
    from app import backup_manager
    from job_tracker import job_tracker, JobType
    from socket_helper import get_socketio_emitter
    import time

    job_tracker.set_emitter(get_socketio_emitter())

    if not backup_manager:
        return jsonify({"success": False, "error": "Backup manager not initialized"}), 500

    data = request.json
    filename = data.get("filename")

    if not filename:
        return jsonify({"success": False, "error": "Filename required"}), 400

    job_id = f"restore_{int(time.time())}"
    job_tracker.start_job(job_id, JobType.BACKUP, f"Restoring {filename}")

    try:
        success = backup_manager.restore_backup(filename)
        if success:
            job_tracker.complete_job(job_id, "Restore successful. Restart recommended.")
            return jsonify({"success": True, "message": f"Restored from {filename}. Please restart the application."})
        else:
            job_tracker.fail_job(job_id, "Restore failed")
            return jsonify({"success": False, "error": "Restore failed"}), 500
    except Exception as e:
        job_tracker.fail_job(job_id, str(e))
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route("/backup/download/<filename>")
@access_required("admin")
def download_backup_api(filename):
    """Download a backup file"""
    from app import backup_manager

    if not backup_manager:
        return jsonify({"success": False, "error": "Backup manager not initialized"}), 500

    return send_from_directory(backup_manager.backup_dir, filename, as_attachment=True, download_name=filename)


@system_bp.delete("/backup/<filename>")
@access_required("admin")
def delete_backup_api(filename):
    """Delete a backup file"""
    from app import backup_manager

    if not backup_manager:
        return jsonify({"success": False, "error": "Backup manager not initialized"}), 500

    success = backup_manager.delete_backup(filename)
    if success:
        return jsonify({"success": True, "message": "Backup deleted successfully"})
    else:
        return jsonify({"success": False, "error": "Delete failed"}), 500


@system_bp.route("/activity", methods=["GET"])
@access_required("admin")
def activity_api():
    """Obter log de atividades"""
    limit = request.args.get("limit", 50, type=int)
    logs = ActivityLog.query.order_by(ActivityLog.timestamp.desc()).limit(limit).all()

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
    return jsonify(results)


@system_bp.route("/plugins", methods=["GET"])
@access_required("admin")
def plugins_api():
    """Obter lista de plugins"""
    from app import plugin_manager

    if not plugin_manager:
        return jsonify([])

    # Return all discovered plugins with their enabled status
    return jsonify(plugin_manager.discovered_plugins)


@system_bp.post("/plugins/toggle")
@access_required("admin")
def toggle_plugin_api():
    """Alternar status do plugin"""
    data = request.json
    plugin_id = data.get("id")
    enabled = data.get("enabled", True)

    if not plugin_id:
        return jsonify({"error": "Plugin ID required"}), 400

    # 1. Update settings file
    import settings

    settings.toggle_plugin_settings(plugin_id, enabled)

    # 2. Reload plugins in the manager to reflect changes
    # Note: This won't "unload" already loaded classes from memory, but will
    # stop them from being active if reload logic is implemented correctly.
    # For now, it updates the discovered_plugins list and future events will skip it.
    from app import plugin_manager

    disabled_plugins = load_settings(force=True).get("plugins", {}).get("disabled", [])
    plugin_manager.load_plugins(disabled_plugins)

    return jsonify({"success": True})


@system_bp.route("/cloud/auth/<provider>", methods=["GET"])
@access_required("admin")
def cloud_auth_api(provider):
    """Autenticação com provedor de nuvem"""
    from app import cloud_manager

    if not cloud_manager:
        return jsonify({"error": "Cloud manager not initialized"}), 500

    redirect_uri = request.host_url.rstrip("/") + f"/api/cloud/callback/{provider}"
    auth_url = cloud_manager.get_auth_url(provider, redirect_uri)

    if not auth_url:
        return jsonify({"error": "Provider not configured or disabled"}), 400

    return jsonify({"auth_url": auth_url})


@system_bp.route("/cloud/callback/<provider>", methods=["GET", "POST"])
def cloud_callback_api(provider):
    """Callback de autenticação com nuvem"""
    from app import cloud_manager

    # This endpoint receives the code from Google
    if request.method == "GET":
        code = request.args.get("code")
        error = request.args.get("error")
        if error:
            return f"Error: {error}"

        if code:
            redirect_uri = request.host_url.rstrip("/") + f"/api/cloud/callback/{provider}"
            if cloud_manager.authenticate(provider, code, redirect_uri):
                return "Authentication successful! You can close this window."
            else:
                return "Authentication failed.", 500

    # POST for manual code entry if needed
    data = request.json
    code = data.get("code")
    redirect_uri = data.get("redirect_uri")

    if cloud_manager.authenticate(provider, code, redirect_uri):
        return jsonify({"success": True})
    return jsonify({"success": False}), 400


@system_bp.route("/cloud/status", methods=["GET"])
@access_required("admin")
def cloud_status_api():
    """Status da integração com nuvem"""
    from cloud_sync import get_cloud_manager

    try:
        cloud_manager = get_cloud_manager(CONFIG_DIR)
    except Exception:
        return jsonify({})

    if not cloud_manager:
        return jsonify({})

    results = {}
    for name, provider in cloud_manager.providers.items():
        results[name] = {
            "configured": True,
            "authenticated": (hasattr(provider, "creds") and provider.creds is not None)
            or (hasattr(provider, "access_token") and provider.access_token is not None),
        }
    return jsonify(results)


@system_bp.route("/cloud/files/<provider>", methods=["GET"])
@access_required("admin")
def cloud_files_api(provider):
    """Listar arquivos na nuvem"""
    from app import cloud_manager

    folder_id = request.args.get("folder_id")
    files = cloud_manager.list_files(provider, folder_id)
    return jsonify({"files": files})


@system_bp.route("/system/jobs", methods=["GET"])
def get_all_jobs_api():
    """Retorna status de todos os jobs recentes"""
    from job_tracker import job_tracker

    # job_tracker now returns list of dicts from DB
    jobs = job_tracker.get_all_jobs()

    # Add TitleDB status info
    titledb_status = titledb.get_active_source_info()

    return jsonify(
        {
            "jobs": jobs,  # Now already in dict format with to_dict()
            "titledb": titledb_status
        }
    )


@system_bp.route("/system/metadata/fetch", methods=["POST"])
@access_required("admin")
def trigger_metadata_fetch():
    """Trigger manual metadata fetch for all games"""
    from metadata_service import metadata_fetcher
    import threading

    data = request.json or {}
    force = data.get("force", False)

    thread = threading.Thread(target=lambda: metadata_fetcher.fetch_all_metadata(force=force))
    thread.daemon = True
    thread.start()

    return jsonify({"success": True, "message": "Metadata fetch started in background"})


@system_bp.route("/system/metadata/status", methods=["GET"])
def get_metadata_status():
    """Get summarized status of metadata fetch service"""
    from db import MetadataFetchLog

    last_fetch = MetadataFetchLog.query.order_by(MetadataFetchLog.started_at.desc()).first()

    return jsonify(
        {
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
    )


@system_bp.route("/system/jobs/<job_id>/cancel", methods=["POST"])
@access_required("admin")
def cancel_job(job_id):
    """Cancela um job em execução marcando-o como failed no banco de dados"""
    from db import SystemJob, db
    from datetime import datetime

    try:
        from job_tracker import job_tracker
        
        # This will update DB and handle in-memory cancellation set
        job_tracker.cancel_job(job_id)
        
        return jsonify({"success": True, "message": "Job cancelled"})
    except Exception as e:
        logger.error(f"Error cancelling job {job_id}: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route("/system/jobs/cleanup", methods=["POST"])
@access_required("admin")
def cleanup_jobs_api():
    """Limpa jobs antigos (>24h) ou todos os jobs completados e cancela jobs presos"""
    try:
        from job_tracker import job_tracker
        from db import SystemJob, db
        
        # 1. Cancel ALL currently running jobs
        running_jobs = SystemJob.query.filter(SystemJob.status == "running").all()
        for job in running_jobs:
            logger.warning(f"Forcing cancellation of job {job.job_id} during cleanup")
            job_tracker.cancel_job(job.job_id)
            
        # 2. History cleanup
        job_tracker.cleanup_old_jobs(max_age_hours=24)
        
        return jsonify({"success": True, "message": f"Cancelled {len(running_jobs)} running jobs and cleaned history"})
    except Exception as e:
        logger.error(f"Error during jobs cleanup: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


@system_bp.route("/system/diagnostic", methods=["GET"])
@access_required("admin")
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

    return jsonify(diagnostic)
