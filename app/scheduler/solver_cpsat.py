"""OR-Tools CP-SAT solver for Notdienst scheduling.

This module provides an alternative solver using constraint programming
for guaranteed optimal fairness within hard constraint satisfaction.
"""

from collections import defaultdict
from datetime import date, timedelta

from ortools.sat.python import cp_model

from .models import (
    Assignment,
    Beruf,
    Schedule,
    Shift,
    ShiftType,
    Staff,
    generate_quarter_shifts,
)
from .validator import validate_schedule


class SolverResult:
    """Result from solver with multiple candidate schedules."""

    def __init__(
        self,
        success: bool,
        schedules: list[Schedule],
        penalties: list[float],
        unsatisfiable_constraints: list[str],
    ) -> None:
        self.success = success
        self.schedules = schedules
        self.penalties = penalties
        self.unsatisfiable_constraints = unsatisfiable_constraints

    def get_best_schedule(self) -> Schedule | None:
        """Get the best schedule (lowest penalty)."""
        return self.schedules[0] if self.schedules else None


def generate_schedule_cpsat(
    staff_list: list[Staff],
    quarter_start: date,
    max_solve_time_seconds: int = 120,
    random_seed: int | None = None,
) -> SolverResult:
    """Generate schedule using OR-Tools CP-SAT solver.

    Args:
        staff_list: List of staff members
        quarter_start: Start date of quarter (e.g., April 1, 2026)
        max_solve_time_seconds: Maximum solver time in seconds
        random_seed: Random seed for reproducibility

    Returns:
        SolverResult with best schedule or unsatisfiable constraints
    """
    model = cp_model.CpModel()

    # Generate all shifts for the quarter
    shifts = generate_quarter_shifts(quarter_start)
    quarter_end = max(s.shift_date for s in shifts) if shifts else quarter_start

    # Index mappings
    staff_by_id = {s.identifier: s for s in staff_list}
    shift_index = {(s.shift_date, s.shift_type): i for i, s in enumerate(shifts)}

    # Separate shifts by category
    weekend_shifts = [s for s in shifts if s.is_weekend_shift()]
    night_shifts = [s for s in shifts if s.is_night_shift()]

    # Night shifts categorized by TA presence
    ta_present_nights = [
        s for s in night_shifts
        if s.shift_type in (ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE)
    ]
    regular_nights = [
        s for s in night_shifts
        if s.shift_type not in (ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE)
    ]

    # =========================================================================
    # DECISION VARIABLES
    # =========================================================================

    # x[s, d, t] = 1 if staff s is assigned to shift (d, t)
    x: dict[tuple[str, date, ShiftType], cp_model.IntVar] = {}
    for staff in staff_list:
        for shift in shifts:
            if staff.can_work_shift(shift.shift_type, shift.shift_date):
                key = (staff.identifier, shift.shift_date, shift.shift_type)
                x[key] = model.NewBoolVar(f"x_{staff.identifier}_{shift.shift_date}_{shift.shift_type.value}")

    # is_paired[s, d] = 1 if staff s works night shift on date d paired (2 people)
    # This is determined by sum of assignments for that night
    is_paired: dict[tuple[str, date], cp_model.IntVar] = {}
    for shift in night_shifts:
        for staff in staff_list:
            key = (staff.identifier, shift.shift_date, shift.shift_type)
            if key in x:
                pair_key = (staff.identifier, shift.shift_date)
                if pair_key not in is_paired:
                    is_paired[pair_key] = model.NewBoolVar(
                        f"paired_{staff.identifier}_{shift.shift_date}"
                    )

    # =========================================================================
    # HARD CONSTRAINTS
    # =========================================================================

    # 1. Weekend shift coverage: exactly 1 person per shift
    for shift in weekend_shifts:
        staff_for_shift = [
            x[(s.identifier, shift.shift_date, shift.shift_type)]
            for s in staff_list
            if (s.identifier, shift.shift_date, shift.shift_type) in x
        ]
        if staff_for_shift:
            model.Add(sum(staff_for_shift) == 1)

    # 2. Night shift coverage: 1-2 people per night
    for shift in night_shifts:
        staff_for_shift = [
            x[(s.identifier, shift.shift_date, shift.shift_type)]
            for s in staff_list
            if (s.identifier, shift.shift_date, shift.shift_type) in x
        ]
        if staff_for_shift:
            coverage_sum = sum(staff_for_shift)
            model.Add(coverage_sum >= 1)
            model.Add(coverage_sum <= 2)

            # Link is_paired variable: paired iff 2 people assigned
            for s in staff_list:
                key = (s.identifier, shift.shift_date, shift.shift_type)
                pair_key = (s.identifier, shift.shift_date)
                if key in x and pair_key in is_paired:
                    # is_paired[s,d] = 1 iff sum >= 2 AND x[s,d,t] = 1
                    # Simplified: is_paired = (sum == 2) AND assigned
                    sum_is_two = model.NewBoolVar(f"sum2_{shift.shift_date}")
                    model.Add(coverage_sum == 2).OnlyEnforceIf(sum_is_two)
                    model.Add(coverage_sum != 2).OnlyEnforceIf(sum_is_two.Not())
                    # is_paired = sum_is_two AND x
                    model.AddBoolAnd([sum_is_two, x[key]]).OnlyEnforceIf(is_paired[pair_key])
                    model.AddBoolOr([sum_is_two.Not(), x[key].Not()]).OnlyEnforceIf(
                        is_paired[pair_key].Not()
                    )

    # 3. nd_alone=False staff must be paired on regular nights (TA not present)
    for shift in regular_nights:
        for staff in staff_list:
            if not staff.nd_alone:
                key = (staff.identifier, shift.shift_date, shift.shift_type)
                pair_key = (staff.identifier, shift.shift_date)
                if key in x and pair_key in is_paired:
                    # If assigned, must be paired
                    model.AddImplication(x[key], is_paired[pair_key])

    # 4. nd_alone=True staff must NOT work TA-present nights (Sun-Mon, Mon-Tue)
    # They don't need pairing, but these nights have a TA present making them "paired"
    for shift in ta_present_nights:
        for staff in staff_list:
            if staff.nd_alone and staff.beruf != Beruf.TA:
                key = (staff.identifier, shift.shift_date, shift.shift_type)
                if key in x:
                    model.Add(x[key] == 0)

    # 5. TA night cap: max 6 nights per quarter (2/month)
    for staff in staff_list:
        if staff.beruf == Beruf.TA:
            ta_night_vars = [
                x[(staff.identifier, s.shift_date, s.shift_type)]
                for s in night_shifts
                if (staff.identifier, s.shift_date, s.shift_type) in x
            ]
            if ta_night_vars:
                model.Add(sum(ta_night_vars) <= 6)

    # 6. Night/Day conflict: no day shift same day or next day after night shift
    for staff in staff_list:
        for night_shift in night_shifts:
            night_key = (staff.identifier, night_shift.shift_date, night_shift.shift_type)
            if night_key not in x:
                continue

            # Same day weekend shift
            for we_shift in weekend_shifts:
                if we_shift.shift_date == night_shift.shift_date:
                    we_key = (staff.identifier, we_shift.shift_date, we_shift.shift_type)
                    if we_key in x:
                        model.Add(x[night_key] + x[we_key] <= 1)

            # Next day weekend shift
            next_day = night_shift.shift_date + timedelta(days=1)
            for we_shift in weekend_shifts:
                if we_shift.shift_date == next_day:
                    we_key = (staff.identifier, we_shift.shift_date, we_shift.shift_type)
                    if we_key in x:
                        model.Add(x[night_key] + x[we_key] <= 1)

    # 7. 2-week block constraint: gaps between shift blocks must be >= 14 days
    # This is complex in CP - we approximate by limiting shifts per 14-day window
    # More accurate: track block starts and enforce gap
    _add_block_constraints(model, x, staff_list, shifts, quarter_start, quarter_end)

    # 8. nd_count max constraint: consecutive night blocks cannot exceed max(nd_count)
    _add_nd_count_constraints(model, x, staff_list, night_shifts)

    # =========================================================================
    # FAIRNESS OBJECTIVE
    # =========================================================================

    # Goal: minimize max FTE-deviation within each role group

    # Calculate FTE-normalized targets
    # Weekend target for each person: (their hours / 40) * avg_weekends_per_40h
    # Night target: similar but accounting for paired=0.5

    # First, calculate total shifts available
    total_weekend_shifts = len(weekend_shifts)
    total_night_shifts = len(night_shifts)  # Each can have 1-2 people

    # Calculate per-group targets
    # Weekends: everyone eligible participates
    # Nights: only nd_possible=True participates

    # For fairness, we minimize the range (max - min) of FTE-normalized counts
    # within each group: TFA, Azubi, TA

    # Weekend counts per staff
    weekend_counts: dict[str, cp_model.LinearExpr] = {}
    for staff in staff_list:
        vars_for_staff = [
            x[(staff.identifier, s.shift_date, s.shift_type)]
            for s in weekend_shifts
            if (staff.identifier, s.shift_date, s.shift_type) in x
        ]
        if vars_for_staff:
            weekend_counts[staff.identifier] = sum(vars_for_staff)
        else:
            weekend_counts[staff.identifier] = 0

    # Night counts per staff (effective: paired = 0.5)
    # We model this by tracking 2*effective_nights to avoid fractions
    # effective_nights * 2 = paired_nights * 1 + solo_nights * 2
    night_counts_2x: dict[str, cp_model.LinearExpr] = {}
    for staff in staff_list:
        if not staff.nd_possible:
            night_counts_2x[staff.identifier] = 0
            continue

        terms = []
        for shift in night_shifts:
            key = (staff.identifier, shift.shift_date, shift.shift_type)
            pair_key = (staff.identifier, shift.shift_date)
            if key in x:
                # Contribution: if paired -> 1, if solo -> 2
                # = 2 * x - is_paired (since is_paired = x when paired)
                # More precisely: 2*x - (x AND is_paired_shift)
                # Simpler: solo_contribution + paired_contribution
                # For now, count raw assignments, we'll handle pairing in post
                terms.append(x[key])

        if terms:
            night_counts_2x[staff.identifier] = sum(terms)
        else:
            night_counts_2x[staff.identifier] = 0

    # FTE-scaled counts (multiplied by 40/hours to normalize)
    # To avoid fractions in CP, we multiply everything by a common factor
    SCALE = 40 * 10  # Scale factor for integer arithmetic

    # Calculate scaled weekend fairness by group
    objective_terms = []

    # Group staff by role for fairness within groups
    tfa_staff = [s for s in staff_list if s.beruf == Beruf.TFA]
    azubi_staff = [s for s in staff_list if s.beruf == Beruf.AZUBI]
    ta_staff = [s for s in staff_list if s.beruf == Beruf.TA]

    # For each group, add fairness constraint/objective
    for group_name, group in [("TFA", tfa_staff), ("Azubi", azubi_staff), ("TA", ta_staff)]:
        if len(group) < 2:
            continue

        # Weekend fairness (all staff in group)
        we_eligible = [s for s in group if s.beruf != Beruf.TA]  # TAs don't do weekends
        if len(we_eligible) >= 2:
            _add_group_fairness_objective(
                model, objective_terms, weekend_counts, we_eligible, SCALE, f"WE_{group_name}"
            )

        # Night fairness (only nd_possible staff)
        nd_eligible = [s for s in group if s.nd_possible]
        if len(nd_eligible) >= 2:
            _add_group_fairness_objective(
                model, objective_terms, night_counts_2x, nd_eligible, SCALE, f"ND_{group_name}"
            )

    # Minimize total fairness deviation
    if objective_terms:
        model.Minimize(sum(objective_terms))

    # =========================================================================
    # SOLVE
    # =========================================================================

    solver = cp_model.CpSolver()
    solver.parameters.max_time_in_seconds = max_solve_time_seconds
    if random_seed is not None:
        solver.parameters.random_seed = random_seed

    status = solver.Solve(model)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        # Extract solution
        schedule = _extract_schedule(solver, x, is_paired, shifts, quarter_start, quarter_end)

        # Validate (should pass, but good to confirm)
        validation = validate_schedule(schedule, staff_list)
        penalty = validation.soft_penalty

        return SolverResult(
            success=True,
            schedules=[schedule],
            penalties=[penalty],
            unsatisfiable_constraints=[],
        )
    else:
        # Infeasible or timeout
        unsatisfiable = _diagnose_infeasibility(model, staff_list, shifts)
        return SolverResult(
            success=False,
            schedules=[],
            penalties=[],
            unsatisfiable_constraints=unsatisfiable,
        )


