"""Data models for staff, shifts, and schedules."""

import csv
import json
from dataclasses import dataclass
from datetime import date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .file_loader import load_staff_from_file as _load_staff_dict
from .file_loader import load_vacations_from_file as _load_vacations_dict
from .file_loader import load_pre_assigned_from_file as _load_pre_assigned_dict
from .file_loader import parse_previous_plan_xlsx as _parse_previous_plan_xlsx


class Beruf(str, Enum):
    """Staff role/profession."""

    TFA = "TFA"
    AZUBI = "Azubi"
    INTERN = "Intern"  # Formerly "TA" - veterinary interns


class Abteilung(str, Enum):
    """Department/ward assignment."""

    STATION = "station"
    OP = "op"
    OTHER = "other"


class ShiftType(str, Enum):
    """Type of shift."""

    SATURDAY_10_21 = "Sa_10-21"  # Anmeldung + Rufbereitschaft
    SATURDAY_10_22 = "Sa_10-22"  # Rufbereitschaft
    SATURDAY_10_19 = "Sa_10-19"  # Azubidienst
    SUNDAY_8_20 = "So_8-20"
    SUNDAY_10_22 = "So_10-22"  # Rufbereitschaft
    SUNDAY_8_2030 = "So_8-20:30"  # Azubi (8-12 onsite, 12-20:30 Rufbereitschaft)
    NIGHT_SUN_MON = "N_So-Mo"  # Sun→Mon (TA onsite)
    NIGHT_MON_TUE = "N_Mo-Di"  # Mon→Tue (TA onsite)
    NIGHT_TUE_WED = "N_Di-Mi"
    NIGHT_WED_THU = "N_Mi-Do"
    NIGHT_THU_FRI = "N_Do-Fr"
    NIGHT_FRI_SAT = "N_Fr-Sa"
    NIGHT_SAT_SUN = "N_Sa-So"


