#!/bin/sh
set -e

# Fall back to default port 8080 if not supplied by Cloud Run
PORT="${PORT:-8080}"
APP_TARGET="${APP_TARGET:-fastapi}"

echo "=========================================================="
echo " Starting Dienstplan Container"
echo " Target Application : ${APP_TARGET}"
echo " Listening Port     : ${PORT}"
echo " Working Directory  : $(pwd)"
echo " Process UID        : $(id -u):$(id -g)"
echo "=========================================================="

# Ensure persistent storage directory exists for the non-root user
mkdir -p /app/data/db/staff /app/data/db/absences /app/data/db/schedules

if [ "${APP_TARGET}" = "streamlit" ]; then
    echo "Launching Streamlit server..."
    # 'exec' replaces the shell process so Streamlit receives SIGTERM directly
    exec streamlit run app/streamlit_app.py \
        --server.port="${PORT}" \
        --server.address=0.0.0.0 \
        --server.headless=true \
        --browser.gatherUsageStats=false \
        --server.enableCORS=false \
        --server.enableXsrfProtection=false
else
    echo "Launching FastAPI server via Uvicorn..."
    # 'exec' ensures Uvicorn runs as PID 1 for graceful shutdown.
    # --proxy-headers and --forwarded-allow-ips ensure Cloud Run TLS/host headers are preserved.
    exec uvicorn app.api.main:app \
        --host 0.0.0.0 \
        --port "${PORT}" \
        --proxy-headers \
        --forwarded-allow-ips "*"
fi

