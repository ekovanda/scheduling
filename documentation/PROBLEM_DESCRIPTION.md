# Notdienst Scheduling - Problem Description

## Goal

Implement a quarterly Streamlit scheduling app that produces **fair, rules-compliant** Notdienst (weekend + night shift) schedules for a veterinary clinic with ~24 TFAs, ~11 Azubis, and 4 Interns.

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
| Sa_10-21 | 10:00-21:00 | Azubi (reception=true) or TFA (Anmeldung) |
| Sa_10-22 | 10:00-22:00 | **TFA only** (Rufbereitschaft) |
| Sa_10-19 | 10:00-19:00 | Any Azubi (Azubidienst) |

### Sunday (3 shifts, 13 weeks = 39 total)
| Shift | Hours | Staffing Rule |
|-------|-------|---------------|
| So_8-20 | 08:00-20:00 | **TFA only** |
| So_10-22 | 10:00-22:00 | **TFA only** (Rufbereitschaft) |
| So_8-20:30 | 08:00-20:30 | Adult Azubi only (8-12 onsite, rest on-call) |

### Night Shifts (91 nights per quarter)
| Night | Staffing | Notes |
|-------|----------|-------|
| Sun→Mon | **Exactly 1** non-Azubi + optional Azubi | Vet on-site |
| Mon→Tue | **Exactly 1** non-Azubi + optional Azubi | Vet on-site |
| Other nights | 1-2 people | At least 1 non-Azubi, Azubi optional as 2nd |

## Hard Constraints (Must Satisfy)

1. **Minors (< 18)**: Cannot work Sundays
2. **Interns**: Never work weekends (only nights)
3. **Azubis**: Must always pair with TFA or Intern on nights
4. **Two Azubis**: Can never work together on any night
5. **Non-Azubis (TFA/Intern)**: Must work at least 2 consecutive nights
6. **nd_alone=False**: Must be paired on regular nights
7. **nd_alone=True**: Must work **completely alone** on regular nights (no pairing allowed)
8. **Block limit**: Max 1 consecutive shift block per 14-day rolling window
9. **Night/Day conflict**: No day shift on same or next day after night shift
10. **nd_max_consecutive**: Max consecutive nights per staff member (soft preference)
11. **nd_exceptions**: Respect weekday exclusions per staff member
12. **Weekend isolation**: Weekend shifts cannot be adjacent to other shifts
13. **Max 1 shift/day**: Each person can only work 1 shift per day
14. **Abteilung constraint**: Staff from same department (op/station) cannot work together or consecutively on nights

## Soft Constraints (Optimize)

1. **Proportional distribution**: Notdienste proportional to contracted hours
2. **FTE-normalized fairness**: Within each role group (TFA/Azubi/Intern), FTE-scaled combined workload (weekends + nights) should be equal (±2 tolerance)
3. **Effective nights**: 
   - TFA/Intern: Paired nights = 0.5× per person, solo nights = 1.0×
   - Azubi: Always 1.0× (even when paired)
4. **nd_max_consecutive**: Prefer not exceeding staff's max consecutive nights

## Staff Data Model

```python
Staff:
    name: str              # Full name
    identifier: str        # Short code (e.g., "Jul", "AA")
    adult: bool            # True if ≥18 years
    hours: int             # Weekly contracted hours (18-40)
    beruf: Beruf           # TFA, Azubi, or Intern
    abteilung: Abteilung   # station, op, or other (NEW)
    reception: bool        # Can work reception/Anmeldung
    nd_possible: bool      # Can do night shifts at all
    nd_alone: bool         # Must work alone on regular nights
    nd_max_consecutive: int | None  # Max consecutive nights allowed (soft)
    nd_exceptions: list[int]  # Weekdays excluded from nights (1=Mon, 7=Sun)
```

### Abteilung Values
| Value | Description | Night Constraint |
|-------|-------------|------------------|
| `station` | Ward/Station staff | Cannot pair with other station staff |
| `op` | Operating room staff | Cannot pair with other OP staff |
| `other` | General/unassigned | **Exempt** from abteilung constraint |

## Solver Requirements

### CP-SAT (OR-Tools)
- Constraint programming for guaranteed optimal fairness
- Models all hard constraints explicitly
- Minimizes max FTE-deviation within role groups
- Default time limit: 120 seconds

## UI Requirements (German)

| Page | Purpose |
|------|---------|
| Laden / CSV | Upload staff data CSV |
| Personal | View/filter staff by role, age, capabilities |
| Regeln | Display constraint rules |
| Plan erstellen | Configure solver, generate schedule |
| Plan anzeigen | View calendar, fairness stats (per job group), validation |
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
