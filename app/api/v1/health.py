"""Health check endpoints."""

from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter

from app.release_info import CURRENT_VERSION

router = APIRouter(tags=["Health"])


@router.get("/health")
def get_health() -> dict[str, Any]:
    """Return health status, current version, and UTC timestamp."""
    return {
        "status": "ok",
        "service": "dienstplan-api",
        "version": CURRENT_VERSION,
        "timestamp": datetime.now(UTC).isoformat(),
    }
