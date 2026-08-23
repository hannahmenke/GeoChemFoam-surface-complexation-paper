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

if [ -n "${GCFOAM_RUNTIME_ROOT:-}" ] && [ -f "$GCFOAM_RUNTIME_ROOT/etc/bashrc" ]; then
  set +e
  set +u
  # shellcheck disable=SC1090
  source "$GCFOAM_RUNTIME_ROOT/etc/bashrc"
  set -e
  set -u
  # The runtime checkout may retain a developer-local path in etc/bashrc.
  # Re-anchor all GeoChemFoam paths to the explicitly selected checkout.
  export GCFOAM_DIR="$GCFOAM_RUNTIME_ROOT"
  export GCFOAM_SRC="$GCFOAM_DIR/src"
  export GCFOAM_APPBIN="$GCFOAM_DIR/bin"
  export GCFOAM_LIBBIN="$GCFOAM_DIR/lib"
  export GCFOAM_TUTORIALS="$GCFOAM_DIR/tutorials"
  export GCFOAM_IMG="$repo_root/images"
  export PATH="$GCFOAM_APPBIN:$PATH"
  export LD_LIBRARY_PATH="$GCFOAM_LIBBIN:${LD_LIBRARY_PATH:-}"
  set +u
  # shellcheck disable=SC1090
  source "$GCFOAM_DIR/ThirdParty/bashrc"
  export LD_LIBRARY_PATH="$GCFOAM_DIR/ThirdParty/PhreeqcRM/lib:$GCFOAM_LIBBIN:${LD_LIBRARY_PATH:-}"
  set -u
elif [ -f "$repo_root/etc/bashrc" ]; then
  set +e
  set +u
  # shellcheck disable=SC1090
  source "$repo_root/etc/bashrc"
  set -e
  set -u
fi

if ! command -v reactiveTransportDBSFoam >/dev/null 2>&1; then
  echo "reactiveTransportDBSFoam is not available. Set GCFOAM_RUNTIME_ROOT to the GeoChemFoam runtime checkout." >&2
  exit 1
fi

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

echo "=== Run: 3DEstailladesSurfaceComplexation ==="
echo "Grid: 500 x 500 x 500; decomposition: ${GCFOAM_NPX:-4} x ${GCFOAM_NPY:-4} x ${GCFOAM_NPZ:-4}"
echo "Reactive transport: dt=${RUN_TIMESTEP:-2}, end=${TOTAL_TIME:-120}, write=${WRITE_TIMESTEP:-20}, binary output"

run_stage="${RUN_STAGE:-all}"
if [[ "$run_stage" == "flow-continue" ]]; then
  echo "=== Continue flow from the preserved processor*/0 fields ==="
  run_task runCaseFlow.sh
  run_task processFlow.sh
  echo "=== Completed continued flow stage; verify convergence before reactive transport ==="
  exit 0
fi

if [[ "$run_stage" == "all" || "$run_stage" == "flow" ]]; then
  run_task createMesh.sh
  run_task initCaseFlow.sh
  run_task runCaseFlow.sh
  run_task processFlow.sh
fi

if [[ "$run_stage" == "flow" ]]; then
  echo "=== Completed flow stage; verify convergence and CFL before reactive transport ==="
  exit 0
fi

if [[ "$run_stage" == "all" || "$run_stage" == "reactive" ]]; then
  run_task initCaseReactiveTransport.sh
  run_task runCaseReactiveTransport.sh
  run_task processReactiveTransport.sh
else
  echo "Unknown RUN_STAGE=$run_stage (expected all, flow, flow-continue, or reactive)" >&2
  exit 1
fi
echo "=== Completed: 3DEstailladesSurfaceComplexation ==="
