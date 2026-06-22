from db import get_shop_files
from Crypto.PublicKey import RSA
from Crypto.Cipher import PKCS1_OAEP
from Crypto.Hash import SHA256
from Crypto.Cipher import AES
import zstandard as zstd
import random
import json

# https://github.com/blawar/tinfoil/blob/master/docs/files/public.key 1160174fa2d7589831f74d149bc403711f3991e4
TINFOIL_PUBLIC_KEY = """-----BEGIN PUBLIC KEY-----
MIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEAvPdrJigQ0rZAy+jla7hS
jwen8gkF0gjtl+lZGY59KatNd9Kj2gfY7dTMM+5M2tU4Wr3nk8KWr5qKm3hzo/2C
Gbc55im3tlRl6yuFxWQ+c/I2SM5L3xp6eiLUcumMsEo0B7ELmtnHTGCCNAIzTFzV
4XcWGVbkZj83rTFxpLsa1oArTdcz5CG6qgyVe7KbPsft76DAEkV8KaWgnQiG0Dps
INFy4vISmf6L1TgAryJ8l2K4y8QbymyLeMsABdlEI3yRHAm78PSezU57XtQpHW5I
aupup8Es6bcDZQKkRsbOeR9T74tkj+k44QrjZo8xpX9tlJAKEEmwDlyAg0O5CLX3
CQIDAQAB
-----END PUBLIC KEY-----"""

import logging

logger = logging.getLogger("main")


def gen_shop_files(db, base_url=""):
    shop_files = []
    titles_map = {}
    files = get_shop_files()

    logger.info(f"gen_shop_files: Processing {len(files)} files from database (base_url={base_url})")

    # Collect all unique Base TitleIDs for the titles map
    seen_base_tids = set()

    for file in files:
        # Build absolute URL: Tinfoil requires full URLs (http/https)
        # The fragment after # is used by Tinfoil as the display filename
        # It must NOT be URL-encoded - Tinfoil reads it as raw text
        file_url = f"{base_url}/api/get_game/{file['id']}#{file['filename']}"

        # Compatibilidade aprimorada com CyberFoil e outros instaladores do ecossistema.
        # Esses instaladores leem metadados adicionais diretamente de cada entrada para mapear
        # corretamente jogos, updates e DLCs.
        app_type_lower = file.get("app_type", "").lower() if file.get("app_type") else ""

        shop_files.append(
            {
                "url": file_url,
                "size": file["size"],
                "name": file["filename"],
                "title_id": file["app_id"],  # O ID do próprio arquivo (ex: ID da DLC ou do UPDATE)
                "app_version": file.get("app_version", 0),
                "app_type": app_type_lower,
            }
        )

        # Collect Base TitleIDs (ending in 000) for the titles map
        # Only base IDs have entries in the TitleDB, so skip DLC/UPDATE IDs
        title_id = file.get("title_id")
        if title_id:
            tid_upper = title_id.upper()
            if tid_upper.endswith("000") and tid_upper not in seen_base_tids:
                seen_base_tids.add(tid_upper)

    # Build titles map: only Base TitleIDs (ending in 000)
    # This is what Tinfoil uses to display game names
    from titles import get_game_info

    for tid in seen_base_tids:
        try:
            info = get_game_info(tid, silent=True)
            if info and info.get("name") and not info["name"].startswith("Unknown"):
                titles_map[tid] = {
                    "id": tid,
                    "name": info["name"].strip(),
                    "version": 0,
                    "region": "US",
                    "releaseDate": 0,
                    "rating": 10,
                    "publisher": info.get("publisher", "N/A"),
                    "description": info.get("description", ""),
                    "size": 0,
                    "rank": 1,
                }
        except Exception:
            pass

    logger.info(
        f"gen_shop_files: Returning {len(shop_files)} files and {len(titles_map)} titles mapping for Tinfoil shop"
    )
    return shop_files, titles_map


def encrypt_shop(shop):
    input = json.dumps(shop).encode("utf-8")
    # random 128-bit AES key (16 bytes), used later for symmetric encryption (AES)
    aesKey = random.randint(0, 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFF).to_bytes(0x10, "big")
    # zstandard compression
    flag = 0xFD
    cctx = zstd.ZstdCompressor(level=22)
    buf = cctx.compress(input)
    sz = len(buf)

    # Encrypt the AES key with RSA, PKCS1_OAEP padding scheme
    pubKey = RSA.importKey(TINFOIL_PUBLIC_KEY)
    cipher = PKCS1_OAEP.new(pubKey, hashAlgo=SHA256, label=b"")
    # Now the AES key can only be decrypted with Tinfoil private key
    sessionKey = cipher.encrypt(aesKey)

    # Encrypting the Data with AES
    cipher = AES.new(aesKey, AES.MODE_ECB)
    buf = cipher.encrypt(buf + (b"\x00" * (0x10 - (sz % 0x10))))

    binary_data = b"TINFOIL" + flag.to_bytes(1, byteorder="little") + sessionKey + sz.to_bytes(8, "little") + buf
    return binary_data
