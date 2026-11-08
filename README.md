# Dienstplan Generator

Quarterly Notdienst (weekend + night shift) scheduling app for veterinary clinics. Uses **OR-Tools CP-SAT** constraint programming for optimal fair schedules.

## Features

- **Constraint Programming**: Guaranteed optimal fairness within hard constraints using Google OR-Tools CP-SAT
- **Open & Closed Nights**: Dedicated staffing rules for open nights (headcount 2, mandatory TFA) and closed nights
- **Intern Weekend Rotation**: Coupled weekend shifts (`Sa_Intern` + `So_Intern`) with two-track fairness and 10-day spacing
- **Tierarzt Midweek Relief**: Auxiliary physicians (`Beruf.VET`) unburden TFAs on Tue-Thu closed nights in exact 2-night solo blocks
- **German UI**: Modern React Single-Page Application (SPA) with calendar views, fairness statistics, and pre-flight validation diagnostics
- **Fair Distribution**: FTE-normalized workload balancing within role groups with cross-quarter carry-forward
- **Effective Nights**: Differentiated weighting for open vs closed nights (TFA paired 0.5×, Intern/Azubi 1.0×)
- **Full Validation**: Automated post-solve validator checking all hospital and statutory labor constraints

## Quick Start

```powershell
# Navigate to project
cd C:\Users\Elliot\Desktop\Coding\scheduling

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Run FastAPI backend + SPA
uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8080 --reload
```

Open `http://localhost:8080` in your browser.

## Usage

1. **Personal**: Manage staff, FTE hours, qualifications, and role constraints
2. **Abwesenheiten**: Manage vacations and absences
3. **Planung**: Pre-flight feasibility check, CP-SAT generation, and live progress
4. **Dienstplan**: View calendar matrix, fairness analytics, and validation diagnostics
5. **Export**: 1-click Excel export with formatting

## Documentation

| File | Purpose |
|------|---------|
| [PROBLEM_DESCRIPTION.md](documentation/PROBLEM_DESCRIPTION.md) | Business requirements & project spec |
| [ARCHITECTURE.md](documentation/ARCHITECTURE.md) | Technical documentation |
| [CONSTRAINTS.md](documentation/CONSTRAINTS.md) | Business rules & stakeholder analysis |
| [DEVELOPMENT.md](documentation/DEVELOPMENT.md) | Developer setup guide |

## Tests

```bash
# Fast development loop (~3-4s; skips full-quarter CP-SAT solver tests)
uv run pytest --fast

# Full test suite (~2m; runs all tests with early-stopping + session cache)
uv run pytest

# Uncapped solver optimization ceilings (original 30s-60s per solver test)
uv run pytest --full-solve
```

## Project Structure

```
├── app/
│   ├── api/                   # FastAPI backend REST API routes & dependencies
│   ├── scheduler/             # Core scheduling logic (models, solver, validator)
│   ├── persistence/           # Datastore abstraction (Firestore + local JSON)
│   └── exporters/             # Excel report generator
├── frontend/                  # React 19 + Tailwind CSS SPA
├── data/staff_sample.csv      # Sample data (39 employees)
├── documentation/             # Project documentation & architecture specs
└── tests/                     # Unit and integration tests
```

## Solver

Uses **OR-Tools CP-SAT** constraint programming solver (60-120s) for guaranteed optimal fairness.

## License

Internal use only.
