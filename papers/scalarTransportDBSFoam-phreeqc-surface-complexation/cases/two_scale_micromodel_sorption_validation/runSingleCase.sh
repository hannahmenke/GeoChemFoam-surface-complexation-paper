#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

repo_root="$(cd ../../../.. && pwd)"

if [ -z "${GCFOAM_DIR:-}" ] && [ -f "$repo_root/etc/bashrc" ]; then
  set +e
  set +u
  # shellcheck disable=SC1090
  source "$repo_root/etc/bashrc"
  set -e
  set -u
fi

TARGET_CASE="${TARGET_CASE:-resolved-reference}"
TARGET_PE="${TARGET_PE:-1}"
DIFFUSION="${DIFFUSION:-1e-9}"
RT_CFL_TARGET="${RT_CFL_TARGET:-0.5}"
RT_LOCAL_VELOCITY_FACTOR="${RT_LOCAL_VELOCITY_FACTOR:-0}"
RT_FACE_VELOCITY_SAFETY="${RT_FACE_VELOCITY_SAFETY:-1.25}"
RT_TIMESTEP_MAX="${RT_TIMESTEP_MAX:-0}"
RT_CHECKPOINT_COUNT="${RT_CHECKPOINT_COUNT:-10}"
ASURF_SURFACE_MODE="${ASURF_SURFACE_MODE:-occupancyGaussian}"
SURFACE_RECONSTRUCTION_LABEL="${SURFACE_RECONSTRUCTION_LABEL:-production}"
PAPER_SOURCE_COMMIT="${PAPER_SOURCE_COMMIT:-$(git -C "$repo_root" rev-parse HEAD)}"

if [[ ! "$SURFACE_RECONSTRUCTION_LABEL" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "SURFACE_RECONSTRUCTION_LABEL must contain only lowercase letters, digits, and hyphens." >&2
  exit 2
fi

case "$TARGET_CASE" in
  resolved-reference|dbs-upscaled) ;;
  *)
    echo "TARGET_CASE must be resolved-reference or dbs-upscaled, got: $TARGET_CASE" >&2
    exit 2
    ;;
esac

export TARGET_PE DIFFUSION ASURF_SURFACE_MODE SURFACE_RECONSTRUCTION_LABEL
export PAPER_SOURCE_COMMIT

mkdir -p results

runtime_root="${GCFOAM_RUNTIME_ROOT:-${GCFOAM_DIR:-}}"
if [ -z "$runtime_root" ]; then
  echo "Set GCFOAM_RUNTIME_ROOT or GCFOAM_DIR to the reviewed production runtime." >&2
  exit 2
fi
python scripts/verify_production_runtime.py \
  --runtime-root "$runtime_root" \
  --output results/runtime_preflight.json

python scripts/prepare_images.py
python scripts/compute_matrix_rev_properties.py \
  shared/metadata.json \
  shared/TSmicromodel_matrix_rev.raw \
  results/matrix_rev_properties.json

for case_dir in resolved-reference dbs-upscaled; do
  rm -rf "$case_dir"/0 \
         "$case_dir"/processor* \
         "$case_dir"/constant/polyMesh \
         "$case_dir"/constant/triSurface \
         "$case_dir"/system/NPX \
         "$case_dir"/system/NPY \
         "$case_dir"/system/NPZ \
         "$case_dir"/system/Nx1 \
         "$case_dir"/system/Ny1 \
         "$case_dir"/system/Nz1 \
         "$case_dir"/system/cellSize
done

echo "=== Calibrate geometry flow metrics for Pe=${TARGET_PE} ==="
for case_dir in "$TARGET_CASE"; do
  echo "--- Calibration: ${case_dir} ---"
  (
    cd "$case_dir"
    ./createMesh.sh
    ./deleteFlow.sh
    ./initCaseFlow.sh
    ./runCaseFlow.sh
    ./processFlow.sh
  )
done

