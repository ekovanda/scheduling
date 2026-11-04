"""Integration tests for FastAPI v1 REST endpoints."""

from collections.abc import Generator
from datetime import date
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api.dependencies import get_repository
from app.api.main import app
from app.persistence.repository import FileJsonRepository
from app.scheduler.models import Assignment, Schedule, Shift, ShiftType
from app.scheduler.solver_cpsat import SolverResult


@pytest.fixture
def client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """Fixture providing a test client with an isolated temporary repository."""
    test_repo = FileJsonRepository(base_dir=tmp_path / "api_test_db")
    app.dependency_overrides[get_repository] = lambda: test_repo
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_api_health(client: TestClient) -> None:
    """Ensure /api/v1/health returns 200 with service metadata."""
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert data["service"] == "dienstplan-api"
    assert "version" in data
    assert "timestamp" in data


def test_staff_api_crud_lifecycle(client: TestClient) -> None:
    """Ensure full staff member CRUD operations through REST API."""
    staff_payload = {
        "id": "STAFF_01",
        "identifier": "MUE",
        "name": "Dr. Anna Müller",
        "beruf": "Vet",
        "abteilung": "station",
        "hours": 40,
        "adult": True,
        "reception": False,
        "nd_possible": True,
        "nd_alone": True,
        "nd_min_consecutive": 2,
        "nd_max_consecutive": 3,
        "nd_exceptions": [1],
        "is_active": True,
    }

    # 1. Create staff
    create_resp = client.post("/api/v1/staff", json=staff_payload)
    assert create_resp.status_code == 201
    assert create_resp.json()["identifier"] == "MUE"

    # 2. Prevent duplicate ID
    dup_resp = client.post("/api/v1/staff", json=staff_payload)
    assert dup_resp.status_code == 409

    # 3. Get staff
    get_resp = client.get("/api/v1/staff/STAFF_01")
    assert get_resp.status_code == 200
    assert get_resp.json()["name"] == "Dr. Anna Müller"

    # 4. Update staff
    staff_payload["name"] = "Dr. Anna Müller-Weber"
    put_resp = client.put("/api/v1/staff/STAFF_01", json=staff_payload)
    assert put_resp.status_code == 200
    assert put_resp.json()["name"] == "Dr. Anna Müller-Weber"

    # 5. Soft delete (deactivate)
    del_resp = client.delete("/api/v1/staff/STAFF_01")
    assert del_resp.status_code == 204

    # Verify deactivated
    list_active = client.get("/api/v1/staff?active_only=true")
    assert len(list_active.json()) == 0
    list_all = client.get("/api/v1/staff?active_only=false")
    assert len(list_all.json()) == 1
    assert list_all.json()[0]["is_active"] is False


def test_absences_api(client: TestClient) -> None:
    """Test creating and querying absences via REST API."""
    # Create staff member first
    client.post(
        "/api/v1/staff",
        json={
            "id": "STAFF_01",
            "identifier": "MUE",
            "name": "Müller",
            "hours": 40,
        },
    )

    absence_payload = {
        "id": "ABS_01",
        "staff_id": "STAFF_01",
        "absence_type": "Vacation",
        "start_date": "2026-05-01",
        "end_date": "2026-05-10",
        "note": "Spring holiday",
    }
    create_resp = client.post("/api/v1/absences", json=absence_payload)
    assert create_resp.status_code == 201

    # Query matching range
    query_resp = client.get("/api/v1/absences?start_date=2026-05-05&end_date=2026-05-15")
    assert query_resp.status_code == 200
    assert len(query_resp.json()) == 1

    # Query outside range
    query_empty = client.get("/api/v1/absences?start_date=2026-06-01&end_date=2026-06-10")
    assert query_empty.status_code == 200
    assert len(query_empty.json()) == 0


