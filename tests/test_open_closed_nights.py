"""Tests for Open and Closed Nights feature (PRD_FEATURE_OPEN_CLOSED_NIGHTS.md).

Covers test cases T1 through T11:
- T1: Exact headcount 2 on open nights
- T2: Mandatory TFA presence on open nights
- T3: Valid pairing TFA + TFA on open night
- T4: Valid pairing TFA + Intern on open night
- T5: Valid pairing TFA + Azubi on open night
- T6: Forbidden pairing Intern + Intern on open night (Open Night Missing TFA)
- T7: Forbidden pairing Intern + Azubi on open night (Open Night Missing TFA)
- T8: nd_alone=True paired on open night is allowed (no violation)
- T9: nd_alone=True on closed night must work alone
- T10: Abteilung separation H17 applies on open nights
- T11: Fairness weighting: TFA=0.5, Intern=1.0, Azubi=1.0 on open nights
"""

from datetime import date
import pytest

from app.scheduler.models import (
    Abteilung,
    Assignment,
    Beruf,
    Schedule,
    Shift,
    ShiftType,
    Staff,
)
from app.scheduler.solver import generate_schedule
from app.scheduler.validator import validate_schedule


# ---------------------------------------------------------------------------
# Model Helpers & Shift Classification Tests
# ---------------------------------------------------------------------------


def test_shift_open_closed_classification() -> None:
    """Verify is_open_night and is_closed_night classification."""
    sun_mon = Shift(shift_type=ShiftType.NIGHT_SUN_MON, shift_date=date(2026, 4, 5))
    mon_tue = Shift(shift_type=ShiftType.NIGHT_MON_TUE, shift_date=date(2026, 4, 6))
    tue_wed = Shift(shift_type=ShiftType.NIGHT_TUE_WED, shift_date=date(2026, 4, 7))
    sat_sun = Shift(shift_type=ShiftType.NIGHT_SAT_SUN, shift_date=date(2026, 4, 11))
    day_shift = Shift(shift_type=ShiftType.SATURDAY_10_21, shift_date=date(2026, 4, 11))

    assert sun_mon.is_open_night() is True
    assert sun_mon.is_closed_night() is False
    assert mon_tue.is_open_night() is True
    assert mon_tue.is_closed_night() is False

    assert tue_wed.is_open_night() is False
    assert tue_wed.is_closed_night() is True
    assert sat_sun.is_open_night() is False
    assert sat_sun.is_closed_night() is True

    assert day_shift.is_open_night() is False
    assert day_shift.is_closed_night() is False


# ---------------------------------------------------------------------------
# T11: Fairness Weighting Unit Tests
# ---------------------------------------------------------------------------


def test_t11_fairness_weighting_calculation() -> None:
    """T11: Effective night weight: TFA=0.5, Intern=1.0 on open nights, Azubi=1.0."""
    tfa = Staff(
        name="TFA Member",
        identifier="TFA1",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        reception=True,
        nd_possible=True,
        nd_alone=False,
    )
    intern = Staff(
        name="Intern Member",
        identifier="INT1",
        adult=True,
        hours=40,
        beruf=Beruf.INTERN,
        reception=False,
        nd_possible=True,
        nd_alone=False,
    )
    azubi = Staff(
        name="Azubi Member",
        identifier="AZ1",
        adult=True,
        hours=40,
        beruf=Beruf.AZUBI,
        reception=False,
        nd_possible=True,
        nd_alone=False,
    )

    # Open night (always paired):
    assert tfa.effective_nights_weight(is_paired=True, is_open_night=True) == 0.5
    assert intern.effective_nights_weight(is_paired=True, is_open_night=True) == 1.0
    assert azubi.effective_nights_weight(is_paired=True, is_open_night=True) == 1.0

    # Closed night (paired):
    assert tfa.effective_nights_weight(is_paired=True, is_open_night=False) == 0.5
    assert intern.effective_nights_weight(is_paired=True, is_open_night=False) == 0.5
    assert azubi.effective_nights_weight(is_paired=True, is_open_night=False) == 1.0

    # Closed night (solo):
    assert tfa.effective_nights_weight(is_paired=False, is_open_night=False) == 1.0
    assert intern.effective_nights_weight(is_paired=False, is_open_night=False) == 1.0
    assert azubi.effective_nights_weight(is_paired=False, is_open_night=False) == 1.0

    # Test via Schedule.count_effective_nights
    open_shift = Shift(shift_type=ShiftType.NIGHT_SUN_MON, shift_date=date(2026, 4, 5))
    closed_shift = Shift(shift_type=ShiftType.NIGHT_TUE_WED, shift_date=date(2026, 4, 7))

    schedule = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=[
            # Intern works 1 open night (paired) and 1 closed night (paired)
            Assignment(shift=open_shift, staff_identifier="INT1", is_paired=True),
            Assignment(shift=closed_shift, staff_identifier="INT1", is_paired=True),
            # TFA works 1 open night (paired) and 1 closed night (solo)
            Assignment(shift=open_shift, staff_identifier="TFA1", is_paired=True),
            Assignment(shift=closed_shift, staff_identifier="TFA1", is_paired=False),
        ],
    )

    # Intern: 1.0 (open) + 0.5 (closed paired) = 1.5
    assert schedule.count_effective_nights("INT1", staff=intern) == 1.5
    # TFA: 0.5 (open paired) + 1.0 (closed solo) = 1.5
    assert schedule.count_effective_nights("TFA1", staff=tfa) == 1.5


