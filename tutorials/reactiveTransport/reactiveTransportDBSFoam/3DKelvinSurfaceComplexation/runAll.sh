#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

repo_root="$(cd ../../../.. && pwd)"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
  set +e
  set +u
  # shellcheck disable=SC1091
  source /usr/local/anaconda3/etc/profile.d/conda.sh
  conda activate gcfoam
  set -e
  set -u
fi

# shellcheck disable=SC1090
source "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/configure_runtime.sh"

: "${TOTAL_TIME:?Set TOTAL_TIME to the reviewed stage endpoint}"
: "${WRITE_TIMESTEP:?Set WRITE_TIMESTEP to the reviewed stage interval}"
: "${RUN_TIMESTEP:?Set RUN_TIMESTEP to the accepted timestep}"

run_task() {
  local name="$1"
  if [[ -f "$name" ]]; then
    [[ -x "$name" ]] || chmod +x "$name" || true
    echo "--- Running: $name ---"
    "./$name"
  else
    echo "--- Running command: $name ---"
    $name
  fi
  echo "--- Done: $name ---"
}

echo "=== Run: 3D Kelvin HFO Mn/Mg selective capture ==="
echo "Runtime: $GCFOAM_RUNTIME_ROOT ($(git -C "$GCFOAM_RUNTIME_ROOT" rev-parse HEAD))"
run_task createMesh.sh
run_task initCaseFlow.sh
run_task runCaseFlow.sh
run_task processFlow.sh
run_task initCaseReactiveTransport.sh
run_task runCaseReactiveTransport.sh
run_task processReactiveTransport.sh
echo "=== Completed: 3D Kelvin HFO Mn/Mg selective capture ==="
