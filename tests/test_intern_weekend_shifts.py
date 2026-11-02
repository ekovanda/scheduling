"""Unit and integration tests for Intern Weekend Shifts (PRD_INTERN_WEEKEND_SHIFTS)."""

from datetime import date, timedelta
from pathlib import Path

import pytest

from app.scheduler.feasibility import analyze_capacity
from app.scheduler.models import (
    Assignment,
    Beruf,
    Schedule,
    SchedulerConfig,
    Shift,
    ShiftType,
    Staff,
    Vacation,
    compute_carry_forward,
    generate_quarter_shifts,
    load_staff_from_csv,
)
from app.scheduler.solver import generate_schedule
from app.scheduler.validator import validate_schedule


def _make_intern(identifier: str = "INT1", name: str = "Intern One") -> Staff:
    return Staff(
        name=name,
        identifier=identifier,
        adult=True,
        hours=40,
        beruf=Beruf.INTERN,
        reception=False,
        nd_possible=True,
        nd_alone=True,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )


def _make_tfa(identifier: str = "TFA1", name: str = "TFA One") -> Staff:
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


def _make_azubi(identifier: str = "AZ1", name: str = "Azubi One") -> Staff:
    return Staff(
        name=name,
        identifier=identifier,
        adult=True,
        hours=40,
        beruf=Beruf.AZUBI,
        reception=True,
        nd_possible=True,
        nd_alone=False,
        nd_max_consecutive=2,
        nd_exceptions=[],
    )


def _sh(shift_type: ShiftType, shift_date: date) -> Shift:
    return Shift(shift_type=shift_type, shift_date=shift_date)


def _asgn(shift_type: ShiftType, shift_date: date, staff_id: str, is_paired: bool = False) -> Assignment:
    return Assignment(
        shift=Shift(shift_type=shift_type, shift_date=shift_date),
        staff_identifier=staff_id,
        is_paired=is_paired,
    )


def test_intern_weekend_shift_types_and_eligibility() -> None:
    """Test ShiftType values, helper predicates, and Staff eligibility."""
    assert ShiftType.SATURDAY_INTERN.value == "Sa_Intern"
    assert ShiftType.SUNDAY_INTERN.value == "So_Intern"

    sa_int = _sh(ShiftType.SATURDAY_INTERN, date(2026, 4, 4))
    so_int = _sh(ShiftType.SUNDAY_INTERN, date(2026, 4, 5))
    sa_reg = _sh(ShiftType.SATURDAY_10_21, date(2026, 4, 4))
    so_reg = _sh(ShiftType.SUNDAY_8_20, date(2026, 4, 5))

    assert sa_int.is_intern_weekend_shift()
    assert so_int.is_intern_weekend_shift()
    assert not sa_reg.is_intern_weekend_shift()
    assert not so_reg.is_intern_weekend_shift()

    assert sa_int.is_weekend_shift()
    assert so_int.is_weekend_shift()

    intern = _make_intern()
    tfa = _make_tfa()
    azubi = _make_azubi()

    # Intern eligibility: allowed on Sa_Intern & So_Intern, barred from other weekend shifts
    assert intern.can_work_shift(ShiftType.SATURDAY_INTERN, date(2026, 4, 4))
    assert intern.can_work_shift(ShiftType.SUNDAY_INTERN, date(2026, 4, 5))
    assert not intern.can_work_shift(ShiftType.SATURDAY_10_19, date(2026, 4, 4))
    assert not intern.can_work_shift(ShiftType.SATURDAY_10_21, date(2026, 4, 4))
    assert not intern.can_work_shift(ShiftType.SATURDAY_10_22, date(2026, 4, 4))
    assert not intern.can_work_shift(ShiftType.SUNDAY_8_20, date(2026, 4, 5))
    assert not intern.can_work_shift(ShiftType.SUNDAY_10_22, date(2026, 4, 5))
    assert not intern.can_work_shift(ShiftType.SUNDAY_8_2030, date(2026, 4, 5))

    # TFA and Azubi: barred from Sa_Intern & So_Intern
    assert not tfa.can_work_shift(ShiftType.SATURDAY_INTERN, date(2026, 4, 4))
    assert not tfa.can_work_shift(ShiftType.SUNDAY_INTERN, date(2026, 4, 5))
    assert not azubi.can_work_shift(ShiftType.SATURDAY_INTERN, date(2026, 4, 4))
    assert not azubi.can_work_shift(ShiftType.SUNDAY_INTERN, date(2026, 4, 5))


