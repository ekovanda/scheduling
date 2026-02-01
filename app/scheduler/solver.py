"""Heuristic solver for Notdienst scheduling."""

import random
from collections import defaultdict
from copy import deepcopy
from datetime import date, timedelta
from enum import Enum

from .models import Assignment, Beruf, Schedule, Shift, ShiftType, Staff, Vacation, generate_quarter_shifts
from .validator import validate_schedule


class SolverBackend(str, Enum):
    """Available solver backends."""

    HEURISTIC = "heuristic"
    CPSAT = "cpsat"


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
        self.schedules = schedules  # Ranked by penalty (best first)
        self.penalties = penalties
        self.unsatisfiable_constraints = unsatisfiable_constraints

    def get_best_schedule(self) -> Schedule | None:
        """Get the best schedule (lowest penalty)."""
        return self.schedules[0] if self.schedules else None


def _calculate_fte_load(
    staff: Staff,
    staff_assignments: dict[str, list[Assignment]],
    shift_type: str = "all",
) -> float:
    """Calculate FTE-normalized load for a staff member.
    
    Args:
        staff: Staff member
        staff_assignments: Current assignment map
        shift_type: "all", "night", or "weekend"
    
    Returns:
        Load normalized to 40h FTE (higher = more loaded)
    """
    assignments = staff_assignments.get(staff.identifier, [])
    
    if shift_type == "night":
        # Effective nights: paired = 0.5, solo = 1.0
        count = sum(0.5 if a.is_paired else 1.0 for a in assignments if a.shift.is_night_shift())
    elif shift_type == "weekend":
        count = sum(1 for a in assignments if a.shift.is_weekend_shift())
    else:
        # Total: weekends + effective nights
        weekend_count = sum(1 for a in assignments if a.shift.is_weekend_shift())
        night_count = sum(0.5 if a.is_paired else 1.0 for a in assignments if a.shift.is_night_shift())
        count = weekend_count + night_count
    
    if staff.hours <= 0:
        return float('inf')  # Avoid division by zero
    
    return (count / staff.hours) * 40


def _select_fairest_staff(
    eligible: list[Staff],
    staff_assignments: dict[str, list[Assignment]],
    load_type: str = "all",
) -> Staff:
    """Select staff member with lowest load, with randomized tie-breaking.
    
    Args:
        eligible: List of eligible staff members
        staff_assignments: Current assignment map
        load_type: Type of load to consider ("all", "night", "weekend")
    
    Returns:
        Selected staff member (fairest choice with random tie-break)
    """
    if not eligible:
        raise ValueError("No eligible staff to select from")
    
    # Calculate load for each eligible staff
    loads = [(s, _calculate_fte_load(s, staff_assignments, load_type)) for s in eligible]
    
    # Find minimum load
    min_load = min(load for _, load in loads)
    
    # Get all staff with minimum load (ties)
    tied_staff = [s for s, load in loads if abs(load - min_load) < 0.001]
    
    # Randomized tie-breaking to avoid CSV order bias
    return random.choice(tied_staff)


