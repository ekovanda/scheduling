"""Regression tests for review findings C1, C2, and C3.

Findings covered:
- C1: Single-instance Cloud Run deployment configuration.
- C2: Global solve concurrency limiter (HTTP 429), num_workers clamp, sync solve timeout guard, year range validation.
- C3: Solve status, optimality gap, best bound, and stagnation metrics recorded in SolverResult, SolverJobRecord, and schedule documents.
"""

from datetime import date
from pathlib import Path

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient

from app.api.v1.quarters import _active_jobs, _jobs_lock, _parse_quarter_key
from app.persistence.models import (
    Beruf,
)
from app.scheduler.models import Assignment, Schedule, Shift, ShiftType, Staff
from app.scheduler.solver_cpsat import SolverResult, generate_schedule_cpsat

# ---------------------------------------------------------------------------
# C1 Tests: Cloud Run deployment script hygiene
# ---------------------------------------------------------------------------


def test_c1_deploy_scripts_enforce_single_instance() -> None:
    """Ensure deploy scripts specify --min-instances=1 and --max-instances=1 (C1)."""
    root_dir = Path(__file__).parents[1]
    sh_script = (root_dir / "scripts" / "deploy_cloud_run.sh").read_text(encoding="utf-8")
    ps_script = (root_dir / "scripts" / "deploy_cloud_run.ps1").read_text(encoding="utf-8")

    assert "--min-instances=1" in sh_script
    assert "--max-instances=1" in sh_script
    assert '"--min-instances", "1"' in ps_script
    assert '"--max-instances", "1"' in ps_script


# ---------------------------------------------------------------------------
# C2 Tests: Concurrency, Workers, Sync Timeout, and Year Range
# ---------------------------------------------------------------------------


def test_c2_parse_quarter_key_year_bounds() -> None:
    """_parse_quarter_key validates year range 2020-2100 (C2)."""
    assert _parse_quarter_key("2020-Q1") == (2020, 1)
    assert _parse_quarter_key("2026-Q3") == (2026, 3)
    assert _parse_quarter_key("2100-Q4") == (2100, 4)

    # Years out of range
    with pytest.raises(HTTPException) as exc_info_low:
        _parse_quarter_key("2019-Q4")
    assert exc_info_low.value.status_code == 400
    assert "between 2020 and 2100" in exc_info_low.value.detail

    with pytest.raises(HTTPException) as exc_info_high:
        _parse_quarter_key("2101-Q1")
    assert exc_info_high.value.status_code == 400
    assert "between 2020 and 2100" in exc_info_high.value.detail

    with pytest.raises(HTTPException):
        _parse_quarter_key("0000-Q1")

    with pytest.raises(HTTPException):
        _parse_quarter_key("9999-Q4")


def test_c2_sync_solve_timeout_validation(client: TestClient) -> None:
    """Synchronous solve request rejects max_solve_time_seconds > 850s to avoid 900s timeout (C2)."""
    # 900s exceeds Cloud Run 900s request timeout threshold
    resp = client.post(
        "/api/v1/quarters/2026-Q2/generate?sync=true",
        json={"max_solve_time_seconds": 900},
    )
    assert resp.status_code == 400
    assert "exceeds maximum allowable limit of 850s" in resp.json()["detail"]