def test_quarter_generation_boundary_guard() -> None:
    """Test boundary guards in generate_quarter_shifts: no orphan Sa_Intern or So_Intern."""
    # Q2/2026 starts Wednesday Apr 1, ends Tuesday Jun 30.
    # All 13 weekends are full natural weekends inside the quarter.
    shifts_q2 = generate_quarter_shifts(date(2026, 4, 1))
    sa_int_q2 = [s for s in shifts_q2 if s.shift_type == ShiftType.SATURDAY_INTERN]
    so_int_q2 = [s for s in shifts_q2 if s.shift_type == ShiftType.SUNDAY_INTERN]
    assert len(sa_int_q2) == 13
    assert len(so_int_q2) == 13

    # Test quarter starting on a Sunday: Oct 1 2023 is Sunday
    # Oct 1 Sunday should NOT have So_Intern (no preceding Saturday in quarter)
    shifts_oct = generate_quarter_shifts(date(2023, 10, 1))
    orphan_so = [
        s for s in shifts_oct
        if s.shift_type == ShiftType.SUNDAY_INTERN and s.shift_date == date(2023, 10, 1)
    ]
    assert len(orphan_so) == 0, "Sunday on Day 0 of quarter must not get orphan So_Intern"

    # Test quarter ending on a Saturday: Dec 31 2022 is Saturday
    # Dec 31 Saturday should NOT have Sa_Intern (no following Sunday in quarter)
    shifts_q4_2022 = generate_quarter_shifts(date(2022, 10, 1))
    orphan_sa = [
        s for s in shifts_q4_2022
        if s.shift_type == ShiftType.SATURDAY_INTERN and s.shift_date == date(2022, 12, 31)
    ]
    assert len(orphan_sa) == 0, "Saturday on last day of quarter must not get orphan Sa_Intern"


def test_coupled_weekend_block_constraint_validator() -> None:
    """Test that validator enforces coupled Sa_Intern + So_Intern for the same Intern."""
    intern1 = _make_intern("INT1", "Intern One")
    intern2 = _make_intern("INT2", "Intern Two")
    sat = date(2026, 4, 4)
    sun = date(2026, 4, 5)

    # 1. Valid: same intern on both days
    sched_valid = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 10),
        assignments=[
            _asgn(ShiftType.SATURDAY_INTERN, sat, "INT1"),
            _asgn(ShiftType.SUNDAY_INTERN, sun, "INT1"),
        ],
    )
    val = validate_schedule(sched_valid, [intern1, intern2])
    coupled_violations = [v for v in val.hard_violations if v.constraint_name == "Intern Coupled Weekend"]
    assert not coupled_violations

    # 2. Invalid: Sat assigned, Sun unassigned
    sched_orphan_sat = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 10),
        assignments=[
            _asgn(ShiftType.SATURDAY_INTERN, sat, "INT1"),
        ],
    )
    val = validate_schedule(sched_orphan_sat, [intern1, intern2])
    coupled_violations = [v for v in val.hard_violations if v.constraint_name == "Intern Coupled Weekend"]
    assert len(coupled_violations) == 1
    assert "without corresponding So_Intern" in coupled_violations[0].description

    # 3. Invalid: Sun assigned, Sat unassigned
    sched_orphan_sun = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 10),
        assignments=[
            _asgn(ShiftType.SUNDAY_INTERN, sun, "INT1"),
        ],
    )
    val = validate_schedule(sched_orphan_sun, [intern1, intern2])
    coupled_violations = [v for v in val.hard_violations if v.constraint_name == "Intern Coupled Weekend"]
    assert len(coupled_violations) == 1
    assert "without corresponding Sa_Intern" in coupled_violations[0].description

    # 4. Invalid: different interns on Sat and Sun
    sched_split = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 10),
        assignments=[
            _asgn(ShiftType.SATURDAY_INTERN, sat, "INT1"),
            _asgn(ShiftType.SUNDAY_INTERN, sun, "INT2"),
        ],
    )
    val = validate_schedule(sched_split, [intern1, intern2])
    coupled_violations = [v for v in val.hard_violations if v.constraint_name == "Intern Coupled Weekend"]
    assert len(coupled_violations) == 1
    assert "Saturday has Intern One, but Sunday has Intern Two" in coupled_violations[0].description


