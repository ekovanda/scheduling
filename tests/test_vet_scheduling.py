"""Unit and integration tests for Vet Midweek Night Shift Relief (PRD_tierarzt_nachtdienst_entlastung)."""

from datetime import date, timedelta
from pathlib import Path
import pytest

from app.scheduler.models import (
    Abteilung,
    Assignment,
    Beruf,
    PreviousPlanContext,
    Schedule,
    SchedulerConfig,
    Shift,
    ShiftType,
    Staff,
    TrailingAssignment,
    Vacation,
    build_previous_context,
    compute_carry_forward,
    load_staff_from_csv,
)
from app.scheduler.exceptions import StaffValidationError
from app.scheduler.feasibility import analyze_capacity
from app.scheduler.file_loader import load_staff_from_file
from app.scheduler.solver import generate_schedule
from app.scheduler.validator import validate_schedule, _calculate_soft_penalty


def _make_vet(identifier: str = "TA1", name: str = "Dr. Vet One") -> Staff:
    return Staff(
        name=name,
        identifier=identifier,
        beruf=Beruf.VET,
    )


def _make_tfa(identifier: str = "TFA1", name: str = "TFA One", hours: float = 40.0) -> Staff:
    return Staff(
        name=name,
        identifier=identifier,
        adult=True,
        hours=hours,
        beruf=Beruf.TFA,
        reception=True,
        nd_possible=True,
        nd_alone=True,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )


def _make_intern(identifier: str = "INT1", name: str = "Intern One") -> Staff:
    return Staff(
        name=name,
        identifier=identifier,
        adult=True,
        hours=40.0,
        beruf=Beruf.INTERN,
        reception=False,
        nd_possible=True,
        nd_alone=True,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )


def _asgn(shift_type: ShiftType, shift_date: date, staff_id: str, is_paired: bool = False) -> Assignment:
    return Assignment(
        shift=Shift(shift_type=shift_type, shift_date=shift_date),
        staff_identifier=staff_id,
        is_paired=is_paired,
    )


# ---------------------------------------------------------------------------
# 1. Model & Invariants Tests
# ---------------------------------------------------------------------------


def test_vet_enum_and_model_invariants() -> None:
    """Verify Beruf.VET exists and Staff enforces invariants for Vets."""
    assert Beruf.VET.value == "Vet"

    vet = _make_vet("TA_MUE", "Dr. Martin Müller")
    assert vet.beruf == Beruf.VET
    assert vet.adult is True
    assert vet.hours == 0.0
    assert vet.abteilung == Abteilung.OTHER
    assert vet.reception is False
    assert vet.nd_possible is True
    assert vet.nd_alone is True
    assert vet.nd_min_consecutive == 2
    assert vet.nd_max_consecutive == 2
    assert vet.nd_exceptions == []

    # Check that even if invalid values are passed, validator overrides them
    vet_forced = Staff(
        name="Dr. Override",
        identifier="TA_OVR",
        beruf=Beruf.VET,
        adult=False,
        hours=40.0,
        reception=True,
        nd_alone=False,
        nd_min_consecutive=1,
        nd_max_consecutive=4,
        abteilung=Abteilung.OP,
    )
    assert vet_forced.adult is True
    assert vet_forced.hours == 0.0
    assert vet_forced.reception is False
    assert vet_forced.nd_alone is True
    assert vet_forced.nd_min_consecutive == 2
    assert vet_forced.nd_max_consecutive == 2
    assert vet_forced.abteilung == Abteilung.OTHER


