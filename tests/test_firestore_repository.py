"""Unit tests for the Firestore repository adapter with mocked GCP client."""

from datetime import date
from unittest.mock import MagicMock

import pytest

from app.persistence.exceptions import EntityNotFoundError
from app.persistence.firestore_repository import FirestoreRepository
from app.persistence.models import (
    AbsenceRecord,
    AbsenceType,
    PreAssignedShiftRecord,
    QuarterScheduleDocument,
    ScheduleState,
    ShiftAssignmentRecord,
    SolverJobRecord,
    SolverJobStatus,
    StaffMember,
)
from app.persistence.repository import RepositoryProtocol
from app.scheduler.models import ShiftType


class FakeDocSnapshot:
    """Mock Firestore DocumentSnapshot."""

    def __init__(self, doc_id: str, data: dict | None, exists: bool = True) -> None:
        self.id = doc_id
        self._data = data
        self.exists = exists

    def to_dict(self) -> dict | None:
        return self._data


def _build_mock_firestore_client() -> tuple[FirestoreRepository, dict[str, dict[str, dict]]]:
    """Build an in-memory dictionary mock simulating a Firestore Client."""
    db_store: dict[str, dict[str, dict]] = {
        "staff": {},
        "absences": {},
        "schedules": {},
        "solver_jobs": {},
        "preassigned": {},
    }

    mock_client = MagicMock()

    def mock_collection(col_name: str) -> MagicMock:
        col = MagicMock()

        def mock_document(doc_id: str) -> MagicMock:
            doc_ref = MagicMock()

            def mock_get() -> FakeDocSnapshot:
                if doc_id in db_store[col_name]:
                    return FakeDocSnapshot(doc_id, db_store[col_name][doc_id], exists=True)
                return FakeDocSnapshot(doc_id, None, exists=False)

            def mock_set(data: dict) -> None:
                db_store[col_name][doc_id] = data

            def mock_delete() -> None:
                db_store[col_name].pop(doc_id, None)

            doc_ref.get = mock_get
            doc_ref.set = mock_set
            doc_ref.delete = mock_delete
            return doc_ref

        def mock_stream() -> list[FakeDocSnapshot]:
            return [
                FakeDocSnapshot(k, v, exists=True) for k, v in db_store[col_name].items()
            ]

        def mock_where(*args, **kwargs) -> MagicMock:
            # Simple chainable query mock
            sub_query = MagicMock()
            sub_query.stream = mock_stream
            sub_query.where = mock_where
            return sub_query

        col.document = mock_document
        col.stream = mock_stream
        col.where = mock_where
        return col

    mock_client.collection = mock_collection
    repo = FirestoreRepository(client=mock_client)
    return repo, db_store


def test_firestore_repo_conforms_to_protocol() -> None:
    """Verify FirestoreRepository conforms to RepositoryProtocol."""
    repo, _ = _build_mock_firestore_client()
    assert isinstance(repo, RepositoryProtocol)


def test_firestore_staff_crud() -> None:
    """Test Firestore staff CRUD operations."""
    repo, _ = _build_mock_firestore_client()

    member = StaffMember(id="STAFF_01", identifier="MUE", name="Dr. Müller", hours=40)
    repo.save_staff(member)

    loaded = repo.get_staff("STAFF_01")
    assert loaded is not None
    assert loaded.identifier == "MUE"
    assert loaded.name == "Dr. Müller"

    staff_list = repo.list_staff(active_only=True)
    assert len(staff_list) == 1
    assert staff_list[0].id == "STAFF_01"

    repo.delete_staff("STAFF_01")
    assert repo.get_staff("STAFF_01") is None

    with pytest.raises(EntityNotFoundError):
        repo.delete_staff("NON_EXISTENT")


def test_firestore_absence_crud_and_range() -> None:
    """Test Firestore absence records and date range filtering."""
    repo, _ = _build_mock_firestore_client()

    rec = AbsenceRecord(
        id="ABS_01",
        staff_id="STAFF_01",
        absence_type=AbsenceType.VACATION,
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 20),
    )
    repo.save_absence(rec)

    loaded = repo.get_absence("ABS_01")
    assert loaded is not None
    assert loaded.staff_id == "STAFF_01"

    # Overlapping ranges
    assert len(repo.list_absences_for_range(date(2026, 4, 15), date(2026, 4, 25))) == 1
    assert len(repo.list_absences_for_range(date(2026, 4, 1), date(2026, 4, 12))) == 1
    # Non-overlapping range
    assert len(repo.list_absences_for_range(date(2026, 5, 1), date(2026, 5, 10))) == 0

    repo.delete_absence("ABS_01")
    assert repo.get_absence("ABS_01") is None


def test_firestore_schedule_lifecycle() -> None:
    """Test Firestore quarter schedule document lifecycle."""
    repo, _ = _build_mock_firestore_client()

    doc = QuarterScheduleDocument(
        quarter_key="2026-Q2",
        year=2026,
        quarter=2,
        state=ScheduleState.DRAFT,
        assignments=[
            ShiftAssignmentRecord(
                shift_date=date(2026, 4, 1),
                shift_type=ShiftType.NIGHT_WED_THU,
                planned_staff_id="MUE",
                actual_staff_id="MUE",
                is_paired=False,
            )
        ],
    )
    repo.save_schedule(doc)

    loaded = repo.get_schedule("2026-Q2")
    assert loaded is not None
    assert loaded.quarter_key == "2026-Q2"
    assert len(loaded.assignments) == 1

    schedules = repo.list_schedules()
    assert len(schedules) == 1

    repo.delete_schedule("2026-Q2")
    assert repo.get_schedule("2026-Q2") is None


def test_firestore_solver_job_lifecycle() -> None:
    """Test Firestore background solver job persistence."""
    repo, _ = _build_mock_firestore_client()

    job = SolverJobRecord(
        job_id="job_test_01",
        quarter_key="2026-Q2",
        status=SolverJobStatus.RUNNING,
        max_solve_time_seconds=600,
    )
    repo.save_solver_job(job)

    loaded = repo.get_solver_job("2026-Q2")
    assert loaded is not None
    assert loaded.job_id == "job_test_01"
    assert loaded.status == SolverJobStatus.RUNNING

    loaded.status = SolverJobStatus.COMPLETED
    loaded.best_objective = 42.0
    repo.save_solver_job(loaded)

    reloaded = repo.get_solver_job("2026-Q2")
    assert reloaded is not None
    assert reloaded.status == SolverJobStatus.COMPLETED
    assert reloaded.best_objective == 42.0

    repo.delete_solver_job("2026-Q2")
    assert repo.get_solver_job("2026-Q2") is None


def test_firestore_preassigned_crud_lifecycle() -> None:
    """Test Firestore repository pre-assigned shift CRUD operations."""
    repo, store = _build_mock_firestore_client()
    assert isinstance(repo, RepositoryProtocol)

    record = PreAssignedShiftRecord(
        id="pa-easter-1",
        staff_id="ks",
        staff_identifier="KS",
        shift_date=date(2027, 3, 25),
        shift_type="N_Do-Fr",
        is_holiday=True,
    )
    repo.save_preassigned(record)

    loaded = repo.get_preassigned("pa-easter-1")
    assert loaded is not None
    assert loaded.staff_identifier == "KS"
    assert loaded.shift_date == date(2027, 3, 25)

    all_pa = repo.list_preassigned()
    assert len(all_pa) == 1
    assert all_pa[0].id == "pa-easter-1"

    repo.delete_preassigned("pa-easter-1")
    assert repo.get_preassigned("pa-easter-1") is None
    assert len(repo.list_preassigned()) == 0


