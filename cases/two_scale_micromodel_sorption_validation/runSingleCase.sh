#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

repo_root="$(cd ../../../.. && pwd)"

if [ -f "$repo_root/etc/bashrc" ]; then
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
RT_TIMESTEP_REF_PE="${RT_TIMESTEP_REF_PE:-1}"
RT_TIMESTEP_REF="${RT_TIMESTEP_REF:-0.01}"
RT_TIMESTEP_MAX="${RT_TIMESTEP_MAX:-0.1}"
RT_CHECKPOINT_COUNT="${RT_CHECKPOINT_COUNT:-10}"

case "$TARGET_CASE" in
  resolved-reference|dbs-upscaled) ;;
  *)
    echo "TARGET_CASE must be resolved-reference or dbs-upscaled, got: $TARGET_CASE" >&2
    exit 2
    ;;
esac

if [ -n "${RT_TIMESTEP_OVERRIDE:-}" ]; then
  RT_TIMESTEP="$RT_TIMESTEP_OVERRIDE"
else
  RT_TIMESTEP="$(
    python - <<'PY' "$TARGET_PE" "$RT_TIMESTEP_REF_PE" "$RT_TIMESTEP_REF" "$RT_TIMESTEP_MAX"
import sys

pe = float(sys.argv[1])
reference_pe = float(sys.argv[2])
reference_dt = float(sys.argv[3])
max_dt = float(sys.argv[4])
if pe <= 0 or reference_pe <= 0:
    raise SystemExit("Pe must be positive")
print(f"{min(reference_dt * reference_pe / pe, max_dt):.12g}")
PY
  )"
fi
export TARGET_PE DIFFUSION RT_TIMESTEP

mkdir -p results

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
         "$case_dir"/constant/aSurfReconstructionDict \
         "$case_dir"/system/NPX \
         "$case_dir"/system/NPY \
         "$case_dir"/system/NPZ \
         "$case_dir"/system/Nx1 \
         "$case_dir"/system/Ny1 \
         "$case_dir"/system/Nz1
done

echo "=== Calibrate geometry flow metrics for Pe=${TARGET_PE} ==="
for case_dir in resolved-reference dbs-upscaled; do
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
  results/matched_pe_flow_rates.json

# shellcheck disable=SC1091
source results/matched_pe_flow_rates.env
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
echo "RT_TOTAL_TIME=${RT_TOTAL_TIME}"
echo "RT_WRITE_TIMESTEP=${RT_WRITE_TIMESTEP}"
echo "RT_TIMESTEP=${RT_TIMESTEP}"

{
  echo "TARGET_CASE=${TARGET_CASE}"
  echo "TARGET_PE=${TARGET_PE}"
  echo "DIFFUSION=${DIFFUSION}"
  echo "RT_TOTAL_TIME=${RT_TOTAL_TIME}"
  echo "RT_WRITE_TIMESTEP=${RT_WRITE_TIMESTEP}"
  echo "RT_TIMESTEP=${RT_TIMESTEP}"
  echo "RT_TIMESTEP_REF_PE=${RT_TIMESTEP_REF_PE}"
  echo "RT_TIMESTEP_REF=${RT_TIMESTEP_REF}"
  echo "RT_TIMESTEP_MAX=${RT_TIMESTEP_MAX}"
  echo "RT_CHECKPOINT_COUNT=${RT_CHECKPOINT_COUNT}"
  echo "RESOLVED_NPX=${RESOLVED_NPX:-${GCFOAM_NPX:-8}}"
  echo "RESOLVED_NPY=${RESOLVED_NPY:-${GCFOAM_NPY:-4}}"
  echo "RESOLVED_NPZ=${RESOLVED_NPZ:-${GCFOAM_NPZ:-1}}"
  echo "DBS_NPX=${DBS_NPX:-${GCFOAM_NPX:-8}}"
  echo "DBS_NPY=${DBS_NPY:-${GCFOAM_NPY:-4}}"
  echo "DBS_NPZ=${DBS_NPZ:-${GCFOAM_NPZ:-1}}"
} > results/current_run_config.env

python scripts/write_preflight_summary.py \
  shared/metadata.json \
  results/matched_pe_flow_rates.json \
  results/preflight_summary.md \
  "$RT_WRITE_TIMESTEP" \
  "$RT_TIMESTEP"

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
  ./initCaseReactiveTransport.sh
  ./runCaseReactiveTransport.sh
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
cp results/preflight_summary.md "$out_dir/"
cp results/matched_pe_flow_rates.json "$out_dir/"
cp results/matched_pe_flow_rates.env "$out_dir/"
cp "$TARGET_CASE"/poroPerm.csv "$out_dir/" 2>/dev/null || true
cp "$TARGET_CASE"/simpleDBSFoam.out "$out_dir/" 2>/dev/null || true
cp "$TARGET_CASE"/simpleDBSFoamFlow.out "$out_dir/" 2>/dev/null || true
cp "$TARGET_CASE"/processPoroPermFlow.out "$out_dir/" 2>/dev/null || true
cp "$TARGET_CASE"/reactiveScalarTransportDBSFoamRT.out "$out_dir/" 2>/dev/null || true
cp "$TARGET_CASE"/system/controlDict "$out_dir/controlDict.reactive" 2>/dev/null || true

echo "=== Completed: ${TARGET_CASE} at Pe=${TARGET_PE} ==="
