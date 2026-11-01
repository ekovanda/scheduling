---
name: review-code
description: >-
  Conducts a thorough, evidence-based code review or security/quality audit and
  writes an untracked Markdown report named
  documentation/REVIEW_<YYYY-MM-DD>-<short-commit-hash>-<feature-slug>.md. Use
  when the user asks for a code review, feature review, PR/commit review,
  security audit, production-readiness assessment, or repository health check.
---

# Thorough Code Review (`review-code`)

Perform an evidence-based, reader-friendly code review that finds consequential defects before cosmetic concerns. Write the report so that someone unfamiliar with the internal implementation details of the codebase can easily understand what each part does and why an issue matters, while giving developers exact line numbers and actionable fixes.

> **Read-only rule**: Do not modify production or test code during a review unless the user explicitly asks to apply fixes.

---

## 1. Pre-Flight & Metadata Collection

1. **Identify Scope, Git Metadata & Feature Slug**:
   - Inspect `git log`, `git status`, and `pyproject.toml` to collect:
     - **Date**: Local date in `YYYY-MM-DD` format.
     - **Last Commit ID**: Short hash (`git rev-parse --short HEAD`) and full hash.
     - **Commits Covered**: Commit range (`<base>..<head>`) or list of commits reviewed, plus whether uncommitted working-tree changes are included.
     - **Feature Slug**: A short, lowercase, hyphenated identifier for the scope (e.g., `open-closed-nights`, `intern-weekend-shifts`, `full-repo`).
2. **Determine Model Name**:
   - Check if the active model name is known from the session context or user prompt.
   - **If the model name is not available or cannot be determined with certainty, ask the user to supply it before finalizing the report.**
3. **Determine Reference PRD (`documentation/PRD_*.md`)**:
   - Check `documentation/PRD_*.md` for a Product Requirements Document matching the reviewed feature or commits.
   - **If the matching PRD is obvious** from the branch, commit messages, or changed files, automatically compare the implementation against its acceptance criteria and requirements.
   - **If it is ambiguous which PRD applies** (and the review is for a feature rather than a general repo check), **ask the user to clarify which PRD should be used** (or whether to review without a PRD).
4. **Output Location (Untracked)**:
   - Save the report to: `documentation/REVIEW_<YYYY-MM-DD>-<short-commit-hash>-<feature-slug>.md`.
   - Verify with `git check-ignore -v` that the generated file is untracked by git.

---

## 2. Severity & Impact Policy

Use the highest severity level that the **demonstrated impact** warrants. Do not inflate theoretical issues, and do not downgrade credible security or data/schedule-integrity defects because a workaround exists:

| Severity | Priority Equivalent | Meaning & Typical Examples |
| :--- | :--- | :--- |
| **Critical** | **P0 — Blocker** | Credible security, privacy, safety, or schedule/data-integrity exposure; secret leakage; remotely exploitable vulnerability; authorization bypass; or a broken hard scheduling constraint that can produce an unsafe/invalid roster without warning. |
| **High** | **P1 — High** | Incorrect implementation of an explicit PRD requirement, business invariant, or supported workflow with material user impact (e.g., wrong carry-forward accounting, solver/validator disagreement, silent ignoring of valid input). |
| **Medium** | **P2 — Medium** | Foreseeable robustness, performance, scalability, operability, or UX failure that degrades normal use (e.g., unbounded file/solver workload, fragile parser edge case, expensive operation on every Streamlit rerun). |
| **Low** | **P3 — Low** | Maintainability, simplicity, readability, testability, or documentation drift with no immediate user-facing failure (e.g., dead code, duplicated logic, stale docs, missing edge-case test). |

If a note has no concrete defect or impact, record it under **Observations & Residual Risk**, not as a numbered finding.

---

## 3. Review Sections & Short Identifiers (`A1`, `B1`, …)

Organize findings into six mandatory sections. Each finding gets a short section-prefixed identifier (`A1`, `A2`, `B1`, etc.):

### A. Critical Security (`A1`, `A2`, …)
- Secrets, credentials, `.env` handling, and personally identifiable staff data (PII) in tracked files, logs, exports, session state, or tracebacks.
- Untrusted file inputs (CSV/XLSX/JSON uploads, previous-plan imports): path traversal, spreadsheet formula injection, malformed archives, unbounded file sizes, unsafe deserialization (`pickle`/`eval`).
- Authentication, authorization, and privilege/session isolation boundaries (never assume a control exists solely because a UI button is hidden).
- Dependency provenance, lockfile consistency (`uv.lock` vs `pyproject.toml`), and known vulnerable packages.

