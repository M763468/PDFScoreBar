#!/bin/bash
set -euo pipefail

CONTAINER_NAME="pdf_score_dev_gpu"
PROJECT_PATH="/workspace"

status() {
  docker inspect -f '{{.State.Status}}' "$CONTAINER_NAME" 2>/dev/null || echo "not-found"
}

current_status=$(status)

echo "[1/4] Container status: $current_status"
if [ "$current_status" = "exited" ] || [ "$current_status" = "created" ] || [ "$current_status" = "dead" ]; then
  echo "        -> starting $CONTAINER_NAME"
  docker start "$CONTAINER_NAME" >/dev/null
  current_status=$(status)
  echo "        -> status after start: $current_status"
elif [ "$current_status" = "running" ]; then
  echo "        -> already running"
elif [ "$current_status" = "not-found" ]; then
  echo "ERROR: container $CONTAINER_NAME not found"
  exit 1
else
  echo "WARNING: unexpected status $current_status"
fi

if [ "$current_status" != "running" ]; then
  echo "ERROR: container is not running"
  exit 1
fi

echo "[2/4] Checking Python inside container"
docker exec "$CONTAINER_NAME" python --version

echo "[3/4] Verifying project mount at $PROJECT_PATH"
docker exec "$CONTAINER_NAME" ls "$PROJECT_PATH" | head -n 10

echo "[4/4] Checking optional tooling (pytest)"
if ! docker exec "$CONTAINER_NAME" command -v pytest >/dev/null 2>&1; then
  echo "  pytest: not installed"
else
  docker exec "$CONTAINER_NAME" pytest --version
fi

echo "✅ Environment check complete."
