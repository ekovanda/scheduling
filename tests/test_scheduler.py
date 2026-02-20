"""Tests for scheduler functionality."""

from datetime import date

import pytest

from app.scheduler.models import Abteilung, Beruf, Staff, ShiftType, generate_quarter_shifts
from app.scheduler.solver import generate_schedule
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
    """Test that 3-week (21-day) block constraint is enforced."""
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
    result = generate_schedule(staff_list, quarter_start, max_solve_time_seconds=60, random_seed=42)

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
        max_solve_time_seconds=60,
        random_seed=42,
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
        max_solve_time_seconds=120,
        random_seed=42,
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


def test_abteilung_same_night_constraint() -> None:
    """Test that staff from same abteilung (op/station) cannot work same night."""
    from app.scheduler.models import Assignment, Schedule, Shift, ShiftType

    # Two OP staff on the same night
    staff_op1 = Staff(
        name="OP Staff 1",
        identifier="OP1",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        abteilung=Abteilung.OP,
        reception=True,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )
    staff_op2 = Staff(
        name="OP Staff 2",
        identifier="OP2",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        abteilung=Abteilung.OP,
        reception=True,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )

    # Schedule with both OP staff on same night (should violate)
    schedule = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 1),
        assignments=[
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_TUE_WED, shift_date=date(2026, 4, 1)),
                staff_identifier="OP1",
                is_paired=True,
            ),
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_TUE_WED, shift_date=date(2026, 4, 1)),
                staff_identifier="OP2",
                is_paired=True,
            ),
        ],
    )

    validation = validate_schedule(schedule, [staff_op1, staff_op2])

    # Should have abteilung same night violation
    abt_violations = [
        v for v in validation.hard_violations if v.constraint_name == "Abteilung Same Night"
    ]
    assert len(abt_violations) > 0, "Should detect same abteilung on same night"


def test_abteilung_consecutive_days_constraint() -> None:
    """Test that staff from same abteilung (op/station) cannot work consecutive nights."""
    from app.scheduler.models import Assignment, Schedule, Shift, ShiftType

    # Two station staff on consecutive nights
    staff_station1 = Staff(
        name="Station Staff 1",
        identifier="ST1",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        abteilung=Abteilung.STATION,
        reception=True,
        nd_possible=True,
        nd_alone=True,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )
    staff_station2 = Staff(
        name="Station Staff 2",
        identifier="ST2",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        abteilung=Abteilung.STATION,
        reception=True,
        nd_possible=True,
        nd_alone=True,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )

    # Schedule with station staff on consecutive nights (should violate)
    schedule = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 2),
        assignments=[
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_TUE_WED, shift_date=date(2026, 4, 1)),
                staff_identifier="ST1",
                is_paired=False,
            ),
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_WED_THU, shift_date=date(2026, 4, 2)),
                staff_identifier="ST2",
                is_paired=False,
            ),
        ],
    )

    validation = validate_schedule(schedule, [staff_station1, staff_station2])

    # Should have abteilung consecutive days violation
    abt_violations = [
        v for v in validation.hard_violations if v.constraint_name == "Abteilung Consecutive Days"
    ]
    assert len(abt_violations) > 0, "Should detect same abteilung on consecutive nights"


def test_abteilung_other_exempt() -> None:
    """Test that staff with abteilung='other' are exempt from abteilung constraints."""
    from app.scheduler.models import Assignment, Schedule, Shift, ShiftType

    # Two staff with abteilung=other on same night (should NOT violate)
    staff_other1 = Staff(
        name="Other Staff 1",
        identifier="OT1",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        abteilung=Abteilung.OTHER,
        reception=True,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )
    staff_other2 = Staff(
        name="Other Staff 2",
        identifier="OT2",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        abteilung=Abteilung.OTHER,
        reception=True,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )

    # Schedule with both 'other' staff on same night (should be allowed)
    schedule = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 1),
        assignments=[
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_TUE_WED, shift_date=date(2026, 4, 1)),
                staff_identifier="OT1",
                is_paired=True,
            ),
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_TUE_WED, shift_date=date(2026, 4, 1)),
                staff_identifier="OT2",
                is_paired=True,
            ),
        ],
    )

    validation = validate_schedule(schedule, [staff_other1, staff_other2])

    # Should NOT have abteilung violations (other is exempt)
    abt_violations = [
        v for v in validation.hard_violations 
        if "Abteilung" in v.constraint_name
    ]
    assert len(abt_violations) == 0, "abteilung=other should be exempt from abteilung constraints"


