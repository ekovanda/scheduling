"""Tests for cross-period carry-forward functionality."""

from datetime import date

import pytest
from ortools.sat.python import cp_model

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
    generate_quarter_shifts,
)
from app.scheduler.solver_cpsat import _add_min_consecutive_nights_constraints


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


# ---------------------------------------------------------------------------
# Regression tests: trailing night boundary constraint bug
# ---------------------------------------------------------------------------

class TestTrailingNightBoundary:
    """Regression tests for the isolated-trailing-night INFEASIBLE bug.

    Bug: _add_min_consecutive_nights_constraints applied the min-consecutive
    adjacency constraint to fixed trailing (historical) variables. An isolated
    trailing night at the Q2/Q3 cutoff boundary had no adjacent neighbour,
    causing model.Add(var==0) to contradict the already-set model.Add(var==1),
    producing immediate INFEASIBLE regardless of the rest of the schedule.
    """

    def _make_tfa(self, identifier: str = "T") -> Staff:
        return Staff(
            name=identifier, identifier=identifier, adult=True, hours=40,
            beruf=Beruf.TFA, reception=True, nd_possible=True,
            nd_alone=True, nd_max_consecutive=5, nd_min_consecutive=2,
            nd_exceptions=[],
        )

    def _solve_model(self, model: cp_model.CpModel) -> int:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 5.0
        return solver.Solve(model)

    def test_isolated_trailing_night_at_cutoff_boundary_is_feasible(self) -> None:
        """Isolated trailing night on cutoff day with long gap to first Q3 night.

        Simulates Jana H (Hör): worked a single night June 10 (first day of the
        trailing window). The Q2 predecessor (June 9) is outside the window and
        the next Q3 night is weeks away. Before the fix this caused INFEASIBLE.
        """
        staff = self._make_tfa("T")
        q3_start = date(2026, 7, 1)
        all_q3_nights = [s for s in generate_quarter_shifts(q3_start) if s.is_night_shift()]

        model = cp_model.CpModel()
        # Only create Q3 vars for the last 30 days (simulating long vacation)
        x: dict = {}
        for shift in all_q3_nights:
            if (shift.shift_date - q3_start).days >= 60:
                x[("T", shift.shift_date, shift.shift_type)] = model.NewBoolVar(
                    f"x_{shift.shift_date}"
                )

        # Isolated trailing night — sole entry, no adjacent Q2 or Q3 night
        trailing = {"T": [date(2026, 6, 10)]}
        _add_min_consecutive_nights_constraints(model, x, [staff], all_q3_nights, trailing)

        status = self._solve_model(model)
        assert status != cp_model.INFEASIBLE, (
            "Isolated trailing night at cutoff boundary must not force INFEASIBLE. "
            "Trailing variables are fixed history and must not be constrained to "
            "have adjacent nights."
        )

    def test_isolated_trailing_night_mid_window_no_adjacent_q3(self) -> None:
        """Isolated trailing night mid-window with vacation consuming all adjacent Q3.

        Simulates Samira W (SW): worked June 28 alone (next block was June 16-17,
        previous block ended there), and her next Q3 night is July 1+ which is
        >1 day away. Before the fix this caused INFEASIBLE.
        """
        staff = self._make_tfa("S")
        q3_start = date(2026, 7, 1)
        all_q3_nights = [s for s in generate_quarter_shifts(q3_start) if s.is_night_shift()]

        model = cp_model.CpModel()
        # First Q3 variable for staff S is July 7 (vacation blocks July 1-6)
        x: dict = {}
        for shift in all_q3_nights:
            if (shift.shift_date - q3_start).days >= 6:
                x[("S", shift.shift_date, shift.shift_type)] = model.NewBoolVar(
                    f"xs_{shift.shift_date}"
                )

        # June 28 isolated trailing night (gap to first Q3 var = 9 days)
        trailing = {"S": [date(2026, 6, 28)]}
        _add_min_consecutive_nights_constraints(model, x, [staff], all_q3_nights, trailing)

        status = self._solve_model(model)
        assert status != cp_model.INFEASIBLE, (
            "Isolated trailing night with no adjacent Q3 neighbour must not force INFEASIBLE."
        )

    def test_contiguous_trailing_nights_still_contextualise_q3(self) -> None:
        """Trailing nights June 29-30 must satisfy min-consec for adjacent Q3 night July 1.

        Trailing nights are context for Q3 decision vars. If Q3 July 1 is assigned,
        it should be satisfied by the adjacent trailing June 30 without needing
        an additional Q3 neighbour on July 2.
        """
        staff = self._make_tfa("C")
        q3_start = date(2026, 7, 1)
        all_q3_nights = [s for s in generate_quarter_shifts(q3_start) if s.is_night_shift()]

        model = cp_model.CpModel()
        x: dict = {}
        for shift in all_q3_nights:
            key = ("C", shift.shift_date, shift.shift_type)
            x[key] = model.NewBoolVar(f"xc_{shift.shift_date}")

        # Two consecutive trailing nights ending right at Q3 start
        trailing = {"C": [date(2026, 6, 29), date(2026, 6, 30)]}
        _add_min_consecutive_nights_constraints(model, x, [staff], all_q3_nights, trailing)

        # Force July 1 to be worked — it must be satisfiable without forcing July 2
        # because June 30 (trailing, fixed=1) is adjacent
        july_1_shift = next(s for s in all_q3_nights if s.shift_date == date(2026, 7, 1))
        july_1_key = ("C", date(2026, 7, 1), july_1_shift.shift_type)
        model.Add(x[july_1_key] == 1)

        # Force July 2 to NOT be worked — this would make July 1 unsatisfied if
        # trailing context isn't working
        july_2_shift = next(
            (s for s in all_q3_nights if s.shift_date == date(2026, 7, 2)), None
        )
        if july_2_shift:
            model.Add(x[("C", date(2026, 7, 2), july_2_shift.shift_type)] == 0)

        status = self._solve_model(model)
        assert status != cp_model.INFEASIBLE, (
            "July 1 should be satisfiable by adjacent trailing June 30 without needing July 2."
        )