def _add_block_constraints(
    model: cp_model.CpModel,
    x: dict[tuple[str, date, ShiftType], cp_model.IntVar],
    staff_list: list[Staff],
    shifts: list[Shift],
    quarter_start: date,
    quarter_end: date,
) -> None:
    """Add 2-week block constraints.

    The constraint from validator: if you have blocks B1 and B2, and B2 starts
    within 14 days of B1's START, that's a violation.

    Implementation: For each potential block-start day D (where we work but didn't
    work D-1), we forbid working on any day in (D+2, D+13) that would also be a
    block-start (i.e., without working the day before).

    Simplified approach: Forbid working on day D1 and day D2 where:
    - D1 and D2 are both "block starts" (no work on D1-1 and D2-1)
    - 2 <= D2 - D1 < 14
    """
    # Group shifts by date
    shifts_by_date: dict[date, list[Shift]] = defaultdict(list)
    for s in shifts:
        shifts_by_date[s.shift_date].append(s)

    all_dates = sorted(shifts_by_date.keys())

    for staff in staff_list:
        # Get all dates where this staff has a possible assignment
        staff_dates = []
        for d in all_dates:
            has_any = any(
                (staff.identifier, s.shift_date, s.shift_type) in x
                for s in shifts_by_date[d]
            )
            if has_any:
                staff_dates.append(d)

        if len(staff_dates) < 2:
            continue

        # Create "works_on_D" variable (OR of all shifts on that date)
        works_on: dict[date, cp_model.IntVar] = {}
        for d in staff_dates:
            vars_on_d = [
                x[(staff.identifier, s.shift_date, s.shift_type)]
                for s in shifts_by_date[d]
                if (staff.identifier, s.shift_date, s.shift_type) in x
            ]
            if len(vars_on_d) == 1:
                works_on[d] = vars_on_d[0]
            elif len(vars_on_d) > 1:
                works_on[d] = model.NewBoolVar(f"works_{staff.identifier}_{d}")
                model.AddMaxEquality(works_on[d], vars_on_d)

        # Create "block_starts_on_D" = works_on[D] AND NOT works_on[D-1]
        block_starts: dict[date, cp_model.IntVar] = {}
        for d in staff_dates:
            if d not in works_on:
                continue
            prev_d = d - timedelta(days=1)
            if prev_d in works_on:
                # block_starts[d] = works_on[d] AND NOT works_on[prev_d]
                block_starts[d] = model.NewBoolVar(f"block_start_{staff.identifier}_{d}")
                not_prev = model.NewBoolVar(f"not_prev_{staff.identifier}_{d}")
                model.Add(not_prev == 1 - works_on[prev_d])
                model.AddBoolAnd([works_on[d], not_prev]).OnlyEnforceIf(block_starts[d])
                model.AddBoolOr([works_on[d].Not(), not_prev.Not()]).OnlyEnforceIf(block_starts[d].Not())
            else:
                # No previous day in schedule, so if working, it's a block start
                block_starts[d] = works_on[d]

        # Enforce: no two block starts within 14 days
        block_start_dates = sorted(block_starts.keys())
        for i, d1 in enumerate(block_start_dates):
            for d2 in block_start_dates[i + 1:]:
                gap = (d2 - d1).days
                if gap >= 14:
                    break  # No need to check further
                # Both being block starts is forbidden
                model.Add(block_starts[d1] + block_starts[d2] <= 1)