python scripts/compute_matched_pe_flow_rates.py \
  "$PWD" \
  "$TARGET_PE" \
  "$DIFFUSION" \
  results/matched_pe_flow_rates.json \
  "$TARGET_CASE"

# shellcheck disable=SC1091
source results/matched_pe_flow_rates.env
if [ -n "${RT_TIMESTEP_OVERRIDE:-}" ]; then
  export RT_TIMESTEP="$RT_TIMESTEP_OVERRIDE"
  rt_timestep_source="override"
elif [ -n "${RT_TIMESTEP:-}" ]; then
  export RT_TIMESTEP
  rt_timestep_source="inherited"
else
  rt_timestep_source="automatic"
  export RT_TIMESTEP="$(
    python scripts/compute_reactive_timestep.py \
      "$PWD" \
      results/matched_pe_flow_rates.json \
      --case "$TARGET_CASE" \
      --target-max-co "$RT_CFL_TARGET" \
      --local-velocity-factor "$RT_LOCAL_VELOCITY_FACTOR" \
      --face-velocity-safety "$RT_FACE_VELOCITY_SAFETY" \
      --max-dt "$RT_TIMESTEP_MAX" \
      --out-json results/reactive_timestep.json
  )"
fi
export RT_TOTAL_TIME="${RT_TOTAL_TIME:-$RECOMMENDED_RT_TOTAL_TIME}"
if [ -z "${RT_WRITE_TIMESTEP:-}" ]; then
  export RT_WRITE_TIMESTEP="$(
    python - <<'PY' "$RT_TOTAL_TIME" "$RT_CHECKPOINT_COUNT"
import sys

total_time = float(sys.argv[1])
checkpoint_count = max(1, int(float(sys.argv[2])))
print(f"{total_time / checkpoint_count:.12g}")
PY
  )"
fi

echo "=== Single-case run configuration ==="
echo "TARGET_CASE=${TARGET_CASE}"
echo "TARGET_PE=${TARGET_PE}"
echo "SURFACE_RECONSTRUCTION_LABEL=${SURFACE_RECONSTRUCTION_LABEL}"
echo "ASURF_SURFACE_MODE=${ASURF_SURFACE_MODE}"
echo "RT_TOTAL_TIME=${RT_TOTAL_TIME}"
echo "RT_WRITE_TIMESTEP=${RT_WRITE_TIMESTEP}"
echo "RT_TIMESTEP=${RT_TIMESTEP}"

