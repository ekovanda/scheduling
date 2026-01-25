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
    TA = "TA"


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
    reception: bool  # Can work reception/Anmeldung
    nd_possible: bool  # Can do night shifts at all
    nd_alone: bool  # Can work nights solo (False = must pair)
    nd_count: list[int]  # Allowed consecutive night counts [1], [2], [1,2], etc.
    nd_exceptions: list[int] = Field(default_factory=list)  # Weekdays (1=Mon, 7=Sun) excluded

    @field_validator("nd_count", "nd_exceptions", mode="before")
    @classmethod
    def parse_json_array(cls, v: Any) -> list[int]:
        """Parse JSON string arrays from CSV."""
        if isinstance(v, str):
            return json.loads(v)
        return v

    def effective_nights_weight(self, is_paired: bool) -> float:
        """Calculate effective night weight for fairness.

        Paired nights count as 0.5 per person (two people share the shift).
        Solo nights count as 1.0.
        """
        return 0.5 if is_paired else 1.0

    def can_work_shift(self, shift_type: ShiftType, shift_date: date) -> bool:
        """Check basic eligibility for a shift type on a given date."""
        # Minors cannot work Sundays
        if not self.adult and shift_type.value.startswith("So_"):
            return False

        # TAs never work weekends
        if self.beruf == Beruf.TA and (
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

        # Saturday 10-19 must be Azubi with reception=False
        if shift_type == ShiftType.SATURDAY_10_19:
            return self.beruf == Beruf.AZUBI and not self.reception

        # Saturday 10-21 prefers Azubi with reception or TFA
        if shift_type == ShiftType.SATURDAY_10_21:
            if self.beruf == Beruf.AZUBI:
                return self.reception
            return self.beruf == Beruf.TFA

        # Sunday 8-20:30 must be adult Azubi
        if shift_type == ShiftType.SUNDAY_8_2030:
            return self.beruf == Beruf.AZUBI and self.adult

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

    def count_effective_nights(self, staff_identifier: str) -> float:
        """Count effective nights for a staff member (paired = 0.5, solo = 1.0)."""
        night_assignments = [
            a for a in self.get_staff_assignments(staff_identifier) if a.shift.is_night_shift()
        ]
        return sum(0.5 if a.is_paired else 1.0 for a in night_assignments)

    def count_weekend_shifts(self, staff_identifier: str) -> int:
        """Count weekend shifts for a staff member."""
        return sum(
            1 for a in self.get_staff_assignments(staff_identifier) if a.shift.is_weekend_shift()
        )

    def count_total_notdienst(self, staff_identifier: str) -> float:
        """Count total Notdienst (weekends + effective nights)."""
        return self.count_weekend_shifts(staff_identifier) + self.count_effective_nights(
            staff_identifier
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