def test_vet_role_normalization() -> None:
    """Verify role 'Vet' normalizes to Beruf.VET, and ambiguous shortcuts raise StaffValidationError."""
    s1 = Staff(name="Vet 1", identifier="V1", beruf="Vet")  # type: ignore[arg-type]
    assert s1.beruf == Beruf.VET

    # Legacy ambiguous shortcuts 'TA', 'Tierarzt', 'TA_Entlastung' must be rejected
    with pytest.raises(StaffValidationError, match="deprecated and ambiguous"):
        Staff(name="Vet 2", identifier="V2", beruf="Tierarzt")  # type: ignore[arg-type]

    with pytest.raises(StaffValidationError, match="deprecated and ambiguous"):
        Staff(name="Vet 3", identifier="V3", beruf="TA_Entlastung")  # type: ignore[arg-type]

    with pytest.raises(StaffValidationError, match="deprecated and ambiguous"):
        Staff(name="Old TA", identifier="T1", adult=True, hours=40, beruf="TA", reception=False, nd_possible=True, nd_alone=True)  # type: ignore[arg-type]


def test_vet_shift_eligibility() -> None:
    """Verify can_work_shift allows only midweek nights (Di-Mi, Mi-Do, Do-Fr)."""
    vet = _make_vet()

    # Allowed
    assert vet.can_work_shift(ShiftType.NIGHT_TUE_WED, date(2026, 4, 7)) is True
    assert vet.can_work_shift(ShiftType.NIGHT_WED_THU, date(2026, 4, 8)) is True
    assert vet.can_work_shift(ShiftType.NIGHT_THU_FRI, date(2026, 4, 9)) is True

    # Disallowed: weekend nights
    assert vet.can_work_shift(ShiftType.NIGHT_FRI_SAT, date(2026, 4, 10)) is False
    assert vet.can_work_shift(ShiftType.NIGHT_SAT_SUN, date(2026, 4, 11)) is False

    # Disallowed: open nights
    assert vet.can_work_shift(ShiftType.NIGHT_SUN_MON, date(2026, 4, 12)) is False
    assert vet.can_work_shift(ShiftType.NIGHT_MON_TUE, date(2026, 4, 13)) is False

    # Disallowed: day shifts
    assert vet.can_work_shift(ShiftType.SATURDAY_10_21, date(2026, 4, 11)) is False
    assert vet.can_work_shift(ShiftType.SUNDAY_8_20, date(2026, 4, 12)) is False
    assert vet.can_work_shift(ShiftType.SATURDAY_INTERN, date(2026, 4, 11)) is False
    assert vet.can_work_shift(ShiftType.SUNDAY_INTERN, date(2026, 4, 12)) is False


# ---------------------------------------------------------------------------
# 2. Validator Constraints Tests
# ---------------------------------------------------------------------------


def test_vet_validator_exact_two_night_blocks() -> None:
    """Verify validator flags single nights and 3-night blocks, but accepts 2-night blocks."""
    vet = _make_vet("TA1")
    tfa = _make_tfa("TFA1")

    # 1. Valid 2-night block: Di+Mi
    sched_valid = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=[
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 4, 7), "TA1"),
            _asgn(ShiftType.NIGHT_WED_THU, date(2026, 4, 8), "TA1"),
        ],
    )
    val = validate_schedule(sched_valid, [vet, tfa])
    vet_violations = [v for v in val.hard_violations if v.constraint_name == "Vet Shift Constraint"]
    assert not vet_violations

    # 2. Invalid 1-night block
    sched_single = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=[
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 4, 7), "TA1"),
        ],
    )
    val_single = validate_schedule(sched_single, [vet, tfa])
    vet_violations = [v for v in val_single.hard_violations if v.constraint_name == "Vet Shift Constraint"]
    assert len(vet_violations) == 1
    assert "hat Block der Länge 1" in vet_violations[0].description

    # 3. Invalid 3-night block: Di+Mi+Do
    sched_triple = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=[
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 4, 7), "TA1"),
            _asgn(ShiftType.NIGHT_WED_THU, date(2026, 4, 8), "TA1"),
            _asgn(ShiftType.NIGHT_THU_FRI, date(2026, 4, 9), "TA1"),
        ],
    )
    val_triple = validate_schedule(sched_triple, [vet, tfa])
    vet_violations = [v for v in val_triple.hard_violations if v.constraint_name == "Vet Shift Constraint"]
    assert len(vet_violations) == 1
    assert "hat Block der Länge 3" in vet_violations[0].description