# ---------------------------------------------------------------------------
# Validator Tests (T3 - T10)
# ---------------------------------------------------------------------------


@pytest.fixture
def base_staff() -> dict[str, Staff]:
    """Helper fixture to create staff dict."""
    return {
        "TFA1": Staff(
            name="TFA One",
            identifier="TFA1",
            adult=True,
            hours=40,
            beruf=Beruf.TFA,
            abteilung=Abteilung.OTHER,
            reception=True,
            nd_possible=True,
            nd_alone=False,
        ),
        "TFA2": Staff(
            name="TFA Two",
            identifier="TFA2",
            adult=True,
            hours=40,
            beruf=Beruf.TFA,
            abteilung=Abteilung.OTHER,
            reception=True,
            nd_possible=True,
            nd_alone=False,
        ),
        "TFA_OP1": Staff(
            name="TFA OP 1",
            identifier="TFA_OP1",
            adult=True,
            hours=40,
            beruf=Beruf.TFA,
            abteilung=Abteilung.OP,
            reception=True,
            nd_possible=True,
            nd_alone=False,
        ),
        "TFA_OP2": Staff(
            name="TFA OP 2",
            identifier="TFA_OP2",
            adult=True,
            hours=40,
            beruf=Beruf.TFA,
            abteilung=Abteilung.OP,
            reception=True,
            nd_possible=True,
            nd_alone=False,
        ),
        "TFA_SOLO": Staff(
            name="TFA Solo",
            identifier="TFA_SOLO",
            adult=True,
            hours=40,
            beruf=Beruf.TFA,
            abteilung=Abteilung.OTHER,
            reception=True,
            nd_possible=True,
            nd_alone=True,
        ),
        "INT1": Staff(
            name="Intern One",
            identifier="INT1",
            adult=True,
            hours=40,
            beruf=Beruf.INTERN,
            abteilung=Abteilung.OTHER,
            reception=False,
            nd_possible=True,
            nd_alone=False,
        ),
        "INT2": Staff(
            name="Intern Two",
            identifier="INT2",
            adult=True,
            hours=40,
            beruf=Beruf.INTERN,
            abteilung=Abteilung.OTHER,
            reception=False,
            nd_possible=True,
            nd_alone=False,
        ),
        "AZ1": Staff(
            name="Azubi One",
            identifier="AZ1",
            adult=True,
            hours=40,
            beruf=Beruf.AZUBI,
            abteilung=Abteilung.OTHER,
            reception=False,
            nd_possible=True,
            nd_alone=False,
            nd_min_consecutive=1,
        ),
        "AZ2": Staff(
            name="Azubi Two",
            identifier="AZ2",
            adult=True,
            hours=40,
            beruf=Beruf.AZUBI,
            abteilung=Abteilung.OTHER,
            reception=False,
            nd_possible=True,
            nd_alone=False,
            nd_min_consecutive=1,
        ),
    }


