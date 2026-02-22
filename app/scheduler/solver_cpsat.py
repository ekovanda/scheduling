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
    PreviousPlanContext,
    Schedule,
    Shift,
    ShiftType,
    Staff,
    Vacation,
    calculate_available_days,
    generate_quarter_shifts,
    get_staff_unavailable_dates,
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
    vacations: list[Vacation] | None = None,
    max_solve_time_seconds: int = 120,
    random_seed: int | None = None,
    previous_context: PreviousPlanContext | None = None,
) -> SolverResult:
    """Generate schedule using OR-Tools CP-SAT solver.

    Args:
        staff_list: List of staff members
        quarter_start: Start date of quarter (e.g., April 1, 2026)
        vacations: List of vacation periods (staff unavailability)
        max_solve_time_seconds: Maximum solver time in seconds
        random_seed: Random seed for reproducibility

    Returns:
        SolverResult with best schedule or unsatisfiable constraints
    """
    if vacations is None:
        vacations = []
    
    model = cp_model.CpModel()

    # Generate all shifts for the quarter
    shifts = generate_quarter_shifts(quarter_start)
    quarter_end = max(s.shift_date for s in shifts) if shifts else quarter_start

    # Index mappings
    staff_by_id = {s.identifier: s for s in staff_list}
    shift_index = {(s.shift_date, s.shift_type): i for i, s in enumerate(shifts)}

    # Pre-compute vacation dates per staff for efficient lookup
    staff_vacation_dates: dict[str, set[date]] = {
        s.identifier: get_staff_unavailable_dates(vacations, s.identifier)
        for s in staff_list
    }

    # Block birthdays: treat an employee's birthday like a vacation day
    for staff in staff_list:
        for year in {quarter_start.year, quarter_end.year}:
            bd = staff.get_birthday_date(year)
            if bd is not None and quarter_start <= bd <= quarter_end:
                staff_vacation_dates[staff.identifier].add(bd)

    # =========================================================================
    # EXTRACT BOUNDARY DATA FROM PREVIOUS CONTEXT
    # =========================================================================
    trailing_work_dates: dict[str, set[date]] = {}  # For block constraints
    trailing_night_dates: dict[str, list[date]] = {}  # For consecutive-night constraints
    trailing_last_night: dict[str, date] = {}  # For night/day conflict
    carry_forward_deltas: dict[str, float] = {}  # For fairness objective

    if previous_context:
        for ta in previous_context.trailing_assignments:
            trailing_work_dates.setdefault(ta.staff_identifier, set()).add(ta.shift_date)
            if ta.shift_type.value.startswith("N_"):
                trailing_night_dates.setdefault(ta.staff_identifier, []).append(
                    ta.shift_date
                )
        # Sort trailing night dates and find last night per person
        for sid in trailing_night_dates:
            trailing_night_dates[sid].sort()
            trailing_last_night[sid] = trailing_night_dates[sid][-1]
        # Extract carry-forward deltas (identifier -> norm_40h delta)
        for entry in previous_context.carry_forward:
            carry_forward_deltas[entry.identifier] = entry.carry_forward_delta

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
    # Staff on vacation are excluded from consideration for that date
    x: dict[tuple[str, date, ShiftType], cp_model.IntVar] = {}
    for staff in staff_list:
        vacation_dates = staff_vacation_dates[staff.identifier]
        for shift in shifts:
            # Skip if staff is on vacation on this date
            if shift.shift_date in vacation_dates:
                continue
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

    # 6b. Night/Day conflict at quarter boundary:
    #     If someone had a night shift on the last day of the previous quarter,
    #     they cannot have a day shift on the first day of this quarter.
    if trailing_last_night:
        for staff in staff_list:
            last_night = trailing_last_night.get(staff.identifier)
            if last_night is None:
                continue
            next_day = last_night + timedelta(days=1)
            for we_shift in weekend_shifts:
                if we_shift.shift_date == next_day:
                    we_key = (staff.identifier, we_shift.shift_date, we_shift.shift_type)
                    if we_key in x:
                        model.Add(x[we_key] == 0)
            # Also block night shift on the same day as the trailing night
            for ns in night_shifts:
                if ns.shift_date == last_night:
                    ns_key = (staff.identifier, ns.shift_date, ns.shift_type)
                    if ns_key in x:
                        model.Add(x[ns_key] == 0)

    # 7. 3-week block constraint: gaps between shift blocks must be >= 21 days
    # Track block starts and enforce gap between consecutive blocks
    _add_block_constraints(
        model, x, staff_list, shifts, quarter_start, quarter_end,
        trailing_work_dates=trailing_work_dates or None,
    )

    # 8. nd_max_consecutive constraint: consecutive night blocks cannot exceed nd_max_consecutive
    _add_nd_max_consecutive_constraints(
        model, x, staff_list, night_shifts,
        trailing_night_dates=trailing_night_dates or None,
    )
    
    # 9. Non-Azubi min consecutive nights: TFA/Intern must work at least 2 consecutive nights
    _add_min_consecutive_nights_constraints(
        model, x, staff_list, night_shifts,
        trailing_night_dates=trailing_night_dates or None,
    )
    
    # 10. Abteilung constraint: employees in same abteilung (op or station) cannot work 
    # night shifts together or on consecutive days (prevents capacity shortages)
    _add_abteilung_night_constraints(model, x, staff_list, night_shifts)

    # 11. Minimum shift participation: eligible staff must work at least 1 night and 1 weekend
    # This ensures better type balance and prevents "0 nights, all weekends" scenarios
    min_participation_info = _add_min_participation_constraints(
        model, x, staff_list, weekend_shifts, night_shifts
    )

    # =========================================================================
    # FAIRNESS OBJECTIVE
    # =========================================================================

    # Goal: minimize max FTE-deviation of combined Notdienste within each role group
    # Notdienste = weekends + effective_nights (paired nights = 0.5 per person)
    # ADJUSTED FOR PRESENCE: FTE is scaled by (available_days / total_quarter_days)
    
    # Calculate total quarter days for presence adjustment
    total_quarter_days = (quarter_end - quarter_start).days + 1
    
    # Pre-compute presence factor per staff (available_days / total_days)
    # We'll use integer arithmetic: presence_factor_scaled = available_days * 1000 / total_days
    presence_factors: dict[str, int] = {}
    for staff in staff_list:
        available_days = calculate_available_days(
            staff.identifier, vacations, quarter_start, quarter_end
        )
        # Scale by 1000 to maintain precision in integer arithmetic
        presence_factors[staff.identifier] = (available_days * 1000) // total_quarter_days
    
    # To handle the 0.5 weight for paired nights, we count in half-units:
    # - Weekend shift = 2 half-units
    # - Solo night = 2 half-units (1.0 effective)
    # - Paired night = 1 half-unit (0.5 effective per person) - EXCEPT Azubis always get 2

    # Combined Notdienste count (in half-units) per staff
    notdienst_half_counts: dict[str, cp_model.LinearExpr] = {}
    
    # Also track separate counts for secondary type-balance objective
    weekend_half_counts: dict[str, cp_model.LinearExpr] = {}
    night_half_counts: dict[str, cp_model.LinearExpr] = {}
    
    for staff in staff_list:
        terms: list[cp_model.LinearExpr] = []
        weekend_terms: list[cp_model.LinearExpr] = []
        night_terms: list[cp_model.LinearExpr] = []
        
        # Weekend shifts: each counts as 2 half-units
        for shift in weekend_shifts:
            key = (staff.identifier, shift.shift_date, shift.shift_type)
            if key in x:
                # 2 * x (2 half-units per weekend)
                terms.append(2 * x[key])
                weekend_terms.append(2 * x[key])
        
        # Night shifts: count depends on pairing and role
        if staff.nd_possible:
            for shift in night_shifts:
                key = (staff.identifier, shift.shift_date, shift.shift_type)
                pair_key = (staff.identifier, shift.shift_date)
                if key in x:
                    if staff.beruf == Beruf.AZUBI:
                        # Azubis always get full credit (2 half-units = 1.0 effective)
                        terms.append(2 * x[key])
                        night_terms.append(2 * x[key])
                    else:
                        # Non-Azubis: paired = 1 half-unit (0.5), solo = 2 half-units (1.0)
                        # Formula: contribution = 2*assigned - paired_and_assigned
                        # = 2 if solo (assigned=1, paired=0)
                        # = 1 if paired (assigned=1, paired=1)
                        # = 0 if not assigned
                        if pair_key in is_paired:
                            # Create auxiliary variable for "assigned AND paired"
                            paired_assigned = model.NewBoolVar(
                                f"paired_assigned_{staff.identifier}_{shift.shift_date}"
                            )
                            # paired_assigned = x[key] AND is_paired[pair_key]
                            model.AddBoolAnd([x[key], is_paired[pair_key]]).OnlyEnforceIf(paired_assigned)
                            model.AddBoolOr([x[key].Not(), is_paired[pair_key].Not()]).OnlyEnforceIf(
                                paired_assigned.Not()
                            )
                            # contribution = 2*x - paired_assigned
                            terms.append(2 * x[key] - paired_assigned)
                            night_terms.append(2 * x[key] - paired_assigned)
                        else:
                            # No pairing info available (shouldn't happen for night-capable staff)
                            # Fall back to solo counting (2 half-units)
                            terms.append(2 * x[key])
                            night_terms.append(2 * x[key])
        
        if terms:
            notdienst_half_counts[staff.identifier] = sum(terms)
        else:
            notdienst_half_counts[staff.identifier] = 0
        
        # Store separate counts for type balance
        weekend_half_counts[staff.identifier] = sum(weekend_terms) if weekend_terms else 0
        night_half_counts[staff.identifier] = sum(night_terms) if night_terms else 0

    # FTE-scaled counts (multiplied by 40/hours AND adjusted for presence)
    # To avoid fractions in CP, we multiply everything by a common factor
    # SCALE = 40 * 10 * 1000 (extra 1000 for presence factor precision)
    SCALE = 40 * 10  # Scale factor for integer arithmetic
    PRESENCE_SCALE = 1000  # Matches presence_factors scaling

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
                _add_group_fairness_objective_with_presence(
                    model, objective_terms, notdienst_half_counts, nd_eligible, 
                    SCALE, presence_factors, f"ND_{group_name}",
                    carry_forward_deltas=carry_forward_deltas or None,
                )
        else:
            # TFA and Azubi: combined weekends + nights
            if len(group) >= 2:
                _add_group_fairness_objective_with_presence(
                    model, objective_terms, notdienst_half_counts, group, 
                    SCALE, presence_factors, f"ND_{group_name}",
                    carry_forward_deltas=carry_forward_deltas or None,
                )

    # =========================================================================
    # SECONDARY OBJECTIVE: Type balance (nights vs weekends) within groups
    # =========================================================================
    # For TFA and Azubi: add soft objective to balance night counts among night-eligible
    # This is weighted lower than the primary objective (total Notdienste fairness)
    
    TYPE_BALANCE_WEIGHT = 1  # Lower weight than primary fairness (which uses range directly)
    
    for group_name, group in [("TFA", tfa_staff), ("Azubi", azubi_staff)]:
        # Only apply type balance to night-eligible staff in the group
        nd_eligible = [s for s in group if s.nd_possible]
        if len(nd_eligible) >= 2:
            _add_type_balance_objective(
                model, objective_terms, night_half_counts, nd_eligible,
                SCALE, presence_factors, f"NightBal_{group_name}", TYPE_BALANCE_WEIGHT
            )

    # Minimize total fairness deviation (primary + secondary objectives)
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
        unsatisfiable = _diagnose_infeasibility(
            model, staff_list, shifts, min_participation_info
        )
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
    trailing_work_dates: dict[str, set[date]] | None = None,
) -> None:
    """Add 3-week block constraints.

    The constraint: if you have blocks B1 and B2, and B2 starts
    within 21 days of B1's START, that's a violation.

    Implementation: For each potential block-start day D (where we work but didn't
    work D-1), we forbid working on any day in (D+2, D+20) that would also be a
    block-start (i.e., without working the day before).

    Simplified approach: Forbid working on day D1 and day D2 where:
    - D1 and D2 are both "block starts" (no work on D1-1 and D2-1)
    - 2 <= D2 - D1 < 21

    When trailing_work_dates is provided, injects fixed work-day variables
    from the previous quarter (last 21 days) so the 3-week gap is
    enforced across the quarter boundary.
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

        if len(staff_dates) < 2 and not trailing_work_dates:
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

        # Inject trailing work dates as fixed variables (previous quarter)
        if trailing_work_dates:
            for d in trailing_work_dates.get(staff.identifier, set()):
                if (quarter_start - d).days <= 21 and d < quarter_start:
                    fixed = model.NewBoolVar(f"trail_work_{staff.identifier}_{d}")
                    model.Add(fixed == 1)
                    works_on[d] = fixed

        # Use all known dates (trailing + current) for block start detection
        all_known_dates = sorted(works_on.keys())

        # Create "block_starts_on_D" = works_on[D] AND NOT works_on[D-1]
        block_starts: dict[date, cp_model.IntVar] = {}
        for d in all_known_dates:
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

        # Enforce: no two block starts within 21 days (3 weeks)
        block_start_dates = sorted(block_starts.keys())
        for i, d1 in enumerate(block_start_dates):
            for d2 in block_start_dates[i + 1:]:
                gap = (d2 - d1).days
                if gap >= 21:
                    break  # No need to check further
                # Both being block starts is forbidden
                model.Add(block_starts[d1] + block_starts[d2] <= 1)


def _add_nd_max_consecutive_constraints(
    model: cp_model.CpModel,
    x: dict[tuple[str, date, ShiftType], cp_model.IntVar],
    staff_list: list[Staff],
    night_shifts: list[Shift],
    trailing_night_dates: dict[str, list[date]] | None = None,
) -> None:
    """Enforce max consecutive nights based on nd_max_consecutive field.

    When trailing_night_dates is provided, prepends fixed night variables from
    the previous quarter so consecutive-night limits are enforced at boundary.
    """
    sorted_nights = sorted(night_shifts, key=lambda s: s.shift_date)

    for staff in staff_list:
        if not staff.nd_possible or staff.nd_max_consecutive is None:
            continue

        max_consecutive = staff.nd_max_consecutive

        # Get this staff's night variables in order
        staff_night_vars: list[tuple[date, cp_model.IntVar]] = []
        for shift in sorted_nights:
            key = (staff.identifier, shift.shift_date, shift.shift_type)
            if key in x:
                staff_night_vars.append((shift.shift_date, x[key]))

        # Prepend trailing night dates as fixed variables
        if trailing_night_dates and staff.identifier in trailing_night_dates:
            trailing_vars: list[tuple[date, cp_model.IntVar]] = []
            for d in trailing_night_dates[staff.identifier]:
                fixed = model.NewBoolVar(f"trail_maxnd_{staff.identifier}_{d}")
                model.Add(fixed == 1)
                trailing_vars.append((d, fixed))
            staff_night_vars = trailing_vars + staff_night_vars

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
    trailing_night_dates: dict[str, list[date]] | None = None,
) -> None:
    """Enforce minimum consecutive nights based on staff.nd_min_consecutive.
    
    Each staff member has an nd_min_consecutive value:
    - Azubis: typically 1 (no minimum consecutive requirement)
    - TFA/Intern: typically 2 (must work at least 2 consecutive nights)
    - Special cases like Anika Alles: 3 (must work at least 3 consecutive nights)
    
    This constraint ensures that if a staff member works any nights, they work
    at least nd_min_consecutive consecutive nights.

    When trailing_night_dates is provided, prepends fixed night variables from
    the previous quarter so min-consecutive is respected at boundary.
    """
    sorted_nights = sorted(night_shifts, key=lambda s: s.shift_date)
    
    for staff in staff_list:
        if not staff.nd_possible:
            continue
        
        min_consecutive = staff.nd_min_consecutive
        
        # If min_consecutive is 1, no constraint needed (single nights allowed)
        if min_consecutive <= 1:
            continue
        
        # Get this staff's night variables in order
        staff_night_vars: list[tuple[date, cp_model.IntVar]] = []
        for shift in sorted_nights:
            key = (staff.identifier, shift.shift_date, shift.shift_type)
            if key in x:
                staff_night_vars.append((shift.shift_date, x[key]))

        # Prepend trailing night dates as fixed variables
        if trailing_night_dates and staff.identifier in trailing_night_dates:
            trailing_vars: list[tuple[date, cp_model.IntVar]] = []
            for d in trailing_night_dates[staff.identifier]:
                fixed = model.NewBoolVar(f"trail_minnd_{staff.identifier}_{d}")
                model.Add(fixed == 1)
                trailing_vars.append((d, fixed))
            staff_night_vars = trailing_vars + staff_night_vars
        
        if len(staff_night_vars) < min_consecutive:
            continue
        
        # For min_consecutive=2: each assigned night needs at least 1 adjacent night
        # For min_consecutive=3: each assigned night needs to be part of a 3+ block
        # General approach: for each night, if assigned, there must be (min_consecutive-1)
        # other nights within the same contiguous block
        
        if min_consecutive == 2:
            # Simple case: each night needs at least one adjacent night
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
                
                if adjacent_vars:
                    # var => OR(adjacent_vars)
                    model.Add(sum(adjacent_vars) >= 1).OnlyEnforceIf(var)
                else:
                    # No adjacent nights available - cannot work this night
                    model.Add(var == 0)
        else:
            # General case for min_consecutive >= 3
            # For each night, if assigned, it must be part of a block of at least min_consecutive
            # This is more complex: we need to ensure the block extends in either direction
            _add_min_block_constraint(model, staff_night_vars, min_consecutive)


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
    max_fte_deviation: float = 1.5,
) -> None:
    """Add min-max fairness objective for a group with hard constraint.

    Enforces hard constraint: (max - min) <= threshold (FTE-normalized).
    Then minimizes (max - min) as soft objective for tightest fairness.

    Args:
        max_fte_deviation: Maximum allowed FTE-normalized Notdienst difference
            within the group. Default 1.5 means no one can have more than
            1.5 FTE-adjusted Notdienste more than the person with fewest.
    """
    if len(group) < 2:
        return

    # Create scaled count variables: count * (scale / hours)
    # This FTE-normalizes the counts so a 20h employee with 5 shifts
    # equals a 40h employee with 10 shifts.
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

    # HARD CONSTRAINT: Enforce maximum allowed deviation
    # Threshold is in scaled units. Since counts are in half-units (1 Notdienst = 2),
    # and scale=400, for a 40h employee: 1 Notdienst = 2 * (400/40) = 20 scaled units.
    # So max_fte_deviation=1.5 Notdienste = 1.5 * 20 = 30 scaled units for 40h.
    # We use 40h as reference (the "full-time equivalent").
    threshold_scaled = int(max_fte_deviation * 2 * (scale // 40))
    model.Add(range_var <= threshold_scaled)

    # SOFT OBJECTIVE: Minimize range further (tightest possible fairness)
    objective_terms.append(range_var)


def _add_group_fairness_objective_with_presence(
    model: cp_model.CpModel,
    objective_terms: list,
    counts: dict[str, cp_model.LinearExpr],
    group: list[Staff],
    scale: int,
    presence_factors: dict[str, int],
    prefix: str,
    max_fte_deviation: float = 1.5,
    carry_forward_deltas: dict[str, float] | None = None,
) -> None:
    """Add min-max fairness objective with presence (vacation) adjustment.

    Similar to _add_group_fairness_objective but scales by presence factor
    so employees with vacation are expected to do proportionally fewer shifts.
    
    The effective FTE multiplier becomes: (40 / hours) * (1000 / presence_factor)
    where presence_factor = available_days * 1000 / total_days

    When carry_forward_deltas is provided, adds per-person offsets from the
    previous quarter so the solver compensates historical imbalances.
    The delta is in Norm./40h units and is converted to the solver's internal
    scaled integer space via the constant factor CARRY_FORWARD_SCALE = 20
    (derived from scale=400, counts in half-units).
    """
    if len(group) < 2:
        return

    PRESENCE_SCALE = 1000  # Matches presence_factors scaling
    # 1.0 Norm./40h = 20 solver-scaled units (= 2 * scale / 40 = 2 * 400 / 40)
    CARRY_FORWARD_SCALE = 2 * scale // 40  # = 20 for scale=400
    
    has_carry_forward = carry_forward_deltas and any(
        carry_forward_deltas.get(s.identifier, 0.0) != 0.0 for s in group
    )

    scaled_counts = []
    for staff in group:
        count_expr = counts.get(staff.identifier, 0)
        presence = presence_factors.get(staff.identifier, PRESENCE_SCALE)
        # Avoid division by zero if someone has no available days
        if presence == 0:
            presence = 1
        
        if isinstance(count_expr, int) and count_expr == 0:
            scaled_var = model.NewIntVar(0, 0, f"{prefix}_scaled_{staff.identifier}")
        else:
            # scaled = count * (scale / hours) * (PRESENCE_SCALE / presence)
            # = count * scale * PRESENCE_SCALE / (hours * presence)
            # Simplified: we multiply by hours_multiplier and presence_multiplier
            hours_multiplier = scale // staff.hours
            # presence_multiplier = PRESENCE_SCALE * 10 // presence (extra 10 for precision)
            presence_multiplier = (PRESENCE_SCALE * 10) // presence
            combined_multiplier = hours_multiplier * presence_multiplier // 10
            
            max_possible = 100 * combined_multiplier
            scaled_var = model.NewIntVar(0, max_possible, f"{prefix}_scaled_{staff.identifier}")
            model.Add(scaled_var == count_expr * combined_multiplier)

        # Apply carry-forward offset (previous quarter imbalance)
        cf_delta = (carry_forward_deltas or {}).get(staff.identifier, 0.0)
        if cf_delta != 0.0:
            cf_offset = int(round(cf_delta * CARRY_FORWARD_SCALE))
            lb = min(0, cf_offset - 500)
            ub = 100000 + abs(cf_offset)
            adjusted_var = model.NewIntVar(
                lb, ub, f"{prefix}_adj_{staff.identifier}"
            )
            model.Add(adjusted_var == scaled_var + cf_offset)
            scaled_counts.append(adjusted_var)
        else:
            scaled_counts.append(scaled_var)

    min_bound = -10000 if has_carry_forward else 0
    max_var = model.NewIntVar(min_bound, 100000, f"{prefix}_max")
    min_var = model.NewIntVar(min_bound, 100000, f"{prefix}_min")
    model.AddMaxEquality(max_var, scaled_counts)
    model.AddMinEquality(min_var, scaled_counts)

    range_var = model.NewIntVar(0, 100000, f"{prefix}_range")
    model.Add(range_var == max_var - min_var)

    # Hard constraint threshold (adjusted for presence scaling)
    threshold_scaled = int(max_fte_deviation * 2 * (scale // 40) * (PRESENCE_SCALE // 100))
    # Widen threshold when carry-forward is active to avoid infeasibility
    if has_carry_forward:
        group_cfs = [carry_forward_deltas.get(s.identifier, 0.0) for s in group]
        cf_spread = max(group_cfs) - min(group_cfs)
        threshold_scaled += int(round(cf_spread * CARRY_FORWARD_SCALE))
    model.Add(range_var <= threshold_scaled)

    objective_terms.append(range_var)


def _add_type_balance_objective(
    model: cp_model.CpModel,
    objective_terms: list,
    night_counts: dict[str, cp_model.LinearExpr],
    group: list[Staff],
    scale: int,
    presence_factors: dict[str, int],
    prefix: str,
    weight: int = 1,
) -> None:
    """Add secondary objective to balance night shift counts within a group.
    
    This encourages more even distribution of night shifts specifically,
    preventing scenarios where one person does 0 nights and many weekends.
    """
    if len(group) < 2:
        return

    PRESENCE_SCALE = 1000
    
    scaled_counts = []
    for staff in group:
        count_expr = night_counts.get(staff.identifier, 0)
        presence = presence_factors.get(staff.identifier, PRESENCE_SCALE)
        if presence == 0:
            presence = 1
        
        if isinstance(count_expr, int) and count_expr == 0:
            scaled_var = model.NewIntVar(0, 0, f"{prefix}_scaled_{staff.identifier}")
        else:
            hours_multiplier = scale // staff.hours
            presence_multiplier = (PRESENCE_SCALE * 10) // presence
            combined_multiplier = hours_multiplier * presence_multiplier // 10
            
            max_possible = 50 * combined_multiplier  # Nights only, so lower max
            scaled_var = model.NewIntVar(0, max_possible, f"{prefix}_scaled_{staff.identifier}")
            model.Add(scaled_var == count_expr * combined_multiplier)
        scaled_counts.append(scaled_var)

    max_var = model.NewIntVar(0, 50000, f"{prefix}_max")
    min_var = model.NewIntVar(0, 50000, f"{prefix}_min")
    model.AddMaxEquality(max_var, scaled_counts)
    model.AddMinEquality(min_var, scaled_counts)

    range_var = model.NewIntVar(0, 50000, f"{prefix}_range")
    model.Add(range_var == max_var - min_var)

    # Add weighted to objective (no hard constraint, just soft optimization)
    objective_terms.append(weight * range_var)


def _add_min_block_constraint(
    model: cp_model.CpModel,
    staff_night_vars: list[tuple[date, cp_model.IntVar]],
    min_consecutive: int,
) -> None:
    """Add constraint that any assigned night must be part of a block of min_consecutive.
    
    For min_consecutive=3: if night i is assigned, then either:
    - nights i-2, i-1, i are all assigned (block ends at i), OR
    - nights i-1, i, i+1 are all assigned (i is in middle), OR
    - nights i, i+1, i+2 are all assigned (block starts at i)
    
    This generalizes to any min_consecutive value.
    """
    n = len(staff_night_vars)
    
    for i, (d, var) in enumerate(staff_night_vars):
        # Find all possible blocks of min_consecutive that include position i
        valid_block_indicators = []
        
        for block_start in range(max(0, i - min_consecutive + 1), min(n - min_consecutive + 1, i + 1)):
            block_end = block_start + min_consecutive
            
            # Check if this is a valid contiguous block (consecutive dates)
            block_vars = []
            is_contiguous = True
            for j in range(block_start, block_end):
                if j > block_start:
                    prev_date = staff_night_vars[j - 1][0]
                    curr_date = staff_night_vars[j][0]
                    if (curr_date - prev_date).days != 1:
                        is_contiguous = False
                        break
                block_vars.append(staff_night_vars[j][1])
            
            if is_contiguous and len(block_vars) == min_consecutive:
                # Create indicator for "all vars in block are assigned"
                block_indicator = model.NewBoolVar(f"block_{d}_{block_start}")
                # block_indicator = 1 iff all block_vars = 1
                model.Add(sum(block_vars) == min_consecutive).OnlyEnforceIf(block_indicator)
                model.Add(sum(block_vars) < min_consecutive).OnlyEnforceIf(block_indicator.Not())
                valid_block_indicators.append(block_indicator)
        
        if valid_block_indicators:
            # If var is assigned, at least one valid block must be active
            model.Add(sum(valid_block_indicators) >= 1).OnlyEnforceIf(var)
        else:
            # No valid blocks include this position - cannot be assigned
            model.Add(var == 0)


def _add_min_participation_constraints(
    model: cp_model.CpModel,
    x: dict[tuple[str, date, ShiftType], cp_model.IntVar],
    staff_list: list[Staff],
    weekend_shifts: list[Shift],
    night_shifts: list[Shift],
) -> dict[str, dict[str, bool]]:
    """Add hard constraints for minimum shift participation.
    
    Eligible staff must work at least:
    - 1 weekend shift (if eligible for any weekend shift type)
    - 1 night shift (if nd_possible=True AND has sufficient availability)
    
    Returns dict tracking which constraints were applied per staff for diagnostics.
    """
    participation_info: dict[str, dict[str, bool]] = {}
    
    for staff in staff_list:
        info: dict[str, bool] = {"weekend_required": False, "night_required": False}
        
        # Weekend participation: TFA and Azubi who can work any weekend shift
        weekend_vars = [
            x[(staff.identifier, s.shift_date, s.shift_type)]
            for s in weekend_shifts
            if (staff.identifier, s.shift_date, s.shift_type) in x
        ]
        
        if weekend_vars and staff.beruf != Beruf.INTERN:
            # Require at least 1 weekend shift
            model.Add(sum(weekend_vars) >= 1)
            info["weekend_required"] = True
        
        # Night participation: staff with nd_possible=True
        if staff.nd_possible:
            night_vars = [
                x[(staff.identifier, s.shift_date, s.shift_type)]
                for s in night_shifts
                if (staff.identifier, s.shift_date, s.shift_type) in x
            ]
            
            # Only require if they have enough availability for min_consecutive requirement
            # Count available consecutive night opportunities
            min_consec = staff.nd_min_consecutive
            available_night_types = 7 - len(staff.nd_exceptions)
            
            # Heuristic: if available types >= min_consecutive, they can likely form a block
            if night_vars and available_night_types >= min_consec:
                model.Add(sum(night_vars) >= 1)
                info["night_required"] = True
        
        participation_info[staff.identifier] = info
    
    return participation_info


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
    participation_info: dict[str, dict[str, bool]] | None = None,
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
    
    # Check for min consecutive nights constraint feasibility
    for staff in staff_list:
        if not staff.nd_possible:
            continue
        min_consec = staff.nd_min_consecutive
        available_nights = 7 - len(staff.nd_exceptions)
        if available_nights < min_consec and available_nights > 0:
            issues.append(
                f"{staff.name} ({staff.beruf.value}) has only {available_nights} available night types "
                f"but requires {min_consec} consecutive nights. Consider reducing nd_min_consecutive."
            )
    
    # Check participation constraints vs vacation/availability
    if participation_info:
        for staff in staff_list:
            info = participation_info.get(staff.identifier, {})
            if info.get("night_required") and len(staff.nd_exceptions) >= 5:
                issues.append(
                    f"{staff.name} requires 1+ night shifts but has limited availability "
                    f"({7 - len(staff.nd_exceptions)} night types). May conflict with vacation."
                )

    if not issues:
        issues.append("Model infeasible. Check constraint interactions, vacation conflicts, or increase solve time.")

    return issues
