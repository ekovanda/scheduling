"""Data models for staff, shifts, and schedules."""

import csv
import json
from datetime import date, timedelta
from enum import Enum
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator


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


def generate_quarter_shifts(quarter_start: date) -> list[Shift]:
    """Generate all shifts for a quarter (13 weeks)."""
    shifts: list[Shift] = []
    current_date = quarter_start

    # Q2/2026: April 1 - June 30 (91 days, 13 weeks)
    quarter_end = quarter_start + timedelta(days=91)

    while current_date < quarter_end:
        weekday = current_date.weekday()  # 0=Mon, 5=Sat, 6=Sun

        # Saturday shifts
        if weekday == 5:
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
) -> int:
    """Calculate number of available (non-vacation) days in the quarter."""
    total_days = (quarter_end - quarter_start).days + 1
    unavailable = get_staff_unavailable_dates(vacations, staff_identifier)
    # Only count vacation days that fall within the quarter
    vacation_days_in_quarter = sum(
        1 for d in unavailable if quarter_start <= d <= quarter_end
    )
    return total_days - vacation_days_in_quarter