def test_intern_weekend_exclusivity_validator() -> None:
    """Test validator flags non-Interns on Intern shifts and Interns on regular weekend shifts."""
    intern = _make_intern("INT1")
    tfa = _make_tfa("TFA1")
    sat = date(2026, 4, 4)

    # TFA on Sa_Intern -> violation
    sched_tfa_on_int = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 10),
        assignments=[
            _asgn(ShiftType.SATURDAY_INTERN, sat, "TFA1"),
        ],
    )
    val = validate_schedule(sched_tfa_on_int, [intern, tfa])
    excl_violations = [v for v in val.hard_violations if v.constraint_name == "Intern Weekend Exclusivity"]
    assert len(excl_violations) == 1

    # Intern on Sa_10-21 -> violation
    sched_int_on_reg = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 10),
        assignments=[
            _asgn(ShiftType.SATURDAY_10_21, sat, "INT1"),
        ],
    )
    val = validate_schedule(sched_int_on_reg, [intern, tfa])
    excl_violations = [
        v for v in val.hard_violations
        if v.constraint_name in ("Intern Weekend Exclusivity", "Intern Weekend Ban")
    ]
    assert len(excl_violations) == 1


def test_intern_monthly_weekend_cap_validator() -> None:
    """Test that validator enforces max 1 weekend per calendar month per Intern."""
    intern = _make_intern("INT1")
    sat1, sun1 = date(2026, 4, 4), date(2026, 4, 5)
    sat2, sun2 = date(2026, 4, 18), date(2026, 4, 19)
    sat3, sun3 = date(2026, 5, 2), date(2026, 5, 3)

    # 2 weekends in April -> violation
    sched_cap_violated = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 5, 31),
        assignments=[
            _asgn(ShiftType.SATURDAY_INTERN, sat1, "INT1"),
            _asgn(ShiftType.SUNDAY_INTERN, sun1, "INT1"),
            _asgn(ShiftType.SATURDAY_INTERN, sat2, "INT1"),
            _asgn(ShiftType.SUNDAY_INTERN, sun2, "INT1"),
        ],
    )
    val = validate_schedule(sched_cap_violated, [intern])
    cap_violations = [v for v in val.hard_violations if v.constraint_name == "Intern Monthly Weekend Cap"]
    assert len(cap_violations) == 1
    assert "maximum is 1 per calendar month" in cap_violations[0].description

    # 1 weekend in April, 1 in May -> valid
    sched_cap_ok = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 5, 31),
        assignments=[
            _asgn(ShiftType.SATURDAY_INTERN, sat1, "INT1"),
            _asgn(ShiftType.SUNDAY_INTERN, sun1, "INT1"),
            _asgn(ShiftType.SATURDAY_INTERN, sat3, "INT1"),
            _asgn(ShiftType.SUNDAY_INTERN, sun3, "INT1"),
        ],
    )
    val = validate_schedule(sched_cap_ok, [intern])
    cap_violations = [v for v in val.hard_violations if v.constraint_name == "Intern Monthly Weekend Cap"]
    assert not cap_violations


