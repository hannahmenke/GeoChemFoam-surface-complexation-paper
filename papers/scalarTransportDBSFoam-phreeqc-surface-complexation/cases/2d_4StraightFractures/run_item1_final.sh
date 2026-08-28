#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

if [[ -z "${ITEM1_RUNTIME_SETUP:-}" || ! -f "$ITEM1_RUNTIME_SETUP" ]]; then
    echo "Set ITEM1_RUNTIME_SETUP to the verified combined-runtime setup.sh" >&2
    exit 2
fi

# shellcheck disable=SC1090
source "$ITEM1_RUNTIME_SETUP"
export GCFOAM_RUNTIME_ROOT="$GCFOAM_DIR"
export TOTAL_TIME=20000
export WRITE_TIMESTEP=2000
export RUN_TIMESTEP=0.25
export GCFOAM_ASURF_PROCS=8

python ./record_item1_launch.py

run_stage() {
    echo "--- Running: $1 ---"
    "./$1"
    echo "--- Done: $1 ---"
}

runtime_commit="$(git -C "$GCFOAM_RUNTIME_ROOT" rev-parse HEAD)"
runtime_parent="$(git -C "$GCFOAM_RUNTIME_ROOT" rev-parse HEAD^)"
runtime_gitlink="$(git -C "$GCFOAM_RUNTIME_ROOT" ls-tree HEAD ThirdParty/PhreeqcRM | awk '{print $3}')"
adapter_commit="$(git -C "$GCFOAM_RUNTIME_ROOT/ThirdParty/PhreeqcRM" rev-parse HEAD)"
if [[ "$runtime_commit" != "3c4a34326b5573d76d48664093a1933a5a65b316" ]]; then
    echo "Wrong GeoChemFoam runtime commit: $runtime_commit" >&2
    exit 2
fi
if [[ "$runtime_parent" != "10f7a66afbf745d25013f7eda45b090cff66b866" ]]; then
    echo "Wrong GeoChemFoam runtime parent: $runtime_parent" >&2
    exit 2
fi
if [[ "$runtime_gitlink" != "a43de2c1d1dd5c0f93489d560fa3cd3e94646471" || "$adapter_commit" != "$runtime_gitlink" ]]; then
    echo "Wrong PhreeqcRM adapter commit: $adapter_commit" >&2
    exit 2
fi

echo "=== Run: Item1FinalFresh ==="
echo "Runtime: $runtime_commit"
echo "Adapter: $adapter_commit"
echo "Controls: ranks=8 deltaT=$RUN_TIMESTEP endTime=$TOTAL_TIME writeInterval=$WRITE_TIMESTEP phreeqcRestoreCheckpoint=false"
run_stage createMesh.sh
run_stage initCaseFlow.sh
run_stage runCaseFlow.sh
run_stage processFlow.sh
run_stage initCaseReactiveTransport.sh
python ./validate_item1_setup.py
run_stage runCaseReactiveTransport.sh
run_stage processReactiveTransport.sh
echo "=== Completed: Item1FinalFresh ==="
