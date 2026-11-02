#!/usr/bin/env bash
set -euo pipefail

source_host=${1:-codex-harness-laptop}
release_path=.codex-agent-harness/releases/linux/onedir
base="$HOME/.local/share/codex-agent-harness"
cache="$base/downloads"
archive=codex-agent-harness-linux-x86_64-onedir.tar.gz
mkdir -p "$cache" "$HOME/.local/bin"

scp "$source_host:$release_path/$archive" "$cache/$archive"
scp "$source_host:$release_path/$archive.sha256" "$cache/$archive.sha256"
(cd "$cache" && sha256sum -c "$archive.sha256")

hash=$(sha256sum "$cache/$archive" | cut -d' ' -f1)
release_dir="$base/releases/$hash"
mkdir -p "$release_dir"
chmod 700 "$release_dir"
tar -xzf "$cache/$archive" -C "$release_dir"
binary="$release_dir/codex-agent-harness-linux-x86_64/codex-agent-harness-linux-x86_64"
chmod 700 "$binary"
"$binary" --help >/dev/null

target="$HOME/.local/bin/codex-agent-harness"
if [ -f "$target" ] && [ ! -L "$target" ] && [ ! -e "$target.onefile.bak" ]; then
  cp -p "$target" "$target.onefile.bak"
fi
ln -sfn "$binary" "$target.next"
mv -Tf "$target.next" "$target"
printf 'INSTALLED_SHA256=%s\n' "$hash"

set -a
. "$HOME/.config/codex-agent-harness/agent.env"
set +a
exec "$target"
