"""Solver facade for Notdienst scheduling.

Delegates to the OR-Tools CP-SAT solver (solver_cpsat.py).
"""

from datetime import date

from .models import Staff, Vacation
from .solver_cpsat import SolverResult, generate_schedule_cpsat


def generate_schedule(
    staff_list: list[Staff],
    quarter_start: date,
    vacations: list[Vacation] | None = None,
    max_solve_time_seconds: int = 120,
    random_seed: int | None = None,
) -> SolverResult:
    """Generate schedule using OR-Tools CP-SAT solver.

    Args:
        staff_list: List of staff members
        quarter_start: Start date of quarter (e.g., April 1, 2026)
        vacations: List of vacation periods (staff unavailability)
        max_solve_time_seconds: Maximum solver time in seconds (default 120)
        random_seed: Random seed for reproducibility

    Returns:
        SolverResult with best schedule or unsatisfiable constraints
    """
    if vacations is None:
        vacations = []

    return generate_schedule_cpsat(
        staff_list,
        quarter_start,
        vacations=vacations,
        max_solve_time_seconds=max_solve_time_seconds,
        random_seed=random_seed,
    )
