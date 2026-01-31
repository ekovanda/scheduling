"""Tests for scheduler functionality."""

from datetime import date

import pytest

from app.scheduler.models import Beruf, Staff, ShiftType, generate_quarter_shifts
from app.scheduler.solver import SolverBackend, generate_schedule
from app.scheduler.validator import validate_schedule


def test_effective_nights_calculation() -> None:
    """Test that paired nights count as 0.5 per person for non-Azubis, 1.0 for Azubis."""
    tfa_staff = Staff(
        name="Test Person",
        identifier="TP",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        reception=True,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=2,
        nd_exceptions=[],
    )

    # Non-Azubi: paired night weight is 0.5
    assert tfa_staff.effective_nights_weight(is_paired=True) == 0.5
    # Non-Azubi: solo night weight is 1.0
    assert tfa_staff.effective_nights_weight(is_paired=False) == 1.0

    azubi_staff = Staff(
        name="Test Azubi",
        identifier="TA",
        adult=True,
        hours=40,
        beruf=Beruf.AZUBI,
        reception=True,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=2,
        nd_exceptions=[],
    )

    # Azubi: always 1.0 even when paired
    assert azubi_staff.effective_nights_weight(is_paired=True) == 1.0
    assert azubi_staff.effective_nights_weight(is_paired=False) == 1.0


def test_minor_cannot_work_sunday() -> None:
    """Test that minors cannot be assigned Sunday shifts."""
    minor = Staff(
        name="Minor Test",
        identifier="MT",
        adult=False,
        hours=40,
        beruf=Beruf.AZUBI,
        reception=False,
        nd_possible=False,
        nd_alone=False,
        nd_max_consecutive=None,
        nd_exceptions=[],
    )

    from app.scheduler.models import ShiftType

    # Minor cannot work any Sunday shift
    assert not minor.can_work_shift(ShiftType.SUNDAY_8_20, date(2026, 4, 6))
    assert not minor.can_work_shift(ShiftType.SUNDAY_10_22, date(2026, 4, 6))
    assert not minor.can_work_shift(ShiftType.SUNDAY_8_2030, date(2026, 4, 6))

    # But can work Saturday (any Azubi can work Sa_10-19 now)
    assert minor.can_work_shift(ShiftType.SATURDAY_10_19, date(2026, 4, 5))


def test_intern_cannot_work_weekend() -> None:
    """Test that Interns cannot be assigned weekend shifts."""
    intern = Staff(
        name="Intern Test",
        identifier="INT",
        adult=True,
        hours=40,
        beruf=Beruf.INTERN,
        reception=True,
        nd_possible=True,
        nd_alone=True,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )

    from app.scheduler.models import ShiftType

    # Intern cannot work weekend shifts
    assert not intern.can_work_shift(ShiftType.SATURDAY_10_21, date(2026, 4, 5))
    assert not intern.can_work_shift(ShiftType.SUNDAY_8_20, date(2026, 4, 6))

    # But can work night shifts
    assert intern.can_work_shift(ShiftType.NIGHT_SUN_MON, date(2026, 4, 6))


