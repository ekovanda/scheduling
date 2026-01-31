# Dienstplan Generator

Quarterly Notdienst (weekend + night shift) scheduling app for veterinary clinics. Uses **OR-Tools CP-SAT** constraint programming for optimal fair schedules.

## Features

- **Constraint Programming**: Guaranteed optimal fairness within hard constraints
- **German UI**: 6-page Streamlit interface
- **Fair Distribution**: FTE-normalized workload balancing within role groups
- **Effective Nights**: Paired shifts count 0.5× per person
- **Full Validation**: Hard constraints enforced, soft constraints optimized

## Quick Start

```powershell
# Navigate to project
cd C:\Users\Elliot\Desktop\Coding\scheduling

# Activate virtual environment
.\.venv\Scripts\Activate.ps1

# Run app
streamlit run app/streamlit_app.py
```

Open `http://localhost:8501` in your browser.

## Usage

1. **Laden / CSV**: Upload staff data (use `data/staff_sample.csv`)
2. **Personal**: View and filter staff
3. **Regeln**: Review constraint rules
4. **Plan erstellen**: Select quarter, choose CP-SAT solver, generate
5. **Plan anzeigen**: View calendar, fairness stats, validation
6. **Export**: Download CSV or Excel

## Documentation

| File | Purpose |
|------|---------|
| [PROBLEM_DESCRIPTION.md](documentation/PROBLEM_DESCRIPTION.md) | Business requirements & project spec |
| [ARCHITECTURE.md](documentation/ARCHITECTURE.md) | Technical documentation |
| [CONSTRAINTS.md](documentation/CONSTRAINTS.md) | Business rules & stakeholder analysis |
| [DEVELOPMENT.md](documentation/DEVELOPMENT.md) | Developer setup guide |

## Tests

```powershell
pytest tests/ -v
```

## Project Structure

```
├── app/streamlit_app.py       # Streamlit UI
├── app/scheduler/             # Core logic (models, solver, validator)
├── data/staff_sample.csv      # Sample data (39 employees)
├── documentation/             # All documentation
└── tests/                     # Unit tests
```

## Solver Options

| Backend | Time | Use Case |
|---------|------|----------|
| **CP-SAT** (default) | 60-120s | Production - optimal fairness |
| Heuristic | 2-5s | Development - quick iterations |

## License

Internal use only.
