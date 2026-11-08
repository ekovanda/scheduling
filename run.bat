@echo off
REM Dienstplan Generator Launcher (FastAPI Backend + React Frontend)
echo Starting Dienstplan Generator on http://localhost:8080 ...
uv run uvicorn app.api.main:app --host 127.0.0.1 --port 8080 --reload
pause
