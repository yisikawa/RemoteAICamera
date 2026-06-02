"""Dependency injection for FastAPI"""
from functools import lru_cache
from pathlib import Path

from db.store import EventStore


@lru_cache(maxsize=1)
def get_event_store() -> EventStore:
    """EventStore singleton"""
    from config import load_config
    cfg = load_config()
    return EventStore(db_path=cfg.storage.db_path)
