"""Pre-assigned (holiday) shift management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.api.dependencies import get_repository
from app.persistence.exceptions import EntityNotFoundError
from app.persistence.models import ENTITY_ID_PATTERN, PreAssignedShiftRecord
from app.persistence.repository import RepositoryProtocol

router = APIRouter(prefix="/preassigned", tags=["PreAssigned"])

RepoDep = Annotated[RepositoryProtocol, Depends(get_repository)]
PreassignedIdPath = Annotated[
    str, Path(pattern=ENTITY_ID_PATTERN, description="Preassigned shift identifier")
]


@router.get("", response_model=list[PreAssignedShiftRecord])
def list_preassigned(
    repo: RepoDep,
) -> list[PreAssignedShiftRecord]:
    """List all pre-assigned (holiday or locked) shifts."""
    return repo.list_preassigned()


@router.post("", response_model=PreAssignedShiftRecord, status_code=status.HTTP_201_CREATED)
def create_preassigned(
    record: PreAssignedShiftRecord,
    repo: RepoDep,
) -> PreAssignedShiftRecord:
    """Create or overwrite a pre-assigned shift."""
    staff = repo.get_staff(record.staff_id)
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Staff member '{record.staff_id}' does not exist.",
        )
    repo.save_preassigned(record)
    return record


@router.put("/{preassigned_id}", response_model=PreAssignedShiftRecord)
def update_preassigned(
    preassigned_id: PreassignedIdPath,
    record: PreAssignedShiftRecord,
    repo: RepoDep,
) -> PreAssignedShiftRecord:
    """Update an existing pre-assigned shift record."""
    if record.id != preassigned_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Path ID '{preassigned_id}' does not match payload ID '{record.id}'.",
        )
    staff = repo.get_staff(record.staff_id)
    if not staff:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Staff member '{record.staff_id}' does not exist.",
        )
    existing = repo.get_preassigned(preassigned_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pre-assigned shift '{preassigned_id}' does not exist.",
        )
    repo.save_preassigned(record)
    return record


@router.delete("/{preassigned_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preassigned(
    preassigned_id: PreassignedIdPath,
    repo: RepoDep,
) -> None:
    """Delete a pre-assigned shift record by ID."""
    try:
        repo.delete_preassigned(preassigned_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
