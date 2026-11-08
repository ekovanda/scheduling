"""Quarter schedule management, solver generation, and lifecycle endpoints."""

import threading
import time
from datetime import UTC, date, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from ortools.sat.python import cp_model
from pydantic import BaseModel, Field

from app.api.dependencies import get_repository
from app.exporters.excel import export_schedule_to_csv, export_schedule_to_excel
from app.persistence.exceptions import EntityNotFoundError
from app.persistence.models import (
    FeasibilityReportRecord,
    QuarterScheduleDocument,
    ScheduleState,
    ShiftAssignmentRecord,
    SolverJobRecord,
    SolverJobStatus,
)
from app.persistence.repository import RepositoryProtocol
from app.persistence.rollover import (
    get_previous_quarter_context,
    get_quarter_date_range,
)
from app.scheduler.feasibility import run_full_feasibility_check
from app.scheduler.models import (
    Assignment,
    Beruf,
    PreAssignedShift,
    Schedule,
    Shift,
    ShiftType,
    Staff,
    Vacation,
    calculate_available_days,
)
from app.scheduler.solver import generate_schedule
from app.scheduler.validator import validate_schedule

router = APIRouter(prefix="/quarters", tags=["Quarters"])

RepoDep = Annotated[RepositoryProtocol, Depends(get_repository)]


class GenerateScheduleRequest(BaseModel):
    """Payload for triggering the asynchronous solver."""

    max_solve_time_seconds: int = Field(default=600, ge=5, le=1200)
    random_seed: int | None = None
    include_previous_context: bool = True
    stagnation_limit_seconds: float | None = Field(default=30.0, ge=2.0, le=300.0)


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
        if not (2020 <= year <= 2100):
            raise ValueError(f"Year must be between 2020 and 2100 (got {year}).")
        if quarter not in (1, 2, 3, 4):
            raise ValueError(f"Quarter must be 1, 2, 3, or 4 (got {quarter}).")
        return year, quarter
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Invalid quarter '{quarter_key}'. {err}"
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


class StaffFairnessRecord(BaseModel):
    identifier: str
    name: str
    beruf: str
    hours: int
    vacation_days: int
    presence_factor: float
    effective_nights: float
    weekend_shifts: int
    total_notdienst: float
    normalized_40h: float
    group_mean_40h: float
    plan_delta: float
    cf_delta: float
    net_delta: float
    status: str
    explanation: str


class GroupFairnessSummary(BaseModel):
    beruf: str
    total_staff: int
    active_with_shifts: int
    group_mean_40h: float
    min_norm: float
    max_norm: float
    plan_spread: float
    min_net: float
    max_net: float
    net_spread: float
    balanced_pct: float


class QuarterFairnessOverviewResponse(BaseModel):
    quarter_key: str
    has_schedule: bool
    total_shifts: int
    groups: dict[str, GroupFairnessSummary]
    records: list[StaffFairnessRecord]


