"""Unit tests for the automated cross-quarter roll-over engine."""

from datetime import date
from pathlib import Path

from app.persistence.models import (
    QuarterScheduleDocument,
    ScheduleState,
    ShiftAssignmentRecord,
    StaffMember,
)
from app.persistence.repository import FileJsonRepository
from app.persistence.rollover import (
    compute_preceding_quarter,
    get_previous_quarter_context,
    get_quarter_date_range,
)
from app.scheduler.models import Beruf, ShiftType


def test_quarter_math() -> None:
    """Verify quarter boundary and preceding quarter computations."""
    assert compute_preceding_quarter(2026, 2) == (2026, 1)
    assert compute_preceding_quarter(2026, 1) == (2025, 4)

    start_q1, end_q1 = get_quarter_date_range(2026, 1)
    assert start_q1 == date(2026, 1, 1)
    assert end_q1 == date(2026, 3, 31)

    start_q2, end_q2 = get_quarter_date_range(2026, 2)
    assert start_q2 == date(2026, 4, 1)
    assert end_q2 == date(2026, 6, 30)


def test_rollover_no_prior_quarter(tmp_path: Path) -> None:
    """When no preceding quarter exists, get_previous_quarter_context returns None."""
    repo = FileJsonRepository(base_dir=tmp_path / "db")
    ctx = get_previous_quarter_context(2026, 2, repo)
    assert ctx is None


def test_rollover_uses_realized_swap_assignments(tmp_path: Path) -> None:
    """Verify roll-over reads actual_staff_id, reflecting realized shift swaps."""
    repo = FileJsonRepository(base_dir=tmp_path / "db")

    # Onboard active staff
    m1 = StaffMember(id="STAFF_01", identifier="MUE", name="Müller", hours=40, beruf=Beruf.TFA)
    m2 = StaffMember(id="STAFF_02", identifier="SCH", name="Schmidt", hours=40, beruf=Beruf.TFA)
    repo.save_staff(m1)
    repo.save_staff(m2)

    # Save Q1 schedule with an override swap on March 30
    q1_doc = QuarterScheduleDocument(
        quarter_key="2026-Q1",
        year=2026,
        quarter=1,
        state=ScheduleState.CLOSED,
        assignments=[
            ShiftAssignmentRecord(
                shift_date=date(2026, 3, 30),
                shift_type=ShiftType.NIGHT_MON_TUE,
                planned_staff_id="MUE",
                actual_staff_id="SCH",  # Realized swap: SCH covered the shift!
                is_paired=False,
                is_override=True,
                override_reason="Krankheitsvertretung",
            )
        ],
    )
    repo.save_schedule(q1_doc)

    # Compute roll-over for Q2 (starts April 1)
    ctx = get_previous_quarter_context(2026, 2, repo, trailing_days=21)
    assert ctx is not None
    assert len(ctx.trailing_assignments) == 1

    trailing = ctx.trailing_assignments[0]
    # The trailing assignment must reflect SCH (the actual person who worked), NOT MUE!
    assert trailing.staff_identifier == "SCH"
    assert trailing.shift_date == date(2026, 3, 30)
