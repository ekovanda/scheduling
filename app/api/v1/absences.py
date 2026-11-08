"""Absence and vacation ledger endpoints."""

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_repository
from app.persistence.exceptions import EntityNotFoundError
from app.persistence.models import AbsenceRecord
from app.persistence.repository import RepositoryProtocol

router = APIRouter(prefix="/absences", tags=["Absences"])

RepoDep = Annotated[RepositoryProtocol, Depends(get_repository)]
StaffIdQuery = Annotated[
    str | None, Query(description="Filter absences for a specific staff member")
]
StartDateQuery = Annotated[date | None, Query(description="Start date of filter window")]
EndDateQuery = Annotated[date | None, Query(description="End date of filter window")]


@router.get("", response_model=list[AbsenceRecord])
def list_absences(
    repo: RepoDep,
    staff_id: StaffIdQuery = None,
    start_date: StartDateQuery = None,
    end_date: EndDateQuery = None,
) -> list[AbsenceRecord]:
    """Query absence records with optional staff and date range filtering."""
    if start_date and end_date:
        if start_date > end_date:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="start_date cannot be after end_date.",
            )
        return repo.list_absences_for_range(start=start_date, end=end_date, staff_id=staff_id)
    if staff_id:
        return repo.list_absences_by_staff(staff_id=staff_id)
    # Default: return all records overlapping a broad default window if not specified
    return repo.list_absences_for_range(
        start=date(2000, 1, 1),
        end=date(2100, 12, 31),
        staff_id=staff_id,
    )


@router.post("", response_model=AbsenceRecord, status_code=status.HTTP_201_CREATED)
def create_absence(
    absence: AbsenceRecord,
    repo: RepoDep,
) -> AbsenceRecord:
    """Record a new absence entry in the ledger."""
    # Verify staff member exists
    staff = repo.get_staff(absence.staff_id)
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Staff member with id '{absence.staff_id}' does not exist.",
        )
    existing = repo.get_absence(absence.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Absence record with id '{absence.id}' already exists.",
        )
    repo.save_absence(absence)
    return absence


@router.get("/{absence_id}", response_model=AbsenceRecord)
def get_absence_by_id(
    absence_id: str,
    repo: RepoDep,
) -> AbsenceRecord:
    """Retrieve an absence record by ID."""
    absence = repo.get_absence(absence_id)
    if not absence:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Absence record with id '{absence_id}' not found.",
        )
    return absence


@router.delete("/{absence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_absence(
    absence_id: str,
    repo: RepoDep,
) -> None:
    """Delete an absence record by ID."""
    try:
        repo.delete_absence(absence_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
