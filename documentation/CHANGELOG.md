# Technical Changelog

Developer-facing implementation reference for released changes. This document complements the short, business-facing release history in `app/release_info.py`.

## Versioning conventions

- `X.Y.0` — user-visible feature release.
- `X.Y.Z` — fix or small adjustment without a new feature.
- `X.0.0` — significant product change; `1.0.0` marks the first productive release.
- Entries are newest first. Historical entries group related commits approximately; commit hashes are included where useful for tracing.

## [1.2.0] - 2026-07-31

### Added: visual review of cross-quarter block-gap exceptions

Current working-tree change set; intended release commit has not yet been created.

- Added `CrossQuarterBlockGapException` and `find_cross_quarter_block_gap_exceptions()` in `app/scheduler/validator.py`.
  - The display-only analysis reconstructs block starts from the generated schedule and imported trailing assignments, using the active `SchedulerConfig` gap values.
  - It identifies only the solver's relaxed Q2→Q3 block-gap cases; a continuous block across the quarter boundary is not reported.
- Updated `page_plan_anzeigen()` in `app/streamlit_app.py`:
  - Affected calendar cells display `⚠️` with an orange highlight and a legend entry.
  - An expander lists the employee, previous and current block start, and actual versus required gap for each exception.
  - The export path is unchanged; indicator data is derived only while displaying the plan.
- Added `TestCrossQuarterBlockGapDisplay` in `tests/test_carry_forward.py` for a detected relaxed gap and a non-flagged continuous boundary block.
- Updated `tests/test_release_info.py`, `pyproject.toml`, `uv.lock`, and `app/release_info.py` for version `1.2.0`.

## [1.1.0] - 2026-07-31

### Added: dedicated About page and release metadata

Current working-tree change set; intended release commit has not yet been created.

- Added `app/release_info.py` as the application-level release metadata source:
  - `APP_NAME` and `CURRENT_VERSION` expose the display values.
  - Immutable `Release` dataclass stores a version, German display date, short expander-heading summary, and one to three user-facing highlights.
  - `RELEASES` is sorted newest first and contains the reconstructed product history.
- Replaced the sidebar expander with `page_about()` in `app/streamlit_app.py`:
  - Adds **Über diese App** to `nav_options` and routes it to the new page.
  - Displays the current version and release date with Streamlit metrics.
  - Renders the current release summary/highlights directly above the history, then one collapsed Streamlit expander per `RELEASES` entry using version, date, and short summary in the heading.
- Set the release version to `1.1.0` in `pyproject.toml`, `uv.lock`, and `app/release_info.py`.
- Added `tests/test_release_info.py` coverage for semantic version format, current-release ordering, the `1.0.0` productive milestone, uniqueness/readability of release entries, and package/display version alignment.
- Added `.github/skills/versioning/SKILL.md` to define the version bump, business changelog, validation, and release-maintenance workflow.

## [1.0.3] - 2026-07-12

### Fixed: predefined holiday shifts on weekends

Source commit: `0368547`.

- Updated `get_pre_assigned_holiday_dates()` and `generate_quarter_shifts()` in `app/scheduler/models.py`.
- A pre-assigned holiday on Saturday is now classified as a holiday before the ordinary Saturday branch is evaluated. This generates the required holiday/Sunday-pattern slots so the existing CP-SAT pinning constraints can bind the assignment.
- Sunday remains excluded from the extra holiday-date generation because normal Sunday slots already exist.

## [1.0.2] - 2026-05-31

### Added: previous-plan import and cross-quarter planning support

Primary source commits: `9c3ad57`, `9878c09`, `ff6ebb0`, `230bc30`, `be350e9`, `b502c55`, `b014261`, `3f1b2ca`, `adc8533`, `20bc00a`.

- Replaced the JSON carry-forward upload workflow with `build_previous_context_from_xlsx()` and Excel parsing in `app/scheduler/models.py` and `app/scheduler/file_loader.py`.
  - Import reconstructs trailing assignments and FTE-normalized carry-forward deltas from a prior schedule export.
  - Parser supports the export's multiple worksheets while retaining compatibility with earlier layouts.
- Extended cross-quarter solver handling in `app/scheduler/solver_cpsat.py`:
  - Applies the boundary block-gap logic between consecutive quarters.
  - Avoids treating trailing assignments from the same quarter as cross-quarter data.
  - Softens the boundary 3-week block constraint when a hard constraint would make an otherwise viable schedule infeasible.
