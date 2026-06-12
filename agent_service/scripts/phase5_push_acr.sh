#!/usr/bin/env bash
# Phase 5 — build and push SuburbScout Hosted Agent image to ACR.
#
# Prereqs: az login, ACR created, AcrPush on your user.
#
# Usage:
#   export ACR_NAME=suburbscoutacr        # no .azurecr.io suffix
#   export IMAGE_TAG=v1
#   bash scripts/phase5_push_acr.sh
#
# Cloud build (recommended on Apple Silicon — builds linux/amd64 in Azure):
#   USE_ACR_BUILD=1 bash scripts/phase5_push_acr.sh

set -euo pipefail

cd "$(dirname "$0")/.."

ACR_NAME="${ACR_NAME:?Set ACR_NAME (e.g. suburbscoutacr)}"
IMAGE_TAG="${IMAGE_TAG:-v1}"
IMAGE_REPO="${IMAGE_REPO:-suburbscout-hosted}"
FULL_IMAGE="${ACR_NAME}.azurecr.io/${IMAGE_REPO}:${IMAGE_TAG}"

if [[ "${USE_ACR_BUILD:-0}" == "1" ]]; then
  echo "=== ACR cloud build: ${FULL_IMAGE} ==="
  az acr build \
    --registry "$ACR_NAME" \
    --image "${IMAGE_REPO}:${IMAGE_TAG}" \
    --platform linux/amd64 \
    --file Dockerfile.hosted \
    .
else
  echo "=== Local docker build (linux/amd64): ${FULL_IMAGE} ==="
  docker build --platform linux/amd64 -f Dockerfile.hosted -t "${IMAGE_REPO}:${IMAGE_TAG}" .
  az acr login --name "$ACR_NAME"
  docker tag "${IMAGE_REPO}:${IMAGE_TAG}" "$FULL_IMAGE"
  docker push "$FULL_IMAGE"
fi

echo ""
echo "Pushed: ${FULL_IMAGE}"
echo "Next:   python scripts/phase6_deploy_foundry.py --image ${FULL_IMAGE}"
