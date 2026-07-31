# Code Audit Report Entry

## Review — [YYYY-MM-DD HH:MM:SS ±HH:MM]

**Scope:** [commit/branch/files reviewed]  
**Reviewer:** [agent/person]  
**Methods:** [tests, static checks, dependency review, manual paths]

## Executive Summary

- **P0 — Critical:** [count]
- **P1 — High:** [count]
- **P2 — Medium:** [count]
- **P3 — Low:** [count]
- **Validation gaps:** [short summary]

State whether the reviewed code is suitable for its intended deployment, with the conditions or blockers.

## Findings

### P0 — Critical: Security, privacy, integrity, or release blockers

| ID | Location | Finding | Evidence and impact | Recommended fix | Validation |
| --- | --- | --- | --- | --- | --- |
| P0-001 | [path:line] | [title] | [reproduction or code path] | [minimal safe remediation] | [test/check] |

### P1 — High: Incorrect implementation or material requirement failure

| ID | Location | Finding | Evidence and impact | Recommended fix | Validation |
| --- | --- | --- | --- | --- | --- |
| P1-001 | [path:line] | [title] | [reproduction or violated invariant] | [minimal remediation] | [test/check] |

### P2 — Medium: Robustness, scalability, operability, or user experience

| ID | Location | Finding | Evidence and impact | Recommended fix | Validation |
| --- | --- | --- | --- | --- | --- |
| P2-001 | [path:line] | [title] | [failure mode or affected users] | [practical remediation] | [test/check] |

### P3 — Low: Maintainability, code smell, or outdated documentation

| ID | Location | Finding | Evidence and impact | Recommended fix | Validation |
| --- | --- | --- | --- | --- | --- |
| P3-001 | [path:line] | [title] | [why it impedes maintenance] | [cleanup] | [test/check] |

## Checks Performed

| Area | Result | Notes |
| --- | --- | --- |
| Secrets and credentials | [pass/fail/not run] | |
| Dependency and supply-chain risk | [pass/fail/not run] | |
| Authentication, authorization, and data exposure | [pass/fail/not applicable] | |
| Input, file, and export handling | [pass/fail/not applicable] | |
| Core business invariants | [pass/fail/not run] | |
| Error handling and recovery | [pass/fail/not run] | |
| Tests and regression coverage | [pass/fail/not run] | |
| Documentation and configuration | [pass/fail/not run] | |

## Not Verified / Residual Risk

- [Unexecuted check, missing environment, or assumption.]
