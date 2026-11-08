"""Integration tests for FastAPI v1 REST endpoints."""

from datetime import date
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.scheduler.models import Assignment, Schedule, Shift, ShiftType
from app.scheduler.solver_cpsat import SolverResult


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

    # Update absence
    updated_payload = {
        "id": "ABS_01",
        "staff_id": "STAFF_01",
        "absence_type": "Vacation",
        "start_date": "2026-05-02",
        "end_date": "2026-05-12",
        "note": "Updated holiday",
    }
    update_resp = client.put("/api/v1/absences/ABS_01", json=updated_payload)
    assert update_resp.status_code == 200
    assert update_resp.json()["start_date"] == "2026-05-02"
    assert update_resp.json()["note"] == "Updated holiday"

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

    # 3. Synchronous Generate via ?sync=true
    gen_resp = client.post("/api/v1/quarters/2026-Q2/generate?sync=true")
    assert gen_resp.status_code == 200
    job_data = gen_resp.json()
    assert job_data["status"] == "COMPLETED"
    assert job_data["quarter_key"] == "2026-Q2"

    # Verify schedule doc was created and populated
    sched_resp = client.get("/api/v1/quarters/2026-Q2")
    assert sched_resp.status_code == 200
    doc_data = sched_resp.json()
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


def test_quarters_async_solver_and_cancellation(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test 202 Accepted async solve, status polling, and cancellation flow."""
    import time
    from threading import Event

    # 1. Onboard staff member
    client.post(
        "/api/v1/staff",
        json={"id": "STAFF_01", "identifier": "MUE", "name": "Müller", "hours": 40},
    )

    # 2. Status initially IDLE
    idle_resp = client.get("/api/v1/quarters/2026-Q3/solver-status")
    assert idle_resp.status_code == 200
    assert idle_resp.json()["status"] == "IDLE"

    started_solve = Event()

    def slow_solve(**kwargs: Any) -> SolverResult:
        started_solve.set()
        cancellation: Event | None = kwargs.get("cancellation_event")
        # Wait until cancelled or 2 seconds
        for _ in range(20):
            if cancellation and cancellation.is_set():
                break
            time.sleep(0.05)
        return SolverResult(
            success=False,
            schedules=[],
            penalties=[],
            unsatisfiable_constraints=["Abgebrochen"],
        )

    monkeypatch.setattr("app.api.v1.quarters.generate_schedule", slow_solve)

    # 3. Launch async generate -> 202 Accepted
    gen_resp = client.post("/api/v1/quarters/2026-Q3/generate")
    assert gen_resp.status_code == 202
    job_data = gen_resp.json()
    assert job_data["status"] == "RUNNING"
    assert job_data["quarter_key"] == "2026-Q3"

    started_solve.wait(timeout=1.0)

    # 4. Status is RUNNING
    run_resp = client.get("/api/v1/quarters/2026-Q3/solver-status")
    assert run_resp.status_code == 200
    assert run_resp.json()["status"] == "RUNNING"

    # 5. Concurrent solve triggers 409 Conflict
    dup_resp = client.post("/api/v1/quarters/2026-Q3/generate")
    assert dup_resp.status_code == 409

    # 6. Request cancellation
    cancel_resp = client.post("/api/v1/quarters/2026-Q3/cancel")
    assert cancel_resp.status_code == 200

    # 7. Polling verifies cancellation
    time.sleep(0.15)
    final_status = client.get("/api/v1/quarters/2026-Q3/solver-status")
    assert final_status.status_code == 200
    assert final_status.json()["status"] in ("CANCELLED", "FAILED")


def test_preassigned_api_crud_lifecycle(client: TestClient) -> None:
    """Ensure full CRUD operations for pre-assigned shifts through REST API."""
    # 0. Create prerequisite staff member
    client.post(
        "/api/v1/staff",
        json={
            "id": "ks",
            "identifier": "KS",
            "name": "Dr. Katharina Schmidt",
            "beruf": "TFA",
            "hours": 40,
            "nd_possible": True,
        },
    )

    payload = {
        "id": "pa-test-1",
        "staff_id": "ks",
        "staff_identifier": "KS",
        "shift_date": "2027-03-25",
        "shift_type": "N_Do-Fr",
        "is_holiday": True,
        "note": "Gründonnerstag Vorgabe",
    }

    # 1. Create preassigned shift
    create_resp = client.post("/api/v1/preassigned", json=payload)
    assert create_resp.status_code == 201
    assert create_resp.json()["id"] == "pa-test-1"

    # 2. List preassigned shifts
    list_resp = client.get("/api/v1/preassigned")
    assert list_resp.status_code == 200
    items = list_resp.json()
    assert len(items) == 1
    assert items[0]["id"] == "pa-test-1"

    # 3. Update preassigned shift
    update_payload = dict(payload)
    update_payload["note"] = "Aktualisierte Vorgabe"
    put_resp = client.put("/api/v1/preassigned/pa-test-1", json=update_payload)
    assert put_resp.status_code == 200
    assert put_resp.json()["note"] == "Aktualisierte Vorgabe"

    # 4. Delete preassigned shift
    del_resp = client.delete("/api/v1/preassigned/pa-test-1")
    assert del_resp.status_code == 204

    # 5. Verify empty list
    empty_resp = client.get("/api/v1/preassigned")
    assert empty_resp.status_code == 200
    assert len(empty_resp.json()) == 0


def test_quarter_fairness_overview_endpoint(client: TestClient) -> None:
    """Ensure /api/v1/quarters/{quarter_key}/fairness returns structured role metrics."""
    # 1. Onboard a staff member
    staff_payload = {
        "id": "STAFF_TFA1",
        "identifier": "T1",
        "name": "TFA One",
        "beruf": "TFA",
        "abteilung": "station",
        "hours": 40,
        "adult": True,
        "reception": False,
        "nd_possible": True,
        "nd_alone": True,
        "nd_min_consecutive": 2,
        "nd_max_consecutive": 4,
        "is_active": True,
    }
    client.post("/api/v1/staff", json=staff_payload)

    # 2. Fetch fairness overview
    resp = client.get("/api/v1/quarters/2026-Q4/fairness")
    assert resp.status_code == 200
    data = resp.json()
    assert data["quarter_key"] == "2026-Q4"
    assert "groups" in data
    assert "TFA" in data["groups"]
    assert "records" in data
    assert any(r["identifier"] == "T1" for r in data["records"])


def test_umlaut_entity_ids_crud(client: TestClient) -> None:
    """Ensure staff, absences, and preassigned shifts support German umlauts in IDs (B5)."""
    staff_payload = {
        "id": "mül",
        "identifier": "MÜL",
        "name": "Dr. Julia Müller",
        "beruf": "TFA",
        "hours": 40,
        "nd_possible": True,
    }
    create_resp = client.post("/api/v1/staff", json=staff_payload)
    assert create_resp.status_code == 201

    get_resp = client.get("/api/v1/staff/mül")
    assert get_resp.status_code == 200
    assert get_resp.json()["identifier"] == "MÜL"

    staff_payload["name"] = "Dr. Julia Müller-Weiß"
    put_resp = client.put("/api/v1/staff/mül", json=staff_payload)
    assert put_resp.status_code == 200
    assert put_resp.json()["name"] == "Dr. Julia Müller-Weiß"

    abs_payload = {
        "id": "abs_mül_1",
        "staff_id": "mül",
        "absence_type": "Vacation",
        "start_date": "2026-05-01",
        "end_date": "2026-05-05",
    }
    assert client.post("/api/v1/absences", json=abs_payload).status_code == 201
    assert client.put("/api/v1/absences/abs_mül_1", json=abs_payload).status_code == 200
    assert client.delete("/api/v1/absences/abs_mül_1").status_code == 204

    pa_payload = {
        "id": "pa_mül_1",
        "staff_id": "mül",
        "staff_identifier": "MÜL",
        "shift_date": "2026-05-14",
        "shift_type": "N_Do-Fr",
        "is_holiday": True,
    }
    assert client.post("/api/v1/preassigned", json=pa_payload).status_code == 201
    assert client.put("/api/v1/preassigned/pa_mül_1", json=pa_payload).status_code == 200
    assert client.delete("/api/v1/preassigned/pa_mül_1").status_code == 204

    assert client.delete("/api/v1/staff/mül").status_code == 204


def test_fairness_overview_excludes_deactivated_staff_without_shifts(
    client: TestClient,
) -> None:
    """Ensure deactivated staff without shifts do not distort role-group means (B6)."""
    client.post(
        "/api/v1/staff",
        json={
            "id": "tfa_active",
            "identifier": "T_ACT",
            "name": "Active TFA",
            "beruf": "TFA",
            "hours": 40,
            "is_active": True,
        },
    )
    client.post(
        "/api/v1/staff",
        json={
            "id": "tfa_inactive",
            "identifier": "T_INACT",
            "name": "Inactive TFA",
            "beruf": "TFA",
            "hours": 40,
            "is_active": False,
        },
    )

    resp = client.get("/api/v1/quarters/2026-Q4/fairness")
    assert resp.status_code == 200
    data = resp.json()
    identifiers = [r["identifier"] for r in data["records"]]
    assert "T_ACT" in identifiers
    assert "T_INACT" not in identifiers
    assert data["groups"]["TFA"]["total_staff"] == 1


def test_b7_generate_request_accepts_block_gap_days(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Ensure GenerateScheduleRequest accepts block_gap_days and passes it to SchedulerConfig (B7)."""
    client.post(
        "/api/v1/staff",
        json={
            "id": "tfa_01",
            "identifier": "T1",
            "name": "TFA One",
            "beruf": "TFA",
            "hours": 40,
            "nd_possible": True,
            "nd_alone": True,
        },
    )

    captured_config: dict[str, Any] = {}

    def fake_solve(**kwargs: Any) -> SolverResult:
        captured_config["config"] = kwargs.get("config")
        return SolverResult(
            success=True,
            schedules=[
                Schedule(
                    quarter_start=date(2026, 4, 1),
                    quarter_end=date(2026, 6, 30),
                    assignments=[
                        Assignment(
                            shift=Shift(
                                shift_type=ShiftType.NIGHT_WED_THU, shift_date=date(2026, 4, 1)
                            ),
                            staff_identifier="T1",
                            is_paired=False,
                        )
                    ],
                )
            ],
            penalties=[1.0],
            unsatisfiable_constraints=[],
        )

    monkeypatch.setattr("app.api.v1.quarters.generate_schedule", fake_solve)

    resp = client.post(
        "/api/v1/quarters/2026-Q2/generate?sync=true",
        json={"max_solve_time_seconds": 10, "block_gap_days": 14},
    )
    assert resp.status_code == 200
    assert captured_config["config"] is not None
    assert captured_config["config"].block_gap_days == 14


def test_b8_cross_quarter_block_gap_holiday_on_second_day_of_block() -> None:
    """Ensure cross-quarter block gap relaxation applies when a pre-assigned holiday is on day 2 of a block (B8)."""
    from app.scheduler.models import PreviousPlanContext, Staff, TrailingAssignment
    from app.scheduler.validator import find_cross_quarter_block_gap_exceptions

    staff = [
        Staff(
            name="TFA One",
            identifier="T1",
            adult=True,
            hours=40,
            reception=False,
            nd_possible=True,
            nd_alone=True,
        )
    ]
    prev_ctx = PreviousPlanContext(
        quarter_start=date(2026, 10, 1),
        quarter_end=date(2026, 12, 31),
        trailing_assignments=[
            TrailingAssignment(
                staff_identifier="T1",
                shift_date=date(2026, 12, 20),
                shift_type=ShiftType.NIGHT_SUN_MON,
            ),
            TrailingAssignment(
                staff_identifier="T1",
                shift_date=date(2026, 12, 21),
                shift_type=ShiftType.NIGHT_MON_TUE,
            ),
        ],
        carry_forward=[],
    )
    # Current block starts 2027-01-01 (non-pre-assigned) and continues 2027-01-02 (pre-assigned holiday)
    # Gap from 2026-12-20 to 2027-01-01 is 12 days (>= 7 holiday_gap_days, < 21 block_gap_days)
    sched = Schedule(
        quarter_start=date(2027, 1, 1),
        quarter_end=date(2027, 3, 31),
        assignments=[
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_FRI_SAT, shift_date=date(2027, 1, 1)),
                staff_identifier="T1",
                is_paired=False,
                is_pre_assigned=False,
            ),
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_SAT_SUN, shift_date=date(2027, 1, 2)),
                staff_identifier="T1",
                is_paired=False,
                is_pre_assigned=True,
            ),
        ],
    )
    exceptions = find_cross_quarter_block_gap_exceptions(
        schedule=sched, previous_context=prev_ctx, staff_list=staff
    )
    assert len(exceptions) == 0


