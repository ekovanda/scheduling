"""Google Cloud Firestore persistence implementation for the SSOT architecture."""

import os
from datetime import date
from typing import Any

from google.cloud import firestore

from app.persistence.exceptions import EntityNotFoundError
from app.persistence.models import (
    AbsenceRecord,
    PreAssignedShiftRecord,
    QuarterScheduleDocument,
    SolverJobRecord,
    StaffMember,
)


class FirestoreRepository:
    """Google Cloud Firestore repository implementing RepositoryProtocol.

    Provides serverless, atomic, multi-planner document persistence in GCP
    (typically europe-west3).
    """

    def __init__(
        self,
        project: str | None = None,
        database: str | None = None,
        client: Any | None = None,
    ) -> None:
        """Initialize Firestore client and collection handles."""
        if client is not None:
            self.client = client
        else:
            proj = project or os.getenv("GCP_PROJECT") or os.getenv("GOOGLE_CLOUD_PROJECT")
            try:
                self.client = firestore.Client(project=proj, database=database)
            except Exception:  # pylint: disable=broad-except
                # Developer fallback: check for gcloud auth token if running locally outside Cloud Run
                import shutil
                import subprocess
                from pathlib import Path

                from google.oauth2.credentials import Credentials  # type: ignore[import-untyped]

                gcloud_bin = shutil.which("gcloud") or str(Path.home() / "google-cloud-sdk/bin/gcloud")
                try:
                    token = subprocess.check_output(
                        [gcloud_bin, "auth", "print-access-token"], text=True
                    ).strip()
                    creds = Credentials(token)
                    self.client = firestore.Client(project=proj, database=database, credentials=creds)
                except Exception:
                    raise

        self.staff_col = self.client.collection("staff")
        self.absence_col = self.client.collection("absences")
        self.schedule_col = self.client.collection("schedules")
        self.job_col = self.client.collection("solver_jobs")
        self.preassigned_col = self.client.collection("preassigned")

    # -------------------------------------------------------------------------
    # Staff Member CRUD
    # -------------------------------------------------------------------------

    def get_staff(self, staff_id: str) -> StaffMember | None:
        doc = self.staff_col.document(staff_id).get()
        if not doc.exists:
            return None
        return StaffMember.model_validate(doc.to_dict())

    def list_staff(self, active_only: bool = True) -> list[StaffMember]:
        query = self.staff_col
        if active_only:
            query = query.where("is_active", "==", True)
        docs = query.stream()
        members = [StaffMember.model_validate(d.to_dict()) for d in docs]
        return sorted(members, key=lambda m: m.identifier)

    def save_staff(self, member: StaffMember) -> None:
        self.staff_col.document(member.id).set(member.model_dump(mode="json"))

    def delete_staff(self, staff_id: str) -> None:
        doc_ref = self.staff_col.document(staff_id)
        if not doc_ref.get().exists:
            raise EntityNotFoundError(f"Staff member with id '{staff_id}' does not exist.")
        doc_ref.delete()

    # -------------------------------------------------------------------------
    # Absence Record CRUD
    # -------------------------------------------------------------------------

    def get_absence(self, absence_id: str) -> AbsenceRecord | None:
        doc = self.absence_col.document(absence_id).get()
        if not doc.exists:
            return None
        return AbsenceRecord.model_validate(doc.to_dict())

    def list_absences_by_staff(self, staff_id: str) -> list[AbsenceRecord]:
        docs = self.absence_col.where("staff_id", "==", staff_id).stream()
        records = [AbsenceRecord.model_validate(d.to_dict()) for d in docs]
        return sorted(records, key=lambda r: r.start_date)

    def list_absences_for_range(
        self, start: date, end: date, staff_id: str | None = None
    ) -> list[AbsenceRecord]:
        query = self.absence_col
        if staff_id:
            query = query.where("staff_id", "==", staff_id)
        # Filter on start_date <= end, then filter end_date >= start in memory
        # to avoid requiring a composite multi-inequality index in Firestore
        query = query.where("start_date", "<=", end.isoformat())
        docs = query.stream()
        records = [AbsenceRecord.model_validate(d.to_dict()) for d in docs]
        matching = [r for r in records if r.end_date >= start]
        return sorted(matching, key=lambda r: r.start_date)

    def save_absence(self, absence: AbsenceRecord) -> None:
        self.absence_col.document(absence.id).set(absence.model_dump(mode="json"))

    def delete_absence(self, absence_id: str) -> None:
        doc_ref = self.absence_col.document(absence_id)
        if not doc_ref.get().exists:
            raise EntityNotFoundError(f"Absence record with id '{absence_id}' does not exist.")
        doc_ref.delete()

    # -------------------------------------------------------------------------
    # Quarter Schedule Document CRUD
    # -------------------------------------------------------------------------

    def get_schedule(self, quarter_key: str) -> QuarterScheduleDocument | None:
        doc = self.schedule_col.document(quarter_key).get()
        if not doc.exists:
            return None
        return QuarterScheduleDocument.model_validate(doc.to_dict())

    def list_schedules(self) -> list[QuarterScheduleDocument]:
        docs = self.schedule_col.stream()
        schedules = [QuarterScheduleDocument.model_validate(d.to_dict()) for d in docs]
        return sorted(schedules, key=lambda s: (s.year, s.quarter))

    def save_schedule(self, document: QuarterScheduleDocument) -> None:
        self.schedule_col.document(document.quarter_key).set(document.model_dump(mode="json"))

    def delete_schedule(self, quarter_key: str) -> None:
        doc_ref = self.schedule_col.document(quarter_key)
        if not doc_ref.get().exists:
            raise EntityNotFoundError(f"Schedule for '{quarter_key}' does not exist.")
        doc_ref.delete()

    # -------------------------------------------------------------------------
    # Solver Job Record CRUD
    # -------------------------------------------------------------------------

    def get_solver_job(self, quarter_key: str) -> SolverJobRecord | None:
        doc = self.job_col.document(quarter_key).get()
        if not doc.exists:
            return None
        return SolverJobRecord.model_validate(doc.to_dict())

    def save_solver_job(self, record: SolverJobRecord) -> None:
        self.job_col.document(record.quarter_key).set(record.model_dump(mode="json"))

    def delete_solver_job(self, quarter_key: str) -> None:
        doc_ref = self.job_col.document(quarter_key)
        if not doc_ref.get().exists:
            raise EntityNotFoundError(f"Solver job for '{quarter_key}' does not exist.")
        doc_ref.delete()

    # -------------------------------------------------------------------------
    # Pre-Assigned Shifts CRUD
    # -------------------------------------------------------------------------

    def get_preassigned(self, preassigned_id: str) -> PreAssignedShiftRecord | None:
        doc = self.preassigned_col.document(preassigned_id).get()
        if not doc.exists:
            return None
        return PreAssignedShiftRecord.model_validate(doc.to_dict())

    def list_preassigned(self) -> list[PreAssignedShiftRecord]:
        docs = self.preassigned_col.stream()
        records = [PreAssignedShiftRecord.model_validate(d.to_dict()) for d in docs]
        return sorted(records, key=lambda r: (r.shift_date, r.shift_type))

    def save_preassigned(self, record: PreAssignedShiftRecord) -> None:
        self.preassigned_col.document(record.id).set(record.model_dump(mode="json"))

    def delete_preassigned(self, preassigned_id: str) -> None:
        doc_ref = self.preassigned_col.document(preassigned_id)
        if not doc_ref.get().exists:
            raise EntityNotFoundError(
                f"Pre-assigned shift '{preassigned_id}' does not exist."
            )
        doc_ref.delete()


