"""Constraint validation for schedules."""

from collections import defaultdict
from datetime import timedelta
from typing import Any

from .models import Abteilung, Assignment, Beruf, Schedule, ShiftType, Staff


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
    violations.extend(_check_intern_weekend_constraint(schedule, staff_dict))
    violations.extend(_check_night_pairing_constraint(schedule, staff_dict))
    violations.extend(_check_nd_alone_improper_pairing(schedule, staff_dict))
    violations.extend(_check_same_day_double_booking(schedule))
    violations.extend(_check_intern_night_capacity(schedule, staff_dict))
    violations.extend(_check_same_day_next_day_constraint(schedule))
    violations.extend(_check_three_week_block_constraint(schedule))
    violations.extend(_check_weekend_isolation_constraint(schedule))
    violations.extend(_check_min_consecutive_nights_constraint(schedule, staff_dict))
    # violations.extend(_check_nd_max_consecutive_constraint(schedule, staff_dict))  # Relaxed to soft
    violations.extend(_check_nd_exceptions_constraint(schedule, staff_dict))
    violations.extend(_check_shift_eligibility(schedule, staff_dict))
    violations.extend(_check_shift_coverage(schedule))
    violations.extend(_check_abteilung_night_constraint(schedule, staff_dict))

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


def _check_same_day_double_booking(schedule: Schedule) -> list[ConstraintViolation]:
    """Check that no person has more than 1 shift on the same day."""
    violations: list[ConstraintViolation] = []

    # Group assignments by (staff, date)
    assignments_by_staff_date: dict[tuple[str, Any], list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        key = (assignment.staff_identifier, assignment.shift.shift_date)
        assignments_by_staff_date[key].append(assignment)

    for (staff_id, shift_date), assignments in assignments_by_staff_date.items():
        if len(assignments) > 1:
            shift_types = [a.shift.shift_type.value for a in assignments]
            violations.append(
                ConstraintViolation(
                    "Same Day Double Booking",
                    f"{staff_id} assigned to multiple shifts on "
                    f"{shift_date.strftime('%d.%m.%Y')}: {', '.join(shift_types)}",
                )
            )

    return violations


def _check_nd_alone_improper_pairing(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Staff with nd_alone=True must work ALONE on regular nights (not Sun-Mon, Mon-Tue).

    They cannot be paired with ANYONE on regular nights.
    Sun-Mon and Mon-Tue nights have a vet on-site, so nd_alone doesn't apply there.
    """
    violations: list[ConstraintViolation] = []
    ta_present_types = {ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE}

    # Group night assignments by (date, shift_type)
    night_assignments_by_shift: dict[tuple[Any, ShiftType], list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        if assignment.shift.is_night_shift():
            key = (assignment.shift.shift_date, assignment.shift.shift_type)
            night_assignments_by_shift[key].append(assignment)

    for (shift_date, shift_type), assignments in night_assignments_by_shift.items():
        # Skip vet-present nights (nd_alone doesn't apply there)
        if shift_type in ta_present_types:
            continue

        if len(assignments) < 2:
            continue

        # Check if any nd_alone=True staff is paired with ANYONE
        nd_alone_true_staff = []
        other_staff = []
        for a in assignments:
            staff = staff_dict.get(a.staff_identifier)
            if staff:
                if staff.nd_alone:
                    nd_alone_true_staff.append(staff.name)
                else:
                    other_staff.append(staff.name)

        # nd_alone=True staff cannot be paired with anyone on regular nights
        if nd_alone_true_staff and len(assignments) > 1:
            all_others = [name for name in nd_alone_true_staff[1:]] + other_staff
            violations.append(
                ConstraintViolation(
                    "ND Alone Improper Pairing",
                    f"Staff with nd_alone=True ({', '.join(nd_alone_true_staff)}) cannot be "
                    f"paired with anyone on regular nights. Found with: {', '.join(all_others)} on "
                    f"{shift_date.strftime('%d.%m.%Y')} {shift_type.value}",
                )
            )

    return violations


def _check_intern_night_capacity(schedule: Schedule, staff_dict: dict[str, Staff]) -> list[ConstraintViolation]:
    """Sun-Mon and Mon-Tue nights: exactly 1 non-Azubi + optional 0-1 Azubi.
    
    These nights have a vet on-site externally, so:
    - Exactly 1 non-Azubi (TFA or Intern) - NOT 2 non-Azubis
    - Optional: 1 Azubi can join for fairness (but not required)
    - Two Azubis cannot work together
    - Two non-Azubis cannot work together on these nights
    """
    violations: list[ConstraintViolation] = []
    vet_present_types = {ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE}

    # Group assignments by (date, shift_type)
    night_assignments_by_shift: dict[tuple[Any, ShiftType], list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        if assignment.shift.is_night_shift():
            key = (assignment.shift.shift_date, assignment.shift.shift_type)
            night_assignments_by_shift[key].append(assignment)

    for (shift_date, shift_type), assignments in night_assignments_by_shift.items():
        if shift_type not in vet_present_types:
            continue
        
        # Categorize staff
        non_azubis = []
        azubis = []
        for a in assignments:
            staff = staff_dict.get(a.staff_identifier)
            if staff:
                if staff.beruf == Beruf.AZUBI:
                    azubis.append(staff.name)
                else:
                    non_azubis.append(staff.name)
        
        # Must have exactly 1 non-Azubi
        if len(non_azubis) == 0:
            violations.append(
                ConstraintViolation(
                    "Intern Night No Non-Azubi",
                    f"Sun-Mon/Mon-Tue night on {shift_date.strftime('%d.%m.%Y')} has "
                    f"only Azubis ({', '.join(azubis)}), needs exactly 1 TFA or Intern",
                )
            )
        elif len(non_azubis) > 1:
            violations.append(
                ConstraintViolation(
                    "Vet Night Over Capacity",
                    f"Sun-Mon/Mon-Tue night on {shift_date.strftime('%d.%m.%Y')} has "
                    f"{len(non_azubis)} non-Azubis ({', '.join(non_azubis)}), max is 1",
                )
            )
        
        # Max 1 Azubi
        if len(azubis) > 1:
            violations.append(
                ConstraintViolation(
                    "Multiple Azubis on Night",
                    f"Night on {shift_date.strftime('%d.%m.%Y')} has multiple Azubis "
                    f"({', '.join(azubis)}), only 1 Azubi allowed per night",
                )
            )

    return violations


def _check_intern_weekend_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Interns never work weekends."""
    violations: list[ConstraintViolation] = []
    for assignment in schedule.assignments:
        if assignment.shift.is_weekend_shift():
            staff = staff_dict.get(assignment.staff_identifier)
            if staff and staff.beruf == Beruf.INTERN:
                violations.append(
                    ConstraintViolation(
                        "Intern Weekend Ban",
                        f"Intern {staff.name} assigned to weekend shift on "
                        f"{assignment.shift.shift_date.strftime('%d.%m.%Y')}",
                    )
                )
    return violations


def _check_night_pairing_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Check night pairing rules:
    - Azubis must always be paired with a non-Azubi (TFA or Intern)
    - Two Azubis can never work together
    - nd_alone=False staff must be paired (except Sun-Mon, Mon-Tue with Intern present)
    """
    violations: list[ConstraintViolation] = []
    intern_present_types = {ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE}

    # Group night assignments by (date, shift_type)
    night_assignments_by_shift: dict[tuple[Any, ShiftType], list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        if assignment.shift.is_night_shift():
            key = (assignment.shift.shift_date, assignment.shift.shift_type)
            night_assignments_by_shift[key].append(assignment)

    for (shift_date, shift_type), assignments in night_assignments_by_shift.items():
        if not assignments:
            continue

        # Categorize staff
        azubis = []
        non_azubis = []
        nd_alone_false_staff = []
        
        for assignment in assignments:
            staff = staff_dict.get(assignment.staff_identifier)
            if not staff:
                continue
            if staff.beruf == Beruf.AZUBI:
                azubis.append(staff)
            else:
                non_azubis.append(staff)
            if not staff.nd_alone:
                nd_alone_false_staff.append(staff)

        # Rule: Two Azubis can never be paired
        if len(azubis) > 1:
            azubi_names = [s.name for s in azubis]
            violations.append(
                ConstraintViolation(
                    "Multiple Azubis on Night",
                    f"Night on {shift_date.strftime('%d.%m.%Y')} {shift_type.value} has "
                    f"multiple Azubis ({', '.join(azubi_names)}), only 1 Azubi allowed",
                )
            )

        # Rule: Azubi must be paired with non-Azubi
        for azubi in azubis:
            if len(non_azubis) == 0:
                violations.append(
                    ConstraintViolation(
                        "Azubi Night Pairing",
                        f"Azubi {azubi.name} working night alone on "
                        f"{shift_date.strftime('%d.%m.%Y')} (no TFA/Intern present)",
                    )
                )

        # Rule: nd_alone=False must be paired (except intern-present nights)
        is_intern_present = shift_type in intern_present_types
        for staff in nd_alone_false_staff:
            # Skip Azubis (handled above)
            if staff.beruf == Beruf.AZUBI:
                continue
            # On regular nights, must be paired
            if not is_intern_present and len(assignments) < 2:
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
    """Each staff can have max 1 consecutive block per rolling 3-week window.
    
    Blocks must be separated by at least 21 days (from start to start).
    Note: Weekend shifts are already constrained to be isolated (single-shift blocks)
    by _check_weekend_isolation_constraint. This function handles the general case.
    """
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

        # Check rolling 2-week windows
        for i, block1 in enumerate(blocks):
            block1_start = block1[0].shift.shift_date
            block1_end = block1[-1].shift.shift_date

            for block2 in blocks[i + 1 :]:
                block2_start = block2[0].shift.shift_date

                # Check if block2 starts within 3 weeks (21 days) of block1 start
                if (block2_start - block1_start).days < 21:
                    violations.append(
                        ConstraintViolation(
                            "3-Week Block Limit",
                            f"{staff_id} has multiple shift blocks within 3 weeks: "
                            f"{block1_start.strftime('%d.%m.%Y')}-{block1_end.strftime('%d.%m.%Y')} "
                            f"and {block2_start.strftime('%d.%m.%Y')}",
                        )
                    )
                    break  # Only report first violation per block

    return violations


def _check_weekend_isolation_constraint(schedule: Schedule) -> list[ConstraintViolation]:
    """Weekend shifts must always be isolated (single-shift, not part of a block).
    
    A weekend shift cannot be adjacent (same day or next day) to any other shift
    for the same person. This prevents weekend shifts from being part of night blocks.
    """
    violations: list[ConstraintViolation] = []

    # Group assignments by staff
    staff_assignments: dict[str, list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        staff_assignments[assignment.staff_identifier].append(assignment)

    for staff_id, assignments in staff_assignments.items():
        # Get weekend shifts and all dates worked
        weekend_assignments = [a for a in assignments if a.shift.is_weekend_shift()]
        all_dates_worked = {a.shift.shift_date for a in assignments}

        for we_assignment in weekend_assignments:
            we_date = we_assignment.shift.shift_date
            prev_date = we_date - timedelta(days=1)
            next_date = we_date + timedelta(days=1)

            # Check if adjacent to another shift (forming a block)
            adjacent_worked = []
            if prev_date in all_dates_worked:
                adjacent_worked.append(prev_date.strftime('%d.%m.%Y'))
            if next_date in all_dates_worked:
                adjacent_worked.append(next_date.strftime('%d.%m.%Y'))

            if adjacent_worked:
                violations.append(
                    ConstraintViolation(
                        "Weekend Isolation",
                        f"{staff_id}'s weekend shift on {we_date.strftime('%d.%m.%Y')} "
                        f"({we_assignment.shift.shift_type.value}) is adjacent to shifts on "
                        f"{', '.join(adjacent_worked)}. Weekend shifts must be isolated.",
                    )
                )

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


def _check_min_consecutive_nights_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Non-Azubi staff (TFA, Intern) must work at least 2 consecutive nights."""
    violations: list[ConstraintViolation] = []

    # Group night assignments by staff
    staff_night_assignments: dict[str, list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        if assignment.shift.is_night_shift():
            staff_night_assignments[assignment.staff_identifier].append(assignment)

    for staff_id, night_assignments in staff_night_assignments.items():
        staff = staff_dict.get(staff_id)
        if not staff or staff.beruf == Beruf.AZUBI:
            continue  # Azubis can do single nights

        # Sort by date
        sorted_nights = sorted(night_assignments, key=lambda a: a.shift.shift_date)

        # Find consecutive night blocks
        consecutive_blocks = _find_consecutive_blocks(sorted_nights)

        for block in consecutive_blocks:
            block_length = len(block)
            if block_length < 2:
                violations.append(
                    ConstraintViolation(
                        "Min Consecutive Nights",
                        f"{staff.name} ({staff.beruf.value}) working only {block_length} "
                        f"consecutive night(s) starting "
                        f"{block[0].shift.shift_date.strftime('%d.%m.%Y')}, "
                        f"minimum is 2 for non-Azubi staff",
                    )
                )

    return violations


def _check_nd_max_consecutive_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Check that consecutive night counts don't exceed staff nd_max_consecutive."""
    violations: list[ConstraintViolation] = []

    # Group night assignments by staff
    staff_night_assignments: dict[str, list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        if assignment.shift.is_night_shift():
            staff_night_assignments[assignment.staff_identifier].append(assignment)

    for staff_id, night_assignments in staff_night_assignments.items():
        staff = staff_dict.get(staff_id)
        if not staff or staff.nd_max_consecutive is None:
            continue

        # Sort by date
        sorted_nights = sorted(night_assignments, key=lambda a: a.shift.shift_date)

        # Find consecutive night blocks
        consecutive_blocks = _find_consecutive_blocks(sorted_nights)

        for block in consecutive_blocks:
            block_length = len(block)
            if block_length > staff.nd_max_consecutive:
                violations.append(
                    ConstraintViolation(
                        "ND Max Consecutive",
                        f"{staff.name} working {block_length} consecutive nights starting "
                        f"{block[0].shift.shift_date.strftime('%d.%m.%Y')}, "
                        f"max is {staff.nd_max_consecutive}",
                    )
                )

    return violations


def _check_nd_count_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """DEPRECATED: Check that consecutive night counts match staff nd_count field.
    
    This is kept for backwards compatibility but now uses nd_max_consecutive.
    """
    # Delegate to the new function
    return _check_nd_max_consecutive_constraint(schedule, staff_dict)

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


def _check_abteilung_night_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Check abteilung separation on night shifts.
    
    Employees in the same abteilung (op or station) cannot:
    1. Work the same night shift together
    2. Work consecutive night shifts (day N and day N+1)
    
    Employees in abteilung="other" are exempt.
    """
    violations: list[ConstraintViolation] = []
    restricted_abteilungen = {Abteilung.OP, Abteilung.STATION}
    
    # Group night assignments by date
    night_assignments_by_date: dict[Any, list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        if assignment.shift.is_night_shift():
            night_assignments_by_date[assignment.shift.shift_date].append(assignment)
    
    sorted_dates = sorted(night_assignments_by_date.keys())
    
    for i, shift_date in enumerate(sorted_dates):
        assignments = night_assignments_by_date[shift_date]
        
        # Get staff with restricted abteilung for this night
        restricted_staff_today: dict[Abteilung, list[str]] = defaultdict(list)
        for a in assignments:
            staff = staff_dict.get(a.staff_identifier)
            if staff and staff.abteilung in restricted_abteilungen:
                restricted_staff_today[staff.abteilung].append(staff.name)
        
        # 1. Check same night: no two staff from same abteilung
        for abteilung, names in restricted_staff_today.items():
            if len(names) >= 2:
                violations.append(
                    ConstraintViolation(
                        "Abteilung Same Night",
                        f"Multiple {abteilung.value} staff ({', '.join(names)}) "
                        f"assigned to same night on {shift_date.strftime('%d.%m.%Y')}",
                    )
                )
        
        # 2. Check consecutive days: no two staff from same abteilung on consecutive days
        if i < len(sorted_dates) - 1:
            next_date = sorted_dates[i + 1]
            # Only check if dates are actually consecutive
            if (next_date - shift_date).days == 1:
                next_assignments = night_assignments_by_date[next_date]
                
                restricted_staff_tomorrow: dict[Abteilung, list[str]] = defaultdict(list)
                for a in next_assignments:
                    staff = staff_dict.get(a.staff_identifier)
                    if staff and staff.abteilung in restricted_abteilungen:
                        restricted_staff_tomorrow[staff.abteilung].append(staff.name)
                
                # Check for same abteilung on consecutive days (different people)
                for abteilung in restricted_abteilungen:
                    today_names = set(restricted_staff_today.get(abteilung, []))
                    tomorrow_names = set(restricted_staff_tomorrow.get(abteilung, []))
                    
                    # Find different people from same abteilung on consecutive days
                    # (same person on consecutive days is allowed and handled elsewhere)
                    different_people = today_names.symmetric_difference(tomorrow_names)
                    if today_names and tomorrow_names and different_people:
                        violations.append(
                            ConstraintViolation(
                                "Abteilung Consecutive Days",
                                f"Staff from {abteilung.value} on consecutive nights: "
                                f"{', '.join(today_names)} on {shift_date.strftime('%d.%m.%Y')} "
                                f"and {', '.join(tomorrow_names)} on {next_date.strftime('%d.%m.%Y')}",
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
    staff_dict = {s.identifier: s for s in staff_list}

    # Calculate target Notdienst per staff based on hours
    total_hours = sum(s.hours for s in staff_list)

    # Penalty for deviation from proportional target
    for staff in staff_list:
        actual_notdienst = schedule.count_total_notdienst(staff.identifier, staff)
        total_notdienst_needed = len(schedule.assignments)

        # Target proportional to hours
        target = (staff.hours / total_hours) * total_notdienst_needed

        # Squared deviation penalty
        deviation = abs(actual_notdienst - target)
        penalty += deviation**2

    # Penalty for unfairness within role groups
    role_groups: dict[Beruf, list[float]] = defaultdict(list)
    for staff in staff_list:
        notdienst_count = schedule.count_total_notdienst(staff.identifier, staff)
        role_groups[staff.beruf].append(notdienst_count)

    # Add standard deviation penalty for each group
    for _role, counts in role_groups.items():
        if len(counts) > 1:
            mean = sum(counts) / len(counts)
            variance = sum((x - mean) ** 2 for x in counts) / len(counts)
            std_dev = variance**0.5
            penalty += std_dev * 10  # Weight std dev heavily
    
    # NEW: Soft penalty for nd_count violations (moved from hard constraints)
    violations = _check_nd_count_constraint(schedule, staff_dict)
    for v in violations:
        # High penalty per violation to strongly discourage it, but allow it if necessary
        penalty += 100.0

    return penalty
