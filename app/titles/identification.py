import os
from pathlib import Path
from binascii import hexlify as hx

from titles._state import (
    logger, _cnmts_db, _dlc_map, _titles_db,
)
from titles.utils import get_app_id_from_filename, get_version_from_filename
from constants import APP_TYPE_BASE, APP_TYPE_UPD, APP_TYPE_DLC
from nstools.Fs import Pfs0, Nca, Type, factory
from nstools.lib import FsTools
from nstools.nut import Keys


def get_title_id_from_app_id(app_id, app_type):
    app_id = app_id.upper()
    prefix = app_id[:-3]

    std_id = prefix + "000"

    char_13 = prefix[-1]
    try:
        val = int(char_13, 16)
        if (app_type == APP_TYPE_DLC or app_type == APP_TYPE_UPD) and (val % 2 != 0):
            even_char = hex(val - 1)[2:].upper()
            even_id = prefix[:-1] + even_char + "000"
            global _titles_db
            if _titles_db:
                if std_id.lower() in _titles_db:
                    return std_id
                if even_id.lower() in _titles_db:
                    return even_id
            return even_id
    except (ValueError, TypeError):
        pass

    return std_id


def identify_appId(app_id):
    app_id = app_id.lower()

    global _cnmts_db, _dlc_map
    if _cnmts_db is None:
        if app_id.endswith("000"):
            return app_id.upper(), APP_TYPE_BASE
        elif app_id.endswith("800"):
            return get_title_id_from_app_id(app_id, APP_TYPE_UPD), APP_TYPE_UPD
        else:
            return get_title_id_from_app_id(app_id, APP_TYPE_DLC), APP_TYPE_DLC

    if app_id in _cnmts_db:
        app_id_keys = list(_cnmts_db[app_id].keys())
        if len(app_id_keys):
            app = _cnmts_db[app_id][app_id_keys[-1]]

            if app["titleType"] == 128:
                app_type = APP_TYPE_BASE
                title_id = app_id.upper()
            elif app["titleType"] == 129:
                app_type = APP_TYPE_UPD
                if "otherApplicationId" in app and app["otherApplicationId"]:
                    title_id = app["otherApplicationId"].upper()
                else:
                    title_id = get_title_id_from_app_id(app_id, app_type)
            elif app["titleType"] == 130:
                app_type = APP_TYPE_DLC
                if "otherApplicationId" in app and app["otherApplicationId"]:
                    title_id = app["otherApplicationId"].upper()
                else:
                    title_id = get_title_id_from_app_id(app_id, app_type)
        else:
            logger.warning(f"{app_id} has no keys in cnmts_db, fallback to default identification.")
            if app_id.endswith("000"):
                app_type = APP_TYPE_BASE
                title_id = app_id
            elif app_id.endswith("800"):
                app_type = APP_TYPE_UPD
                title_id = get_title_id_from_app_id(app_id, app_type)
            else:
                app_type = APP_TYPE_DLC
                title_id = get_title_id_from_app_id(app_id, app_type)

    elif _dlc_map and app_id.upper() in _dlc_map:
        base_id = _dlc_map[app_id.upper()]
        title_id = base_id.upper()
        app_type = APP_TYPE_DLC

    else:
        logger.debug(f"{app_id} not in cnmts_db, fallback to default identification.")
        if app_id.endswith("000"):
            app_type = APP_TYPE_BASE
            title_id = app_id
        elif app_id.endswith("800"):
            app_type = APP_TYPE_UPD
            title_id = get_title_id_from_app_id(app_id, app_type)
        else:
            app_type = APP_TYPE_DLC
            title_id = get_title_id_from_app_id(app_id, app_type)

    return title_id.upper() if title_id else app_id.upper(), app_type


def identify_file_from_filename(filename):
    title_id = None
    app_id = None
    app_type = None
    version = None
    errors = []

    app_id = get_app_id_from_filename(filename)
    if app_id is None:
        errors.append(
            "Could not determine App ID from filename, pattern [APPID] not found. Title ID and Type cannot be derived."
        )
    else:
        title_id, app_type = identify_appId(app_id)

    version = get_version_from_filename(filename)
    if version is None:
        errors.append("Could not determine version from filename, pattern [vVERSION] not found.")

    error = " ".join(errors)
    return app_id, title_id, app_type, version, error


def identify_file_from_cnmt(filepath):
    contents = []
    titleId = None
    version = None
    titleType = None
    container = factory(Path(filepath).resolve())
    container.open(filepath, "rb")
    if filepath.lower().endswith((".xci", ".xcz")):
        container = container.hfs0["secure"]
    try:
        for nspf in container:
            if isinstance(nspf, Nca.Nca) and nspf.header.contentType == Type.Content.META:
                for section in nspf:
                    if isinstance(section, Pfs0.Pfs0):
                        Cnmt = section.getCnmt()

                        titleType = FsTools.parse_cnmt_type_n(
                            hx(
                                Cnmt.titleType.to_bytes(
                                    length=(min(Cnmt.titleType.bit_length(), 1) + 7) // 8, byteorder="big"
                                )
                            )
                        )
                        if titleType == "GAME":
                            titleType = APP_TYPE_BASE
                        titleId = Cnmt.titleId.upper()
                        version = Cnmt.version
                        contents.append((titleType, titleId, version))

    finally:
        container.close()

    return contents


def identify_file(filepath):
    filename = os.path.split(filepath)[-1]

    db_size = len(_titles_db) if _titles_db else 0
    logger.info(f"Identifying '{filename}'... (Keys loaded: {Keys.keys_loaded}, TitleDB: {db_size} titles)")

    contents = []
    success = True
    error = ""
    if Keys.keys_loaded:
        identification = "cnmt"
        try:
            logger.debug(f"Attempting CNMT identification for {filename}")
            cnmt_contents = identify_file_from_cnmt(filepath)
            if not cnmt_contents:
                logger.debug(f"No CNMT content found for {filename}")
                error = "No content found in NCA containers."
                success = False
            else:
                logger.debug(f"CNMT found for {filename}: {cnmt_contents}")
                for content in cnmt_contents:
                    app_type, app_id, version = content
                    if app_type != APP_TYPE_BASE:
                        title_id, app_type = identify_appId(app_id)
                    else:
                        title_id = app_id
                    contents.append((title_id, app_type, app_id, version))
        except Exception as e:
            logger.warning(
                f"Could not identify file {filepath} from metadata (this is common if keys are missing): {e}"
            )
            error = str(e)
            success = False

    else:
        identification = "filename"
        app_id, title_id, app_type, version, error = identify_file_from_filename(filename)
        if not error:
            contents.append((title_id, app_type, app_id, version))
        else:
            success = False

    if contents:
        if isinstance(contents[0], dict):
            pass
        else:
            contents = [
                {
                    "title_id": c[0],
                    "app_id": c[2],
                    "type": c[1],
                    "version": c[3],
                }
                for c in contents
            ]

    if not contents and not success:
        logger.debug(f"Falling back to filename identification for {filename}")
        app_id, title_id, app_type, version, f_error = identify_file_from_filename(filename)
        if title_id:
            logger.debug(f"Filename identification success for {filename}: {title_id}")
            contents = [
                {
                    "title_id": title_id,
                    "app_id": app_id,
                    "type": app_type,
                    "version": version,
                }
            ]
            identification = "filename"
            success = True
            error = ""

    if contents and success:
        error = ""

    suggested_name = None
    if contents and success:
        name_part = filename.split("[")[0].strip()
        if name_part and name_part != filename:
            suggested_name = name_part

    return identification, success, contents, error, suggested_name
