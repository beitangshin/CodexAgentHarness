#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
dist_dir=${1:-"$repo_root/dist/portable"}
only_role=${2:-all}
mkdir -p "$dist_dir"

# Some build hosts provide psutil only as a distribution package. Keep the
# active virtual environment first so its Pydantic dependencies win.
if ! python -c 'import psutil' >/dev/null 2>&1; then
  venv_site=$(python -c 'import sysconfig; print(sysconfig.get_paths()["purelib"])')
  export PYTHONPATH="$venv_site:/usr/lib/python3/dist-packages${PYTHONPATH:+:$PYTHONPATH}"
fi

build_one() {
  local role=$1
  local entry=$2
  local target="$dist_dir/linux-$role"
  mkdir -p "$target"
  local imports=(--hidden-import codex_agent_harness.managed)
  if [[ $role == master ]]; then
    imports+=(--hidden-import codex_agent_harness.server --collect-data codex_agent_harness)
  else
    imports+=(--hidden-import codex_agent_harness.gui)
  fi
  python -m PyInstaller --noconfirm --clean --onedir \
    --name "codex-agent-harness-$role" \
    --paths "$repo_root" \
    "${imports[@]}" \
    --distpath "$target" \
    --workpath "$repo_root/build/pyinstaller-linux-$role" \
    --specpath "$repo_root/build/pyinstaller-spec-linux-$role" \
    "$repo_root/$entry"
  "$target/codex-agent-harness-$role/codex-agent-harness-$role" --help >/dev/null
}

if [[ $only_role == all || $only_role == slave ]]; then
  build_one slave codex_agent_harness/__main__.py
fi
if [[ $only_role == all || $only_role == master ]]; then
  build_one master codex_agent_harness/master_entry.py
fi

if [[ -n ${GODOT_BIN:-} && ( $only_role == all || $only_role == master ) ]]; then
  "$GODOT_BIN" --headless --path "$repo_root/godot_master" \
    --export-release Linux "$dist_dir/linux-master/CodexAgentHarness-Master.x86_64"
  master_root=$(realpath -- "$dist_dir/linux-master")
  source_backend="$master_root/codex-agent-harness-master"
  target_backend="$master_root/backend"
  if [[ -d $source_backend ]]; then
    if [[ -d $target_backend ]]; then
      rm -rf -- "$target_backend"
    fi
    mv -- "$source_backend" "$target_backend"
  fi
fi