def test_t3_allowed_combination_tfa_plus_tfa(base_staff: dict[str, Staff]) -> None:
    """T3: TFA + TFA on open night is valid."""
    shift = Shift(shift_type=ShiftType.NIGHT_SUN_MON, shift_date=date(2026, 4, 5))
    schedule = Schedule(
        quarter_start=date(2026, 4, 5),
        quarter_end=date(2026, 4, 5),
        assignments=[
            Assignment(shift=shift, staff_identifier="TFA1", is_paired=True),
            Assignment(shift=shift, staff_identifier="TFA2", is_paired=True),
        ],
    )
    result = validate_schedule(schedule, list(base_staff.values()))
    open_night_violations = [
        v for v in result.hard_violations
        if v.constraint_name in ("Open Night Headcount", "Open Night Missing TFA", "Multiple Azubis on Night")
    ]
    assert len(open_night_violations) == 0


def test_t4_allowed_combination_tfa_plus_intern(base_staff: dict[str, Staff]) -> None:
    """T4: TFA + Intern on open night is valid."""
    shift = Shift(shift_type=ShiftType.NIGHT_SUN_MON, shift_date=date(2026, 4, 5))
    schedule = Schedule(
        quarter_start=date(2026, 4, 5),
        quarter_end=date(2026, 4, 5),
        assignments=[
            Assignment(shift=shift, staff_identifier="TFA1", is_paired=True),
            Assignment(shift=shift, staff_identifier="INT1", is_paired=True),
        ],
    )
    result = validate_schedule(schedule, list(base_staff.values()))
    open_night_violations = [
        v for v in result.hard_violations
        if v.constraint_name in ("Open Night Headcount", "Open Night Missing TFA", "Multiple Azubis on Night")
    ]
    assert len(open_night_violations) == 0


def test_t5_allowed_combination_tfa_plus_azubi(base_staff: dict[str, Staff]) -> None:
    """T5: TFA + Azubi on open night is valid."""
    shift = Shift(shift_type=ShiftType.NIGHT_MON_TUE, shift_date=date(2026, 4, 6))
    schedule = Schedule(
        quarter_start=date(2026, 4, 6),
        quarter_end=date(2026, 4, 6),
        assignments=[
            Assignment(shift=shift, staff_identifier="TFA1", is_paired=True),
            Assignment(shift=shift, staff_identifier="AZ1", is_paired=True),
        ],
    )
    result = validate_schedule(schedule, list(base_staff.values()))
    open_night_violations = [
        v for v in result.hard_violations
        if v.constraint_name in ("Open Night Headcount", "Open Night Missing TFA", "Multiple Azubis on Night")
    ]
    assert len(open_night_violations) == 0


def test_t6_forbidden_combination_intern_plus_intern(base_staff: dict[str, Staff]) -> None:
    """T6: Intern + Intern on open night is forbidden (no TFA present)."""
    shift = Shift(shift_type=ShiftType.NIGHT_SUN_MON, shift_date=date(2026, 4, 5))
    schedule = Schedule(
        quarter_start=date(2026, 4, 5),
        quarter_end=date(2026, 4, 5),
        assignments=[
            Assignment(shift=shift, staff_identifier="INT1", is_paired=True),
            Assignment(shift=shift, staff_identifier="INT2", is_paired=True),
        ],
    )
    result = validate_schedule(schedule, list(base_staff.values()))
    tfa_violations = [v for v in result.hard_violations if v.constraint_name == "Open Night Missing TFA"]
    assert len(tfa_violations) == 1


def test_t7_forbidden_combination_intern_plus_azubi(base_staff: dict[str, Staff]) -> None:
    """T7: Intern + Azubi on open night is forbidden (no TFA present)."""
    shift = Shift(shift_type=ShiftType.NIGHT_MON_TUE, shift_date=date(2026, 4, 6))
    schedule = Schedule(
        quarter_start=date(2026, 4, 6),
        quarter_end=date(2026, 4, 6),
        assignments=[
            Assignment(shift=shift, staff_identifier="INT1", is_paired=True),
            Assignment(shift=shift, staff_identifier="AZ1", is_paired=True),
        ],
    )
    result = validate_schedule(schedule, list(base_staff.values()))
    tfa_violations = [v for v in result.hard_violations if v.constraint_name == "Open Night Missing TFA"]
    assert len(tfa_violations) == 1


