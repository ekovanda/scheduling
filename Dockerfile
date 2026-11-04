# syntax=docker/dockerfile:1
FROM python:3.12-slim

# Copy uv binary from official Astral uv image
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

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

# Install minimal OS utilities needed for container healthcheck
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies strictly locked from uv.lock
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Add virtual environment and app directories to PATH and PYTHONPATH
ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONPATH="/app:/app/app"

# Copy application code, scripts, and sample data
COPY app/ ./app/
COPY scripts/ ./scripts/
COPY data/ ./data/

# Security hardening:
# 1. Pre-create database directories so appuser has full write ownership
# 2. Run as non-root system user (UID 10001)
RUN mkdir -p /app/data/db/staff /app/data/db/absences /app/data/db/schedules \
    && chmod +x /app/scripts/entrypoint.sh \
    && groupadd -r appuser && useradd -r -g appuser -u 10001 -m -d /app appuser \
    && chown -R appuser:appuser /app

USER appuser

# Expose default port
EXPOSE 8080

# Dual healthcheck: probes FastAPI health endpoint first, falls back to Streamlit
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:${PORT}/api/v1/health || curl --fail http://localhost:${PORT}/_stcore/health || exit 1

# Launch container via entrypoint script for clean PID 1 signal propagation
ENTRYPOINT ["/app/scripts/entrypoint.sh"]
