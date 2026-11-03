#!/usr/bin/env bash
# Deploy Dienstplan Generator to Google Cloud Run
set -euo pipefail

# Ensure gcloud is on PATH if in standard user location
if [ -d "$HOME/google-cloud-sdk/bin" ]; then
    export PATH="$HOME/google-cloud-sdk/bin:$PATH"
fi

PROJECT_ID="${PROJECT_ID:-tierklinik-trillig}"
REGION="${REGION:-europe-west3}"
REPOSITORY="${REPOSITORY:-dienstplan-repo}"
SERVICE_NAME="${SERVICE_NAME:-dienstplan-app}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPOSITORY}/${SERVICE_NAME}:${IMAGE_TAG}"

echo "=========================================================="
echo " Deploying Dienstplan App to GCP Cloud Run"
echo " Project:    ${PROJECT_ID}"
echo " Region:     ${REGION}"
echo " Service:    ${SERVICE_NAME}"
echo " Image:      ${IMAGE_NAME}"
echo "=========================================================="

# 1. Handle Password Configuration
PASSWORD_HASH_ARG=()
if [ -n "${APP_PASSWORD:-}" ]; then
    echo "Hashing provided APP_PASSWORD..."
    PASSWORD_HASH=$(echo -n "${APP_PASSWORD}" | sha256sum | awk '{print $1}')
    PASSWORD_HASH_ARG=("--set-env-vars=PASSWORD_HASH=${PASSWORD_HASH}")
elif [ -n "${PASSWORD_HASH:-}" ]; then
    PASSWORD_HASH_ARG=("--set-env-vars=PASSWORD_HASH=${PASSWORD_HASH}")
else
    echo "Notice: No APP_PASSWORD or PASSWORD_HASH specified."
    echo "App will start without password gate. You can set it later via: "
    echo "  gcloud run services update ${SERVICE_NAME} --region=${REGION} --project=${PROJECT_ID} --update-env-vars=PASSWORD_HASH=<hash>"
fi

# 2. Build and Push Container via Google Cloud Build (guarantees native linux/amd64 target)
echo "Submitting build to Google Cloud Build (native linux/amd64)..."
gcloud builds submit \
    --tag="${IMAGE_NAME}" \
    --project="${PROJECT_ID}" \
    .

# 3. Deploy to Cloud Run
echo "Deploying to Cloud Run..."
DEPLOY_CMD=(
    gcloud run deploy "${SERVICE_NAME}"
    --image="${IMAGE_NAME}"
    --platform=managed
    --region="${REGION}"
    --project="${PROJECT_ID}"
    --cpu=2
    --memory=2Gi
    --timeout=300s
    --concurrency=10
    --session-affinity
    --min-instances=0
    --max-instances=3
    --allow-unauthenticated
)

if [ ${#PASSWORD_HASH_ARG[@]} -gt 0 ]; then
    DEPLOY_CMD+=("${PASSWORD_HASH_ARG[@]}")
fi

"${DEPLOY_CMD[@]}"

echo "=========================================================="
echo " Deployment Complete!"
echo " Service URL:"
gcloud run services describe "${SERVICE_NAME}" --platform=managed --region="${REGION}" --project="${PROJECT_ID}" --format='value(status.url)'
echo "=========================================================="