def test_b4_export_excel_resolves_staff_names_when_id_differs_from_identifier(
    client: TestClient,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Ensure Excel export resolves full staff names when staff.id is lowercase and actual_staff_id is uppercase identifier (B4)."""
    import io

    import openpyxl

    client.post(
        "/api/v1/staff",
        json={
            "id": "mue",
            "identifier": "MUE",
            "name": "Dr. Müller",
            "beruf": "Vet",
            "abteilung": "station",
            "hours": 40,
            "is_active": True,
        },
    )

    def fake_solve(**kwargs: Any) -> SolverResult:
        return SolverResult(
            success=True,
            schedules=[
                Schedule(
                    quarter_start=date(2026, 4, 1),
                    quarter_end=date(2026, 6, 30),
                    assignments=[
                        Assignment(
                            shift=Shift(
                                shift_type=ShiftType.NIGHT_WED_THU, shift_date=date(2026, 4, 1)
                            ),
                            staff_identifier="MUE",
                            is_paired=False,
                        )
                    ],
                )
            ],
            penalties=[1.0],
            unsatisfiable_constraints=[],
        )

    monkeypatch.setattr("app.api.v1.quarters.generate_schedule", fake_solve)

    gen_resp = client.post(
        "/api/v1/quarters/2026-Q2/generate?sync=true",
        json={"max_solve_time_seconds": 10},
    )
    assert gen_resp.status_code == 200

    resp = client.get("/api/v1/quarters/2026-Q2/export?format=xlsx")
    assert resp.status_code == 200
    wb = openpyxl.load_workbook(io.BytesIO(resp.content))
    ws_summary = wb["Schichtverteilung"]
    found_name = False
    for row in ws_summary.iter_rows(values_only=True):
        if "Dr. Müller" in [str(c) for c in row if c is not None]:
            found_name = True
            break
    assert found_name, "Expected full staff name 'Dr. Müller' in Schichtverteilung sheet"


def test_delete_staff_cascades_absences_and_preassigned(client: TestClient) -> None:
    """Ensure hard-deleting a staff member cascades and cleans up absences and preassignments (D1)."""
    staff_payload = {
        "id": "cascade_tfa",
        "identifier": "CAS",
        "name": "Cascade Test TFA",
        "beruf": "TFA",
        "hours": 40,
        "is_active": True,
    }
    assert client.post("/api/v1/staff", json=staff_payload).status_code == 201

    absence_payload = {
        "id": "abs_cascade_1",
        "staff_id": "cascade_tfa",
        "absence_type": "Vacation",
        "start_date": "2026-05-01",
        "end_date": "2026-05-10",
        "note": "Cascade vacation",
    }
    assert client.post("/api/v1/absences", json=absence_payload).status_code == 201

    pa_payload = {
        "id": "pa_cascade_1",
        "staff_id": "cascade_tfa",
        "staff_identifier": "CAS",
        "shift_date": "2026-05-20",
        "shift_type": "N_Mi-Do",
        "is_holiday": True,
        "note": "Holiday preassignment",
    }
    assert client.post("/api/v1/preassigned", json=pa_payload).status_code == 201

    assert len(client.get("/api/v1/absences?staff_id=cascade_tfa").json()) == 1
    pa_list = client.get("/api/v1/preassigned").json()
    assert any(p["id"] == "pa_cascade_1" for p in pa_list)

    assert client.delete("/api/v1/staff/cascade_tfa?hard_delete=true").status_code == 204

    assert client.get("/api/v1/staff/cascade_tfa").status_code == 404
    assert len(client.get("/api/v1/absences?staff_id=cascade_tfa").json()) == 0
    pa_list_after = client.get("/api/v1/preassigned").json()
    assert not any(p["id"] == "pa_cascade_1" for p in pa_list_after)