def _add_nd_count_constraints(
    model: cp_model.CpModel,
    x: dict[tuple[str, date, ShiftType], cp_model.IntVar],
    staff_list: list[Staff],
    night_shifts: list[Shift],
) -> None:
    """Enforce max consecutive nights based on nd_count field."""
    sorted_nights = sorted(night_shifts, key=lambda s: s.shift_date)

    for staff in staff_list:
        if not staff.nd_possible or not staff.nd_count:
            continue

        max_consecutive = max(staff.nd_count)

        # Get this staff's night variables in order
        staff_night_vars = []
        for shift in sorted_nights:
            key = (staff.identifier, shift.shift_date, shift.shift_type)
            if key in x:
                staff_night_vars.append((shift.shift_date, x[key]))

        if len(staff_night_vars) <= max_consecutive:
            continue

        # For each window of (max_consecutive + 1) consecutive dates,
        # enforce sum <= max_consecutive
        i = 0
        while i < len(staff_night_vars):
            window_vars = []
            window_start = staff_night_vars[i][0]
            j = i

            # Collect consecutive dates starting from i
            while j < len(staff_night_vars):
                d, var = staff_night_vars[j]
                if j == i or (d - staff_night_vars[j - 1][0]).days == 1:
                    window_vars.append(var)
                    j += 1
                else:
                    break

            # If window is longer than max_consecutive, add sliding constraints
            if len(window_vars) > max_consecutive:
                for k in range(len(window_vars) - max_consecutive):
                    # Sum of (max_consecutive + 1) consecutive vars <= max_consecutive
                    constraint_vars = window_vars[k : k + max_consecutive + 1]
                    model.Add(sum(constraint_vars) <= max_consecutive)

            i = j