def test_vet_validator_solo_duty() -> None:
    """Verify validator flags any night where Vet is paired with another staff member."""
    vet = _make_vet("TA1")
    tfa = _make_tfa("TFA1")

    # Vet paired with TFA on Tuesday night
    sched_paired = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=[
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 4, 7), "TA1"),
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 4, 7), "TFA1"),
            _asgn(ShiftType.NIGHT_WED_THU, date(2026, 4, 8), "TA1"),
        ],
    )
    val = validate_schedule(sched_paired, [vet, tfa])
    vet_violations = [v for v in val.hard_violations if v.constraint_name == "Vet Shift Constraint"]
    assert any("Vet muss Alleindienst leisten" in v.description for v in vet_violations)


def test_vet_validator_disallowed_shift() -> None:
    """Verify validator flags Vet assigned to forbidden shift."""
    vet = _make_vet("TA1")

    sched = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=[
            _asgn(ShiftType.NIGHT_FRI_SAT, date(2026, 4, 10), "TA1"),
            _asgn(ShiftType.NIGHT_SAT_SUN, date(2026, 4, 11), "TA1"),
        ],
    )
    val = validate_schedule(sched, [vet])
    vet_violations = [v for v in val.hard_violations if v.constraint_name == "Vet Shift Constraint"]
    assert any("unzulässige Schicht" in v.description for v in vet_violations)


def test_vet_validator_two_month_frequency_rule() -> None:
    """Verify validator enforces max 1 block per 2 consecutive calendar months."""
    vet = _make_vet("TA1")

    # Block 1 in April (2026-04-07..08) and Block 2 in May (2026-05-05..06) -> Consecutive months, violation!
    sched_consec_months = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 6, 30),
        assignments=[
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 4, 7), "TA1"),
            _asgn(ShiftType.NIGHT_WED_THU, date(2026, 4, 8), "TA1"),
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 5, 5), "TA1"),
            _asgn(ShiftType.NIGHT_WED_THU, date(2026, 5, 6), "TA1"),
        ],
    )
    val_consec = validate_schedule(sched_consec_months, [vet])
    freq_violations = [v for v in val_consec.hard_violations if v.constraint_name == "Vet Shift Constraint" and "Kalendermonaten" in v.description]
    assert len(freq_violations) == 1
    assert "04.2026 und 05.2026" in freq_violations[0].description

    # Block 1 in April and Block 2 in June -> Month diff is 2, valid!
    sched_spaced = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 6, 30),
        assignments=[
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 4, 7), "TA1"),
            _asgn(ShiftType.NIGHT_WED_THU, date(2026, 4, 8), "TA1"),
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 6, 9), "TA1"),
            _asgn(ShiftType.NIGHT_WED_THU, date(2026, 6, 10), "TA1"),
        ],
    )
    val_spaced = validate_schedule(sched_spaced, [vet])
    freq_violations_spaced = [v for v in val_spaced.hard_violations if v.constraint_name == "Vet Shift Constraint" and "Kalendermonaten" in v.description]
    assert not freq_violations_spaced


def test_vet_validator_cross_quarter_lockout() -> None:
    """Verify validator flags Vet assigned in month 1 if locked out from previous quarter (B3/E2)."""
    vet = _make_vet("V1")
    tfa = _make_tfa("TFA1")

    # V1 assigned in April (month 4)
    sched = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 6, 30),
        assignments=[
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 4, 7), "V1"),
            _asgn(ShiftType.NIGHT_WED_THU, date(2026, 4, 8), "V1"),
        ],
    )

    prev_ctx = PreviousPlanContext(
        quarter_start=date(2026, 1, 1),
        quarter_end=date(2026, 3, 31),
        carry_forward=[],
        trailing_assignments=[],
        vet_active_last_month_ids=["V1"],
    )

    # Locked out vet assigned in month 1 -> Hard violation
    val = validate_schedule(sched, [vet, tfa], previous_context=prev_ctx)
    lockout_violations = [
        v for v in val.hard_violations
        if v.constraint_name == "Vet Shift Constraint" and "Vorquartalsdienst gesperrt" in v.description
    ]
    assert len(lockout_violations) == 1
    assert "V1" in lockout_violations[0].description

    # Without previous context (or vet not locked out), validation passes
    val_ok = validate_schedule(sched, [vet, tfa])
    assert not any("Vorquartalsdienst gesperrt" in v.description for v in val_ok.hard_violations)


