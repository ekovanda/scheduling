"""Repository protocols and flat JSON file storage implementations."""

import json
import os
import tempfile
from datetime import date, datetime
from pathlib import Path
from typing import Any, Protocol

from app.persistence.exceptions import EntityNotFoundError
from app.persistence.models import (
    AbsenceRecord,
    QuarterScheduleDocument,
    StaffMember,
)


class StaffRepositoryProtocol(Protocol):
    """Protocol for master staff member persistence."""

    def get(self, staff_id: str) -> StaffMember | None:
        """Retrieve staff member by ID."""

    def list(self, active_only: bool = True) -> list[StaffMember]:
        """List staff members, optionally filtering by active status."""

    def save(self, member: StaffMember) -> None:
        """Persist or update staff member."""

    def delete(self, staff_id: str) -> None:
        """Delete staff member by ID."""


class AbsenceRepositoryProtocol(Protocol):
    """Protocol for continuous absence ledger persistence."""

    def get(self, absence_id: str) -> AbsenceRecord | None:
        """Retrieve absence record by ID."""

    def list_by_staff(self, staff_id: str) -> list[AbsenceRecord]:
        """List absences for a specific staff member."""

    def list_for_range(
        self, start: date, end: date, staff_id: str | None = None
    ) -> list[AbsenceRecord]:
        """List absences overlapping a specific date range."""

    def save(self, absence: AbsenceRecord) -> None:
        """Persist or update absence record."""

    def delete(self, absence_id: str) -> None:
        """Delete absence record by ID."""


class ScheduleRepositoryProtocol(Protocol):
    """Protocol for quarterly schedule document persistence."""

    def get(self, quarter_key: str) -> QuarterScheduleDocument | None:
        """Retrieve quarter schedule document by key (e.g. '2026-Q2')."""

    def list(self) -> list[QuarterScheduleDocument]:
        """List all saved quarter schedule documents."""

    def save(self, document: QuarterScheduleDocument) -> None:
        """Persist or update quarter schedule document."""

    def delete(self, quarter_key: str) -> None:
        """Delete quarter schedule document by key."""


def _json_serial(obj: Any) -> Any:
    """JSON serializer for objects not serializable by default json code."""
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Type {type(obj)} not serializable")


class FileJsonRepository:
    """Flat, file-based JSON repository with atomic writes.

    Designed for simplicity and fast local/testing workflows before deploying
    managed cloud datastores like Firestore.
    """

    def __init__(self, base_dir: str | Path = "data/db") -> None:
        self.base_dir = Path(base_dir)
        self.staff_dir = self.base_dir / "staff"
        self.absence_dir = self.base_dir / "absences"
        self.schedule_dir = self.base_dir / "schedules"

        self.staff_dir.mkdir(parents=True, exist_ok=True)
        self.absence_dir.mkdir(parents=True, exist_ok=True)
        self.schedule_dir.mkdir(parents=True, exist_ok=True)

    def _atomic_write_json(self, target_path: Path, data: dict[str, Any]) -> None:
        """Write JSON atomically using a temporary file in the same directory."""
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=target_path.parent,
            delete=False,
        ) as tmp_file:
            json.dump(data, tmp_file, default=_json_serial, indent=2, ensure_ascii=False)
            tmp_path = Path(tmp_file.name)
        os.replace(tmp_path, target_path)

    # -------------------------------------------------------------------------
    # Staff Member CRUD
    # -------------------------------------------------------------------------

    def get_staff(self, staff_id: str) -> StaffMember | None:
        path = self.staff_dir / f"{staff_id}.json"
        if not path.is_file():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return StaffMember.model_validate(data)

    def list_staff(self, active_only: bool = True) -> list[StaffMember]:
        members: list[StaffMember] = []
        for path in sorted(self.staff_dir.glob("*.json")):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            member = StaffMember.model_validate(data)
            if not active_only or member.is_active:
                members.append(member)
        return members

    def save_staff(self, member: StaffMember) -> None:
        path = self.staff_dir / f"{member.id}.json"
        self._atomic_write_json(path, member.model_dump(mode="json"))

    def delete_staff(self, staff_id: str) -> None:
        path = self.staff_dir / f"{staff_id}.json"
        if not path.is_file():
            raise EntityNotFoundError(f"Staff member with id '{staff_id}' does not exist.")
        path.unlink()

    # -------------------------------------------------------------------------
    # Absence Record CRUD
    # -------------------------------------------------------------------------

    def get_absence(self, absence_id: str) -> AbsenceRecord | None:
        path = self.absence_dir / f"{absence_id}.json"
        if not path.is_file():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return AbsenceRecord.model_validate(data)

    def list_absences_by_staff(self, staff_id: str) -> list[AbsenceRecord]:
        absences: list[AbsenceRecord] = []
        for path in sorted(self.absence_dir.glob("*.json")):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            rec = AbsenceRecord.model_validate(data)
            if rec.staff_id == staff_id:
                absences.append(rec)
        return sorted(absences, key=lambda a: a.start_date)

    def list_absences_for_range(
        self, start: date, end: date, staff_id: str | None = None
    ) -> list[AbsenceRecord]:
        absences: list[AbsenceRecord] = []
        for path in sorted(self.absence_dir.glob("*.json")):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            rec = AbsenceRecord.model_validate(data)
            if staff_id and rec.staff_id != staff_id:
                continue
            # Absence overlaps [start, end] if rec.start_date <= end and rec.end_date >= start
            if rec.start_date <= end and rec.end_date >= start:
                absences.append(rec)
        return sorted(absences, key=lambda a: a.start_date)

    def save_absence(self, absence: AbsenceRecord) -> None:
        path = self.absence_dir / f"{absence.id}.json"
        self._atomic_write_json(path, absence.model_dump(mode="json"))

    def delete_absence(self, absence_id: str) -> None:
        path = self.absence_dir / f"{absence_id}.json"
        if not path.is_file():
            raise EntityNotFoundError(f"Absence record with id '{absence_id}' does not exist.")
        path.unlink()

    # -------------------------------------------------------------------------
    # Quarter Schedule Document CRUD
    # -------------------------------------------------------------------------

    def get_schedule(self, quarter_key: str) -> QuarterScheduleDocument | None:
        path = self.schedule_dir / f"{quarter_key}.json"
        if not path.is_file():
            return None
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        return QuarterScheduleDocument.model_validate(data)

    def list_schedules(self) -> list[QuarterScheduleDocument]:
        docs: list[QuarterScheduleDocument] = []
        for path in sorted(self.schedule_dir.glob("*.json")):
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            docs.append(QuarterScheduleDocument.model_validate(data))
        return sorted(docs, key=lambda d: (d.year, d.quarter))

    def save_schedule(self, document: QuarterScheduleDocument) -> None:
        path = self.schedule_dir / f"{document.quarter_key}.json"
        self._atomic_write_json(path, document.model_dump(mode="json"))

    def delete_schedule(self, quarter_key: str) -> None:
        path = self.schedule_dir / f"{quarter_key}.json"
        if not path.is_file():
            raise EntityNotFoundError(f"Schedule for '{quarter_key}' does not exist.")
        path.unlink()