{
  echo "TARGET_CASE=${TARGET_CASE}"
  echo "TARGET_PE=${TARGET_PE}"
  echo "SURFACE_RECONSTRUCTION_LABEL=${SURFACE_RECONSTRUCTION_LABEL}"
  echo "ASURF_SURFACE_MODE=${ASURF_SURFACE_MODE}"
  echo "PAPER_SOURCE_COMMIT=${PAPER_SOURCE_COMMIT}"
  echo "DIFFUSION=${DIFFUSION}"
  echo "RT_TOTAL_TIME=${RT_TOTAL_TIME}"
  echo "RT_WRITE_TIMESTEP=${RT_WRITE_TIMESTEP}"
  echo "RT_TIMESTEP=${RT_TIMESTEP}"
  echo "RT_CFL_TARGET=${RT_CFL_TARGET}"
  echo "RT_LOCAL_VELOCITY_FACTOR=${RT_LOCAL_VELOCITY_FACTOR}"
  echo "RT_FACE_VELOCITY_SAFETY=${RT_FACE_VELOCITY_SAFETY}"
  echo "RT_TIMESTEP_MAX=${RT_TIMESTEP_MAX}"
  echo "RT_CHECKPOINT_COUNT=${RT_CHECKPOINT_COUNT}"
  echo "FLOW_TOTAL_TIME=${FLOW_TOTAL_TIME:-300}"
  echo "RT_BOUND_AQUEOUS_TRANSPORT=${RT_BOUND_AQUEOUS_TRANSPORT:-0}"
  echo "RT_AQUEOUS_LOWER_BOUND=${RT_AQUEOUS_LOWER_BOUND:-0}"
  echo "RT_AQUEOUS_UPPER_BOUND=${RT_AQUEOUS_UPPER_BOUND:-1e30}"
  echo "RESOLVED_NPX=${RESOLVED_NPX:-${GCFOAM_NPX:-8}}"
  echo "RESOLVED_NPY=${RESOLVED_NPY:-${GCFOAM_NPY:-4}}"
  echo "RESOLVED_NPZ=${RESOLVED_NPZ:-${GCFOAM_NPZ:-1}}"
  echo "DBS_NPX=${DBS_NPX:-${GCFOAM_NPX:-8}}"
  echo "DBS_NPY=${DBS_NPY:-${GCFOAM_NPY:-4}}"
  echo "DBS_NPZ=${DBS_NPZ:-${GCFOAM_NPZ:-1}}"
  echo "RESOLVED_COARSEN_FACTOR=${RESOLVED_COARSEN_FACTOR:-1}"
  echo "DBS_COARSEN_FACTOR=${DBS_COARSEN_FACTOR:-1}"
  echo "X_MIRROR_COPIES=${X_MIRROR_COPIES:-2}"
  echo "RESOLVED_CROP_X_MIN=${RESOLVED_CROP_X_MIN:-0}"
  echo "RESOLVED_CROP_X_MAX=${RESOLVED_CROP_X_MAX:-6000}"
  echo "RESOLVED_CROP_Y_MIN=${RESOLVED_CROP_Y_MIN:-0}"
  echo "RESOLVED_CROP_Y_MAX=${RESOLVED_CROP_Y_MAX:-6000}"
  echo "DBS_CROP_X_MIN=${DBS_CROP_X_MIN:-0}"
  echo "DBS_CROP_X_MAX=${DBS_CROP_X_MAX:-1200}"
  echo "DBS_CROP_Y_MIN=${DBS_CROP_Y_MIN:-0}"
  echo "DBS_CROP_Y_MAX=${DBS_CROP_Y_MAX:-1200}"
  echo "RESOLVED_INLET_PAD_VOXELS=${RESOLVED_INLET_PAD_VOXELS:-4}"
  echo "DBS_INLET_PAD_VOXELS=${DBS_INLET_PAD_VOXELS:-1}"
} > results/current_run_config.env

python scripts/write_preflight_summary.py \
  shared/metadata.json \
  results/matched_pe_flow_rates.json \
  results/preflight_summary.md \
  "$RT_WRITE_TIMESTEP" \
  "$RT_TIMESTEP" \
  "$RT_TOTAL_TIME"

if [ "${PREFLIGHT_ONLY:-0}" = "1" ]; then
  echo "=== Preflight complete; stopping before reactive transport because PREFLIGHT_ONLY=1 ==="
  exit 0
fi

(
  cd "$TARGET_CASE"
  ./deleteFlow.sh
  ./deleteReactiveTransport.sh
)

if [ "$TARGET_CASE" = "resolved-reference" ]; then
  flow_rate="$RESOLVED_REFERENCE_FLOW_RATE"
  rt_diffusion="$RESOLVED_REFERENCE_DIFFUSION"
else
  flow_rate="$DBS_UPSCALED_FLOW_RATE"
  rt_diffusion="$DBS_UPSCALED_DIFFUSION"
fi

