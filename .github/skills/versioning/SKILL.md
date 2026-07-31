---
name: versioning
description: "Use when: releasing the clinic scheduling app, changing its version number, or updating its business-facing changelog."
---

# Application Versioning

Maintain a concise, business-friendly version history for the Dienstplan Generator.

## Sources of truth

- `app/release_info.py` holds the version shown in the application (`CURRENT_VERSION`) and its release history (`RELEASES`).
- `pyproject.toml` holds the distributable package version.
- `documentation/CHANGELOG.md` is the developer-facing technical implementation history.
- These two current-version values must always match.

## Version numbers

Use semantic versioning. Version `1.0.0` is the first productive release (24 March 2026).

- **Feature release** (`X.Y.0`, for example `1.1.0`): a user-visible feature or meaningful workflow improvement. This is the normal scope for a medium-sized update.
- **Patch** (`X.Y.Z`, for example `1.0.3`): a bug fix, typo correction, or small adjustment that does not introduce a new user-facing feature.
- **Major** (`X.0.0`, for example `2.0.0`): reserve for a significant change to the application, such as a deliberately breaking core workflow or a substantially different product. Do not use a major bump for routine improvements.

Do not create a release for refactoring, tests, documentation, or dependency-only work unless it changes what users experience.

## Release procedure

1. Inspect the commits since the previous release and group related changes into one release.
2. Choose the smallest appropriate version increase using the rules above.
3. Update `CURRENT_VERSION` and `pyproject.toml` together.
4. Add the new `Release` at the top of `RELEASES`, using the release date in German.
5. Add a matching entry at the top of `documentation/CHANGELOG.md`, including relevant commit hashes, changed modules, key functions/models, data or behavior changes, and tests. Use an approximate grouped history only when documenting releases that predate this workflow.
6. Add a short German `summary` to the `Release` entry (maximum 60 characters) so users can scan expander headings. Write one to three short German `highlights` that state the practical benefit. Avoid implementation names, commit hashes, internal solver details, and jargon.
7. Keep both changelogs newest first and preserve the existing release history.
8. Update or add tests in `tests/test_release_info.py`, then run the relevant tests before completing the release.

## Changelog writing standard

Write for clinic staff, not developers. Prefer “Vorgegebene Dienste werden zuverlässig übernommen” over a description of the code change. Combine several technical commits when they delivered one coherent improvement. Keep each bullet to one sentence.

## Technical changelog writing standard

Write `documentation/CHANGELOG.md` for developers. Use a version heading with an ISO date, then concise sections such as **Added**, **Changed**, or **Fixed**. Reference concrete modules, symbols, configuration, data formats, tests, and relevant commit hashes. Describe the implementation mechanism and compatibility or migration impact; do not duplicate the business-facing wording from `RELEASES`.