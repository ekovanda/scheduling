# Notdienst Scheduling - Problem Description

## Goal

Implement a quarterly Streamlit scheduling app that produces **fair, rules-compliant** Notdienst (weekend + night shift) schedules for a veterinary clinic with ~24 TFAs, ~11 Azubis, and 4 TAs.

## Business Context

The clinic requires 24/7 coverage through:
- **Weekend shifts** (Saturday + Sunday): 3 parallel shifts each day
- **Night shifts**: 7 nights per week, staffed by 1-2 people

Scheduling must balance:
1. **Hard constraints**: Legal requirements, safety rules (must be satisfied)
2. **Fairness**: Proportional workload distribution (optimized)

## Shift Types

### Saturday (3 shifts, 13 weeks = 39 total)
| Shift | Hours | Staffing Rule |
|-------|-------|---------------|
| Sa_10-21 | 10:00-21:00 | Azubi (reception=true) or TFA |
| Sa_10-22 | 10:00-22:00 | Any eligible staff |
| Sa_10-19 | 10:00-19:00 | Azubi (reception=false) ONLY |

### Sunday (3 shifts, 13 weeks = 39 total)
| Shift | Hours | Staffing Rule |
|-------|-------|---------------|
| So_8-20 | 08:00-20:00 | Adults only |
| So_10-22 | 10:00-22:00 | Adults only |
| So_8-20:30 | 08:00-20:30 | Adult Azubi only (8-12 onsite, rest on-call) |

### Night Shifts (91 nights per quarter)
| Night | Staffing | Notes |
|-------|----------|-------|
| Sun→Mon | 1 person | TA is present on-site |
| Mon→Tue | 1 person | TA is present on-site |
| Other nights | 1-2 people | Pair required if nd_alone=False |

## Hard Constraints (Must Satisfy)

1. **Minors (< 18)**: Cannot work Sundays
2. **TAs**: Never work weekends (only nights)
3. **Azubis**: Never work nights alone (except Sun→Mon, Mon→Tue where TA present)
4. **nd_alone=False**: Must be paired on regular nights
5. **nd_alone=True**: Cannot work Sun→Mon or Mon→Tue (would be paired with TA)
6. **Block limit**: Max 1 consecutive shift block per 14-day rolling window
7. **Night/Day conflict**: No day shift on same or next day after night shift
8. **nd_count**: Max consecutive nights per staff member's preference
9. **nd_exceptions**: Respect weekday exclusions per staff member

## Soft Constraints (Optimize)

1. **Proportional distribution**: Notdienste proportional to contracted hours
2. **FTE-normalized fairness**: Within each role group (TFA/Azubi/TA), FTE-scaled workload should be equal (±1 tolerance)
3. **Effective nights**: Paired nights count as 0.5× per person (shared workload)
4. **Minor compensation**: Minors get more Saturdays (can't work Sundays)

## Staff Data Model

```python
Staff:
    name: str              # Full name
    identifier: str        # Short code (e.g., "Jul", "AA")
    adult: bool            # True if ≥18 years
    hours: int             # Weekly contracted hours (18-40)
    beruf: Beruf           # TFA, Azubi, or TA
    reception: bool        # Can work reception/Anmeldung
    nd_possible: bool      # Can do night shifts at all
    nd_alone: bool         # Can work nights solo (False = must pair)
    nd_count: list[int]    # Allowed consecutive night counts [1], [2], [1,2], etc.
    nd_exceptions: list[int]  # Weekdays excluded from nights (1=Mon, 7=Sun)
```

## Solver Requirements

### Primary: CP-SAT (OR-Tools)
- Constraint programming for guaranteed optimal fairness
- Models all hard constraints explicitly
- Minimizes max FTE-deviation within role groups
- Recommended for production use

### Fallback: Heuristic
- Greedy assignment + local search (simulated annealing)
- Faster but cannot guarantee optimal fairness
- Useful for quick iterations during development

## UI Requirements (German)

| Page | Purpose |
|------|---------|
| Laden / CSV | Upload staff data CSV |
| Personal | View/filter staff by role, age, capabilities |
| Regeln | Display constraint rules |
| Plan erstellen | Configure solver, generate schedule |
| Plan anzeigen | View calendar, fairness stats, validation |
| Export | Download CSV or Excel |

## Acceptance Criteria

1. ✅ `streamlit run app/streamlit_app.py` launches app
2. ✅ Can generate Q2/2026 schedule from staff_sample.csv
3. ✅ Lists hard constraint violations when unsatisfiable
4. ✅ Shows fairness metrics and penalty breakdown
5. ✅ All hard constraints satisfied (0 violations)
6. ✅ FTE-normalized fairness within ±1 for groups with uniform availability

## Dependencies

**Runtime**: `streamlit`, `pandas`, `pydantic`, `python-dateutil`, `xlsxwriter`, `ortools`

**Development**: `pytest`, `ruff`, `pylint`, `mypy`

## Future Enhancements

- [ ] Vacation/availability import
- [ ] Manual schedule overrides with re-solve
- [ ] Azubi school-day constraints
- [ ] Multi-quarter planning
