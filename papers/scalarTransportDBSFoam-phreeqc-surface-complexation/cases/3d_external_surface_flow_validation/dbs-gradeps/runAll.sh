#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

repo_root="$(cd ../../../../.. && pwd)"

if [ -f "$repo_root/etc/bashrc" ]; then
  set +e
  set +u
  # shellcheck disable=SC1090
  source "$repo_root/etc/bashrc"
  set -e
  set -u
fi

echo "=== Run: 3D external DBS grad-eps flow case ==="
./createMesh.sh
./initCaseFlow.sh
./runCaseFlow.sh
./processFlow.sh
./initCaseReactiveTransport.sh
rm -f 0/aSurf processor*/0/aSurf
./runCaseReactiveTransport.sh
./processReactiveTransport.sh
echo "=== Completed: 3D external DBS grad-eps flow case ==="
