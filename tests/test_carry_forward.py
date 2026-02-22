"""Tests for cross-period carry-forward functionality."""

from datetime import date

import pytest

from app.scheduler.models import (
    Assignment,
    Beruf,
    CarryForwardEntry,
    PreviousPlanContext,
    Schedule,
    Shift,
    ShiftType,
    Staff,
    TrailingAssignment,
    Vacation,
    build_previous_context,
    compute_carry_forward,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_staff(
    identifier: str,
    beruf: Beruf = Beruf.TFA,
    hours: int = 40,
    name: str | None = None,
    nd_possible: bool = True,
) -> Staff:
    return Staff(
        name=name or identifier,
        identifier=identifier,
        adult=True,
        hours=hours,
        beruf=beruf,
        reception=True,
        nd_possible=nd_possible,
        nd_alone=False,
        nd_max_consecutive=3,
        nd_exceptions=[],
    )


def _make_schedule(
    assignments: list[Assignment],
    quarter_start: date = date(2026, 4, 1),
    quarter_end: date = date(2026, 6, 30),
) -> Schedule:
    return Schedule(
        quarter_start=quarter_start,
        quarter_end=quarter_end,
        assignments=assignments,
    )


def _night_assignment(
    identifier: str, shift_date: date, is_paired: bool = False,
) -> Assignment:
    """Create a night assignment on a given date."""
    # Pick correct shift type based on weekday
    weekday = shift_date.isoweekday()
    shift_types = {
        1: ShiftType.NIGHT_MON_TUE,
        2: ShiftType.NIGHT_TUE_WED,
        3: ShiftType.NIGHT_WED_THU,
        4: ShiftType.NIGHT_THU_FRI,
        5: ShiftType.NIGHT_FRI_SAT,
        6: ShiftType.NIGHT_SAT_SUN,
        7: ShiftType.NIGHT_SUN_MON,
    }
    shift_type = shift_types[weekday]
    return Assignment(
        shift=Shift(shift_type=shift_type, shift_date=shift_date),
        staff_identifier=identifier,
        is_paired=is_paired,
    )


def _weekend_assignment(identifier: str, shift_date: date) -> Assignment:
    return Assignment(
        shift=Shift(shift_type=ShiftType.SATURDAY_10_22, shift_date=shift_date),
        staff_identifier=identifier,
        is_paired=False,
    )


# ---------------------------------------------------------------------------
# Tests: compute_carry_forward
# ---------------------------------------------------------------------------

class TestComputeCarryForward:
    """Tests for the compute_carry_forward function."""

    def test_equal_load_gives_zero_deltas(self) -> None:
        """Two TFA with identical loads should both have delta ~0."""
        staff = [_make_staff("A"), _make_staff("B")]
        assignments = [
            _weekend_assignment("A", date(2026, 4, 4)),
            _weekend_assignment("B", date(2026, 4, 11)),
        ]
        schedule = _make_schedule(assignments)
        carry = compute_carry_forward(schedule, staff)

        for entry in carry:
            assert abs(entry.carry_forward_delta) < 0.01, (
                f"{entry.identifier} has non-zero delta {entry.carry_forward_delta}"
            )

    def test_unequal_load_creates_opposite_deltas(self) -> None:
        """If A does 2 WE and B does 0, A should have positive delta, B negative."""
        staff = [_make_staff("A"), _make_staff("B")]
        assignments = [
            _weekend_assignment("A", date(2026, 4, 4)),
            _weekend_assignment("A", date(2026, 4, 11)),
        ]
        schedule = _make_schedule(assignments)
        carry = compute_carry_forward(schedule, staff)

        deltas = {e.identifier: e.carry_forward_delta for e in carry}
        assert deltas["A"] > 0, "A should have positive delta (did more)"
        assert deltas["B"] < 0, "B should have negative delta (did less)"
        # Sum of deltas within group should be ~0
        assert abs(deltas["A"] + deltas["B"]) < 0.01

    def test_fte_normalization(self) -> None:
        """20h staff doing 1 WE should have higher norm_40h than 40h staff doing 1 WE."""
        staff = [_make_staff("A", hours=40), _make_staff("B", hours=20)]
        assignments = [
            _weekend_assignment("A", date(2026, 4, 4)),
            _weekend_assignment("B", date(2026, 4, 11)),
        ]
        schedule = _make_schedule(assignments)
        carry = compute_carry_forward(schedule, staff)

        norms = {e.identifier: e.normalized_40h for e in carry}
        assert norms["B"] > norms["A"], (
            "20h staff doing same shifts should have higher Norm./40h"
        )

    def test_groups_are_independent(self) -> None:
        """TFA delta should not be affected by Azubi assignments."""
        staff = [
            _make_staff("T1", beruf=Beruf.TFA),
            _make_staff("T2", beruf=Beruf.TFA),
            _make_staff("AZ", beruf=Beruf.AZUBI),
        ]
        assignments = [
            _weekend_assignment("T1", date(2026, 4, 4)),
            _weekend_assignment("T2", date(2026, 4, 4)),
            # Azubi does many WE
            _weekend_assignment("AZ", date(2026, 4, 4)),
            _weekend_assignment("AZ", date(2026, 4, 11)),
            _weekend_assignment("AZ", date(2026, 4, 18)),
        ]
        schedule = _make_schedule(assignments)
        carry = compute_carry_forward(schedule, staff)

        tfa_deltas = [e for e in carry if e.beruf == "TFA"]
        for entry in tfa_deltas:
            assert abs(entry.carry_forward_delta) < 0.01

    def test_presence_adjustment_with_vacation(self) -> None:
        """Staff on vacation should have higher norm_40h per actual shift."""
        staff = [_make_staff("A"), _make_staff("B")]
        vacations = [Vacation(identifier="B", start_date=date(2026, 4, 1), end_date=date(2026, 5, 15))]
        assignments = [
            _weekend_assignment("A", date(2026, 5, 23)),
            _weekend_assignment("B", date(2026, 5, 23)),
        ]
        schedule = _make_schedule(assignments)
        carry = compute_carry_forward(schedule, staff, vacations)

        norms = {e.identifier: e.normalized_40h for e in carry}
        # B had same raw count but fewer available days → higher normalized
        assert norms["B"] > norms["A"]


# ---------------------------------------------------------------------------
# Tests: build_previous_context
# ---------------------------------------------------------------------------

class TestBuildPreviousContext:
    """Tests for build_previous_context."""

    def test_trailing_assignments_within_window(self) -> None:
        """Only assignments in the last 21 days should be trailing."""
        staff = [_make_staff("A")]
        assignments = [
            _night_assignment("A", date(2026, 6, 5)),   # 25 days before end → excluded
            _night_assignment("A", date(2026, 6, 15)),  # 15 days before end → included
            _night_assignment("A", date(2026, 6, 28)),  # 2 days before end → included
        ]
        schedule = _make_schedule(assignments)
        ctx = build_previous_context(schedule, staff, trailing_days=21)

        trailing_dates = {ta.shift_date for ta in ctx.trailing_assignments}
        assert date(2026, 6, 5) not in trailing_dates
        assert date(2026, 6, 15) in trailing_dates
        assert date(2026, 6, 28) in trailing_dates

    def test_context_json_roundtrip(self) -> None:
        """Context should survive JSON serialization and deserialization."""
        staff = [_make_staff("A"), _make_staff("B")]
        assignments = [
            _weekend_assignment("A", date(2026, 6, 27)),
            _night_assignment("B", date(2026, 6, 29), is_paired=True),
        ]
        schedule = _make_schedule(assignments)
        ctx = build_previous_context(schedule, staff)

        json_str = ctx.model_dump_json()
        restored = PreviousPlanContext.model_validate_json(json_str)

        assert restored.quarter_start == ctx.quarter_start
        assert len(restored.carry_forward) == len(ctx.carry_forward)
        assert len(restored.trailing_assignments) == len(ctx.trailing_assignments)
        for orig, rest in zip(ctx.carry_forward, restored.carry_forward):
            assert orig.identifier == rest.identifier
            assert abs(orig.carry_forward_delta - rest.carry_forward_delta) < 0.001


# ---------------------------------------------------------------------------
# Tests: solver carry-forward integration
# ---------------------------------------------------------------------------

class TestSolverCarryForward:
    """Integration tests verifying carry-forward plumbing in the solver."""

    def test_solver_accepts_previous_context(self) -> None:
        """Solver should not crash when previous_context is provided."""
        from app.scheduler.solver import generate_schedule

        ctx = PreviousPlanContext(
            quarter_start=date(2026, 1, 1),
            quarter_end=date(2026, 3, 31),
            carry_forward=[
                CarryForwardEntry(
                    identifier="AA",
                    name="A A",
                    beruf="TFA",
                    hours=40,
                    effective_nights=3.0,
                    weekend_shifts=2,
                    total_notdienst=5.0,
                    normalized_40h=5.0,
                    group_mean_40h=5.0,
                    carry_forward_delta=0.0,
                ),
            ],
            trailing_assignments=[],
        )

        # Minimal staff list for a solvable instance (smoke test)
        staff_list = _build_minimal_staff()

        # Very short time limit — we just check it doesn't raise
        result = generate_schedule(
            staff_list,
            date(2026, 4, 1),
            max_solve_time_seconds=10,
            random_seed=42,
            previous_context=ctx,
        )
        # We don't assert success (may timeout on CI), just no exception
        assert result is not None

    def test_solver_runs_without_previous_context(self) -> None:
        """Backward compat: solver works fine when previous_context is None."""
        from app.scheduler.solver import generate_schedule

        staff_list = _build_minimal_staff()

        result = generate_schedule(
            staff_list,
            date(2026, 4, 1),
            max_solve_time_seconds=10,
            random_seed=42,
            previous_context=None,
        )
        assert result is not None


def _build_minimal_staff() -> list[Staff]:
    """Build a minimal staff list that can produce a feasible schedule."""
    return [
        Staff(
            name="TFA One", identifier="T1", adult=True, hours=40,
            beruf=Beruf.TFA, reception=True, nd_possible=True,
            nd_alone=True, nd_max_consecutive=5, nd_min_consecutive=2,
            nd_exceptions=[],
        ),
        Staff(
            name="TFA Two", identifier="T2", adult=True, hours=40,
            beruf=Beruf.TFA, reception=True, nd_possible=True,
            nd_alone=False, nd_max_consecutive=5, nd_min_consecutive=2,
            nd_exceptions=[],
        ),
        Staff(
            name="TFA Three", identifier="T3", adult=True, hours=40,
            beruf=Beruf.TFA, reception=True, nd_possible=True,
            nd_alone=False, nd_max_consecutive=5, nd_min_consecutive=2,
            nd_exceptions=[],
        ),
        Staff(
            name="TFA Four", identifier="T4", adult=True, hours=40,
            beruf=Beruf.TFA, reception=True, nd_possible=True,
            nd_alone=True, nd_max_consecutive=5, nd_min_consecutive=2,
            nd_exceptions=[],
        ),
        Staff(
            name="Azubi One", identifier="AZ1", adult=True, hours=40,
            beruf=Beruf.AZUBI, reception=True, nd_possible=True,
            nd_alone=False, nd_max_consecutive=3, nd_min_consecutive=1,
            nd_exceptions=[],
        ),
        Staff(
            name="Azubi Two", identifier="AZ2", adult=True, hours=40,
            beruf=Beruf.AZUBI, reception=True, nd_possible=True,
            nd_alone=False, nd_max_consecutive=3, nd_min_consecutive=1,
            nd_exceptions=[],
        ),
        Staff(
            name="Intern One", identifier="IN1", adult=True, hours=40,
            beruf=Beruf.INTERN, reception=False, nd_possible=True,
            nd_alone=False, nd_max_consecutive=3, nd_min_consecutive=2,
            nd_exceptions=[],
        ),
        Staff(
            name="Intern Two", identifier="IN2", adult=True, hours=40,
            beruf=Beruf.INTERN, reception=False, nd_possible=True,
            nd_alone=False, nd_max_consecutive=3, nd_min_consecutive=2,
            nd_exceptions=[],
        ),
    ]