def generate_schedule(
    staff_list: list[Staff],
    quarter_start: date,
    vacations: list[Vacation] | None = None,
    max_iterations: int = 2000,
    random_seed: int | None = None,
    backend: SolverBackend = SolverBackend.HEURISTIC,
) -> SolverResult:
    """Generate schedule using the specified backend.

    Args:
        staff_list: List of staff members
        quarter_start: Start date of quarter (e.g., April 1, 2026)
        vacations: List of vacation periods (staff unavailability)
        max_iterations: Max local search iterations (heuristic) or solve time seconds (cpsat)
        random_seed: Random seed for reproducibility
        backend: Which solver to use (heuristic or cpsat)

    Returns:
        SolverResult with best schedules or unsatisfiable constraints
    """
    if vacations is None:
        vacations = []
    
    if backend == SolverBackend.CPSAT:
        from .solver_cpsat import generate_schedule_cpsat

        return generate_schedule_cpsat(
            staff_list,
            quarter_start,
            vacations=vacations,
            max_solve_time_seconds=max(60, max_iterations // 20),  # Scale iterations to time
            random_seed=random_seed,
        )

    # Default: heuristic solver
    if random_seed is not None:
        random.seed(random_seed)

    # Generate all shifts for the quarter
    shifts = generate_quarter_shifts(quarter_start)
    quarter_end = quarter_start  # Will be set by last shift date
    if shifts:
        quarter_end = max(s.shift_date for s in shifts)

    # Greedy phase: initial assignment
    schedule = _greedy_assignment(staff_list, shifts, quarter_start, quarter_end)

    # Validate initial schedule
    validation = validate_schedule(schedule, staff_list)
    if not validation.is_valid():
        # Try to identify unsatisfiable constraints
        unsatisfiable = [str(v) for v in validation.hard_violations[:10]]  # Limit to 10
        return SolverResult(
            success=False, schedules=[], penalties=[], unsatisfiable_constraints=unsatisfiable
        )

    # Local search phase: improve soft constraints
    best_penalty = validation.soft_penalty
    candidates: list[tuple[Schedule, float]] = [(schedule, best_penalty)]

    for iteration in range(max_iterations):
        # Choose move type: 40% fairness-targeted, 30% swap, 30% shift
        r = random.random()
        if r < 0.4:
            new_schedule = _try_fairness_move(schedule, staff_list)
        elif r < 0.7:
            new_schedule = _try_swap_move(schedule, staff_list)
        else:
            new_schedule = _try_shift_move(schedule, staff_list)

        if new_schedule is None:
            continue

        # Validate new schedule
        new_validation = validate_schedule(new_schedule, staff_list)
        if new_validation.is_valid():
            new_penalty = new_validation.soft_penalty

            # Accept if better
            if new_penalty < best_penalty:
                schedule = new_schedule
                best_penalty = new_penalty
                candidates.append((new_schedule, new_penalty))

                # Keep only top 5 candidates
                candidates = sorted(candidates, key=lambda x: x[1])[:5]

            # Simulated annealing: accept worse with probability
            elif random.random() < _acceptance_probability(
                best_penalty, new_penalty, iteration, max_iterations
            ):
                schedule = new_schedule

    # Return top 3 unique schedules
    unique_schedules = []
    unique_penalties = []
    for sched, penalty in candidates[:3]:
        if penalty not in unique_penalties:
            unique_schedules.append(sched)
            unique_penalties.append(penalty)

    return SolverResult(
        success=True,
        schedules=unique_schedules,
        penalties=unique_penalties,
        unsatisfiable_constraints=[],
    )


def _is_block_compatible(
    staff_id: str,
    check_date: date,
    staff_assignments: dict[str, list[Assignment]],
    ignore_continuity: bool = False,
) -> bool:
    """Check if assigning check_date violates the 2-week block constraint.

    If ignore_continuity is True, we don't check for continuity (useful for Sat/Sun shifts).
    If ignore_continuity is False (default), we allow dates that are adjacent to existing blocks (extending them).
    """
    sorted_assigns = sorted(staff_assignments.get(staff_id, []), key=lambda a: a.shift.shift_date)
    if not sorted_assigns:
        return True

    # Find the latest block's end date
    # (Simplified: just check last assignment if we assume chronological processing)
    # However, since we process Sat then Sun then Night, order isn't strictly chronological in execution
    # but strictly sorted_dates logic helps.
    
    # Let's look at all distinct blocks
    last_assignment = sorted_assigns[-1]
    last_date = last_assignment.shift.shift_date

    # If extending last block (adjacent date)
    if not ignore_continuity and abs((check_date - last_date).days) <= 1:
        return True

    # New block start? Check distance from start of last block
    # Find start of last block
    block_start = last_date
    for i in range(len(sorted_assigns) - 2, -1, -1):
        curr = sorted_assigns[i].shift.shift_date
        next_d = sorted_assigns[i + 1].shift.shift_date
        if (next_d - curr).days > 1:
            break
        block_start = curr
    
    # Current constraint: 2 weeks (14 days)
    if (check_date - block_start).days < 14:
        return False
        
    return True


def _greedy_assignment(
    staff_list: list[Staff], shifts: list[Shift], quarter_start: date, quarter_end: date
) -> Schedule:
    """Greedy assignment phase with fairness and block logic.

    Priorities:
    - Azubi minors get proportionally more Saturdays
    - Night shifts respect nd_max_consecutive blocking (continuity)
    - Night shifts pair staff with nd_alone=False
    """
    schedule = Schedule(quarter_start=quarter_start, quarter_end=quarter_end, assignments=[])

    # Track assignments per staff for fairness
    staff_assignments: dict[str, list[Assignment]] = defaultdict(list)

    # Sort shifts by date
    sorted_shifts = sorted(shifts, key=lambda s: (s.shift_date, s.shift_type.value))

    # Separate shifts by type
    saturday_shifts = [s for s in sorted_shifts if s.shift_type.value.startswith("Sa_")]
    sunday_shifts = [s for s in sorted_shifts if s.shift_type.value.startswith("So_")]
    night_shifts = [s for s in sorted_shifts if s.shift_type.value.startswith("N_")]

    # Assign Saturday shifts (prioritize minors for Sa_10-19)
    for shift in saturday_shifts:
        eligible = [s for s in staff_list if s.can_work_shift(shift.shift_type, shift.shift_date)]

        # Filter out staff who already have this date or next day assigned
        eligible = [
            s
            for s in eligible
            if not _has_conflict_on_date(s.identifier, shift.shift_date, staff_assignments)
            # Check block constraint (Sat is usually start of block, so ignore_continuity=False is fine but implicit)
            and _is_block_compatible(s.identifier, shift.shift_date, staff_assignments)
        ]

        if not eligible:
            continue

        # For Azubi shifts, prioritize minors
        if shift.shift_type == ShiftType.SATURDAY_10_19:
            minors = [s for s in eligible if not s.adult]
            if minors:
                eligible = minors

        # Pick staff with LOWEST WEEKEND FTE load for weekend-specific fairness
        # Use randomized tie-breaking to avoid CSV order bias
        selected = _select_fairest_staff(eligible, staff_assignments, "weekend")
        assignment = Assignment(shift=shift, staff_identifier=selected.identifier)
        schedule.assignments.append(assignment)
        staff_assignments[selected.identifier].append(assignment)

    # Assign Sunday shifts
    for shift in sunday_shifts:
        eligible = [s for s in staff_list if s.can_work_shift(shift.shift_type, shift.shift_date)]
        eligible = [
            s
            for s in eligible
            if not _has_conflict_on_date(s.identifier, shift.shift_date, staff_assignments)
            # Check block constraint
            and _is_block_compatible(s.identifier, shift.shift_date, staff_assignments)
        ]

        if not eligible:
            continue

        # Pick staff with LOWEST WEEKEND FTE load for weekend-specific fairness
        selected = _select_fairest_staff(eligible, staff_assignments, "weekend")
        assignment = Assignment(shift=shift, staff_identifier=selected.identifier)
        schedule.assignments.append(assignment)
        staff_assignments[selected.identifier].append(assignment)

    # Assign night shifts using Block-Aware Logic
    # Group by date
    night_shifts_map = defaultdict(list)
    for s in night_shifts:
        night_shifts_map[s.shift_date].append(s)
    
    sorted_dates = sorted(night_shifts_map.keys())
    
    # State: staff_id -> (current_block_length, last_worked_date)
    active_blocks: dict[str, tuple[int, date]] = {}

    for d in sorted_dates:
        shifts_for_day = night_shifts_map[d]
        if not shifts_for_day:
            continue
        shift = shifts_for_day[0]  # Assuming single night shift type per date

        ta_present = shift.shift_type in [ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE]

        # Cleanup stale blocks (only keep blocks from prev day)
        prev_day = d - timedelta(days=1)
        active_blocks = {
            sid: val for sid, val in active_blocks.items() 
            if val[1] == prev_day
        }

        # Build list of ALL eligible staff for today
        def is_eligible_for_night(staff: Staff) -> bool:
            return (
                staff.can_work_shift(shift.shift_type, d)
                and not _has_conflict_on_date(staff.identifier, d, staff_assignments)
                and not _has_conflict_on_date(staff.identifier, d + timedelta(days=1), staff_assignments)
                and _is_block_compatible(staff.identifier, d, staff_assignments)
                and not _has_reached_intern_night_cap(staff, staff_assignments)
            )

        all_eligible = [s for s in staff_list if is_eligible_for_night(s)]
        
        # Separate by nd_alone status
        solo_capable = [s for s in all_eligible if s.nd_alone]  # Can work alone
        pair_required = [s for s in all_eligible if not s.nd_alone]  # Must be paired

        # Check active blocks that need to continue
        candidates_must_solo = []
        candidates_must_pair = []
        candidates_can_solo = []
        candidates_can_pair = []

        for sid, (length, _) in active_blocks.items():
            staff_matches = [s for s in all_eligible if s.identifier == sid]
            if not staff_matches:
                continue
            staff = staff_matches[0]

            # Non-Azubis must do at least 2 consecutive nights; Azubis can do 1
            min_len = 1 if staff.beruf == Beruf.AZUBI else 2
            max_len = staff.nd_max_consecutive if staff.nd_max_consecutive else 7

            if length < min_len:
                if staff.nd_alone:
                    candidates_must_solo.append(staff)
                else:
                    candidates_must_pair.append(staff)
            elif length < max_len:
                if staff.nd_alone:
                    candidates_can_solo.append(staff)
                else:
                    candidates_can_pair.append(staff)

        # NEW eligible (not in active blocks)
        new_solo = [s for s in solo_capable if s.identifier not in active_blocks]
        new_pair = [s for s in pair_required if s.identifier not in active_blocks]

        # Sort new candidates by fairness
        new_solo.sort(key=lambda s: (_calculate_fte_load(s, staff_assignments, "night"), random.random()))
        new_pair.sort(key=lambda s: (_calculate_fte_load(s, staff_assignments, "night"), random.random()))

        assigned_staff: list[Staff] = []

        # === SELECTION LOGIC ===
        # Priority: Continue existing blocks, then start new ones
        # Rule: nd_alone=True works solo, nd_alone=False must be paired

        # 1. Handle MUST continues first
        # Solo MUST continues can always be added (they work alone)
        for s in candidates_must_solo:
            if not assigned_staff:  # Only 1 solo person needed
                assigned_staff.append(s)
                break

        # If we have a solo person, we're done
        if assigned_staff and assigned_staff[0].nd_alone:
            pass  # Solo coverage achieved
        else:
            # No solo assigned yet - try pair MUST continues
            # Only add pair-required if we can find 2 people
            if len(candidates_must_pair) >= 2:
                assigned_staff = candidates_must_pair[:2]
            elif len(candidates_must_pair) == 1:
                # Need to find a partner from CAN or NEW
                partner_pool = candidates_can_pair + candidates_can_solo + new_pair + new_solo
                if partner_pool:
                    assigned_staff = [candidates_must_pair[0], partner_pool[0]]
                # else: MUST pair person cannot continue - capacity issue

        # 2. If still no assignment, try CAN continues
        if not assigned_staff:
            if candidates_can_solo:
                assigned_staff = [candidates_can_solo[0]]
            elif len(candidates_can_pair) >= 2:
                assigned_staff = candidates_can_pair[:2]
            elif len(candidates_can_pair) == 1:
                partner_pool = new_pair + new_solo
                if partner_pool:
                    assigned_staff = [candidates_can_pair[0], partner_pool[0]]

        # 3. If still no assignment, start NEW block
        if not assigned_staff:
            if new_solo:
                assigned_staff = [new_solo[0]]
            elif len(new_pair) >= 2:
                assigned_staff = new_pair[:2]
            # else: No valid assignment possible - capacity issue

        # 4. For TA-present nights (Sun-Mon, Mon-Tue), 1 person is enough even if nd_alone=False
        if not assigned_staff and ta_present:
            # Anyone can work since TA is present
            all_candidates = candidates_must_solo + candidates_must_pair + candidates_can_solo + candidates_can_pair + new_solo + new_pair
            if all_candidates:
                assigned_staff = [all_candidates[0]]

        # Register assignments
        actual_paired = len(assigned_staff) > 1
        
        for s in assigned_staff:
            assign = Assignment(
                shift=shift, 
                staff_identifier=s.identifier, 
                is_paired=actual_paired
            )
            schedule.assignments.append(assign)
            staff_assignments[s.identifier].append(assign)
            
            # Update block state
            old_len = active_blocks.get(s.identifier, (0, date.min))[0]
            active_blocks[s.identifier] = (old_len + 1, d)

    return schedule


def _has_conflict_on_date(
    staff_id: str, check_date: date, staff_assignments: dict[str, list[Assignment]]
) -> bool:
    """Check if staff has assignment on this date."""
    for assignment in staff_assignments.get(staff_id, []):
        if assignment.shift.shift_date == check_date:
            return True
    return False


def _has_reached_intern_night_cap(
    staff: Staff, staff_assignments: dict[str, list[Assignment]], cap: int = 6
) -> bool:
    """Check if an Intern has reached their quarterly night cap.
    
    Interns should work max 2 nights/month = 6 nights/quarter.
    Non-Interns always return False (no cap).
    """
    if staff.beruf != Beruf.INTERN:
        return False
    
    night_count = sum(
        1 for a in staff_assignments.get(staff.identifier, [])
        if a.shift.is_night_shift()
    )
    return night_count >= cap


def _try_swap_move(schedule: Schedule, staff_list: list[Staff]) -> Schedule | None:
    """Try swapping two random assignments."""
    if len(schedule.assignments) < 2:
        return None

    new_schedule = deepcopy(schedule)

    # Pick two random assignments
    idx1, idx2 = random.sample(range(len(new_schedule.assignments)), 2)
    assign1 = new_schedule.assignments[idx1]
    assign2 = new_schedule.assignments[idx2]

    # Swap staff identifiers
    assign1.staff_identifier, assign2.staff_identifier = (
        assign2.staff_identifier,
        assign1.staff_identifier,
    )

    return new_schedule


def _try_shift_move(schedule: Schedule, staff_list: list[Staff]) -> Schedule | None:
    """Try reassigning one shift to a different staff member."""
    if not schedule.assignments:
        return None

    new_schedule = deepcopy(schedule)

    # Pick random assignment
    idx = random.randint(0, len(new_schedule.assignments) - 1)
    assignment = new_schedule.assignments[idx]

    # Find alternative staff
    eligible = [
        s
        for s in staff_list
        if s.can_work_shift(assignment.shift.shift_type, assignment.shift.shift_date)
        and s.identifier != assignment.staff_identifier
    ]

    if not eligible:
        return None

    # Pick random alternative
    new_staff = random.choice(eligible)
    assignment.staff_identifier = new_staff.identifier

    return new_schedule


def _try_fairness_move(schedule: Schedule, staff_list: list[Staff]) -> Schedule | None:
    """Targeted move: take shift from most overloaded and give to least loaded eligible."""
    if not schedule.assignments:
        return None

    new_schedule = deepcopy(schedule)
    staff_dict = {s.identifier: s for s in staff_list}

    # Build current assignment map
    staff_assignments: dict[str, list[Assignment]] = defaultdict(list)
    for a in new_schedule.assignments:
        staff_assignments[a.staff_identifier].append(a)

    # Find most overloaded staff (by FTE load)
    overloaded_candidates = []
    for staff in staff_list:
        load = _calculate_fte_load(staff, staff_assignments, "all")
        assignments = staff_assignments.get(staff.identifier, [])
        if assignments:
            overloaded_candidates.append((staff, load, assignments))

    if not overloaded_candidates:
        return None

    # Sort by load descending (most overloaded first)
    overloaded_candidates.sort(key=lambda x: x[1], reverse=True)

    # Try to reassign a shift from the most overloaded
    for overloaded_staff, _, assignments in overloaded_candidates[:5]:  # Top 5 overloaded
        # Pick a random assignment from this person
        if not assignments:
            continue
        victim_assignment = random.choice(assignments)

        # Find eligible replacements with lower load
        current_load = _calculate_fte_load(overloaded_staff, staff_assignments, "all")
        
        eligible = [
            s for s in staff_list
            if s.can_work_shift(victim_assignment.shift.shift_type, victim_assignment.shift.shift_date)
            and s.identifier != overloaded_staff.identifier
            and _calculate_fte_load(s, staff_assignments, "all") < current_load - 0.5  # Must be meaningfully lower
        ]

        if eligible:
            # Pick the least loaded eligible
            new_staff = min(eligible, key=lambda s: _calculate_fte_load(s, staff_assignments, "all"))
            
            # Find and update the assignment in new_schedule
            for a in new_schedule.assignments:
                if (a.shift.shift_date == victim_assignment.shift.shift_date 
                    and a.shift.shift_type == victim_assignment.shift.shift_type
                    and a.staff_identifier == overloaded_staff.identifier):
                    a.staff_identifier = new_staff.identifier
                    return new_schedule

    return None


def _acceptance_probability(
    current_penalty: float, new_penalty: float, iteration: int, max_iterations: int
) -> float:
    """Calculate acceptance probability for simulated annealing."""
    if new_penalty < current_penalty:
        return 1.0

    # Temperature decreases over time
    temperature = 100.0 * (1.0 - iteration / max_iterations)
    if temperature <= 0:
        return 0.0

    delta = new_penalty - current_penalty
    return min(1.0, (2.718 ** (-delta / temperature)))  # e^(-delta/T)
