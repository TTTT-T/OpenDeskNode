#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
firmware_dir="$repo_root/firmware/xiaozhi"

expected_remote="https://github.com/78/xiaozhi-esp32.git"
actual_remote="$(git -C "$repo_root" remote get-url xiaozhi-upstream)"
[[ "$actual_remote" == "$expected_remote" ]]

rg -q 'set\(PROJECT_VER "2\.4\.2"\)' "$firmware_dir/CMakeLists.txt"
rg -q '"type": "esp32-s3-rlcd-4\.2"' \
  "$firmware_dir/main/boards/waveshare/esp32-s3-rlcd-4.2/config.json"
rg -q 'CONFIG_USE_DEVICE_AEC=y' \
  "$firmware_dir/main/boards/waveshare/esp32-s3-rlcd-4.2/config.json"

python3 -m unittest discover -s "$firmware_dir/scripts/tests" -v

python3 - "$repo_root" <<'PY'
import pathlib
import re
import sys

root = pathlib.Path(sys.argv[1])
missing = []
pattern = re.compile(r"\[[^\]]+\]\(([^)]+)\)")
paths = [root / "AGENTS.md", root / "README.md"]
paths.extend((root / "docs").rglob("*.md"))
for path in paths:
    if not path.exists():
        continue
    text = path.read_text(encoding="utf-8")
    for target in pattern.findall(text):
        target = target.split("#", 1)[0]
        if not target or "://" in target or target.startswith("mailto:"):
            continue
        if not (path.parent / target).resolve().exists():
            missing.append(f"{path.relative_to(root)} -> {target}")
if missing:
    print("Missing local Markdown links:", *missing, sep="\n", file=sys.stderr)
    raise SystemExit(1)
print("LOCAL_LINKS_OK")
PY

git -C "$repo_root" diff --check
echo "PHASE_0A_STATIC_CHECKS_OK"
