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

export PLATFORM="${PLATFORM:-ARCHER2}"
TARGET_PE="${TARGET_PE:-1}"
DIFFUSION="${DIFFUSION:-1e-9}"
RT_TOTAL_TIME="${RT_TOTAL_TIME:-2}"
RT_WRITE_TIMESTEP="${RT_WRITE_TIMESTEP:-$RT_TOTAL_TIME}"
RT_CFL_TARGET="${RT_CFL_TARGET:-0.8}"
RT_LOCAL_VELOCITY_FACTOR="${RT_LOCAL_VELOCITY_FACTOR:-2.5}"
RT_TIMESTEP_MAX="${RT_TIMESTEP_MAX:-0}"
SCALING_SPECS="${SCALING_SPECS:-32x16x1 32x32x1 64x32x1}"

mkdir -p results/scaling

python scripts/prepare_images.py
python scripts/compute_matrix_rev_properties.py \
  shared/metadata.json \
  shared/TSmicromodel_matrix_rev.raw \
  results/matrix_rev_properties.json

for spec in $SCALING_SPECS; do
  IFS=x read -r npx npy npz <<< "$spec"
  ranks=$((npx * npy * npz))
  out_dir="results/scaling/resolved_${ranks}_${npx}x${npy}x${npz}"
  mkdir -p "$out_dir"

  echo "=== Resolved-reference scaling: ranks=${ranks}, NPX=${npx}, NPY=${npy}, NPZ=${npz} ==="
  echo "Output: ${out_dir}"

  (
    cd resolved-reference
    rm -rf 0 processor* constant/polyMesh constant/triSurface \
      system/NPX system/NPY system/NPZ system/Nx1 system/Ny1 system/Nz1 \
      constant/transportProperties constant/thermoPhysicalProperties \
      simpleDBSFoam.out simpleDBSFoamFlow.out processPoroPermFlow.out reactiveTransportDBSFoamRT.out

    export RESOLVED_NPX="$npx"
    export RESOLVED_NPY="$npy"
    export RESOLVED_NPZ="$npz"
    ./createMesh.sh

    ./deleteFlow.sh
    ./initCaseFlow.sh
    ./runCaseFlow.sh
    ./processFlow.sh
  )

  flow_rate="$(
    python - <<'PY' "$TARGET_PE" "$DIFFUSION" resolved-reference/poroPerm.csv
import csv
import sys

target_pe = float(sys.argv[1])
diffusion = float(sys.argv[2])
poro_perm_path = sys.argv[3]
with open(poro_perm_path) as handle:
    row = next(csv.DictReader(handle, delimiter=" "))
porosity = float(row["poro"])
lpore = float(row["Lpore"])
darcy_velocity = target_pe * diffusion * porosity / lpore
flow_rate = darcy_velocity * 6.0e-3 * 1.0e-6
print(f"{flow_rate:.12g}")
PY
  )"

  if [ -n "${RT_TIMESTEP_OVERRIDE:-}" ]; then
    rt_timestep="$RT_TIMESTEP_OVERRIDE"
  elif [ -n "${RT_TIMESTEP:-}" ]; then
    rt_timestep="$RT_TIMESTEP"
  else
    rt_timestep="$(
      python - <<'PY' "$TARGET_PE" "$DIFFUSION" "$RT_CFL_TARGET" "$RT_LOCAL_VELOCITY_FACTOR" "$RT_TIMESTEP_MAX" resolved-reference/poroPerm.csv resolved-reference/createMesh.sh
import csv
import re
import sys

target_pe = float(sys.argv[1])
diffusion = float(sys.argv[2])
target_max_co = float(sys.argv[3])
local_velocity_factor = float(sys.argv[4])
max_dt = float(sys.argv[5])
poro_perm_path = sys.argv[6]
create_mesh_path = sys.argv[7]

with open(poro_perm_path) as handle:
    row = next(csv.DictReader(handle, delimiter=" "))
