"""Unit and integration regression tests for review findings B1, B3, B5, and B7.

Covers:
- B1: Exact calendar quarter horizons (2026-2028, 30 Sep, 31 Dec, leap year Feb 29).
- B3: Uncovered shifts explicitly enforced in solver and caught in validator.
- B5: Solver success strictly gated on post-solve validation.
- B7: Pre-assigned shift type/staff validation, persistence, and 7-day holiday relaxation.
"""

from datetime import date, timedelta
from typing import Any
from unittest.mock import patch

from fastapi.testclient import TestClient

from app.api.v1.quarters import _execute_solver_worker
from app.persistence.models import (
    SolverJobRecord,
    SolverJobStatus,
    StaffMember,
)
from app.persistence.repository import FileJsonRepository
from app.persistence.rollover import get_quarter_date_range
from app.scheduler.models import (
    Assignment,
    Beruf,
    Schedule,
    SchedulerConfig,
    Shift,
    ShiftType,
    Staff,
    Vacation,
    generate_quarter_shifts,
)
from app.scheduler.solver_cpsat import SolverResult, generate_schedule_cpsat
from app.scheduler.validator import ConstraintViolation, ValidationResult, validate_schedule

# =============================================================================
# B1: Exact Calendar Quarter Horizon Tests
# =============================================================================


def test_b1_calendar_quarter_horizons_2026_to_2028() -> None:
    """Verify generate_quarter_shifts covers every calendar date in each quarter."""
    for year in (2026, 2027, 2028):
        for quarter in (1, 2, 3, 4):
            q_start, q_end = get_quarter_date_range(year, quarter)
            shifts = generate_quarter_shifts(q_start, quarter_end=q_end)

            night_dates = {s.shift_date for s in shifts if s.is_night_shift()}
            expected_dates = {
                q_start + timedelta(days=i) for i in range((q_end - q_start).days + 1)
            }

            assert night_dates == expected_dates, (
                f"Night shift dates for {year}-Q{quarter} do not match calendar dates. "
                f"Missing: {expected_dates - night_dates}, Extra: {night_dates - expected_dates}"
            )


def test_b1_specific_quarter_edge_dates() -> None:
    """Verify specific dates identified in finding B1."""
    # 2026-Q3: Sep 30 must have a night shift
    q3_shifts = generate_quarter_shifts(date(2026, 7, 1))
    q3_night_dates = {s.shift_date for s in q3_shifts if s.is_night_shift()}
    assert date(2026, 9, 30) in q3_night_dates
    assert len(q3_night_dates) == 92

    # 2026-Q4: Dec 31 (New Year's Eve) must have a night shift
    q4_shifts = generate_quarter_shifts(date(2026, 10, 1))
    q4_night_dates = {s.shift_date for s in q4_shifts if s.is_night_shift()}
    assert date(2026, 12, 31) in q4_night_dates
    assert len(q4_night_dates) == 92

    # 2027-Q1: Ends on March 31, April 1 is not generated
    q1_shifts = generate_quarter_shifts(date(2027, 1, 1))
    q1_night_dates = {s.shift_date for s in q1_shifts if s.is_night_shift()}
    assert date(2027, 3, 31) in q1_night_dates
    assert date(2027, 4, 1) not in q1_night_dates
    assert len(q1_night_dates) == 90

    # 2028-Q1 (Leap year): Includes Feb 29, 91 nights total
    q1_leap_shifts = generate_quarter_shifts(date(2028, 1, 1))
    q1_leap_dates = {s.shift_date for s in q1_leap_shifts if s.is_night_shift()}
    assert date(2028, 2, 29) in q1_leap_dates
    assert len(q1_leap_dates) == 91


# =============================================================================
# B3: Uncovered Shifts Enforcement & Validation Tests
# =============================================================================


def _create_minimal_tfa(identifier: str = "TFA1", name: str = "Test TFA") -> Staff:
    return Staff(
        name=name,
        identifier=identifier,
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        reception=True,
        nd_possible=True,
        nd_alone=True,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )


def _create_minimal_azubi(identifier: str = "AZ1", name: str = "Test Azubi") -> Staff:
    return Staff(
        name=name,
        identifier=identifier,
        adult=True,
        hours=40,
        beruf=Beruf.AZUBI,
        reception=False,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=2,
        nd_exceptions=[],
    )


def test_b3_solver_fails_when_weekend_shift_has_no_eligible_staff() -> None:
    """If no staff is eligible for a required regular weekend shift, solver must fail."""
    tfa = _create_minimal_tfa("T1")
    q_start = date(2026, 4, 1)
    # Vacate the entire quarter for Saturday shifts
    vacations = [Vacation(identifier="T1", start_date=date(2026, 4, 1), end_date=date(2026, 6, 30))]

    result = generate_schedule_cpsat(
        staff_list=[tfa],
        quarter_start=q_start,
        vacations=vacations,
        max_solve_time_seconds=2,
    )
    assert not result.success