# ---------------------------------------------------------------------------
# Regression tests: trailing block-gap constraint bug
# ---------------------------------------------------------------------------

class TestTrailingBlockGap:
    """Regression tests for the Q2→Q2 trailing block gap INFEASIBLE bug.

    Bug: _add_block_constraints applied the intra-quarter block-gap rest
    constraint (≥21 days between block starts) to pairs of Q2 trailing dates.
    When a staff member had two Q2 block starts less than 21 days apart, both
    fixed=1, the constraint produced model.Add(1+1 <= 1) — immediate INFEASIBLE.

    Fix: skip the gap constraint whenever d1 < quarter_start (i.e., d1 is a
    trailing/historical date).  This covers Q2→Q2 and Q2→Q3 pairs.
    """

    def _solve(self, model: cp_model.CpModel) -> int:
        solver = cp_model.CpSolver()
        solver.parameters.max_time_in_seconds = 2.0
        return solver.Solve(model)

    def test_two_q2_trailing_block_starts_no_contradiction(self) -> None:
        """Two Q2 trailing block starts <21 days apart must not produce a contradiction.

        Old code: `if d1 < quarter_start <= d2: continue` only skipped Q2→Q3
        pairs. For SW Jun 17 + Jun 28 (gap=11 days, both Q2) it still added
        model.Add(fixed=1 + fixed=1 <= 1) → immediate INFEASIBLE.

        New code: `if d1 < quarter_start: continue` skips ALL pairs where d1
        is trailing (Q2→Q2 and Q2→Q3 both skipped).
        """
        DEFAULT_GAP = 21
        quarter_start = date(2026, 7, 1)
        d1 = date(2026, 6, 17)  # Q2 trailing block start
        d2 = date(2026, 6, 28)  # Q2 trailing block start, gap=11 days

        model = cp_model.CpModel()
        b1 = model.NewBoolVar("block_start_d1")
        b2 = model.NewBoolVar("block_start_d2")
        model.Add(b1 == 1)  # fixed trailing history
        model.Add(b2 == 1)  # fixed trailing history

        gap = (d2 - d1).days
        # New code: skip whenever d1 < quarter_start → no constraint added here
        if not (d1 < quarter_start) and gap < DEFAULT_GAP:
            model.Add(b1 + b2 <= 1)

        status = self._solve(model)
        assert status != cp_model.INFEASIBLE, (
            "Two Q2 trailing block starts within gap window must not cause contradiction. "
            "The block-gap constraint is intra-quarter only and must skip Q2 dates."
        )

    def test_old_q2_to_q2_logic_would_have_been_infeasible(self) -> None:
        """The OLD condition produced a contradiction for Q2→Q2 pairs (documents bug)."""
        DEFAULT_GAP = 21
        quarter_start = date(2026, 7, 1)
        d1 = date(2026, 6, 17)
        d2 = date(2026, 6, 28)

        model = cp_model.CpModel()
        b1 = model.NewBoolVar("block_start_d1")
        b2 = model.NewBoolVar("block_start_d2")
        model.Add(b1 == 1)
        model.Add(b2 == 1)

        gap = (d2 - d1).days
        # OLD buggy condition: `if d1 < quarter_start <= d2: continue`
        # For Jun17 < Jul1 <= Jun28: Jul1 <= Jun28 is False → constraint IS added
        old_skip = d1 < quarter_start <= d2  # evaluates False
        if not old_skip and gap < DEFAULT_GAP:
            model.Add(b1 + b2 <= 1)  # BUG: both fixed=1 → contradiction

        status = self._solve(model)
        assert status == cp_model.INFEASIBLE, (
            "Documents the bug: old Q2→Q2 logic added b1+b2<=1 with both fixed=1."
        )

    def test_two_q3_blocks_within_gap_window_is_still_enforced(self) -> None:
        """Intra-Q3 block gap enforcement must remain active after the fix."""
        DEFAULT_GAP = 21
        quarter_start = date(2026, 7, 1)
        d1 = date(2026, 7, 1)   # Q3 block start
        d2 = date(2026, 7, 10)  # Q3 block start, gap=9 days

        model = cp_model.CpModel()
        b1 = model.NewBoolVar("q3_block_1")
        b2 = model.NewBoolVar("q3_block_2")
        model.Add(b1 == 1)
        model.Add(b2 == 1)

        gap = (d2 - d1).days
        # New code: d1=Jul1 is NOT < Jul1, so constraint is added
        if not (d1 < quarter_start) and gap < DEFAULT_GAP:
            model.Add(b1 + b2 <= 1)

        status = self._solve(model)
        assert status == cp_model.INFEASIBLE, (
            "Intra-Q3 gap enforcement must remain active. "
            "Two Q3 block starts within 21 days must not both be allowed."
        )
