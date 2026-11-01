# Constraints & Stakeholder Analysis

## Constraint Summary

### Hard Constraints (Must Satisfy)

| ID | Constraint | Rationale |
|----|------------|-----------|
| H1 | Minors cannot work Sundays | German labor law |
| H2 | Interns work only dedicated `Sa_Intern` / `So_Intern` weekends; non-interns forbidden on them | Contract/role definition |
| H3 | Azubis must pair with non-Azubi on nights | Safety requirement |
| H4 | Two Azubis can never pair on nights (max 1 Azubi per night) | Supervision requirement |
| H5 | nd_alone=False must be paired (on closed nights) | Employee capability |
| H6 | nd_alone=True must work **completely alone** on closed nights (may pair on open nights) | Employee preference & clinic status |
| H7 | Min consecutive nights per employee (`nd_min_consecutive`) | Block scheduling |
| H8 | Max 1 block per **21-day** window (TFA/Azubi); **10 days** for Interns; **7 days** for holiday-forced blocks | Workload distribution |
| H9 | No day shift on same day or next day after night shift | Rest requirement |
| H10 | Respect `nd_exceptions` weekday exclusions | Employee availability |
| H11 | All shifts must be covered (regular weekends 1; open nights 2; closed nights 1–2) | Operational requirement |
| H12 | At least 1 non-Azubi per night | Supervision requirement |
| H13 | Max 1 shift per person per day | Workload limit |
| H14 | Open Nights (Sun-Mon, Mon-Tue): Headcount exactly 2, with at least 1 TFA mandatory | Clinic in operation |
| H15 | Weekend shifts isolated (no adjacent shift day before or after) | Prevents fatigue |
| H16 | Sa 10-22, So 8-20, So 10-22: TFA only; So 8-20:30: adult Azubi only | Role eligibility |
| H17 | Abteilung (op/station) cannot work same night | Capacity protection |
| H18 | Abteilung (op/station) cannot work consecutive nights | Capacity protection |
| H19 | Vacation dates block all shift types | Planned absence |
| H20 | Birthday blocks all shift types (treated identically to H19) | Employee wellbeing |
| H21 | TFA and Azubi must work ≥1 weekend shift per quarter | Participation fairness |
| H22 | Night-eligible staff must work ≥1 night shift per quarter (viability-exempt) | Participation fairness |
| H23 | Interns must work 6–9 night shifts per quarter (≈2–3/month) | Contract/role definition |
| H24 | `available_from` blocks all shifts before employee start date | New-hire absence |
| H-INT-1 | Intern weekend coupling: `Sa_Intern` and `So_Intern` must be assigned as a pair to the same Intern | Fair and contiguous weekend rest |
| H-INT-2 | Max 1 Intern weekend block per calendar month | Workload distribution |
| H-INT-3 | Weekend vacation guard: vacation on Sat or Sun blocks both days for Intern | Contiguous rest |
| H-VET-1 | Vet midweek blocks: strictly exact 2-night blocks (`Di+Mi` or `Mi+Do`) in `N_Di-Mi`, `N_Mi-Do`, `N_Do-Fr` | Clinically viable relief blocks |
| H-VET-2 | Vet solo duty: Headcount = exactly 1 on Vet nights (no TFA, Intern, or Azubi) | Vet-only night shift |
| H-VET-3 | Vet frequency: Max 1 block per 2 consecutive calendar months | Sustainable relief rotation |
| H-VET-4 | Vet cross-quarter lockout: duty in last month of previous quarter blocks month 1 of next quarter | Respects 2-month boundary |
| H-VET-5 | Vet exclusions: Excluded from TFA/Azubi FTE fairness and minimum participation | Voluntary auxiliary relief |

> **H8 relaxation**: When a block is forced by a pre-assigned holiday shift, the required gap drops
> from 21 days to 7 days for that block only.
>
> **H22 exemption**: The night-participation constraint is only added when the employee has enough
> remaining (non-vacation, non-exception) night slots to form ≥3 valid consecutive blocks of
> `nd_min_consecutive` length. Below that threshold the solver relies on the fairness objective.

### Constraint Enforcement: Solver vs Validator

The CP-SAT solver enforces all hard constraints during solving. The post-solve validator
(`validator.py`) re-checks them on the extracted schedule. One deliberate exception:

