"""
Model: Titles
Extracted from db.py during Phase 3.1 refactoring
"""

from db import db, now_utc
from flask_login import UserMixin


class Titles(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title_id = db.Column(db.String, unique=True, index=True)  # Index for faster lookups
    have_base = db.Column(db.Boolean, default=False)
    up_to_date = db.Column(db.Boolean, default=False)
    complete = db.Column(db.Boolean, default=False)

    # Metadata fields (Previously stored in JSON cache)
    name = db.Column(db.String)
    icon_url = db.Column(db.String)
    banner_url = db.Column(db.String)
    category = db.Column(db.String)  # Comma separated or JSON string
    release_date = db.Column(db.String)
    publisher = db.Column(db.String)
    description = db.Column(db.Text)
    size = db.Column(db.BigInteger)
    nsuid = db.Column(db.String)

    # Track when it was last updated from TitleDB vs User edit
    last_updated = db.Column(db.DateTime, default=db.func.now(), onupdate=db.func.now())
    is_custom = db.Column(db.Boolean, default=False)  # True if edited by user
    added_at = db.Column(db.DateTime)  # When game was first added to library

    # === RATINGS E REVIEWS ===
    metacritic_score = db.Column(db.Integer)  # 0-100
    user_rating = db.Column(db.Float)  # 0.0-5.0
    rawg_rating = db.Column(db.Float)  # 0.0-5.0
    rating_count = db.Column(db.Integer)  # Número de avaliações

    # === TEMPO DE JOGO ===
    playtime_main = db.Column(db.Integer)  # Horas (story principal)
    playtime_extra = db.Column(db.Integer)  # Main + extras
    playtime_completionist = db.Column(db.Integer)  # 100%

    # === METADADOS ADICIONAIS ===
    genres_json = db.Column(db.JSON)  # ["Action", "Adventure"]
    tags_json = db.Column(db.JSON)  # ["Open World", "RPG"]
    screenshots_json = db.Column(db.JSON)  # [{"url": "...", "source": "rawg"}]

    # Materialized counters to speed up common filters (populated by update_titles)
    redundant_updates_count = db.Column(db.Integer, default=0, index=True)
    missing_dlcs_count = db.Column(db.Integer, default=0, index=True)

    # === API TRACKING ===
    rawg_id = db.Column(db.Integer)  # ID no RAWG
    igdb_id = db.Column(db.Integer)  # ID no IGDB
    api_last_update = db.Column(db.DateTime)  # Quando foi atualizado
    api_source = db.Column(db.String(20))  # "rawg" | "igdb" | "manual"

    tags = db.relationship("Tag", secondary="title_tag", backref=db.backref("titles", lazy="dynamic"))


# TitleDB Cache - stores downloaded TitleDB data for fast access
