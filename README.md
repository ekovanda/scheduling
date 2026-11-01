# Dienstplan Generator

Quarterly Notdienst (weekend + night shift) scheduling app for veterinary clinics. Uses **OR-Tools CP-SAT** constraint programming for optimal fair schedules.

## Features

- **Constraint Programming**: Guaranteed optimal fairness within hard constraints using Google OR-Tools CP-SAT
- **Open & Closed Nights**: Dedicated staffing rules for open nights (headcount 2, mandatory TFA) and closed nights
- **Intern Weekend Rotation**: Coupled weekend shifts (`Sa_Intern` + `So_Intern`) with two-track fairness and 10-day spacing
- **Tierarzt Midweek Relief**: Auxiliary physicians (`Beruf.VET`) unburden TFAs on Tue-Thu closed nights in exact 2-night solo blocks
- **German UI**: 7-page Streamlit interface with calendar views, fairness statistics, and validation diagnostics
- **Fair Distribution**: FTE-normalized workload balancing within role groups with cross-quarter carry-forward
- **Effective Nights**: Differentiated weighting for open vs closed nights (TFA paired 0.5×, Intern/Azubi 1.0×)
- **Full Validation**: Automated post-solve validator checking all hospital and statutory labor constraints

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

## Solver

Uses **OR-Tools CP-SAT** constraint programming solver (60-120s) for guaranteed optimal fairness.

## License

Internal use only.
