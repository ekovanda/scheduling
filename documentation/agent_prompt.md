Goal: Implement a quarterly Streamlit scheduling app that produces fair, rules-compliant Notdienst (Wochenend- + Nachtdienste) schedules from the business rules in `task_description.md` and staff data in `data/ma.md`.

Priority
- Heuristic-first, pure-Python solver (greedy + local search). Do not use OR-Tools unless explicitly justified.
- German UI.
- Transparent constraint reporting: hard constraints must be enforced or shown as unsatisfiable; soft constraints produce penalty scores.

MVP Features
- CSV import of staff (`staff.csv`) and optional availability CSV; editable staff table in-app is a stretch goal.
- Generate a quarter schedule (Q2/2026 start by default) covering:
  - Saturdays: 3 parallel shifts per week (10–21, 10–22, 10–19) with role rules for Azubis/TFA.
  - Sundays: 3 parallel shifts per week (8–20, 10–22, 8–20:30) with Azubi age and onsite windows.
  - Nightly: 7 nights/week staffed (Sun→Mon: 1 TFA; Mon→Tue: 1 TFA; other nights 1–2 TFA). TA present those two nights as specified.
- Hard constraints (examples): minors cannot work Sundays; TA never weekends; one Notdienst block per three weeks per employee (strict); Azubis never alone for ND; staff with ND cannot have day shift same day or next day.
- Soft constraints: proportional distribution by contracted hours, minimal deviation across peers within the same role group (TFA/Azubi/TA).
- Failure behavior: if hard constraints are unsatisfiable, app should FAIL and list unsatisfiable constraints; include a button to propose minimal relaxations.

Solver design
- Pure-Python greedy assignment followed by local search (swap/shift moves) to reduce penalty.
- Encode hard constraints as infeasible states; soft constraints add penalty terms; produce multiple candidate solutions and show scores.
- Provide a validation function that returns hard-violations and soft-penalty breakdown for any candidate schedule.

UI (German)
- Pages: `Laden / CSV`, `Personal`, `Regeln`, `Plan erstellen`, `Plan anzeigen`, `Export`.
- Display: calendar/table, per-MA counters, deviations, and a constraint-violation panel.
- Human-in-loop: accept candidate schedule, manually override cells, and re-run solver.

Input / data
- Seed `data/staff_sample.csv` from `data/ma.md` (provided). Columns: `name,identifier,adult,hours,beruf,reception,nd_possible,nd_alone,nd_count,nd_exceptions` (JSON arrays for list fields).
- Date format: `DD.MM.YYYY` and German locale for UI.
- Quarter start: Q2/2026.

Deliverables
- `pyproject.toml`, `README.md`, `Dockerfile`
- `app/streamlit_app.py`
- `app/scheduler/` (models, heuristic solver, validator)
- `data/staff_sample.csv` seeded from `data/ma.md`
- `tests/test_scheduler.py`
- linter/mypy configs

Acceptance criteria
- `python -m streamlit run app/streamlit_app.py` launches app and can generate a Q2/2026 schedule from sample CSV.
- App lists hard constraint violations when unsatisfiable and shows penalty breakdown otherwise.
- `pytest` includes at least one unit test covering ND assignment and the 1-per-3-weeks rule.

Dependencies (use `uv`)
- Runtime: `uv add streamlit pandas pydantic python-dateutil`
- Dev: `uv add --dev pytest ruff pylint mypy`

Pre-coding: ask clarifying questions and produce a short implementation plan and timeline before writing code.
