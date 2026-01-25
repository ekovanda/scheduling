"""Heuristic solver for Notdienst scheduling."""

import random
from collections import defaultdict
from copy import deepcopy
from datetime import date

from .models import Assignment, Schedule, Shift, ShiftType, Staff, generate_quarter_shifts
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
        self.schedules = schedules  # Ranked by penalty (best first)
        self.penalties = penalties
        self.unsatisfiable_constraints = unsatisfiable_constraints

    def get_best_schedule(self) -> Schedule | None:
        """Get the best schedule (lowest penalty)."""
        return self.schedules[0] if self.schedules else None


def generate_schedule(
    staff_list: list[Staff],
    quarter_start: date,
    max_iterations: int = 2000,
    random_seed: int | None = None,
) -> SolverResult:
    """Generate schedule using greedy + local search.

    Args:
        staff_list: List of staff members
        quarter_start: Start date of quarter (e.g., April 1, 2026)
        max_iterations: Max local search iterations
        random_seed: Random seed for reproducibility

    Returns:
        SolverResult with best schedules or unsatisfiable constraints
    """
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
        # Try random swap or shift move
        if random.random() < 0.5:
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


def _greedy_assignment(
    staff_list: list[Staff], shifts: list[Shift], quarter_start: date, quarter_end: date
) -> Schedule:
    """Greedy assignment phase with fairness logic.

    Priorities:
    - Azubi minors get proportionally more Saturdays
    - Night shifts pair staff with nd_alone=False
    - Respect nd_count and nd_exceptions
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
        ]

        if not eligible:
            continue

        # For Azubi shifts, prioritize minors
        if shift.shift_type == ShiftType.SATURDAY_10_19:
            minors = [s for s in eligible if not s.adult]
            if minors:
                eligible = minors

        # Pick staff with fewest assignments (fairness)
        selected = min(eligible, key=lambda s: len(staff_assignments[s.identifier]))
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
        ]

        if not eligible:
            continue

        # Pick staff with fewest assignments
        selected = min(eligible, key=lambda s: len(staff_assignments[s.identifier]))
        assignment = Assignment(shift=shift, staff_identifier=selected.identifier)
        schedule.assignments.append(assignment)
        staff_assignments[selected.identifier].append(assignment)

    # Assign night shifts (handle pairing)
    for shift in night_shifts:
        eligible = [s for s in staff_list if s.can_work_shift(shift.shift_type, shift.shift_date)]
        eligible = [
            s
            for s in eligible
            if not _has_conflict_on_date(s.identifier, shift.shift_date, staff_assignments)
            and not _has_conflict_on_date(s.identifier, shift.get_next_day(), staff_assignments)
        ]

        if not eligible:
            continue

        # Determine if this is a night with TA present (Sun-Mon, Mon-Tue)
        ta_present = shift.shift_type in [ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE]

        # Check if we need pairing
        solo_eligible = [s for s in eligible if s.nd_alone or ta_present]
        paired_eligible = [s for s in eligible if not s.nd_alone and not ta_present]

        # Try to assign solo worker first
        if solo_eligible:
            selected = min(solo_eligible, key=lambda s: len(staff_assignments[s.identifier]))
            assignment = Assignment(
                shift=shift, staff_identifier=selected.identifier, is_paired=False
            )
            schedule.assignments.append(assignment)
            staff_assignments[selected.identifier].append(assignment)

        # If we have paired_eligible, assign a pair
        elif len(paired_eligible) >= 2:
            # Pick two staff with fewest assignments
            sorted_paired = sorted(
                paired_eligible, key=lambda s: len(staff_assignments[s.identifier])
            )
            staff1, staff2 = sorted_paired[0], sorted_paired[1]

            assignment1 = Assignment(
                shift=shift, staff_identifier=staff1.identifier, is_paired=True
            )
            assignment2 = Assignment(
                shift=shift, staff_identifier=staff2.identifier, is_paired=True
            )
            schedule.assignments.append(assignment1)
            schedule.assignments.append(assignment2)
            staff_assignments[staff1.identifier].append(assignment1)
            staff_assignments[staff2.identifier].append(assignment2)

    return schedule


def _has_conflict_on_date(
    staff_id: str, check_date: date, staff_assignments: dict[str, list[Assignment]]
) -> bool:
    """Check if staff has assignment on this date."""
    for assignment in staff_assignments.get(staff_id, []):
        if assignment.shift.shift_date == check_date:
            return True
    return False


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
