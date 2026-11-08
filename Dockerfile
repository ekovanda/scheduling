# syntax=docker/dockerfile:1

# Stage 1: Build React Frontend SPA
FROM node:22-slim AS frontend-builder
WORKDIR /app/frontend
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# Stage 2: Python Backend & Runtime Container
FROM python:3.12-slim

# Copy uv binary from official Astral uv image (pinned release tag for reproducible builds, E4)
COPY --from=ghcr.io/astral-sh/uv:0.13.0 /uv /uvx /bin/

# Environment settings:
# - PYTHONUNBUFFERED: Stream logs immediately to stdout/stderr for Cloud Run & Docker
# - PYTHONDONTWRITEBYTECODE: Avoid writing unnecessary .pyc files
# - PORT: Default listening port (overridden dynamically by Cloud Run)
# - UV_LINK_MODE=copy: Ensures files are copied cleanly across layers
# - UV_COMPILE_BYTECODE=1: Precompile bytecode for faster app startup
# - UV_PYTHON_DOWNLOADS=never: Use system python from base image
# - DATA_DIR: Default location for JSON single-source-of-truth datastore
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never \
    DATA_DIR="/app/data/db"

WORKDIR /app

# Install Python dependencies strictly locked from uv.lock
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Add virtual environment to PATH and set canonical PYTHONPATH root (E4)
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app"

# Copy application code, scripts, and non-sensitive sample data (A7)
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY data/staff_sample.csv ./data/staff_sample.csv

# Copy compiled React frontend from frontend-builder stage
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Security hardening:
# 1. Pre-create database directories so appuser has full write ownership
# 2. Run as non-root system user (UID 10001)
RUN mkdir -p /app/data/db/staff /app/data/db/absences /app/data/db/schedules /app/data/db/jobs /app/data/db/preassigned \
    && chmod +x /app/scripts/entrypoint.sh \
    && groupadd -r appuser && useradd -r -g appuser -u 10001 -m -d /app appuser \
    && chown -R appuser:appuser /app

USER appuser

# Expose default port
EXPOSE 8080

# Healthcheck: probes FastAPI health endpoint using Python stdlib (Finding E4)
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python3 /app/scripts/healthcheck.py

# Launch container via entrypoint script for clean PID 1 signal propagation
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
