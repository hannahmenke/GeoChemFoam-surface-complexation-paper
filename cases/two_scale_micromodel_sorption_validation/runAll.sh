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

if [ -f "$repo_root/etc/bashrc" ]; then
  set +e
  set +u
  # shellcheck disable=SC1090
  source "$repo_root/etc/bashrc"
  set -e
  set -u
fi

python scripts/prepare_images.py
python scripts/compute_matrix_rev_properties.py \
  shared/metadata.json \
  shared/TSmicromodel_matrix_rev.raw \
  results/matrix_rev_properties.json

TARGET_PE="${TARGET_PE:-1}"
DIFFUSION="${DIFFUSION:-1e-9}"
RT_TIMESTEP="${RT_TIMESTEP:-0.01}"
export RT_TIMESTEP
mkdir -p results

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

echo "=== Calibrate geometry flow metrics ==="
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
  RT_CHECKPOINT_COUNT="${RT_CHECKPOINT_COUNT:-4}"
  export RT_WRITE_TIMESTEP="$(
    python - <<'PY' "$RT_TOTAL_TIME" "$RT_CHECKPOINT_COUNT"
import sys

total_time = float(sys.argv[1])
checkpoint_count = max(1, int(float(sys.argv[2])))
print(f"{total_time / checkpoint_count:.12g}")
PY
  )"
fi
echo "Reactive transport time: RT_TOTAL_TIME=${RT_TOTAL_TIME}, RT_WRITE_TIMESTEP=${RT_WRITE_TIMESTEP}, RT_TIMESTEP=${RT_TIMESTEP}"

{
  echo "TARGET_PE=${TARGET_PE}"
  echo "DIFFUSION=${DIFFUSION}"
  echo "RT_TOTAL_TIME=${RT_TOTAL_TIME}"
  echo "RT_WRITE_TIMESTEP=${RT_WRITE_TIMESTEP}"
  echo "RT_TIMESTEP=${RT_TIMESTEP}"
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

for case_dir in resolved-reference dbs-upscaled; do
  (
    cd "$case_dir"
    ./deleteFlow.sh
    ./deleteReactiveTransport.sh
  )
done

echo "=== Run: resolved micromodel sorption reference ==="
(
  cd resolved-reference
  export BOUNDARY_TYPE=flow_rate
  export FLOW_RATE="$RESOLVED_REFERENCE_FLOW_RATE"
  export RT_DIFFUSION="$RESOLVED_REFERENCE_DIFFUSION"
  ./initCaseFlow.sh
  ./runCaseFlow.sh
  ./processFlow.sh
  ./initCaseReactiveTransport.sh
  ./runCaseReactiveTransport.sh
  ./processReactiveTransport.sh
)

echo "=== Run: upscaled DBS micromodel sorption case ==="
(
  cd dbs-upscaled
  export BOUNDARY_TYPE=flow_rate
  export FLOW_RATE="$DBS_UPSCALED_FLOW_RATE"
  export RT_DIFFUSION="$DBS_UPSCALED_DIFFUSION"
  ./initCaseFlow.sh
  ./runCaseFlow.sh
  ./processFlow.sh
  ./initCaseReactiveTransport.sh
  ./runCaseReactiveTransport.sh
  ./processReactiveTransport.sh
)

python scripts/analyze_results.py

echo "=== Completed: two-scale micromodel sorption validation ==="
