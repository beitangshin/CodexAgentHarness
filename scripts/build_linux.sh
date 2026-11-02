#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
dist_dir=${1:-"$repo_root/dist/linux"}

python -m PyInstaller --noconfirm --clean --onefile \
  --name codex-agent-harness-linux-x86_64 \
  --paths "$repo_root" \
  --hidden-import codex_agent_harness.gui \
  --distpath "$dist_dir" \
  --workpath "$repo_root/build/pyinstaller-linux" \
  --specpath "$repo_root/build/pyinstaller-spec" \
  "$repo_root/codex_agent_harness/__main__.py"
