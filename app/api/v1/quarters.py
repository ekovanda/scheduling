"""Quarter schedule management, solver generation, and lifecycle endpoints."""

from datetime import UTC, date, datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field

from app.api.dependencies import get_repository
from app.exporters.excel import export_schedule_to_csv, export_schedule_to_excel
from app.persistence.exceptions import EntityNotFoundError
from app.persistence.models import (
    QuarterScheduleDocument,
    ScheduleState,
    ShiftAssignmentRecord,
)
from app.persistence.repository import FileJsonRepository
from app.persistence.rollover import (
    get_previous_quarter_context,
    get_quarter_date_range,
)
from app.scheduler.models import (
    Assignment,
    Schedule,
    Shift,
    ShiftType,
    Staff,
    Vacation,
)
from app.scheduler.solver import generate_schedule
from app.scheduler.validator import validate_schedule

router = APIRouter(prefix="/quarters", tags=["Quarters"])

RepoDep = Annotated[FileJsonRepository, Depends(get_repository)]


class GenerateScheduleRequest(BaseModel):
    """Payload for triggering the synchronous solver."""

    max_solve_time_seconds: int = Field(default=120, ge=5, le=300)
    random_seed: int | None = None
    include_previous_context: bool = True


class ShiftSwapRequest(BaseModel):
    """Payload for swapping or reassigning a shift."""

    shift_date: date
    shift_type: ShiftType
    old_staff_id: str
    new_staff_id: str
    reason: str
    force: bool = False


class ValidationReport(BaseModel):
    """Result of rule validation on a quarterly plan."""

    is_valid: bool
    violations: list[str]
    soft_penalty: float


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


@router.get("/{quarter_key}/rollover")
def get_quarter_rollover_context(
    quarter_key: str,
    repo: RepoDep,
) -> dict[str, Any]:
    """Retrieve automated carry-over fairness deltas and trailing 21-day border shifts."""
    year, quarter = _parse_quarter_key(quarter_key)
    ctx = get_previous_quarter_context(year, quarter, repo)
    if not ctx:
        return {
            "has_context": False,
            "message": f"Kein historischer Vorplan für {year}-Q{quarter} vorhanden.",
            "carry_forward": [],
            "trailing_assignments": [],
        }
    return {
        "has_context": True,
        "quarter_start": ctx.quarter_start.isoformat(),
        "quarter_end": ctx.quarter_end.isoformat(),
        "carry_forward": [entry.model_dump() for entry in ctx.carry_forward],
        "trailing_assignments": [
            {
                "staff_identifier": t.staff_identifier,
                "shift_date": t.shift_date.isoformat(),
                "shift_type": t.shift_type.value,
                "is_night": t.shift_type.value.startswith("N_"),
                "is_paired": t.is_paired,
            }
            for t in ctx.trailing_assignments
        ],
        "vet_active_last_month_ids": ctx.vet_active_last_month_ids,
    }


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


@router.post("/{quarter_key}/generate", response_model=QuarterScheduleDocument)
def generate_quarter_schedule(
    quarter_key: str,
    repo: RepoDep,
    req: GenerateScheduleRequest | None = None,
) -> QuarterScheduleDocument:
    """Synchronously run CP-SAT solver and persist candidate schedule."""
    solver_req = req or GenerateScheduleRequest()
    year, quarter = _parse_quarter_key(quarter_key)
    q_start, q_end = get_quarter_date_range(year, quarter)

    active_members = repo.list_staff(active_only=True)
    if not active_members:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active staff members found in database. Onboard staff first.",
        )

    staff_list: list[Staff] = [m.to_scheduler_staff() for m in active_members]
    staff_id_to_ident = {m.id: m.identifier for m in active_members}

    # Load recorded absences overlapping this quarter
    raw_absences = repo.list_absences_for_range(start=q_start, end=q_end)
    vacations: list[Vacation] = [
        Vacation(
            identifier=staff_id_to_ident.get(a.staff_id, a.staff_id),
            start_date=a.start_date,
            end_date=a.end_date,
        )
        for a in raw_absences
    ]

    # Automated roll-over context from preceding quarter
    context = None
    if solver_req.include_previous_context:
        context = get_previous_quarter_context(year, quarter, repo)

    result = generate_schedule(
        staff_list=staff_list,
        quarter_start=q_start,
        vacations=vacations,
        max_solve_time_seconds=solver_req.max_solve_time_seconds,
        random_seed=solver_req.random_seed,
        previous_context=context,
    )

    best_schedule = result.get_best_schedule()
    if not result.success or best_schedule is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "message": "Solver could not find a feasible schedule.",
                "unsatisfiable_constraints": result.unsatisfiable_constraints,
            },
        )

    assignment_records = [
        ShiftAssignmentRecord(
            shift_date=a.shift.shift_date,
            shift_type=a.shift.shift_type,
            planned_staff_id=a.staff_identifier,
            actual_staff_id=a.staff_identifier,
            is_paired=a.is_paired,
            is_override=False,
        )
        for a in best_schedule.assignments
    ]

    metrics = {
        "best_penalty": result.penalties[0] if result.penalties else 0.0,
        "candidate_count": len(result.schedules),
        "convergence_steps": len(result.convergence_log),
        "trailing_context_applied": context is not None,
    }

    doc = repo.get_schedule(quarter_key)
    if not doc:
        doc = QuarterScheduleDocument(
            quarter_key=quarter_key,
            year=year,
            quarter=quarter,
            state=ScheduleState.DRAFT,
        )

    doc.assignments = assignment_records
    doc.solver_metrics = metrics
    doc.updated_at = datetime.now(UTC)
    repo.save_schedule(doc)
    return doc