# ---------------------------------------------------------------------------
# 3. Carry Forward & Soft Penalty Exclusion Tests
# ---------------------------------------------------------------------------


def test_vet_excluded_from_carry_forward_and_soft_penalty() -> None:
    """Verify Vet (hours=0) does not cause ZeroDivisionError in compute_carry_forward or soft penalty."""
    vet = _make_vet("TA1")
    tfa = _make_tfa("TFA1", hours=40.0)

    sched = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 4, 30),
        assignments=[
            _asgn(ShiftType.NIGHT_TUE_WED, date(2026, 4, 7), "TA1"),
            _asgn(ShiftType.NIGHT_WED_THU, date(2026, 4, 8), "TA1"),
            _asgn(ShiftType.NIGHT_THU_FRI, date(2026, 4, 9), "TFA1"),
            _asgn(ShiftType.NIGHT_FRI_SAT, date(2026, 4, 10), "TFA1"),
        ],
    )

    # compute_carry_forward should skip TA1 and compute only for TFA1
    cf = compute_carry_forward(sched, [vet, tfa])
    cf_ids = [entry.identifier for entry in cf]
    assert "TA1" not in cf_ids
    assert "TFA1" in cf_ids

    # _calculate_soft_penalty should run without error
    penalty = _calculate_soft_penalty(sched, [vet, tfa])
    assert isinstance(penalty, float)


# ---------------------------------------------------------------------------
# 4. Feasibility Check F Tests
# ---------------------------------------------------------------------------


def test_feasibility_check_f_with_vets() -> None:
    """Verify analyze_capacity detects Vets, calculates max blocks, and adds Check F."""
    vet1 = _make_vet("TA1")
    vet2 = _make_vet("TA2")
    tfa = _make_tfa("TFA1")

    # Quarter: 2026-04-01 to 2026-06-30
    res = analyze_capacity(
        staff_list=[vet1, vet2, tfa],
        vacations=[],
        pre_assigned=[],
        quarter_start=date(2026, 4, 1),
        config=SchedulerConfig(),
    )

    # Check F should be present in results
    check_f = next((c for c in res.checks if c.name == "Vet-Nachtdienst-Entlastung"), None)
    assert check_f is not None
    assert check_f.status == "ok"
    assert "2 Vet/Vets: bis zu 4 Blöcke (8 Nächte Entlastung)" in check_f.message
    assert len(check_f.details) == 2
    assert "Dr. Vet One: bis zu 2 Blöcke (4 Nächte)" in check_f.details[0]
    assert "Dr. Vet One: bis zu 2 Blöcke (4 Nächte)" in check_f.details[1]


# ---------------------------------------------------------------------------
# 5. Solver Integration Tests
# ---------------------------------------------------------------------------


