#!/usr/bin/env bash
# Deploy compiled React SPA to Firebase Hosting CDN
set -euo pipefail

# Ensure node/npm are on PATH if in nvm
if [ -d "$HOME/.nvm/versions/node/v24.14.1/bin" ]; then
    export PATH="$HOME/.nvm/versions/node/v24.14.1/bin:$PATH"
fi

PROJECT_ID="${PROJECT_ID:-tierklinik-trillig}"

echo "=========================================================="
echo " Building and Deploying Frontend to Firebase Hosting"
echo " Project: ${PROJECT_ID}"
echo "=========================================================="

echo "1. Building frontend production bundle via Vite..."
(cd frontend && npm run build)

echo "2. Deploying to Firebase Hosting..."
npx firebase-tools deploy --only hosting --project="${PROJECT_ID}"

echo "=========================================================="
echo " Firebase Hosting Deployment Complete!"
echo " Portal URL: https://dienstplan-tierklinik-trillig.web.app"
echo "=========================================================="