@router.get("/{quarter_key}/fairness", response_model=QuarterFairnessOverviewResponse)
def get_quarter_fairness_overview(
    quarter_key: str,
    repo: RepoDep,
) -> QuarterFairnessOverviewResponse:
    """Retrieve structured fairness metrics, balanced deltas, and group distributions."""
    year, quarter = _parse_quarter_key(quarter_key)
    q_start, q_end = get_quarter_date_range(year, quarter)
    total_quarter_days = (q_end - q_start).days + 1

    doc = repo.get_schedule(quarter_key)
    has_schedule = doc is not None and bool(doc.assignments)
    total_shifts = len(doc.assignments) if (doc and doc.assignments) else 0

    active_members = repo.list_staff(active_only=False)
    all_staff = [m.to_scheduler_staff() for m in active_members]
    staff_id_to_ident = {m.id: m.identifier for m in active_members}

    raw_absences = repo.list_absences_for_range(start=q_start, end=q_end)
    vacations = [
        Vacation(
            identifier=staff_id_to_ident.get(a.staff_id, a.staff_id),
            start_date=a.start_date,
            end_date=a.end_date,
        )
        for a in raw_absences
    ]

    context = get_previous_quarter_context(year, quarter, repo)
    prev_cf = (
        {entry.identifier: entry.carry_forward_delta for entry in context.carry_forward}
        if context
        else {}
    )

    current_assignments: list[Assignment] = []
    if doc and doc.assignments:
        current_assignments = [
            Assignment(
                shift=Shift(shift_type=a.shift_type, shift_date=a.shift_date),
                staff_identifier=a.actual_staff_id,
                is_paired=a.is_paired,
            )
            for a in doc.assignments
        ]
    schedule = Schedule(quarter_start=q_start, quarter_end=q_end, assignments=current_assignments)

    all_records: list[StaffFairnessRecord] = []
    groups_summary: dict[str, GroupFairnessSummary] = {}

    for role_name in ["TFA", "Azubi", "Intern", "Vet"]:
        group_staff = [
            s
            for s in all_staff
            if (s.beruf.value == role_name) or (role_name == "Vet" and s.beruf == Beruf.VET)
        ]

        temp_recs = []
        for s in group_staff:
            avail_days = calculate_available_days(
                s.identifier, vacations, q_start, q_end, effective_start=s.available_from
            )
            if avail_days <= 0:
                continue
            vacation_days = max(0, total_quarter_days - avail_days)
            presence = avail_days / total_quarter_days if total_quarter_days > 0 else 1.0
            eff_hours = s.hours if s.hours > 0 else 40

            we = schedule.count_weekends(s.identifier, s)
            nights = schedule.count_effective_nights(s.identifier, s)
            tot = schedule.count_total_notdienst(s.identifier, s)

            load = nights if s.beruf == Beruf.INTERN else tot
            norm = (load / eff_hours / presence) * 40 if presence > 0 else 0.0

            temp_recs.append(
                {
                    "staff": s,
                    "hours": s.hours,
                    "vacation_days": vacation_days,
                    "presence_factor": round(presence, 4),
                    "effective_nights": round(nights, 2),
                    "weekend_shifts": we,
                    "total_notdienst": round(tot, 2),
                    "normalized_40h": round(norm, 2),
                    "weight": eff_hours * presence,
                }
            )

        total_w = sum(r["weight"] for r in temp_recs)
        group_mean = (
            sum(r["normalized_40h"] * r["weight"] for r in temp_recs) / total_w
            if total_w > 0
            else 0.0
        )
        group_mean = round(group_mean, 2)

        role_records: list[StaffFairnessRecord] = []
        for r in temp_recs:
            s = r["staff"]
            plan_delta = round(r["normalized_40h"] - group_mean, 2)
            cf_delta = round(prev_cf.get(s.identifier, 0.0), 2)
            net_delta = round(plan_delta + cf_delta, 2)

            abs_net = abs(net_delta)
            if abs_net <= 0.5:
                status_str = "balanced"
                if abs(cf_delta) >= 0.5:
                    exp = f"Vorquartal ({cf_delta:+.2f}) durch aktuellen Plan ({plan_delta:+.2f}) erfolgreich neutralisiert."
                else:
                    exp = "Exakt im fairen Zielbereich der Berufsgruppe."
            elif abs_net <= 1.0:
                status_str = "slight_deviation"
                exp = f"Leichte Netto-Abweichung von {net_delta:+.2f} Diensten (wird im Folgequartal ausgeglichen)."
            else:
                status_str = "warning"
                exp = f"Netto-Abweichung von {net_delta:+.2f} Diensten (Prioritärer Ausgleich im Folgequartal)."

            rec = StaffFairnessRecord(
                identifier=s.identifier,
                name=s.name,
                beruf=role_name,
                hours=r["hours"],
                vacation_days=r["vacation_days"],
                presence_factor=r["presence_factor"],
                effective_nights=r["effective_nights"],
                weekend_shifts=r["weekend_shifts"],
                total_notdienst=r["total_notdienst"],
                normalized_40h=r["normalized_40h"],
                group_mean_40h=group_mean,
                plan_delta=plan_delta,
                cf_delta=cf_delta,
                net_delta=net_delta,
                status=status_str,
                explanation=exp,
            )
            role_records.append(rec)
            all_records.append(rec)

        if role_records:
            norms = [r.normalized_40h for r in role_records]
            nets = [r.net_delta for r in role_records]
            balanced_c = sum(1 for r in role_records if r.status == "balanced")
            groups_summary[role_name] = GroupFairnessSummary(
                beruf=role_name,
                total_staff=len(role_records),
                active_with_shifts=sum(1 for r in role_records if r.total_notdienst > 0),
                group_mean_40h=group_mean,
                min_norm=round(min(norms), 2),
                max_norm=round(max(norms), 2),
                plan_spread=round(max(norms) - min(norms), 2),
                min_net=round(min(nets), 2),
                max_net=round(max(nets), 2),
                net_spread=round(max(nets) - min(nets), 2),
                balanced_pct=round((balanced_c / len(role_records)) * 100, 1),
            )
        else:
            groups_summary[role_name] = GroupFairnessSummary(
                beruf=role_name,
                total_staff=0,
                active_with_shifts=0,
                group_mean_40h=0.0,
                min_norm=0.0,
                max_norm=0.0,
                plan_spread=0.0,
                min_net=0.0,
                max_net=0.0,
                net_spread=0.0,
                balanced_pct=100.0,
            )

    return QuarterFairnessOverviewResponse(
        quarter_key=quarter_key,
        has_schedule=has_schedule,
        total_shifts=total_shifts,
        groups=groups_summary,
        records=all_records,
    )


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


