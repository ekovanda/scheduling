"""Quarter schedule management and lifecycle endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_repository
from app.persistence.exceptions import EntityNotFoundError
from app.persistence.models import (
    QuarterScheduleDocument,
    ScheduleState,
)
from app.persistence.repository import FileJsonRepository

router = APIRouter(prefix="/quarters", tags=["Quarters"])

RepoDep = Annotated[FileJsonRepository, Depends(get_repository)]


def _parse_quarter_key(quarter_key: str) -> tuple[int, int]:
    """Parse 'YYYY-QX' string into (year, quarter)."""
    parts = quarter_key.split("-Q")
    if len(parts) != 2:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid quarter key format '{quarter_key}'. "
                "Expected format: 'YYYY-QX' (e.g. '2026-Q2')."
            ),
        )
    try:
        year = int(parts[0])
        quarter = int(parts[1])
        if quarter not in (1, 2, 3, 4):
            raise ValueError()
        return year, quarter
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid quarter '{quarter_key}'. Year must be valid "
                "and quarter must be 1, 2, 3, or 4."
            ),
        ) from None


@router.get("", response_model=list[QuarterScheduleDocument])
def list_schedules(
    repo: RepoDep,
) -> list[QuarterScheduleDocument]:
    """List all persisted quarter schedule documents."""
    return repo.list_schedules()


@router.get("/{quarter_key}", response_model=QuarterScheduleDocument)
def get_schedule(
    quarter_key: str,
    repo: RepoDep,
) -> QuarterScheduleDocument:
    """Retrieve a quarter schedule document by key."""
    doc = repo.get_schedule(quarter_key)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quarter schedule '{quarter_key}' not found.",
        )
    return doc


@router.post(
    "/{quarter_key}/init",
    response_model=QuarterScheduleDocument,
    status_code=status.HTTP_201_CREATED,
)
def init_quarter(
    quarter_key: str,
    repo: RepoDep,
) -> QuarterScheduleDocument:
    """Initialize a new quarterly planning draft."""
    existing = repo.get_schedule(quarter_key)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Quarter schedule '{quarter_key}' already exists in state "
                f"'{existing.state.value}'."
            ),
        )
    year, quarter = _parse_quarter_key(quarter_key)
    doc = QuarterScheduleDocument(
        quarter_key=quarter_key,
        year=year,
        quarter=quarter,
        state=ScheduleState.DRAFT,
    )
    repo.save_schedule(doc)
    return doc


@router.post("/{quarter_key}/publish", response_model=QuarterScheduleDocument)
def publish_quarter(
    quarter_key: str,
    repo: RepoDep,
) -> QuarterScheduleDocument:
    """Publish a draft schedule as the official schedule (Soll-Plan)."""
    doc = repo.get_schedule(quarter_key)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quarter schedule '{quarter_key}' not found.",
        )
    if doc.state != ScheduleState.DRAFT:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot publish schedule in '{doc.state.value}' state. Must be in DRAFT.",
        )
    doc.state = ScheduleState.PUBLISHED
    doc.updated_at = datetime.now(UTC)
    repo.save_schedule(doc)
    return doc


@router.post("/{quarter_key}/lock", response_model=QuarterScheduleDocument)
def lock_quarter(
    quarter_key: str,
    repo: RepoDep,
) -> QuarterScheduleDocument:
    """Lock quarter into CLOSED state for historical continuity."""
    doc = repo.get_schedule(quarter_key)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quarter schedule '{quarter_key}' not found.",
        )
    doc.state = ScheduleState.CLOSED
    doc.updated_at = datetime.now(UTC)
    repo.save_schedule(doc)
    return doc


@router.delete("/{quarter_key}", status_code=status.HTTP_204_NO_CONTENT)
def delete_schedule(
    quarter_key: str,
    repo: RepoDep,
) -> None:
    """Delete a draft schedule document."""
    doc = repo.get_schedule(quarter_key)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quarter schedule '{quarter_key}' not found.",
        )
    if doc.state in (ScheduleState.PUBLISHED, ScheduleState.CLOSED):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Cannot delete schedule in '{doc.state.value}' state. "
                "Must be unlocked or in DRAFT."
            ),
        )
    try:
        repo.delete_schedule(quarter_key)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
