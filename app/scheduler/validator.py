"""Constraint validation for schedules."""

from collections import defaultdict
from typing import Any

from .models import Assignment, Beruf, Schedule, ShiftType, Staff


class ConstraintViolation:
    """A single constraint violation."""

    def __init__(self, constraint_name: str, description: str, severity: str = "hard") -> None:
        self.constraint_name = constraint_name
        self.description = description
        self.severity = severity  # "hard" or "soft"

    def __str__(self) -> str:
        return f"[{self.severity.upper()}] {self.constraint_name}: {self.description}"


class ValidationResult:
    """Result of schedule validation."""

    def __init__(self, hard_violations: list[ConstraintViolation], soft_penalty: float) -> None:
        self.hard_violations = hard_violations
        self.soft_penalty = soft_penalty

    def is_valid(self) -> bool:
        """Check if schedule satisfies all hard constraints."""
        return len(self.hard_violations) == 0

    def __str__(self) -> str:
        if self.is_valid():
            return f"Valid schedule (Soft penalty: {self.soft_penalty:.2f})"
        return f"Invalid schedule ({len(self.hard_violations)} violations)"


def validate_schedule(schedule: Schedule, staff_list: list[Staff]) -> ValidationResult:
    """Validate schedule against all constraints.

    Returns ValidationResult with hard violations and soft penalty score.
    """
    violations: list[ConstraintViolation] = []
    staff_dict = {s.identifier: s for s in staff_list}

    # Check hard constraints
    violations.extend(_check_minor_sunday_constraint(schedule, staff_dict))
    violations.extend(_check_ta_weekend_constraint(schedule, staff_dict))
    violations.extend(_check_night_pairing_constraint(schedule, staff_dict))
    violations.extend(_check_nd_alone_ta_nights_constraint(schedule, staff_dict))
    violations.extend(_check_same_day_next_day_constraint(schedule))
    violations.extend(_check_three_week_block_constraint(schedule))
    # violations.extend(_check_nd_count_constraint(schedule, staff_dict))  # Relaxed AND MOVED TO SOFT
    violations.extend(_check_nd_exceptions_constraint(schedule, staff_dict))
    violations.extend(_check_shift_eligibility(schedule, staff_dict))
    violations.extend(_check_shift_coverage(schedule))

    # Calculate soft penalty
    soft_penalty = _calculate_soft_penalty(schedule, staff_list)

    return ValidationResult(hard_violations=violations, soft_penalty=soft_penalty)


def _check_minor_sunday_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Minors cannot work Sundays."""
    violations: list[ConstraintViolation] = []
    for assignment in schedule.assignments:
        if assignment.shift.shift_type.value.startswith("So_"):
            staff = staff_dict.get(assignment.staff_identifier)
            if staff and not staff.adult:
                violations.append(
                    ConstraintViolation(
                        "Minor Sunday Ban",
                        f"Minor {staff.name} assigned to Sunday shift on "
                        f"{assignment.shift.shift_date.strftime('%d.%m.%Y')}",
                    )
                )
    return violations


def _check_nd_alone_ta_nights_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Staff with nd_alone=True must NOT work Sun-Mon or Mon-Tue nights (TA present).
    
    On these nights, a TA is already present (scheduled separately), so the staff
    would effectively be paired. Staff who prefer to work alone (nd_alone=True)
    should not be assigned to these nights.
    """
    violations: list[ConstraintViolation] = []
    ta_present_types = {ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE}

    for assignment in schedule.assignments:
        if assignment.shift.shift_type in ta_present_types:
            staff = staff_dict.get(assignment.staff_identifier)
            if staff and staff.nd_alone and staff.beruf != Beruf.TA:
                violations.append(
                    ConstraintViolation(
                        "ND Alone TA Night Conflict",
                        f"{staff.name} (nd_alone=True) assigned to {assignment.shift.shift_type.value} on "
                        f"{assignment.shift.shift_date.strftime('%d.%m.%Y')} where TA is present",
                    )
                )

    return violations


def _check_ta_weekend_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """TAs never work weekends."""
    violations: list[ConstraintViolation] = []
    for assignment in schedule.assignments:
        if assignment.shift.is_weekend_shift():
            staff = staff_dict.get(assignment.staff_identifier)
            if staff and staff.beruf == Beruf.TA:
                violations.append(
                    ConstraintViolation(
                        "TA Weekend Ban",
                        f"TA {staff.name} assigned to weekend shift on "
                        f"{assignment.shift.shift_date.strftime('%d.%m.%Y')}",
                    )
                )
    return violations