class ActiveJobState:
    """In-memory active solver job tracking thread, cancel event, and solver instance."""

    def __init__(
        self,
        job_id: str,
        quarter_key: str,
        thread: threading.Thread,
        cancellation_event: threading.Event,
    ) -> None:
        self.job_id = job_id
        self.quarter_key = quarter_key
        self.thread = thread
        self.cancellation_event = cancellation_event
        self.solver: cp_model.CpSolver | None = None


_active_jobs: dict[str, ActiveJobState] = {}
_jobs_lock = threading.Lock()


def _load_domain_data(
    quarter_key: str,
    repo: RepositoryProtocol,
) -> tuple[int, int, date, date, list[Staff], list[Vacation], list[PreAssignedShift]]:
    """Load and map staff, absences, and pre-assigned shifts for a quarter."""
    year, quarter = _parse_quarter_key(quarter_key)
    q_start, q_end = get_quarter_date_range(year, quarter)

    active_members = repo.list_staff(active_only=True)
    staff_list = [m.to_scheduler_staff() for m in active_members]
    staff_id_to_ident = {m.id: m.identifier for m in active_members}

    raw_absences = repo.list_absences_for_range(start=q_start, end=q_end)
    vacations = [
        Vacation(
            identifier=staff_id_to_ident.get(a.staff_id, a.staff_id),
            start_date=a.start_date,
            end_date=a.end_date,
        )
        for a in raw_absences
    ]

    raw_preassigned = repo.list_preassigned()
    pa_shifts: list[PreAssignedShift] = []
    for r in raw_preassigned:
        if q_start <= r.shift_date <= q_end:
            st = None
            try:
                st = ShiftType(r.shift_type)
            except ValueError:
                if "nacht" in r.shift_type.lower():
                    from app.scheduler.file_loader import _WEEKDAY_TO_NIGHT

                    st = ShiftType(_WEEKDAY_TO_NIGHT[r.shift_date.weekday()])
            if st is not None:
                is_paired = False
                if st.value.startswith("N_"):
                    same_date_nights = [
                        x
                        for x in raw_preassigned
                        if x.shift_date == r.shift_date
                        and (x.shift_type == st.value or "nacht" in x.shift_type.lower())
                    ]
                    is_paired = len(same_date_nights) > 1
                pa_shifts.append(
                    PreAssignedShift(
                        shift_date=r.shift_date,
                        shift_type=st,
                        staff_identifier=r.staff_identifier,
                        is_paired=is_paired,
                    )
                )

    return year, quarter, q_start, q_end, staff_list, vacations, pa_shifts


