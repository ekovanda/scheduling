#!/usr/bin/env bash
# Deploy Dienstplan Generator to Google Cloud Run
set -euo pipefail

# Ensure gcloud is on PATH if in standard user location
if [ -d "$HOME/google-cloud-sdk/bin" ]; then
    export PATH="$HOME/google-cloud-sdk/bin:$PATH"
fi

# 1. Parse CLI Target Flags (--dev or --prod)
TARGET="prod"
APP_TARGET="fastapi"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --dev)
      TARGET="dev"
      shift
      ;;
    --prod)
      TARGET="prod"
      shift
      ;;
    --legacy-streamlit|--streamlit)
      APP_TARGET="streamlit"
      shift
      ;;
    -h|--help)
      echo "Usage: $0 [--dev | --prod] [--legacy-streamlit]"
      echo "  --prod              Deploy production app to 'dienstplan-app' (FastAPI + React SPA, default)"
      echo "  --dev               Deploy to 'dienstplan-dev' (FastAPI + React SPA)"
      echo "  --legacy-streamlit  Deploy legacy Streamlit UI for temporary fallback"
      exit 0
      ;;
    *)
      echo "Unknown flag: $1"
      echo "Run '$0 --help' for usage."
      exit 1
      ;;
  esac
done

PROJECT_ID="${PROJECT_ID:-tierklinik-trillig}"
REGION="${REGION:-europe-west3}"
REPOSITORY="${REPOSITORY:-dienstplan-repo}"
IMAGE_TAG="${IMAGE_TAG:-latest}"

if [ "$TARGET" = "dev" ]; then
    SERVICE_NAME="${SERVICE_NAME:-dienstplan-dev}"
    AUTH_REQUIRED="${AUTH_REQUIRED:-true}"
    STORAGE_BACKEND="${STORAGE_BACKEND:-file}"
    FIRESTORE_COLLECTION_PREFIX="${FIRESTORE_COLLECTION_PREFIX:-dev_}"
else
    SERVICE_NAME="${SERVICE_NAME:-dienstplan-app}"
    AUTH_REQUIRED="${AUTH_REQUIRED:-true}"
    STORAGE_BACKEND="${STORAGE_BACKEND:-firestore}"
    FIRESTORE_COLLECTION_PREFIX="${FIRESTORE_COLLECTION_PREFIX:-}"
fi

IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${SERVICE_NAME}:${IMAGE_TAG}"

echo "=========================================================="
echo " Deploying Dienstplan App to GCP Cloud Run"
echo " Target Mode:   ${TARGET} (APP_TARGET=${APP_TARGET})"
echo " Auth Enforced: ${AUTH_REQUIRED}"
echo " Storage Mode:  ${STORAGE_BACKEND}"
echo " Project:       ${PROJECT_ID}"
echo " Region:        ${REGION}"
echo " Service:       ${SERVICE_NAME}"
echo " Image:         ${IMAGE_NAME}"
echo "=========================================================="

# 2. Environment Variables Configuration
ENV_VARS_LIST=(
  "APP_TARGET=${APP_TARGET}"
  "STORAGE_BACKEND=${STORAGE_BACKEND}"
  "AUTH_REQUIRED=${AUTH_REQUIRED}"
  "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}"
  "GCP_PROJECT=${PROJECT_ID}"
)

if [ -n "${FIRESTORE_COLLECTION_PREFIX}" ]; then
  ENV_VARS_LIST+=("FIRESTORE_COLLECTION_PREFIX=${FIRESTORE_COLLECTION_PREFIX}")
fi

if [ -n "${FIRESTORE_DATABASE:-}" ]; then
  ENV_VARS_LIST+=("FIRESTORE_DATABASE=${FIRESTORE_DATABASE}")
fi

# Ensure multi-instance Cloud Run shares a persistent SESSION_SECRET (A4)
if [ -n "${SESSION_SECRET:-}" ]; then
  ENV_VARS_LIST+=("SESSION_SECRET=${SESSION_SECRET}")
else
  SESSION_SECRET=$(openssl rand -hex 32 2>/dev/null || python3 -c 'import secrets; print(secrets.token_hex(32))')
  ENV_VARS_LIST+=("SESSION_SECRET=${SESSION_SECRET}")
fi

if [ -n "${APP_PASSWORD:-}" ]; then
    echo "Hashing provided APP_PASSWORD..."
    PASSWORD_HASH=$(echo -n "${APP_PASSWORD}" | sha256sum | awk '{print $1}')
    ENV_VARS_LIST+=("PASSWORD_HASH=${PASSWORD_HASH}")
elif [ -n "${PASSWORD_HASH:-}" ]; then
    ENV_VARS_LIST+=("PASSWORD_HASH=${PASSWORD_HASH}")
elif [ "${AUTH_REQUIRED}" = "true" ]; then
    echo "ERROR: AUTH_REQUIRED is 'true' but neither APP_PASSWORD nor PASSWORD_HASH is configured." >&2
    echo "Aborting deployment to prevent deploying an inaccessible or fail-open service." >&2
    exit 1
fi

ENV_VARS_CSV=$(IFS=,; echo "${ENV_VARS_LIST[*]}")

# 3. Build and Push Container via Google Cloud Build (guarantees native linux/amd64 target)
echo "Submitting build to Google Cloud Build (native linux/amd64)..."
gcloud builds submit \
    --tag="${IMAGE_NAME}" \
    --project="${PROJECT_ID}" \
    .

# 4. Deploy to Cloud Run
echo "Deploying to Cloud Run..."
gcloud run deploy "${SERVICE_NAME}" \
    --image="${IMAGE_NAME}" \
    --platform=managed \
    --region="${REGION}" \
    --project="${PROJECT_ID}" \
    --cpu=2 \
    --memory=4Gi \
    --no-cpu-throttling \
    --timeout=900s \
    --concurrency=2 \
    --session-affinity \
    --min-instances=1 \
    --max-instances=1 \
    --set-env-vars="${ENV_VARS_CSV}" \
    --allow-unauthenticated

echo "=========================================================="
echo " Deployment Complete!"
echo " Service URL:"
gcloud run services describe "${SERVICE_NAME}" --platform=managed --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)'
echo "=========================================================="
