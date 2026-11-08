"""Constraint validation for schedules."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Any

from .models import (
    Abteilung,
    Assignment,
    Beruf,
    PreviousPlanContext,
    Schedule,
    SchedulerConfig,
    ShiftType,
    Staff,
    generate_quarter_shifts,
)


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


@dataclass(frozen=True)
class CrossQuarterBlockGapException:
    """A displayed schedule block that used the cross-quarter gap relaxation."""

    staff_identifier: str
    previous_block_start: date
    current_block_start: date
    required_gap_days: int
    actual_gap_days: int


def find_cross_quarter_block_gap_exceptions(
    schedule: Schedule,
    previous_context: PreviousPlanContext | None,
    config: SchedulerConfig | None = None,
    staff_list: list[Staff] | None = None,
) -> list[CrossQuarterBlockGapException]:
    """Find boundary block gaps that the solver may relax with a penalty.

    This is presentation-only analysis. It mirrors the solver's block-start
    calculation without changing schedule validation or exported assignments.
    """
    if previous_context is None:
        return []

    config = config or SchedulerConfig()
    staff_dict = {s.identifier: s for s in staff_list} if staff_list else {}

    trailing_dates_by_staff: dict[str, set[date]] = defaultdict(set)
    for assignment in previous_context.trailing_assignments:
        staff = staff_dict.get(assignment.staff_identifier)
        staff_gap = (
            config.intern_block_gap_days
            if staff and staff.beruf == Beruf.INTERN
            else config.block_gap_days
        )
        if 0 < (schedule.quarter_start - assignment.shift_date).days <= staff_gap:
            trailing_dates_by_staff[assignment.staff_identifier].add(assignment.shift_date)

    current_dates_by_staff: dict[str, set[date]] = defaultdict(set)
    pre_assigned_dates_by_staff: dict[str, set[date]] = defaultdict(set)
    for assignment in schedule.assignments:
        current_dates_by_staff[assignment.staff_identifier].add(assignment.shift.shift_date)
        if assignment.is_pre_assigned:
            pre_assigned_dates_by_staff[assignment.staff_identifier].add(
                assignment.shift.shift_date
            )

    exceptions: list[CrossQuarterBlockGapException] = []
    for staff_identifier, current_dates in current_dates_by_staff.items():
        all_work_dates_set = trailing_dates_by_staff.get(staff_identifier, set()) | current_dates
        all_work_dates = sorted(all_work_dates_set)
        block_starts = [
            work_date
            for work_date in all_work_dates
            if work_date - timedelta(days=1) not in all_work_dates_set
        ]

        staff_pa_dates = pre_assigned_dates_by_staff.get(staff_identifier, set())

        def _block_has_pre_assigned(start_d: date) -> bool:
            cur = start_d
            while cur in all_work_dates_set:
                if cur in staff_pa_dates:
                    return True
                cur += timedelta(days=1)
            return False

        staff = staff_dict.get(staff_identifier)
        staff_gap = (
            config.intern_block_gap_days
            if staff and staff.beruf == Beruf.INTERN
            else config.block_gap_days
        )

        for previous_block_start in block_starts:
            if previous_block_start >= schedule.quarter_start:
                continue
            prev_has_pa = _block_has_pre_assigned(previous_block_start)
            for current_block_start in block_starts:
                if current_block_start < schedule.quarter_start:
                    continue
                curr_has_pa = _block_has_pre_assigned(current_block_start)
                actual_gap_days = (current_block_start - previous_block_start).days
                required_gap_days = (
                    config.holiday_gap_days
                    if (prev_has_pa or curr_has_pa)
                    else staff_gap
                )
                if actual_gap_days < required_gap_days:
                    exceptions.append(
                        CrossQuarterBlockGapException(
                            staff_identifier=staff_identifier,
                            previous_block_start=previous_block_start,
                            current_block_start=current_block_start,
                            required_gap_days=required_gap_days,
                            actual_gap_days=actual_gap_days,
                        )
                    )

    return exceptions


def validate_schedule(
    schedule: Schedule,
    staff_list: list[Staff],
    config: SchedulerConfig | None = None,
    previous_context: PreviousPlanContext | None = None,
) -> ValidationResult:
    """Validate schedule against all constraints.

    Returns ValidationResult with hard violations and soft penalty score.
    """
    violations: list[ConstraintViolation] = []
    staff_dict = {s.identifier: s for s in staff_list}
    config = config or SchedulerConfig()

    # Check hard constraints
    violations.extend(_check_minor_sunday_constraint(schedule, staff_dict))
    violations.extend(_check_intern_weekend_constraint(schedule, staff_dict))
    violations.extend(_check_intern_coupled_weekend_constraint(schedule, staff_dict))
    violations.extend(_check_intern_monthly_weekend_cap(schedule, staff_dict))
    violations.extend(_check_night_pairing_constraint(schedule, staff_dict))
    violations.extend(_check_nd_alone_improper_pairing(schedule, staff_dict))
    violations.extend(_check_same_day_double_booking(schedule))
    violations.extend(_check_open_night_capacity(schedule, staff_dict))
    violations.extend(_check_same_day_next_day_constraint(schedule))
    violations.extend(_check_three_week_block_constraint(schedule, staff_dict, config))
    violations.extend(_check_weekend_isolation_constraint(schedule))
    violations.extend(_check_min_consecutive_nights_constraint(schedule, staff_dict))
    # violations.extend(_check_nd_max_consecutive_constraint(schedule, staff_dict))  # Relaxed to soft
    violations.extend(_check_nd_exceptions_constraint(schedule, staff_dict))
    violations.extend(_check_shift_eligibility(schedule, staff_dict))
    violations.extend(_check_shift_coverage(schedule, staff_dict))
    violations.extend(_check_abteilung_night_constraint(schedule, staff_dict, previous_context))
    violations.extend(_check_vet_shift_constraints(schedule, staff_dict, previous_context))

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
    """Staff with nd_alone=True must work ALONE on closed nights.

    They cannot be paired with ANYONE on closed nights.
    On open nights (Sun-Mon, Mon-Tue), the nd_alone restriction is lifted.
    """
    violations: list[ConstraintViolation] = []
    open_night_types = {ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE}

    # Group night assignments by (date, shift_type)
    night_assignments_by_shift: dict[tuple[Any, ShiftType], list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        if assignment.shift.is_night_shift():
            key = (assignment.shift.shift_date, assignment.shift.shift_type)
            night_assignments_by_shift[key].append(assignment)

    for (shift_date, shift_type), assignments in night_assignments_by_shift.items():
        # Skip open nights (nd_alone is lifted there)
        if shift_type in open_night_types:
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

        # nd_alone=True staff cannot be paired with anyone on closed nights
        if nd_alone_true_staff and len(assignments) > 1:
            all_others = [name for name in nd_alone_true_staff[1:]] + other_staff
            violations.append(
                ConstraintViolation(
                    "ND Alone Improper Pairing",
                    f"Staff with nd_alone=True ({', '.join(nd_alone_true_staff)}) cannot be "
                    f"paired with anyone on closed nights. Found with: {', '.join(all_others)} on "
                    f"{shift_date.strftime('%d.%m.%Y')} {shift_type.value}",
                )
            )

    return violations


def _check_open_night_capacity(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Sun-Mon and Mon-Tue nights: exactly 2 persons, at least 1 TFA, max 1 Azubi.

    Open nights have regular clinic operations with higher patient volume:
    - Exakt 2 Personen erforderlich (FR-2.1)
    - Mindestens 1 TFA erforderlich (FR-2.2)
    - Maximal 1 Azubi (FR-2.5)
    - Skips shifts that are externally pre-assigned (is_pre_assigned=True)
    """
    violations: list[ConstraintViolation] = []
    open_night_types = {ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE}

    # Group assignments by (date, shift_type)
    night_assignments_by_shift: dict[tuple[Any, ShiftType], list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        if assignment.shift.is_night_shift():
            key = (assignment.shift.shift_date, assignment.shift.shift_type)
            night_assignments_by_shift[key].append(assignment)

    for (shift_date, shift_type), assignments in night_assignments_by_shift.items():
        if shift_type not in open_night_types:
            continue

        # Skip externally pre-assigned holiday shifts
        if any(a.is_pre_assigned for a in assignments):
            continue

        assigned_staff = [
            staff_dict[a.staff_identifier]
            for a in assignments
            if a.staff_identifier in staff_dict
        ]

        # 1. Exact headcount: exactly 2 persons
        if len(assignments) != 2:
            violations.append(
                ConstraintViolation(
                    "Open Night Headcount",
                    f"Offene Nacht am {shift_date.strftime('%d.%m.%Y')} ({shift_type.value}) "
                    f"erfordert exakt 2 Personen, gefunden: {len(assignments)}",
                )
            )

        # 2. Mandatory TFA: at least 1 TFA
        tfa_count = sum(1 for p in assigned_staff if p.beruf == Beruf.TFA)
        if tfa_count < 1:
            violations.append(
                ConstraintViolation(
                    "Open Night Missing TFA",
                    f"Offene Nacht am {shift_date.strftime('%d.%m.%Y')} ({shift_type.value}) "
                    f"erfordert mind. 1 TFA (gefunden: {[p.name for p in assigned_staff]})",
                )
            )

        # 3. Max 1 Azubi
        azubis = [p.name for p in assigned_staff if p.beruf == Beruf.AZUBI]
        if len(azubis) > 1:
            violations.append(
                ConstraintViolation(
                    "Multiple Azubis on Night",
                    f"Nacht am {shift_date.strftime('%d.%m.%Y')} ({shift_type.value}) hat "
                    f"mehrere Azubis ({', '.join(azubis)}), nur 1 Azubi erlaubt",
                )
            )

    return violations


def _check_intern_weekend_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Interns can only work Sa_Intern / So_Intern among weekend shifts,
    and non-Interns cannot work Sa_Intern / So_Intern."""
    violations: list[ConstraintViolation] = []
    for assignment in schedule.assignments:
        if assignment.shift.is_weekend_shift():
            staff = staff_dict.get(assignment.staff_identifier)
            if not staff:
                continue
            if staff.beruf == Beruf.INTERN:
                if not assignment.shift.is_intern_weekend_shift():
                    violations.append(
                        ConstraintViolation(
                            "Intern Weekend Ban",
                            f"Intern {staff.name} assigned to regular weekend shift on "
                            f"{assignment.shift.shift_date.strftime('%d.%m.%Y')} "
                            f"({assignment.shift.shift_type.value})",
                        )
                    )
            else:
                if assignment.shift.is_intern_weekend_shift():
                    violations.append(
                        ConstraintViolation(
                            "Intern Weekend Exclusivity",
                            f"Non-Intern {staff.name} ({staff.beruf.value}) assigned to Intern weekend shift on "
                            f"{assignment.shift.shift_date.strftime('%d.%m.%Y')} "
                            f"({assignment.shift.shift_type.value})",
                        )
                    )
    return violations


def _check_intern_coupled_weekend_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Intern assigned to Saturday must also work Sunday of that same weekend."""
    violations: list[ConstraintViolation] = []

    # Map Saturday dates to Sa_Intern and So_Intern assignments
    intern_we_by_sat: dict[date, dict[ShiftType, list[Assignment]]] = defaultdict(lambda: defaultdict(list))
    for a in schedule.assignments:
        if a.shift.shift_type == ShiftType.SATURDAY_INTERN:
            intern_we_by_sat[a.shift.shift_date][ShiftType.SATURDAY_INTERN].append(a)
        elif a.shift.shift_type == ShiftType.SUNDAY_INTERN:
            # Saturday of this Sunday is shift_date - 1 day
            sat_date = a.shift.shift_date - timedelta(days=1)
            intern_we_by_sat[sat_date][ShiftType.SUNDAY_INTERN].append(a)

    for sat_date, shifts in intern_we_by_sat.items():
        sun_date = sat_date + timedelta(days=1)
        sat_assigns = shifts.get(ShiftType.SATURDAY_INTERN, [])
        sun_assigns = shifts.get(ShiftType.SUNDAY_INTERN, [])

        # Both empty is allowed (soft coverage)
        if not sat_assigns and not sun_assigns:
            continue

        if sat_assigns and not sun_assigns:
            sid = sat_assigns[0].staff_identifier
            s_name = staff_dict[sid].name if sid in staff_dict else sid
            violations.append(
                ConstraintViolation(
                    "Intern Coupled Weekend",
                    f"Intern {s_name} assigned to Sa_Intern on {sat_date.strftime('%d.%m.%Y')} "
                    f"without corresponding So_Intern on {sun_date.strftime('%d.%m.%Y')}",
                )
            )
        elif sun_assigns and not sat_assigns:
            sid = sun_assigns[0].staff_identifier
            s_name = staff_dict[sid].name if sid in staff_dict else sid
            violations.append(
                ConstraintViolation(
                    "Intern Coupled Weekend",
                    f"Intern {s_name} assigned to So_Intern on {sun_date.strftime('%d.%m.%Y')} "
                    f"without corresponding Sa_Intern on {sat_date.strftime('%d.%m.%Y')}",
                )
            )
        else:
            # Both assigned: check if assigned to the same staff member
            sat_staff = sat_assigns[0].staff_identifier
            sun_staff = sun_assigns[0].staff_identifier
            if sat_staff != sun_staff:
                s1_name = staff_dict[sat_staff].name if sat_staff in staff_dict else sat_staff
                s2_name = staff_dict[sun_staff].name if sun_staff in staff_dict else sun_staff
                violations.append(
                    ConstraintViolation(
                        "Intern Coupled Weekend",
                        f"Intern weekend uncoupled on {sat_date.strftime('%d.%m.%Y')}/{sun_date.strftime('%d.%m.%Y')}: "
                        f"Saturday has {s1_name}, but Sunday has {s2_name}",
                    )
                )

    return violations


def _check_intern_monthly_weekend_cap(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Each Intern works at most one weekend (Saturday + Sunday) per calendar month."""
    violations: list[ConstraintViolation] = []
    # Month is defined by Saturday date
    intern_months: dict[str, dict[tuple[int, int], int]] = defaultdict(lambda: defaultdict(int))

    for a in schedule.assignments:
        if a.shift.shift_type == ShiftType.SATURDAY_INTERN:
            d = a.shift.shift_date
            intern_months[a.staff_identifier][(d.year, d.month)] += 1

    for staff_id, months in intern_months.items():
        staff = staff_dict.get(staff_id)
        name = staff.name if staff else staff_id
        for (year, month), count in months.items():
            if count > 1:
                violations.append(
                    ConstraintViolation(
                        "Intern Monthly Weekend Cap",
                        f"Intern {name} assigned to {count} weekend blocks in "
                        f"{month:02d}/{year}, maximum is 1 per calendar month",
                    )
                )

    return violations


def _check_night_pairing_constraint(
    schedule: Schedule, staff_dict: dict[str, Staff]
) -> list[ConstraintViolation]:
    """Check night pairing rules:
    - Azubis must always be paired with a non-Azubi (TFA or Intern)
    - Two Azubis can never work together
    - nd_alone=False staff must be paired (on closed nights; open nights enforce 2 persons)
    """
    violations: list[ConstraintViolation] = []
    open_night_types = {ShiftType.NIGHT_SUN_MON, ShiftType.NIGHT_MON_TUE}

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

        # Rule: nd_alone=False must be paired (except on open nights)
        is_open_night = shift_type in open_night_types
        for staff in nd_alone_false_staff:
            # Skip Azubis (handled above)
            if staff.beruf == Beruf.AZUBI:
                continue
            # On closed nights, must be paired
            if not is_open_night and len(assignments) < 2:
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


def _check_three_week_block_constraint(
    schedule: Schedule,
    staff_dict: dict[str, Staff] | None = None,
    config: SchedulerConfig | None = None,
) -> list[ConstraintViolation]:
    """Each staff can have max 1 consecutive block per rolling window.
    
    Blocks must be separated by at least 21 days for TFA/Azubi, or
    intern_block_gap_days (10 days) for Interns (from start to start).
    Note: Weekend shifts are already constrained to be isolated (single-shift blocks,
    or coupled 2-day blocks for Interns) by _check_weekend_isolation_constraint.
    """
    violations: list[ConstraintViolation] = []
    config = config or SchedulerConfig()

    # Group assignments by staff
    staff_assignments: dict[str, list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        staff_assignments[assignment.staff_identifier].append(assignment)

    for staff_id, assignments in staff_assignments.items():
        staff = staff_dict.get(staff_id) if staff_dict else None
        if staff and staff.beruf == Beruf.VET:
            continue

        # Sort by date
        sorted_assignments = sorted(assignments, key=lambda a: a.shift.shift_date)

        # Find consecutive blocks
        blocks = _find_consecutive_blocks(sorted_assignments)

        base_gap = (
            config.intern_block_gap_days
            if staff and staff.beruf == Beruf.INTERN
            else config.block_gap_days
        )

        # Check rolling windows
        for i, block1 in enumerate(blocks):
            block1_start = block1[0].shift.shift_date
            block1_end = block1[-1].shift.shift_date
            b1_has_holiday = any(a.is_pre_assigned for a in block1)

            for block2 in blocks[i + 1 :]:
                block2_start = block2[0].shift.shift_date
                b2_has_holiday = any(a.is_pre_assigned for a in block2)

                # 7-day relaxation if either block includes pre-assigned holiday duty
                required_gap = (
                    config.holiday_gap_days
                    if (b1_has_holiday or b2_has_holiday)
                    else base_gap
                )

                # Check if block2 starts within required_gap days of block1 start
                if (block2_start - block1_start).days < required_gap:
                    name = (
                        "Holiday Block Limit"
                        if (b1_has_holiday or b2_has_holiday)
                        else ("3-Week Block Limit" if required_gap >= 21 else "10-Day Block Limit")
                    )
                    violations.append(
                        ConstraintViolation(
                            name,
                            f"{staff_id} has multiple shift blocks within {required_gap} days: "
                            f"{block1_start.strftime('%d.%m.%Y')}-{block1_end.strftime('%d.%m.%Y')} "
                            f"and {block2_start.strftime('%d.%m.%Y')}",
                        )
                    )
                    break  # Only report first violation per block

    return violations


def _check_weekend_isolation_constraint(schedule: Schedule) -> list[ConstraintViolation]:
    """Weekend shifts must always be isolated (single-shift, not part of a block).
    
    A weekend shift cannot be adjacent (same day or next day) to any other shift
    for the same person. For Interns, the coupled Sa_Intern + So_Intern weekend pair
    is allowed, but adjacencies to night shifts (e.g. Friday or Monday) remain forbidden.
    """
    violations: list[ConstraintViolation] = []

    # Group assignments by staff
    staff_assignments: dict[str, list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        staff_assignments[assignment.staff_identifier].append(assignment)

    for staff_id, assignments in staff_assignments.items():
        # Get weekend shifts and all dates worked
        weekend_assignments = [a for a in assignments if a.shift.is_weekend_shift()]
        shifts_by_date: dict[date, list[ShiftType]] = defaultdict(list)
        for a in assignments:
            shifts_by_date[a.shift.shift_date].append(a.shift.shift_type)

        for we_assignment in weekend_assignments:
            we_date = we_assignment.shift.shift_date
            prev_date = we_date - timedelta(days=1)
            next_date = we_date + timedelta(days=1)

            # Check if adjacent to another shift (forming a block)
            adjacent_worked = []
            if prev_date in shifts_by_date:
                prev_types = shifts_by_date[prev_date]
                is_coupled = (
                    we_assignment.shift.shift_type == ShiftType.SUNDAY_INTERN
                    and prev_types == [ShiftType.SATURDAY_INTERN]
                )
                if not is_coupled:
                    adjacent_worked.append(prev_date.strftime('%d.%m.%Y'))

            if next_date in shifts_by_date:
                next_types = shifts_by_date[next_date]
                is_coupled = (
                    we_assignment.shift.shift_type == ShiftType.SATURDAY_INTERN
                    and next_types == [ShiftType.SUNDAY_INTERN]
                )
                if not is_coupled:
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
    """Staff must work at least nd_min_consecutive consecutive nights per block.

    Skips staff where nd_min_consecutive <= 1 (e.g. Azubis or special TFA cases).
    """
    violations: list[ConstraintViolation] = []

    # Group night assignments by staff
    staff_night_assignments: dict[str, list[Assignment]] = defaultdict(list)
    for assignment in schedule.assignments:
        if assignment.shift.is_night_shift():
            staff_night_assignments[assignment.staff_identifier].append(assignment)

    for staff_id, night_assignments in staff_night_assignments.items():
        staff = staff_dict.get(staff_id)
        if not staff or staff.beruf == Beruf.VET:
            continue

        min_consecutive = staff.nd_min_consecutive
        if min_consecutive <= 1:
            continue  # Single nights allowed — no constraint to enforce

        # Sort by date
        sorted_nights = sorted(night_assignments, key=lambda a: a.shift.shift_date)

        # Find consecutive night blocks
        consecutive_blocks = _find_consecutive_blocks(sorted_nights)

        for block in consecutive_blocks:
            block_length = len(block)
            if block_length < min_consecutive:
                violations.append(
                    ConstraintViolation(
                        "Min Consecutive Nights",
                        f"{staff.name} ({staff.beruf.value}) working only {block_length} "
                        f"consecutive night(s) starting "
                        f"{block[0].shift.shift_date.strftime('%d.%m.%Y')}, "
                        f"minimum is {min_consecutive} (nd_min_consecutive)",
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
        if not staff or staff.beruf == Beruf.VET or staff.nd_max_consecutive is None:
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


def _check_shift_coverage(
    schedule: Schedule,
    staff_dict: dict[str, Staff] | None = None,
) -> list[ConstraintViolation]:
    """Check that all required shifts are covered.

    Iterates over the expected shift list from generate_quarter_shifts:
    - Weekend regular shifts: exactly 1 person (or matches pre-assigned count).
    - Night shifts: 1-2 persons, and on closed nights at least 1 non-Azubi.
    """
    violations: list[ConstraintViolation] = []
    if not schedule.assignments:
        return violations

    holiday_dates = {
        a.shift.shift_date
        for a in schedule.assignments
        if a.shift.shift_date.weekday() < 5 and a.shift.is_weekend_shift()
    }
    expected_shifts = generate_quarter_shifts(
        schedule.quarter_start, holiday_dates=holiday_dates, quarter_end=schedule.quarter_end
    )

    assignments_by_shift: dict[tuple[date, ShiftType], list[Assignment]] = defaultdict(list)
    for a in schedule.assignments:
        assignments_by_shift[(a.shift.shift_date, a.shift.shift_type)].append(a)

    for shift in expected_shifts:
        assigned = assignments_by_shift.get((shift.shift_date, shift.shift_type), [])
        count = len(assigned)

        if shift.is_night_shift():
            if count == 0:
                violations.append(
                    ConstraintViolation(
                        "Shift Coverage",
                        f"Night shift {shift.shift_type.value} on {shift.shift_date.strftime('%d.%m.%Y')} "
                        "has no coverage",
                    )
                )
            elif count > 2:
                violations.append(
                    ConstraintViolation(
                        "Shift Overstaffing",
                        f"Night shift {shift.shift_type.value} on {shift.shift_date.strftime('%d.%m.%Y')} "
                        f"has {count} staff (max 2)",
                    )
                )
            elif staff_dict and shift.is_closed_night():
                # On closed nights, at least one assigned staff member must be non-Azubi (H12)
                non_azubi = [
                    a
                    for a in assigned
                    if staff_dict.get(a.staff_identifier)
                    and staff_dict[a.staff_identifier].beruf != Beruf.AZUBI
                ]
                if not non_azubi:
                    violations.append(
                        ConstraintViolation(
                            "Shift Coverage",
                            f"Night shift {shift.shift_type.value} on {shift.shift_date.strftime('%d.%m.%Y')} "
                            "has no non-Azubi staff (Azubi alone on closed night)",
                        )
                    )
        elif shift.is_weekend_shift() and not shift.is_intern_weekend_shift():
            if count == 0:
                violations.append(
                    ConstraintViolation(
                        "Shift Coverage",
                        f"Weekend shift {shift.shift_type.value} on {shift.shift_date.strftime('%d.%m.%Y')} "
                        "has no coverage",
                    )
                )
            elif count > 1 and not any(a.is_pre_assigned for a in assigned):
                violations.append(
                    ConstraintViolation(
                        "Shift Overstaffing",
                        f"Weekend shift {shift.shift_type.value} on {shift.shift_date.strftime('%d.%m.%Y')} "
                        f"has {count} staff (expected 1)",
                    )
                )

    return violations


def _check_abteilung_night_constraint(
    schedule: Schedule,
    staff_dict: dict[str, Staff],
    previous_context: PreviousPlanContext | None = None,
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

    # Check cross-quarter boundary with previous context
    if previous_context and schedule.quarter_start:
        prev_last_night = schedule.quarter_start - timedelta(days=1)
        first_night_assignments = night_assignments_by_date.get(schedule.quarter_start, [])
        for ta in previous_context.trailing_assignments:
            if ta.shift_date == prev_last_night and ta.shift_type.value.startswith("N_"):
                prev_staff = staff_dict.get(ta.staff_identifier)
                if prev_staff and prev_staff.abteilung in restricted_abteilungen:
                    for a in first_night_assignments:
                        curr_staff = staff_dict.get(a.staff_identifier)
                        if (
                            curr_staff
                            and curr_staff.abteilung == prev_staff.abteilung
                            and curr_staff.identifier != prev_staff.identifier
                        ):
                            violations.append(
                                ConstraintViolation(
                                    "Abteilung Consecutive Days",
                                    f"Staff from {prev_staff.abteilung.value} on consecutive nights across quarter boundary: "
                                    f"{prev_staff.name} on {prev_last_night.strftime('%d.%m.%Y')} "
                                    f"and {curr_staff.name} on {schedule.quarter_start.strftime('%d.%m.%Y')}",
                                )
                            )
    
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

    # Calculate target Notdienst per staff based on hours (excluding Vets who have hours=0)
    total_hours = sum(s.hours for s in staff_list if s.beruf != Beruf.VET)

    # Penalty for deviation from proportional target
    for staff in staff_list:
        if staff.beruf == Beruf.VET:
            continue
        actual_notdienst = schedule.count_total_notdienst(staff.identifier, staff)
        total_notdienst_needed = len(schedule.assignments)

        # Target proportional to hours
        target = (staff.hours / total_hours) * total_notdienst_needed if total_hours > 0 else 0.0

        # Squared deviation penalty
        deviation = abs(actual_notdienst - target)
        penalty += deviation**2

    # Penalty for unfairness within role groups
    for role in [Beruf.TFA, Beruf.AZUBI]:
        counts = [
            schedule.count_total_notdienst(s.identifier, s)
            for s in staff_list
            if s.beruf == role
        ]
        if len(counts) > 1:
            mean = sum(counts) / len(counts)
            variance = sum((x - mean) ** 2 for x in counts) / len(counts)
            std_dev = variance**0.5
            penalty += std_dev * 10

    # For Interns: Two-Track separate fairness (Track 1 Nights, Track 2 Weekends)
    intern_staff = [s for s in staff_list if s.beruf == Beruf.INTERN]
    if len(intern_staff) > 1:
        # Track 1: Night fairness
        night_counts = [schedule.count_effective_nights(s.identifier, s) for s in intern_staff]
        n_mean = sum(night_counts) / len(night_counts)
        n_variance = sum((x - n_mean) ** 2 for x in night_counts) / len(night_counts)
        penalty += (n_variance**0.5) * 10

        # Track 2: Weekend fairness (measured in full coupled weekends, not individual shifts)
        we_counts = [schedule.count_weekends(s.identifier, s) for s in intern_staff]
        w_mean = sum(we_counts) / len(we_counts)
        w_variance = sum((x - w_mean) ** 2 for x in we_counts) / len(we_counts)
        penalty += (w_variance**0.5) * 10
    
    # Soft penalty for consecutive night shifts exceeding nd_max_consecutive
    consecutive_nd_violations = _check_nd_max_consecutive_constraint(schedule, staff_dict)
    penalty += 100.0 * len(consecutive_nd_violations)

    return penalty


def _check_vet_shift_constraints(
    schedule: Schedule,
    staff_dict: dict[str, Staff],
    previous_context: PreviousPlanContext | None = None,
) -> list[ConstraintViolation]:
    """Validate specific constraints for Vets (Beruf.VET):
    - Shift types: only N_Di-Mi, N_Mi-Do, N_Do-Fr allowed.
    - Exact 2-night blocks: each block must be exactly 2 consecutive nights (neither 1 nor >= 3).
    - Solo duty: exactly 1 person on any night where a Vet is assigned.
    - 2-month rule (calendar months): max 1 block start in any two consecutive calendar months (m, m+1).
    - Cross-quarter lockout (H-VET-4): active in last month of previous quarter blocks month 1 of new quarter.
    """
    violations: list[ConstraintViolation] = []
    allowed_vet_shifts = {
        ShiftType.NIGHT_TUE_WED,
        ShiftType.NIGHT_WED_THU,
        ShiftType.NIGHT_THU_FRI,
    }

    # Group all assignments by shift (date, shift_type)
    assignments_by_shift: dict[tuple[date, ShiftType], list[Assignment]] = defaultdict(list)
    vet_assignments_by_id: dict[str, list[Assignment]] = defaultdict(list)

    for a in schedule.assignments:
        assignments_by_shift[(a.shift.shift_date, a.shift.shift_type)].append(a)
        staff = staff_dict.get(a.staff_identifier)
        if staff and staff.beruf == Beruf.VET:
            vet_assignments_by_id[a.staff_identifier].append(a)

    # 1. Solo duty on shifts where a Vet is assigned
    for (shift_date, shift_type), shift_assignments in assignments_by_shift.items():
        has_vet = any(
            staff_dict.get(a.staff_identifier) and staff_dict[a.staff_identifier].beruf == Beruf.VET
            for a in shift_assignments
        )
        if has_vet and len(shift_assignments) > 1:
            all_names = [
                staff_dict[a.staff_identifier].name if a.staff_identifier in staff_dict else a.staff_identifier
                for a in shift_assignments
            ]
            violations.append(
                ConstraintViolation(
                    "Vet Shift Constraint",
                    f"Vet muss Alleindienst leisten, aber {len(shift_assignments)} Personen eingeteilt am "
                    f"{shift_date.strftime('%d.%m.%Y')} {shift_type.value}: {', '.join(all_names)}",
                )
            )

    # 2. Per-Vet checks: shift type, exact 2-night blocks, 2-month rule
    for staff_id, assignments in vet_assignments_by_id.items():
        staff = staff_dict[staff_id]

        for a in assignments:
            if a.shift.shift_type not in allowed_vet_shifts:
                violations.append(
                    ConstraintViolation(
                        "Vet Shift Constraint",
                        f"Vet {staff.name} ({staff_id}) für unzulässige Schicht {a.shift.shift_type.value} am "
                        f"{a.shift.shift_date.strftime('%d.%m.%Y')} eingeteilt. Zulässig sind nur Di-Mi, Mi-Do, Do-Fr.",
                    )
                )

        sorted_assignments = sorted(assignments, key=lambda x: x.shift.shift_date)
        blocks = _find_consecutive_blocks(sorted_assignments)

        for block in blocks:
            if len(block) != 2:
                violations.append(
                    ConstraintViolation(
                        "Vet Shift Constraint",
                        f"Vet {staff.name} ({staff_id}) hat Block der Länge {len(block)} ab "
                        f"{block[0].shift.shift_date.strftime('%d.%m.%Y')}. Erlaubt sind exakt 2 Nächte am Stück.",
                    )
                )

        # 2-month calendar boundary check
        block_starts = [b[0].shift.shift_date for b in blocks]
        for i, d1 in enumerate(block_starts):
            for d2 in block_starts[i + 1 :]:
                month_diff = abs((d2.year * 12 + d2.month) - (d1.year * 12 + d1.month))
                if month_diff <= 1:
                    violations.append(
                        ConstraintViolation(
                            "Vet Shift Constraint",
                            f"Vet {staff.name} ({staff_id}) hat Blöcke in aufeinanderfolgenden oder gleichen "
                            f"Kalendermonaten ({d1.strftime('%m.%Y')} und {d2.strftime('%m.%Y')}). "
                            f"Maximal 1 Block alle 2 Monate erlaubt.",
                        )
                    )

    # 3. Cross-quarter vet lockout check (H-VET-4)
    if previous_context and getattr(previous_context, "vet_active_last_month_ids", None):
        q_start_month = schedule.quarter_start.month
        for staff_id in previous_context.vet_active_last_month_ids:
            if staff_id in vet_assignments_by_id:
                asgns = vet_assignments_by_id[staff_id]
                first_month_asgns = [a for a in asgns if a.shift.shift_date.month == q_start_month]
                if first_month_asgns:
                    staff = staff_dict.get(staff_id)
                    s_name = staff.name if staff else staff_id
                    violations.append(
                        ConstraintViolation(
                            "Vet Shift Constraint",
                            f"Vet {s_name} ({staff_id}) hat Dienst im ersten Monat ({schedule.quarter_start.strftime('%m.%Y')}), "
                            f"ist aber durch Vorquartalsdienst gesperrt (H-VET-4).",
                        )
                    )

    return violations
