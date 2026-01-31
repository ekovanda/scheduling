# Constraints & Stakeholder Analysis

## Constraint Summary

### Hard Constraints (Must Satisfy)

| ID | Constraint | Rationale | Implemented |
|----|------------|-----------|-------------|
| H1 | Minors cannot work Sundays | German labor law | ✅ |
| H2 | Interns never work weekends | Contract/role definition | ✅ |
| H3 | Azubis must pair with non-Azubi on nights | Safety requirement | ✅ |
| H4 | Two Azubis can never pair on nights | Supervision requirement | ✅ |
| H5 | nd_alone=False must be paired (regular nights) | Employee capability | ✅ |
| H6 | nd_alone=True must work **completely alone** (regular nights) | Employee preference | ✅ |
| H7 | Non-Azubis min 2 consecutive nights | Block scheduling | ✅ |
| H8 | Max 1 block per 14-day window | Workload distribution | ✅ |
| H9 | No day shift after night shift | Rest requirement | ✅ |
| H10 | Respect nd_exceptions | Employee availability | ✅ |
| H11 | All shifts must be covered | Operational requirement | ✅ |
| H12 | At least 1 non-Azubi per night | Supervision requirement | ✅ |
| H13 | Max 1 shift per person per day | Workload limit | ✅ |
| H14 | Sun-Mon/Mon-Tue: exactly 1 non-Azubi + optional Azubi | Vet on-site requirement | ✅ |
| H15 | Weekend shifts isolated (not in blocks) | Prevents fatigue | ✅ |
| H16 | Sa 10-22, So 8-20, So 10-22: TFA only | Role eligibility | ✅ |
| H17 | Abteilung (op/station) cannot work same night | Capacity protection | ✅ |
| H18 | Abteilung (op/station) cannot work consecutive nights | Capacity protection | ✅ |

### Soft Constraints (Optimized)

| ID | Constraint | Weight | Implemented |
|----|------------|--------|-------------|
| S1 | Proportional to hours | Squared deviation | ✅ |
| S2 | Within-group fairness (combined Notdienste) | StdDev × 10 | ✅ |
| S3 | Effective nights (TFA/Intern: paired=0.5, Azubi: always 1.0) | Built into counting | ✅ |
| S4 | nd_max_consecutive not exceeded | 100 per violation | ✅ |

---

## Staff Data Model

```python
class Staff:
    name: str              # Full name
    identifier: str        # Short code (e.g., "Jul", "AA")
    adult: bool            # True if ≥18 years
    hours: int             # Weekly contracted hours (18-40)
    beruf: Beruf           # TFA, Azubi, or Intern
    abteilung: Abteilung   # station, op, or other (NEW)
    reception: bool        # Can work reception/Anmeldung
    nd_possible: bool      # Can do night shifts at all
    nd_alone: bool         # Must work alone on regular nights
    nd_max_consecutive: int | None  # Max consecutive nights (soft limit)
    nd_exceptions: list[int]  # Weekdays excluded (1=Mon, 7=Sun)
```

### Abteilung Enum

| Value | Description | Constraint |
|-------|-------------|------------|
| `station` | Station/Ward staff | Cannot pair with other station staff on nights |
| `op` | Operating room staff | Cannot pair with other OP staff on nights |
| `other` | General/unassigned | **Exempt** from abteilung constraints |

---

## Key Constraint Details

### nd_alone Behavior

- **nd_alone=True**: Staff MUST work **completely alone** on regular nights (Tue-Wed through Sat-Sun). No pairing allowed.
- **nd_alone=False**: Staff MUST be paired with another person on regular nights.
- **Sun-Mon / Mon-Tue**: Vet is on-site, so nd_alone rules don't apply. Exactly 1 non-Azubi required, optional Azubi.

### Azubi Effective Nights

Azubis **always count as 1.0 effective night**, even when paired. This ensures fairness tracking reflects their full participation, since they cannot lead a shift.

### Weekend Isolation

Weekend shifts (Sa/So) must always be **single-shift blocks** — they cannot be adjacent to any other shift for the same person. This prevents weekend shifts from being part of multi-day fatigue blocks.

### Abteilung Night Constraint

To prevent capacity shortages in specialized departments:
1. **Same night**: Two staff from the same `abteilung` (op or station) cannot work the same night shift
2. **Consecutive nights**: Two staff from the same `abteilung` cannot work on consecutive calendar days (e.g., if Alice from OP works Monday night, Bob from OP cannot work Tuesday night)

**Exempt**: Staff with `abteilung=other` are not subject to these constraints.

---

## Stakeholder Analysis: Fairness Limitations

### Fairness Calculation

Fairness is now calculated **per job group** (TFA, Azubi, Intern) rather than globally:
- Threshold for unfair: ≥2 normalized shifts deviation from group mean
- Color coding: Green (underburdened), Yellow (normal), Red (overburdened)

### Root Cause: Restrictive Individual Constraints

High FTE variance within groups is often caused by:
1. **nd_exceptions**: Employees available only on certain weekdays
2. **Part-time hours**: Same absolute shifts = higher FTE-normalized count
3. **nd_alone restrictions**: Solo workers have fewer pairing options

---

## Recommendations for Business Stakeholders

### Option A: Accept Current Constraints (Recommended)

**Accept that perfect fairness is impossible** given individual employee contracts and preferences.

### Option B: Exempt Restricted Employees

Exclude employees with <4/7 night availability from fairness metrics.

### Option C: Use Absolute Counts

Display absolute shift counts instead of FTE-normalized values for part-timers.

---

## Appendix: Constraint Violation Examples

### Abteilung Same Night Violation
```
Staff: SH (Sabrina Hafer, abteilung=op)
Staff: JH (Jacqueline Hülsmann, abteilung=op)
Shift: N_Di-Mi on 2026-04-07
→ VIOLATION (two OP staff on same night)
```

### Abteilung Consecutive Days Violation
```
Staff: LB (Lisanne Bayerl, abteilung=station) on N_Di-Mi (2026-04-07)
Staff: SG (Stefanie Gelhardt, abteilung=station) on N_Mi-Do (2026-04-08)
→ VIOLATION (two station staff on consecutive nights)
```

### nd_alone Improper Pairing Violation
```
Employee: Jul (Julia Hausmann, nd_alone=True)
Shift: N_Di-Mi on 2026-04-07
Assigned with: AA (Anika Alles)
→ VIOLATION (nd_alone=True must work completely alone on regular nights)
```
