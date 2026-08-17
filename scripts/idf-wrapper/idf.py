#!/usr/bin/env bash
set -euo pipefail

: "${XIAOZHI_REAL_IDF_PY:?XIAOZHI_REAL_IDF_PY is required}"
: "${XIAOZHI_BUILD_DIR:?XIAOZHI_BUILD_DIR is required}"

exec "$XIAOZHI_REAL_IDF_PY" -B "$XIAOZHI_BUILD_DIR" "$@"
