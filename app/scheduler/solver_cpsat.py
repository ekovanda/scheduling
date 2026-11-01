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
    PreAssignedShift,
    PreviousPlanContext,
    Schedule,
    SchedulerConfig,
    Shift,
    ShiftType,
    Staff,
    Vacation,
    calculate_available_days,
    generate_quarter_shifts,
    get_pre_assigned_holiday_dates,
    get_staff_unavailable_dates,
)
from .validator import validate_schedule
from .feasibility import analyze_capacity


class SolverResult:
    """Result from solver with multiple candidate schedules."""

    def __init__(
        self,
        success: bool,
        schedules: list[Schedule],
        penalties: list[float],
        unsatisfiable_constraints: list[str],
        convergence_log: list[dict[str, float]] | None = None,
    ) -> None:
        self.success = success
        self.schedules = schedules
        self.penalties = penalties
        self.unsatisfiable_constraints = unsatisfiable_constraints
        self.convergence_log: list[dict[str, float]] = convergence_log or []

    def get_best_schedule(self) -> Schedule | None:
        """Get the best schedule (lowest penalty)."""
        return self.schedules[0] if self.schedules else None


class _SchedulingProgressCallback(cp_model.CpSolverSolutionCallback):
    """Records each improving solution found during solving.

    Populated via Solve(model, callback) and attached to SolverResult
    as convergence_log for post-solve display in the UI.
    """

    def __init__(self) -> None:
        super().__init__()
        self.solutions: list[dict[str, float]] = []

    def on_solution_callback(self) -> None:
        self.solutions.append({
            "wall_time": round(self.wall_time, 2),
            "objective": float(self.objective_value),
            "bound": float(self.best_objective_bound),
        })