def test_weekend_shift_eligibility() -> None:
    """Test weekend shift eligibility rules for each role."""
    from app.scheduler.models import ShiftType, Beruf

    # TFA staff
    tfa = Staff(
        name="TFA Test",
        identifier="TFA",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        reception=True,
        nd_possible=True,
        nd_alone=True,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )

    # Adult Azubi with reception
    azubi_reception = Staff(
        name="Azubi Reception",
        identifier="AZR",
        adult=True,
        hours=40,
        beruf=Beruf.AZUBI,
        reception=True,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=2,
        nd_exceptions=[],
    )

    # Adult Azubi without reception
    azubi_no_reception = Staff(
        name="Azubi No Reception",
        identifier="AZN",
        adult=True,
        hours=40,
        beruf=Beruf.AZUBI,
        reception=False,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=2,
        nd_exceptions=[],
    )

    # Saturday 10-19: Azubis only
    assert not tfa.can_work_shift(ShiftType.SATURDAY_10_19, date(2026, 4, 5))
    assert azubi_reception.can_work_shift(ShiftType.SATURDAY_10_19, date(2026, 4, 5))
    assert azubi_no_reception.can_work_shift(ShiftType.SATURDAY_10_19, date(2026, 4, 5))

    # Saturday 10-21: TFA or Azubi with reception
    assert tfa.can_work_shift(ShiftType.SATURDAY_10_21, date(2026, 4, 5))
    assert azubi_reception.can_work_shift(ShiftType.SATURDAY_10_21, date(2026, 4, 5))
    assert not azubi_no_reception.can_work_shift(ShiftType.SATURDAY_10_21, date(2026, 4, 5))

    # Saturday 10-22: TFA only
    assert tfa.can_work_shift(ShiftType.SATURDAY_10_22, date(2026, 4, 5))
    assert not azubi_reception.can_work_shift(ShiftType.SATURDAY_10_22, date(2026, 4, 5))

    # Sunday 8-20: TFA only
    assert tfa.can_work_shift(ShiftType.SUNDAY_8_20, date(2026, 4, 6))
    assert not azubi_reception.can_work_shift(ShiftType.SUNDAY_8_20, date(2026, 4, 6))

    # Sunday 8-20:30: Adult Azubis only
    assert not tfa.can_work_shift(ShiftType.SUNDAY_8_2030, date(2026, 4, 6))
    assert azubi_reception.can_work_shift(ShiftType.SUNDAY_8_2030, date(2026, 4, 6))
    assert azubi_no_reception.can_work_shift(ShiftType.SUNDAY_8_2030, date(2026, 4, 6))

    # Sunday 10-22: TFA only
    assert tfa.can_work_shift(ShiftType.SUNDAY_10_22, date(2026, 4, 6))
    assert not azubi_reception.can_work_shift(ShiftType.SUNDAY_10_22, date(2026, 4, 6))


def test_generate_quarter_shifts() -> None:
    """Test that quarter shift generation creates correct number of shifts."""
    quarter_start = date(2026, 4, 1)  # Q2/2026
    shifts = generate_quarter_shifts(quarter_start)

    # Q2 has 91 days (April=30, May=31, June=30)
    # Each day: 1 night shift
    # Each Saturday (13): 3 shifts
    # Each Sunday (13): 3 shifts
    # Total: 91 nights + 13*3 Sat + 13*3 Sun = 91 + 39 + 39 = 169

    # Count shift types
    night_shifts = [s for s in shifts if s.is_night_shift()]
    saturday_shifts = [s for s in shifts if s.shift_type.value.startswith("Sa_")]
    sunday_shifts = [s for s in shifts if s.shift_type.value.startswith("So_")]

    assert len(night_shifts) == 91
    assert len(saturday_shifts) == 39  # 13 weeks * 3 shifts
    assert len(sunday_shifts) == 39  # 13 weeks * 3 shifts
    assert len(shifts) == 169


def test_three_week_block_constraint() -> None:
    """Test that 3-week block constraint is enforced."""
    # Create minimal staff list
    staff_list = [
        Staff(
            name="Test TFA",
            identifier="TFA1",
            adult=True,
            hours=40,
            beruf=Beruf.TFA,
            reception=True,
            nd_possible=True,
            nd_alone=True,
            nd_max_consecutive=2,
            nd_exceptions=[],
        ),
        Staff(
            name="Test Azubi",
            identifier="AZ1",
            adult=True,
            hours=40,
            beruf=Beruf.AZUBI,
            reception=False,
            nd_possible=True,
            nd_alone=False,
            nd_max_consecutive=2,
            nd_exceptions=[],
        ),
    ]

    # Generate schedule for a short period
    quarter_start = date(2026, 4, 1)
    result = generate_schedule(staff_list, quarter_start, max_iterations=500, random_seed=42)

    if result.success:
        schedule = result.get_best_schedule()
        validation = validate_schedule(schedule, staff_list)

        # Check for 3-week block violations
        block_violations = [
            v for v in validation.hard_violations if v.constraint_name == "3-Week Block Limit"
        ]

        # Should have no violations (or schedule generation should handle this)
        assert len(block_violations) == 0, f"Found {len(block_violations)} 3-week block violations"


