# Development Setup

## Prerequisites

- Windows 11 (or Linux/macOS)
- Python 3.11+
- PowerShell (Windows) or Bash (Linux/macOS)

## Quick Start

```powershell
# Clone and navigate to project
cd C:\Users\Elliot\Desktop\Coding\scheduling

# Create virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -e .

# Run app
streamlit run app/streamlit_app.py
```

## Using uv (Recommended)

```powershell
# Install uv if not present
# See: https://github.com/astral-sh/uv

# Sync dependencies from pyproject.toml
uv sync

# Run with uv
uv run streamlit run app/streamlit_app.py
```

## Dependencies

### Runtime
| Package | Purpose |
|---------|---------|
| streamlit | Web UI framework |
| pandas | Data manipulation |
| pydantic | Data validation |
| python-dateutil | Date parsing |
| xlsxwriter | Excel export |
| ortools | Constraint programming solver |

### Development
| Package | Purpose |
|---------|---------|
| pytest | Testing framework |
| ruff | Linting and formatting |
| pylint | Additional linting |
| mypy | Type checking |
| pandas-stubs | Type stubs for pandas |

## Running the App

```powershell
# Standard
streamlit run app/streamlit_app.py

# With specific port
streamlit run app/streamlit_app.py --server.port 8502

# Using batch file (Windows)
.\run.bat
```

App opens at `http://localhost:8501`

## Running Tests

```powershell
# All tests
pytest tests/ -v

# Specific test
pytest tests/test_scheduler.py::test_cpsat_solver_produces_valid_schedule -v

# With coverage
pytest tests/ --cov=app --cov-report=html
```

## Code Quality

```powershell
# Format code
ruff format app/ tests/

# Lint (check only)
ruff check app/ tests/

# Lint (auto-fix)
ruff check app/ tests/ --fix

# Type check
mypy app/ --strict
```

## Docker

```powershell
# Build image
docker build -t dienstplan:latest .

# Run container
docker run -p 8501:8501 dienstplan:latest

# Access at http://localhost:8501
```

## Project Structure

```
scheduling/
├── app/
│   ├── streamlit_app.py      # Main UI
│   └── scheduler/
│       ├── models.py          # Data models
│       ├── validator.py       # Constraint validation
│       ├── solver.py          # Solver facade
│       └── solver_cpsat.py    # CP-SAT implementation
├── data/
│   └── staff_sample.csv       # Sample data (39 employees)
├── documentation/
│   ├── PROBLEM_DESCRIPTION.md # Business requirements
│   ├── ARCHITECTURE.md        # Technical docs
│   ├── CONSTRAINTS.md         # Rules & stakeholder analysis
│   └── DEVELOPMENT.md         # This file
├── tests/
│   └── test_scheduler.py      # Unit tests
├── pyproject.toml             # Dependencies & config
├── Dockerfile                 # Container definition
└── README.md                  # Quick start
```

## Common Tasks

### Add a New Constraint

1. Add check function in `validator.py`
2. Add CP constraint in `solver_cpsat.py`
3. Add test case in `test_scheduler.py`
4. Update `CONSTRAINTS.md`

### Modify Staff Data

Edit `data/staff_sample.csv` with columns:
- name, identifier, adult, hours, beruf
- reception, nd_possible, nd_alone
- nd_count (JSON array), nd_exceptions (JSON array)

### Debug Solver

```python
# In Python REPL
from datetime import date
from app.scheduler.models import load_staff_from_csv
from app.scheduler.solver import generate_schedule
from pathlib import Path

staff = load_staff_from_csv(Path("data/staff_sample.csv"))
result = generate_schedule(staff, date(2026, 4, 1), random_seed=42)

if result.success:
    print(f"Assignments: {len(result.get_best_schedule().assignments)}")
else:
    print(f"Failed: {result.unsatisfiable_constraints}")
```

## Troubleshooting

### Import Errors
```powershell
# Ensure virtual environment is activated
.\.venv\Scripts\Activate.ps1

# Reinstall in editable mode
pip install -e .
```

### OR-Tools Not Found
```powershell
pip install ortools
```

### Streamlit Warnings
Deprecation warnings about `use_container_width` are non-breaking and can be ignored.
