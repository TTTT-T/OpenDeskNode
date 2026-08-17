#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

required_files=(
  README.md
  LICENSE
  THIRD_PARTY_NOTICES.md
  LICENSES/OFL-1.1.txt
  CHANGELOG.md
  SECURITY.md
  .gitignore
)
for file in "${required_files[@]}"; do
  [[ -s "$file" ]] || { echo "Missing public release file: $file" >&2; exit 1; }
done

rg -q '^# OpenDeskNode$' README.md
rg -q '^\*\*Version:\*\* v0\.1\.0' README.md
rg -q '^\*\*Release:\*\* Stock Dashboard$' README.md
rg -q 'set\(PROJECT_VER "0\.1\.0"\)' firmware/product/CMakeLists.txt
rg -q 'Apache License' LICENSE

forbidden='TerrenceNAS|terrencenas|192\.168\.31\.209|CACHEDEV3_DATA|usbmodem3101|TTT-Macmini'
if git grep -n -I -E "$forbidden" -- \
  ':!firmware/xiaozhi/**' ':!scripts/verify-public-release.sh'; then
  echo "Private deployment identifier remains in the public tree" >&2
  exit 1
fi

if git ls-files | rg -q '(^|/)(\.env|[^/]*\.(sqlite3?|db|log))$'; then
  echo "A local environment, database, or log file is tracked" >&2
  exit 1
fi

if git grep -n -I -E '(OPENAI_API_KEY|TUSHARE_TOKEN)=[^[:space:]]+' -- .; then
  echo "A non-empty API credential assignment is tracked" >&2
  exit 1
fi

git diff --check
git diff --cached --check
echo "OPEN_DESK_NODE_PUBLIC_RELEASE_CHECKS_OK"