def test_forbidden_azubi_plus_azubi(base_staff: dict[str, Staff]) -> None:
    """FR-2.4: Azubi + Azubi on open night is forbidden."""
    shift = Shift(shift_type=ShiftType.NIGHT_SUN_MON, shift_date=date(2026, 4, 5))
    schedule = Schedule(
        quarter_start=date(2026, 4, 5),
        quarter_end=date(2026, 4, 5),
        assignments=[
            Assignment(shift=shift, staff_identifier="AZ1", is_paired=True),
            Assignment(shift=shift, staff_identifier="AZ2", is_paired=True),
        ],
    )
    result = validate_schedule(schedule, list(base_staff.values()))
    assert any(v.constraint_name == "Open Night Missing TFA" for v in result.hard_violations)
    assert any(v.constraint_name == "Multiple Azubis on Night" for v in result.hard_violations)


def test_open_night_headcount_violations(base_staff: dict[str, Staff]) -> None:
    """FR-2.1: Open nights with 1 person or 3 persons fail headcount constraint."""
    shift = Shift(shift_type=ShiftType.NIGHT_SUN_MON, shift_date=date(2026, 4, 5))

    # Headcount = 1 (TFA solo)
    sched_solo = Schedule(
        quarter_start=date(2026, 4, 5),
        quarter_end=date(2026, 4, 5),
        assignments=[
            Assignment(shift=shift, staff_identifier="TFA1", is_paired=False),
        ],
    )
    result_solo = validate_schedule(sched_solo, list(base_staff.values()))
    assert any(v.constraint_name == "Open Night Headcount" for v in result_solo.hard_violations)

    # Headcount = 3 (TFA + TFA + Azubi)
    sched_three = Schedule(
        quarter_start=date(2026, 4, 5),
        quarter_end=date(2026, 4, 5),
        assignments=[
            Assignment(shift=shift, staff_identifier="TFA1", is_paired=True),
            Assignment(shift=shift, staff_identifier="TFA2", is_paired=True),
            Assignment(shift=shift, staff_identifier="AZ1", is_paired=True),
        ],
    )
    result_three = validate_schedule(sched_three, list(base_staff.values()))
    assert any(v.constraint_name == "Open Night Headcount" for v in result_three.hard_violations)


def test_t8_nd_alone_true_on_open_night(base_staff: dict[str, Staff]) -> None:
    """T8: nd_alone=True employee working on open night paired with another employee is valid."""
    shift = Shift(shift_type=ShiftType.NIGHT_SUN_MON, shift_date=date(2026, 4, 5))
    schedule = Schedule(
        quarter_start=date(2026, 4, 5),
        quarter_end=date(2026, 4, 5),
        assignments=[
            Assignment(shift=shift, staff_identifier="TFA_SOLO", is_paired=True),
            Assignment(shift=shift, staff_identifier="TFA1", is_paired=True),
        ],
    )
    result = validate_schedule(schedule, list(base_staff.values()))
    h6_violations = [v for v in result.hard_violations if v.constraint_name == "ND Alone Improper Pairing"]
    assert len(h6_violations) == 0


def test_t9_nd_alone_true_on_closed_night(base_staff: dict[str, Staff]) -> None:
    """T9: nd_alone=True on closed night paired with anyone must trigger violation."""
    shift = Shift(shift_type=ShiftType.NIGHT_TUE_WED, shift_date=date(2026, 4, 7))
    schedule = Schedule(
        quarter_start=date(2026, 4, 7),
        quarter_end=date(2026, 4, 7),
        assignments=[
            Assignment(shift=shift, staff_identifier="TFA_SOLO", is_paired=True),
            Assignment(shift=shift, staff_identifier="TFA1", is_paired=True),
        ],
    )
    result = validate_schedule(schedule, list(base_staff.values()))
    h6_violations = [v for v in result.hard_violations if v.constraint_name == "ND Alone Improper Pairing"]
    assert len(h6_violations) == 1


def test_t10_abteilung_h17_separation_on_open_night(base_staff: dict[str, Staff]) -> None:
    """T10: Two OP staff on the same open night triggers Abteilung Same Night violation."""
    shift = Shift(shift_type=ShiftType.NIGHT_SUN_MON, shift_date=date(2026, 4, 5))
    schedule = Schedule(
        quarter_start=date(2026, 4, 5),
        quarter_end=date(2026, 4, 5),
        assignments=[
            Assignment(shift=shift, staff_identifier="TFA_OP1", is_paired=True),
            Assignment(shift=shift, staff_identifier="TFA_OP2", is_paired=True),
        ],
    )
    result = validate_schedule(schedule, list(base_staff.values()))
    h17_violations = [v for v in result.hard_violations if v.constraint_name == "Abteilung Same Night"]
    assert len(h17_violations) == 1