def _execute_solver_worker(
    quarter_key: str,
    job_id: str,
    max_solve_time_seconds: int,
    random_seed: int | None,
    include_previous_context: bool,
    repo: RepositoryProtocol,
    cancellation_event: threading.Event,
    active_job: ActiveJobState,
    stagnation_limit_seconds: float | None = 15.0,
) -> None:
    """Worker function executed inside background thread."""
    start_time = time.time()

    def on_progress(entry: dict[str, Any]) -> None:
        rec = repo.get_solver_job(quarter_key)
        if rec and rec.status == SolverJobStatus.RUNNING:
            rec.elapsed_seconds = round(time.time() - start_time, 1)
            rec.solutions_found += 1
            rec.best_objective = entry.get("objective")
            rec.soft_penalty = entry.get("objective")
            repo.save_solver_job(rec)

    def on_solver_created(solver: cp_model.CpSolver) -> None:
        active_job.solver = solver

    try:
        year, quarter, q_start, q_end, staff_list, vacations, pa_shifts = _load_domain_data(
            quarter_key, repo
        )

        context = None
        if include_previous_context:
            context = get_previous_quarter_context(year, quarter, repo)

        result = generate_schedule(
            staff_list=staff_list,
            quarter_start=q_start,
            vacations=vacations,
            pre_assigned=pa_shifts if pa_shifts else None,
            max_solve_time_seconds=max_solve_time_seconds,
            random_seed=random_seed,
            previous_context=context,
            cancellation_event=cancellation_event,
            on_progress=on_progress,
            on_solver_created=on_solver_created,
            stagnation_limit_seconds=stagnation_limit_seconds,
            quarter_end=q_end,
            num_workers=2,
        )

        elapsed = round(time.time() - start_time, 1)
        job_rec = repo.get_solver_job(quarter_key) or SolverJobRecord(
            job_id=job_id,
            quarter_key=quarter_key,
            status=SolverJobStatus.RUNNING,
        )
        job_rec.elapsed_seconds = elapsed
        job_rec.completed_at = datetime.now(UTC)

        status_name = getattr(result, "status_name", "UNKNOWN")
        best_bound = getattr(result, "best_objective_bound", None)
        obj_val = getattr(result, "objective_value", None)
        stopped_due_to_stagnation = getattr(result, "stopped_due_to_stagnation", False)
        num_workers = getattr(result, "num_workers", 2)
        optimality_gap = (
            round(abs(obj_val - best_bound), 2)
            if (obj_val is not None and best_bound is not None)
            else None
        )

        job_rec.status_name = status_name
        job_rec.best_objective_bound = best_bound
        job_rec.stopped_due_to_stagnation = stopped_due_to_stagnation
        job_rec.num_workers = num_workers

        if cancellation_event.is_set():
            job_rec.status = SolverJobStatus.CANCELLED
            job_rec.status_name = "CANCELLED"
            job_rec.error = "Berechnung durch Benutzer abgebrochen."
            repo.save_solver_job(job_rec)
            return

        best_schedule = result.get_best_schedule()
        hard_violations = getattr(result, "hard_violations", [])
        if not result.success or best_schedule is None or hard_violations:
            job_rec.status = SolverJobStatus.FAILED
            err_msg = (
                "; ".join(result.unsatisfiable_constraints or hard_violations)
                if (result.unsatisfiable_constraints or hard_violations)
                else "Kein machbarer Dienstplan gefunden."
            )
            job_rec.error = err_msg
            job_rec.diagnostics = getattr(result, "diagnostics", [])
            repo.save_solver_job(job_rec)
            return

        assignment_records = [
            ShiftAssignmentRecord(
                shift_date=a.shift.shift_date,
                shift_type=a.shift.shift_type,
                planned_staff_id=a.staff_identifier,
                actual_staff_id=a.staff_identifier,
                is_paired=a.is_paired,
                is_pre_assigned=a.is_pre_assigned,
                is_override=False,
            )
            for a in best_schedule.assignments
        ]
        best_penalty_val = float(result.penalties[0]) if result.penalties else 0.0
        metrics = {
            "best_penalty": best_penalty_val,
            "candidate_count": len(result.schedules),
            "convergence_steps": len(result.convergence_log),
            "trailing_context_applied": context is not None,
            "solve_time_seconds": elapsed,
            "hard_violations": hard_violations,
            "status_name": status_name,
            "is_optimal": status_name == "OPTIMAL",
            "best_objective_bound": best_bound,
            "objective_value": obj_val,
            "optimality_gap": optimality_gap,
            "stopped_due_to_stagnation": stopped_due_to_stagnation,
            "num_workers": num_workers,
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

        job_rec.status = SolverJobStatus.COMPLETED
        job_rec.best_objective = best_penalty_val
        job_rec.soft_penalty = best_penalty_val
        job_rec.solutions_found = max(job_rec.solutions_found, 1)
        job_rec.status_name = status_name
        job_rec.best_objective_bound = best_bound
        job_rec.stopped_due_to_stagnation = stopped_due_to_stagnation
        job_rec.num_workers = num_workers
        repo.save_solver_job(job_rec)

    except Exception as exc:  # pylint: disable=broad-except
        err_job = repo.get_solver_job(quarter_key)
        if err_job:
            err_job.status = SolverJobStatus.FAILED
            err_job.completed_at = datetime.now(UTC)
            err_job.elapsed_seconds = round(time.time() - start_time, 1)
            err_job.error = str(exc)
            repo.save_solver_job(err_job)
    finally:
        with _jobs_lock:
            if quarter_key in _active_jobs and _active_jobs[quarter_key].job_id == job_id:
                del _active_jobs[quarter_key]


@router.post(
    "/{quarter_key}/validate-feasibility",
    response_model=FeasibilityReportRecord,
)
def validate_quarter_feasibility(
    quarter_key: str,
    repo: RepoDep,
) -> FeasibilityReportRecord:
    """Pre-flight check: validate pre-assigned shifts and capacity feasibility without solving."""
    _parse_quarter_key(quarter_key)
    year, quarter, q_start, q_end, staff_list, vacations, pa_shifts = _load_domain_data(
        quarter_key, repo
    )
    if not staff_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active staff members found in database. Onboard staff first.",
        )

    from app.scheduler.models import SchedulerConfig

    return run_full_feasibility_check(
        staff_list=staff_list,
        vacations=vacations,
        pre_assigned=pa_shifts,
        quarter_start=q_start,
        quarter_end=q_end,
        config=SchedulerConfig(),
        quarter_key=quarter_key,
    )


