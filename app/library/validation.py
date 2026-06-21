import os
import logging
from pathlib import Path
from constants import ALLOWED_EXTENSIONS

logger = logging.getLogger("main")

MAX_FILE_SIZE = 50 * 1024 * 1024 * 1024  # 50GB


def validate_file(filepath):
    path = Path(filepath)

    if path.suffix.lower() not in ALLOWED_EXTENSIONS:
        raise ValueError(f"Extensão não permitida: {path.suffix}")

    if not path.exists():
        raise FileNotFoundError(f"Arquivo não encontrado: {filepath}")

    size = path.stat().st_size
    if size == 0:
        raise ValueError("Arquivo vazio")
    if size > MAX_FILE_SIZE:
        raise ValueError("Arquivo excede limite de tamanho (50GB)")

    if path.is_symlink():
        logger.warning(f"Processando symlink: {filepath}")

    try:
        with open(filepath, "rb") as f:
            header = f.read(4)
            if path.suffix.lower() in [".nsp", ".nsz"]:
                if header != b"PFS0":
                    raise ValueError(f"Cabeçalho NSP inválido: {header}")
            elif path.suffix.lower() in [".xci", ".xcz"]:
                f.seek(0x100)
                header_xci = f.read(4)
                if header_xci != b"HEAD":
                    raise ValueError(f"Cabeçalho XCI inválido: {header_xci}")
    except Exception as e:
        if isinstance(e, ValueError):
            raise
        raise ValueError(f"Erro ao ler cabeçalho do arquivo: {str(e)}")

    return True


def cleanup_metadata_files(path):
    deleted_count = 0
    for root, dirs, files in os.walk(path):
        for file in files:
            if file.startswith("._") or file == ".DS_Store":
                try:
                    os.remove(os.path.join(root, file))
                    deleted_count += 1
                except Exception as e:
                    logger.warning(f"Failed to delete metadata file {file}: {e}")
    if deleted_count > 0:
        logger.info(f"Deleted {deleted_count} metadata files.")
