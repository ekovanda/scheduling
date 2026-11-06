"""Automated roll-over engine for cross-quarter scheduling context.

Replaces manual Excel upload workflows by querying preceding quarter records
from the database, reconstructing realized shifts worked (including swaps and
sick cover), and feeding build_previous_context(...) directly.
"""

from datetime import date

from app.persistence.models import ScheduleState
from app.persistence.repository import RepositoryProtocol
from app.scheduler.models import (
    Assignment,
    PreviousPlanContext,
    Schedule,
    Shift,
    Staff,
    build_previous_context,
)


def compute_preceding_quarter(year: int, quarter: int) -> tuple[int, int]:
    """Compute the (year, quarter) tuple for the quarter immediately preceding."""
    if quarter == 1:
        return year - 1, 4
    return year, quarter - 1


def get_quarter_date_range(year: int, quarter: int) -> tuple[date, date]:
    """Return the (start_date, end_date) for a given quarter."""
    start_month = (quarter - 1) * 3 + 1
    start_date = date(year, start_month, 1)

    if quarter == 1:
        end_date = date(year, 3, 31)
    elif quarter == 2:
        end_date = date(year, 6, 30)
    elif quarter == 3:
        end_date = date(year, 9, 30)
    else:
        end_date = date(year, 12, 31)

    return start_date, end_date


def get_previous_quarter_context(
    target_year: int,
    target_quarter: int,
    repo: RepositoryProtocol,
    trailing_days: int = 21,
) -> PreviousPlanContext | None:
    """Auto-compute PreviousPlanContext from the preceding quarter document in the database.

    Uses `actual_staff_id` (the realized shift assignments) to ensure any sick leave
    replacements or manual swaps that occurred late in the preceding quarter are
    accurately captured as boundary rest-period constraints in the target quarter.
    """
    prev_year, prev_quarter = compute_preceding_quarter(target_year, target_quarter)
    prev_key = f"{prev_year}-Q{prev_quarter}"
    prev_doc = repo.get_schedule(prev_key)

    if (
        not prev_doc
        or prev_doc.state
        not in (ScheduleState.ACTIVE, ScheduleState.CLOSED, ScheduleState.PUBLISHED)
        or not prev_doc.assignments
    ):
        return None

    prev_start, prev_end = get_quarter_date_range(prev_year, prev_quarter)

    # Reconstruct realized schedule using actual_staff_id
    realized_assignments: list[Assignment] = [
        Assignment(
            shift=Shift(shift_type=a.shift_type, shift_date=a.shift_date),
            staff_identifier=a.actual_staff_id,
            is_paired=a.is_paired,
        )
        for a in prev_doc.assignments
    ]

    realized_schedule = Schedule(
        quarter_start=prev_start,
        quarter_end=prev_end,
        assignments=realized_assignments,
    )

    active_members = repo.list_staff(active_only=True)
    if not active_members:
        return None

    active_staff: list[Staff] = [m.to_scheduler_staff() for m in active_members]

    return build_previous_context(
        schedule=realized_schedule,
        staff_list=active_staff,
        trailing_days=trailing_days,
    )
