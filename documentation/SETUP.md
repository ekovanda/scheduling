# Development Setup

## Prerequisites

- Windows 11
- Python 3.11 or higher
- PowerShell

## Installation

### Option 1: pip (Current Setup)

```powershell
# Navigate to project
cd "g:\Meine Ablage\Creative Projects\Programming\Dienstplan"

# Install runtime dependencies
python -m pip install streamlit pandas pydantic python-dateutil xlsxwriter

# Install development dependencies (optional)
python -m pip install pytest ruff mypy pandas-stubs
```

### Option 2: uv (Recommended for Future)

```powershell
# Install uv (if not already installed)
# See: https://github.com/astral-sh/uv

# Install dependencies
uv pip install -e .

# Install dev dependencies
uv pip install -e ".[dev]"
```

## Running the App

### Quick Launch

```powershell
# Option 1: Use batch file
.\run.bat

# Option 2: Direct command
python -m streamlit run app\streamlit_app.py

# Option 3: From any directory
cd "g:\Meine Ablage\Creative Projects\Programming\Dienstplan"
streamlit run app\streamlit_app.py
```

The app will open at `http://localhost:8501`

## Development Workflow

### Run Tests

```powershell
# All tests
python -m pytest tests/ -v

# Specific test
python -m pytest tests/test_scheduler.py::test_effective_nights_calculation -v

# With coverage
python -m pytest tests/ --cov=app --cov-report=html
```

### Code Quality

```powershell
# Format code
ruff format app/ tests/

# Check linting
ruff check app/ tests/

# Auto-fix linting issues
ruff check app/ tests/ --fix

# Type check (strict mode)
mypy app/ --strict
```

### Docker Build

```powershell
# Build image
docker build -t dienstplan:latest .

# Run container
docker run -p 8501:8501 dienstplan:latest

# Access at http://localhost:8501
```

## Project Structure

```
dienstplan/
├── app/
│   ├── __init__.py
│   ├── streamlit_app.py          # Main UI
│   └── scheduler/
│       ├── __init__.py
│       ├── models.py              # Data models
│       ├── validator.py           # Constraint validation
│       └── solver.py              # Heuristic solver
├── data/
│   └── staff_sample.csv           # Sample staff data
├── tests/
│   └── test_scheduler.py          # Unit tests
├── documentation/
│   └── readme.md                  # Technical docs
├── pyproject.toml                 # Config & dependencies
├── README.md                      # User guide
├── Dockerfile                     # Container setup
├── .gitignore                     # Git excludes
└── run.bat                        # Windows launcher
```

## Troubleshooting

### Streamlit not found

```powershell
python -m pip install --upgrade streamlit
```

### Import errors

```powershell
# Ensure you're in project root
cd "g:\Meine Ablage\Creative Projects\Programming\Dienstplan"

# Reinstall dependencies
python -m pip install -r requirements.txt  # if created
# or
python -m pip install streamlit pandas pydantic python-dateutil xlsxwriter
```

### Port already in use

```powershell
# Use different port
streamlit run app\streamlit_app.py --server.port 8502
```

### Type checking errors

```powershell
# Install type stubs
python -m pip install pandas-stubs types-python-dateutil
```

## VS Code Setup (Optional)

### Recommended Extensions

- Python (ms-python.python)
- Pylance (ms-python.vscode-pylance)
- Ruff (charliermarsh.ruff)

### settings.json

```json
{
  "python.defaultInterpreterPath": "python",
  "python.linting.enabled": true,
  "python.formatting.provider": "none",
  "[python]": {
    "editor.formatOnSave": true,
    "editor.codeActionsOnSave": {
      "source.organizeImports": true
    },
    "editor.defaultFormatter": "charliermarsh.ruff"
  },
  "ruff.format.args": ["--config=pyproject.toml"]
}
```

## Environment Variables

None required for basic operation.

## Data Files

### Required

- `data/staff_sample.csv` - Included in repo

### Optional

- Vacation/availability CSV (future feature)

## Performance Notes

- Schedule generation: 2-5 seconds for Q2/2026
- Max iterations: Adjustable (default 2000)
- Memory usage: <100MB typical

## Known Issues

- Streamlit deprecation warnings for `use_container_width` (non-breaking)
- uv not installed on system (using pip instead)

## Support

For issues, check:
1. Python version ≥3.11
2. All dependencies installed
3. Running from project root
4. Windows PowerShell (not CMD)