@pytest.mark.slow
def test_solver_vet_schedule_generation() -> None:
    """Test solver schedules Vets in exact 2-night blocks alone and satisfies all rules."""
    staff = load_staff_from_csv(Path("data/staff_sample.csv"))
    vet1 = _make_vet("TA1", "Dr. Vet Eins")
    vet2 = _make_vet("TA2", "Dr. Vet Zwei")
    staff_with_vets = staff + [vet1, vet2]
    quarter_start = date(2026, 4, 1)

    result = generate_schedule(
        staff_with_vets,
        quarter_start,
        vacations=[],
        max_solve_time_seconds=30,
        random_seed=42,
    )
    assert result.success, f"Solver failed: {result.unsatisfiable_constraints}"

    schedule = result.get_best_schedule()
    val = validate_schedule(schedule, staff_with_vets)
    assert val.is_valid(), f"Validation violations: {[str(v) for v in val.hard_violations]}"

    # Check Vet assignments
    for vet_id in ("TA1", "TA2"):
        vet_asgns = sorted(
            [a for a in schedule.assignments if a.staff_identifier == vet_id],
            key=lambda a: a.shift.shift_date,
        )
        assert len(vet_asgns) > 0, f"Vet {vet_id} received 0 assignments despite high priority incentive"

        # Every Vet assignment must be midweek
        for a in vet_asgns:
            assert a.shift.shift_type in (
                ShiftType.NIGHT_TUE_WED,
                ShiftType.NIGHT_WED_THU,
                ShiftType.NIGHT_THU_FRI,
            )

        # Check solo duty on all Vet nights
        for a in vet_asgns:
            co_workers = [
                x for x in schedule.assignments
                if x.shift.shift_date == a.shift.shift_date and x.shift.shift_type == a.shift.shift_type
            ]
            assert len(co_workers) == 1, f"Vet {vet_id} not alone on {a.shift.shift_date}: {co_workers}"

        # Check block lengths
        from app.scheduler.validator import _find_consecutive_blocks
        blocks = _find_consecutive_blocks(vet_asgns)
        for b in blocks:
            assert len(b) == 2, f"Vet {vet_id} block has length {len(b)} != 2: {[a.shift.shift_date for a in b]}"

        # Check 2-month calendar boundary
        block_months = [b[0].shift.shift_date.month for b in blocks]
        for i, m1 in enumerate(block_months):
            for m2 in block_months[i + 1:]:
                assert abs(m2 - m1) > 1, f"Vet {vet_id} has blocks in consecutive months: {block_months}"


@pytest.mark.slow
def test_solver_vet_cross_quarter_lockout() -> None:
    """Test that a Vet active in last month of previous quarter is locked out in month 1."""
    staff = load_staff_from_csv(Path("data/staff_sample.csv"))
    vet1 = _make_vet("TA1", "Dr. Vet Eins")
    vet2 = _make_vet("TA2", "Dr. Vet Zwei")
    staff_with_vets = staff + [vet1, vet2]
    quarter_start = date(2026, 4, 1)

    # Previous context: TA1 worked in March (month 3)
    prev_context = PreviousPlanContext(
        quarter_start=date(2026, 1, 1),
        quarter_end=date(2026, 3, 31),
        carry_forward=[],
        trailing_assignments=[],
        vet_active_last_month_ids=["TA1"],
    )

    result = generate_schedule(
        staff_with_vets,
        quarter_start,
        vacations=[],
        previous_context=prev_context,
        max_solve_time_seconds=30,
        random_seed=42,
    )
    assert result.success

    schedule = result.get_best_schedule()
    val = validate_schedule(schedule, staff_with_vets)
    assert val.is_valid(), f"Validation violations: {[str(v) for v in val.hard_violations]}"

    # TA1 must NOT be scheduled in April (month 4)
    ta1_asgns = [a for a in schedule.assignments if a.staff_identifier == "TA1"]
    ta1_months = {a.shift.shift_date.month for a in ta1_asgns}
    assert 4 not in ta1_months, f"TA1 scheduled in April despite being locked out from previous quarter: {ta1_months}"

    # TA1 should be scheduled in May (5) or June (6)
    if ta1_asgns:
        assert all(m in (5, 6) for m in ta1_months)


@pytest.mark.slow
def test_solver_fallback_without_vets() -> None:
    """Test solver solves and validates cleanly when no Vets are provided."""
    staff = load_staff_from_csv(Path("data/staff_sample.csv"))
    quarter_start = date(2026, 4, 1)

    result = generate_schedule(
        staff,
        quarter_start,
        vacations=[],
        max_solve_time_seconds=30,
        random_seed=42,
    )
    assert result.success
    schedule = result.get_best_schedule()
    val = validate_schedule(schedule, staff)
    assert val.is_valid()