- Added `Staff.available_from` and blocks assignment before an employee's start date in the planning and feasibility paths.
- Consolidated the Streamlit input flow into the upload page and moved related review views into tabs on the staff page.
- Split the Excel export into night-duty and weekend-duty worksheets, updated the parser to concatenate them during import, and refined export/fairness display columns.
- Completed the rules-page documentation and persisted the soft-penalty score so the fairness view can show a score breakdown.

## [1.0.1] - 2026-05-31

### Added: feasibility diagnostics and solver controls

Primary source commits: `68c4bb9`, `211e98a`, `02d68e8`.

- Added `app/scheduler/feasibility.py` with a pre-solve capacity analysis that checks viable night-duty blocks and reports errors or warnings before launching CP-SAT.
- Added `SchedulerConfig` and exposed configuration, random seed, quarter/year selection, and solve-time choices through the Streamlit UI.
- Added solver convergence logging via a CP-SAT callback and rendered progress/convergence information in the application.
- Improved infeasibility diagnostics and added tests for the new constraint/configuration paths.
- Standardized Excel export column order to `Wochentag`, `Datum`, `Mitarbeiter`, `Schicht`, and `Paarweise`.

## [1.0.0] - 2026-03-24

### First productive release

Primary source commits: `2150e28`, `89fa0bc`.

- Added flexible CSV/XLSX ingestion in `app/scheduler/file_loader.py`:
  - Normalizes column headers and resolves aliases instead of requiring one exact spelling.
  - Parses staff, vacation, and optional pre-assignment input files into scheduler models.
  - Added focused loader tests for the supported header and input variants.
- Added `PreAssignedShift` support across models, upload UI, validation, and the CP-SAT solver.
  - Pre-assigned duties are translated into fixed assignment constraints when their corresponding schedule slots are generated.
  - Upload and validation feedback exposes conflicts before scheduling.

## [0.3.0] - 2026-02-20

### Added: access control and review improvements

Primary source commits: `f6ac188`, `c8e12cc`, `8408e8d`, `48314ec`, `d5b487d`.

- Added optional login handling in `app/streamlit_app.py`:
  - Reads `password_hash` from Streamlit secrets or `PASSWORD_HASH` from the environment.
  - Compares SHA-256 hashes and gates all scheduling UI behind `st.session_state.authenticated` when configured.
- Removed the heuristic scheduling path and retained the CP-SAT solver behind the simpler facade in `app/scheduler/solver.py`.
- Corrected validator handling of staff-specific `nd_min_consecutive` values and exposed quick/thorough solve-time options.
- Added an optional birthday field to `Staff`; the solver treats the birthday as unavailable for all duty types.
- Refined plan-review and fairness UI components.

## [0.2.0] - 2026-01-31

### Added: operational constraint and fairness framework

Primary source commits: `143a9d4`, `0434158`, `a801397`, `9e368e6`, `bd3db9e`, `67583ca`, `d3c2f6b`, `c967dd6`.

- Expanded CP-SAT coverage, eligibility, pairing, rest, and workload constraints in `app/scheduler/solver_cpsat.py` and mirrored validation in `app/scheduler/validator.py`.
- Added department (`abteilung`) data to `Staff` and prevents incompatible department combinations on the same night duty.
- Added effective night-duty weighting for paired assignments and used role-aware FTE normalization in the fairness objective and review UI.
- Enforced the three-week night-duty block gap and a maximum fairness deviation, with employee-specific minimum consecutive night settings.
- Added vacation handling, duty-type balancing, calendar improvements, and general plan-review UI updates.

## [0.1.0] - 2026-01-25

### Initial internal prototype

Primary source commits: `87fe728`, `0633bad`, `8571576`, `f232ddf`, `62c2ab3`, `9c1f2e7`.

- Established the Streamlit application shell and package structure under `app/`.
- Introduced core scheduler models for staff, shifts, assignments, schedules, vacations, and role/eligibility metadata.
- Implemented initial quarter shift generation, schedule validation, and a CP-SAT-based scheduling path using OR-Tools.
- Added the first data upload, schedule review, fairness, and calendar views; later January prototype commits iterated on constraint strictness and review behavior.