def test_nd_max_consecutive_constraint() -> None:
    """Test that nd_max_consecutive is respected for consecutive nights."""
    from app.scheduler.models import Assignment, Schedule, Shift, ShiftType

    staff = Staff(
        name="Test TFA",
        identifier="TFA1",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        reception=True,
        nd_possible=True,
        nd_alone=True,
        nd_max_consecutive=2,  # Can only work max 2 consecutive nights
        nd_exceptions=[],
    )

    # Create schedule with 3 consecutive nights (should violate)
    schedule = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 3),
        assignments=[
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_TUE_WED, shift_date=date(2026, 4, 1)),
                staff_identifier="TFA1",
            ),
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_WED_THU, shift_date=date(2026, 4, 2)),
                staff_identifier="TFA1",
            ),
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_THU_FRI, shift_date=date(2026, 4, 3)),
                staff_identifier="TFA1",
            ),
        ],
    )

    validation = validate_schedule(schedule, [staff])

    # nd_max_consecutive is now a soft constraint, so check score instead of hard violations
    assert validation.soft_penalty > 0, "Should have penalty for nd_max_consecutive violation"
#     
#     # Original hard check (commented out)
#     # nd_count_violations = [
#     #     v for v in validation.hard_violations if v.constraint_name == "ND Count Constraint"
#     # ]
#     # assert len(nd_count_violations) > 0, "Should detect 3 consecutive nights violation"

def test_paired_night_requirement() -> None:
    """Test that Azubis must be paired with non-Azubi."""
    from app.scheduler.models import Assignment, Schedule, Shift, ShiftType

    staff_needs_pair = Staff(
        name="Needs Pair",
        identifier="NP1",
        adult=True,
        hours=40,
        beruf=Beruf.AZUBI,
        reception=False,
        nd_possible=True,
        nd_alone=False,  # Must be paired
        nd_max_consecutive=2,
        nd_exceptions=[],
    )

    # Create schedule with unpaired night shift (not Sun-Mon or Mon-Tue)
    schedule = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 1),
        assignments=[
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_TUE_WED, shift_date=date(2026, 4, 1)),
                staff_identifier="NP1",
                is_paired=False,  # Should violate
            )
        ],
    )

    validation = validate_schedule(schedule, [staff_needs_pair])

    # Should have pairing violation (Azubi alone without TFA/Intern)
    pairing_violations = [
        v
        for v in validation.hard_violations
        if v.constraint_name in ["Night Pairing Required", "Azubi Night Pairing"]
    ]
    assert len(pairing_violations) > 0, "Should detect unpaired night violation"


def test_nd_alone_can_work_intern_nights_and_regular_nights() -> None:
    """Test that staff with nd_alone=True can work all nights but must work alone on regular nights."""
    solo_worker = Staff(
        name="Solo Worker",
        identifier="SW1",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        reception=True,
        nd_possible=True,
        nd_alone=True,  # Must work alone on regular nights
        nd_max_consecutive=2,
        nd_exceptions=[],
    )

    # CAN work Sun-Mon and Mon-Tue (intern on-site, can work solo)
    assert solo_worker.can_work_shift(ShiftType.NIGHT_SUN_MON, date(2026, 4, 5))
    assert solo_worker.can_work_shift(ShiftType.NIGHT_MON_TUE, date(2026, 4, 6))
    # Can work other nights (but must be alone, not paired)
    assert solo_worker.can_work_shift(ShiftType.NIGHT_TUE_WED, date(2026, 4, 7))
    assert solo_worker.can_work_shift(ShiftType.NIGHT_FRI_SAT, date(2026, 4, 10))