def test_c2_global_concurrency_limit_429(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Only 1 concurrent solve allowed per instance; second returns HTTP 429 (C2)."""
    import threading
    import time

    # Onboard staff member
    client.post(
        "/api/v1/staff",
        json={
            "id": "tfa1",
            "identifier": "TFA1",
            "name": "TFA One",
            "beruf": "TFA",
            "hours": 40,
            "adult": True,
            "reception": False,
            "nd_possible": True,
            "nd_alone": True,
        },
    )

    solve_started = threading.Event()
    release_solve = threading.Event()

    def slow_solve(**kwargs):
        solve_started.set()
        release_solve.wait(timeout=5)
        # Return dummy result
        sched = Schedule(
            quarter_start=date(2026, 4, 1),
            quarter_end=date(2026, 6, 30),
            assignments=[
                Assignment(
                    shift=Shift(shift_type=ShiftType.NIGHT_WED_THU, shift_date=date(2026, 4, 1)),
                    staff_identifier="TFA1",
                )
            ],
        )
        return SolverResult(
            success=True,
            schedules=[sched],
            penalties=[10.0],
            unsatisfiable_constraints=[],
            status_name="FEASIBLE",
            objective_value=10.0,
            best_objective_bound=5.0,
            num_workers=2,
        )

    monkeypatch.setattr("app.api.v1.quarters.generate_schedule", slow_solve)

    # Clean active jobs before starting
    with _jobs_lock:
        _active_jobs.clear()

    try:
        # Start first solve for Q2
        res1 = client.post("/api/v1/quarters/2026-Q2/generate")
        assert res1.status_code == 202

        # Wait until worker has started
        assert solve_started.wait(timeout=2.0)

        # Attempt to start concurrent solve for Q3 -> must return 429
        res2 = client.post("/api/v1/quarters/2026-Q3/generate")
        assert res2.status_code == 429
        assert "Only 1 concurrent solve is permitted per instance" in res2.json()["detail"]
        assert "2026-Q2" in res2.json()["detail"]

    finally:
        release_solve.set()
        # Wait briefly for thread to join
        time.sleep(0.3)
        with _jobs_lock:
            _active_jobs.clear()


def test_c2_solver_num_workers_parameter() -> None:
    """generate_schedule_cpsat sets solver num_workers parameter (C2)."""
    captured_solver = []

    def capture_solver(s):
        captured_solver.append(s)

    staff = [
        Staff(
            identifier="TFA1",
            name="TFA One",
            beruf=Beruf.TFA,
            hours=40,
            adult=True,
            reception=False,
            nd_possible=True,
            nd_alone=True,
            nd_min_consecutive=1,
        )
    ]

    res = generate_schedule_cpsat(
        staff_list=staff,
        quarter_start=date(2026, 4, 1),
        max_solve_time_seconds=1,
        on_solver_created=capture_solver,
        num_workers=2,
    )

    assert len(captured_solver) == 1
    # num_workers parameter in CpSolver
    assert captured_solver[0].parameters.num_workers == 2
    assert res.num_workers == 2


# ---------------------------------------------------------------------------
# C3 Tests: Optimality Metrics, Best Bound, Gap & Stagnation
# ---------------------------------------------------------------------------


def test_c3_solver_result_records_optimality_fields() -> None:
    """SolverResult records status_name, objective_value, best_objective_bound, and num_workers (C3)."""
    result = SolverResult(
        success=True,
        schedules=[],
        penalties=[42.0],
        unsatisfiable_constraints=[],
        status_name="OPTIMAL",
        objective_value=42.0,
        best_objective_bound=42.0,
        stopped_due_to_stagnation=False,
        num_workers=2,
    )

    assert result.status_name == "OPTIMAL"
    assert result.objective_value == 42.0
    assert result.best_objective_bound == 42.0
    assert not result.stopped_due_to_stagnation
    assert result.num_workers == 2


def test_c3_execute_solver_worker_stores_optimality_metrics(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """_execute_solver_worker records optimality metrics in schedule document and job record (C3)."""
    # 1. Onboard staff
    client.post(
        "/api/v1/staff",
        json={
            "id": "tfa1",
            "identifier": "TFA1",
            "name": "TFA One",
            "beruf": "TFA",
            "hours": 40,
            "adult": True,
            "reception": False,
            "nd_possible": True,
            "nd_alone": True,
        },
    )

    fake_schedule = Schedule(
        quarter_start=date(2026, 4, 1),
        quarter_end=date(2026, 6, 30),
        assignments=[
            Assignment(
                shift=Shift(shift_type=ShiftType.NIGHT_WED_THU, shift_date=date(2026, 4, 1)),
                staff_identifier="TFA1",
            )
        ],
    )

    fake_result = SolverResult(
        success=True,
        schedules=[fake_schedule],
        penalties=[15.0],
        unsatisfiable_constraints=[],
        status_name="FEASIBLE",
        objective_value=15.0,
        best_objective_bound=10.0,
        stopped_due_to_stagnation=True,
        num_workers=2,
    )

    monkeypatch.setattr("app.api.v1.quarters.generate_schedule", lambda **kwargs: fake_result)

    # Run synchronous solve
    resp = client.post("/api/v1/quarters/2026-Q2/generate?sync=true")
    assert resp.status_code == 200

    job_data = resp.json()
    assert job_data["status"] == "COMPLETED"
    assert job_data["status_name"] == "FEASIBLE"
    assert job_data["best_objective_bound"] == 10.0
    assert job_data["stopped_due_to_stagnation"] is True
    assert job_data["num_workers"] == 2

    # Verify QuarterScheduleDocument solver_metrics via GET endpoint
    sched_resp = client.get("/api/v1/quarters/2026-Q2")
    assert sched_resp.status_code == 200
    metrics = sched_resp.json()["solver_metrics"]
    assert metrics["status_name"] == "FEASIBLE"
    assert metrics["is_optimal"] is False
    assert metrics["best_objective_bound"] == 10.0
    assert metrics["objective_value"] == 15.0
    assert metrics["optimality_gap"] == 5.0
    assert metrics["stopped_due_to_stagnation"] is True
    assert metrics["num_workers"] == 2
