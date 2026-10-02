from functools import lru_cache

from backend.app.pipeline.runner import Services
from backend.app.settings import get_settings
from backend.app.storage.db import Database
from backend.app.storage.media_store import MediaKeyMissing, MediaStore, load_key


def build_services(settings) -> Services:
    try:
        key = load_key(settings.media_key)
    except MediaKeyMissing:
        key = None
    return Services(
        settings=settings,
        db=Database(settings.db_path, key),
        store=MediaStore(settings.media_dir, key) if key else None,
        key=key,
    )


@lru_cache
def _default_services() -> Services:
    return build_services(get_settings())


def get_services() -> Services:
    """FastAPI dependency; tests override it."""
    return _default_services()