@router.post(
    "/{quarter_key}/generate",
    response_model=SolverJobRecord,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_quarter_schedule(
    quarter_key: str,
    repo: RepoDep,
    response: Response,
    req: GenerateScheduleRequest | None = None,
    sync: bool = Query(default=False, description="Wait synchronously until solve finishes"),
) -> SolverJobRecord:
    """Launch asynchronous CP-SAT solve (returns 202 Accepted + job_id)."""
    solver_req = req or GenerateScheduleRequest()
    _parse_quarter_key(quarter_key)

    if sync and solver_req.max_solve_time_seconds > 850:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"max_solve_time_seconds ({solver_req.max_solve_time_seconds}s) exceeds "
                "maximum allowable limit of 850s for synchronous solves "
                "(Cloud Run HTTP request timeout is 900s). "
                "Use asynchronous mode (sync=false) for longer solves."
            ),
        )

    year, quarter, q_start, q_end, staff_list, vacations, pa_shifts = _load_domain_data(
        quarter_key, repo
    )
    if not staff_list:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No active staff members found in database. Onboard staff first.",
        )

    # Deterministic Pre-Flight Consistency & Capacity Validation
    from app.scheduler.models import SchedulerConfig

    feasibility_report = run_full_feasibility_check(
        staff_list=staff_list,
        vacations=vacations,
        pre_assigned=pa_shifts,
        quarter_start=q_start,
        quarter_end=q_end,
        config=SchedulerConfig(),
        quarter_key=quarter_key,
    )
    if feasibility_report.blocking_error_count > 0:
        first_err = feasibility_report.diagnostics[0]
        failed_record = SolverJobRecord(
            job_id=f"job_{quarter_key}_{uuid4().hex[:8]}",
            quarter_key=quarter_key,
            status=SolverJobStatus.FAILED,
            completed_at=datetime.now(UTC),
            error=f"Vorprüfung fehlgeschlagen: {first_err.title} — {first_err.message}",
            diagnostics=feasibility_report.diagnostics,
        )
        repo.save_solver_job(failed_record)
        if sync:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=failed_record.error,
            )
        response.status_code = status.HTTP_202_ACCEPTED
        return failed_record

    with _jobs_lock:
        # Prune terminated threads from in-memory tracking
        dead_keys = [k for k, v in _active_jobs.items() if not v.thread.is_alive()]
        for k in dead_keys:
            del _active_jobs[k]

        if quarter_key in _active_jobs:
            existing = _active_jobs[quarter_key]
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Solver job '{existing.job_id}' is already running "
                    f"for quarter '{quarter_key}'."
                ),
            )

        if len(_active_jobs) >= 1:
            running_q = next(iter(_active_jobs.keys()))
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=(
                    f"A solver job is already actively running for quarter '{running_q}'. "
                    "Only 1 concurrent solve is permitted per instance."
                ),
            )

        job_id = f"job_{quarter_key}_{uuid4().hex[:8]}"
        cancellation_event = threading.Event()
        initial_record = SolverJobRecord(
            job_id=job_id,
            quarter_key=quarter_key,
            status=SolverJobStatus.RUNNING,
            max_solve_time_seconds=solver_req.max_solve_time_seconds,
        )
        repo.save_solver_job(initial_record)

        active_job = ActiveJobState(
            job_id=job_id,
            quarter_key=quarter_key,
            thread=threading.Thread(),  # placeholder, set below
            cancellation_event=cancellation_event,
        )
        worker_thread = threading.Thread(
            target=_execute_solver_worker,
            args=(
                quarter_key,
                job_id,
                solver_req.max_solve_time_seconds,
                solver_req.random_seed,
                solver_req.include_previous_context,
                repo,
                cancellation_event,
                active_job,
                solver_req.stagnation_limit_seconds,
            ),
            daemon=True,
        )
        active_job.thread = worker_thread
        _active_jobs[quarter_key] = active_job
        worker_thread.start()

    if sync:
        worker_thread.join(timeout=min(solver_req.max_solve_time_seconds + 30, 880))
        final_record = repo.get_solver_job(quarter_key) or initial_record
        if final_record.status == SolverJobStatus.FAILED:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=final_record.error or "Solver could not find a feasible schedule.",
            )
        response.status_code = status.HTTP_200_OK
        return final_record

    response.status_code = status.HTTP_202_ACCEPTED
    return initial_record


