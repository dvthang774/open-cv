#!/usr/bin/env sh
set -eu

# This entrypoint optionally syncs a YOLO model from MinIO/S3 into a container cache.
# It then exports VP_YOLO_MODEL to the cached file path (unless already set),
# and finally execs the worker command.

AI_MODE="${VP_AI_MODE:-stub}"

if [ "${AI_MODE}" = "yolo" ]; then
  BUCKET="${VP_MODEL_S3_BUCKET:-models}"
  KEY="${VP_MODEL_S3_KEY:-}"
  CACHE_DIR="${VP_MODEL_CACHE_DIR:-/var/cache/vp-models}"

  if [ -z "${KEY}" ]; then
    echo "VP_AI_MODE=yolo but VP_MODEL_S3_KEY is empty. Set VP_MODEL_S3_KEY (e.g. yolov8_v1.pt)." >&2
    exit 2
  fi

  mkdir -p "${CACHE_DIR}"
  python -m app.tools.sync_model --bucket "${BUCKET}" --key "${KEY}" --cache-dir "${CACHE_DIR}"

  CACHED_PATH="${CACHE_DIR}/${KEY}"
  if [ -z "${VP_YOLO_MODEL:-}" ]; then
    export VP_YOLO_MODEL="${CACHED_PATH}"
  fi
fi

exec "$@"