class Staff(BaseModel):
    """Staff member with Notdienst capabilities."""

    name: str
    identifier: str
    adult: bool
    hours: int  # Weekly contracted hours
    beruf: Beruf
    abteilung: Abteilung = Abteilung.OTHER  # Department assignment
    reception: bool  # Can work reception/Anmeldung
    nd_possible: bool  # Can do night shifts at all
    nd_alone: bool  # Can work nights solo (False = must pair)
    nd_max_consecutive: int | None = None  # Max consecutive nights allowed (None = no limit)
    nd_min_consecutive: int = 2  # Min consecutive nights required (Azubis=1, most TFA/Intern=2)
    nd_exceptions: list[int] = Field(default_factory=list)  # Weekdays (1=Mon, 7=Sun) excluded
    birthday: str | None = None  # Birthday in MM-DD format (no year), e.g. "04-15"
    available_from: date | None = None  # First date available for scheduling (new employees)

    @field_validator("birthday", mode="before")
    @classmethod
    def parse_birthday(cls, v: Any) -> str | None:
        """Parse birthday from CSV (handles empty strings)."""
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return None
        return v.strip()

    @field_validator("abteilung", mode="before")
    @classmethod
    def parse_abteilung(cls, v: Any) -> Abteilung:
        """Parse abteilung from CSV (handles empty strings)."""
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return Abteilung.OTHER
        if isinstance(v, str):
            return Abteilung(v.lower())
        return v

    @field_validator("nd_max_consecutive", mode="before")
    @classmethod
    def parse_nd_max_consecutive(cls, v: Any) -> int | None:
        """Parse nd_max_consecutive from CSV (handles empty strings)."""
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return None
        return int(v)

    @field_validator("nd_min_consecutive", mode="before")
    @classmethod
    def parse_nd_min_consecutive(cls, v: Any) -> int:
        """Parse nd_min_consecutive from CSV (handles empty strings, defaults to 2)."""
        if v is None or v == "" or (isinstance(v, str) and v.strip() == ""):
            return 2
        return int(v)

    @field_validator("nd_exceptions", mode="before")
    @classmethod
    def parse_json_array(cls, v: Any) -> list[int]:
        """Parse JSON string arrays from CSV."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    def get_birthday_date(self, year: int) -> date | None:
        """Return this employee's birthday as a date for the given year.

        Returns None if birthday is unset or doesn't exist in that year (e.g. Feb 29).
        """
        if self.birthday is None:
            return None
        month, day = (int(p) for p in self.birthday.split("-"))
        try:
            return date(year, month, day)
        except ValueError:
            return None  # e.g. Feb 29 in a non-leap year

    def effective_nights_weight(self, is_paired: bool) -> float:
        """Calculate effective night weight for fairness.

        Azubis always count as 1.0 effective night (even when paired).
        Non-Azubis: Paired nights count as 0.5, solo nights count as 1.0.
        """
        if self.beruf == Beruf.AZUBI:
            return 1.0  # Azubis always get full credit
        return 0.5 if is_paired else 1.0

    def can_work_shift(self, shift_type: ShiftType, shift_date: date) -> bool:
        """Check basic eligibility for a shift type on a given date."""
        # Minors cannot work Sundays
        if not self.adult and shift_type.value.startswith("So_"):
            return False

        # Interns never work weekends
        if self.beruf == Beruf.INTERN and (
            shift_type.value.startswith("Sa_") or shift_type.value.startswith("So_")
        ):
            return False

        # Night shifts
        if shift_type.value.startswith("N_"):
            if not self.nd_possible:
                return False
            # Check nd_exceptions (weekday restrictions)
            weekday = shift_date.isoweekday()  # 1=Mon, 7=Sun
            if weekday in self.nd_exceptions:
                return False
            # Note: nd_alone and Azubi pairing constraints are handled at solver level

        # Saturday 10-19: Azubis only
        if shift_type == ShiftType.SATURDAY_10_19:
            return self.beruf == Beruf.AZUBI

        # Saturday 10-21: TFA or Azubi with reception=True
        if shift_type == ShiftType.SATURDAY_10_21:
            if self.beruf == Beruf.AZUBI:
                return self.reception
            return self.beruf == Beruf.TFA

        # Saturday 10-22: TFA only
        if shift_type == ShiftType.SATURDAY_10_22:
            return self.beruf == Beruf.TFA

        # Sunday 8-20: TFA only
        if shift_type == ShiftType.SUNDAY_8_20:
            return self.beruf == Beruf.TFA

        # Sunday 8-20:30: Adult Azubis only
        if shift_type == ShiftType.SUNDAY_8_2030:
            return self.beruf == Beruf.AZUBI and self.adult

        # Sunday 10-22: TFA only
        if shift_type == ShiftType.SUNDAY_10_22:
            return self.beruf == Beruf.TFA

        return True


class Shift(BaseModel):
    """A single shift slot."""

    shift_type: ShiftType
    shift_date: date
    requires_pair: bool = False  # Night shifts may require pairing

    def is_night_shift(self) -> bool:
        """Check if this is a night shift."""
        return self.shift_type.value.startswith("N_")

    def is_weekend_shift(self) -> bool:
        """Check if this is a weekend shift."""
        return self.shift_type.value.startswith("Sa_") or self.shift_type.value.startswith("So_")

    def get_next_day(self) -> date:
        """Get the date of the next day after this shift."""
        return self.shift_date + timedelta(days=1)


class Assignment(BaseModel):
    """Assignment of staff to a shift."""

    shift: Shift
    staff_identifier: str
    is_paired: bool = False  # True if this night shift is worked with a partner
    is_pre_assigned: bool = False  # True if fixed by external process (holidays)


class Schedule(BaseModel):
    """Complete schedule for a quarter."""

    quarter_start: date
    quarter_end: date
    assignments: list[Assignment] = Field(default_factory=list)

    def get_staff_assignments(self, staff_identifier: str) -> list[Assignment]:
        """Get all assignments for a specific staff member."""
        return [a for a in self.assignments if a.staff_identifier == staff_identifier]

    def get_shift_assignments(self, shift: Shift) -> list[Assignment]:
        """Get all assignments for a specific shift."""
        return [
            a
            for a in self.assignments
            if a.shift.shift_date == shift.shift_date and a.shift.shift_type == shift.shift_type
        ]

    def count_effective_nights(self, staff_identifier: str, staff: "Staff | None" = None) -> float:
        """Count effective nights for a staff member.
        
        Azubis always get 1.0 effective night (even when paired).
        Non-Azubis: paired = 0.5, solo = 1.0.
        
        If staff object is provided, uses proper role-based calculation.
        Otherwise falls back to standard paired/solo logic.
        """
        night_assignments = [
            a for a in self.get_staff_assignments(staff_identifier) if a.shift.is_night_shift()
        ]
        
        if staff is not None:
            return sum(staff.effective_nights_weight(a.is_paired) for a in night_assignments)
        
        # Fallback without staff object (legacy behavior)
        return sum(0.5 if a.is_paired else 1.0 for a in night_assignments)

    def count_weekend_shifts(self, staff_identifier: str) -> int:
        """Count weekend shifts for a staff member."""
        return sum(
            1 for a in self.get_staff_assignments(staff_identifier) if a.shift.is_weekend_shift()
        )

    def count_total_notdienst(self, staff_identifier: str, staff: "Staff | None" = None) -> float:
        """Count total Notdienst (weekends + effective nights)."""
        return self.count_weekend_shifts(staff_identifier) + self.count_effective_nights(
            staff_identifier, staff
        )


def load_staff_from_csv(csv_path: Path) -> list[Staff]:
    """Load staff data from CSV file."""
    staff_list: list[Staff] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Convert string booleans
            row["adult"] = row["adult"].lower() == "true"
            row["reception"] = row["reception"].lower() == "true"
            row["nd_possible"] = row["nd_possible"].lower() == "true"
            row["nd_alone"] = row["nd_alone"].lower() == "true"
            row["hours"] = int(row["hours"])
            # birthday column is optional for backwards compatibility
            if "birthday" not in row:
                row["birthday"] = None
            staff_list.append(Staff(**row))
    return staff_list


class PreAssignedShift(BaseModel):
    """A shift pre-assigned from an external process (e.g., holidays)."""

    shift_date: date
    shift_type: ShiftType
    staff_identifier: str
    is_paired: bool = False


def generate_quarter_shifts(
    quarter_start: date,
    holiday_dates: set[date] | None = None,
) -> list[Shift]:
    """Generate all shifts for a quarter (13 weeks).

    Args:
        quarter_start: First day of the quarter.
        holiday_dates: Weekday dates that should receive Sunday-pattern
            weekend shifts (e.g., public holidays).
    """
    shifts: list[Shift] = []
    current_date = quarter_start
    holiday_dates = holiday_dates or set()

    # Q2/2026: April 1 - June 30 (91 days, 13 weeks)
    quarter_end = quarter_start + timedelta(days=91)

    while current_date < quarter_end:
        weekday = current_date.weekday()  # 0=Mon, 5=Sat, 6=Sun
        is_holiday = current_date in holiday_dates

        # Public holiday: Sunday-pattern shifts take priority regardless of
        # the actual weekday (holidays can fall on a Saturday too, e.g. the
        # Tag der Deutschen Einheit or 2. Weihnachtsfeiertag).
        if is_holiday:
            shifts.append(Shift(shift_type=ShiftType.SUNDAY_8_20, shift_date=current_date))
            shifts.append(Shift(shift_type=ShiftType.SUNDAY_10_22, shift_date=current_date))
            shifts.append(Shift(shift_type=ShiftType.SUNDAY_8_2030, shift_date=current_date))

        # Saturday shifts
        elif weekday == 5:
            shifts.append(Shift(shift_type=ShiftType.SATURDAY_10_21, shift_date=current_date))
            shifts.append(Shift(shift_type=ShiftType.SATURDAY_10_22, shift_date=current_date))
            shifts.append(Shift(shift_type=ShiftType.SATURDAY_10_19, shift_date=current_date))

        # Sunday shifts
        elif weekday == 6:
            shifts.append(Shift(shift_type=ShiftType.SUNDAY_8_20, shift_date=current_date))
            shifts.append(Shift(shift_type=ShiftType.SUNDAY_10_22, shift_date=current_date))
            shifts.append(Shift(shift_type=ShiftType.SUNDAY_8_2030, shift_date=current_date))

        # Night shifts (every night)
        # Determine shift type based on day
        if weekday == 6:  # Sun→Mon
            night_type = ShiftType.NIGHT_SUN_MON
        elif weekday == 0:  # Mon→Tue
            night_type = ShiftType.NIGHT_MON_TUE
        elif weekday == 1:  # Tue→Wed
            night_type = ShiftType.NIGHT_TUE_WED
        elif weekday == 2:  # Wed→Thu
            night_type = ShiftType.NIGHT_WED_THU
        elif weekday == 3:  # Thu→Fri
            night_type = ShiftType.NIGHT_THU_FRI
        elif weekday == 4:  # Fri→Sat
            night_type = ShiftType.NIGHT_FRI_SAT
        else:  # Sat→Sun
            night_type = ShiftType.NIGHT_SAT_SUN

        shifts.append(Shift(shift_type=night_type, shift_date=current_date))

        current_date += timedelta(days=1)

    return shifts


class Vacation(BaseModel):
    """Vacation/unavailability period for a staff member."""

    identifier: str  # Staff identifier
    start_date: date
    end_date: date  # Inclusive

    def contains(self, check_date: date) -> bool:
        """Check if a date falls within this vacation period."""
        return self.start_date <= check_date <= self.end_date

    def get_dates(self) -> list[date]:
        """Get all dates in this vacation period."""
        dates = []
        current = self.start_date
        while current <= self.end_date:
            dates.append(current)
            current += timedelta(days=1)
        return dates

    def duration_days(self) -> int:
        """Get the number of days in this vacation period."""
        return (self.end_date - self.start_date).days + 1

    def duration_days_in_range(self, range_start: date, range_end: date) -> int:
        """Count vacation days that overlap with [range_start, range_end]."""
        overlap_start = max(self.start_date, range_start)
        overlap_end = min(self.end_date, range_end)
        if overlap_start > overlap_end:
            return 0
        return (overlap_end - overlap_start).days + 1


def load_vacations_from_csv(csv_path: Path) -> list[Vacation]:
    """Load vacation data from CSV file.

    Expected format: identifier,start_date,end_date
    Dates should be in ISO format (YYYY-MM-DD).
    """
    vacations: list[Vacation] = []
    with csv_path.open("r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            vacations.append(
                Vacation(
                    identifier=row["identifier"].strip(),
                    start_date=date.fromisoformat(row["start_date"].strip()),
                    end_date=date.fromisoformat(row["end_date"].strip()),
                )
            )
    return vacations


def load_staff_from_file(file_path: Path | str) -> list[Staff]:
    """Load staff data from CSV or XLSX file with flexible column name matching.

    Supports both .csv and .xlsx formats. Column names are matched case-insensitively
    with fuzzy matching, so "Name", "name", "Name des Mitarbeiters", etc. all work.

    Args:
        file_path: Path to CSV or XLSX file

    Returns:
        List of Staff objects

    Raises:
        ValueError: If required columns not found or data validation fails
    """
    staff_dict = _load_staff_dict(file_path)
    return [Staff(**data) for data in staff_dict.values()]


def load_vacations_from_file(file_path: Path | str) -> list[Vacation]:
    """Load vacation data from CSV or XLSX file with flexible column name matching.

    Supports both .csv and .xlsx formats. Column names are matched case-insensitively
    with fuzzy matching, and date formats (YYYY-MM-DD, DD.MM.YYYY, etc.) are auto-detected.

    Args:
        file_path: Path to CSV or XLSX file

    Returns:
        List of Vacation objects

    Raises:
        ValueError: If required columns not found or data validation fails
    """
    vacations_dict = _load_vacations_dict(file_path)
    vacations: list[Vacation] = []
    for vac_list in vacations_dict.values():
        for vac in vac_list:
            vacations.append(Vacation(**vac))
    return vacations


def load_pre_assigned_from_file(file_path: Path | str) -> list[PreAssignedShift]:
    """Load pre-assigned holiday shifts from CSV or XLSX."""
    raw = _load_pre_assigned_dict(file_path)
    return [
        PreAssignedShift(
            shift_date=r["shift_date"],
            shift_type=ShiftType(r["shift_type"]),
            staff_identifier=r["staff_identifier"],
            is_paired=r["is_paired"],
        )
        for r in raw
    ]


def validate_pre_assigned(
    pre_assigned: list[PreAssignedShift],
    staff_list: list[Staff],
    vacations: list[Vacation] | None = None,
) -> list[str]:
    """Check pre-assigned shifts for conflicts. Returns list of warning messages."""
    warnings: list[str] = []
    staff_by_id = {s.identifier: s for s in staff_list}
    vacation_dates: dict[str, set[date]] = {}
    if vacations:
        for v in vacations:
            vacation_dates.setdefault(v.identifier, set()).update(v.get_dates())

    for pa in pre_assigned:
        if pa.staff_identifier not in staff_by_id:
            warnings.append(
                f"Kürzel '{pa.staff_identifier}' (Datum {pa.shift_date:%d.%m.%Y}) "
                f"nicht in Personaldaten gefunden."
            )
            continue
        vac_dates = vacation_dates.get(pa.staff_identifier, set())
        if pa.shift_date in vac_dates:
            name = staff_by_id[pa.staff_identifier].name
            warnings.append(
                f"Konflikt: {name} ({pa.staff_identifier}) ist am "
                f"{pa.shift_date:%d.%m.%Y} im Urlaub, aber für "
                f"{pa.shift_type.value} eingeteilt."
            )
    return warnings


def get_pre_assigned_holiday_dates(
    pre_assigned: list[PreAssignedShift],
) -> set[date]:
    """Extract unique holiday dates from pre-assigned shifts.

    A date is treated as a holiday whenever it carries a Sunday-pattern
    (``So_``) shift type but is not already a natural Sunday (weekday 6).
    This covers holidays falling on any weekday, including Saturdays
    (e.g. Tag der Deutschen Einheit, 2. Weihnachtsfeiertag), so the
    Sunday-pattern shift slots get generated and pre-assigned shifts can
    be pinned as hard constraints.
    """
    holidays: set[date] = set()
    for pa in pre_assigned:
        if pa.shift_date.weekday() != 6 and pa.shift_type.value.startswith("So_"):
            holidays.add(pa.shift_date)
    return holidays


def get_staff_unavailable_dates(
    vacations: list[Vacation], staff_identifier: str
) -> set[date]:
    """Get all dates a staff member is unavailable due to vacation."""
    unavailable: set[date] = set()
    for v in vacations:
        if v.identifier == staff_identifier:
            unavailable.update(v.get_dates())
    return unavailable


def calculate_available_days(
    staff_identifier: str,
    vacations: list[Vacation],
    quarter_start: date,
    quarter_end: date,
    effective_start: date | None = None,
) -> int:
    """Calculate number of available (non-vacation) days in the quarter.

    ``effective_start`` overrides ``quarter_start`` for new employees whose
    first available date falls within the planning period.  Vacation days
    before that date are ignored since the employee wasn't present yet.
    """
    eff_start = max(quarter_start, effective_start) if effective_start else quarter_start
    total_days = (quarter_end - eff_start).days + 1
    unavailable = get_staff_unavailable_dates(vacations, staff_identifier)
    # Only count vacation days that fall within the effective window
    vacation_days_in_quarter = sum(
        1 for d in unavailable if eff_start <= d <= quarter_end
    )
    return total_days - vacation_days_in_quarter


# =========================================================================
# CROSS-PERIOD CARRY-FORWARD MODELS
# =========================================================================


class TrailingAssignment(BaseModel):
    """Simplified assignment for cross-quarter boundary constraints.

    Stores the last ~21 days of the previous quarter's assignments so the
    solver can enforce block-gap, consecutive-night, and rest-period rules
    across the quarter boundary.
    """

    shift_date: date
    shift_type: ShiftType
    staff_identifier: str
    is_paired: bool = False


class CarryForwardEntry(BaseModel):
    """Per-person fairness carry-forward data from a completed quarter.

    Stores the FTE-normalized Notdienst load and the delta from the group
    mean.  A positive delta means the person did more than average and
    should be compensated in the next quarter.
    """

    identifier: str
    name: str
    beruf: str
    hours: int
    effective_nights: float
    weekend_shifts: int
    total_notdienst: float
    normalized_40h: float
    group_mean_40h: float
    carry_forward_delta: float


class PreviousPlanContext(BaseModel):
    """Complete carry-forward context from a prior quarter.

    Contains per-person fairness deltas and trailing assignments (last 21
    days) for boundary constraint enforcement.  Serialised to JSON for
    export/import between planning periods.
    """

    quarter_start: date
    quarter_end: date
    carry_forward: list[CarryForwardEntry]
    trailing_assignments: list[TrailingAssignment]


def compute_carry_forward(
    schedule: Schedule,
    staff_list: list[Staff],
    vacations: list[Vacation] | None = None,
) -> list[CarryForwardEntry]:
    """Compute per-person carry-forward fairness deltas from a schedule.

    For each person, calculates their FTE-normalised Notdienst load
    (Norm./40h) and the delta from their beruf group mean.  A positive
    delta means they did more than average; a negative delta means less.
    """
    if vacations is None:
        vacations = []

    quarter_start = schedule.quarter_start
    quarter_end = schedule.quarter_end
    total_days = (quarter_end - quarter_start).days + 1

    # Compute per-person stats grouped by beruf
    entries_by_beruf: dict[str, list[dict]] = {}
    all_entries: list[dict] = []

    for staff in staff_list:
        avail_days = calculate_available_days(
            staff.identifier, vacations, quarter_start, quarter_end,
            effective_start=staff.available_from,
        )
        # Skip staff with zero available days (e.g. available_from > quarter_end);
        # they have no presence in this quarter and must not skew group means.
        if avail_days <= 0:
            continue

        weekends = schedule.count_weekend_shifts(staff.identifier)
        effective_nights = schedule.count_effective_nights(staff.identifier, staff)
        total_notdienst = weekends + effective_nights

        presence_factor = avail_days / total_days if total_days > 0 else 1.0

        if staff.hours > 0 and presence_factor > 0:
            normalized_40h = (total_notdienst / staff.hours / presence_factor) * 40
        else:
            normalized_40h = 0.0

        entry = {
            "identifier": staff.identifier,
            "name": staff.name,
            "beruf": staff.beruf.value,
            "hours": staff.hours,
            "effective_nights": round(effective_nights, 4),
            "weekend_shifts": weekends,
            "total_notdienst": round(total_notdienst, 4),
            "normalized_40h": round(normalized_40h, 4),
        }
        all_entries.append(entry)

        entries_by_beruf.setdefault(staff.beruf.value, []).append(entry)

    # Group means
    group_means: dict[str, float] = {}
    for beruf, entries in entries_by_beruf.items():
        group_means[beruf] = (
            sum(e["normalized_40h"] for e in entries) / len(entries)
            if entries
            else 0.0
        )

    result: list[CarryForwardEntry] = []
    for entry in all_entries:
        mean = group_means.get(entry["beruf"], 0.0)
        delta = entry["normalized_40h"] - mean
        result.append(
            CarryForwardEntry(
                identifier=entry["identifier"],
                name=entry["name"],
                beruf=entry["beruf"],
                hours=entry["hours"],
                effective_nights=entry["effective_nights"],
                weekend_shifts=entry["weekend_shifts"],
                total_notdienst=entry["total_notdienst"],
                normalized_40h=round(entry["normalized_40h"], 4),
                group_mean_40h=round(mean, 4),
                carry_forward_delta=round(delta, 4),
            )
        )
    return result


def build_previous_context(
    schedule: Schedule,
    staff_list: list[Staff],
    vacations: list[Vacation] | None = None,
    trailing_days: int = 21,
) -> PreviousPlanContext:
    """Build complete carry-forward context from a finished schedule.

    Extracts:
    1. Per-person fairness deltas (for solver fairness objective).
    2. Trailing assignments from last ``trailing_days`` days (for boundary
       constraint enforcement across quarters).
    """
    quarter_end = schedule.quarter_end
    cutoff = quarter_end - timedelta(days=trailing_days - 1)

    trailing: list[TrailingAssignment] = []
    for a in schedule.assignments:
        if a.shift.shift_date >= cutoff:
            trailing.append(
                TrailingAssignment(
                    shift_date=a.shift.shift_date,
                    shift_type=a.shift.shift_type,
                    staff_identifier=a.staff_identifier,
                    is_paired=a.is_paired,
                )
            )

    return PreviousPlanContext(
        quarter_start=schedule.quarter_start,
        quarter_end=schedule.quarter_end,
        carry_forward=compute_carry_forward(schedule, staff_list, vacations),
        trailing_assignments=trailing,
    )


def build_previous_context_from_xlsx(
    source: "Path | str | IO[bytes]",
    staff_list: list[Staff],
    trailing_days: int = 21,
) -> PreviousPlanContext:
    """Build a carry-forward context by parsing a previous quarter's xlsx.

    Parses the long-format *Arbeitseinsätze* xlsx (one row per assignment),
    auto-detects the quarter boundaries from the date range in the file, and
    delegates to :func:`build_previous_context`.

    Vacation data is intentionally omitted: staff absent in the previous quarter
    carry a negative delta, which combined with their higher presence in the next
    quarter naturally rebalances workload over the year.

    Args:
        source: Path or file-like object for the xlsx (e.g. Streamlit UploadedFile).
        staff_list: Staff for the *new* quarter — used for beruf/hours normalisation.
        trailing_days: Number of days at the end of the previous quarter whose
            assignments are forwarded as boundary constraints (default 21).

    Raises:
        FileFormatError: If the xlsx is missing required columns.
        ValueError: If a ShiftType value in the file is not recognised.
    """
    raw = _parse_previous_plan_xlsx(source)
    if not raw:
        raise ValueError("The uploaded xlsx contains no valid assignment rows.")

    assignments: list[Assignment] = []
    for row in raw:
        assignments.append(
            Assignment(
                shift=Shift(
                    shift_type=ShiftType(row["shift_type"]),
                    shift_date=row["shift_date"],
                ),
                staff_identifier=row["staff_identifier"],
                is_paired=row["is_paired"],
            )
        )

    all_dates = [a.shift.shift_date for a in assignments]
    quarter_start = min(all_dates)
    quarter_end = max(all_dates)

    schedule = Schedule(
        quarter_start=quarter_start,
        quarter_end=quarter_end,
        assignments=assignments,
    )
    return build_previous_context(schedule, staff_list, vacations=None, trailing_days=trailing_days)


@dataclass
class SchedulerConfig:
    """Configurable solver constraint parameters.

    All fields correspond to hard constraints that may need adjustment
    per quarter or per stakeholder request.
    """

    intern_min_nights: int = 6
    intern_max_nights: int = 9
    block_gap_days: int = 21
    holiday_gap_days: int = 7
