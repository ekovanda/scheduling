"""Solver facade for Notdienst scheduling.

Delegates to the OR-Tools CP-SAT solver (solver_cpsat.py).
"""

import threading
from collections.abc import Callable
from datetime import date
from typing import Any

from ortools.sat.python import cp_model

from .models import PreAssignedShift, PreviousPlanContext, SchedulerConfig, Staff, Vacation
from .solver_cpsat import SolverResult, generate_schedule_cpsat


def generate_schedule(
    staff_list: list[Staff],
    quarter_start: date,
    vacations: list[Vacation] | None = None,
    max_solve_time_seconds: int = 120,
    random_seed: int | None = None,
    previous_context: PreviousPlanContext | None = None,
    pre_assigned: list[PreAssignedShift] | None = None,
    config: SchedulerConfig | None = None,
    cancellation_event: threading.Event | None = None,
    on_progress: Callable[[dict[str, Any]], None] | None = None,
    on_solver_created: Callable[[cp_model.CpSolver], None] | None = None,
    stagnation_limit_seconds: float | None = 15.0,
) -> SolverResult:
    """Generate schedule using OR-Tools CP-SAT solver.

    Args:
        staff_list: List of staff members
        quarter_start: Start date of quarter (e.g., April 1, 2026)
        vacations: List of vacation periods (staff unavailability)
        max_solve_time_seconds: Maximum solver time in seconds (default 120)
        random_seed: Random seed for reproducibility
        previous_context: Carry-forward context from previous quarter

    Returns:
        SolverResult with best schedule or unsatisfiable constraints
    """
    if vacations is None:
        vacations = []

    kwargs: dict[str, Any] = {
        "vacations": vacations,
        "max_solve_time_seconds": max_solve_time_seconds,
        "random_seed": random_seed,
        "previous_context": previous_context,
        "pre_assigned": pre_assigned,
        "config": config,
    }
    if cancellation_event is not None:
        kwargs["cancellation_event"] = cancellation_event
    if on_progress is not None:
        kwargs["on_progress"] = on_progress
    if on_solver_created is not None:
        kwargs["on_solver_created"] = on_solver_created
    if stagnation_limit_seconds is not None:
        kwargs["stagnation_limit_seconds"] = stagnation_limit_seconds

    return generate_schedule_cpsat(
        staff_list,
        quarter_start,
        **kwargs,
    )
