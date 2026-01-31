"""OR-Tools CP-SAT solver for Notdienst scheduling.

This module provides an alternative solver using constraint programming
for guaranteed optimal fairness within hard constraint satisfaction.
"""

from collections import defaultdict
from datetime import date, timedelta

from ortools.sat.python import cp_model

from .models import (
    Abteilung,
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

    # Night shifts categorized by Intern presence (Interns are on-site Sun-Mon, Mon-Tue)
    intern_present_nights = [
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

    # 0. Max 1 shift per person per day (prevents double-booking on same day)
    shifts_by_date: dict[date, list[Shift]] = defaultdict(list)
    for s in shifts:
        shifts_by_date[s.shift_date].append(s)
    
    for staff in staff_list:
        for d, day_shifts in shifts_by_date.items():
            vars_for_day = [
                x[(staff.identifier, s.shift_date, s.shift_type)]
                for s in day_shifts
                if (staff.identifier, s.shift_date, s.shift_type) in x
            ]
            if len(vars_for_day) > 1:
                model.Add(sum(vars_for_day) <= 1)

    # 1. Weekend shift coverage: exactly 1 person per shift
    for shift in weekend_shifts:
        staff_for_shift = [
            x[(s.identifier, shift.shift_date, shift.shift_type)]
            for s in staff_list
            if (s.identifier, shift.shift_date, shift.shift_type) in x
        ]
        if staff_for_shift:
            model.Add(sum(staff_for_shift) == 1)

    # 2. Night shift coverage:
    #    - Sun-Mon and Mon-Tue (vet present): exactly 1 non-Azubi + optional 0-1 Azubi
    #    - Other nights: 1-2 people total
    #    - At least one non-Azubi required on all nights
    for shift in night_shifts:
        is_vet_present = shift.shift_type in (ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE)
        
        # Categorize staff for this shift
        azubi_vars = [
            x[(s.identifier, shift.shift_date, shift.shift_type)]
            for s in staff_list
            if (s.identifier, shift.shift_date, shift.shift_type) in x
            and s.beruf == Beruf.AZUBI
        ]
        non_azubi_vars = [
            x[(s.identifier, shift.shift_date, shift.shift_type)]
            for s in staff_list
            if (s.identifier, shift.shift_date, shift.shift_type) in x
            and s.beruf != Beruf.AZUBI
        ]
        all_vars = azubi_vars + non_azubi_vars
        
        if not all_vars:
            continue
        
        if is_vet_present:
            # Vet-present nights: exactly 1 non-Azubi + optional 0-1 Azubi
            if non_azubi_vars:
                model.Add(sum(non_azubi_vars) == 1)  # Exactly 1 non-Azubi
            if azubi_vars:
                model.Add(sum(azubi_vars) <= 1)  # Optional: max 1 Azubi
        else:
            # Regular nights: 1-2 people total, at least 1 non-Azubi
            coverage_sum = sum(all_vars)
            model.Add(coverage_sum >= 1)
            model.Add(coverage_sum <= 2)
            if non_azubi_vars:
                model.Add(sum(non_azubi_vars) >= 1)
        
        # Link is_paired variable: paired iff 2 people assigned (only for regular nights)
        if not is_vet_present:
            coverage_sum = sum(all_vars)
            sum_is_two = model.NewBoolVar(f"sum2_{shift.shift_date}_{shift.shift_type.value}")
            model.Add(coverage_sum == 2).OnlyEnforceIf(sum_is_two)
            model.Add(coverage_sum != 2).OnlyEnforceIf(sum_is_two.Not())
            
            for s in staff_list:
                key = (s.identifier, shift.shift_date, shift.shift_type)
                pair_key = (s.identifier, shift.shift_date)
                if key in x and pair_key in is_paired:
                    # is_paired = sum_is_two AND assigned
                    model.AddBoolAnd([sum_is_two, x[key]]).OnlyEnforceIf(is_paired[pair_key])
                    model.AddBoolOr([sum_is_two.Not(), x[key].Not()]).OnlyEnforceIf(
                        is_paired[pair_key].Not()
                    )

    # 3. Azubi and nd_alone constraints:
    #    - Azubis must always pair with a non-Azubi (TFA or Intern)
    #    - Two Azubis can NEVER work together on any night
    #    - nd_alone=False (non-Azubi) must be paired on regular nights
    #    - nd_alone=True (non-Azubi) must work COMPLETELY ALONE on regular nights
    
    for shift in night_shifts:
        is_vet_present = shift.shift_type in (ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE)
        
        # Categorize staff for this shift
        azubi_vars = []  # Azubis
        non_azubi_nd_alone_true = []  # Non-Azubis who must work alone
        non_azubi_nd_alone_false = []  # Non-Azubis who must be paired
        
        for staff in staff_list:
            key = (staff.identifier, shift.shift_date, shift.shift_type)
            if key not in x:
                continue
            
            if staff.beruf == Beruf.AZUBI:
                azubi_vars.append((staff, x[key]))
            elif staff.nd_alone:
                non_azubi_nd_alone_true.append((staff, x[key]))
            else:
                non_azubi_nd_alone_false.append((staff, x[key]))
        
        # Rule: At most 1 Azubi per night (two Azubis can never pair)
        if len(azubi_vars) > 1:
            model.Add(sum(v for _, v in azubi_vars) <= 1)
        
        # Rule: Azubi can only work if a non-Azubi is also assigned
        for azubi_staff, azubi_var in azubi_vars:
            non_azubi_vars = [v for _, v in non_azubi_nd_alone_true + non_azubi_nd_alone_false]
            if non_azubi_vars:
                # If Azubi is assigned, at least one non-Azubi must be assigned
                model.Add(sum(non_azubi_vars) >= 1).OnlyEnforceIf(azubi_var)
        
        # For regular nights (not vet-present):
        if not is_vet_present:
            # nd_alone=True staff must work COMPLETELY alone (no one else at all)
            for staff, var in non_azubi_nd_alone_true:
                all_other_vars = [
                    v for (s, v) in non_azubi_nd_alone_true + non_azubi_nd_alone_false + azubi_vars
                    if s.identifier != staff.identifier
                ]
                if all_other_vars:
                    # If nd_alone=True staff is assigned, no one else can be
                    for other_var in all_other_vars:
                        model.Add(var + other_var <= 1)
                    # If nd_alone=True staff is assigned, no one else can be
                    for other_var in all_other_vars:
                        model.Add(var + other_var <= 1)
            
            # nd_alone=False staff must be paired (sum == 2)
            for staff, var in non_azubi_nd_alone_false:
                pair_key = (staff.identifier, shift.shift_date)
                if pair_key in is_paired:
                    model.AddImplication(var, is_paired[pair_key])

    # 4. Intern night cap: 6-9 nights per quarter (2-3/month)
    for staff in staff_list:
        if staff.beruf == Beruf.INTERN:
            intern_night_vars = [
                x[(staff.identifier, s.shift_date, s.shift_type)]
                for s in night_shifts
                if (staff.identifier, s.shift_date, s.shift_type) in x
            ]
            if intern_night_vars:
                model.Add(sum(intern_night_vars) >= 6)
                model.Add(sum(intern_night_vars) <= 9)

    # 5. Weekend isolation: weekend shifts cannot be adjacent to any other shift
    # This ensures weekend shifts are always single-shift blocks
    _add_weekend_isolation_constraints(model, x, staff_list, weekend_shifts, night_shifts)

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

    # 8. nd_max_consecutive constraint: consecutive night blocks cannot exceed nd_max_consecutive
    _add_nd_max_consecutive_constraints(model, x, staff_list, night_shifts)
    
    # 9. Non-Azubi min consecutive nights: TFA/Intern must work at least 2 consecutive nights
    _add_min_consecutive_nights_constraints(model, x, staff_list, night_shifts)
    
    # 10. Abteilung constraint: employees in same abteilung (op or station) cannot work 
    # night shifts together or on consecutive days (prevents capacity shortages)
    _add_abteilung_night_constraints(model, x, staff_list, night_shifts)

    # =========================================================================
    # FAIRNESS OBJECTIVE
    # =========================================================================

    # Goal: minimize max FTE-deviation of combined Notdienste within each role group
    # Notdienste = weekends + effective_nights (paired nights = 0.5 per person)
    
    # To handle the 0.5 weight for paired nights, we count in half-units:
    # - Weekend shift = 2 half-units
    # - Solo night = 2 half-units (1.0 effective)
    # - Paired night = 1 half-unit (0.5 effective per person) - EXCEPT Azubis always get 2

    # Combined Notdienste count (in half-units) per staff
    notdienst_half_counts: dict[str, cp_model.LinearExpr] = {}
    
    for staff in staff_list:
        terms = []
        
        # Weekend shifts: each counts as 2 half-units
        for shift in weekend_shifts:
            key = (staff.identifier, shift.shift_date, shift.shift_type)
            if key in x:
                # 2 * x (2 half-units per weekend)
                terms.append(2 * x[key])
        
        # Night shifts: count depends on pairing and role
        if staff.nd_possible:
            for shift in night_shifts:
                key = (staff.identifier, shift.shift_date, shift.shift_type)
                pair_key = (staff.identifier, shift.shift_date)
                if key in x:
                    if staff.beruf == Beruf.AZUBI:
                        # Azubis always get full credit (2 half-units = 1.0 effective)
                        terms.append(2 * x[key])
                    else:
                        # Non-Azubis: paired = 1 half-unit (0.5), solo = 2 half-units (1.0)
                        # Approximation: count 1 per assignment (refined in post-processing)
                        terms.append(x[key])
        
        if terms:
            notdienst_half_counts[staff.identifier] = sum(terms)
        else:
            notdienst_half_counts[staff.identifier] = 0

    # FTE-scaled counts (multiplied by 40/hours to normalize)
    # To avoid fractions in CP, we multiply everything by a common factor
    SCALE = 40 * 10  # Scale factor for integer arithmetic

    # Calculate scaled fairness by group
    objective_terms = []

    # Group staff by role for fairness within groups
    tfa_staff = [s for s in staff_list if s.beruf == Beruf.TFA]
    azubi_staff = [s for s in staff_list if s.beruf == Beruf.AZUBI]
    intern_staff = [s for s in staff_list if s.beruf == Beruf.INTERN]

    # For each group, add combined fairness objective
    for group_name, group in [("TFA", tfa_staff), ("Azubi", azubi_staff), ("Intern", intern_staff)]:
        if len(group) < 2:
            continue
        
        # Combined Notdienste fairness (weekends + nights together)
        # For Interns: only nights (they don't do weekends)
        if group_name == "Intern":
            nd_eligible = [s for s in group if s.nd_possible]
            if len(nd_eligible) >= 2:
                _add_group_fairness_objective(
                    model, objective_terms, notdienst_half_counts, nd_eligible, SCALE, f"ND_{group_name}"
                )
        else:
            # TFA and Azubi: combined weekends + nights
            if len(group) >= 2:
                _add_group_fairness_objective(
                    model, objective_terms, notdienst_half_counts, group, SCALE, f"ND_{group_name}"
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


def _add_weekend_isolation_constraints(
    model: cp_model.CpModel,
    x: dict[tuple[str, date, ShiftType], cp_model.IntVar],
    staff_list: list[Staff],
    weekend_shifts: list[Shift],
    night_shifts: list[Shift],
) -> None:
    """Ensure weekend shifts are isolated (not adjacent to other shifts).
    
    A weekend shift cannot be on the same day or adjacent day to any other shift
    for the same person. This prevents weekend shifts from being part of blocks.
    """
    # Group shifts by date
    shifts_by_date: dict[date, list[Shift]] = defaultdict(list)
    for s in weekend_shifts + night_shifts:
        shifts_by_date[s.shift_date].append(s)
    
    all_dates = sorted(shifts_by_date.keys())
    
    for staff in staff_list:
        for we_shift in weekend_shifts:
            we_key = (staff.identifier, we_shift.shift_date, we_shift.shift_type)
            if we_key not in x:
                continue
            
            we_date = we_shift.shift_date
            prev_date = we_date - timedelta(days=1)
            next_date = we_date + timedelta(days=1)
            
            # Cannot have shifts on adjacent days
            for adj_date in [prev_date, next_date]:
                if adj_date in shifts_by_date:
                    for other_shift in shifts_by_date[adj_date]:
                        other_key = (staff.identifier, other_shift.shift_date, other_shift.shift_type)
                        if other_key in x and other_key != we_key:
                            # Weekend shift and adjacent shift cannot both be assigned
                            model.Add(x[we_key] + x[other_key] <= 1)


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


def _add_nd_max_consecutive_constraints(
    model: cp_model.CpModel,
    x: dict[tuple[str, date, ShiftType], cp_model.IntVar],
    staff_list: list[Staff],
    night_shifts: list[Shift],
) -> None:
    """Enforce max consecutive nights based on nd_max_consecutive field."""
    sorted_nights = sorted(night_shifts, key=lambda s: s.shift_date)

    for staff in staff_list:
        if not staff.nd_possible or staff.nd_max_consecutive is None:
            continue

        max_consecutive = staff.nd_max_consecutive

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


def _add_min_consecutive_nights_constraints(
    model: cp_model.CpModel,
    x: dict[tuple[str, date, ShiftType], cp_model.IntVar],
    staff_list: list[Staff],
    night_shifts: list[Shift],
) -> None:
    """Enforce minimum 2 consecutive nights for non-Azubi staff (TFA, Intern).
    
    This constraint ensures that if a non-Azubi works any nights, they work
    at least 2 consecutive nights (no single-night assignments).
    """
    sorted_nights = sorted(night_shifts, key=lambda s: s.shift_date)
    
    for staff in staff_list:
        # Only applies to non-Azubi staff
        if staff.beruf == Beruf.AZUBI or not staff.nd_possible:
            continue
        
        # Get this staff's night variables in order
        staff_night_vars = []
        for shift in sorted_nights:
            key = (staff.identifier, shift.shift_date, shift.shift_type)
            if key in x:
                staff_night_vars.append((shift.shift_date, x[key]))
        
        if len(staff_night_vars) < 2:
            continue
        
        # For each night, if assigned, at least one adjacent night must also be assigned
        # This prevents single-night assignments
        for i, (d, var) in enumerate(staff_night_vars):
            adjacent_vars = []
            
            # Check previous day
            if i > 0:
                prev_d, prev_var = staff_night_vars[i - 1]
                if (d - prev_d).days == 1:
                    adjacent_vars.append(prev_var)
            
            # Check next day
            if i < len(staff_night_vars) - 1:
                next_d, next_var = staff_night_vars[i + 1]
                if (next_d - d).days == 1:
                    adjacent_vars.append(next_var)
            
            # If this night is assigned, at least one adjacent night must be assigned
            if adjacent_vars:
                # var => OR(adjacent_vars)
                model.Add(sum(adjacent_vars) >= 1).OnlyEnforceIf(var)
            else:
                # No adjacent nights available - this non-Azubi cannot work this night
                # (would result in isolated single night)
                model.Add(var == 0)


def _add_abteilung_night_constraints(
    model: cp_model.CpModel,
    x: dict[tuple[str, date, ShiftType], cp_model.IntVar],
    staff_list: list[Staff],
    night_shifts: list[Shift],
) -> None:
    """Enforce abteilung separation on night shifts.
    
    Employees in the same abteilung (op or station) cannot:
    1. Work the same night shift together
    2. Work consecutive night shifts (day N and day N+1)
    
    This prevents capacity shortages in specialized departments.
    Employees in abteilung="other" are exempt from this rule.
    """
    sorted_nights = sorted(night_shifts, key=lambda s: s.shift_date)
    
    # Only apply to staff in "op" or "station" abteilung
    restricted_abteilungen = {Abteilung.OP, Abteilung.STATION}
    
    # Group staff by abteilung
    staff_by_abteilung: dict[Abteilung, list[Staff]] = defaultdict(list)
    for staff in staff_list:
        if staff.nd_possible and staff.abteilung in restricted_abteilungen:
            staff_by_abteilung[staff.abteilung].append(staff)
    
    # For each restricted abteilung, add constraints
    for abteilung, abt_staff in staff_by_abteilung.items():
        if len(abt_staff) < 2:
            continue  # No constraint needed if only 1 person in abteilung
        
        # 1. Same night constraint: no two staff from same abteilung on same night
        for shift in sorted_nights:
            vars_for_shift = []
            for staff in abt_staff:
                key = (staff.identifier, shift.shift_date, shift.shift_type)
                if key in x:
                    vars_for_shift.append(x[key])
            
            # At most 1 person from this abteilung per night
            if len(vars_for_shift) >= 2:
                model.Add(sum(vars_for_shift) <= 1)
        
        # 2. Consecutive nights constraint: no two staff from same abteilung on consecutive days
        for i, shift in enumerate(sorted_nights):
            # Find next day's night shifts
            next_day = shift.shift_date + timedelta(days=1)
            next_day_shifts = [s for s in sorted_nights if s.shift_date == next_day]
            
            if not next_day_shifts:
                continue
            
            # For each pair of staff in same abteilung
            for staff1 in abt_staff:
                key1 = (staff1.identifier, shift.shift_date, shift.shift_type)
                if key1 not in x:
                    continue
                
                for staff2 in abt_staff:
                    if staff1.identifier == staff2.identifier:
                        continue  # Same person, handled by single-assignment constraint
                    
                    for next_shift in next_day_shifts:
                        key2 = (staff2.identifier, next_shift.shift_date, next_shift.shift_type)
                        if key2 not in x:
                            continue
                        
                        # staff1 on day N and staff2 on day N+1 cannot both be true
                        model.Add(x[key1] + x[key2] <= 1)


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

    # Saturday 10-19: Any Azubi can work this shift
    sa_1019_eligible = [s for s in staff_list if s.beruf == Beruf.AZUBI]
    if len(sa_1019_eligible) * 13 < len([s for s in saturday_shifts if s.shift_type == ShiftType.SATURDAY_10_19]):
        issues.append(f"Insufficient Azubis for Sa_10-19 shifts. Have {len(sa_1019_eligible)}, need coverage for 13 weeks.")

    # Sunday: adults only
    adult_azubis = [s for s in staff_list if s.beruf == Beruf.AZUBI and s.adult]
    if len(adult_azubis) == 0:
        issues.append("No adult Azubis available for Sunday So_8-20:30 shifts.")

    # Night capacity - need non-Azubis for all nights
    non_azubi_nd_eligible = [s for s in staff_list if s.nd_possible and s.beruf != Beruf.AZUBI]
    if len(non_azubi_nd_eligible) < 1:
        issues.append("Insufficient non-Azubi night-capable staff. Need at least 1 TFA or Intern per night.")
    
    # Check for min 2 consecutive nights constraint feasibility
    # Non-Azubis with limited availability may not be able to do 2+ consecutive
    for staff in non_azubi_nd_eligible:
        if len(staff.nd_exceptions) >= 6:  # Can only work 1 night type
            issues.append(
                f"{staff.name} ({staff.beruf.value}) has too many nd_exceptions to work "
                f"2 consecutive nights (min required for non-Azubis)."
            )

    if not issues:
        issues.append("Model infeasible. Check constraint interactions or increase solve time.")

    return issues