@router.get("/{quarter_key}/solver-status", response_model=SolverJobRecord)
def get_solver_status(
    quarter_key: str,
    repo: RepoDep,
) -> SolverJobRecord:
    """Retrieve live background solver progress and solution metrics."""
    _parse_quarter_key(quarter_key)
    job = repo.get_solver_job(quarter_key)
    if not job:
        return SolverJobRecord(
            job_id="",
            quarter_key=quarter_key,
            status=SolverJobStatus.IDLE,
        )

    if job.status == SolverJobStatus.RUNNING:
        with _jobs_lock:
            active = _active_jobs.get(quarter_key)
            if not active or not active.thread.is_alive():
                job.status = SolverJobStatus.FAILED
                job.error = "Solver-Hintergrundprozess wurde unerwartet beendet."
                job.completed_at = datetime.now(UTC)
                repo.save_solver_job(job)
            else:
                job.elapsed_seconds = round((datetime.now(UTC) - job.started_at).total_seconds(), 1)

    return job


@router.post("/{quarter_key}/cancel")
def cancel_solver_job(
    quarter_key: str,
    repo: RepoDep,
) -> dict[str, str]:
    """Gracefully cancel an active background CP-SAT solve."""
    _parse_quarter_key(quarter_key)
    with _jobs_lock:
        active = _active_jobs.get(quarter_key)
        if not active or not active.thread.is_alive():
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kein aktiver Berechnungsprozess für Quartal '{quarter_key}' gefunden.",
            )
        active.cancellation_event.set()
        if active.solver:
            try:
                active.solver.stop_search()
            except Exception:
                pass

    return {"message": f"Abbruch für Quartal '{quarter_key}' angefordert."}


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
                is_pre_assigned=a.is_pre_assigned,
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
            is_pre_assigned=a.is_pre_assigned,
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
