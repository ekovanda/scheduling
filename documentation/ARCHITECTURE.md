# Architecture & Technical Documentation

## Overview

The Dienstplan Generator uses a **constraint programming** approach (OR-Tools CP-SAT) to find optimal schedules that satisfy all hard constraints while minimizing fairness deviation.

## Module Structure

```
app/
├── streamlit_app.py          # Streamlit UI (6 pages, German)
└── scheduler/
    ├── __init__.py           # Public exports
    ├── models.py             # Pydantic data models
    ├── validator.py          # Constraint validation engine
    ├── solver.py             # Solver facade + heuristic implementation
    └── solver_cpsat.py       # OR-Tools CP-SAT implementation
```

## Core Components

### 1. models.py - Data Structures

**Enums:**
- `Beruf`: Staff roles (TFA, Azubi, TA)
- `ShiftType`: All shift types (Sa_10-21, N_So-Mo, etc.)

**Pydantic Models:**
- `Staff`: Employee with constraints (nd_count, nd_exceptions, etc.)
- `Shift`: A specific shift slot (type + date)
- `Assignment`: Staff → Shift mapping with `is_paired` flag
- `Schedule`: Full quarter schedule with helper methods

**Key Methods:**
```python
Staff.can_work_shift(shift_type, date) -> bool  # Eligibility check
Staff.effective_nights_weight(is_paired) -> float  # 0.5 if paired, 1.0 if solo
Schedule.count_effective_nights(staff_id) -> float  # Sum of weighted nights
```

### 2. validator.py - Constraint Validation

**Hard Constraint Checks:**
| Function | Rule |
|----------|------|
| `_check_minor_sunday_constraint` | Minors cannot work Sundays |
| `_check_ta_weekend_constraint` | TAs never work weekends |
| `_check_night_pairing_constraint` | nd_alone=False must be paired |
| `_check_nd_alone_ta_nights_constraint` | nd_alone=True cannot work TA-present nights |
| `_check_same_day_next_day_constraint` | No day shift after night shift |
| `_check_three_week_block_constraint` | Max 1 block per 14-day window |
| `_check_nd_exceptions_constraint` | Respect weekday exclusions |
| `_check_shift_eligibility` | General eligibility check |
| `_check_shift_coverage` | All shifts must be covered |

**Soft Penalty Calculation:**
- Squared deviation from proportional target
- Standard deviation within role groups × 10
- nd_count violations × 100 (moved from hard to soft)

### 3. solver.py - Solver Facade

**SolverBackend Enum:**
- `HEURISTIC`: Greedy + local search (fast, less optimal)
- `CPSAT`: OR-Tools constraint programming (slower, optimal)

**Main Entry Point:**
```python
def generate_schedule(
    staff_list: list[Staff],
    quarter_start: date,
    max_iterations: int = 2000,
    random_seed: int | None = None,
    backend: SolverBackend = SolverBackend.HEURISTIC,
) -> SolverResult
```

### 4. solver_cpsat.py - CP-SAT Implementation

**Decision Variables:**
- `x[staff, date, shift_type]`: Binary, 1 if assigned
- `is_paired[staff, date]`: Binary, 1 if working paired night

**Constraint Encoding:**
- Weekend coverage: `sum(x[*, date, type]) == 1`
- Night coverage: `1 <= sum(x[*, date, type]) <= 2`
- Pairing logic: `x[s,d,t] => is_paired[s,d]` for nd_alone=False
- Block constraint: Track block starts, forbid two within 14 days
- nd_count: Sliding window sum constraints

**Objective Function:**
Minimize `sum(range_var)` where `range_var = max_fte - min_fte` for each group.

## Algorithms

### CP-SAT Fairness Optimization

```
1. Create boolean variables for each (staff, shift) pair
2. Add hard constraints as CP constraints
3. Create scaled FTE variables: count * (SCALE / hours)
4. For each role group:
   - max_var = max(scaled_counts)
   - min_var = min(scaled_counts)
   - range_var = max_var - min_var
5. Minimize sum of all range_var
6. Solve with time limit
7. Extract solution
```

### Heuristic Fallback

```
Phase 1 - Greedy Assignment:
1. Sort shifts by date
2. For each shift, select staff with lowest FTE load
3. Track active night blocks for nd_count continuity

Phase 2 - Local Search:
1. For 2000 iterations:
   a. 40% fairness moves (overloaded → underloaded)
   b. 30% swap moves (exchange two assignments)
   c. 30% shift moves (reassign single shift)
2. Accept if valid and improves penalty
3. Simulated annealing for exploration
```

## Performance Characteristics

| Solver | Time | Optimality | Use Case |
|--------|------|------------|----------|
| CP-SAT | 60-120s | Guaranteed optimal | Production |
| Heuristic | 2-5s | Local optimum | Development/testing |

## Data Flow

```
CSV Upload → Staff List → Solver → Schedule → Validator → UI Display
                ↓                      ↓
            Shift Generation      Assignment List
```

## Session State (Streamlit)

```python
st.session_state.staff_list: list[Staff] | None
st.session_state.schedule: Schedule | None
st.session_state.validation_result: ValidationResult | None
```

## Testing Strategy

- Unit tests for constraint checks (`test_scheduler.py`)
- Integration tests for solver validity
- Fairness tolerance tests (±1 FTE within groups)

## Extension Points

1. **New constraints**: Add check function to validator.py, add CP constraint to solver_cpsat.py
2. **New shift types**: Add to ShiftType enum, update generate_quarter_shifts()
3. **Custom objectives**: Modify `_add_group_fairness_objective()` in solver_cpsat.py