# ---------------------------------------------------------------------------
# Solver Integration Tests (T1, T2)
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_t1_and_t2_solver_open_night_headcount_and_tfa() -> None:
    """T1 & T2: Solver produces exact headcount 2 and at least 1 TFA for every open night."""
    # Create a realistic staff pool capable of covering 91 days of night shifts and weekends
    staff_list: list[Staff] = []

    # 16 TFAs
    for i in range(1, 17):
        staff_list.append(
            Staff(
                name=f"TFA {i}",
                identifier=f"TFA_{i}",
                adult=True,
                hours=40,
                beruf=Beruf.TFA,
                abteilung=Abteilung.OTHER if i > 4 else (Abteilung.OP if i % 2 == 0 else Abteilung.STATION),
                reception=True,
                nd_possible=True,
                nd_alone=(i % 3 == 0),
                nd_min_consecutive=2,
            )
        )

    # 3 Interns
    for i in range(1, 4):
        staff_list.append(
            Staff(
                name=f"Intern {i}",
                identifier=f"INT_{i}",
                adult=True,
                hours=40,
                beruf=Beruf.INTERN,
                abteilung=Abteilung.OTHER,
                reception=False,
                nd_possible=True,
                nd_alone=False,
                nd_min_consecutive=2,
            )
        )

    # 4 Azubis
    for i in range(1, 5):
        staff_list.append(
            Staff(
                name=f"Azubi {i}",
                identifier=f"AZ_{i}",
                adult=True,
                hours=40,
                beruf=Beruf.AZUBI,
                abteilung=Abteilung.OTHER,
                reception=True,
                nd_possible=True,
                nd_alone=False,
                nd_min_consecutive=1,
            )
        )

    from app.scheduler.models import SchedulerConfig

    result = generate_schedule(
        staff_list=staff_list,
        quarter_start=date(2026, 4, 1),
        max_solve_time_seconds=30,
        random_seed=42,
        config=SchedulerConfig(block_gap_days=7),
    )

    assert result.success, f"Solver failed: {result.unsatisfiable_constraints}"
    schedule = result.get_best_schedule()
    assert schedule is not None

    # Check every open night in schedule
    staff_by_id = {s.identifier: s for s in staff_list}
    open_night_assignments = {}
    for a in schedule.assignments:
        if a.shift.is_open_night():
            key = (a.shift.shift_date, a.shift.shift_type)
            open_night_assignments.setdefault(key, []).append(a)

    assert len(open_night_assignments) > 0, "Schedule must contain open nights"

    for (shift_date, shift_type), assignments in open_night_assignments.items():
        # T1: Exakt 2 Personen
        assert len(assignments) == 2, (
            f"Open night on {shift_date} ({shift_type.value}) has {len(assignments)} assignments, expected 2"
        )
        # All assignments on open nights must have is_paired == True
        for a in assignments:
            assert a.is_paired is True, f"Assignment on open night {shift_date} must be paired"

        # T2: Mindestens 1 TFA
        assigned_roles = [staff_by_id[a.staff_identifier].beruf for a in assignments]
        tfa_count = sum(1 for r in assigned_roles if r == Beruf.TFA)
        assert tfa_count >= 1, (
            f"Open night on {shift_date} ({shift_type.value}) has no TFA! Roles: {assigned_roles}"
        )
        # At most 1 Azubi
        azubi_count = sum(1 for r in assigned_roles if r == Beruf.AZUBI)
        assert azubi_count <= 1


