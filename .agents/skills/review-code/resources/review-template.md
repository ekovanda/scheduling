# Code Review: [Feature / Scope Title]

- **Date**: `YYYY-MM-DD`
- **Last Commit ID**: `<short-hash>` (`<full-hash>`)
- **Commits Covered**: `<base-hash>..<head-hash>` ([count] commits: list short hashes & subjects, plus working-tree status)
- **Reference PRD**: `[documentation/PRD_...md or N/A]`
- **Model Name**: `[Model Name]`
- **Reviewed Scope**: `[files, directories, or feature scope]`

---

## Executive Overview (Plain-Language Summary)

[2–4 sentences explaining in plain, non-jargon language what this feature or code area does for the clinic scheduling system, how well it meets its PRD requirements, and the key takeaways from this review.]

### Summary of Findings

| ID | Status | Category | Title | File & Lines | Severity | Complexity |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **A1** | `[ ]` | Critical Security | [Short title] | `path/to/file.py:L10-L25` | [Critical/High/Medium/Low] | [Low/Medium/High] |
| **B1** | `[ ]` | Functionality & Bugs | [Short title] | `path/to/file.py:L40-L62` | [Critical/High/Medium/Low] | [Low/Medium/High] |

---

## PRD Conformance Summary

| PRD Requirement / Acceptance Criterion | Status | Notes / Finding Ref |
| :--- | :--- | :--- |
| [Requirement 1] | [Met / Partial / Missing] | [e.g., Verified in `solver_cpsat.py` or see `B1`] |

---

## A. Critical Security

### A1 — [Short Descriptive Title]
- **Status**: [ ] Open
- **Filename & Lines**: `path/to/file.py` (Lines `X–Y`)
- **Issue Description**:
  - *Context*: [Plain-language explanation of what this part of the application does.]
  - *Details*: [Technical explanation of the vulnerability, exposure, or missing safeguard.]
- **Impact Assessment**: **[Critical | High | Medium | Low]** — [Concrete consequence if triggered or exploited.]
- **Remediation Approach**: [Actionable, minimal steps to resolve the issue.]
- **Remediation Complexity**: **[Low | Medium | High]** — [1-sentence rationale.]

---

## B. Functionality & Bugs

### B1 — [Short Descriptive Title]
- **Status**: [ ] Open
- **Filename & Lines**: `path/to/file.py` (Lines `X–Y`)
- **Issue Description**:
  - *Context*: [Plain-language explanation of the scheduling rule or user workflow.]
  - *Details*: [How the code deviates from the PRD, solver/validator parity, or edge case behavior.]
- **Impact Assessment**: **[Critical | High | Medium | Low]** — [Effect on generated schedules, fairness, validation, or exports.]
- **Remediation Approach**: [Concrete fix steps and regression test to add.]
- **Remediation Complexity**: **[Low | Medium | High]** — [1-sentence rationale.]

---

## C. Scalability & Efficiency

### C1 — [Short Descriptive Title]
- **Status**: [ ] Open
- **Filename & Lines**: `path/to/file.py` (Lines `X–Y`)
- **Issue Description**:
  - *Context*: [Plain-language explanation of when and how often this runs.]
  - *Details*: [Solver complexity growth, redundant API calculation, or resource bound issue.]
- **Impact Assessment**: **[Critical | High | Medium | Low]** — [User-perceived latency, solver timeout risk, or memory growth.]
- **Remediation Approach**: [Concrete optimization or bound to introduce.]
- **Remediation Complexity**: **[Low | Medium | High]** — [1-sentence rationale.]

---

## D. Simplicity

### D1 — [Short Descriptive Title]
- **Status**: [ ] Open
- **Filename & Lines**: `path/to/file.py` (Lines `X–Y`)
- **Issue Description**:
  - *Context*: [What the code is accomplishing in the scheduling workflow.]
  - *Details*: [Why the current approach is over-engineered or harder to follow than necessary.]
- **Impact Assessment**: **[Low | Medium]** — [Cognitive load or risk of subtle bugs during future changes.]
- **Remediation Approach**: [How to flatten or simplify the logic.]
- **Remediation Complexity**: **[Low | Medium | High]** — [1-sentence rationale.]

---

## E. Maintainability

### E1 — [Short Descriptive Title]
- **Status**: [ ] Open
- **Filename & Lines**: `path/to/file.py` (Lines `X–Y`)
- **Issue Description**:
  - *Context*: [How this module connects to the rest of the application.]
  - *Details*: [Duplication across solver/validator, typing gap, exception handling, or missing test coverage.]
- **Impact Assessment**: **[Low | Medium | High]** — [Risk of regression when modifying scheduling rules or UI.]
- **Remediation Approach**: [Specific refactoring, typing, or test addition.]
- **Remediation Complexity**: **[Low | Medium | High]** — [1-sentence rationale.]

---

## F. Documentation Correctness

### F1 — [Short Descriptive Title]
- **Status**: [ ] Open
- **Filename & Lines**: `path/to/doc_or_code.md` (Lines `X–Y`)
- **Issue Description**:
  - *Context*: [What the documentation states vs. how the app actually behaves.]
  - *Details*: [Exact discrepancy in `CONSTRAINTS.md`, `ARCHITECTURE.md`, `README.md`, or docstrings.]
- **Impact Assessment**: **[Low | Medium]** — [How this could mislead a developer, reviewer, or clinic user.]
- **Remediation Approach**: [Exact text or section to update.]
- **Remediation Complexity**: **[Low | Medium | High]** — [1-sentence rationale.]

---

## Checks Performed & Residual Risk

| Check / Review Area | Result | Notes |
| :--- | :--- | :--- |
| Automated Tests (`uv run pytest`) | [Pass / Fail / Not Run] | |
| Linter (`uv run ruff check .`) | [Pass / Fail / Not Run] | |
| Type Check (`uv run mypy .`) | [Pass / Fail / Not Run] | |
| Security & Input Handling | [Pass / Issues Found / N/A] | |
| Solver ↔ Validator ↔ Export Parity | [Pass / Issues Found / N/A] | |

### Observations & Not Verified
- [Non-defect observations, unexecuted checks, or residual risks.]

