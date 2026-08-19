#!/usr/bin/env bash
#SBATCH --job-name=ts-li-case
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=24:00:00
#SBATCH --exclusive
#SBATCH --partition=standard
#SBATCH --qos=standard
#SBATCH --account=n03-hw

set -Eeuo pipefail

: "${TARGET_CASE:?Set TARGET_CASE=dbs-upscaled or TARGET_CASE=resolved-reference}"
: "${TARGET_PE:?Set TARGET_PE to the requested Peclet number}"

submit_dir="$SLURM_SUBMIT_DIR"
case_root_name="two_scale_${TARGET_CASE}_pe_${TARGET_PE}_${SLURM_JOB_ID}"
# The run directory must be visible from every compute node. ARCHER2's /tmp is
# node-local, so do not default to TMPDIR for MPI jobs.
scratch_parent="${TWO_SCALE_WORK_PARENT:-${SCRATCH:-$submit_dir/archer_work}}"
case "$scratch_parent" in
  /tmp|/tmp/*)
    echo "TWO_SCALE_WORK_PARENT/SCRATCH resolves to node-local $scratch_parent; use a shared Lustre path." >&2
    exit 4
    ;;
esac
work_dir="${TWO_SCALE_WORK_DIR:-$scratch_parent/$case_root_name}"
archive_dir="${TWO_SCALE_ARCHIVE_DIR:-$submit_dir/results/archer/$case_root_name}"

mkdir -p "$work_dir" "$archive_dir"

RT_CHECKPOINT_COUNT="${RT_CHECKPOINT_COUNT:-10}"
archive_mode="${TWO_SCALE_ARCHIVE_MODE:-metadata}"
case "$archive_mode" in
  metadata|selected|full) ;;
  *)
    echo "Unknown TWO_SCALE_ARCHIVE_MODE=$archive_mode" >&2
    exit 2
    ;;
esac

estimate_bytes() {
  python - <<'PY' "$TARGET_CASE" "$RT_CHECKPOINT_COUNT" "$1" "$archive_mode"
import os
import sys

case_name = sys.argv[1]
checkpoint_count = max(1, int(float(sys.argv[2])))
scope = sys.argv[3]
archive_mode = sys.argv[4]
mirror_copies = int(os.environ.get("X_MIRROR_COPIES", "2"))
if case_name == "resolved-reference":
    x_min = int(os.environ.get("RESOLVED_CROP_X_MIN", "0"))
    x_max = int(os.environ.get("RESOLVED_CROP_X_MAX", "6000"))
    y_min = int(os.environ.get("RESOLVED_CROP_Y_MIN", "0"))
    y_max = int(os.environ.get("RESOLVED_CROP_Y_MAX", "6000"))
    coarsen_factor = int(os.environ.get("RESOLVED_COARSEN_FACTOR", "1"))
elif case_name == "dbs-upscaled":
    x_min = int(os.environ.get("DBS_CROP_X_MIN", "0"))
    x_max = int(os.environ.get("DBS_CROP_X_MAX", "1200"))
    y_min = int(os.environ.get("DBS_CROP_Y_MIN", "0"))
    y_max = int(os.environ.get("DBS_CROP_Y_MAX", "1200"))
    coarsen_factor = int(os.environ.get("DBS_COARSEN_FACTOR", "1"))
else:
    raise SystemExit(f"unknown TARGET_CASE: {case_name}")
if coarsen_factor <= 0:
    raise SystemExit("coarsen factor must be positive")
if (x_max - x_min) % coarsen_factor or (y_max - y_min) % coarsen_factor:
    raise SystemExit("crop dimensions must be divisible by coarsen factor")
cells = (
    ((x_max - x_min) // coarsen_factor)
    * (1 + mirror_copies)
    * ((y_max - y_min) // coarsen_factor)
)

write_count = checkpoint_count + 1  # includes time 0
bytes_per_scalar_ascii = 22
archived_fields = 11
runtime_field_multiplier = 2.0
safety_factor = 2.5
estimated = (
    cells
    * bytes_per_scalar_ascii
    * archived_fields
    * write_count
    * runtime_field_multiplier
    * safety_factor
)
# The solver retains only the newest complete PHREEQC dump, but peak space
# briefly contains the previous and new checkpoints while the new one is
# written. The 4.32-million-cell DBS smoke measured approximately 4.3 kB per
# active cell; use 4.6 kB/cell here to retain margin around that observation.
estimated += 2 * cells * 4600
if scope == "scratch" or archive_mode == "full":
    result = estimated
elif archive_mode == "selected":
    # Selected mode copies eleven scalar fields but no PHREEQC dumps.
    result = cells * bytes_per_scalar_ascii * archived_fields * write_count * safety_factor
    result += 5 * 1024**3
elif archive_mode == "metadata":
    # Allow ample room for root logs, summaries, dictionaries, and reports.
    result = 5 * 1024**3
else:
    raise SystemExit(f"unknown archive mode: {archive_mode}")
print(int(result))
PY
}

available_bytes() {
  df -PB1 "$1" | awk 'NR==2 {print $4}'
}

human_bytes() {
  numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "${1} B"
}

scratch_required_bytes="${TWO_SCALE_REQUIRED_BYTES:-$(estimate_bytes scratch)}"
archive_required_bytes="${TWO_SCALE_ARCHIVE_REQUIRED_BYTES:-$(estimate_bytes archive)}"
scratch_available="$(available_bytes "$work_dir")"
archive_available="$(available_bytes "$archive_dir")"

echo "=== Disk/quota preflight ==="
echo "TARGET_CASE=$TARGET_CASE"
echo "TARGET_PE=$TARGET_PE"
echo "RT_CHECKPOINT_COUNT=$RT_CHECKPOINT_COUNT"
echo "TWO_SCALE_ARCHIVE_MODE=$archive_mode"
echo "estimated_scratch_required=$(human_bytes "$scratch_required_bytes")"
echo "estimated_archive_required=$(human_bytes "$archive_required_bytes")"
echo "scratch_available=$(human_bytes "$scratch_available") at $work_dir"
echo "archive_available=$(human_bytes "$archive_available") at $archive_dir"

if [ "$scratch_available" -lt "$scratch_required_bytes" ]; then
  echo "Insufficient scratch space for estimated run output." >&2
  exit 3
fi
if [ "$archive_available" -lt "$archive_required_bytes" ]; then
  echo "Insufficient archive space for estimated synchronized output." >&2
  exit 3
fi

sync_back() {
  rc=$?
  mkdir -p "$archive_dir"
  if [ "$archive_mode" = "full" ]; then
    rsync -a --exclude='.git/' "$work_dir/" "$archive_dir/full_case/" || true
    echo "$rc" > "$archive_dir/slurm_exit_code.txt"
    exit "$rc"
  fi
  if [ -d "$work_dir/results" ]; then
    rsync -a "$work_dir/results/" "$archive_dir/results/" || true
  fi
  for case_dir in resolved-reference dbs-upscaled; do
    if [ -d "$work_dir/$case_dir" ]; then
      mkdir -p "$archive_dir/$case_dir"
      rsync -a \
        --exclude='processor*/' \
        --exclude='createASurfSmoothInterface.proc*.out' \
        --exclude='createASurfSmoothInterface.support.proc*.out' \
        --include='*/' \
        --include='*.out' \
        --include='poroPerm.csv' \
        --include='system/controlDict' \
        --exclude='*' \
        "$work_dir/$case_dir/" "$archive_dir/$case_dir/" || true
      if [ "$archive_mode" = "selected" ]; then
        rsync -a \
        --include='*/' \
        --include='processor*/[0-9]*/Li+' \
        --include='processor*/[0-9]*/Na+' \
        --include='processor*/[0-9]*/K+' \
        --include='processor*/[0-9]*/Mg+2' \
        --include='processor*/[0-9]*/Cl-' \
        --include='processor*/[0-9]*/Sor_aLi' \
        --include='processor*/[0-9]*/Sor_aNa' \
        --include='processor*/[0-9]*/Sor_aK' \
        --include='processor*/[0-9]*/Sor_aMg+' \
        --include='processor*/[0-9]*/theta' \
        --include='processor*/[0-9]*/aSurf' \
        --exclude='*' \
        "$work_dir/$case_dir/" "$archive_dir/$case_dir/" || true
      fi
    fi
  done
  echo "$rc" > "$archive_dir/slurm_exit_code.txt"
  exit "$rc"
}
trap sync_back EXIT

