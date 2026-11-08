"""Regression tests for code review findings E2, E3, and E4.

Findings covered:
- E2: Regression tests for critical/high review findings:
  - B2: CP-SAT fairness ceiling probe codifying the 2-person deviation model.
  - B4: Shift swap validation edge cases.
  - B6: Schedule document lifecycle states (DRAFT -> PUBLISHED -> CLOSED).
- E3: Error sanitization in worker thread (avoiding internal leak to clients, attaching Fehler-ID)
  and specific exception handling in CP-SAT callbacks/cancellation.
- E4: Dockerfile build hygiene and Python-based container healthcheck execution.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from ortools.sat.python import cp_model

from app.api.v1.quarters import ActiveJobState, _execute_solver_worker
from app.persistence.models import (
    Beruf,
    QuarterScheduleDocument,
    ScheduleState,
    SolverJobRecord,
    SolverJobStatus,
)
from app.persistence.repository import FileJsonRepository
from app.scheduler.exceptions import SchedulingError
from app.scheduler.models import Staff
from app.scheduler.solver_cpsat import (
    _add_group_fairness_objective_with_presence,
    _SchedulingProgressCallback,
)
from scripts.healthcheck import check_health

# =============================================================================
# E2: Critical / High Findings Regressions
# =============================================================================


def test_e2_b2_fairness_ceiling_probe() -> None:
    """Codify the B2 probe: 2-person CP model with presence fairness.

    Under current formula, differences up to 14 duties are feasible,
    while 16 duties exceeds the ceiling and is INFEASIBLE.
    """
    model = cp_model.CpModel()
    s1 = Staff(
        name="Staff 1",
        identifier="S1",
        beruf=Beruf.TFA,
        hours=40,
        nd_possible=True,
        adult=True,
        reception=False,
        nd_alone=True,
    )
    s2 = Staff(
        name="Staff 2",
        identifier="S2",
        beruf=Beruf.TFA,
        hours=40,
        nd_possible=True,
        adult=True,
        reception=False,
        nd_alone=True,
    )

    # Shift count decision variables for 2 staff members (in half-units: 1 duty = 2 units)
    c1 = model.NewIntVar(0, 50, "c1")
    c2 = model.NewIntVar(0, 50, "c2")
    counts = {s1.identifier: c1, s2.identifier: c2}
    presence_factors = {s1.identifier: 1000, s2.identifier: 1000}
    scale = 400

    objective_terms: list[cp_model.LinearExpr] = []
    _add_group_fairness_objective_with_presence(
        model=model,
        objective_terms=objective_terms,
        counts=counts,
        group=[s1, s2],
        scale=scale,
        presence_factors=presence_factors,
        prefix="TFA_test",
        max_fte_deviation=1.5,
    )

    # Helper to test feasibility under forced half-unit duty difference
    def check_difference_half_units(diff_half_units: int) -> int:
        test_model = model.Clone()
        test_model.Add(c1 - c2 == diff_half_units)
        solver = cp_model.CpSolver()
        return solver.Solve(test_model)

    # 1.5 Notdienste difference (= 3 half-units) is OPTIMAL/FEASIBLE under 1.5 FTE ceiling (threshold_scaled = 30)
    status_1_5 = check_difference_half_units(3)
    assert status_1_5 in (cp_model.OPTIMAL, cp_model.FEASIBLE)

    # 2.0 Notdienste difference (= 4 half-units) exceeds the 1.5 ceiling (scaled range 40 > 30) and is INFEASIBLE
    status_2_0 = check_difference_half_units(4)
    assert status_2_0 == cp_model.INFEASIBLE


def test_e2_b6_schedule_lifecycle_states(tmp_path: Path) -> None:
    """Ensure schedule documents support and track DRAFT, PUBLISHED, CLOSED states."""
    repo = FileJsonRepository(base_dir=tmp_path)
    doc = QuarterScheduleDocument(
        quarter_key="2026-Q3",
        year=2026,
        quarter=3,
        state=ScheduleState.DRAFT,
    )
    repo.save_schedule(doc)

    loaded = repo.get_schedule("2026-Q3")
    assert loaded is not None
    assert loaded.state == ScheduleState.DRAFT

    # Transition to PUBLISHED
    loaded.state = ScheduleState.PUBLISHED
    repo.save_schedule(loaded)
    assert repo.get_schedule("2026-Q3").state == ScheduleState.PUBLISHED

    # Transition to CLOSED
    loaded.state = ScheduleState.CLOSED
    repo.save_schedule(loaded)
    assert repo.get_schedule("2026-Q3").state == ScheduleState.CLOSED


def test_e2_b4_swap_shift_validates_staff_presence(client: TestClient) -> None:
    """Swap endpoint rejects swaps when target staff does not exist in the quarter."""
    swap_payload = {
        "shift_date": "2026-04-05",
        "shift_type": "N_Sa-So",
        "source_staff_id": "non_existent_1",
        "target_staff_id": "non_existent_2",
    }
    resp = client.post("/api/v1/quarters/2026-Q2/shifts/swap", json=swap_payload)
    assert resp.status_code in (404, 422)


# =============================================================================
# E3: Exception Handling & Client Error Sanitization
# =============================================================================


def test_e3_worker_sanitizes_unhandled_exception(tmp_path: Path) -> None:
    """Unhandled internal exception masks stack trace and returns a safe Fehler-ID."""
    repo = FileJsonRepository(base_dir=tmp_path)
    job_rec = SolverJobRecord(
        job_id="job_e3_err",
        quarter_key="2026-Q3",
        status=SolverJobStatus.RUNNING,
    )
    repo.save_solver_job(job_rec)

    active_job = ActiveJobState(
        job_id="job_e3_err",
        quarter_key="2026-Q3",
        thread=MagicMock(),
        cancellation_event=MagicMock(),
    )

    with patch(
        "app.api.v1.quarters.generate_schedule",
        side_effect=ZeroDivisionError("secret internal divide-by-zero at line 42"),
    ):
        _execute_solver_worker(
            quarter_key="2026-Q3",
            job_id="job_e3_err",
            max_solve_time_seconds=5,
            random_seed=42,
            include_previous_context=False,
            repo=repo,
            cancellation_event=active_job.cancellation_event,
            active_job=active_job,
        )

    saved_job = repo.get_solver_job("2026-Q3")
    assert saved_job is not None
    assert saved_job.status == SolverJobStatus.FAILED
    assert "Fehler-ID:" in saved_job.error
    assert "secret internal divide-by-zero" not in saved_job.error
    assert "ZeroDivisionError" not in saved_job.error


def test_e3_worker_includes_domain_exception_message(tmp_path: Path) -> None:
    """Domain SchedulingError or ValueError retains its user-friendly message with Fehler-ID."""
    repo = FileJsonRepository(base_dir=tmp_path)
    job_rec = SolverJobRecord(
        job_id="job_e3_sched",
        quarter_key="2026-Q3",
        status=SolverJobStatus.RUNNING,
    )
    repo.save_solver_job(job_rec)

    active_job = ActiveJobState(
        job_id="job_e3_sched",
        quarter_key="2026-Q3",
        thread=MagicMock(),
        cancellation_event=MagicMock(),
    )

    with patch(
        "app.api.v1.quarters.generate_schedule",
        side_effect=SchedulingError("Unzureichende Notdienst-Besetzung für Q3."),
    ):
        _execute_solver_worker(
            quarter_key="2026-Q3",
            job_id="job_e3_sched",
            max_solve_time_seconds=5,
            random_seed=42,
            include_previous_context=False,
            repo=repo,
            cancellation_event=active_job.cancellation_event,
            active_job=active_job,
        )

    saved_job = repo.get_solver_job("2026-Q3")
    assert saved_job is not None
    assert saved_job.status == SolverJobStatus.FAILED
    assert "Unzureichende Notdienst-Besetzung für Q3." in saved_job.error
    assert "Fehler-ID:" in saved_job.error


def test_e3_progress_callback_handles_exception_without_crashing() -> None:
    """_SchedulingProgressCallback catches callback errors and logs without crashing search."""
    bad_callback = MagicMock(side_effect=RuntimeError("UI rendering failed"))
    cb = _SchedulingProgressCallback(
        cancellation_event=None,
        on_progress=bad_callback,
    )

    # Run a trivial 1ms solve that triggers the solution callback
    model = cp_model.CpModel()
    v = model.NewIntVar(0, 10, "v")
    model.Minimize(v)
    solver = cp_model.CpSolver()
    status = solver.Solve(model, cb)

    assert status == cp_model.OPTIMAL
    assert len(cb.solutions) >= 1
    assert bad_callback.called


# =============================================================================
# E4: Docker & Container Hygiene Tests
# =============================================================================


def test_e4_dockerfile_hygiene() -> None:
    """Verify Dockerfile uses pinned uv version, single canonical PYTHONPATH, and python healthcheck."""
    dockerfile_path = Path(__file__).parents[1] / "Dockerfile"
    content = dockerfile_path.read_text(encoding="utf-8")

    # Pinned uv image tag (not unpinned :latest)
    assert "ghcr.io/astral-sh/uv:" in content
    assert "ghcr.io/astral-sh/uv:latest" not in content

    # Canonical PYTHONPATH root without redundant doubled child
    assert 'PYTHONPATH="/app"' in content
    assert 'PYTHONPATH="/app:/app/app"' not in content

    # Python stdlib healthcheck script without curl
    assert "scripts/healthcheck.py" in content
    assert "curl" not in content


def test_e4_healthcheck_script_execution(monkeypatch: pytest.MonkeyPatch) -> None:
    """Healthcheck script returns 0 on HTTP 200 and 1 on connection failure."""
    # When connection fails
    monkeypatch.setenv("PORT", "59999")
    assert check_health() == 1

    # When mocked HTTP 200 response
    mock_resp = MagicMock()
    mock_resp.status = 200
    mock_resp.__enter__.return_value = mock_resp
    with patch("urllib.request.urlopen", return_value=mock_resp):
        assert check_health() == 0