def test_weekend_isolation_constraint() -> None:
    """Test that weekend shifts cannot be adjacent to other shifts."""
    from app.scheduler.models import Assignment, Schedule, Shift, ShiftType

    staff = Staff(
        name="Test TFA",
        identifier="TFA1",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        reception=True,
        nd_possible=True,
        nd_alone=True,
        nd_max_consecutive=2,
        nd_exceptions=[],
    )

    # Create schedule with weekend shift adjacent to night shift (should violate)
    # Friday night + Saturday weekend shift = violation
    schedule = Schedule(
        quarter_start=date(2026, 4, 3),
        quarter_end=date(2026, 4, 4),
        assignments=[
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_FRI_SAT, shift_date=date(2026, 4, 3)),
                staff_identifier="TFA1",
            ),
            Assignment(
                shift=Shift(shift_type=ShiftType.SATURDAY_10_21, shift_date=date(2026, 4, 4)),
                staff_identifier="TFA1",
            ),
        ],
    )

    validation = validate_schedule(schedule, [staff])

    # Check for weekend isolation violations
    isolation_violations = [
        v for v in validation.hard_violations if v.constraint_name == "Weekend Isolation"
    ]
    assert len(isolation_violations) > 0, "Should detect weekend isolation violation"


def test_cpsat_solver_produces_valid_schedule() -> None:
    """Test that CP-SAT solver produces a valid schedule with good fairness."""
    from pathlib import Path
    from app.scheduler.models import load_staff_from_csv

    staff = load_staff_from_csv(Path("data/staff_sample.csv"))

    result = generate_schedule(
        staff,
        date(2026, 4, 1),
        max_iterations=1200,  # 60 seconds
        random_seed=42,
        backend=SolverBackend.CPSAT,
    )

    assert result.success, f"CP-SAT solver failed: {result.unsatisfiable_constraints}"

    schedule = result.get_best_schedule()
    assert schedule is not None
    assert len(schedule.assignments) > 0

    # Validate the schedule
    validation = validate_schedule(schedule, staff)
    assert validation.is_valid(), f"Schedule has violations: {[str(v) for v in validation.hard_violations[:5]]}"


def test_cpsat_fairness_within_tolerance() -> None:
    """Test that CP-SAT solver produces fair schedules within FTE tolerance."""
    from collections import defaultdict
    from pathlib import Path
    from app.scheduler.models import load_staff_from_csv

    staff = load_staff_from_csv(Path("data/staff_sample.csv"))
    staff_dict = {s.identifier: s for s in staff}

    result = generate_schedule(
        staff,
        date(2026, 4, 1),
        max_iterations=2400,  # 120 seconds
        random_seed=42,
        backend=SolverBackend.CPSAT,
    )

    assert result.success

    schedule = result.get_best_schedule()

    # Calculate night FTE for each staff
    stats = defaultdict(lambda: 0.0)
    for a in schedule.assignments:
        if a.shift.is_night_shift():
            stats[a.staff_identifier] += 0.5 if a.is_paired else 1.0

    # Check Azubi fairness (all should have similar FTE)
    azubi_nd_eligible = [s for s in staff if s.beruf == Beruf.AZUBI and s.nd_possible]
    if len(azubi_nd_eligible) >= 2:
        azubi_ftes = [stats[s.identifier] / s.hours * 40 for s in azubi_nd_eligible]
        azubi_range = max(azubi_ftes) - min(azubi_ftes)
        # Azubis should be reasonably balanced (range < 3.0)
        # Note: Stricter pairing constraints (nd_alone=True must work alone, 
        # single-capacity Sun-Mon/Mon-Tue) limit solution space significantly
        assert azubi_range < 3.0, f"Azubi FTE range too wide: {azubi_range:.2f}"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