cd "$submit_dir"

rsync -a \
  --exclude='results/' \
  --exclude='archer_work/' \
  --exclude='dbs-upscaled/[0-9]*/' \
  --exclude='resolved-reference/[0-9]*/' \
  --exclude='*/processor*/' \
  --exclude='*/constant/polyMesh/' \
  --exclude='*/constant/triSurface/' \
  --exclude='*.out' \
  --exclude='*.log' \
  --exclude='*.pid' \
  --exclude='*.status' \
  --exclude='__pycache__/' \
  --exclude='*/__pycache__/' \
  ./ "$work_dir/"

cd "$work_dir"

export PLATFORM=ARCHER2
export OMP_NUM_THREADS=1

repo_root="$(git -C "$submit_dir" rev-parse --show-toplevel 2>/dev/null || true)"
env_file="${GCFOAM_ENV_FILE:-${repo_root:+$repo_root/.archer2-tools/gcfoam-env.sh}}"
if [ -n "$env_file" ] && [ -f "$env_file" ]; then
  module purge
  # shellcheck disable=SC1090
  source "$env_file"
elif ! command -v reactiveTransportDBSFoam >/dev/null 2>&1 || \
     [ -z "${WM_PROJECT_DIR:-}" ]; then
  echo "GeoChemFoam/OpenFOAM environment is not loaded." >&2
  echo "Load it before sbatch or set GCFOAM_ENV_FILE to a site environment helper." >&2
  exit 2