echo "=== Run: ${TARGET_CASE} at Pe=${TARGET_PE} ==="
(
  cd "$TARGET_CASE"
  export BOUNDARY_TYPE=flow_rate
  export FLOW_RATE="$flow_rate"
  export RT_DIFFUSION="$rt_diffusion"
  ./initCaseFlow.sh
  ./runCaseFlow.sh
  ./processFlow.sh
  if [ "$rt_timestep_source" = "automatic" ]; then
    export RT_TIMESTEP="$(
      python ../scripts/compute_reactive_timestep.py \
        .. \
        ../results/matched_pe_flow_rates.json \
        --case "$TARGET_CASE" \
        --target-max-co "$RT_CFL_TARGET" \
        --local-velocity-factor "$RT_LOCAL_VELOCITY_FACTOR" \
        --face-velocity-safety "$RT_FACE_VELOCITY_SAFETY" \
        --max-dt "$RT_TIMESTEP_MAX" \
        --velocity-at-target-flow \
        --out-json ../results/reactive_timestep.json
    )"
    python - <<'PY' ../results/current_run_config.env "$RT_TIMESTEP"
from pathlib import Path
import sys

path = Path(sys.argv[1])
lines = path.read_text().splitlines()
lines = [
    f"RT_TIMESTEP={sys.argv[2]}" if line.startswith("RT_TIMESTEP=") else line
    for line in lines
]
path.write_text("\n".join(lines) + "\n")
PY
    python ../scripts/write_preflight_summary.py \
      ../shared/metadata.json \
      ../results/matched_pe_flow_rates.json \
      ../results/preflight_summary.md \
      "$RT_WRITE_TIMESTEP" \
      "$RT_TIMESTEP" \
      "$RT_TOTAL_TIME"
    echo "Recomputed reactive timestep from the final flow-rate velocity field: $RT_TIMESTEP"
  fi
  ./initCaseReactiveTransport.sh
  if [ "$TARGET_CASE" = "dbs-upscaled" ]; then
    python ../scripts/write_matched_run_provenance.py \
      --phase initial \
      --case-dir . \
      --run-config ../results/current_run_config.env \
      --output "../results/matched_run_provenance_${SURFACE_RECONSTRUCTION_LABEL}.json"
  fi
  if [ "${RT_INIT_ONLY:-0}" = "1" ]; then
    echo "=== Reactive-transport initialization complete; stopping because RT_INIT_ONLY=1 ==="
    exit 0
  fi
  ./runCaseReactiveTransport.sh
  if [ "${RT_DRY_RUN_ONLY:-0}" = "1" ]; then
    echo "=== Reactive-transport dry-run complete; stopping because RT_DRY_RUN_ONLY=1 ==="
    exit 0
  fi
  ./processReactiveTransport.sh
)

case_tag="${TARGET_CASE//-/_}"
pe_tag="$(python - <<'PY' "$TARGET_PE"
import sys
print(("pe_" + sys.argv[1].replace(".", "p").replace("-", "m")).replace("+", ""))
PY
)"
out_dir="results/single_case/${case_tag}_${pe_tag}"
mkdir -p "$out_dir"
cp results/current_run_config.env "$out_dir/"
cp results/runtime_preflight.json "$out_dir/"
cp results/preflight_summary.md "$out_dir/"
cp results/matched_pe_flow_rates.json "$out_dir/"
cp results/matched_pe_flow_rates.env "$out_dir/"
cp results/reactive_timestep.json "$out_dir/" 2>/dev/null || true
if [ "$TARGET_CASE" = "dbs-upscaled" ]; then
  cp "results/matched_run_provenance_${SURFACE_RECONSTRUCTION_LABEL}.json" "$out_dir/"
fi
cp "$TARGET_CASE"/poroPerm.csv "$out_dir/" 2>/dev/null || true
cp "$TARGET_CASE"/simpleDBSFoam.out "$out_dir/" 2>/dev/null || true
cp "$TARGET_CASE"/simpleDBSFoamFlow.out "$out_dir/" 2>/dev/null || true
cp "$TARGET_CASE"/processPoroPermFlow.out "$out_dir/" 2>/dev/null || true
cp "$TARGET_CASE"/reactiveTransportDBSFoamRT.out "$out_dir/" 2>/dev/null || true
cp "$TARGET_CASE"/system/controlDict "$out_dir/controlDict.reactive" 2>/dev/null || true

echo "=== Completed: ${TARGET_CASE} at Pe=${TARGET_PE} ==="
