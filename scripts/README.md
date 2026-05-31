# Scripts

One-off development and debugging scripts. Not part of the application. Safe to run standalone from the project root with the `.venv` activated.

| Script | Purpose | Key Imports | Run With |
|---|---|---|---|
| `debug_capacity.py` | Analyzes night staffing capacity: lists all night-eligible staff split by `nd_alone` status, calculates how many solo vs. paired nights they cover, and checks if total non-Azubi supply is sufficient for 91 nights. | `pandas`, Excel file at `data/MA_excel.xlsx` | `python scripts/debug_capacity.py` |
| `debug_paired.py` | Reads `data/Feiertage_Excel.xlsx` and prints every pre-assigned holiday shift with its occupant(s), flagging any day shifts with unexpected pairs. | `pandas` | `python scripts/debug_paired.py` |
| `debug_trace.py` | Traces available night dates for a hardcoded set of staff (from Q2/2026 infeasibility debugging). Shows which dates each person is available given their weekday exclusions and vacations, then prints block-gap analysis relative to pre-assigned holiday dates. No external files needed. | `datetime` stdlib only | `python scripts/debug_trace.py` |
| `debug_math.py` | Slot-demand vs. capacity analysis: loads `data/staff_sample.csv`, counts total shift slots (day + night), estimates supply under the 21-day block rule, and flags if the schedule is mathematically infeasible. Also checks for day/night conflict regressions. | `scheduler.models` (`load_staff_from_csv`, `generate_quarter_shifts`) | `python scripts/debug_math.py` |
