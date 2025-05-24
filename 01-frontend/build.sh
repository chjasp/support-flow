#!/usr/bin/env bash
set -euo pipefail

# ---- config ----
PROJECT_ID="main-dev-431619"
REGION="europe-west3"
REPO_NAME="frontend"
IMAGE_TAG="dev"
TFVARS_FILE="../05-infra/dev.tfvars"
# ---------------

IMAGE_BASE="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_TAG}"
IMAGE_LATEST="${IMAGE_BASE}:latest"

echo "▶ Building ${IMAGE_LATEST}"
docker build --platform=linux/amd64 -t "${IMAGE_LATEST}" .

echo "▶ Pushing ${IMAGE_LATEST}"
PUSH_OUTPUT=$(docker push "${IMAGE_LATEST}")
DIGEST=$(echo "${PUSH_OUTPUT}" | grep -o 'sha256:[a-f0-9]*' | head -n1)

NEW_PATH="${IMAGE_BASE}@${DIGEST}"
echo "▶ Updating ${TFVARS_FILE} → frontend_image_path = \"${NEW_PATH}\""
sed -i.bak "s|^frontend_image_path.*|frontend_image_path = \"${NEW_PATH}\"|" "${TFVARS_FILE}"
rm -f "${TFVARS_FILE}.bak"