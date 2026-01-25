"""
Library Service - Lógica de negócio relacionada à biblioteca
"""

from db import *
from library import *
from settings import load_settings
import titles
import structlog
from typing import Dict, List, Any, Optional

logger = structlog.get_logger()


class LibraryService:
    """Serviço para operações relacionadas à biblioteca"""

    @staticmethod
    def get_library_stats(library_id: Optional[int] = None) -> Dict[str, Any]:
        """Obter estatísticas detalhadas da biblioteca com filtros otimizados"""
        from sqlalchemy import func, case, and_

        # 1. Fetch library list for filter dropdown
        libs = Libraries.query.all()
        libraries_list = [{"id": l.id, "path": l.path} for l in libs]

        # 2. Otimização: Combinar todas as queries de Files em uma única query com agregações
        if library_id:
            # Query otimizada usando join direto ao invés de subquery
            file_stats = (
                db.session.query(
                    func.count(Files.id).label("total_files"),
                    func.sum(Files.size).label("total_size"),
                    func.sum(case((Files.identified == False, 1), else_=0)).label("unidentified_files"),
                )
                .filter(Files.library_id == library_id)
                .first()
            )

            # Query otimizada para Apps usando join direto
            Apps.query.join(app_files).join(Files).filter(Files.library_id == library_id)
        else:
            # Query otimizada sem filtro de library
            file_stats = db.session.query(
                func.count(Files.id).label("total_files"),
                func.sum(Files.size).label("total_size"),
                func.sum(case((Files.identified == False, 1), else_=0)).label("unidentified_files"),
            ).first()


        # Extrair resultados da query otimizada
        total_files = file_stats.total_files or 0
        total_size = file_stats.total_size or 0
        unidentified_files = file_stats.unidentified_files or 0
        identified_files = total_files - unidentified_files
        id_rate = round((identified_files / total_files * 100), 1) if total_files > 0 else 0

        # 4. Collection Breakdown (Owned Apps) - Otimizado com uma única query
        if library_id:
            owned_apps_stats = (
                db.session.query(
                    func.sum(case((Apps.owned == True, 1), else_=0)).label("total_owned"),
                    func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_BASE), 1), else_=0)).label(
                        "total_bases"
                    ),
                    func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_UPD), 1), else_=0)).label(
                        "total_updates"
                    ),
                    func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_DLC), 1), else_=0)).label(
                        "total_dlcs"
                    ),
                    func.count(func.distinct(case((Apps.owned == True, Apps.title_id), else_=None))).label(
                        "distinct_titles"
                    ),
                )
                .select_from(Apps)
                .join(app_files)
                .join(Files)
                .filter(Files.library_id == library_id)
                .first()
            )
        else:
            owned_apps_stats = (
                db.session.query(
                    func.sum(case((Apps.owned == True, 1), else_=0)).label("total_owned"),
                    func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_BASE), 1), else_=0)).label(
                        "total_bases"
                    ),
                    func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_UPD), 1), else_=0)).label(
                        "total_updates"
                    ),
                    func.sum(case((and_(Apps.owned == True, Apps.app_type == APP_TYPE_DLC), 1), else_=0)).label(
                        "total_dlcs"
                    ),
                    func.count(func.distinct(case((Apps.owned == True, Apps.title_id), else_=None))).label(
                        "distinct_titles"
                    ),
                )
                .select_from(Apps)
                .first()
            )

        total_owned_bases = owned_apps_stats.total_bases or 0
        total_owned_updates = owned_apps_stats.total_updates or 0
        total_owned_dlcs = owned_apps_stats.total_dlcs or 0

        # 5. Outros cálculos
        Titles.query.count()
        titles.get_titles_count()

        lib_data = load_library_from_disk()
        if not lib_data:
            games = generate_library()
        else:
            games = lib_data.get("library", []) if isinstance(lib_data, dict) else lib_data

        # Filter games list if library_id provided
        filtered_games = games
        if library_id:
            lib_path = Libraries.query.get(library_id).path
            filtered_games = [g for g in games if any(lib_path in f for f in g.get("files", []))]

        total_owned = len(filtered_games)
        up_to_date = len([g for g in filtered_games if g.get("status_color") == "green" and g.get("has_base")])
        genre_dist = {}
        for g in filtered_games:
            cats = g.get("category", [])
            if not cats:
                cats = ["Unknown"]
            for c in cats:
                genre_dist[c] = genre_dist.get(c, 0) + 1

        recognized_games = len(
            [g for g in filtered_games if g.get("name") and not g.get("name", "").startswith("Unknown")]
        )
        recognition_rate = round((recognized_games / total_owned * 100), 1) if total_owned > 0 else 0

        # Coverage: percentage of library games that have TitleDB metadata
        games_with_titledb = len(
            [g for g in filtered_games if g.get("name") and not g.get("name", "").startswith("Unknown")]
        )
        coverage_pct = round((games_with_titledb / total_owned * 100), 2) if total_owned > 0 else 0

        app_settings = load_settings()
        keys_valid = app_settings.get("titles", {}).get("valid_keys", False)

        active_src = titles.get_active_source_info()
        source_name = active_src.get("name", "Nenhuma") if active_src else "Nenhuma"

        return {
            "libraries": libraries_list,
            "library": {
                "total_titles": len(filtered_games),
                "total_owned": total_owned,
                "total_bases": total_owned_bases,
                "total_updates": total_owned_updates,
                "total_dlcs": total_owned_dlcs,
                "total_size": total_size,
                "total_size_formatted": format_size_py(total_size),
                "up_to_date": up_to_date,
                "pending": total_owned - up_to_date,
                "completion_rate": round((up_to_date / total_owned * 100), 1) if total_owned > 0 else 0,
            },
            "titledb": {
                "total_available": games_with_titledb,
                "coverage_pct": coverage_pct,
                "source_name": source_name,
            },
            "identification": {
                "total_files": total_files,
                "identified_pct": id_rate,
                "recognition_pct": recognition_rate,
                "unidentified_count": unidentified_files,
                "unrecognized_count": total_owned - recognized_games,
                "keys_valid": keys_valid,
            },
            "genres": genre_dist,
            "recent": filtered_games[:8],
        }

    @staticmethod
    def get_game_details(title_id: str, app_id: Optional[str] = None) -> Dict[str, Any]:
        """Obter detalhes completos de um jogo"""
        tid = title_id.upper()
        title_obj = Titles.query.filter_by(title_id=tid).first()

        if not title_obj and str(title_id).isdigit():
            app_obj = db.session.get(Apps, int(title_id))
            if app_obj:
                tid = app_obj.title.title_id
                title_obj = app_obj.title

        if not title_obj:
            titles_lib.load_titledb()
            base_tid, app_type = titles_lib.identify_appId(tid)
            if base_tid and tid != base_tid:
                if app_type == APP_TYPE_DLC:
                    pass
                else:
                    tid = base_tid
                    title_obj = Titles.query.filter_by(title_id=tid).first()

        info = titles_lib.get_game_info(tid)
        if not info:
            info = {
                "name": f"Unknown ({tid})",
                "publisher": "--",
                "description": "No information available.",
                "release_date": "--",
                "iconUrl": "/static/img/no-icon.png",
            }

        if not title_obj:
            result = info.copy()
            result.update(
                {
                    "id": tid,
                    "app_id": tid,
                    "owned_version": 0,
                    "has_base": False,
                    "has_latest_version": False,
                    "has_all_dlcs": False,
                    "owned": False,
                    "files": [],
                    "updates": [],
                    "dlcs": [],
                    "category": info.get("category", []),
                }
            )

            app_obj_dlc = Apps.query.filter_by(app_id=tid, owned=True).first()
            if app_obj_dlc:
                result["owned"] = True
                result["files"] = [
                    {
                        "id": f.id,
                        "filename": f.filename,
                        "filepath": f.filepath,
                        "size_formatted": format_size_py(f.size),
                    }
                    for f in app_obj_dlc.files
                ]

            return result

        all_title_apps = get_all_title_apps(tid)
        base_files = []
        base_apps = [a for a in all_title_apps if a["app_type"] == APP_TYPE_BASE and a["owned"]]
        for b in base_apps:
            app_model = db.session.get(Apps, b["id"])
            for f in app_model.files:
                base_files.append(
                    {
                        "id": f.id,
                        "filename": f.filename,
                        "filepath": f.filepath,
                        "size": f.size,
                        "size_formatted": format_size_py(f.size),
                        "version": app_model.app_version,
                    }
                )

        seen_ids = set()
        unique_base_files = []
        seen_file_ids_in_modal = set()
        for f in base_files:
            if f["id"] not in seen_ids:
                unique_base_files.append(f)
                seen_ids.add(f["id"])
                seen_file_ids_in_modal.add(f["id"])

        available_versions = titles_lib.get_all_existing_versions(tid)
        version_release_dates = {v["version"]: v["release_date"] for v in available_versions}

        if base_release_date := info.get("release_date", ""):
            if len(str(base_release_date)) == 8 and str(base_release_date).isdigit():
                formatted_date = (
                    f"{str(base_release_date)[:4]}-{str(base_release_date)[4:6]}-{str(base_release_date)[6:]}"
                )
                info["release_date"] = formatted_date
                version_release_dates[0] = formatted_date
            elif base_release_date:
                version_release_dates[0] = base_release_date

        update_apps = [a for a in all_title_apps if a["app_type"] == APP_TYPE_UPD]
        updates_list = []
        for upd in update_apps:
            v_int = int(upd["app_version"])
            if v_int == 0:
                continue

            files = []
            if upd["owned"]:
                app_model = db.session.get(Apps, upd["id"])
                for f in app_model.files:
                    if f.id in seen_file_ids_in_modal:
                        continue
                    files.append({"id": f.id, "filename": f.filename, "size_formatted": format_size_py(f.size)})

            updates_list.append(
                {
                    "version": v_int,
                    "owned": upd["owned"],
                    "release_date": version_release_dates.get(v_int, "Unknown"),
                    "files": files,
                }
            )

        dlc_ids = titles_lib.get_all_existing_dlc(tid)
        dlcs_list = []
        dlc_apps_grouped = {}
        for a in [a for a in all_title_apps if a["app_type"] == APP_TYPE_DLC]:
            aid = a["app_id"]
            if aid not in dlc_apps_grouped:
                dlc_apps_grouped[aid] = []
            dlc_apps_grouped[aid].append(a)

        for dlc_id in dlc_ids:
            apps_for_dlc = dlc_apps_grouped.get(dlc_id, [])
            owned = any(a["owned"] for a in apps_for_dlc)
            files = []
            if owned:
                for a in apps_for_dlc:
                    if a["owned"]:
                        app_model = db.session.get(Apps, a["id"])
                        for f in app_model.files:
                            files.append(
                                {
                                    "id": f.id,
                                    "filename": f.filename,
                                    "filepath": f.filepath,
                                    "size_formatted": format_size_py(f.size),
                                }
                            )

            dlc_info = titles_lib.get_game_info(dlc_id)
            dlcs_list.append(
                {
                    "app_id": dlc_id,
                    "name": dlc_info.get("name", f"DLC {dlc_id}"),
                    "owned": owned,
                    "release_date": dlc_info.get("release_date", ""),
                    "files": files,
                }
            )

        result = info.copy()
        result.update(
            {
                "id": tid,
                "app_id": tid,
                "title_id": tid,
                "owned_version": max((int(a["app_version"]) for a in all_title_apps if a["owned"]), default=0),
                "display_version": result["owned_version"],
                "has_base": title_obj.have_base,
                "has_latest_version": title_obj.up_to_date,
                "has_all_dlcs": title_obj.complete,
                "files": unique_base_files,
                "updates": sorted(updates_list, key=lambda x: x["version"]),
                "dlcs": sorted(dlcs_list, key=lambda x: x["name"]),
                "category": info.get("category", []),
            }
        )

        total_size = sum(f.size for a in all_title_apps if a["owned"] for f in db.session.get(Apps, a["id"]).files)
        result.update(
            {
                "size": total_size,
                "size_formatted": format_size_py(total_size),
                "status_color": "orange"
                if result["has_base"] and (not result["has_latest_version"] or not result["has_all_dlcs"])
                else ("green" if result["has_base"] else "gray"),
            }
        )

        return result

    @staticmethod
    def search_games(query: str, filters: Dict[str, Any]) -> Dict[str, Any]:
        """Buscar jogos com filtros"""
        lib_data = generate_library()

        results = []
        for game in lib_data:
            if query:
                name = (game.get("name") or "").lower()
                publisher = (game.get("publisher") or "").lower()
                tid = (game.get("id") or "").lower()
                if query.lower() not in name and query.lower() not in publisher and query.lower() not in tid:
                    continue

            if genre := filters.get("genre"):
                if genre != "Todos os Gêneros":
                    categories = game.get("category") or []
                    if genre not in categories:
                        continue

            is_owned = game.get("have_base", False)
            if filters.get("owned_only") and not is_owned:
                continue
            if filters.get("missing_only") and is_owned:
                continue

            is_up_to_date = game.get("up_to_date", False)
            if filters.get("up_to_date") and not is_up_to_date:
                continue

            has_pending = not is_up_to_date and is_owned
            if filters.get("pending") and not has_pending:
                continue

            results.append(game)

        return {"count": len(results), "results": results[:100]}

    @staticmethod
    def get_unidentified_files() -> List[Dict[str, Any]]:
        """Obter arquivos não identificados"""
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

        identified_files = Files.query.filter(Files.identified == True).all()
        for f in identified_files:
            if not f.apps:
                continue

            try:
                tid = f.apps[0].title.title_id
                tinfo = titles.get_title_info(tid)
                name = tinfo.get("name", "")

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

        return results

    @staticmethod
    def delete_file(file_id: int) -> tuple[bool, str]:
        """Deletar arquivo específico"""
        file_obj = db.session.get(Files, file_id)
        if not file_obj:
            return False, "File not found"

        title_ids = []
        if file_obj.apps:
            title_ids = list(set([a.title.title_id for a in file_obj.apps if a.title]))

        success, error = delete_file_from_db_and_disk(file_id)

        if success:
            logger.info(f"File {file_id} deleted. Updating cache for titles: {title_ids}")
            for tid in title_ids:
                try:
                    update_game_in_cache(tid)
                except Exception as ex:
                    logger.error(f"Error updating cache for title {tid}: {ex}")
        else:
            logger.warning(f"File deletion failed for {file_id}: {error}")

        return success, error
