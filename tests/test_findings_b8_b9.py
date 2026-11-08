"""Regression tests for findings B8 and B9.

Finding B8: Staff API accepts invalid data that crashes solver thread later.
Finding B9: Abteilung (H17/H18) not enforced across quarter boundary.
"""

from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.api.dependencies import get_repository
from app.api.main import app
from app.persistence.models import StaffMember
from app.persistence.repository import FileJsonRepository
from app.scheduler.exceptions import StaffValidationError
from app.scheduler.models import (
    Abteilung,
    Assignment,
    Beruf,
    PreviousPlanContext,
    Schedule,
    Shift,
    ShiftType,
    Staff,
    TrailingAssignment,
)
from app.scheduler.solver_cpsat import generate_schedule_cpsat
from app.scheduler.validator import validate_schedule

# =============================================================================
# Finding B8 Tests
# =============================================================================


def test_b8_staff_member_rejects_zero_or_negative_hours_for_non_vet() -> None:
    """Non-vet staff must have weekly hours > 0."""
    with pytest.raises(ValidationError, match="must have contracted weekly hours > 0"):
        StaffMember(
            id="tfa_1",
            identifier="TFA1",
            name="TFA One",
            beruf=Beruf.TFA,
            hours=0,
        )

    with pytest.raises(ValidationError):
        StaffMember(
            id="tfa_2",
            identifier="TFA2",
            name="TFA Two",
            beruf=Beruf.TFA,
            hours=-10,
        )


def test_b8_staff_member_accepts_zero_hours_for_vet() -> None:
    """Veterinarians legitimately have 0 contracted weekly clinic hours."""
    vet = StaffMember(
        id="vet_1",
        identifier="VET1",
        name="Dr. Vet",
        beruf=Beruf.VET,
        hours=0,
    )
    assert vet.hours == 0
    assert vet.beruf == Beruf.VET


def test_b8_staff_member_rejects_min_greater_than_max_consecutive() -> None:
    """nd_min_consecutive cannot exceed nd_max_consecutive."""
    with pytest.raises(ValidationError, match="cannot exceed nd_max_consecutive"):
        StaffMember(
            id="tfa_1",
            identifier="TFA1",
            name="TFA One",
            nd_min_consecutive=3,
            nd_max_consecutive=2,
        )


def test_b8_staff_member_rejects_invalid_nd_exceptions() -> None:
    """nd_exceptions must be valid weekdays (1-7)."""
    with pytest.raises(ValidationError, match="weekdays 1-7"):
        StaffMember(
            id="tfa_1",
            identifier="TFA1",
            name="TFA One",
            nd_exceptions=[0, 3],
        )

    with pytest.raises(ValidationError, match="weekdays 1-7"):
        StaffMember(
            id="tfa_2",
            identifier="TFA2",
            name="TFA Two",
            nd_exceptions=[3, 8],
        )


def test_b8_staff_member_validates_birthday_format() -> None:
    """birthday must be in MM-DD format, or None/empty string."""
    valid = StaffMember(
        id="tfa_1",
        identifier="TFA1",
        name="TFA One",
        birthday="04-15",
    )
    assert valid.birthday == "04-15"

    empty = StaffMember(
        id="tfa_2",
        identifier="TFA2",
        name="TFA Two",
        birthday="",
    )
    assert empty.birthday is None

    with pytest.raises(ValidationError):
        StaffMember(
            id="tfa_3",
            identifier="TFA3",
            name="TFA Three",
            birthday="1990-04-15",
        )

    with pytest.raises(ValidationError):
        StaffMember(
            id="tfa_4",
            identifier="TFA4",
            name="TFA Four",
            birthday="13-45",
        )


def test_b8_staff_domain_invariants_rejects_invalid_data() -> None:
    """Core domain Staff model also validates min <= max and exceptions."""
    with pytest.raises(StaffValidationError, match="cannot exceed nd_max_consecutive"):
        Staff(
            name="Test",
            identifier="T1",
            adult=True,
            hours=40,
            beruf=Beruf.TFA,
            reception=True,
            nd_possible=True,
            nd_alone=True,
            nd_min_consecutive=4,
            nd_max_consecutive=2,
        )

    with pytest.raises(StaffValidationError, match="weekdays 1-7"):
        Staff(
            name="Test",
            identifier="T2",
            adult=True,
            hours=40,
            beruf=Beruf.TFA,
            reception=True,
            nd_possible=True,
            nd_alone=True,
            nd_exceptions=[9],
        )


@pytest.fixture
def clean_client(tmp_path: Path) -> TestClient:
    """Fixture providing isolated FileJsonRepository and TestClient."""
    repo = FileJsonRepository(tmp_path)
    app.dependency_overrides[get_repository] = lambda: repo
    client = TestClient(app)
    return client


