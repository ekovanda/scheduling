"""Pre-assigned (holiday) shift management endpoints."""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_repository
from app.api.v1.auth import require_planner
from app.persistence.exceptions import EntityNotFoundError
from app.persistence.models import PreAssignedShiftRecord
from app.persistence.repository import RepositoryProtocol

router = APIRouter(prefix="/preassigned", tags=["PreAssigned"])

RepoDep = Annotated[RepositoryProtocol, Depends(get_repository)]
PlannerDep = Annotated[bool, Depends(require_planner)]


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
    _planner: PlannerDep = True,
) -> PreAssignedShiftRecord:
    """Create or overwrite a pre-assigned shift."""
    repo.save_preassigned(record)
    return record


@router.delete("/{preassigned_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_preassigned(
    preassigned_id: str,
    repo: RepoDep,
    _planner: PlannerDep = True,
) -> None:
    """Delete a pre-assigned shift record by ID."""
    try:
        repo.delete_preassigned(preassigned_id)
    except EntityNotFoundError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc

