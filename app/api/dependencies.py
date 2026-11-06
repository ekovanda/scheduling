"""FastAPI dependency providers."""

import os
from functools import lru_cache

from app.persistence.repository import FileJsonRepository, RepositoryProtocol


@lru_cache
def get_repository() -> RepositoryProtocol:
    """Provide a singleton repository instance configured via STORAGE_BACKEND.

    Options:
      - 'firestore': Google Cloud Firestore (production on Cloud Run)
      - 'file': Local JSON file repository in DATA_DIR (default for local dev/tests)
    """
    backend = os.getenv("STORAGE_BACKEND", "file").strip().lower()
    if backend == "firestore":
        from app.persistence.firestore_repository import FirestoreRepository

        return FirestoreRepository()

    base_dir = os.environ.get("DATA_DIR", "data/db")
    return FileJsonRepository(base_dir=base_dir)