@pytest.mark.slow
def test_q4_real_data_open_closed_nights() -> None:
    """End-to-end integration test with real Q4/2026 clinic scheduling data.

    Verifies open nights (exact headcount 2, mandatory TFA, max 1 Azubi, is_paired=True),
    closed nights (nd_alone strictly respected), and Intern fairness on real data.
    """
    from pathlib import Path
    from app.scheduler.models import (
        load_staff_from_file,
        load_vacations_from_file,
        load_pre_assigned_from_file,
        build_previous_context_from_xlsx,
    )

    data_dir = Path("data/2026-Q4")
    staff_file = data_dir / "staff.xlsx" if (data_dir / "staff.xlsx").exists() else data_dir / "MA_excel (2).xlsx"
    vac_file = data_dir / "vacations.xlsx" if (data_dir / "vacations.xlsx").exists() else data_dir / "Urlaube_excel (2).xlsx"
    pre_file = data_dir / "pre_assigned.xlsx" if (data_dir / "pre_assigned.xlsx").exists() else data_dir / "Feiertage_Excel (2).xlsx"
    prev_file = data_dir / "previous_plan_q3.xlsx" if (data_dir / "previous_plan_q3.xlsx").exists() else data_dir / "Q3_Arbeitseinsätze.xlsx"

    if not staff_file.exists():
        pytest.skip("Real Q4 dataset not present")

    staff = load_staff_from_file(staff_file)
    vacations = load_vacations_from_file(vac_file)
    pre_assigned = load_pre_assigned_from_file(pre_file)
    prev_context = build_previous_context_from_xlsx(prev_file, staff_list=staff)

    result = generate_schedule(
        staff_list=staff,
        quarter_start=date(2026, 10, 1),
        vacations=vacations,
        pre_assigned=pre_assigned,
        previous_context=prev_context,
        max_solve_time_seconds=60,
        random_seed=42,
    )

    assert result.success, f"Q4 solve failed: {result.unsatisfiable_constraints}"
    schedule = result.get_best_schedule()
    assert schedule is not None

    staff_dict = {s.identifier: s for s in staff}

    # Verify every open night
    open_nights: dict[tuple[date, ShiftType], list[Assignment]] = {}
    closed_nights: dict[tuple[date, ShiftType], list[Assignment]] = {}
    for a in schedule.assignments:
        if a.shift.is_open_night():
            open_nights.setdefault((a.shift.shift_date, a.shift.shift_type), []).append(a)
        elif a.shift.is_night_shift():
            closed_nights.setdefault((a.shift.shift_date, a.shift.shift_type), []).append(a)

    # 13 weeks = 26 open nights
    assert len(open_nights) == 26

    for (shift_date, shift_type), assignments in open_nights.items():
        # Exact headcount 2
        assert len(assignments) == 2, f"Open night on {shift_date} must have exactly 2 persons"
        for a in assignments:
            assert a.is_paired is True, "Open night assignment must be paired"

        assigned_roles = [staff_dict[a.staff_identifier].beruf for a in assignments]
        tfa_count = sum(1 for r in assigned_roles if r == Beruf.TFA)
        azubi_count = sum(1 for r in assigned_roles if r == Beruf.AZUBI)
        intern_count = sum(1 for r in assigned_roles if r == Beruf.INTERN)

        # Mandatory TFA
        assert tfa_count >= 1, f"Open night on {shift_date} must have at least 1 TFA"
        # Max 1 Azubi
        assert azubi_count <= 1
        # No forbidden combinations
        assert not (intern_count == 2), "Intern + Intern forbidden on open nights"
        assert not (intern_count == 1 and azubi_count == 1), "Intern + Azubi forbidden on open nights"
        assert not (azubi_count == 2), "Azubi + Azubi forbidden on open nights"

    # Closed nights nd_alone rule
    for (shift_date, shift_type), assignments in closed_nights.items():
        assigned_staff = [staff_dict[a.staff_identifier] for a in assignments]
        for s in assigned_staff:
            if s.nd_alone:
                assert len(assignments) == 1, (
                    f"Staff {s.name} (nd_alone=True) must work alone on closed night {shift_date}"
                )
            elif s.beruf != Beruf.AZUBI:
                assert len(assignments) >= 2, (
                    f"Staff {s.name} (nd_alone=False) must be paired on closed night {shift_date}"
                )

    # Intern quarterly night cap and effective nights count
    for s in staff:
        if s.beruf == Beruf.INTERN:
            int_nights = [a for a in schedule.get_staff_assignments(s.identifier) if a.shift.is_night_shift()]
            open_int_nights = [a for a in int_nights if a.shift.is_open_night()]
            closed_int_nights = [a for a in int_nights if a.shift.is_closed_night()]

            assert 6 <= len(int_nights) <= 9, f"Intern {s.name} nights {len(int_nights)} out of [6, 9] range"

            # Check that each open night counted as 1.0 effective night
            eff_nights = schedule.count_effective_nights(s.identifier, staff=s)
            expected_eff = len(open_int_nights) * 1.0 + sum(
                0.5 if a.is_paired else 1.0 for a in closed_int_nights
            )
            assert eff_nights == expected_eff