def test_b3_validator_detects_missing_shift_coverage() -> None:
    """Validator must flag a schedule where an expected night or weekend shift is missing."""
    q_start = date(2026, 4, 1)
    q_end = date(2026, 4, 10)

    # Generate expected shifts for this window
    expected = generate_quarter_shifts(q_start, quarter_end=q_end)

    # Populate assignments for all shifts except the first night shift (2026-04-01)
    tfa = _create_minimal_tfa("T1")
    assignments = []
    for s in expected:
        if s.is_night_shift() and s.shift_date == date(2026, 4, 1):
            continue  # Drop this assignment
        assignments.append(
            Assignment(
                shift=s,
                staff_identifier="T1",
                is_paired=False,
            )
        )

    sched = Schedule(quarter_start=q_start, quarter_end=q_end, assignments=assignments)
    res = validate_schedule(sched, [tfa])

    coverage_violations = [v for v in res.hard_violations if v.constraint_name == "Shift Coverage"]
    assert len(coverage_violations) >= 1
    assert any("01.04.2026" in v.description for v in coverage_violations)


def test_b3_validator_flags_azubi_alone_on_closed_night() -> None:
    """Validator must flag closed nights staffed exclusively by Azubis."""
    q_start = date(2026, 4, 1)
    q_end = date(2026, 4, 3)  # Wed-Thu and Thu-Fri are closed nights

    azubi = _create_minimal_azubi("AZ1")
    # Night on 2026-04-01 is Wed->Thu (closed night)
    night_shift = Shift(shift_type=ShiftType.NIGHT_WED_THU, shift_date=date(2026, 4, 1))

    sched = Schedule(
        quarter_start=q_start,
        quarter_end=q_end,
        assignments=[
            Assignment(shift=night_shift, staff_identifier="AZ1", is_paired=False),
        ],
    )
    res = validate_schedule(sched, [azubi])
    assert not res.is_valid()
    assert any(
        "no non-Azubi staff" in v.description or "Azubi" in v.constraint_name
        for v in res.hard_violations
    )


# =============================================================================
# B5: Solver Success Gated on Validator Tests
# =============================================================================


def test_b5_solver_result_fails_when_validator_emits_hard_violations() -> None:
    """If post-solve validation fails, solver must return success=False and record violations."""
    fake_violation = ConstraintViolation("SyntheticRule", "Simulated constraint failure")
    dummy_schedule = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 6, 30),
        assignments=[],
    )

    from ortools.sat.python import cp_model

    with (
        patch("ortools.sat.python.cp_model.CpSolver.Solve", return_value=cp_model.OPTIMAL),
        patch("app.scheduler.solver_cpsat._extract_schedule", return_value=dummy_schedule),
        patch(
            "app.scheduler.solver_cpsat.validate_schedule",
            return_value=ValidationResult(hard_violations=[fake_violation], soft_penalty=100.0),
        ),
    ):
        result = generate_schedule_cpsat(
            staff_list=[_create_minimal_tfa("T1")],
            quarter_start=date(2026, 4, 1),
            vacations=[],
            max_solve_time_seconds=5,
        )

        assert not result.success
        assert len(result.hard_violations) == 1
        assert "SyntheticRule: Simulated constraint failure" in result.unsatisfiable_constraints[0]


def test_b5_solver_worker_fails_job_on_validator_violations(tmp_path: Any) -> None:
    """_execute_solver_worker must mark job FAILED if solver returns hard violations."""
    import threading

    from app.api.v1.quarters import ActiveJobState

    repo = FileJsonRepository(base_dir=tmp_path / "b5_repo")
    staff = StaffMember(
        id="S1",
        identifier="T1",
        name="TFA 1",
        beruf=Beruf.TFA,
        hours=40,
        nd_possible=True,
    )
    repo.save_staff(staff)

    job_rec = SolverJobRecord(
        job_id="job_b5", quarter_key="2026-Q2", status=SolverJobStatus.RUNNING
    )
    repo.save_solver_job(job_rec)

    fake_result = SolverResult(
        success=False,
        schedules=[],
        penalties=[],
        unsatisfiable_constraints=["Post-solve validation failed: Test violation"],
        hard_violations=["Test violation"],
    )

    cancel_event = threading.Event()
    active_job = ActiveJobState(
        job_id="job_b5",
        quarter_key="2026-Q2",
        thread=threading.current_thread(),
        cancellation_event=cancel_event,
    )

    with patch("app.api.v1.quarters.generate_schedule", return_value=fake_result):
        _execute_solver_worker(
            quarter_key="2026-Q2",
            job_id="job_b5",
            max_solve_time_seconds=5,
            random_seed=42,
            include_previous_context=False,
            repo=repo,
            cancellation_event=cancel_event,
            active_job=active_job,
        )

    saved_job = repo.get_solver_job("2026-Q2")
    assert saved_job is not None
    assert saved_job.status == SolverJobStatus.FAILED
    assert "Test violation" in (saved_job.error or "")

    # Ensure no schedule document was persisted
    doc = repo.get_schedule("2026-Q2")
    assert doc is None