def test_abteilung_cross_department_allowed() -> None:
    """Test that staff from different abteilungen can work together/consecutively."""
    from app.scheduler.models import Assignment, Schedule, Shift, ShiftType

    # OP staff and station staff on same night (should be allowed)
    staff_op = Staff(
        name="OP Staff",
        identifier="OP1",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        abteilung=Abteilung.OP,
        reception=True,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )
    staff_station = Staff(
        name="Station Staff",
        identifier="ST1",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        abteilung=Abteilung.STATION,
        reception=True,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )

    # Schedule with OP and station staff on same night (should be allowed)
    schedule = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 1),
        assignments=[
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_TUE_WED, shift_date=date(2026, 4, 1)),
                staff_identifier="OP1",
                is_paired=True,
            ),
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_TUE_WED, shift_date=date(2026, 4, 1)),
                staff_identifier="ST1",
                is_paired=True,
            ),
        ],
    )

    validation = validate_schedule(schedule, [staff_op, staff_station])

    # Should NOT have abteilung violations (different abteilungen)
    abt_violations = [
        v for v in validation.hard_violations 
        if "Abteilung" in v.constraint_name
    ]
    assert len(abt_violations) == 0, "Different abteilungen should be allowed to work together"


# =============================================================================
# VACATION AND ND_MIN_CONSECUTIVE TESTS
# =============================================================================


def test_vacation_model() -> None:
    """Test Vacation model functionality."""
    from app.scheduler.models import Vacation
    
    vacation = Vacation(
        identifier="AA",
        start_date=date(2026, 4, 13),
        end_date=date(2026, 4, 15),
    )
    
    # Test contains
    assert vacation.contains(date(2026, 4, 13))
    assert vacation.contains(date(2026, 4, 14))
    assert vacation.contains(date(2026, 4, 15))
    assert not vacation.contains(date(2026, 4, 12))
    assert not vacation.contains(date(2026, 4, 16))
    
    # Test get_dates
    dates = vacation.get_dates()
    assert len(dates) == 3
    assert date(2026, 4, 13) in dates
    assert date(2026, 4, 14) in dates
    assert date(2026, 4, 15) in dates
    
    # Test duration_days
    assert vacation.duration_days() == 3


def test_vacation_csv_loading() -> None:
    """Test loading vacations from CSV."""
    from pathlib import Path
    import tempfile
    from app.scheduler.models import load_vacations_from_csv
    
    csv_content = """identifier,start_date,end_date
AA,2026-04-13,2026-04-15
Jul,2026-05-01,2026-05-03
"""
    
    with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False) as f:
        f.write(csv_content)
        temp_path = Path(f.name)
    
    try:
        vacations = load_vacations_from_csv(temp_path)
        assert len(vacations) == 2
        assert vacations[0].identifier == "AA"
        assert vacations[0].start_date == date(2026, 4, 13)
        assert vacations[0].end_date == date(2026, 4, 15)
        assert vacations[1].identifier == "Jul"
    finally:
        temp_path.unlink()


def test_staff_unavailable_dates() -> None:
    """Test getting unavailable dates for a staff member."""
    from app.scheduler.models import Vacation, get_staff_unavailable_dates
    
    vacations = [
        Vacation(identifier="AA", start_date=date(2026, 4, 13), end_date=date(2026, 4, 15)),
        Vacation(identifier="AA", start_date=date(2026, 5, 1), end_date=date(2026, 5, 2)),
        Vacation(identifier="Jul", start_date=date(2026, 4, 20), end_date=date(2026, 4, 21)),
    ]
    
    aa_dates = get_staff_unavailable_dates(vacations, "AA")
    assert len(aa_dates) == 5  # 3 + 2 days
    assert date(2026, 4, 13) in aa_dates
    assert date(2026, 5, 1) in aa_dates
    assert date(2026, 4, 20) not in aa_dates  # Jul's vacation
    
    jul_dates = get_staff_unavailable_dates(vacations, "Jul")
    assert len(jul_dates) == 2