@router.post("/{quarter_key}/shifts/swap", response_model=QuarterScheduleDocument)
def swap_shift(
    quarter_key: str,
    swap_req: ShiftSwapRequest,
    repo: RepoDep,
) -> QuarterScheduleDocument:
    """Swap or reassign a shift with live constraint validation."""
    doc = repo.get_schedule(quarter_key)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quarter schedule '{quarter_key}' not found.",
        )

    new_member = repo.get_staff(swap_req.new_staff_id)
    if not new_member:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Replacement staff member '{swap_req.new_staff_id}' does not exist.",
        )

    target_idx: int | None = None
    for idx, a in enumerate(doc.assignments):
        if (
            a.shift_date == swap_req.shift_date
            and a.shift_type == swap_req.shift_type
            and a.actual_staff_id == swap_req.old_staff_id
        ):
            target_idx = idx
            break

    if target_idx is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Shift assignment on {swap_req.shift_date} ({swap_req.shift_type.value}) "
                f"for staff '{swap_req.old_staff_id}' not found."
            ),
        )

    year, quarter = _parse_quarter_key(quarter_key)
    q_start, q_end = get_quarter_date_range(year, quarter)
    all_staff: list[Staff] = [m.to_scheduler_staff() for m in repo.list_staff(active_only=False)]
    context = get_previous_quarter_context(year, quarter, repo)

    proposed_assignments: list[Assignment] = []
    for idx, a in enumerate(doc.assignments):
        staff_id = swap_req.new_staff_id if idx == target_idx else a.actual_staff_id
        proposed_assignments.append(
            Assignment(
                shift=Shift(shift_type=a.shift_type, shift_date=a.shift_date),
                staff_identifier=staff_id,
                is_paired=a.is_paired,
            )
        )
    proposed_schedule = Schedule(
        quarter_start=q_start,
        quarter_end=q_end,
        assignments=proposed_assignments,
    )

    if not swap_req.force:
        val_result = validate_schedule(proposed_schedule, all_staff, previous_context=context)
        if not val_result.is_valid():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": "Shift swap violates scheduling constraints.",
                    "violations": [str(v) for v in val_result.hard_violations],
                },
            )

    target = doc.assignments[target_idx]
    target.actual_staff_id = swap_req.new_staff_id
    target.is_override = True
    target.override_reason = swap_req.reason
    target.override_timestamp = datetime.now(UTC)
    doc.updated_at = datetime.now(UTC)
    repo.save_schedule(doc)
    return doc


@router.post("/{quarter_key}/validate", response_model=ValidationReport)
def validate_quarter_plan(
    quarter_key: str,
    repo: RepoDep,
) -> ValidationReport:
    """Validate current quarterly assignments against all constraints."""
    doc = repo.get_schedule(quarter_key)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quarter schedule '{quarter_key}' not found.",
        )

    if not doc.assignments:
        return ValidationReport(is_valid=True, violations=[], soft_penalty=0.0)

    year, quarter = _parse_quarter_key(quarter_key)
    q_start, q_end = get_quarter_date_range(year, quarter)
    all_staff = [m.to_scheduler_staff() for m in repo.list_staff(active_only=False)]
    context = get_previous_quarter_context(year, quarter, repo)

    current_assignments = [
        Assignment(
            shift=Shift(shift_type=a.shift_type, shift_date=a.shift_date),
            staff_identifier=a.actual_staff_id,
            is_paired=a.is_paired,
        )
        for a in doc.assignments
    ]
    schedule = Schedule(
        quarter_start=q_start,
        quarter_end=q_end,
        assignments=current_assignments,
    )
    val_result = validate_schedule(schedule, all_staff, previous_context=context)

    return ValidationReport(
        is_valid=val_result.is_valid(),
        violations=[str(v) for v in val_result.hard_violations],
        soft_penalty=val_result.soft_penalty,
    )


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


@router.get("/{quarter_key}/export")
def export_quarter_schedule(
    quarter_key: str,
    repo: RepoDep,
    export_format: Annotated[
        str,
        Query(
            alias="format",
            pattern="^(xlsx|csv)$",
            description="Export format: 'xlsx' (default) or 'csv'",
        ),
    ] = "xlsx",
) -> Response:
    """Export quarterly schedule to styled Excel workbook or CSV for noticeboards."""
    doc = repo.get_schedule(quarter_key)
    if not doc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Quarter schedule '{quarter_key}' not found.",
        )
    if not doc.assignments:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Quarter schedule '{quarter_key}' has no assignments to export.",
        )

    staff_members = repo.list_staff(active_only=False)
    staff_map = {m.id: m for m in staff_members}

    if export_format == "csv":
        csv_data = export_schedule_to_csv(doc)
        return Response(
            content=csv_data,
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="Dienstplan_{quarter_key}.csv"'},
        )

    excel_bytes = export_schedule_to_excel(doc, staff_map=staff_map)
    return Response(
        content=excel_bytes,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="Dienstplan_{quarter_key}.xlsx"'},
    )
