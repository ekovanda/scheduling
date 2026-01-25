"""Tests for scheduler functionality."""

from datetime import date

import pytest

from app.scheduler.models import Beruf, Staff, generate_quarter_shifts
from app.scheduler.solver import generate_schedule
from app.scheduler.validator import validate_schedule


def test_effective_nights_calculation() -> None:
    """Test that paired nights count as 0.5 per person."""
    staff = Staff(
        name="Test Person",
        identifier="TP",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        reception=True,
        nd_possible=True,
        nd_alone=False,
        nd_count=[1, 2],
        nd_exceptions=[],
    )

    # Test paired night weight
    assert staff.effective_nights_weight(is_paired=True) == 0.5

    # Test solo night weight
    assert staff.effective_nights_weight(is_paired=False) == 1.0


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
        nd_count=[],
        nd_exceptions=[],
    )

    from app.scheduler.models import ShiftType

    # Minor cannot work any Sunday shift
    assert not minor.can_work_shift(ShiftType.SUNDAY_8_20, date(2026, 4, 6))
    assert not minor.can_work_shift(ShiftType.SUNDAY_10_22, date(2026, 4, 6))
    assert not minor.can_work_shift(ShiftType.SUNDAY_8_2030, date(2026, 4, 6))

    # But can work Saturday
    assert minor.can_work_shift(ShiftType.SATURDAY_10_19, date(2026, 4, 5))


def test_ta_cannot_work_weekend() -> None:
    """Test that TAs cannot be assigned weekend shifts."""
    ta = Staff(
        name="TA Test",
        identifier="TAT",
        adult=True,
        hours=40,
        beruf=Beruf.TA,
        reception=True,
        nd_possible=True,
        nd_alone=True,
        nd_count=[1],
        nd_exceptions=[],
    )

    from app.scheduler.models import ShiftType

    # TA cannot work weekend shifts
    assert not ta.can_work_shift(ShiftType.SATURDAY_10_21, date(2026, 4, 5))
    assert not ta.can_work_shift(ShiftType.SUNDAY_8_20, date(2026, 4, 6))

    # But can work night shifts
    assert ta.can_work_shift(ShiftType.NIGHT_SUN_MON, date(2026, 4, 6))


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
            nd_count=[1, 2],
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
            nd_count=[1],
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


def test_nd_count_constraint() -> None:
    """Test that nd_count is respected for consecutive nights."""
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
        nd_count=[1, 2],  # Can only work 1 or 2 consecutive nights
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

    # Should have nd_count violation (3 consecutive not in [1,2])
    nd_count_violations = [
        v for v in validation.hard_violations if v.constraint_name == "ND Count Constraint"
    ]
    assert len(nd_count_violations) > 0, "Should detect 3 consecutive nights violation"


def test_paired_night_requirement() -> None:
    """Test that staff with nd_alone=False must be paired."""
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
        nd_count=[1],
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

    # Should have pairing violation
    pairing_violations = [
        v
        for v in validation.hard_violations
        if v.constraint_name in ["Night Pairing Required", "Azubi Night Pairing"]
    ]
    assert len(pairing_violations) > 0, "Should detect unpaired night violation"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
