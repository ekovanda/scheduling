"""Staff member management endpoints."""

from datetime import UTC, datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.api.dependencies import get_repository
from app.persistence.exceptions import EntityNotFoundError
from app.persistence.models import ENTITY_ID_PATTERN, StaffMember
from app.persistence.repository import RepositoryProtocol

router = APIRouter(prefix="/staff", tags=["Staff"])

RepoDep = Annotated[RepositoryProtocol, Depends(get_repository)]
StaffIdPath = Annotated[str, Path(pattern=ENTITY_ID_PATTERN, description="Staff identifier")]


def check_identifier_unique(
    repo: RepositoryProtocol,
    identifier: str,
    exclude_id: str | None = None,
) -> None:
    """Ensure staff identifier is unique across all existing staff records."""
    all_members = repo.list_staff(active_only=False)
    for m in all_members:
        if exclude_id and m.id == exclude_id:
            continue
        if m.identifier.strip().upper() == identifier.strip().upper():
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Staff member with identifier '{identifier}' already exists.",
            )


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
    check_identifier_unique(repo, member.identifier, exclude_id=member.id)
    repo.save_staff(member)
    return member


@router.get("/{staff_id}", response_model=StaffMember)
def get_staff_by_id(
    staff_id: StaffIdPath,
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
    staff_id: StaffIdPath,
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
    check_identifier_unique(repo, updated_data.identifier, exclude_id=staff_id)
    updated_data.id = staff_id
    updated_data.updated_at = datetime.now(UTC)
    repo.save_staff(updated_data)
    return updated_data


def _cascade_delete_staff_associations(
    repo: RepositoryProtocol,
    staff: StaffMember,
) -> None:
    """Cascade delete all absences and pre-assigned shifts associated with a staff member."""
    target_keys = {
        staff.id,
        staff.identifier,
        staff.id.lower(),
        staff.identifier.lower(),
        staff.identifier.upper(),
    }

    absence_ids: set[str] = set()
    for key in target_keys:
        if not key:
            continue
        try:
            for absence in repo.list_absences_by_staff(key):
                absence_ids.add(absence.id)
        except Exception:
            pass

    for aid in absence_ids:
        try:
            repo.delete_absence(aid)
        except EntityNotFoundError:
            pass

    try:
        for pa in repo.list_preassigned():
            if pa.staff_id in target_keys or pa.staff_identifier in target_keys:
                try:
                    repo.delete_preassigned(pa.id)
                except EntityNotFoundError:
                    pass
    except Exception:
        pass


@router.delete("/{staff_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_staff(
    staff_id: StaffIdPath,
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
        _cascade_delete_staff_associations(repo, existing)
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
    seen_ids: set[str] = set()
    seen_identifiers: set[str] = set()
    for m in members:
        if m.id in seen_ids:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Duplicate id '{m.id}' within import batch.",
            )
        ident_upper = m.identifier.strip().upper()
        if ident_upper in seen_identifiers:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Duplicate identifier '{m.identifier}' within import batch.",
            )
        seen_ids.add(m.id)
        seen_identifiers.add(ident_upper)

    for m in members:
        check_identifier_unique(repo, m.identifier, exclude_id=m.id)

    count = 0
    for member in members:
        repo.save_staff(member)
        count += 1
    return {"imported": count}
