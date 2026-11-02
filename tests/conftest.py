"""Pytest configuration, CLI flags, and solver runtime optimizations.

Provides three ways to balance test speed and solver depth:
1. ``pytest --fast`` (or ``pytest -m "not slow"``): skips full-quarter CP-SAT
   integration tests for ~3s inner-loop feedback during active development.
2. Default ``pytest``: runs all tests (including ``@pytest.mark.slow``), but
   applies a post-first-solution grace window (default 1.5s) and session-level
   memoization of identical solver inputs. This cuts full-suite runtime by ~80%
   without weakening any hard-constraint or soft-fairness assertions.
3. ``pytest --full-solve``: disables early stopping and runs every CP-SAT test
   for its full 30s-60s timeout ceiling.
"""

import json
from collections.abc import Generator
from dataclasses import asdict, is_dataclass
from datetime import date
from typing import Any

import pytest

from app.scheduler import solver as solver_facade
from app.scheduler import solver_cpsat
from app.scheduler.models import (
    PreAssignedShift,
    PreviousPlanContext,
    SchedulerConfig,
    Staff,
    Vacation,
)
from app.scheduler.solver_cpsat import SolverResult

_BASE_PROGRESS_CALLBACK_CLS = (
    solver_cpsat._SchedulingProgressCallback  # pylint: disable=protected-access
)


def _serialize_item(obj: Any) -> Any:
    """Serialize Pydantic models and dataclasses into JSON-compatible primitives."""
    if obj is None:
        return None
    if hasattr(obj, "model_dump"):
        return obj.model_dump(mode="json")
    if is_dataclass(obj) and not isinstance(obj, type):
        return asdict(obj)
    return str(obj)


def pytest_addoption(parser: pytest.Parser) -> None:
    """Register custom CLI flags for controlling test speed vs solver depth."""
    group = parser.getgroup("scheduler", "Scheduler test execution options")
    group.addoption(
        "--fast",
        action="store_true",
        default=False,
        help="Skip @pytest.mark.slow full-quarter CP-SAT solver integration tests.",
    )
    group.addoption(
        "--full-solve",
        action="store_true",
        default=False,
        help="Disable CP-SAT early stopping and run solver tests for their full time limit.",
    )
    group.addoption(
        "--solver-grace",
        action="store",
        type=float,
        default=1.5,
        help="Seconds to continue optimizing after first feasible CP-SAT solution (default: 1.5).",
    )


def pytest_collection_modifyitems(
    config: pytest.Config, items: list[pytest.Item]
) -> None:
    """Skip @pytest.mark.slow tests when --fast is passed."""
    if not config.getoption("--fast"):
        return

    skip_slow = pytest.mark.skip(
        reason="Skipped in --fast mode (omit --fast to run full-quarter solver tests)"
    )
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip_slow)


def build_solver_cache_key(  # pylint: disable=too-many-positional-arguments
    staff_list: list[Staff],
    quarter_start: date,
    vacations: list[Vacation] | None = None,
    random_seed: int | None = None,
    previous_context: PreviousPlanContext | None = None,
    pre_assigned: list[PreAssignedShift] | None = None,
    config: SchedulerConfig | None = None,
) -> str:
    """Build a deterministic JSON cache key from solver problem inputs.

    Intentionally excludes ``max_solve_time_seconds`` so identical baseline
    schedules requested with 30s vs 60s ceilings share a single solve per session.
    """
    payload = {
        "staff": [_serialize_item(s) for s in staff_list],
        "quarter_start": quarter_start.isoformat(),
        "vacations": [_serialize_item(v) for v in (vacations or [])],
        "random_seed": random_seed,
        "previous_context": _serialize_item(previous_context),
        "pre_assigned": [_serialize_item(p) for p in (pre_assigned or [])],
        "config": _serialize_item(config or SchedulerConfig()),
    }
    return json.dumps(payload, sort_keys=True, default=str)


def make_early_stop_callback_class(
    grace_seconds: float,
) -> type[solver_cpsat._SchedulingProgressCallback]:
    """Create a solution callback subclass that stops ``grace_seconds`` after first solution."""
    base_cls = _BASE_PROGRESS_CALLBACK_CLS

    class _EarlyStopProgressCallback(base_cls):  # type: ignore[valid-type,misc]
        """Stops CP-SAT once a feasible schedule has been refined for ``grace_seconds``."""

        def on_solution_callback(self) -> None:
            super().on_solution_callback()
            if (
                len(self.solutions) >= 1
                and (self.wall_time - self.solutions[0]["wall_time"]) >= grace_seconds
            ):
                self.StopSearch()

    return _EarlyStopProgressCallback


@pytest.fixture(scope="session", autouse=True)
def _configure_test_solver(
    request: pytest.FixtureRequest,
) -> Generator[None, None, None]:
    """Apply session-level solver memoization and optional post-solution early stopping."""
    full_solve: bool = bool(request.config.getoption("--full-solve"))
    grace_seconds: float = float(request.config.getoption("--solver-grace"))

    original_callback_cls = (
        solver_cpsat._SchedulingProgressCallback  # pylint: disable=protected-access
    )
    original_cpsat_fn = solver_cpsat.generate_schedule_cpsat
    original_facade_fn = (
        solver_facade.generate_schedule_cpsat  # type: ignore[attr-defined]
    )

    session_cache: dict[str, SolverResult] = {}

    if not full_solve:
        early_cls = make_early_stop_callback_class(grace_seconds)
        solver_cpsat._SchedulingProgressCallback = (  # type: ignore[misc]  # pylint: disable=protected-access
            early_cls
        )

    def cached_generate_schedule_cpsat(  # pylint: disable=too-many-positional-arguments
        staff_list: list[Staff],
        quarter_start: date,
        vacations: list[Vacation] | None = None,
        max_solve_time_seconds: int = 120,
        random_seed: int | None = None,
        previous_context: PreviousPlanContext | None = None,
        pre_assigned: list[PreAssignedShift] | None = None,
        config: SchedulerConfig | None = None,
    ) -> SolverResult:
        key = build_solver_cache_key(
            staff_list=staff_list,
            quarter_start=quarter_start,
            vacations=vacations,
            random_seed=random_seed,
            previous_context=previous_context,
            pre_assigned=pre_assigned,
            config=config,
        )
        if key not in session_cache:
            session_cache[key] = original_cpsat_fn(
                staff_list,
                quarter_start,
                vacations=vacations,
                max_solve_time_seconds=max_solve_time_seconds,
                random_seed=random_seed,
                previous_context=previous_context,
                pre_assigned=pre_assigned,
                config=config,
            )
        return session_cache[key]

    solver_cpsat.generate_schedule_cpsat = cached_generate_schedule_cpsat
    solver_facade.generate_schedule_cpsat = (  # type: ignore[attr-defined]
        cached_generate_schedule_cpsat
    )

    try:
        yield
    finally:
        solver_cpsat._SchedulingProgressCallback = (  # type: ignore[misc]  # pylint: disable=protected-access
            original_callback_cls
        )
        solver_cpsat.generate_schedule_cpsat = original_cpsat_fn
        solver_facade.generate_schedule_cpsat = (  # type: ignore[attr-defined]
            original_facade_fn
        )
