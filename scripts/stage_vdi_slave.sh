#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 2 ]]; then
  echo 'usage: stage_vdi_slave.sh PORTABLE_LINUX_SLAVE_DIRECTORY LAPTOP_RELEASE_DIRECTORY' >&2
  exit 2
fi
package=$(realpath -- "$1")
release=$(realpath -- "$2")
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
name=codex-agent-harness-linux-x86_64
cp -a -- "$package/codex-agent-harness-slave" "$stage/$name"
mv -- "$stage/$name/codex-agent-harness-slave" "$stage/$name/$name"
find "$stage/$name" -type d -exec chmod 755 {} +
find "$stage/$name" -type f -exec chmod 644 {} +
find "$stage/$name" -type f \( -name '*.so' -o -name '*.so.*' \) -exec chmod 755 {} +
chmod 755 "$stage/$name/$name"
"$stage/$name/$name" --help >/dev/null

archive="$release/$name-onedir.tar.gz"
if [[ -f $archive ]]; then
  prior_hash=$(sha256sum "$archive" | cut -d' ' -f1)
  cp -p -- "$archive" "$release/archive-$prior_hash.tar.gz"
fi
temporary="$release/.$name-onedir.tar.gz.$$.tmp"
tar -C "$stage" -czf "$temporary" "$name"
mv -f -- "$temporary" "$archive"
(cd "$release" && sha256sum "$name-onedir.tar.gz" > "$name-onedir.tar.gz.sha256")
sha256sum "$archive"