def test_intern_10_day_block_gap_validator() -> None:
    """Test that validator allows 10-day gap for Interns while enforcing 21-day gap for TFAs."""
    intern = _make_intern("INT1")
    tfa = _make_tfa("TFA1")

    # Intern: Weekend block Apr 4-5 (start Apr 4), Night block starts Apr 14 (exactly 10 days later)
    sched_intern_ok = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=[
            _asgn(ShiftType.SATURDAY_INTERN, date(2026, 4, 4), "INT1"),
            _asgn(ShiftType.SUNDAY_INTERN, date(2026, 4, 5), "INT1"),
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 4, 14), "INT1"),
            _asgn(ShiftType.NIGHT_WED_THU, date(2026, 4, 15), "INT1"),
        ],
    )
    val = validate_schedule(sched_intern_ok, [intern, tfa], config=SchedulerConfig(intern_block_gap_days=10))
    block_violations = [v for v in val.hard_violations if "Block Limit" in v.constraint_name]
    assert not block_violations, f"10-day gap should be valid for Intern, got: {block_violations}"

    # Intern: Block starts Apr 4 and Apr 11 (7 days later) -> violation
    sched_intern_fail = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=[
            _asgn(ShiftType.SATURDAY_INTERN, date(2026, 4, 4), "INT1"),
            _asgn(ShiftType.SUNDAY_INTERN, date(2026, 4, 5), "INT1"),
            _asgn(ShiftType.NIGHT_SAT_SUN, date(2026, 4, 11), "INT1"),
            _asgn(ShiftType.NIGHT_SUN_MON, date(2026, 4, 12), "INT1"),
        ],
    )
    val = validate_schedule(sched_intern_fail, [intern, tfa], config=SchedulerConfig(intern_block_gap_days=10))
    block_violations = [v for v in val.hard_violations if v.constraint_name == "10-Day Block Limit"]
    assert len(block_violations) == 1

    # TFA: Block starts Apr 4 and Apr 18 (14 days later, < 21 days) -> violation
    sched_tfa_fail = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=[
            _asgn(ShiftType.SATURDAY_10_21, date(2026, 4, 4), "TFA1"),
            _asgn(ShiftType.SATURDAY_10_21, date(2026, 4, 18), "TFA1"),
        ],
    )
    val = validate_schedule(sched_tfa_fail, [intern, tfa])
    block_violations = [v for v in val.hard_violations if v.constraint_name == "3-Week Block Limit"]
    assert len(block_violations) == 1


def test_intern_weekend_isolation_validator() -> None:
    """Test weekend isolation: Sa_Intern + So_Intern pair allowed, adjacent nights banned."""
    intern = _make_intern("INT1")
    sat = date(2026, 4, 4)
    sun = date(2026, 4, 5)

    # 1. Coupled weekend only -> Valid
    sched_pair_ok = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 10),
        assignments=[
            _asgn(ShiftType.SATURDAY_INTERN, sat, "INT1"),
            _asgn(ShiftType.SUNDAY_INTERN, sun, "INT1"),
        ],
    )
    val = validate_schedule(sched_pair_ok, [intern])
    we_iso = [v for v in val.hard_violations if v.constraint_name == "Weekend Isolation"]
    assert not we_iso

    # 2. Friday night before Sa_Intern -> Banned!
    fri = date(2026, 4, 3)
    sched_fri_night = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 10),
        assignments=[
            _asgn(ShiftType.NIGHT_FRI_SAT, fri, "INT1"),
            _asgn(ShiftType.SATURDAY_INTERN, sat, "INT1"),
            _asgn(ShiftType.SUNDAY_INTERN, sun, "INT1"),
        ],
    )
    val = validate_schedule(sched_fri_night, [intern])
    we_iso = [v for v in val.hard_violations if v.constraint_name == "Weekend Isolation"]
    assert len(we_iso) > 0, "Friday night before Saturday Intern shift must violate Weekend Isolation"

    # 3. Sunday So_Intern followed by Monday night -> Banned!
    mon = date(2026, 4, 6)
    sched_mon_night = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 10),
        assignments=[
            _asgn(ShiftType.SATURDAY_INTERN, sat, "INT1"),
            _asgn(ShiftType.SUNDAY_INTERN, sun, "INT1"),
            _asgn(ShiftType.NIGHT_MON_TUE, mon, "INT1"),
        ],
    )
    val = validate_schedule(sched_mon_night, [intern])
    we_iso = [v for v in val.hard_violations if v.constraint_name == "Weekend Isolation"]
    assert len(we_iso) > 0, "Sunday Intern shift followed by Monday night must violate Weekend Isolation"


