# Dienstplan Generator

Quarterly Notdienst (weekend + night shift) scheduling app built with Streamlit, using a pure-Python heuristic solver (greedy + local search).

## Features

- **CSV Import**: Load staff data with role, availability, and constraint preferences
- **Constraint Validation**: Enforces hard constraints (age restrictions, pairing rules, 3-week block limits) and optimizes soft constraints (proportional distribution, fairness)
- **Heuristic Solver**: Greedy assignment + simulated annealing local search
- **German UI**: 6-page Streamlit interface with schedule visualization and export
- **Effective Nights**: Paired night shifts count as 0.5× per person for fair workload distribution

## Quick Start

### Prerequisites

- Python 3.11+
- Dependencies: `streamlit`, `pandas`, `pydantic`, `python-dateutil`, `xlsxwriter`

### Installation

```powershell
# Clone/navigate to project directory
cd "g:\Meine Ablage\Creative Projects\Programming\Dienstplan"

# Install dependencies
python -m pip install streamlit pandas pydantic python-dateutil xlsxwriter

# For development
python -m pip install pytest ruff pylint mypy
```

### Run App

```powershell
python -m streamlit run app/streamlit_app.py
```

The app will launch at `http://localhost:8501`.

### Run Tests

```powershell
python -m pytest tests/ -v
```

## Usage Workflow

1. **Laden / CSV**: Upload `data/staff_sample.csv` (39 staff members included)
2. **Personal**: View and filter staff by role, age, night shift capability
3. **Regeln**: Review hard and soft constraints
4. **Plan erstellen**: Select Q2/2026, configure solver (default 2000 iterations), generate schedule
5. **Plan anzeigen**: View assignments, per-staff counters, validation results
6. **Export**: Download CSV or Excel

## Data Format

### Staff CSV Columns

- `name`: Full name
- `identifier`: Short code (e.g., "Jul", "AA")
- `adult`: `true` if ≥18 years
- `hours`: Weekly contracted hours
- `beruf`: `TFA`, `Azubi`, or `TA`
- `reception`: Can work reception/Anmeldung
- `nd_possible`: Can do night shifts
- `nd_alone`: Can work nights solo
- `nd_count`: JSON array of allowed consecutive night lengths (e.g., `[1,2]`)
- `nd_exceptions`: JSON array of weekdays (1=Mon, 7=Sun) excluded from nights

## Constraints

### Hard Constraints (Must Satisfy)

- Minors cannot work Sundays
- TAs never work weekends
- Azubis never work nights alone (except with TA present)
- Max 1 consecutive shift block per rolling 3-week window
- No day shift on same/next day after night shift
- `nd_count` and `nd_exceptions` respected

### Soft Constraints (Optimized)

- Notdienste proportional to contracted hours
- Paired nights count 0.5× per person
- Minimal deviation within role groups (TFA/Azubi/TA)

## Project Structure

```
.
├── app/
│   ├── streamlit_app.py       # Streamlit UI (6 pages)
│   └── scheduler/
│       ├── models.py           # Pydantic models (Staff, Shift, Schedule)
│       ├── validator.py        # Constraint validation
│       └── solver.py           # Greedy + local search solver
├── data/
│   └── staff_sample.csv        # Sample staff data (39 members)
├── tests/
│   └── test_scheduler.py       # Unit tests
├── pyproject.toml              # Dependencies & tooling config
└── README.md
```

## Development

### Linting & Formatting

```powershell
# Format code
ruff format .

# Lint
pylint app/ --disable=fixme

# Type check
mypy app/ --strict
```

### Configuration

- **Ruff**: Line length 100, Python 3.11+, PEP 8 rules
- **Mypy**: Strict mode with type hints enforced
- **Pylint**: Max line 100, disabled C0111, R0913-15, W0511

## Known Limitations

- Vacation/availability import is a placeholder (not yet implemented)
- Manual schedule overrides planned for future release
- Azubi school-day constraint not enforced (out of MVP scope)

## License

Hobby project for internal use.
