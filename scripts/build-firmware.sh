#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
idf_dir="$repo_root/.tools/esp-idf-v6.0.2"
idf_tools_dir="$repo_root/.tools/espressif-tools"
firmware_dir="$repo_root/firmware/xiaozhi"
ascii_build_dir="${XIAOZHI_BUILD_DIR:-/private/tmp/esp32-s3-rlcd-4.2-build}"
artifact="$ascii_build_dir/merged-binary.bin"

if [[ ! -f "$idf_dir/export.sh" ]]; then
  echo "ESP-IDF is missing. Run: bash scripts/setup-idf.sh" >&2
  exit 1
fi

export IDF_TOOLS_PATH="$idf_tools_dir"
source "$idf_dir/export.sh" >/dev/null

idf_version="$(idf.py --version)"
if [[ "$idf_version" != "ESP-IDF v6.0.2" ]]; then
  echo "Expected ESP-IDF v6.0.2, found $idf_version" >&2
  exit 1
fi

if [[ "$ascii_build_dir" != /private/tmp/* ]]; then
  echo "XIAOZHI_BUILD_DIR must be an explicit child of /private/tmp" >&2
  exit 1
fi
if [[ "$ascii_build_dir" == *[![:ascii:]]* ]]; then
  echo "XIAOZHI_BUILD_DIR must contain ASCII characters only" >&2
  exit 1
fi

mkdir -p "$ascii_build_dir"
export XIAOZHI_REAL_IDF_PY="$(command -v idf.py)"
export XIAOZHI_BUILD_DIR="$ascii_build_dir"
export PATH="$repo_root/scripts/idf-wrapper:$PATH"

cd "$firmware_dir"
python scripts/build.py waveshare/esp32-s3-rlcd-4.2 --name esp32-s3-rlcd-4.2

if [[ ! -s "$artifact" ]]; then
  echo "Build did not produce $artifact" >&2
  exit 1
fi

shasum -a 256 "$artifact"