else
  echo "Using the inherited GeoChemFoam/OpenFOAM environment."
fi

export TARGET_CASE
export TARGET_PE

# The submit-all helper overrides node count by case: native 1 um resolved jobs
# use 128 nodes, coarsened resolved jobs use 8 nodes, and DBS jobs use 2 nodes.
# Keep NPZ=1 because the benchmark is a one-cell-thick 2D extrusion.
export RESOLVED_NPX="${RESOLVED_NPX:-256}"
export RESOLVED_NPY="${RESOLVED_NPY:-64}"
export RESOLVED_NPZ="${RESOLVED_NPZ:-1}"
export DBS_NPX="${DBS_NPX:-32}"
export DBS_NPY="${DBS_NPY:-8}"
export DBS_NPZ="${DBS_NPZ:-1}"

export RT_CFL_TARGET="${RT_CFL_TARGET:-0.5}"
export RT_LOCAL_VELOCITY_FACTOR="${RT_LOCAL_VELOCITY_FACTOR:-0}"
export RT_FACE_VELOCITY_SAFETY="${RT_FACE_VELOCITY_SAFETY:-1.25}"
export RT_TIMESTEP_MAX="${RT_TIMESTEP_MAX:-0}"
export RT_CHECKPOINT_COUNT

echo "=== ARCHER2 two-scale single-case job ==="
echo "submit_dir=$submit_dir"
echo "work_dir=$work_dir"
echo "archive_dir=$archive_dir"
echo "TARGET_CASE=$TARGET_CASE"
echo "TARGET_PE=$TARGET_PE"
echo "SLURM_NNODES=${SLURM_NNODES:-unknown}"
echo "SLURM_NTASKS=${SLURM_NTASKS:-unknown}"

./runSingleCase.sh