- **`nd_max_consecutive`** is enforced as a **hard constraint in the solver** (sliding-window sum
  on night variables). The validator does *not* flag it as a hard violation; instead it adds
  **100 soft-penalty points per violation** via `_calculate_soft_penalty`. This catches violations
  only in externally-imported or manually-edited schedules.

### Soft Constraints & Optimization Objectives

| ID | Constraint | Mechanism |
|----|------------|-----------|
| O1 | Maximale Vet-Entlastung (Highest Priority) | Objective term: $-100\,000 \cdot \sum b$ (maximizes midweek TFA relief) |
| O2 | Cross-Quarter Boundary Block-Gap Soft Penalty | Near-hard penalty: `gap_diff × 10,000,000` |
| S1 | Proportional to hours AND presence (vacation-adjusted) | FTE-normalization in objective |
| S2 | Within-group fairness for combined Notdienste (TFA / Azubi / Intern) | **Hard ceiling**: range ≤ 1.5 FTE-units; **Soft**: minimize range |
| S3 | Effective nights weighting | Open nights: TFA=0.5, Intern=1.0, Azubi=1.0. Closed nights: paired TFA/Intern=0.5, solo=1.0, Azubi=1.0 |
| S4 | `nd_max_consecutive` not exceeded | Hard in solver; +100 pts/violation in validator |
| S5 | Night-shift type balance within groups (secondary objective) | Minimize FTE-scaled night range |
| S6 | Cross-quarter carry-forward: compensate prior-quarter imbalance | Per-person delta offset on fairness variable |
| S7 | Intern weekend fairness (Track 2) | Objective term: $300 \cdot (\max_i w_i - \min_i w_i)$ (balanced weekend rotation $\le 1$) |
| S8 | Vet block fairness | Objective term: $500 \cdot (\max_v b_v - \min_v b_v)$ |

---

## Staff Data Model

```python
class Staff:
    name: str              # Full name
    identifier: str        # Short code (e.g., "Jul", "AA", "TA_MUE")
    adult: bool            # True if 18 years old
    hours: int             # Weekly contracted hours (18-40; 0 for Vet)
    beruf: Beruf           # TFA, Azubi, Intern, or Vet
    abteilung: Abteilung   # station, op, or other
    reception: bool        # Can work reception/Anmeldung (Sa 10-21 eligibility)
    nd_possible: bool      # Can do night shifts at all
    nd_alone: bool         # True = must work completely alone; False = must be paired
    nd_max_consecutive: int | None  # Hard limit on consecutive nights (2 for Vet)
    nd_min_consecutive: int  # Min consecutive nights per block (2 for Vet)
    nd_exceptions: list[int]  # Weekdays blocked for nights (1=Mon, 7=Sun)
    birthday: str | None   # Birthday in MM-DD format (no year), e.g. "04-15"
    available_from: date | None  # First schedulable date (new employees; None = full quarter)
```

### nd_min_consecutive Field

| Beruf | Default Value | Description |
|-------|---------------|-------------|
| Azubi | 1 | Single nights allowed (always paired anyway) |
| TFA | 2 | Must work at least 2 consecutive nights |
| Intern | 2 | Must work at least 2 consecutive nights |
| Vet | 2 | Must work exactly 2 consecutive nights (Di+Mi or Mi+Do) |
| Special (e.g., Anika Alles) | 3 | Must work at least 3 consecutive nights |

### Vacation / Unavailability

### Birthday Unavailability

Each `Staff` record has an optional `birthday` field in `MM-DD` format. When set, the employee's
birthday is treated exactly like a vacation day: no shift of any type can be assigned to them on
that date. The year is resolved per-quarter at solve time.

**Behavior matches H19**: the birthday date is injected into the per-staff blocked-date set
before decision variables are built, so the constraint is enforced at the variable-creation
level rather than as an explicit model constraint.

---

### Vacation / Unavailability (CSV)

Vacation data is stored in a separate CSV file (`data/vacations.csv`):

```csv
identifier,start_date,end_date
AA,2026-04-13,2026-04-24
Jul,2026-05-18,2026-05-22
```

- **identifier**: Staff member short code (must match staff_sample.csv)
- **start_date**: First day of vacation (YYYY-MM-DD format)
- **end_date**: Last day of vacation, inclusive (YYYY-MM-DD format)

### Behavior

1. **Shift Blocking**: Staff on vacation cannot be assigned to ANY shift on vacation dates
2. **Fairness Adjustment**: Expected Notdienste are scaled by presence ratio:
   - `expected_shifts = base_shifts * (hours/40) * (available_days/total_days)`
