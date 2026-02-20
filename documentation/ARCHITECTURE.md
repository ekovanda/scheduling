# Architecture & Technical Documentation

## Overview

The Dienstplan Generator uses a **constraint programming** approach (OR-Tools CP-SAT) to find optimal schedules that satisfy all hard constraints while minimizing fairness deviation.

## Module Structure

```
app/
├── streamlit_app.py          # Streamlit UI (7 pages, German)
└── scheduler/
    ├── __init__.py           # Public exports
    ├── models.py             # Pydantic data models
    ├── validator.py          # Constraint validation engine
    ├── solver.py             # Solver facade (delegates to solver_cpsat)
    └── solver_cpsat.py       # OR-Tools CP-SAT implementation
```

## Core Components

### 1. models.py - Data Structures

**Enums:**
- `Beruf`: Staff roles (TFA, Azubi, Intern)
- `Abteilung`: Department (station, op, other)
- `ShiftType`: All shift types (Sa_10-21, N_So-Mo, etc.)

**Pydantic Models:**
- `Staff`: Employee with constraints (abteilung, nd_max_consecutive, nd_exceptions, etc.)
- `Shift`: A specific shift slot (type + date)
- `Assignment`: Staff → Shift mapping with `is_paired` flag
- `Schedule`: Full quarter schedule with helper methods

**Key Methods:**
```python
Staff.can_work_shift(shift_type, date) -> bool  # Eligibility check
Staff.effective_nights_weight(is_paired) -> float  # TFA/Intern: 0.5 if paired, 1.0 if solo; Azubi: always 1.0
Schedule.count_effective_nights(staff_id, staff) -> float  # Sum of weighted nights
```

### 2. validator.py - Constraint Validation

**Hard Constraint Checks:**
| Function | Rule |
|----------|------|
| `_check_minor_sunday_constraint` | Minors cannot work Sundays |
| `_check_intern_weekend_constraint` | Interns never work weekends |
| `_check_night_pairing_constraint` | Azubis must pair with non-Azubi |
| `_check_nd_alone_improper_pairing` | nd_alone=True must work **completely alone** on regular nights |
| `_check_intern_night_capacity` | Sun-Mon/Mon-Tue: exactly 1 non-Azubi + optional 0-1 Azubi |
| `_check_min_consecutive_nights_constraint` | Non-Azubis must work 2+ consecutive nights |
| `_check_same_day_next_day_constraint` | No day shift after night shift |
| `_check_three_week_block_constraint` | Max 1 block per 14-day window |
| `_check_weekend_isolation_constraint` | Weekend shifts cannot be adjacent to other shifts |
| `_check_nd_exceptions_constraint` | Respect weekday exclusions |
| `_check_shift_eligibility` | General eligibility check (Sa 10-22, So 8-20, So 10-22 = TFA only) |
| `_check_shift_coverage` | All shifts must be covered |
| `_check_abteilung_night_constraint` | Same abteilung (op/station) cannot work together or consecutively |
| `_check_same_day_double_booking` | Max 1 shift per person per day |

**Soft Penalty Calculation:**
- Squared deviation from proportional target
- Standard deviation within role groups × 10
- nd_max_consecutive violations × 100

### 3. solver.py - Solver Facade

Thin facade that delegates to the CP-SAT solver.

**Main Entry Point:**
```python
def generate_schedule(
    staff_list: list[Staff],
    quarter_start: date,
    max_solve_time_seconds: int = 120,
    random_seed: int | None = None,
) -> SolverResult
```

### 4. solver_cpsat.py - CP-SAT Implementation

**Decision Variables:**
- `x[staff, date, shift_type]`: Binary, 1 if assigned
- `is_paired[staff, date]`: Binary, 1 if working paired night

**Constraint Encoding:**
- Weekend coverage: `sum(x[*, date, type]) == 1`
- Night coverage: `1 <= sum(x[*, date, type]) <= 2`, at least 1 non-Azubi
- Sun-Mon/Mon-Tue: exactly 1 non-Azubi + optional 0-1 Azubi
- Azubi pairing: Azubi assigned => non-Azubi assigned
- Pairing logic: `x[s,d,t] => is_paired[s,d]` for nd_alone=False
- nd_alone=True: Must work alone (sum of all others == 0)
- Min consecutive: Non-Azubis must have adjacent night if assigned
- Block constraint: Track block starts, forbid two within 14 days
- Weekend isolation: Weekend shifts cannot be adjacent to other shifts
- nd_max_consecutive: Sliding window sum constraints
- Abteilung constraint: Same abteilung (op/station) <= 1 per night, no consecutive

**Objective Function:**
Minimize `sum(range_var)` where `range_var = max_fte - min_fte` for combined Notdienste within each group.

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
6. Solve with time limit (120s default)
7. Extract solution
```

## Performance Characteristics

| Solver | Time | Optimality | Use Case |
|--------|------|------------|----------|
| CP-SAT | 60-120s | Guaranteed optimal | Production |

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