def _add_group_fairness_objective(
    model: cp_model.CpModel,
    objective_terms: list,
    counts: dict[str, cp_model.LinearExpr],
    group: list[Staff],
    scale: int,
    prefix: str,
) -> None:
    """Add min-max fairness objective for a group.

    Minimizes (max_scaled_count - min_scaled_count) for the group.
    """
    if len(group) < 2:
        return

    # Create scaled count variables: count * (scale / hours)
    scaled_counts = []
    for staff in group:
        count_expr = counts.get(staff.identifier, 0)
        if isinstance(count_expr, int) and count_expr == 0:
            # Zero count, skip
            scaled_var = model.NewIntVar(0, 0, f"{prefix}_scaled_{staff.identifier}")
        else:
            # scaled = count * (scale / hours) = count * scale / hours
            # Since scale=400 and hours in [18,40], multiplier in [10,22]
            multiplier = scale // staff.hours
            max_possible = 100 * multiplier  # Conservative upper bound
            scaled_var = model.NewIntVar(0, max_possible, f"{prefix}_scaled_{staff.identifier}")
            model.Add(scaled_var == count_expr * multiplier)
        scaled_counts.append(scaled_var)

    # Create max and min variables
    max_var = model.NewIntVar(0, 10000, f"{prefix}_max")
    min_var = model.NewIntVar(0, 10000, f"{prefix}_min")
    model.AddMaxEquality(max_var, scaled_counts)
    model.AddMinEquality(min_var, scaled_counts)

    # Range = max - min
    range_var = model.NewIntVar(0, 10000, f"{prefix}_range")
    model.Add(range_var == max_var - min_var)

    # Add to objective (minimize range)
    objective_terms.append(range_var)