# =============================================================================
# B7: Pre-Assigned Shift Validation, Persistence & Gap Relaxation Tests
# =============================================================================


def test_b7_create_preassigned_validates_staff_and_shift_type(client: TestClient) -> None:
    """POST /preassigned must return 422 if staff does not exist or shift_type is invalid."""
    # 1. Unknown staff_id with valid shift_type -> 422 (staff existence failure)
    resp_unknown_staff = client.post(
        "/api/v1/preassigned",
        json={
            "id": "pa_01",
            "staff_id": "NON_EXISTENT_STAFF",
            "staff_identifier": "NON",
            "shift_date": "2026-05-01",
            "shift_type": "So_8-20",
        },
    )
    assert resp_unknown_staff.status_code == 422
    assert "does not exist" in resp_unknown_staff.text

    # 2. Create valid staff member first
    client.post(
        "/api/v1/staff",
        json={
            "id": "STAFF_PA",
            "identifier": "SPA",
            "name": "Staff Preassigned",
            "beruf": "TFA",
            "hours": 40,
            "nd_possible": True,
        },
    )

    # 3. Invalid shift_type -> 422 (Pydantic validation)
    resp_bad_type = client.post(
        "/api/v1/preassigned",
        json={
            "id": "pa_02",
            "staff_id": "STAFF_PA",
            "staff_identifier": "SPA",
            "shift_date": "2026-05-01",
            "shift_type": "CompletelyInvalidShiftType",
        },
    )
    assert resp_bad_type.status_code == 422

    # 4. Valid shift_type -> 201
    resp_valid = client.post(
        "/api/v1/preassigned",
        json={
            "id": "pa_03",
            "staff_id": "STAFF_PA",
            "staff_identifier": "SPA",
            "shift_date": "2026-05-01",
            "shift_type": "So_8-20",
        },
    )
    assert resp_valid.status_code == 201


def test_b7_validator_holiday_gap_relaxation() -> None:
    """Pre-assigned holiday duties must relax the 3-week block limit from 21 days to 7 days."""
    tfa = _create_minimal_tfa("T1")
    config = SchedulerConfig(block_gap_days=21, holiday_gap_days=7)

    # Block 1: April 1-2
    # Block 2: April 10-11 (gap = 9 days, less than 21 days)
    block1 = [
        Assignment(
            shift=Shift(shift_type=ShiftType.NIGHT_WED_THU, shift_date=date(2026, 4, 1)),
            staff_identifier="T1",
            is_pre_assigned=False,
        ),
        Assignment(
            shift=Shift(shift_type=ShiftType.NIGHT_THU_FRI, shift_date=date(2026, 4, 2)),
            staff_identifier="T1",
            is_pre_assigned=False,
        ),
    ]
    block2 = [
        Assignment(
            shift=Shift(shift_type=ShiftType.NIGHT_FRI_SAT, shift_date=date(2026, 4, 10)),
            staff_identifier="T1",
            is_pre_assigned=False,
        ),
        Assignment(
            shift=Shift(shift_type=ShiftType.NIGHT_SAT_SUN, shift_date=date(2026, 4, 11)),
            staff_identifier="T1",
            is_pre_assigned=False,
        ),
    ]

    # Without holiday flag: 9 days gap violates 21-day rule
    sched_unrelaxed = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=block1 + block2,
    )
    res_unrelaxed = validate_schedule(sched_unrelaxed, [tfa], config=config)
    block_violations = [
        v for v in res_unrelaxed.hard_violations if "Block Limit" in v.constraint_name
    ]
    assert len(block_violations) >= 1

    # With pre-assigned holiday duty in Block 1: gap requirement is relaxed to 7 days (9 >= 7 -> Valid!)
    block1_holiday = [
        Assignment(
            shift=Shift(shift_type=ShiftType.NIGHT_WED_THU, shift_date=date(2026, 4, 1)),
            staff_identifier="T1",
            is_pre_assigned=True,
        ),
        Assignment(
            shift=Shift(shift_type=ShiftType.NIGHT_THU_FRI, shift_date=date(2026, 4, 2)),
            staff_identifier="T1",
            is_pre_assigned=True,
        ),
    ]
    sched_relaxed = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=block1_holiday + block2,
    )
    res_relaxed = validate_schedule(sched_relaxed, [tfa], config=config)
    block_violations_relaxed = [
        v for v in res_relaxed.hard_violations if "Block Limit" in v.constraint_name
    ]
    assert len(block_violations_relaxed) == 0, (
        f"Expected 7-day relaxation for holiday block, got violations: "
        f"{[v.description for v in block_violations_relaxed]}"
    )
