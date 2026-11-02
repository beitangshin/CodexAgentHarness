#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
dist_dir=${1:-"$repo_root/dist/linux"}
mkdir -p "$dist_dir"

python -m PyInstaller --noconfirm --clean --onedir \
  --name codex-agent-harness-linux-x86_64 \
  --paths "$repo_root" \
  --hidden-import codex_agent_harness.gui \
  --distpath "$dist_dir" \
  --workpath "$repo_root/build/pyinstaller-linux-onedir" \
  --specpath "$repo_root/build/pyinstaller-spec-onedir" \
  "$repo_root/codex_agent_harness/__main__.py"

tar -C "$dist_dir" -czf "$dist_dir/codex-agent-harness-linux-x86_64-onedir.tar.gz" \
  codex-agent-harness-linux-x86_64
(cd "$dist_dir" && sha256sum codex-agent-harness-linux-x86_64-onedir.tar.gz \
  > codex-agent-harness-linux-x86_64-onedir.tar.gz.sha256)
cp "$repo_root/scripts/install_linux_onedir.sh" "$dist_dir/install-linux-onedir.sh"
