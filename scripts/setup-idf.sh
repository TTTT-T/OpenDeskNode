#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
idf_dir="$repo_root/.tools/esp-idf-v6.0.2"
idf_tools_dir="$repo_root/.tools/espressif-tools"
expected_commit="7101770dc6db2667b3c477cc31365dd1acd6db4e"

mkdir -p "$repo_root/.tools"

if [[ ! -d "$idf_dir/.git" ]]; then
  git clone \
    --branch v6.0.2 \
    --depth 1 \
    --recursive \
    --shallow-submodules \
    https://github.com/espressif/esp-idf.git \
    "$idf_dir"
fi

actual_version="$(git -C "$idf_dir" describe --tags --always)"
if [[ "$actual_version" != "v6.0.2" ]]; then
  echo "Expected ESP-IDF v6.0.2, found $actual_version" >&2
  exit 1
fi
actual_commit="$(git -C "$idf_dir" rev-parse HEAD)"
if [[ "$actual_commit" != "$expected_commit" ]]; then
  echo "Expected ESP-IDF $expected_commit, found $actual_commit" >&2
  exit 1
fi

if git -C "$idf_dir" submodule status --recursive | rg -q '^[-+U]'; then
  git -C "$idf_dir" submodule update --init --recursive --depth 1
fi
if git -C "$idf_dir" submodule status --recursive | rg -q '^[-+U]'; then
  echo "ESP-IDF contains missing or mismatched submodules" >&2
  exit 1
fi

export IDF_TOOLS_PATH="$idf_tools_dir"
"$idf_dir/install.sh" esp32s3
source "$idf_dir/export.sh" >/dev/null
python "$idf_dir/tools/idf_tools.py" install cmake ninja
echo "ESP-IDF $actual_version is ready in $idf_dir"
