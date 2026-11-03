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
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=8080 \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_PYTHON_DOWNLOADS=never

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

# Copy application code and sample data
COPY app/ ./app/
COPY data/ ./data/

# Security hardening: run as a non-root system user
RUN groupadd -r appuser && useradd -r -g appuser -u 10001 -m -d /app appuser \
    && chown -R appuser:appuser /app

USER appuser

# Expose default port
EXPOSE 8080

# Health check probing Streamlit's built-in health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl --fail http://localhost:${PORT}/_stcore/health || exit 1

# Execute Streamlit with exec for clean signal handling (SIGTERM propagation in Cloud Run)
ENTRYPOINT ["sh", "-c", "exec streamlit run app/streamlit_app.py --server.port=${PORT} --server.address=0.0.0.0 --server.headless=true --browser.gatherUsageStats=false --server.enableCORS=false --server.enableXsrfProtection=false"]
