"""Unit tests for the persistence layer models and repository."""

from datetime import date
from pathlib import Path

import pytest

from app.persistence.exceptions import EntityNotFoundError
from app.persistence.models import (
    AbsenceRecord,
    AbsenceType,
    QuarterScheduleDocument,
    ScheduleState,
    ShiftAssignmentRecord,
    SolverJobRecord,
    SolverJobStatus,
    StaffMember,
)
from app.persistence.repository import FileJsonRepository
from app.scheduler.models import Abteilung, Beruf, ShiftType, Staff


@pytest.fixture
def temp_repo(tmp_path: Path) -> FileJsonRepository:
    """Fixture providing an isolated FileJsonRepository in a temporary directory."""
    return FileJsonRepository(base_dir=tmp_path / "db")


def test_staff_member_conversion_bidirectional() -> None:
    """Test converting between persistent StaffMember and scheduler domain Staff."""
    staff = Staff(
        name="Anna Schmidt",
        identifier="SCH",
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        abteilung=Abteilung.STATION,
        reception=True,
        nd_possible=True,
        nd_alone=True,
        nd_max_consecutive=3,
        nd_min_consecutive=2,
        nd_exceptions=[1, 2],
        birthday="05-12",
        available_from=date(2026, 1, 1),
    )

    member = StaffMember.from_scheduler_staff(staff, staff_id="SCH")
    assert member.id == "SCH"
    assert member.identifier == "SCH"
    assert member.beruf == Beruf.TFA
    assert member.hours == 40
    assert member.is_active is True

    converted_back = member.to_scheduler_staff()
    assert converted_back.name == staff.name
    assert converted_back.identifier == staff.identifier
    assert converted_back.beruf == Beruf.TFA
    assert converted_back.hours == 40
    assert converted_back.available_from == date(2026, 1, 1)

    # Vet role enforces hours=0 invariant
    vet = Staff(
        name="Dr. Müller",
        identifier="MUE",
        adult=True,
        hours=0,
        beruf=Beruf.VET,
        reception=False,
        nd_possible=True,
        nd_alone=True,
    )
    vet_member = StaffMember.from_scheduler_staff(vet)
    assert vet_member.beruf == Beruf.VET
    assert vet_member.to_scheduler_staff().hours == 0


def test_absence_record_date_validation() -> None:
    """Ensure AbsenceRecord raises ValueError when start_date > end_date."""
    with pytest.raises(ValueError, match="start_date .* cannot be after end_date"):
        AbsenceRecord(
            id="ABS_1",
            staff_id="MUE",
            absence_type=AbsenceType.VACATION,
            start_date=date(2026, 6, 10),
            end_date=date(2026, 6, 5),
        )


def test_quarter_key_validation() -> None:
    """Ensure QuarterScheduleDocument raises ValueError if quarter_key mismatches year/quarter."""
    with pytest.raises(ValueError, match="quarter_key .* does not match expected"):
        QuarterScheduleDocument(
            quarter_key="2026-Q1",
            year=2026,
            quarter=2,
        )


def test_staff_repository_crud(temp_repo: FileJsonRepository) -> None:
    """Test CRUD operations on StaffRepository."""
    m1 = StaffMember(id="STAFF_01", identifier="MUE", name="Müller", hours=40)
    m2 = StaffMember(id="STAFF_02", identifier="SCH", name="Schmidt", hours=30, is_active=False)

    temp_repo.save_staff(m1)
    temp_repo.save_staff(m2)

    assert temp_repo.get_staff("STAFF_01") is not None
    assert temp_repo.get_staff("NON_EXISTENT") is None

    # Check active filter
    active_staff = temp_repo.list_staff(active_only=True)
    assert len(active_staff) == 1
    assert active_staff[0].identifier == "MUE"

    all_staff = temp_repo.list_staff(active_only=False)
    assert len(all_staff) == 2

    temp_repo.delete_staff("STAFF_02")
    assert temp_repo.get_staff("STAFF_02") is None

    with pytest.raises(EntityNotFoundError):
        temp_repo.delete_staff("STAFF_02")


def test_absence_repository_filtering(temp_repo: FileJsonRepository) -> None:
    """Test date range and staff filtering on AbsenceRepository."""
    a1 = AbsenceRecord(
        id="A1",
        staff_id="MUE",
        absence_type=AbsenceType.VACATION,
        start_date=date(2026, 4, 10),
        end_date=date(2026, 4, 15),
    )
    a2 = AbsenceRecord(
        id="A2",
        staff_id="SCH",
        absence_type=AbsenceType.SICK_LEAVE,
        start_date=date(2026, 4, 20),
        end_date=date(2026, 4, 25),
    )
    temp_repo.save_absence(a1)
    temp_repo.save_absence(a2)

    # Filter by staff
    mue_absences = temp_repo.list_absences_by_staff("MUE")
    assert len(mue_absences) == 1
    assert mue_absences[0].id == "A1"

    # Filter overlapping window: 2026-04-14 to 2026-04-21 includes both A1 and A2
    overlap = temp_repo.list_absences_for_range(date(2026, 4, 14), date(2026, 4, 21))
    assert len(overlap) == 2

    # Window before A1
    early = temp_repo.list_absences_for_range(date(2026, 4, 1), date(2026, 4, 5))
    assert len(early) == 0


def test_schedule_repository_lifecycle(temp_repo: FileJsonRepository) -> None:
    """Test persisting and updating a quarter schedule document."""
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
    temp_repo.save_schedule(doc)

    loaded = temp_repo.get_schedule("2026-Q2")
    assert loaded is not None
    assert loaded.quarter_key == "2026-Q2"
    assert loaded.state == ScheduleState.DRAFT
    assert len(loaded.assignments) == 1
    assert loaded.assignments[0].planned_staff_id == "MUE"

    # Update state
    loaded.state = ScheduleState.PUBLISHED
    temp_repo.save_schedule(loaded)

    reloaded = temp_repo.get_schedule("2026-Q2")
    assert reloaded is not None
    assert reloaded.state == ScheduleState.PUBLISHED


def test_solver_job_repository_lifecycle(temp_repo: FileJsonRepository) -> None:
    """Test saving, retrieving, updating, and deleting SolverJobRecord."""
    assert temp_repo.get_solver_job("2026-Q2") is None

    job = SolverJobRecord(
        job_id="job_2026_q2_test",
        quarter_key="2026-Q2",
        status=SolverJobStatus.RUNNING,
        max_solve_time_seconds=60,
    )
    temp_repo.save_solver_job(job)

    loaded = temp_repo.get_solver_job("2026-Q2")
    assert loaded is not None
    assert loaded.job_id == "job_2026_q2_test"
    assert loaded.status == SolverJobStatus.RUNNING
    assert loaded.max_solve_time_seconds == 60

    # Update progress
    loaded.status = SolverJobStatus.COMPLETED
    loaded.solutions_found = 5
    loaded.best_objective = 420.0
    temp_repo.save_solver_job(loaded)

    reloaded = temp_repo.get_solver_job("2026-Q2")
    assert reloaded is not None
    assert reloaded.status == SolverJobStatus.COMPLETED
    assert reloaded.solutions_found == 5
    assert reloaded.best_objective == 420.0

    # Delete
    temp_repo.delete_solver_job("2026-Q2")
    assert temp_repo.get_solver_job("2026-Q2") is None

