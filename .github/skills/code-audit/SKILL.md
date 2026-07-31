---
name: code-audit
description: "Use when: performing a thorough code review, security audit, production-readiness assessment, technical-debt review, or repository health check. Finds and prioritizes verified issues as P0 critical security/privacy/integrity blockers, P1 implementation errors, P2 robustness/scalability/operability/user-experience risks, and P3 maintainability, code-smell, or documentation drift."
argument-hint: "Optional scope, such as a PR, feature, directory, or 'full repository'"
---

# Thorough Code Audit

Perform an evidence-based audit that finds consequential defects before cosmetic concerns. This is a review workflow: do not modify production code unless the requester explicitly asks for fixes.

## Severity Policy

Use the highest level that the **demonstrated impact** warrants. Do not inflate a finding because it is theoretically possible, and do not downgrade a security or data-integrity issue because a workaround exists.

| Priority | Meaning | Typical examples |
| --- | --- | --- |
| **P0 — Critical** | A release blocker: credible security, privacy, safety, or data-integrity exposure; secret leakage; remotely exploitable vulnerability; authorization bypass; irreversible corruption; or a critical workflow that can produce unsafe/invalid output without a viable workaround. | Committed credential, unsafe deserialization of untrusted data, sensitive data exposed to an unauthorized user, missing hard scheduling constraint that can create an unsafe roster. |
| **P1 — High** | An incorrect implementation of an explicit requirement, invariant, or supported path with material user or business impact. Fix before relying on the affected workflow. | Incorrect carry-forward accounting, accepted input silently ignored, export disagrees with the validated schedule, valid data produces an incorrect plan. |
| **P2 — Medium** | A foreseeable robustness, performance, reliability, operational, accessibility, or user-experience failure. It is not presently an implementation contradiction, but can degrade or prevent normal use. | Unbounded file or solver workload, unclear recoverable error, fragile parser edge case, an expensive operation on every UI rerun. |
| **P3 — Low** | A maintainability, consistency, readability, testability, or documentation concern with no current material user impact. | Dead code, duplicated logic, misleading type/name, stale documentation, missing low-risk test. |

If a concern has no concrete impact, put it in **Observations**, not in the findings list. Never report style preferences as P0–P2.

## Audit Procedure

1. **Set scope and baseline.** Identify the requested files, branch/commit, deployment model, trusted/untrusted inputs, data sensitivity, supported Python version, and commands configured in `pyproject.toml`. When auditing a change, inspect both the diff and its callers, callees, tests, configuration, and documentation.
2. **Map the system.** Inventory entry points, public APIs, UI and CLI paths, data imports/exports, external services, persistent state, authentication, authorization, privilege boundaries, and generated artifacts. For this scheduler, trace user data from upload through parsing, model construction, solver, validator, display, and export.
3. **Review P0 first.** Check tracked files, history when available, CI/configuration, environment-variable handling, logs, examples, exports, and error messages for secrets or personally identifiable staff data. Examine dependency provenance and known vulnerable versions. Follow every untrusted input to dangerous sinks: filesystem paths, archive/spreadsheet parsing, formula injection, subprocesses, dynamic imports/evaluation, deserialization, templates, redirects, and network calls. Verify access controls and that sensitive data is not exposed through downloads, session state, debug output, or tracebacks.
4. **Verify implementation correctness.** Derive the core invariants from requirements, models, validation rules, and tests. Trace each invariant through parsing, normalization, scheduling, validation, rendering, and export. Look for mismatched units/dates/time zones, off-by-one boundaries, skipped branches, default values that change meaning, inconsistent duplicate logic, silent exception handling, and results reported as successful despite incomplete or invalid work. For constraint systems, compare solver constraints with the independent validator and exported schedule.
5. **Assess resilience and user impact.** Use malformed, empty, duplicate, oversized, boundary-date, and conflicting input cases. Check cancellation/timeouts, resource bounds, retry/idempotency behavior, concurrency/session isolation, partial failures, solver feasibility messaging, error recovery, and accessibility/usability of critical errors and warnings. Identify hot loops, needless repeated work, quadratic/cubic growth, and unbounded uploads, exports, or logs.
6. **Assess quality and documentation.** Examine API boundaries, exception taxonomy, type safety, test isolation, determinism, dead code, duplication, naming, configuration drift, and documentation accuracy. Prefer targeted improvements over architecture rewrites; this project values flat, simple designs.
7. **Run proportionate checks.** Read existing test and tool configuration first. Run the most relevant existing tests and linters/type checks when the environment permits. Do not claim a check passed unless it was run successfully. When a check cannot run, state why and provide the precise residual risk.
8. **Corroborate and prioritize.** A finding needs a precise location plus a code path, reproducible scenario, failing test, or other direct evidence. Combine duplicate root causes. Separate confirmed issues from assumptions and missing coverage.
9. **Persist and deliver the report.** Before responding, get the local timestamp in ISO-style form, including the UTC offset. Create or update [the findings history](../../../documentation/CODE_REVIEW_FINDINGS.md) for **every** code review, including reviews with zero findings. Insert the complete new report directly below the document introduction, so the newest review is first; preserve all earlier reports unchanged. Include the audited revision/scope, timestamp, methods and checks performed, counts by priority, all findings, and residual risk. Then provide the user with a concise summary and a link to the newly recorded review. Use [the report template](./assets/audit-report-template.md) for the report content.

## Required Review Areas

- Secrets, credential handling, private staff data, logging, exports, error displays, and debug artifacts.
- Dependencies, lockfile consistency, pinned versions, unsafe or abandoned packages, and development/production configuration differences.
- Authentication and authorization where applicable; never infer a control exists solely from a UI element.
- All file upload, CSV/XLSX, archive, previous-plan, and export paths: size/type limits, formula injection, malformed data, path traversal, parser behavior, and safe errors.
- Business invariants and cross-module agreement: especially schedule coverage, eligibility, availability, pre-assignment, carry-forward, fairness accounting, validator agreement, and export fidelity.
- Failure handling: explicit custom exceptions, failure visibility, partial state cleanup, feasibility diagnostics, time/resource limits, and deterministic behavior where expected.
- Tests: regression coverage for every confirmed P0/P1; boundary and malicious-input coverage for P2; test assertions that would actually catch the reported fault.
- Documentation, architecture descriptions, runbooks, and configuration that no longer match executable behavior.

## Reporting Rules

- `documentation/CODE_REVIEW_FINDINGS.md` is the canonical, append-only review history. Do not overwrite, delete, or silently rewrite a prior review; correct an earlier entry only when the user explicitly requests it.
- Use an `## Review — YYYY-MM-DD HH:MM:SS ±HH:MM` heading for each persisted report. Record a report even when all priority counts are zero.
- Cite exact paths and line ranges; explain the user-facing or security consequence before proposing a fix.
- State relevant preconditions and confidence. A missing mitigation is not a vulnerability unless an attack path is credible in the stated deployment model.
- Prefer a minimal remediation. Mark larger redesigns as optional follow-ups.
- Do not report a vulnerability with exploit instructions or expose discovered secrets. Redact values and recommend rotation/removal.
- Include a P0 or P1 only when it is confirmed or strongly evidenced. Use P2/P3 or `Not Verified` for uncertainty.
- Do not declare the code secure, compliant, or production-ready. State the reviewed scope and remaining uncertainty instead.
