#!/usr/bin/env bash
set -euo pipefail

archive=$1
name=$2
stage=$(mktemp -d)
trap 'rm -rf -- "$stage"' EXIT
tar -xzf "$archive" -C "$stage"
if [[ $name == linux-master ]]; then
  test -x "$stage/$name/CodexAgentHarness-Master.x86_64"
  binary="$stage/$name/backend/codex-agent-harness-master"
elif [[ $name == linux-slave ]]; then
  binary="$stage/$name/codex-agent-harness-slave/codex-agent-harness-slave"
else
  echo "Unknown package: $name" >&2
  exit 2
fi
test -x "$binary"
"$binary" --help >/dev/null
echo "$name archive OK"