porosity = float(row["poro"])
lpore = float(row["Lpore"])
pore_velocity = target_pe * diffusion / lpore
match = re.search(r"^res=([0-9.eE+-]+)", open(create_mesh_path).read(), re.M)
if not match:
    raise SystemExit(f"Could not find res= in {create_mesh_path}")
dx = float(match.group(1))
dt = target_max_co * dx / (local_velocity_factor * pore_velocity)
if max_dt > 0:
    dt = min(dt, max_dt)
print(f"{dt:.12g}")
PY
    )"
  fi

  python - <<'PY' "$TARGET_PE" "$DIFFUSION" "$flow_rate" "$RT_TOTAL_TIME" "$rt_timestep" "$spec" "$out_dir" resolved-reference/poroPerm.csv "$RT_CFL_TARGET" "$RT_LOCAL_VELOCITY_FACTOR"
import csv
import json
import sys
from pathlib import Path

target_pe = float(sys.argv[1])
diffusion = float(sys.argv[2])
flow_rate = float(sys.argv[3])
rt_total_time = float(sys.argv[4])
rt_timestep = float(sys.argv[5])
spec = sys.argv[6]
out_dir = Path(sys.argv[7])
poro_perm_path = sys.argv[8]
rt_cfl_target = float(sys.argv[9])
rt_local_velocity_factor = float(sys.argv[10])
with open(poro_perm_path) as handle:
    row = next(csv.DictReader(handle, delimiter=" "))
porosity = float(row["poro"])
lpore = float(row["Lpore"])
darcy_velocity = target_pe * diffusion * porosity / lpore
payload = {
    "purpose": "short resolved-reference strong-scaling timing run",
    "decomposition": spec,
    "target_pe": target_pe,
    "diffusion_m2_per_s": diffusion,
    "porosity": porosity,
    "lpore_m": lpore,
    "darcy_velocity_m_per_s": darcy_velocity,
    "flow_rate_m3_per_s": flow_rate,
    "reactive_transport_total_time_s": rt_total_time,
    "reactive_transport_timestep_s": rt_timestep,
    "reactive_transport_timestep_policy": "dt = target_max_co * cell_size / (local_velocity_factor * pore_velocity)",
    "reactive_transport_target_max_courant": rt_cfl_target,
    "reactive_transport_local_velocity_factor": rt_local_velocity_factor,
}
(out_dir / "scaling_preflight.json").write_text(json.dumps(payload, indent=2) + "\n")
PY

  (
    cd resolved-reference
    ./deleteFlow.sh
    ./deleteReactiveTransport.sh

    export BOUNDARY_TYPE=flow_rate
    export FLOW_RATE="$flow_rate"
    export RT_DIFFUSION="$DIFFUSION"
    export RT_TOTAL_TIME
    export RT_WRITE_TIMESTEP
    export RT_TIMESTEP="$rt_timestep"

    ./initCaseFlow.sh
    ./runCaseFlow.sh
    ./processFlow.sh
    ./initCaseReactiveTransport.sh
    ./runCaseReactiveTransport.sh
  )

  cp resolved-reference/poroPerm.csv "$out_dir/" 2>/dev/null || true
  cp resolved-reference/simpleDBSFoam.out "$out_dir/" 2>/dev/null || true
  cp resolved-reference/simpleDBSFoamFlow.out "$out_dir/" 2>/dev/null || true
  cp resolved-reference/processPoroPermFlow.out "$out_dir/" 2>/dev/null || true
  cp resolved-reference/reactiveTransportDBSFoamRT.out "$out_dir/" 2>/dev/null || true
  cp resolved-reference/system/controlDict "$out_dir/controlDict.reactive" 2>/dev/null || true
  echo "=== Completed scaling point: ${ranks} ranks ==="
done

echo "=== Completed resolved-reference scaling sweep: ${SCALING_SPECS} ==="
