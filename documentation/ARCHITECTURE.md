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
- `Beruf`: Staff roles (`TFA`, `Azubi`, `Intern`, `Vet`)
- `Abteilung`: Department (`station`, `op`, `other`)
- `ShiftType`: All shift types (`Sa_10-21`, `So_8-20`, `Sa_Intern`, `So_Intern`, `N_So-Mo`, `N_Mo-Di`, `N_Di-Mi`, etc.)

**Pydantic Models:**
- `Staff`: Employee with constraints (`abteilung`, `nd_max_consecutive`, `nd_exceptions`, etc.)
  - Special invariants for `Beruf.VET`: `hours=0.0`, `adult=True`, `nd_alone=True`, `nd_min_consecutive=2`, `nd_max_consecutive=2`, `reception=False`, `abteilung=OTHER`.
- `Shift`: A specific shift slot (type + date).
  - Categorization helpers: `is_open_night()` (`N_So-Mo`, `N_Mo-Di`) and `is_closed_night()` (`N_Di-Mi` through `N_Sa-So`).
  - Weekend helpers: `is_intern_weekend_shift()` (`Sa_Intern`, `So_Intern`).
- `Assignment`: Staff → Shift mapping with `is_paired` flag
- `Schedule`: Full quarter schedule with helper methods

**Cross-Quarter Models:**
```python
TrailingAssignment  # Last 21 days of previous quarter — boundary constraint source
CarryForwardEntry   # Per-person FTE delta from prior quarter
PreviousPlanContext # Trailing assignments + carry-forward + vet_active_last_month_ids
```

**Key Methods:**
```python
Staff.can_work_shift(shift_type, date) -> bool  # Eligibility check
Staff.effective_nights_weight(is_paired, is_open_night) -> float
# Open nights: TFA: 0.5, Intern: 1.0, Azubi: 1.0
# Closed nights: TFA/Intern paired: 0.5, solo: 1.0; Azubi: 1.0
Schedule.count_effective_nights(staff_id, staff) -> float  # Sum of weighted nights
build_previous_context(schedule, staff_list) -> PreviousPlanContext  # Export carry-forward & active Vets
build_previous_context_from_xlsx(source, staff_list) -> PreviousPlanContext  # Import from xlsx
```

### 2. validator.py - Constraint Validation

**Hard Constraint Checks:**
| Function | Rule |
|----------|------|
| `_check_minor_sunday_constraint` | Minors cannot work Sundays |
| `_check_intern_weekend_exclusivity` | Interns only on `Sa_Intern`/`So_Intern`; non-interns forbidden on Intern shifts |
| `_check_intern_coupled_weekend` | `Sa_Intern` and `So_Intern` of the same weekend must be assigned as an atomic pair to the same Intern |
| `_check_intern_monthly_weekend_cap` | Max 1 Intern weekend block per calendar month |
| `_check_open_night_headcount` | Open nights (`N_So-Mo`, `N_Mo-Di`) require exactly 2 persons (headcount = 2) |
| `_check_open_night_missing_tfa` | Open nights require at least 1 TFA (valid: TFA+TFA, TFA+Intern, TFA+Azubi; forbidden: Intern+Intern, Intern+Azubi) |
| `_check_night_pairing_constraint` | Azubis must pair with non-Azubi (TFA or Intern); max 1 Azubi per night |
| `_check_nd_alone_improper_pairing` | `nd_alone=True` staff must work **completely alone** on closed nights (may be paired on open nights) |
| `_check_vet_shift_constraints` | Tierärzte (`Beruf.VET`): only Di-Do (`N_Di-Mi`, `N_Mi-Do`, `N_Do-Fr`), exact 2-night blocks, strictly solo (headcount = 1), max 1 block per 2 calendar months |
| `_check_min_consecutive_nights_constraint` | Per-staff `nd_min_consecutive` blocks enforced |
| `_check_same_day_next_day_constraint` | No day shift on same day or next day after night shift |
| `_check_three_week_block_constraint` | Min gap between blocks: 21 days for TFA/Azubi, 10 days for Interns |
| `_check_weekend_isolation_constraint` | Weekend shifts cannot be adjacent to other shifts |
| `_check_nd_exceptions_constraint` | Respect weekday exclusions |
| `_check_shift_eligibility` | General eligibility check |
| `_check_shift_coverage` | All shifts must be covered |
| `_check_abteilung_night_constraint` | Same abteilung (op/station) cannot work together or consecutively |
| `_check_same_day_double_booking` | Max 1 shift per person per day |

