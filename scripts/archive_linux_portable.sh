#!/usr/bin/env bash
set -euo pipefail

if [[ $# != 2 ]]; then
  echo 'usage: archive_linux_portable.sh PACKAGE_DIRECTORY OUTPUT_TAR_GZ' >&2
  exit 2
fi
package_dir=$(realpath -- "$1")
archive=$(realpath -m -- "$2")
name=$(basename -- "$package_dir")
if [[ $name != linux-master && $name != linux-slave ]]; then
  echo "Unexpected Linux package name: $name" >&2
  exit 2
fi
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
cp -a -- "$package_dir" "$stage/$name"
find "$stage/$name" -type d -exec chmod 755 {} +
find "$stage/$name" -type f -exec chmod 644 {} +
if [[ $name == linux-master ]]; then
  chmod 755 "$stage/$name/CodexAgentHarness-Master.x86_64"
  chmod 755 "$stage/$name/backend/codex-agent-harness-master"
else
  chmod 755 "$stage/$name/codex-agent-harness-slave/codex-agent-harness-slave"
fi
find "$stage/$name" -type f \( -name '*.so' -o -name '*.so.*' \) -exec chmod 755 {} +
tar -C "$stage" -czf "$archive" "$name"
sha256sum "$archive"
