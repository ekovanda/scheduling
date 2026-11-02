"""Unit tests for the fast testing workflow and solver test harness (conftest.py)."""

from datetime import date
from unittest.mock import MagicMock, patch

from conftest import (
    build_solver_cache_key,
    make_early_stop_callback_class,
    pytest_collection_modifyitems,
)

from app.scheduler.models import Beruf, SchedulerConfig, Staff, Vacation


def _sample_staff() -> list[Staff]:
    return [
        Staff(
            name="Alice",
            identifier="AL",
            adult=True,
            hours=40,
            beruf=Beruf.TFA,
            reception=True,
            nd_possible=True,
            nd_alone=True,
        )
    ]


def test_build_solver_cache_key_is_deterministic_and_sensitive_to_inputs() -> None:
    """Cache key is deterministic and changes when any problem input changes."""
    staff = _sample_staff()
    q_start = date(2026, 4, 1)

    key_a = build_solver_cache_key(staff, q_start, vacations=[], random_seed=42)
    key_b = build_solver_cache_key(staff, q_start, vacations=None, random_seed=42)
    assert key_a == key_b

    # Different seed -> different key
    key_diff_seed = build_solver_cache_key(staff, q_start, vacations=[], random_seed=7)
    assert key_a != key_diff_seed

    # Different config -> different key
    key_diff_cfg = build_solver_cache_key(
        staff,
        q_start,
        vacations=[],
        random_seed=42,
        config=SchedulerConfig(block_gap_days=14),
    )
    assert key_a != key_diff_cfg

    # Different vacations -> different key
    key_diff_vac = build_solver_cache_key(
        staff,
        q_start,
        vacations=[
            Vacation(
                identifier="AL",
                start_date=date(2026, 4, 2),
                end_date=date(2026, 4, 5),
            )
        ],
        random_seed=42,
    )
    assert key_a != key_diff_vac


def test_early_stop_callback_triggers_stop_search_after_grace_window() -> None:
    """Early-stop callback calls StopSearch only after grace_seconds has elapsed."""
    cb_cls = make_early_stop_callback_class(grace_seconds=1.5)
    cb = cb_cls()
    current_wt = {"value": 0.0}

    with (
        patch.object(
            type(cb),
            "wall_time",
            new_callable=lambda: property(lambda _self: current_wt["value"]),
            create=True,
        ),
        patch.object(
            type(cb),
            "objective_value",
            new_callable=lambda: property(lambda _self: 100.0),
            create=True,
        ),
        patch.object(
            type(cb),
            "best_objective_bound",
            new_callable=lambda: property(lambda _self: 50.0),
            create=True,
        ),
        patch.object(cb, "StopSearch") as mock_stop,
    ):
        # First solution at t=5.0s -> should NOT stop yet
        current_wt["value"] = 5.0
        cb.on_solution_callback()
        mock_stop.assert_not_called()

        # Second solution at t=6.0s (elapsed 1.0s < 1.5s) -> should NOT stop yet
        current_wt["value"] = 6.0
        cb.on_solution_callback()
        mock_stop.assert_not_called()

        # Third solution at t=6.6s (elapsed 1.6s >= 1.5s) -> MUST stop search
        current_wt["value"] = 6.6
        cb.on_solution_callback()
        mock_stop.assert_called_once()


def test_pytest_collection_modifyitems_skips_slow_only_when_fast_flag_set() -> None:
    """--fast marks @pytest.mark.slow tests as skipped while keeping fast tests active."""
    slow_item = MagicMock()
    slow_item.keywords = {"slow": True}
    fast_item = MagicMock()
    fast_item.keywords = {}

    # 1. --fast is False: nothing skipped
    cfg_default = MagicMock()
    cfg_default.getoption.return_value = False
    pytest_collection_modifyitems(cfg_default, [slow_item, fast_item])
    slow_item.add_marker.assert_not_called()
    fast_item.add_marker.assert_not_called()

    # 2. --fast is True: only slow_item gets skip marker
    cfg_fast = MagicMock()
    cfg_fast.getoption.return_value = True
    pytest_collection_modifyitems(cfg_fast, [slow_item, fast_item])
    slow_item.add_marker.assert_called_once()
    fast_item.add_marker.assert_not_called()
