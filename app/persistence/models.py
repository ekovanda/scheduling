"""Persistent data models for the Single Source of Truth (SSOT) architecture."""

from datetime import UTC, date, datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, model_validator

from app.scheduler.feasibility import (
    DiagnosticSeverity,
    FeasibilityReportRecord,
    InfeasibilityCategory,
    InfeasibilityDiagnosticRecord,
)
from app.scheduler.models import Abteilung, Beruf, ShiftType, Staff


class AbsenceType(str, Enum):
    """Type of staff absence."""

    VACATION = "Vacation"
    SICK_LEAVE = "SickLeave"
    SPECIAL_LEAVE = "SpecialLeave"
    TRAINING = "Training"


class ScheduleState(str, Enum):
    """Lifecycle state of a quarterly schedule."""

    DRAFT = "DRAFT"
    PUBLISHED = "PUBLISHED"
    ACTIVE = "ACTIVE"
    CLOSED = "CLOSED"


class StaffMember(BaseModel):
    """Master staff record in persistent datastore."""

    id: str
    identifier: str
    name: str
    beruf: Beruf = Beruf.TFA
    abteilung: Abteilung = Abteilung.OTHER
    hours: int = 40
    adult: bool = True
    reception: bool = False
    nd_possible: bool = True
    nd_alone: bool = True
    nd_min_consecutive: int = 2
    nd_max_consecutive: int | None = None
    nd_exceptions: list[int] = Field(default_factory=list)
    birthday: str | None = None
    available_from: date | None = None
    is_active: bool = True
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    def to_scheduler_staff(self) -> Staff:
        """Convert persistent staff record to core scheduler domain model."""
        return Staff(
            name=self.name,
            identifier=self.identifier,
            adult=self.adult,
            hours=self.hours,
            beruf=self.beruf,
            abteilung=self.abteilung,
            reception=self.reception,
            nd_possible=self.nd_possible,
            nd_alone=self.nd_alone,
            nd_max_consecutive=self.nd_max_consecutive,
            nd_min_consecutive=self.nd_min_consecutive,
            nd_exceptions=list(self.nd_exceptions),
            birthday=self.birthday,
            available_from=self.available_from,
        )

    @classmethod
    def from_scheduler_staff(
        cls,
        staff: Staff,
        staff_id: str | None = None,
        is_active: bool = True,
    ) -> "StaffMember":
        """Instantiate a persistent staff record from a scheduler domain model."""
        return cls(
            id=staff_id or staff.identifier,
            identifier=staff.identifier,
            name=staff.name,
            beruf=staff.beruf,
            abteilung=staff.abteilung,
            hours=staff.hours,
            adult=staff.adult,
            reception=staff.reception,
            nd_possible=staff.nd_possible,
            nd_alone=staff.nd_alone,
            nd_min_consecutive=staff.nd_min_consecutive,
            nd_max_consecutive=staff.nd_max_consecutive,
            nd_exceptions=list(staff.nd_exceptions),
            birthday=staff.birthday,
            available_from=staff.available_from,
            is_active=is_active,
        )


class AbsenceRecord(BaseModel):
    """Continuous absence ledger entry for vacations, sick leave, or training."""

    id: str
    staff_id: str
    absence_type: AbsenceType = AbsenceType.VACATION
    start_date: date
    end_date: date
    note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_date_range(self) -> "AbsenceRecord":
        """Ensure start_date is not after end_date."""
        if self.start_date > self.end_date:
            raise ValueError(
                f"Absence start_date ({self.start_date}) cannot be after end_date ({self.end_date})"
            )
        return self


class ShiftAssignmentRecord(BaseModel):
    """Detailed assignment record with planned vs. actual tracking for shift swaps."""

    shift_date: date
    shift_type: ShiftType
    planned_staff_id: str
    actual_staff_id: str
    is_paired: bool
    is_override: bool = False
    override_reason: str | None = None
    override_timestamp: datetime | None = None


class QuarterScheduleDocument(BaseModel):
    """Quarterly schedule document representing candidate, active, or closed state."""

    quarter_key: str
    year: int
    quarter: int
    state: ScheduleState = ScheduleState.DRAFT
    config: dict[str, Any] = Field(default_factory=dict)
    assignments: list[ShiftAssignmentRecord] = Field(default_factory=list)
    solver_metrics: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))

    @model_validator(mode="after")
    def validate_quarter_key(self) -> "QuarterScheduleDocument":
        """Ensure quarter_key matches year and quarter integers."""
        expected_key = f"{self.year}-Q{self.quarter}"
        if self.quarter_key != expected_key:
            raise ValueError(
                f"quarter_key '{self.quarter_key}' does not match expected '{expected_key}'"
            )
        return self


class SolverJobStatus(str, Enum):
    """Execution state of an asynchronous background solver job."""

    IDLE = "IDLE"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"


class SolverJobRecord(BaseModel):
    """Persistent execution record and live metrics for a background solve."""

    job_id: str
    quarter_key: str
    status: SolverJobStatus = SolverJobStatus.RUNNING
    started_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None
    max_solve_time_seconds: int = 120
    elapsed_seconds: float = 0.0
    solutions_found: int = 0
    best_objective: float | None = None
    soft_penalty: float | None = None
    error: str | None = None
    diagnostics: list[InfeasibilityDiagnosticRecord] = Field(default_factory=list)


class PreAssignedShiftRecord(BaseModel):
    """Pre-assigned (holiday or locked) shift record in persistent datastore."""

    id: str
    staff_id: str
    staff_identifier: str
    shift_date: date
    shift_type: str
    is_holiday: bool = True
    note: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


__all__ = [
    "AbsenceRecord",
    "AbsenceType",
    "DiagnosticSeverity",
    "FeasibilityReportRecord",
    "InfeasibilityCategory",
    "InfeasibilityDiagnosticRecord",
    "PreAssignedShiftRecord",
    "QuarterScheduleDocument",
    "ScheduleState",
    "ShiftAssignmentRecord",
    "SolverJobRecord",
    "SolverJobStatus",
    "StaffMember",
]