3. **Solver Failure**: If vacation makes coverage impossible, the solver fails with diagnostic info

---

## Key Constraint Details

### nd_alone Behavior

- **nd_alone=True**: Staff MUST work **completely alone** on regular nights (Tue-Wed through Sat-Sun)
- **nd_alone=False**: Staff MUST be paired with another person on regular nights
- **Sun-Mon / Mon-Tue**: Vet is on-site, so nd_alone rules do not apply

### Minimum Participation (H21, H22, H23)

To prevent scenarios where some employees do all nights and others do all weekends:

- **Weekend Participation (H21)**: All TFA and Azubi must work at least 1 weekend shift per quarter.
- **Night Participation (H22)**: All staff with `nd_possible=True` must work at least 1 night shift
  per quarter. **Exception**: Only enforced when remaining available night slots can form ≥3
  consecutive blocks of `nd_min_consecutive` length (viability guard).
- **Intern Night Cap (H23)**: Interns must work exactly 6–9 nights per quarter (enforced as a
  hard range constraint in the solver).

### Type Balance Objective (S5)

Secondary soft objective that minimizes the **FTE-scaled min-max range** of night-shift counts
among night-eligible staff within each group (TFA, Azubi). This complements S2 by discouraging
scenarios where one person does 0 nights + many weekends while a colleague does the opposite.
Weighted lower than S2.

### Abteilung Night Constraint

To prevent capacity shortages in specialized departments:
1. **Same night**: Two staff from the same abteilung (op or station) cannot work the same night
2. **Consecutive nights**: Two staff from same abteilung cannot work consecutive calendar days

**Exempt**: Staff with abteilung=other are not subject to these constraints.

---

## Fairness Calculation

### Two Fairness Systems

There are two independent fairness mechanisms with different formulas:

| System | Where | Formula | Purpose |
|--------|-------|---------|--------|
| **CP-SAT objective** | solver_cpsat.py | Minimize min-max range of FTE-scaled counts | Drives the solver toward fair solutions |
| **Validator score** | validator.py `_calculate_soft_penalty` | Σ(actual−target)² + std_dev×10 per group + 100 per nd_max violation | Post-solve diagnostic score |

These two systems coexist. The solver's objective is what actually shapes the schedule;
the validator score is displayed in the UI for review.

### CP-SAT Presence-Adjusted FTE Normalization

Fairness is calculated **per job group** (TFA, Azubi, Intern) with adjustments for:

1. **Working Hours**: 20h employee expected to do half the shifts of a 40h employee.
2. **Vacation/Presence**: Employee with 2 weeks vacation expected to do proportionally fewer shifts.
3. **Carry-forward**: Prior-quarter imbalance shifts each person's effective FTE score by their
   `carry_forward_delta`, so the solver compensates historical over/under-allocation.

Formula: `FTE_adjusted = count × (40/hours) × (total_days/available_days) + carry_forward_delta`

The solver uses integer arithmetic; counts are tracked in **half-units** (1 Notdienst = 2 units)
to represent the 0.5 weight for paired TFA/Intern nights without fractions.

Hard ceiling in solver: `(max_fte − min_fte) ≤ 1.5` per group (widened when carry-forward deltas
are active to avoid infeasibility from historical spread).

### Eligibility Exemptions

Staff may be exempt from certain participation requirements:

| Condition | Weekend Exempt | Night Exempt |
|-----------|----------------|--------------|
| Intern |  |  |
| nd_possible=False |  |  |
| Available night types < nd_min_consecutive |  |  |

---

## Appendix: Constraint Violation Examples

### Vacation Conflict
```
Staff: AA (Anika Alles)
Vacation: 2026-04-13 to 2026-04-24
Attempted Assignment: N_Di-Mi on 2026-04-14
 BLOCKED (staff on vacation)
```

### nd_min_consecutive Violation
```
Staff: AA (Anika Alles, nd_min_consecutive=3)
Assigned: N_Di-Mi (2026-04-07), N_Mi-Do (2026-04-08)
 VIOLATION (only 2 consecutive, requires 3)
```

### Minimum Participation Violation
```
Staff: CB (Caroline Bauer, nd_possible=True)
Quarter assignments: 5 weekend shifts, 0 night shifts
 VIOLATION (must work at least 1 night shift)
```