def generate_schedule_cpsat(
    staff_list: list[Staff],
    quarter_start: date,
    vacations: list[Vacation] | None = None,
    max_solve_time_seconds: int = 120,
    random_seed: int | None = None,
    previous_context: PreviousPlanContext | None = None,
    pre_assigned: list[PreAssignedShift] | None = None,
    config: SchedulerConfig | None = None,
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
    if pre_assigned is None:
        pre_assigned = []
    if config is None:
        config = SchedulerConfig()

    model = cp_model.CpModel()

    # Derive holiday dates from pre-assigned shifts for shift generation
    holiday_dates = get_pre_assigned_holiday_dates(pre_assigned)

    # Generate all shifts for the quarter (including holiday Sunday-pattern shifts)
    shifts = generate_quarter_shifts(quarter_start, holiday_dates=holiday_dates)
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

    # Block pre-arrival dates for new employees.
    # Any date before available_from (up to quarter_end) is treated as unavailable.
    # This handles both mid-quarter arrivals and available_from > quarter_end (fully absent).
    for staff in staff_list:
        if staff.available_from is not None and staff.available_from > quarter_start:
            block_end = min(staff.available_from - timedelta(days=1), quarter_end)
            current = quarter_start
            while current <= block_end:
                staff_vacation_dates[staff.identifier].add(current)
                current += timedelta(days=1)

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

    # New employees (available_from within the planning period) always start
    # with a clean slate regardless of any prior carry-forward entry.
    for staff in staff_list:
        if (
            staff.available_from is not None
            and quarter_start <= staff.available_from <= quarter_end
        ):
            carry_forward_deltas[staff.identifier] = 0.0

    # Separate shifts by category
    weekend_shifts = [s for s in shifts if s.is_weekend_shift()]
    regular_weekend_shifts = [s for s in weekend_shifts if not s.is_intern_weekend_shift()]
    intern_weekend_shifts = [s for s in weekend_shifts if s.is_intern_weekend_shift()]
    intern_sat_shifts = [s for s in intern_weekend_shifts if s.shift_type == ShiftType.SATURDAY_INTERN]
    night_shifts = [s for s in shifts if s.is_night_shift()]

    # Staff subsets
    intern_staff = [s for s in staff_list if s.beruf == Beruf.INTERN]
    vet_staff = [s for s in staff_list if s.beruf == Beruf.VET]

    # Night shifts categorized into open and closed nights
    open_nights = [s for s in night_shifts if s.is_open_night()]
    closed_nights = [s for s in night_shifts if s.is_closed_night()]

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
    # PRE-ASSIGNED (FIXED) SHIFTS
    # =========================================================================
    # Pin decision variables for pre-assigned shifts (holidays, external process)
    pre_assigned_keys: set[tuple[str, date, ShiftType]] = set()
    for pa in pre_assigned:
        key = (pa.staff_identifier, pa.shift_date, pa.shift_type)
        if key in x:
            model.Add(x[key] == 1)
            pre_assigned_keys.add(key)
        else:
            # Variable doesn't exist — staff may be on vacation or ineligible.
            # Create the variable so the assignment can still be recorded,
            # but only if the shift exists in our shift list.
            shift_exists = any(
                s.shift_date == pa.shift_date and s.shift_type == pa.shift_type
                for s in shifts
            )
            if shift_exists:
                x[key] = model.NewBoolVar(
                    f"x_{pa.staff_identifier}_{pa.shift_date}_{pa.shift_type.value}"
                )
                model.Add(x[key] == 1)
                pre_assigned_keys.add(key)

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

    # 1. Weekend shift coverage
    # Regular TFA/Azubi shifts: default exactly 1 person per shift.
    # Pre-assigned holidays may have >1 person pinned; adjust target accordingly.
    pre_assigned_count: dict[tuple[date, ShiftType], int] = {}
    for pa in pre_assigned:
        key = (pa.shift_date, pa.shift_type)
        pre_assigned_count[key] = pre_assigned_count.get(key, 0) + 1
    pre_assigned_shift_slots: set[tuple[date, ShiftType]] = set(pre_assigned_count.keys())

    for shift in regular_weekend_shifts:
        staff_for_shift = [
            x[(s.identifier, shift.shift_date, shift.shift_type)]
            for s in staff_list
            if (s.identifier, shift.shift_date, shift.shift_type) in x
        ]
        if staff_for_shift:
            target = pre_assigned_count.get(
                (shift.shift_date, shift.shift_type), 1
            )
            model.Add(sum(staff_for_shift) == target)

    # Intern weekend shifts (soft coverage: at most 1 Intern per shift)
    if intern_staff:
        for shift in intern_weekend_shifts:
            staff_for_shift = [
                x[(s.identifier, shift.shift_date, shift.shift_type)]
                for s in intern_staff
                if (s.identifier, shift.shift_date, shift.shift_type) in x
            ]
            if staff_for_shift:
                model.Add(sum(staff_for_shift) <= 1)

        # 1b. Intern coupled weekend blocks: Saturday == Sunday for same Intern
        # Vacation guard: If unavailable on one day, cannot work the other day either
        for sat_shift in intern_sat_shifts:
            d_sat = sat_shift.shift_date
            d_sun = d_sat + timedelta(days=1)
            for s in intern_staff:
                sat_key = (s.identifier, d_sat, ShiftType.SATURDAY_INTERN)
                sun_key = (s.identifier, d_sun, ShiftType.SUNDAY_INTERN)
                if sat_key in x and sun_key in x:
                    model.Add(x[sat_key] == x[sun_key])
                elif sat_key in x:
                    model.Add(x[sat_key] == 0)
                elif sun_key in x:
                    model.Add(x[sun_key] == 0)

        # Monthly cap: max 1 coupled weekend (Saturday + Sunday) per calendar month per Intern
        intern_sat_by_month: dict[tuple[int, int], list[date]] = defaultdict(list)
        for sat_shift in intern_sat_shifts:
            intern_sat_by_month[(sat_shift.shift_date.year, sat_shift.shift_date.month)].append(
                sat_shift.shift_date
            )

        for s in intern_staff:
            for _year_month, sat_dates in intern_sat_by_month.items():
                month_sat_vars = [
                    x[(s.identifier, d, ShiftType.SATURDAY_INTERN)]
                    for d in sat_dates
                    if (s.identifier, d, ShiftType.SATURDAY_INTERN) in x
                ]
                if month_sat_vars:
                    model.Add(sum(month_sat_vars) <= 1)

    # 1c. Tierarzt-Nachtdienst-Entlastung (Midweek Vet Night Shift Relief)
    # H-TA-1 (2-night atomic blocks), H-TA-3 (1x per 2 months), H-TA-4 (Cross-quarter transition)
    b_DiMi: dict[tuple[str, tuple[int, int]], cp_model.BoolVar] = {}
    b_MiDo: dict[tuple[str, tuple[int, int]], cp_model.BoolVar] = {}
    vet_blocks_by_month: dict[tuple[str, tuple[int, int]], list[cp_model.BoolVar]] = defaultdict(list)
    all_vet_b_vars: list[cp_model.BoolVar] = []

    if vet_staff:
        # Collect distinct weeks that have any Di, Mi, or Do night in the quarter
        weeks_map: dict[tuple[int, int], dict[int, date]] = defaultdict(dict)
        for s in night_shifts:
            wd = s.shift_date.weekday()  # 1=Tue, 2=Wed, 3=Thu
            if wd in (1, 2, 3):
                iso = s.shift_date.isocalendar()
                w_key = (iso.year, iso.week)
                weeks_map[w_key][wd] = s.shift_date

        sorted_w_keys = sorted(weeks_map.keys())

        for w_key in sorted_w_keys:
            d_di = weeks_map[w_key].get(1)
            d_mi = weeks_map[w_key].get(2)
            d_do = weeks_map[w_key].get(3)

            for v in vet_staff:
                # b_DiMi exists iff both Tue and Wed exist in quarter and v can work both (no vacation)
                if (
                    d_di is not None
                    and (v.identifier, d_di, ShiftType.NIGHT_TUE_WED) in x
                    and d_mi is not None
                    and (v.identifier, d_mi, ShiftType.NIGHT_WED_THU) in x
                ):
                    b_dimi_var = model.NewBoolVar(f"b_dimi_{v.identifier}_{w_key[0]}_{w_key[1]}")
                    b_DiMi[(v.identifier, w_key)] = b_dimi_var
                    all_vet_b_vars.append(b_dimi_var)
                    vet_blocks_by_month[(v.identifier, (d_di.year, d_di.month))].append(b_dimi_var)

                # b_MiDo exists iff both Wed and Thu exist in quarter and v can work both (no vacation)
                if (
                    d_mi is not None
                    and (v.identifier, d_mi, ShiftType.NIGHT_WED_THU) in x
                    and d_do is not None
                    and (v.identifier, d_do, ShiftType.NIGHT_THU_FRI) in x
                ):
                    b_mido_var = model.NewBoolVar(f"b_mido_{v.identifier}_{w_key[0]}_{w_key[1]}")
                    b_MiDo[(v.identifier, w_key)] = b_mido_var
                    all_vet_b_vars.append(b_mido_var)
                    vet_blocks_by_month[(v.identifier, (d_mi.year, d_mi.month))].append(b_mido_var)

                # At most 1 block per week per vet: b_DiMi + b_MiDo <= 1
                v_week_b = [
                    b for b in [b_DiMi.get((v.identifier, w_key)), b_MiDo.get((v.identifier, w_key))]
                    if b is not None
                ]
                if len(v_week_b) > 1:
                    model.Add(sum(v_week_b) <= 1)

                # H-TA-1: Link shift decision variables x to block indicators
                if d_di is not None and (v.identifier, d_di, ShiftType.NIGHT_TUE_WED) in x:
                    if (v.identifier, w_key) in b_DiMi:
                        model.Add(x[(v.identifier, d_di, ShiftType.NIGHT_TUE_WED)] == b_DiMi[(v.identifier, w_key)])
                    else:
                        model.Add(x[(v.identifier, d_di, ShiftType.NIGHT_TUE_WED)] == 0)

                if d_mi is not None and (v.identifier, d_mi, ShiftType.NIGHT_WED_THU) in x:
                    active_wed = [
                        b for b in [b_DiMi.get((v.identifier, w_key)), b_MiDo.get((v.identifier, w_key))]
                        if b is not None
                    ]
                    if active_wed:
                        model.Add(x[(v.identifier, d_mi, ShiftType.NIGHT_WED_THU)] == sum(active_wed))
                    else:
                        model.Add(x[(v.identifier, d_mi, ShiftType.NIGHT_WED_THU)] == 0)

                if d_do is not None and (v.identifier, d_do, ShiftType.NIGHT_THU_FRI) in x:
                    if (v.identifier, w_key) in b_MiDo:
                        model.Add(x[(v.identifier, d_do, ShiftType.NIGHT_THU_FRI)] == b_MiDo[(v.identifier, w_key)])
                    else:
                        model.Add(x[(v.identifier, d_do, ShiftType.NIGHT_THU_FRI)] == 0)

            # At most 1 Vet block per week across all Tierärzte
            all_b_in_week = [
                b for v in vet_staff
                for b in [b_DiMi.get((v.identifier, w_key)), b_MiDo.get((v.identifier, w_key))]
                if b is not None
            ]
            if len(all_b_in_week) > 1:
                model.Add(sum(all_b_in_week) <= 1)

        # H-TA-3: 1x per 2 months per Vet (calendar month boundary)
        sorted_months = sorted(list({(s.shift_date.year, s.shift_date.month) for s in shifts}))
        for i in range(len(sorted_months) - 1):
            m1 = sorted_months[i]
            m2 = sorted_months[i + 1]
            if (m2[0] * 12 + m2[1]) == (m1[0] * 12 + m1[1]) + 1:
                for v in vet_staff:
                    m1_m2_blocks = (
                        vet_blocks_by_month.get((v.identifier, m1), [])
                        + vet_blocks_by_month.get((v.identifier, m2), [])
                    )
                    if len(m1_m2_blocks) > 1:
                        model.Add(sum(m1_m2_blocks) <= 1)

        # H-TA-4: Cross-quarter transition (PreviousPlanContext)
        if previous_context:
            active_vet_ids = set(getattr(previous_context, "vet_active_last_month_ids", []))
            last_prev_month = previous_context.quarter_end.month
            for ta in previous_context.trailing_assignments:
                if (
                    ta.shift_date.month == last_prev_month
                    and ta.shift_type in (
                        ShiftType.NIGHT_TUE_WED,
                        ShiftType.NIGHT_WED_THU,
                        ShiftType.NIGHT_THU_FRI,
                    )
                    and any(s.identifier == ta.staff_identifier and s.beruf == Beruf.VET for s in staff_list)
                ):
                    active_vet_ids.add(ta.staff_identifier)

            m_first = (quarter_start.year, quarter_start.month)
            for v in vet_staff:
                if v.identifier in active_vet_ids:
                    first_month_b = vet_blocks_by_month.get((v.identifier, m_first), [])
                    for b in first_month_b:
                        model.Add(b == 0)

    # 2. Night shift coverage:
    #    - Open nights (Sun-Mon, Mon-Tue): exactly 2 people, at least 1 TFA, max 1 Azubi
    #    - Closed nights: 1-2 people total, at least 1 non-Azubi
    for shift in night_shifts:
        shift_slot = (shift.shift_date, shift.shift_type)
        
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
        
        if shift_slot in pre_assigned_shift_slots:
            # Pre-assigned holiday night: enforce exact headcount, skip role rules
            target = pre_assigned_count[shift_slot]
            model.Add(sum(all_vars) == target)
        elif shift.is_open_night():
            # Open nights (Sun-Mon, Mon-Tue): exactly 2 persons, at least 1 TFA, max 1 Azubi
            tfa_vars = [
                x[(s.identifier, shift.shift_date, shift.shift_type)]
                for s in staff_list
                if (s.identifier, shift.shift_date, shift.shift_type) in x
                and s.beruf == Beruf.TFA
            ]
            # 1. Gesamtkopfzahl immer exakt 2 Personen
            model.Add(sum(all_vars) == 2)

            # 2. Mindestens 1 TFA zwingend erforderlich
            model.Add(sum(tfa_vars) >= 1)

            # 3. Maximal 1 Azubi (verhindert Azubi + Azubi)
            if azubi_vars:
                model.Add(sum(azubi_vars) <= 1)
        else:
            # Closed nights: 1-2 people total, at least 1 non-Azubi
            coverage_sum = sum(all_vars)
            model.Add(coverage_sum >= 1)
            model.Add(coverage_sum <= 2)
            if non_azubi_vars:
                model.Add(sum(non_azubi_vars) >= 1)
        
        # Link is_paired variable: paired iff 2 people assigned (for all night shifts)
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
    #    - nd_alone=False (non-Azubi) must be paired on closed nights
    #    - nd_alone=True (non-Azubi) must work COMPLETELY ALONE on closed nights
    
    for shift in night_shifts:
        if (shift.shift_date, shift.shift_type) in pre_assigned_shift_slots:
            continue  # Externally-assigned holidays bypass pairing rules
        
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
        
        # For closed nights (nd_alone strictly enforced):
        if shift.is_closed_night():
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
                model.Add(sum(intern_night_vars) >= config.intern_min_nights)
                model.Add(sum(intern_night_vars) <= config.intern_max_nights)

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
    # Pre-assigned holiday dates get a relaxed 1-week gap per stakeholder request
    pre_assigned_dates_by_staff: dict[str, set[date]] = {}
    for sid, d, _ in pre_assigned_keys:
        pre_assigned_dates_by_staff.setdefault(sid, set()).add(d)

    cross_quarter_violations = _add_block_constraints(
        model, x, staff_list, shifts, quarter_start, quarter_end,
        trailing_work_dates=trailing_work_dates or None,
        pre_assigned_dates_by_staff=pre_assigned_dates_by_staff,
        gap_days=config.block_gap_days,
        holiday_gap_days=config.holiday_gap_days,
        intern_block_gap_days=config.intern_block_gap_days,
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
            staff.identifier, vacations, quarter_start, quarter_end,
            effective_start=staff.available_from,
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
                    if staff.beruf == Beruf.AZUBI or (staff.beruf == Beruf.INTERN and shift.is_open_night()):
                        # Azubis (all nights) and Interns on open nights get full credit (2 half-units = 1.0 effective)
                        terms.append(2 * x[key])
                        night_terms.append(2 * x[key])
                    else:
                        # Non-Azubis on closed nights (and TFAs on open nights): paired = 1 half-unit (0.5), solo = 2 half-units (1.0)
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

    # Minimize cross-quarter block gap violations with absolute highest priority.
    # Weight is gap_diff * 10,000,000 to place it far above standard fairness metrics in scale.
    for viol_var, gap_diff in cross_quarter_violations:
        objective_terms.append(viol_var * gap_diff * 10000000)

    # Soft coverage fill incentive (W_unfilled = 100_000 per unassigned Intern weekend)
    if intern_staff:
        for sat_shift in intern_sat_shifts:
            d_sat = sat_shift.shift_date
            unfilled_we = model.NewBoolVar(f"unfilled_intern_we_{d_sat}")
            intern_sat_vars = [
                x[(s.identifier, d_sat, ShiftType.SATURDAY_INTERN)]
                for s in intern_staff
                if (s.identifier, d_sat, ShiftType.SATURDAY_INTERN) in x
            ]
            model.Add(sum(intern_sat_vars) + unfilled_we == 1)
            objective_terms.append(100000 * unfilled_we)

    # Group staff by role for fairness within groups
    tfa_staff = [s for s in staff_list if s.beruf == Beruf.TFA]
    azubi_staff = [s for s in staff_list if s.beruf == Beruf.AZUBI]
    intern_staff = [s for s in staff_list if s.beruf == Beruf.INTERN]

    # For each group, add combined fairness objective
    for group_name, group in [("TFA", tfa_staff), ("Azubi", azubi_staff), ("Intern", intern_staff)]:
        if len(group) < 2:
            continue
        
        # Combined Notdienste fairness (weekends + nights together)
        # Track 1: For Interns, use night_half_counts (not pooled notdienst_half_counts)
        if group_name == "Intern":
            nd_eligible = [s for s in group if s.nd_possible]
            if len(nd_eligible) >= 2:
                _add_group_fairness_objective_with_presence(
                    model, objective_terms, night_half_counts, nd_eligible, 
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

    # Track 2: Intern Weekend Fairness (min-max range, W_intern_we_fairness = 100)
    if len(intern_staff) >= 2:
        max_we = model.NewIntVar(0, 50, "max_intern_we")
        min_we = model.NewIntVar(0, 50, "min_intern_we")
        for s in intern_staff:
            model.Add(max_we >= weekend_half_counts[s.identifier])
            model.Add(min_we <= weekend_half_counts[s.identifier])
        we_range = model.NewIntVar(0, 50, "range_intern_we")
        model.Add(we_range == max_we - min_we)
        objective_terms.append(100 * we_range)

    # Secondary Spacing Preference: push night blocks away from weekend blocks (>= 14 days)
    W_intern_spacing = 5
    for s in intern_staff:
        for sat_shift in intern_sat_shifts:
            sat_key = (s.identifier, sat_shift.shift_date, sat_shift.shift_type)
            if sat_key not in x:
                continue
            d_sat = sat_shift.shift_date
            for n_shift in night_shifts:
                n_key = (s.identifier, n_shift.shift_date, n_shift.shift_type)
                if n_key not in x:
                    continue
                d_night = n_shift.shift_date
                gap = abs((d_night - d_sat).days)
                if 10 <= gap < 14:
                    close_var = model.NewBoolVar(
                        f"close_intern_{s.identifier}_{d_sat}_{d_night}"
                    )
                    model.Add(x[sat_key] + x[n_key] - 1 <= close_var)
                    objective_terms.append(W_intern_spacing * (14 - gap) * close_var)

    # -------------------------------------------------------------------------
    # Tierarzt Relief & Fairness Objectives (PRD 4.3)
    # -------------------------------------------------------------------------
    # 1. Primary: Maximize Vet relief blocks (W_vet = 100_000)
    for b in all_vet_b_vars:
        objective_terms.append(-100000 * b)

    # 2. Secondary: Vet block fairness across available Tierärzte (W_vet_fairness = 500)
    if len(vet_staff) >= 2 and vet_staff:
        vet_block_counts: dict[str, cp_model.IntVar] = {}
        for v in vet_staff:
            v_all_b = [
                b for w_key in sorted_w_keys
                for b in [b_DiMi.get((v.identifier, w_key)), b_MiDo.get((v.identifier, w_key))]
                if b is not None
            ]
            v_cnt = model.NewIntVar(0, len(sorted_w_keys), f"vet_blocks_{v.identifier}")
            model.Add(v_cnt == sum(v_all_b))
            vet_block_counts[v.identifier] = v_cnt

        max_vb = model.NewIntVar(0, len(sorted_w_keys), "max_vet_blocks")
        min_vb = model.NewIntVar(0, len(sorted_w_keys), "min_vet_blocks")
        for v in vet_staff:
            model.Add(max_vb >= vet_block_counts[v.identifier])
            model.Add(min_vb <= vet_block_counts[v.identifier])
        diff_vb = model.NewIntVar(0, len(sorted_w_keys), "range_vet_blocks")
        model.Add(diff_vb == max_vb - min_vb)
        objective_terms.append(500 * diff_vb)

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

    progress = _SchedulingProgressCallback()
    status = solver.Solve(model, progress)

    if status == cp_model.OPTIMAL or status == cp_model.FEASIBLE:
        # Extract solution
        schedule = _extract_schedule(
            solver, x, is_paired, shifts, quarter_start, quarter_end,
            pre_assigned_keys=pre_assigned_keys,
        )

        # Validate (should pass, but good to confirm)
        validation = validate_schedule(schedule, staff_list, config=config)
        penalty = validation.soft_penalty

        return SolverResult(
            success=True,
            schedules=[schedule],
            penalties=[penalty],
            unsatisfiable_constraints=[],
            convergence_log=progress.solutions,
        )
    else:
        # Infeasible or timeout
        status_name = solver.StatusName(status)
        unsatisfiable = _diagnose_infeasibility(
            model, staff_list, shifts, min_participation_info,
            vacations=vacations,
            pre_assigned=pre_assigned,
            quarter_start=quarter_start,
            quarter_end=quarter_end,
            config=config,
        )
        unsatisfiable.insert(
            0,
            f"Solver-Status: {status_name} "
            f"(Wall-Time: {solver.WallTime():.1f}s)",
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
                        # Allow coupled Intern weekend pair (Sa_Intern on Sat and So_Intern on Sun)
                        is_coupled_intern_pair = (
                            (we_shift.shift_type == ShiftType.SATURDAY_INTERN
                             and other_shift.shift_type == ShiftType.SUNDAY_INTERN
                             and other_shift.shift_date == we_shift.shift_date + timedelta(days=1))
                            or
                            (we_shift.shift_type == ShiftType.SUNDAY_INTERN
                             and other_shift.shift_type == ShiftType.SATURDAY_INTERN
                             and other_shift.shift_date == we_shift.shift_date - timedelta(days=1))
                        )
                        if is_coupled_intern_pair:
                            continue

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
    pre_assigned_dates_by_staff: dict[str, set[date]] | None = None,
    gap_days: int = 21,
    holiday_gap_days: int = 7,
    intern_block_gap_days: int = 10,
) -> list[tuple[cp_model.IntVar, int]]:
    """Add block gap constraints.

    The constraint: if you have blocks B1 and B2, and B2 starts
    within GAP days of B1's START, that's a violation.

    Default GAP is 21 days (3 weeks) for TFA/Azubi, and 10 days for
    Interns (intern_block_gap_days). When a block starts on a
    pre-assigned (holiday) date for that staff member, the gap to/from
    that block is relaxed to 7 days (1 week).

    Implementation: For each potential block-start day D (where we work but didn't
    work D-1), we forbid working on any day in (D+2, D+GAP-1) that would also be a
    block-start (i.e., without working the day before).

    When trailing_work_dates is provided, injects fixed work-day variables
    from the previous quarter (last 21 days) so the gap is enforced across
    the quarter boundary.
    """
    HOLIDAY_GAP = holiday_gap_days

    if pre_assigned_dates_by_staff is None:
        pre_assigned_dates_by_staff = {}

    cross_quarter_violations: list[tuple[cp_model.BoolVar, int]] = []

    # Group shifts by date
    shifts_by_date: dict[date, list[Shift]] = defaultdict(list)
    for s in shifts:
        shifts_by_date[s.shift_date].append(s)

    all_dates = sorted(shifts_by_date.keys())

    for staff in staff_list:
        if staff.beruf == Beruf.VET:
            continue
        staff_gap_days = (
            intern_block_gap_days
            if staff.beruf == Beruf.INTERN
            else gap_days
        )

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
                if (quarter_start - d).days <= staff_gap_days and d < quarter_start:
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

        # Enforce block gap: default 21 days for TFA/Azubi, 10 days for Interns,
        # relaxed to 7 if either block starts on a pre-assigned (holiday) date for this staff.
        # Block-gap enforcement across quarter boundaries:
        #   Q2 → Q2: SKIP. Both block starts are fixed history (both = 1). Adding
        #            block_starts[d1] + block_starts[d2] <= 1 with both fixed=1
        #            creates an immediate contradiction.
        #   Q2 → Q3: ENFORCE. d1 is fixed=1, so the constraint reduces to
        #            block_starts[d2] <= 0, correctly restricting the Q3 date.
        #            This implements the rolling 3-week window across quarters.
        #   Q3 → Q3: ENFORCE (standard intra-quarter rest constraint).
        staff_pa_dates = pre_assigned_dates_by_staff.get(staff.identifier, set())
        block_start_dates = sorted(block_starts.keys())
        for i, d1 in enumerate(block_start_dates):
            for d2 in block_start_dates[i + 1:]:
                gap = (d2 - d1).days
                if gap >= staff_gap_days:
                    break  # No need to check further
                # Skip only when both dates are Q2 trailing (fixed history)
                if d1 < quarter_start and d2 < quarter_start:
                    continue
                # Use relaxed gap if either date is pre-assigned
                required_gap = (
                    HOLIDAY_GAP
                    if d1 in staff_pa_dates or d2 in staff_pa_dates
                    else staff_gap_days
                )
                if gap < required_gap:
                    is_cross_quarter = d1 < quarter_start and d2 >= quarter_start
                    if is_cross_quarter:
                        # Soften cross-quarter block constraint
                        violation = model.NewBoolVar(f"cross_quarter_viol_{staff.identifier}_{d1}_{d2}")
                        model.Add(block_starts[d1] + block_starts[d2] <= 1 + violation)
                        cross_quarter_violations.append((violation, required_gap - gap))
                    else:
                        # Both being block starts is forbidden (intra-quarter)
                        model.Add(block_starts[d1] + block_starts[d2] <= 1)

    return cross_quarter_violations


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
        if not staff.nd_possible or staff.beruf == Beruf.VET or staff.nd_max_consecutive is None:
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
        if not staff.nd_possible or staff.beruf == Beruf.VET:
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

        # Prepend trailing night dates as fixed variables.
        # These are committed history and only serve as adjacency context for the
        # first Q3 nights — they must NOT themselves be constrained to have adjacent
        # nights (their Q2 predecessor may be before the trailing cutoff window).
        num_trailing = 0
        if trailing_night_dates and staff.identifier in trailing_night_dates:
            trailing_vars: list[tuple[date, cp_model.IntVar]] = []
            for d in trailing_night_dates[staff.identifier]:
                fixed = model.NewBoolVar(f"trail_minnd_{staff.identifier}_{d}")
                model.Add(fixed == 1)
                trailing_vars.append((d, fixed))
            num_trailing = len(trailing_vars)
            staff_night_vars = trailing_vars + staff_night_vars
        
        if len(staff_night_vars) < min_consecutive:
            continue
        
        # For min_consecutive=2: each assigned night needs at least 1 adjacent night
        # For min_consecutive=3: each assigned night needs to be part of a 3+ block
        # General approach: for each night, if assigned, there must be (min_consecutive-1)
        # other nights within the same contiguous block.
        # Skip trailing vars — they are historical facts, not decision variables.
        
        if min_consecutive == 2:
            # Simple case: each night needs at least one adjacent night
            for i, (d, var) in enumerate(staff_night_vars):
                if i < num_trailing:
                    continue  # Trailing nights are fixed history; skip constraint

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
            _add_min_block_constraint(model, staff_night_vars, min_consecutive,
                                      num_trailing=num_trailing)


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
    num_trailing: int = 0,
) -> None:
    """Add constraint that any assigned night must be part of a block of min_consecutive.
    
    For min_consecutive=3: if night i is assigned, then either:
    - nights i-2, i-1, i are all assigned (block ends at i), OR
    - nights i-1, i, i+1 are all assigned (i is in middle), OR
    - nights i, i+1, i+2 are all assigned (block starts at i)
    
    This generalizes to any min_consecutive value.
    
    num_trailing: number of leading entries that are trailing (historical) vars.
    These are skipped — they are fixed=1 history, not decision variables.
    """
    n = len(staff_night_vars)
    
    for i, (d, var) in enumerate(staff_night_vars):
        if i < num_trailing:
            continue  # Trailing nights are fixed history; skip constraint

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


def _count_consecutive_blocks(
    night_dates: list[date],
    min_block: int,
) -> int:
    """Count how many consecutive runs of length >= min_block exist in sorted dates."""
    if len(night_dates) < min_block:
        return 0
    blocks = 0
    run = 1
    for i in range(1, len(night_dates)):
        if (night_dates[i] - night_dates[i - 1]).days == 1:
            run += 1
        else:
            if run >= min_block:
                blocks += 1
            run = 1
    if run >= min_block:
        blocks += 1
    return blocks


# Minimum number of valid consecutive blocks needed to justify a hard
# participation constraint.  With fewer blocks the solver has almost no
# room to place the mandatory shift alongside 3-week-gap, abteilung
# and other hard constraints—so we fall back to the soft fairness
# objective instead.
_MIN_VIABLE_BLOCKS = 3


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
    
    Night participation is vacation-aware: only required if the remaining
    (non-vacation) night variables can form at least _MIN_VIABLE_BLOCKS
    consecutive blocks of nd_min_consecutive length, giving the solver
    enough room to place the shift alongside other hard constraints.
    
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
        
        if weekend_vars and staff.beruf not in (Beruf.INTERN, Beruf.VET):
            # Require at least 1 weekend shift
            model.Add(sum(weekend_vars) >= 1)
            info["weekend_required"] = True
        
        # Night participation: staff with nd_possible=True (excluding VET)
        if staff.nd_possible and staff.beruf != Beruf.VET:
            # Collect the dates for which decision variables exist
            # (vacation days are already excluded during variable creation)
            night_dates_with_vars: list[date] = sorted({
                s.shift_date
                for s in night_shifts
                if (staff.identifier, s.shift_date, s.shift_type) in x
            })
            night_vars = [
                x[(staff.identifier, s.shift_date, s.shift_type)]
                for s in night_shifts
                if (staff.identifier, s.shift_date, s.shift_type) in x
            ]
            
            min_consec = staff.nd_min_consecutive

            # Only require night participation if remaining dates can form
            # enough consecutive blocks to give the solver real flexibility.
            viable_blocks = _count_consecutive_blocks(
                night_dates_with_vars, min_consec
            )
            if night_vars and viable_blocks >= _MIN_VIABLE_BLOCKS:
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
    pre_assigned_keys: set[tuple[str, date, ShiftType]] | None = None,
) -> Schedule:
    """Extract Schedule object from solver solution."""
    assignments = []
    pre_assigned_keys = pre_assigned_keys or set()

    for shift in shifts:
        assigned_staff = []
        for (staff_id, shift_date, shift_type), var in x.items():
            if shift_date == shift.shift_date and shift_type == shift.shift_type:
                if solver.Value(var) == 1:
                    assigned_staff.append(staff_id)

        # Determine if paired (2 people on same night)
        paired = len(assigned_staff) >= 2 and shift.is_night_shift()

        for staff_id in assigned_staff:
            key = (staff_id, shift.shift_date, shift.shift_type)
            assignments.append(
                Assignment(
                    shift=shift,
                    staff_identifier=staff_id,
                    is_paired=paired,
                    is_pre_assigned=key in pre_assigned_keys,
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
    vacations: list[Vacation] | None = None,
    pre_assigned: list[PreAssignedShift] | None = None,
    quarter_start: date | None = None,
    quarter_end: date | None = None,
    config: SchedulerConfig | None = None,
) -> list[str]:
    """Attempt to diagnose why the model is infeasible.

    When vacation, pre_assigned, quarter_start and config are provided the
    analysis uses actual availability data (via analyze_capacity) for
    per-staff block feasibility instead of only inspecting nd_exceptions.
    """
    issues: list[str] = []

    # --- Capacity analysis with real availability data ---
    if vacations is not None and quarter_start is not None and config is not None:
        report = analyze_capacity(
            staff_list,
            vacations,
            pre_assigned or [],
            quarter_start,
            config,
        )
        for check in report.checks:
            if check.status in ("error", "warning"):
                issues.append(check.message)
                for detail in check.details:
                    issues.append(f"  → {detail}")

    # --- min_consecutive vs nd_exceptions (static check, no vacation data needed) ---
    for staff in staff_list:
        if not staff.nd_possible or staff.beruf == Beruf.VET:
            continue
        available_night_types = 7 - len(staff.nd_exceptions)
        if 0 < available_night_types < staff.nd_min_consecutive:
            issues.append(
                f"{staff.name} ({staff.beruf.value}): nur {available_night_types} verfügbare "
                f"Nacht-Wochentage, aber nd_min_consecutive={staff.nd_min_consecutive} — "
                f"nd_min_consecutive reduzieren oder nd_exceptions anpassen."
            )

    # --- Participation constraints vs limited availability ---
    if participation_info:
        for staff in staff_list:
            info = participation_info.get(staff.identifier, {})
            if info.get("night_required"):
                available_night_types = 7 - len(staff.nd_exceptions)
                if available_night_types <= 2:
                    issues.append(
                        f"{staff.name}: Nacht-Pflicht aktiv, aber nur "
                        f"{available_night_types} verfügbare Nacht-Wochentage."
                    )

    if not issues:
        issues.append(
            "Modell nicht lösbar. Constraint-Interaktionen, Urlaub-Konflikte "
            "prüfen oder Solver-Zeitlimit erhöhen."
        )

    return issues