def test_intern_carry_forward_track1_only() -> None:
    """Test that compute_carry_forward normalizes only effective_nights for Interns."""
    intern = _make_intern("INT1")
    tfa = _make_tfa("TFA1")

    # Schedule: INT1 has 2 weekend shifts (1 weekend) and 4 effective nights
    # TFA1 has 2 weekend shifts and 4 effective nights
    sched = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=[
            _asgn(ShiftType.SATURDAY_INTERN, date(2026, 4, 4), "INT1"),
            _asgn(ShiftType.SUNDAY_INTERN, date(2026, 4, 5), "INT1"),
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 4, 14), "INT1"),
            _asgn(ShiftType.NIGHT_WED_THU, date(2026, 4, 15), "INT1"),
            _asgn(ShiftType.NIGHT_THU_FRI, date(2026, 4, 16), "INT1"),
            _asgn(ShiftType.NIGHT_FRI_SAT, date(2026, 4, 17), "INT1"),
            _asgn(ShiftType.SATURDAY_10_21, date(2026, 4, 4), "TFA1"),
            _asgn(ShiftType.SUNDAY_8_20, date(2026, 4, 5), "TFA1"),
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 4, 28), "TFA1"),
            _asgn(ShiftType.NIGHT_WED_THU, date(2026, 4, 29), "TFA1"),
        ],
    )
    cf = compute_carry_forward(sched, [intern, tfa], vacations=[])
    int_entry = next(e for e in cf if e.identifier == "INT1")
    tfa_entry = next(e for e in cf if e.identifier == "TFA1")

    # Intern normalized_40h should be based on 4.0 nights (Track 1)
    # Weekend duties for interns are counted in coupled weekend blocks (1 weekend = 1 duty)
    assert int_entry.effective_nights == 4.0
    assert int_entry.weekend_shifts == 1
    assert int_entry.total_notdienst == 5.0
    assert pytest.approx(int_entry.normalized_40h, 0.01) == 4.0

    # TFA normalized_40h should be based on 2 nights + 2 weekends = 4.0 total Notdienst
    assert tfa_entry.effective_nights == 2.0
    assert tfa_entry.weekend_shifts == 2
    assert pytest.approx(tfa_entry.normalized_40h, 0.01) == 4.0


def test_intern_weekend_counting_and_fairness_units() -> None:
    """Finding B4: verify that coupled intern weekends count as 1 weekend block."""
    intern = _make_intern("INT1")
    tfa = _make_tfa("TFA1")

    sched = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=[
            _asgn(ShiftType.SATURDAY_INTERN, date(2026, 4, 4), "INT1"),
            _asgn(ShiftType.SUNDAY_INTERN, date(2026, 4, 5), "INT1"),
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 4, 14), "INT1"),
            _asgn(ShiftType.SATURDAY_10_21, date(2026, 4, 4), "TFA1"),
            _asgn(ShiftType.SUNDAY_8_20, date(2026, 4, 5), "TFA1"),
        ],
    )

    # Raw shifts vs coupled weekend units for Intern
    assert sched.count_weekend_shifts("INT1") == 2
    assert sched.count_intern_weekends("INT1") == 1
    assert sched.count_weekends("INT1", intern) == 1
    assert sched.count_weekends("INT1") == 1  # Inferred without staff object
    assert sched.count_total_notdienst("INT1", intern) == 2.0  # 1 weekend + 1 night

    # For TFA, weekend count equals raw shifts
    assert sched.count_weekend_shifts("TFA1") == 2
    assert sched.count_weekends("TFA1", tfa) == 2
    assert sched.count_total_notdienst("TFA1", tfa) == 2.0  # 2 weekend shifts + 0 nights


def test_feasibility_capacity_check_intern() -> None:
    """Test that analyze_capacity reports both night and weekend capacity for Interns."""
    intern = _make_intern("INT1")
    tfa = _make_tfa("TFA1")
    report = analyze_capacity(
        staff_list=[intern, tfa],
        vacations=[],
        pre_assigned=[],
        quarter_start=date(2026, 4, 1),
        config=SchedulerConfig(),
    )
    check_intern = next(c for c in report.checks if "Intern Kapazität" in c.name)
    assert check_intern.status == "ok"
    # Message should mention both nights and weekends
    assert "Nächte" in check_intern.message
    assert "Wochenenden" in check_intern.message


