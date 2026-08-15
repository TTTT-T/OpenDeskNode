#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
idf_dir="$repo_root/.tools/esp-idf-v6.0.2"
idf_tools_dir="$repo_root/.tools/espressif-tools"
firmware_dir="$repo_root/firmware/product"
ascii_build_dir="${CLEAN_FIRMWARE_BUILD_DIR:-/private/tmp/esp32-s3-rlcd-4.2-clean-build}"
artifact="$ascii_build_dir/esp32_s3_rlcd_dashboard.bin"

if [[ ! -f "$idf_dir/export.sh" ]]; then
  echo "ESP-IDF is missing. Run: bash scripts/setup-idf.sh" >&2
  exit 1
fi
if [[ "$ascii_build_dir" != /private/tmp/* || "$ascii_build_dir" == *[![:ascii:]]* ]]; then
  echo "CLEAN_FIRMWARE_BUILD_DIR must be an ASCII child of /private/tmp" >&2
  exit 1
fi

export IDF_TOOLS_PATH="$idf_tools_dir"
source "$idf_dir/export.sh" >/dev/null

idf_version="$(idf.py --version)"
if [[ "$idf_version" != "ESP-IDF v6.0.2" ]]; then
  echo "Expected ESP-IDF v6.0.2, found $idf_version" >&2
  exit 1
fi

mkdir -p "$ascii_build_dir"
cd "$firmware_dir"
idf.py -B "$ascii_build_dir" build

if [[ ! -s "$artifact" ]]; then
  echo "Build did not produce $artifact" >&2
  exit 1
fi

shasum -a 256 "$artifact"