def test_b8_api_create_and_update_enforces_identifier_uniqueness(clean_client: TestClient) -> None:
    """POST /staff and PUT /staff/{id} reject duplicate identifiers with HTTP 409."""
    # 1. Create first member
    resp1 = clean_client.post(
        "/api/v1/staff",
        json={
            "id": "staff_01",
            "identifier": "AN",
            "name": "Anna",
            "hours": 40,
        },
    )
    assert resp1.status_code == 201

    # 2. Try creating second member with duplicate identifier (case-insensitive) -> 409
    resp2 = clean_client.post(
        "/api/v1/staff",
        json={
            "id": "staff_02",
            "identifier": "an",
            "name": "Another Anna",
            "hours": 40,
        },
    )
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"]

    # 3. Create second member with different identifier -> 201
    resp3 = clean_client.post(
        "/api/v1/staff",
        json={
            "id": "staff_02",
            "identifier": "BO",
            "name": "Bob",
            "hours": 40,
        },
    )
    assert resp3.status_code == 201

    # 4. Try updating staff_02 identifier to collide with staff_01 -> 409
    resp4 = clean_client.put(
        "/api/v1/staff/staff_02",
        json={
            "id": "staff_02",
            "identifier": "AN",
            "name": "Bob Renamed",
            "hours": 40,
        },
    )
    assert resp4.status_code == 409
    assert "already exists" in resp4.json()["detail"]

    # 5. Updating staff_02 keeping same identifier -> 200
    resp5 = clean_client.put(
        "/api/v1/staff/staff_02",
        json={
            "id": "staff_02",
            "identifier": "BO",
            "name": "Bob Updated",
            "hours": 35,
        },
    )
    assert resp5.status_code == 200
    assert resp5.json()["name"] == "Bob Updated"


def test_b8_api_bulk_import_validates_batch_and_repo_uniqueness(clean_client: TestClient) -> None:
    """POST /staff/bulk-import checks batch internal uniqueness and repo collisions."""
    # 1. Collision inside batch -> 409
    batch_dup = [
        {"id": "s1", "identifier": "ID1", "name": "Name 1", "hours": 40},
        {"id": "s2", "identifier": "id1", "name": "Name 2", "hours": 40},
    ]
    resp1 = clean_client.post("/api/v1/staff/bulk-import", json=batch_dup)
    assert resp1.status_code == 409
    assert "Duplicate identifier" in resp1.json()["detail"]

    # 2. Existing member in repo
    clean_client.post(
        "/api/v1/staff",
        json={"id": "existing", "identifier": "EXT", "name": "Existing", "hours": 40},
    )

    # 3. Batch collides with existing repo member under different ID -> 409
    batch_collide = [
        {"id": "new_guy", "identifier": "EXT", "name": "Imposter", "hours": 40},
    ]
    resp2 = clean_client.post("/api/v1/staff/bulk-import", json=batch_collide)
    assert resp2.status_code == 409
    assert "already exists" in resp2.json()["detail"]

    # 4. Upserting existing member under same ID -> 200
    batch_upsert = [
        {"id": "existing", "identifier": "EXT", "name": "Existing Updated", "hours": 38},
        {"id": "brand_new", "identifier": "BN", "name": "Brand New", "hours": 40},
    ]
    resp3 = clean_client.post("/api/v1/staff/bulk-import", json=batch_upsert)
    assert resp3.status_code == 200
    assert resp3.json()["imported"] == 2


# =============================================================================
# Finding B9 Tests
# =============================================================================


def _make_staff_member(
    identifier: str,
    abteilung: Abteilung = Abteilung.OTHER,
    nd_possible: bool = True,
    nd_alone: bool = True,
) -> Staff:
    return Staff(
        name=f"Staff {identifier}",
        identifier=identifier,
        adult=True,
        hours=40,
        beruf=Beruf.TFA,
        abteilung=abteilung,
        reception=True,
        nd_possible=nd_possible,
        nd_alone=nd_alone,
        nd_min_consecutive=2,
        nd_max_consecutive=3,
    )