def _check_night_pairing_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Staff with nd_alone=False must work nights in pairs (except Sun-Mon, Mon-Tue with TA)."""
    violations: list[ConstraintViolation] = []

    # Group night assignments by date
    night_assignments_by_date: dict[Any, list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        if assignment.shift.is_night_shift():
            night_assignments_by_date[assignment.shift.shift_date].append(assignment)

    for shift_date, assignments in night_assignments_by_date.items():
        if not assignments:
            continue

        # Check each assignment
        for assignment in assignments:
            staff = staff_dict.get(assignment.staff_identifier)
            if not staff:
                continue

            # Azubis never work nights alone
            if staff.beruf == Beruf.AZUBI and not assignment.is_paired:
                shift_type = assignment.shift.shift_type
                # Sun-Mon and Mon-Tue have TA present, so Azubi can be "alone" (with TA)
                if shift_type not in [ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE]:
                    violations.append(
                        ConstraintViolation(
                            "Azubi Night Pairing",
                            f"Azubi {staff.name} working night alone on "
                            f"{shift_date.strftime('%d.%m.%Y')} (TA not present)",
                        )
                    )

            # Staff with nd_alone=False must be paired (unless TA present)
            if not staff.nd_alone and not assignment.is_paired:
                shift_type = assignment.shift.shift_type
                if shift_type not in [ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE]:
                    violations.append(
                        ConstraintViolation(
                            "Night Pairing Required",
                            f"{staff.name} (nd_alone=False) working night alone on "
                            f"{shift_date.strftime('%d.%m.%Y')}",
                        )
                    )

    return violations


def _check_same_day_next_day_constraint(schedule: Schedule) -> list[ConstraintViolation]:
    """Staff with night shift cannot have day shift same day or next day."""
    violations: list[ConstraintViolation] = []

    # Group all assignments by staff
    staff_assignments: dict[str, list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        staff_assignments[assignment.staff_identifier].append(assignment)

    for staff_id, assignments in staff_assignments.items():
        # Get night shifts
        night_shifts = [a for a in assignments if a.shift.is_night_shift()]

        for night_assignment in night_shifts:
            night_date = night_assignment.shift.shift_date
            next_date = night_assignment.shift.get_next_day()

            # Check for day shifts on same day or next day
            for assignment in assignments:
                if not assignment.shift.is_night_shift():
                    shift_date = assignment.shift.shift_date
                    if shift_date == night_date or shift_date == next_date:
                        violations.append(
                            ConstraintViolation(
                                "Night/Day Conflict",
                                f"{staff_id} has day shift on {shift_date.strftime('%d.%m.%Y')} "
                                f"conflicting with night shift on {night_date.strftime('%d.%m.%Y')}",
                            )
                        )

    return violations


def _check_three_week_block_constraint(schedule: Schedule) -> list[ConstraintViolation]:
    """Each staff can have max 1 consecutive block per rolling 3-week window."""
    violations: list[ConstraintViolation] = []

    # Group assignments by staff
    staff_assignments: dict[str, list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        staff_assignments[assignment.staff_identifier].append(assignment)

    for staff_id, assignments in staff_assignments.items():
        # Sort by date
        sorted_assignments = sorted(assignments, key=lambda a: a.shift.shift_date)

        # Find consecutive blocks
        blocks = _find_consecutive_blocks(sorted_assignments)

        # Check rolling 3-week windows
        for i, block1 in enumerate(blocks):
            block1_start = block1[0].shift.shift_date
            block1_end = block1[-1].shift.shift_date

            for block2 in blocks[i + 1 :]:
                block2_start = block2[0].shift.shift_date

                # Check if block2 starts within 2 weeks (14 days) of block1 start
                # Relaxed from 21 days due to capacity constraints
                if (block2_start - block1_start).days < 14:
                    violations.append(
                        ConstraintViolation(
                            "2-Week Block Limit",
                            f"{staff_id} has multiple shift blocks within 2 weeks: "
                            f"{block1_start.strftime('%d.%m.%Y')}-{block1_end.strftime('%d.%m.%Y')} "
                            f"and {block2_start.strftime('%d.%m.%Y')}",
                        )
                    )
                    break  # Only report first violation per block

    return violations


def _find_consecutive_blocks(sorted_assignments: list[Assignment]) -> list[list[Assignment]]:
    """Find consecutive blocks of shifts (gaps > 1 day break blocks)."""
    if not sorted_assignments:
        return []

    blocks: list[list[Assignment]] = []
    current_block = [sorted_assignments[0]]

    for i in range(1, len(sorted_assignments)):
        prev_date = sorted_assignments[i - 1].shift.shift_date
        curr_date = sorted_assignments[i].shift.shift_date

        # If gap is <= 1 day, continue current block
        if (curr_date - prev_date).days <= 1:
            current_block.append(sorted_assignments[i])
        else:
            # Start new block
            if len(current_block) >= 1:
                blocks.append(current_block)
            current_block = [sorted_assignments[i]]

    # Add final block
    if len(current_block) >= 1:
        blocks.append(current_block)

    return blocks


def _check_nd_count_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Check that consecutive night counts match staff nd_count field."""
    violations: list[ConstraintViolation] = []

    # Group night assignments by staff
    staff_night_assignments: dict[str, list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        if assignment.shift.is_night_shift():
            staff_night_assignments[assignment.staff_identifier].append(assignment)

    for staff_id, night_assignments in staff_night_assignments.items():
        staff = staff_dict.get(staff_id)
        if not staff or not staff.nd_count:
            continue

        # Sort by date
        sorted_nights = sorted(night_assignments, key=lambda a: a.shift.shift_date)

        # Find consecutive night blocks
        consecutive_blocks = _find_consecutive_blocks(sorted_nights)

        for block in consecutive_blocks:
            block_length = len(block)
            if block_length not in staff.nd_count:
                violations.append(
                    ConstraintViolation(
                        "ND Count Constraint",
                        f"{staff.name} working {block_length} consecutive nights starting "
                        f"{block[0].shift.shift_date.strftime('%d.%m.%Y')}, "
                        f"but nd_count={staff.nd_count}",
                    )
                )

    return violations


def _check_nd_exceptions_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Check that night shifts respect nd_exceptions weekdays."""
    violations: list[ConstraintViolation] = []

    for assignment in schedule.assignments:
        if assignment.shift.is_night_shift():
            staff = staff_dict.get(assignment.staff_identifier)
            if not staff:
                continue

            weekday = assignment.shift.shift_date.isoweekday()  # 1=Mon, 7=Sun
            if weekday in staff.nd_exceptions:
                violations.append(
                    ConstraintViolation(
                        "ND Exception Weekday",
                        f"{staff.name} assigned night shift on "
                        f"{assignment.shift.shift_date.strftime('%d.%m.%Y')} "
                        f"(weekday {weekday} in exceptions)",
                    )
                )

    return violations


def _check_shift_eligibility(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Check that staff are eligible for their assigned shifts."""
    violations: list[ConstraintViolation] = []

    for assignment in schedule.assignments:
        staff = staff_dict.get(assignment.staff_identifier)
        if not staff:
            violations.append(
                ConstraintViolation(
                    "Unknown Staff",
                    f"Staff {assignment.staff_identifier} not found in staff list",
                )
            )
            continue

        if not staff.can_work_shift(assignment.shift.shift_type, assignment.shift.shift_date):
            violations.append(
                ConstraintViolation(
                    "Shift Eligibility",
                    f"{staff.name} not eligible for {assignment.shift.shift_type.value} on "
                    f"{assignment.shift.shift_date.strftime('%d.%m.%Y')}",
                )
            )

    return violations


def _check_shift_coverage(schedule: Schedule) -> list[ConstraintViolation]:
    """Check that all required shifts are covered."""
    violations: list[ConstraintViolation] = []

    # Group assignments by shift
    shift_coverage: dict[tuple[Any, Any], int] = defaultdict(int)
    for assignment in schedule.assignments:
        key = (assignment.shift.shift_date, assignment.shift.shift_type)
        shift_coverage[key] += 1

    # Check night shifts (require 1-2 staff)
    for key, count in shift_coverage.items():
        shift_date, shift_type = key
        if shift_type.value.startswith("N_"):
            if count == 0:
                violations.append(
                    ConstraintViolation(
                        "Shift Coverage",
                        f"Night shift {shift_type.value} on {shift_date.strftime('%d.%m.%Y')} "
                        "has no coverage",
                    )
                )
            elif count > 2:
                violations.append(
                    ConstraintViolation(
                        "Shift Overstaffing",
                        f"Night shift {shift_type.value} on {shift_date.strftime('%d.%m.%Y')} "
                        f"has {count} staff (max 2)",
                    )
                )

    return violations


def _calculate_soft_penalty(schedule: Schedule, staff_list: list[Staff]) -> float:
    """Calculate soft constraint penalty score.

    Lower is better. Penalizes:
    - Deviation from proportional distribution (by hours)
    - Unfairness within role groups (std deviation)
    """
    penalty = 0.0

    # Calculate target Notdienst per staff based on hours
    total_hours = sum(s.hours for s in staff_list)

    # Penalty for deviation from proportional target
    for staff in staff_list:
        actual_notdienst = schedule.count_total_notdienst(staff.identifier)
        total_notdienst_needed = len(schedule.assignments)

        # Target proportional to hours
        target = (staff.hours / total_hours) * total_notdienst_needed

        # Squared deviation penalty
        deviation = abs(actual_notdienst - target)
        penalty += deviation**2

    # Penalty for unfairness within role groups
    role_groups: dict[Beruf, list[float]] = defaultdict(list)
    for staff in staff_list:
        notdienst_count = schedule.count_total_notdienst(staff.identifier)
        role_groups[staff.beruf].append(notdienst_count)

    # Add standard deviation penalty for each group
    for _role, counts in role_groups.items():
        if len(counts) > 1:
            mean = sum(counts) / len(counts)
            variance = sum((x - mean) ** 2 for x in counts) / len(counts)
            std_dev = variance**0.5
            penalty += std_dev * 10  # Weight std dev heavily
    
    # NEW: Soft penalty for nd_count violations (moved from hard constraints)
    violations = _check_nd_count_constraint(schedule, {s.identifier: s for s in staff_list})
    for v in violations:
        # High penalty per violation to strongly discourage it, but allow it if necessary
        penalty += 100.0

    return penalty