### B. Functionality & Bugs (`B1`, `B2`, …)
- **PRD Conformance**: Every requirement and acceptance criterion in the target `documentation/PRD_*.md` is implemented and behaves as specified.
- **Core Scheduling Invariants**: Shift coverage, eligibility, availability, pre-assignments, open/closed night rules, carry-forward accounting, and fairness metrics.
- **Cross-Layer Parity (`feasibility.py` ↔ `solver_cpsat.py` ↔ `validator.py` ↔ Export/UI)**:
  - Verify that any rule added or changed in the CP-SAT solver (`app/scheduler/solver_cpsat.py`) is identically enforced in pre-solve feasibility checks (`app/scheduler/feasibility.py`), post-solve/manual-edit validation (`app/scheduler/validator.py`), and reflected accurately in the Streamlit UI and Excel export.
- **Edge Cases & Error Handling**: Quarter/year boundaries, leap years, empty/duplicate inputs, partial failures, and custom exceptions (`exceptions.py` instead of bare `except:`).

### C. Scalability & Efficiency (`C1`, `C2`, …)
- CP-SAT model growth (variable/constraint explosion), missing solver timeouts, or unguided search parameters.
- Redundant work on every Streamlit UI rerun (missing caching, repeated file parsing or DataFrame copies).
- Quadratic/cubic loops over staff × days × shifts, or unbounded memory/log growth.

### D. Simplicity (`D1`, `D2`, …)
- Adherence to the project's **"Flat & Simple" over "Complex & Scalable"** rule.
- Unnecessary abstractions, deep inheritance, convoluted control flow, or custom plumbing that can be replaced with straightforward Python/Pandas/Pydantic constructs.

### E. Maintainability (`E1`, `E2`, …)
- Strict type safety (`mypy --strict` compliance), clear naming, and modular boundaries.
- Duplicated business constants or rule logic across solver, validator, and UI.
- Test quality and regression coverage: verify that confirmed `Critical`/`High` issues have (or are recommended) targeted `pytest` tests that actually fail when the bug is present.

### F. Documentation Correctness (`F1`, `F2`, …)
- Agreement between executable behavior and `README.md`, `documentation/ARCHITECTURE.md`, `documentation/CONSTRAINTS.md`, `documentation/CHANGELOG.md`, `app/release_info.py`, and target `documentation/PRD_*.md` files.
- Accuracy of docstrings on complex scheduling/solver logic.

*(If a section has zero findings, keep the section heading and state: "No issues identified in this category within the reviewed scope.")*

---

## 4. Required Fields for Every Finding

Every finding (`A1`, `B1`, etc.) must include:

1. **ID & Title**: Short identifier and plain-English summary (e.g., `### B1 — Validator does not check intern weekend shift cap after manual edits`).
2. **Status**: `- **Status**: [ ] Open` (actionable checkbox so the report can be used as a follow-up punch list).
3. **Filename & Lines**: Exact relative path and line range (e.g., `app/scheduler/validator.py` (Lines `210–245`)).
4. **Issue Description**:
   - *Context (Plain Language)*: 1–2 sentences explaining what this component does in everyday clinic/scheduling terms for a reader unfamiliar with the code.
   - *Technical Details*: Concrete code path, violated invariant, or reproducible scenario.
5. **Impact Assessment**:
   - Severity (`Critical` | `High` | `Medium` | `Low`) + concrete consequence for clinic schedulers, staff rosters, security, or developers.
6. **Remediation Approach**: Minimal, actionable steps to fix the issue (plus suggested regression test).
7. **Remediation Complexity**:
   - `Low` (< 30 min, localized to a single function/file)
   - `Medium` (1–3 hours, touches 2–4 modules or requires new test fixtures)
   - `High` (> half day, cross-cutting model or solver constraint redesign)
   - Include a 1-sentence justification.

---

## 5. Execution Procedure

1. **Confirm Metadata & PRD**: Check model name and target PRD; ask the user if either is missing/ambiguous.
2. **Trace & Inspect**: Map data flow from `file_loader.py` → `models.py` → `feasibility.py` → `solver_cpsat.py` → `validator.py` → `streamlit_app.py`.
3. **Run Proportionate Automated Checks**: Run relevant `uv run pytest`, `uv run ruff check`, and `uv run mypy` checks when the environment permits. Never claim a check passed unless it was actually executed.
4. **Write the Untracked Report**: Use [resources/review-template.md](./resources/review-template.md) to write `documentation/REVIEW_<YYYY-MM-DD>-<short-commit-hash>-<feature-slug>.md`.
5. **Verify Untracked Status & Summarize**: Confirm via `git status --short` that the new review file is ignored by git, then provide a concise summary table and clickable link in chat.