**Soft Penalty Calculation:**
- Squared deviation from proportional target (excluding `Beruf.VET` with `hours=0`)
- Standard deviation within role groups × 10
- `nd_max_consecutive` violations × 100

### 3. solver.py - Solver Facade

Thin facade that delegates to the CP-SAT solver.

**Main Entry Point:**
```python
def generate_schedule(
    staff_list: list[Staff],
    quarter_start: date,
    vacations: list[Vacation] | None = None,
    pre_assigned: list[PreAssignedShift] | None = None,
    previous_context: PreviousPlanContext | None = None,
    config: SchedulerConfig | None = None,
    max_solve_time_seconds: int = 120,
    random_seed: int | None = None,
) -> SolverResult
```

### 4. solver_cpsat.py - CP-SAT Implementation

**Decision Variables:**
- `x[staff, date, shift_type]`: Binary, 1 if assigned
- `is_paired[staff, date]`: Binary, 1 if working paired night
- `w_int[intern, weekend_idx]`: Binary, coupled weekend assignment for Interns
- `b_dimi[vet, week]`, `b_mido[vet, week]`: Binary, exact 2-night midweek relief blocks for Tierärzte

**Constraint Encoding:**
- **Open Nights:** Exactly 2 persons (`sum(x) == 2`), at least 1 TFA (`sum(x_tfa) >= 1`), at most 1 Azubi (`sum(x_azubi) <= 1`).
- **Closed Nights:** Headcount 1 for `nd_alone=True` and Vets; headcount 2 for `nd_alone=False` and Azubi pairings.
- **Intern Coupled Weekends:** $x[\text{Sa\_Intern}] == w_{\text{int}}$ and $x[\text{So\_Intern}] == w_{\text{int}}$; single-day vacations block the entire weekend; max 1 weekend per calendar month.
- **Vet Midweek Relief:** $x[\text{Di}] == b_{\text{DiMi}}$, $x[\text{Mi}] == b_{\text{DiMi}} + b_{\text{MiDo}}$, $x[\text{Do}] == b_{\text{MiDo}}$; $b_{\text{DiMi}} + b_{\text{MiDo}} \le 1$ per week; max 1 block in any two consecutive calendar months; locked out in Month 1 if active in last month of previous quarter.
- **Block Spacing:** 21-day rolling gap for TFA/Azubi; 10-day rolling gap for Interns.
- **Night Quota:** Interns restricted to 6–9 night shifts per quarter.

**Objective Hierarchy:**
1. **Tierarzt-Entlastung (Highest Priority):**
   $$\text{Minimize} \quad -100\,000 \cdot \sum_{w, v} b[v, w]$$
2. **Cross-Quarter Boundary Feasibility:** Gap violation penalty `gap_diff * 10,000,000`.
3. **Primary Fairness:** FTE-scaled Notdienste range per group (presence + carry-forward adjusted).
4. **Secondary Fairness:** FTE-scaled night-shift range per group (type balance).
5. **Intern Weekend Fairness:** $300 \cdot (\max_{i} w_i - \min_{i} w_i)$ (balanced weekend rotation $\le 1$).
6. **Tierarzt Block Fairness:** $500 \cdot (\max_{v} b_v - \min_{v} b_v)$ (balanced relief distribution).

### 5. feasibility.py - Pre-Solve Diagnostics

Fast pre-solve validation:
- **Check A:** Closed night coverage vs TFA/Intern capacity (automatically discounted by Vet relief capacity).
- **Check B:** Weekend shift capacity.
- **Check C:** Azubi pairing capacity.
- **Check D:** Open night TFA presence capacity.
- **Check E:** Intern night and weekend capacity.
- **Check F:** Tierarzt-Nachtdienst-Entlastung capacity (reporting available Vets, max blocks, and relief nights).

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
CSV/XLSX Upload → Staff List + Vacations + Pre-assigned Shifts
                          ↓
                  Optional: Previous Plan XLSX → PreviousPlanContext
                          ↓                         (trailing assignments + carry-forward)
                       Solver
                          ↓
                      Schedule → Validator → UI Display
```

## Session State (Streamlit)

```python
st.session_state.staff_list: list[Staff] | None
st.session_state.vacations: list[Vacation] | None
st.session_state.pre_assigned: list[PreAssignedShift] | None
st.session_state.previous_context: PreviousPlanContext | None
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
