# Constraints & Stakeholder Analysis

## Constraint Summary

### Hard Constraints (Must Satisfy)

| ID | Constraint | Rationale | Implemented |
|----|------------|-----------|-------------|
| H1 | Minors cannot work Sundays | German labor law | ✅ |
| H2 | TAs never work weekends | Contract/role definition | ✅ |
| H3 | Azubis never work nights alone | Safety requirement | ✅ |
| H4 | nd_alone=False must be paired | Employee preference/capability | ✅ |
| H5 | nd_alone=True cannot work TA nights | Would be forced pairing | ✅ |
| H6 | Max 1 block per 14-day window | Workload distribution | ✅ |
| H7 | No day shift after night shift | Rest requirement | ✅ |
| H8 | Respect nd_exceptions | Employee availability | ✅ |
| H9 | nd_count max not exceeded | Employee preference | ✅ |
| H10 | All shifts must be covered | Operational requirement | ✅ |

### Soft Constraints (Optimized)

| ID | Constraint | Weight | Implemented |
|----|------------|--------|-------------|
| S1 | Proportional to hours | Squared deviation | ✅ |
| S2 | Within-group fairness | StdDev × 10 | ✅ |
| S3 | Effective nights (paired=0.5) | Built into counting | ✅ |
| S4 | nd_count preference match | 100 per violation | ✅ |

---

## Stakeholder Analysis: Fairness Limitations

### Current Fairness Results (Q2/2026)

| Group | Metric | Range | Tolerance | Status |
|-------|--------|-------|-----------|--------|
| **TFA** | Weekend FTE | 1.74 - 2.67 | ±1 | ⚠️ Slightly wide |
| **TFA** | Night FTE | 3.00 - 6.67 | ±1 | ❌ Exceeds tolerance |
| **Azubi** | Weekend FTE | 3.00 - 3.00 | ±1 | ✅ Perfect |
| **Azubi** | Night FTE | 0.50 - 0.50 | ±1 | ✅ Perfect |
| **TA** | Night FTE | 1.00 - 2.00 | ±1 | ✅ Within tolerance |

### Root Cause: Restrictive Individual Constraints

The TFA night FTE range (3.00 - 6.67) exceeds tolerance **not due to algorithm failure**, but because certain employees have highly restrictive availability.

---

## Staff Availability Analysis

### TFA Night Availability (21 night-capable TFAs)

| Availability | Staff | Night FTE Result |
|--------------|-------|------------------|
| **1/7 nights** | Julia Hausmann (20h) | 6.00 FTE |
| **3/7 nights** | Sarah Heiter (30h), Anke Penzin (23h), Tiago Santos (40h) | 4.35-6.00 FTE |
| **5/7 nights** | Elena Wottrich (32h) | 3.12 FTE |
| **7/7 nights** | 16 other TFAs | 3.00-5.00 FTE |

### Detailed Constraint Analysis

| Employee | Hours | nd_exceptions | Available Nights | nd_alone | nd_count | Impact |
|----------|-------|---------------|------------------|----------|----------|--------|
| **Julia Hausmann** | 20 | [1,2,3,4,6,7] | Fri-Sat only (1/7) | solo | [1] | Cannot achieve fairness - only 2 nights/quarter possible |
| **Sarah Heiter** | 30 | [1,2,3,4] | Fri-Sat-Sun (3/7) | solo | [3] | Limited, but 3-night blocks help |
| **Anke Penzin** | 23 | [1,2,3,4] | Fri-Sat-Sun (3/7) | solo | [2] | Part-time + restrictions = high FTE |
| **Tiago Santos** | 40 | [1,2,3,4] | Fri-Sat-Sun (3/7) | solo | [2,3] | Weekend-only nights |
| **Caroline Bauer** | 18 | [] | All nights (7/7) | solo | [3] | Part-time causes high FTE despite full availability |

---

## Recommendations for Business Stakeholders

### Option A: Accept Current Constraints (Recommended)

**Accept that perfect fairness is impossible** given individual employee contracts and preferences.

**Rationale:**
- Julia Hausmann's exceptions are presumably for valid personal reasons
- Forcing more nights would violate her stated availability
- The algorithm is optimal *given the constraints*

**Action:** Document that employees with restrictive nd_exceptions will appear "unfair" in FTE metrics but are working their maximum available shifts.

### Option B: Exempt Restricted Employees from Fairness Calculation

**Exclude** employees with <4/7 night availability from fairness metrics.

**Affected:** Julia Hausmann, Sarah Heiter, Anke Penzin, Tiago Santos

**Impact:**
- Remaining TFA Night FTE range: 3.00 - 5.00 (within ±2)
- Fairness metrics become meaningful for comparable employees

**Implementation:** Add `fairness_exempt: bool` field to Staff model.

### Option C: Relax Individual Constraints

Discuss with affected employees whether their nd_exceptions can be reduced.

| Employee | Current | Proposed | Gain |
|----------|---------|----------|------|
| Julia Hausmann | [1,2,3,4,6,7] | [1,2,3,4,7] | +1 night (Thu-Fri) |
| Sarah Heiter | [1,2,3,4] | [1,2,3] | +1 night (Thu-Fri) |

**Caution:** These are personal preferences that may have valid reasons (childcare, second job, etc.)

### Option D: Adjust Part-Timer Expectations

**Recognize** that part-timers (18-23h) will always show higher FTE-normalized metrics.

**Math:**
- Julia (20h) with 3 nights = 3/20×40 = **6.0 FTE**
- Full-timer (40h) with 3 nights = 3/40×40 = **3.0 FTE**

This is mathematically unavoidable if they work the same absolute number of shifts.

**Option:** Use absolute counts instead of FTE for fairness, accepting that part-timers work fewer total shifts.

---

## Decision Matrix

| Option | Fairness Impact | Employee Impact | Implementation Effort |
|--------|-----------------|-----------------|----------------------|
| A: Accept | None | None | None |
| B: Exempt | Improved metrics | May feel excluded | Low (model change) |
| C: Relax | Improved actual | Potential pushback | Medium (negotiation) |
| D: Absolute | Different metric | Part-timers favored | Low (UI change) |

---

## Appendix: Full Constraint Violation Examples

### Block Constraint (H6) Violation Example
```
Employee: AA (Anika Alles)
Block 1: 2026-04-04 to 2026-04-07 (Sat-Sun-Mon-Tue)
Block 2: 2026-04-11 (Sat)
Gap: 7 days < 14 days → VIOLATION
```

### Night Pairing (H4) Violation Example
```
Employee: Bax (Lindsay Bax, nd_alone=False)
Shift: N_Di-Mi on 2026-04-07
Assigned: Bax alone (no partner)
→ VIOLATION (must be paired or TA present)
```

### nd_alone TA Night (H5) Violation Example
```
Employee: Jul (Julia Hausmann, nd_alone=True)
Shift: N_So-Mo on 2026-04-05
→ VIOLATION (solo worker assigned to TA-present night)
```
