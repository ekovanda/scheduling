"""Staff member management endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_repository
from app.persistence.exceptions import EntityNotFoundError
from app.persistence.models import StaffMember
from app.persistence.repository import RepositoryProtocol

router = APIRouter(prefix="/staff", tags=["Staff"])

RepoDep = Annotated[RepositoryProtocol, Depends(get_repository)]


@router.get("", response_model=list[StaffMember])
def list_staff(
    repo: RepoDep,
    active_only: bool = True,
) -> list[StaffMember]:
    """List staff members, optionally filtered by active status."""
    return repo.list_staff(active_only=active_only)


@router.post("", response_model=StaffMember, status_code=status.HTTP_201_CREATED)
def create_staff(
    member: StaffMember,
    repo: RepoDep,
) -> StaffMember:
    """Create a new staff member."""
    existing = repo.get_staff(member.id)
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Staff member with id '{member.id}' already exists.",
        )
    # Ensure identifier uniqueness among existing staff
    all_members = repo.list_staff(active_only=False)
    for m in all_members:
        if m.identifier.upper() == member.identifier.upper():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Staff member with identifier '{member.identifier}' already exists.",
            )
    repo.save_staff(member)
    return member


@router.get("/{staff_id}", response_model=StaffMember)
def get_staff_by_id(
    staff_id: str,
    repo: RepoDep,
) -> StaffMember:
    """Retrieve a staff member by ID."""
    member = repo.get_staff(staff_id)
    if not member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Staff member with id '{staff_id}' not found.",
        )
    return member


@router.put("/{staff_id}", response_model=StaffMember)
def update_staff(
    staff_id: str,
    updated_data: StaffMember,
    repo: RepoDep,
) -> StaffMember:
    """Update an existing staff member."""
    existing = repo.get_staff(staff_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Staff member with id '{staff_id}' not found.",
        )
    updated_data.id = staff_id
    updated_data.updated_at = datetime.now(UTC)
    repo.save_staff(updated_data)
    return updated_data


@router.delete("/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_staff(
    staff_id: str,
    repo: RepoDep,
    hard_delete: bool = False,
) -> None:
    """Deactivate (default) or hard-delete a staff member."""
    existing = repo.get_staff(staff_id)
    if not existing:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Staff member with id '{staff_id}' not found.",
        )
    if hard_delete:
        try:
            repo.delete_staff(staff_id)
        except EntityNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=str(exc),
            ) from exc
    else:
        existing.is_active = False
        existing.updated_at = datetime.now(UTC)
        repo.save_staff(existing)


@router.post("/bulk-import", response_model=dict[str, int])
def bulk_import_staff(
    members: list[StaffMember],
    repo: RepoDep,
) -> dict[str, int]:
    """Bulk import or upsert staff records."""
    count = 0
    for member in members:
        repo.save_staff(member)
        count += 1
    return {"imported": count}
