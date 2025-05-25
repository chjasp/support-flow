#!/bin/bash

# --- Configuration ---
PROJECT_ID="main-dev-431619"
REGION="europe-west3"
REPO_NAME="ingester"
IMAGE_TAG="dev"
TFVARS_FILE="../05-infra/dev.tfvars"
# --- End Configuration ---

# Construct the full image name
IMAGE_NAME="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_TAG}"
IMAGE_NAME_LATEST="${IMAGE_NAME}:latest"

# 1. Build the Docker image
echo "Building Docker image: ${IMAGE_NAME_LATEST}"
docker build --platform linux/amd64 -t "${IMAGE_NAME_LATEST}" .
if [ $? -ne 0 ]; then
  echo "Docker build failed."
  exit 1
fi

# 2. Push the Docker image and capture output
echo "Pushing Docker image: ${IMAGE_NAME_LATEST}"
PUSH_OUTPUT=$(docker push "${IMAGE_NAME_LATEST}" 2>&1) # Capture both stdout and stderr
EXIT_CODE=$?                                         # Capture the exit code of docker push

echo "$PUSH_OUTPUT" # Print the output for visibility

if [ $EXIT_CODE -ne 0 ]; then
  echo "Docker push failed."
  exit 1
fi

# 3. Extract the SHA256 digest
# Look for the line containing 'digest: sha256:' and extract the hash
DIGEST=$(echo "$PUSH_OUTPUT" | grep -o 'sha256:[a-f0-9]*' | head -n 1)

if [ -z "$DIGEST" ]; then
  echo "Could not extract digest from docker push output."
  exit 1
fi

echo "Extracted digest: ${DIGEST}"

# 4. Update dev.tfvars
NEW_IMAGE_PATH="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO_NAME}/${IMAGE_TAG}@${DIGEST}"
echo "Updating ${TFVARS_FILE} with new image path: ${NEW_IMAGE_PATH}"

# Use sed to replace the line starting with 'ingester_image_path'
# The use of '|' as a delimiter avoids issues with '/' in the path
sed -i.bak "s|^ingester_image_path.*|ingester_image_path = \"${NEW_IMAGE_PATH}\"|" "${TFVARS_FILE}"

if [ $? -ne 0 ]; then
  echo "Failed to update ${TFVARS_FILE}."
  # Optionally restore from backup: mv "${TFVARS_FILE}.bak" "${TFVARS_FILE}"
  exit 1
fi

echo "Successfully updated ${TFVARS_FILE}."
# Remove the backup file created by sed
rm -f "${TFVARS_FILE}.bak"

exit 0