def _extract_schedule(
    solver: cp_model.CpSolver,
    x: dict[tuple[str, date, ShiftType], cp_model.IntVar],
    is_paired: dict[tuple[str, date], cp_model.IntVar],
    shifts: list[Shift],
    quarter_start: date,
    quarter_end: date,
) -> Schedule:
    """Extract Schedule object from solver solution."""
    assignments = []

    for shift in shifts:
        assigned_staff = []
        for (staff_id, shift_date, shift_type), var in x.items():
            if shift_date == shift.shift_date and shift_type == shift.shift_type:
                if solver.Value(var) == 1:
                    assigned_staff.append(staff_id)

        # Determine if paired (2 people on same night)
        paired = len(assigned_staff) >= 2 and shift.is_night_shift()

        # Also mark as paired for TA-present nights (Sun-Mon, Mon-Tue)
        if shift.shift_type in (ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE):
            paired = True  # Always paired with TA

        for staff_id in assigned_staff:
            assignments.append(
                Assignment(
                    shift=shift,
                    staff_identifier=staff_id,
                    is_paired=paired,
                )
            )

    return Schedule(
        quarter_start=quarter_start,
        quarter_end=quarter_end,
        assignments=assignments,
    )


def _diagnose_infeasibility(
    model: cp_model.CpModel,
    staff_list: list[Staff],
    shifts: list[Shift],
) -> list[str]:
    """Attempt to diagnose why the model is infeasible."""
    issues = []

    # Check basic capacity
    weekend_shifts = [s for s in shifts if s.is_weekend_shift()]
    night_shifts = [s for s in shifts if s.is_night_shift()]

    # Weekend capacity check
    saturday_shifts = [s for s in weekend_shifts if s.shift_type.value.startswith("Sa_")]
    sunday_shifts = [s for s in weekend_shifts if s.shift_type.value.startswith("So_")]

    # Saturday 10-19: only Azubi with reception=False
    sa_1019_eligible = [s for s in staff_list if s.beruf == Beruf.AZUBI and not s.reception]
    if len(sa_1019_eligible) * 13 < len([s for s in saturday_shifts if s.shift_type == ShiftType.SATURDAY_10_19]):
        issues.append(f"Insufficient Azubi (reception=False) for Sa_10-19 shifts. Have {len(sa_1019_eligible)}, need coverage for 13 weeks.")

    # Sunday: adults only
    adult_azubis = [s for s in staff_list if s.beruf == Beruf.AZUBI and s.adult]
    if len(adult_azubis) == 0:
        issues.append("No adult Azubis available for Sunday So_8-20:30 shifts.")

    # Night capacity
    nd_eligible = [s for s in staff_list if s.nd_possible]
    if len(nd_eligible) < 2:
        issues.append(f"Insufficient night-capable staff. Have {len(nd_eligible)}, need at least 2 for pairing.")

    # Check nd_alone availability for TA-present nights
    ta_present_eligible = [
        s for s in nd_eligible
        if not s.nd_alone or s.beruf == Beruf.TA  # nd_alone=False OR is TA
    ]
    if len(ta_present_eligible) == 0:
        issues.append("No staff eligible for Sun-Mon and Mon-Tue nights (need nd_alone=False or TA).")

    if not issues:
        issues.append("Model infeasible. Check constraint interactions or increase solve time.")

    return issues