@pytest.mark.slow
def test_solver_coupled_intern_weekend_and_monthly_cap() -> None:
    """Test that solver generates coupled weekends and respects the 1 WE/month cap for Interns."""
    staff = load_staff_from_csv(Path("data/staff_sample.csv"))
    intern = _make_intern("INT_A", "Intern Alpha")
    staff_with_intern = staff + [intern]
    quarter_start = date(2026, 4, 1)

    result = generate_schedule(
        staff_with_intern,
        quarter_start,
        vacations=[],
        max_solve_time_seconds=30,
        random_seed=42,
    )
    assert result.success, f"Solver failed: {result.unsatisfiable_constraints}"

    schedule = result.get_best_schedule()
    val = validate_schedule(schedule, staff_with_intern)
    assert val.is_valid(), f"Schedule had violations: {[str(v) for v in val.hard_violations]}"

    # Verify coupled weekends for INT_A
    int_assignments = [a for a in schedule.assignments if a.staff_identifier == "INT_A"]
    sat_dates = {a.shift.shift_date for a in int_assignments if a.shift.shift_type == ShiftType.SATURDAY_INTERN}
    sun_dates = {a.shift.shift_date for a in int_assignments if a.shift.shift_type == ShiftType.SUNDAY_INTERN}

    # Every Saturday must have Sunday = Saturday + 1 day
    for s_date in sat_dates:
        assert (s_date + timedelta(days=1)) in sun_dates, f"Sa_Intern on {s_date} missing paired So_Intern"
    for u_date in sun_dates:
        assert (u_date - timedelta(days=1)) in sat_dates, f"So_Intern on {u_date} missing paired Sa_Intern"

    # Monthly cap: <= 1 weekend per calendar month
    months_seen = [d.month for d in sat_dates]
    assert len(months_seen) == len(set(months_seen)), f"Intern worked >1 weekend in a month: {months_seen}"
    assert len(sat_dates) <= 3, f"Intern worked >3 weekends across quarter: {len(sat_dates)}"


@pytest.mark.slow
def test_solver_single_day_vacation_guard() -> None:
    """Test that vacation on Saturday prevents Sunday assignment for the same Intern."""
    staff = load_staff_from_csv(Path("data/staff_sample.csv"))
    intern = _make_intern("INT_V", "Intern Vacation")
    staff_with_intern = staff + [intern]
    quarter_start = date(2026, 4, 1)

    # Saturday April 4 is on vacation for INT_V
    vac = [Vacation(identifier="INT_V", start_date=date(2026, 4, 4), end_date=date(2026, 4, 4))]

    result = generate_schedule(
        staff_with_intern,
        quarter_start,
        vacations=vac,
        max_solve_time_seconds=30,
        random_seed=42,
    )
    assert result.success

    schedule = result.get_best_schedule()
    int_assignments = [a for a in schedule.assignments if a.staff_identifier == "INT_V"]
    # Neither April 4 nor April 5 can be assigned to INT_V
    apr_we = [a for a in int_assignments if a.shift.shift_date in (date(2026, 4, 4), date(2026, 4, 5))]
    assert not apr_we, f"INT_V assigned during or adjacent to vacation weekend: {apr_we}"


@pytest.mark.slow
def test_solver_two_track_intern_fairness() -> None:
    """Test that solver balances Track 1 (nights) and Track 2 (weekends) across multiple Interns."""
    staff = load_staff_from_csv(Path("data/staff_sample.csv"))
    int1 = _make_intern("INT_1", "Intern One")
    int2 = _make_intern("INT_2", "Intern Two")
    staff_with_interns = staff + [int1, int2]
    quarter_start = date(2026, 4, 1)

    result = generate_schedule(
        staff_with_interns,
        quarter_start,
        vacations=[],
        max_solve_time_seconds=30,
        random_seed=42,
    )
    assert result.success

    schedule = result.get_best_schedule()
    val = validate_schedule(schedule, staff_with_interns)
    assert val.is_valid(), f"Violations: {[str(v) for v in val.hard_violations]}"

    # Track 1: nights 6-9
    nights_1 = sum(1 for a in schedule.assignments if a.staff_identifier == "INT_1" and a.shift.is_night_shift())
    nights_2 = sum(1 for a in schedule.assignments if a.staff_identifier == "INT_2" and a.shift.is_night_shift())
    assert 6 <= nights_1 <= 9
    assert 6 <= nights_2 <= 9

    # Track 2: weekends balanced (min-max range <= 1)
    we_1 = sum(1 for a in schedule.assignments if a.staff_identifier == "INT_1" and a.shift.shift_type == ShiftType.SATURDAY_INTERN)
    we_2 = sum(1 for a in schedule.assignments if a.staff_identifier == "INT_2" and a.shift.shift_type == ShiftType.SATURDAY_INTERN)
    assert abs(we_1 - we_2) <= 1, f"Intern weekend spread too wide: {we_1} vs {we_2}"