def test_b9_validator_detects_abteilung_consecutive_nights_across_boundary() -> None:
    """OP staff on prev quarter last night forbids different OP staff on night 1 in validator."""
    op1 = _make_staff_member("OP1", abteilung=Abteilung.OP)
    op2 = _make_staff_member("OP2", abteilung=Abteilung.OP)
    tfa3 = _make_staff_member("T3", abteilung=Abteilung.OTHER)
    staff_list = [op1, op2, tfa3]

    q_start = date(2026, 4, 1)
    prev_last_night = date(2026, 3, 31)

    # Previous context: OP1 worked night shift on March 31
    context = PreviousPlanContext(
        quarter_start=date(2026, 1, 1),
        quarter_end=prev_last_night,
        carry_forward=[],
        trailing_assignments=[
            TrailingAssignment(
                shift_date=prev_last_night,
                shift_type=ShiftType.NIGHT_TUE_WED,
                staff_identifier="OP1",
            )
        ],
    )

    # Scenario A: OP2 (different OP person) assigned on April 1 -> VIOLATION
    bad_schedule = Schedule(
        quarter_start=q_start,
        quarter_end=date(2026, 6, 30),
        assignments=[
            Assignment(
                shift=Shift(shift_date=q_start, shift_type=ShiftType.NIGHT_WED_THU),
                staff_identifier="OP2",
            )
        ],
    )

    val_res = validate_schedule(bad_schedule, staff_list, previous_context=context)
    abteilung_violations = [
        v for v in val_res.hard_violations if v.constraint_name == "Abteilung Consecutive Days"
    ]
    assert len(abteilung_violations) == 1
    assert "across quarter boundary" in abteilung_violations[0].description
    assert "Staff OP1" in abteilung_violations[0].description
    assert "Staff OP2" in abteilung_violations[0].description


def test_b9_validator_allows_same_person_across_boundary() -> None:
    """Same OP staff continuing block across quarter boundary is allowed."""
    op1 = _make_staff_member("OP1", abteilung=Abteilung.OP)
    op2 = _make_staff_member("OP2", abteilung=Abteilung.OP)
    staff_list = [op1, op2]

    q_start = date(2026, 4, 1)
    prev_last_night = date(2026, 3, 31)

    context = PreviousPlanContext(
        quarter_start=date(2026, 1, 1),
        quarter_end=prev_last_night,
        carry_forward=[],
        trailing_assignments=[
            TrailingAssignment(
                shift_date=prev_last_night,
                shift_type=ShiftType.NIGHT_TUE_WED,
                staff_identifier="OP1",
            )
        ],
    )

    # Same person (OP1) on both nights
    ok_schedule = Schedule(
        quarter_start=q_start,
        quarter_end=date(2026, 6, 30),
        assignments=[
            Assignment(
                shift=Shift(shift_date=q_start, shift_type=ShiftType.NIGHT_WED_THU),
                staff_identifier="OP1",
            )
        ],
    )

    val_res = validate_schedule(ok_schedule, staff_list, previous_context=context)
    abteilung_violations = [
        v for v in val_res.hard_violations if v.constraint_name == "Abteilung Consecutive Days"
    ]
    assert len(abteilung_violations) == 0


def test_b9_solver_forbids_different_abteilung_staff_on_night_1() -> None:
    """Solver respects cross-quarter abteilung boundary constraint."""
    from app.scheduler.models import load_staff_from_csv

    q_start = date(2026, 4, 1)  # Wednesday (closed night)
    prev_last_night = date(2026, 3, 31)  # Tuesday

    raw_staff = load_staff_from_csv(Path("data/staff_sample.csv"))
    staff_list = [s for s in raw_staff if s.available_from is None or s.available_from <= q_start]

    # Find OP staff in the sample
    op_staff_ids = [s.identifier for s in staff_list if s.abteilung == Abteilung.OP]
    assert len(op_staff_ids) >= 2, "Expected at least 2 OP staff in sample"
    op1_id = op_staff_ids[0]
    other_op_ids = set(op_staff_ids[1:])

    context = PreviousPlanContext(
        quarter_start=date(2026, 1, 1),
        quarter_end=prev_last_night,
        carry_forward=[],
        trailing_assignments=[
            # op1_id was on night duty on March 31
            TrailingAssignment(
                shift_date=prev_last_night,
                shift_type=ShiftType.NIGHT_TUE_WED,
                staff_identifier=op1_id,
            )
        ],
    )

    result = generate_schedule_cpsat(
        staff_list=staff_list,
        quarter_start=q_start,
        quarter_end=date(2026, 6, 30),
        previous_context=context,
        max_solve_time_seconds=15,
        random_seed=42,
    )

    assert result.success is True
    best_schedule = result.get_best_schedule()
    assert best_schedule is not None

    # Check night 1 (April 1): OTHER OP staff MUST NOT be assigned!
    first_night_assignments = [
        a
        for a in best_schedule.assignments
        if a.shift.shift_date == q_start and a.shift.is_night_shift()
    ]
    assigned_ids = {a.staff_identifier for a in first_night_assignments}
    for other_op in other_op_ids:
        assert (
            other_op not in assigned_ids
        ), f"{other_op} must not be scheduled on night 1 after {op1_id} worked on last night of previous quarter"