def test_quarters_api_lifecycle(client: TestClient) -> None:
    """Test quarter planning lifecycle: init -> publish -> lock."""
    # 1. Invalid key format
    bad_init = client.post("/api/v1/quarters/invalid-key/init")
    assert bad_init.status_code == 400

    # 2. Init quarter
    init_resp = client.post("/api/v1/quarters/2026-Q2/init")
    assert init_resp.status_code == 201
    assert init_resp.json()["state"] == "DRAFT"

    # 3. Prevent duplicate init
    dup_init = client.post("/api/v1/quarters/2026-Q2/init")
    assert dup_init.status_code == 409

    # 4. Publish quarter
    pub_resp = client.post("/api/v1/quarters/2026-Q2/publish")
    assert pub_resp.status_code == 200
    assert pub_resp.json()["state"] == "PUBLISHED"

    # 5. Lock quarter
    lock_resp = client.post("/api/v1/quarters/2026-Q2/lock")
    assert lock_resp.status_code == 200
    assert lock_resp.json()["state"] == "CLOSED"

    # 6. Attempting to delete locked schedule fails
    del_resp = client.delete("/api/v1/quarters/2026-Q2")
    assert del_resp.status_code == 400


def test_quarters_generate_and_swap_api(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test solver generation and shift swapping endpoints."""
    # 1. Generate with no staff -> 400
    err_gen = client.post("/api/v1/quarters/2026-Q2/generate")
    assert err_gen.status_code == 400

    # 2. Onboard 2 staff members
    client.post(
        "/api/v1/staff",
        json={
            "id": "STAFF_01",
            "identifier": "MUE",
            "name": "Müller",
            "beruf": "TFA",
            "hours": 40,
            "nd_possible": True,
            "nd_alone": True,
        },
    )
    client.post(
        "/api/v1/staff",
        json={
            "id": "STAFF_02",
            "identifier": "SCH",
            "name": "Schmidt",
            "beruf": "TFA",
            "hours": 40,
            "nd_possible": True,
            "nd_alone": True,
        },
    )

    # Mock generate_schedule for fast unit test execution
    fake_schedule = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 6, 30),
        assignments=[
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_WED_THU, shift_date=date(2026, 4, 1)),
                staff_identifier="MUE",
                is_paired=False,
            )
        ],
    )
    fake_result = SolverResult(
        success=True,
        schedules=[fake_schedule],
        penalties=[5.0],
        unsatisfiable_constraints=[],
    )
    monkeypatch.setattr("app.api.v1.quarters.generate_schedule", lambda **kwargs: fake_result)

    # 3. Synchronous Generate
    gen_resp = client.post("/api/v1/quarters/2026-Q2/generate")
    assert gen_resp.status_code == 200
    doc_data = gen_resp.json()
    assert len(doc_data["assignments"]) == 1
    assert doc_data["assignments"][0]["planned_staff_id"] == "MUE"
    assert doc_data["assignments"][0]["actual_staff_id"] == "MUE"

    # 4. Validate quarter plan
    val_resp = client.post("/api/v1/quarters/2026-Q2/validate")
    assert val_resp.status_code == 200
    assert "is_valid" in val_resp.json()

    # 5. Swap shift to SCH (force=True to bypass full quarter min consecutive checks)
    swap_payload = {
        "shift_date": "2026-04-01",
        "shift_type": "N_Mi-Do",
        "old_staff_id": "MUE",
        "new_staff_id": "STAFF_02",
        "reason": "Diensttausch",
        "force": True,
    }
    swap_resp = client.post("/api/v1/quarters/2026-Q2/shifts/swap", json=swap_payload)
    assert swap_resp.status_code == 200
    swapped_doc = swap_resp.json()
    swapped_assign = swapped_doc["assignments"][0]
    assert swapped_assign["planned_staff_id"] == "MUE"
    assert swapped_assign["actual_staff_id"] == "STAFF_02"
    assert swapped_assign["is_override"] is True
    assert swapped_assign["override_reason"] == "Diensttausch"

    # 6. Swap with non-existent staff member -> 404
    swap_payload["new_staff_id"] = "UNKNOWN_STAFF"
    err_swap = client.post("/api/v1/quarters/2026-Q2/shifts/swap", json=swap_payload)
    assert err_swap.status_code == 404

    # 7. Export schedule as Excel (.xlsx)
    export_xlsx = client.get("/api/v1/quarters/2026-Q2/export?format=xlsx")
    assert export_xlsx.status_code == 200
    assert "application/vnd.openxmlformats" in export_xlsx.headers["content-type"]
    assert len(export_xlsx.content) > 0

    # 8. Export schedule as CSV
    export_csv = client.get("/api/v1/quarters/2026-Q2/export?format=csv")
    assert export_csv.status_code == 200
    assert "text/csv" in export_csv.headers["content-type"]
    assert "N_Mi-Do" in export_csv.text
