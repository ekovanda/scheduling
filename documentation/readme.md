# Dienstplan Scheduler - Technical Documentation

## Architecture

### Core Components

1. **models.py**: Pydantic models for type-safe data structures
   - `Staff`: Employee data with constraints (nd_count, nd_exceptions)
   - `Shift`: Shift slots (Saturday/Sunday/Night)
   - `Assignment`: Staff → Shift mapping
   - `Schedule`: Full quarter schedule with helper methods

2. **validator.py**: Constraint validation engine
   - Hard constraints: Return violations list (must be empty)
   - Soft constraints: Return penalty score (minimize)
   - Rolling 3-week window checker
   - Consecutive block detector

3. **solver.py**: Heuristic optimizer
   - Phase 1: Greedy assignment (fairness-based)
   - Phase 2: Local search with simulated annealing
   - Swap/shift moves for optimization
   - Returns top 3 candidates

4. **streamlit_app.py**: German UI with 6 pages
   - Session state management
   - CSV upload/parsing
   - Schedule visualization
   - Excel/CSV export

## Key Algorithms

### Greedy Assignment

```
1. Sort shifts by date.
2. Assign Saturdays/Sundays using "Fewest Assignments" heuristic.
3. Assign Night Shifts using "Block-Aware" logic:
   Iterate per day:
     - Identify staff continuing a block from yesterday (Priority 1)
     - Identify staff starting a new block (Priority 2)
     - Maintain `active_blocks` state to satisfy `nd_count` constraints
```

### 3-Week Block Constraint

```python
def check_3_week_blocks(assignments):
    blocks = find_consecutive_blocks(assignments)
    for each block_pair:
        if start_distance < 21 days:
            violation!
```

### Effective Nights Calculation

```python
effective_nights = sum(
    0.5 if assignment.is_paired else 1.0
    for assignment in night_assignments
)
```

## Business Rules Reference

### Shift Coverage Requirements

**Saturdays (13 weeks × 3 shifts = 39 total)**
- 10-21: Azubi (reception=true) or TFA
- 10-22: Any eligible
- 10-19: Azubi (reception=false) ONLY

**Sundays (13 weeks × 3 shifts = 39 total)**
- 8-20: Adult only
- 10-22: Adult only
- 8-20:30: Adult Azubi only (8-12 onsite, rest on-call)

**Nights (91 days)**
- Sun→Mon: 1 TFA (TA present)
- Mon→Tue: 1 TFA (TA present)
- Other: 1-2 TFA (pair if nd_alone=False)

### Constraint Priority

1. **Hard** (fail if violated)
   - Age restrictions (minors/Sundays)
   - Role restrictions (TA/weekends)
   - Pairing rules (Azubi/nd_alone)
   - 3-week block limit
   - nd_count/nd_exceptions

2. **Soft** (minimize penalty)
   - Proportional distribution (by hours)
   - Within-group fairness (TFA/Azubi/TA)
   - Azubi minor Saturday compensation

## Performance Notes

- Greedy phase: O(n × m) where n=shifts, m=staff
- Local search: 2000 iterations × O(m) validation
- Typical runtime: 2-5 seconds for Q2/2026

## Testing Strategy

- Unit tests: Core logic (effective_nights, eligibility)
- Integration tests: End-to-end schedule generation
- Constraint tests: Each hard constraint validated
- Coverage target: >80% for scheduler/ module

## Future Enhancements

- [ ] Vacation/availability import
- [ ] Manual schedule overrides
- [ ] Multi-quarter planning
- [ ] Constraint relaxation suggestions
- [ ] Historical fairness tracking
- [ ] Azubi school day filtering
