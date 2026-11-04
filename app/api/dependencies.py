"""FastAPI dependency providers."""

import os
from functools import lru_cache

from app.persistence.repository import FileJsonRepository


@lru_cache
def get_repository() -> FileJsonRepository:
    """Provide a singleton repository instance configured via DATA_DIR environment variable."""
    base_dir = os.environ.get("DATA_DIR", "data/db")
    return FileJsonRepository(base_dir=base_dir)
