#!/usr/bin/env bash
# Deploy Dienstplan Generator to Google Cloud Run
set -euo pipefail

# Ensure gcloud is on PATH if in standard user location
if [ -d "$HOME/google-cloud-sdk/bin" ]; then
    export PATH="$HOME/google-cloud-sdk/bin:$PATH"
fi

# 1. Parse CLI Target Flags (--dev or --prod)
TARGET="prod"

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
    -h|--help)
      echo "Usage: $0 [--dev | --prod]"
      echo "  --dev   Deploy modernization API to 'dienstplan-dev' with APP_TARGET=fastapi"
      echo "  --prod  Deploy stable application to 'dienstplan-app' with APP_TARGET=streamlit (default)"
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
    APP_TARGET="fastapi"
else
    SERVICE_NAME="${SERVICE_NAME:-dienstplan-app}"
    APP_TARGET="streamlit"
fi

IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${SERVICE_NAME}:${IMAGE_TAG}"

echo "=========================================================="
echo " Deploying Dienstplan App to GCP Cloud Run"
echo " Target Mode: ${TARGET} (APP_TARGET=${APP_TARGET})"
echo " Project:     ${PROJECT_ID}"
echo " Region:      ${REGION}"
echo " Service:     ${SERVICE_NAME}"
echo " Image:       ${IMAGE_NAME}"
echo "=========================================================="

# 2. Environment Variables Configuration
STORAGE_BACKEND="${STORAGE_BACKEND:-firestore}"
ENV_VARS_LIST=("APP_TARGET=${APP_TARGET}" "STORAGE_BACKEND=${STORAGE_BACKEND}" "GOOGLE_CLOUD_PROJECT=${PROJECT_ID}" "GCP_PROJECT=${PROJECT_ID}")

if [ -n "${APP_PASSWORD:-}" ]; then
    echo "Hashing provided APP_PASSWORD..."
    PASSWORD_HASH=$(echo -n "${APP_PASSWORD}" | sha256sum | awk '{print $1}')
    ENV_VARS_LIST+=("PASSWORD_HASH=${PASSWORD_HASH}")
elif [ -n "${PASSWORD_HASH:-}" ]; then
    ENV_VARS_LIST+=("PASSWORD_HASH=${PASSWORD_HASH}")
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
    --min-instances=0 \
    --max-instances=3 \
    --set-env-vars="${ENV_VARS_CSV}" \
    --allow-unauthenticated

echo "=========================================================="
echo " Deployment Complete!"
echo " Service URL:"
gcloud run services describe "${SERVICE_NAME}" --platform=managed --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)'
echo "=========================================================="