def test_calculate_available_days() -> None:
    """Test calculating available days in a quarter."""
    from app.scheduler.models import Vacation, calculate_available_days
    
    quarter_start = date(2026, 4, 1)
    quarter_end = date(2026, 6, 30)
    total_days = (quarter_end - quarter_start).days + 1  # 91 days
    
    vacations = [
        Vacation(identifier="AA", start_date=date(2026, 4, 13), end_date=date(2026, 4, 22)),  # 10 days
    ]
    
    available = calculate_available_days("AA", vacations, quarter_start, quarter_end)
    assert available == total_days - 10
    
    # Staff with no vacation
    available_all = calculate_available_days("Jul", vacations, quarter_start, quarter_end)
    assert available_all == total_days


def test_nd_min_consecutive_parsing() -> None:
    """Test that nd_min_consecutive is parsed correctly from CSV."""
    staff_default = Staff(
        name="Test Default",
        identifier="TD",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        reception=True,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=2,
        nd_exceptions=[],
    )
    assert staff_default.nd_min_consecutive == 2  # Default value
    
    staff_custom = Staff(
        name="Test Custom",
        identifier="TC",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        reception=True,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=3,
        nd_min_consecutive=3,
        nd_exceptions=[],
    )
    assert staff_custom.nd_min_consecutive == 3
    
    staff_azubi = Staff(
        name="Test Azubi",
        identifier="TA",
        adult=True,
        hours=40,
        beruf=Beruf.AZUBI,
        reception=False,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=2,
        nd_min_consecutive=1,
        nd_exceptions=[],
    )
    assert staff_azubi.nd_min_consecutive == 1


def test_vacation_blocks_shifts() -> None:
    """Test that vacation dates are blocked in the solver."""
    from app.scheduler.models import Vacation
    
    staff_list = [
        Staff(
            name="Test TFA 1",
            identifier="TFA1",
            adult=True,
            hours=40,
            beruf=Beruf.TFA,
            reception=True,
            nd_possible=True,
            nd_alone=True,
            nd_max_consecutive=3,
            nd_min_consecutive=2,
            nd_exceptions=[],
        ),
        Staff(
            name="Test TFA 2",
            identifier="TFA2",
            adult=True,
            hours=40,
            beruf=Beruf.TFA,
            reception=True,
            nd_possible=True,
            nd_alone=True,
            nd_max_consecutive=3,
            nd_min_consecutive=2,
            nd_exceptions=[],
        ),
        Staff(
            name="Test Azubi",
            identifier="AZ1",
            adult=True,
            hours=40,
            beruf=Beruf.AZUBI,
            reception=True,
            nd_possible=True,
            nd_alone=False,
            nd_max_consecutive=2,
            nd_min_consecutive=1,
            nd_exceptions=[],
        ),
    ]
    
    # TFA1 on vacation for first week of April
    vacations = [
        Vacation(identifier="TFA1", start_date=date(2026, 4, 1), end_date=date(2026, 4, 7)),
    ]
    
    quarter_start = date(2026, 4, 1)
    result = generate_schedule(
        staff_list, quarter_start, vacations=vacations, 
        max_solve_time_seconds=60, random_seed=42
    )
    
    if result.success:
        schedule = result.get_best_schedule()
        
        # Check that TFA1 has no assignments during vacation
        tfa1_assignments = schedule.get_staff_assignments("TFA1")
        vacation_assignments = [
            a for a in tfa1_assignments 
            if date(2026, 4, 1) <= a.shift.shift_date <= date(2026, 4, 7)
        ]
        assert len(vacation_assignments) == 0, "TFA1 should have no shifts during vacation"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
