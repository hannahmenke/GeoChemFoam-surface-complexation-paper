#!/usr/bin/env bash
#SBATCH --job-name=ts-li-case
#SBATCH --nodes=50
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=24:00:00
#SBATCH --exclusive
#SBATCH --partition=standard
#SBATCH --account=YOUR_BUDGET_CODE

set -Eeuo pipefail

submit_dir="$SLURM_SUBMIT_DIR"
case_root_name="two_scale_${TARGET_CASE:-resolved-reference}_pe_${TARGET_PE:-1}_${SLURM_JOB_ID}"
scratch_parent="${SCRATCH:-${TMPDIR:-$submit_dir/archer_work}}"
work_dir="${TWO_SCALE_WORK_DIR:-$scratch_parent/$case_root_name}"
archive_dir="${TWO_SCALE_ARCHIVE_DIR:-$submit_dir/results/archer/$case_root_name}"

mkdir -p "$work_dir" "$archive_dir"

TARGET_CASE="${TARGET_CASE:-resolved-reference}"
TARGET_PE="${TARGET_PE:-1}"
RT_CHECKPOINT_COUNT="${RT_CHECKPOINT_COUNT:-10}"

estimate_bytes() {
  python - <<'PY' "$TARGET_CASE" "$RT_CHECKPOINT_COUNT"
import sys

case_name = sys.argv[1]
checkpoint_count = max(1, int(float(sys.argv[2])))
if case_name == "resolved-reference":
    cells = 18000 * 6000
elif case_name == "dbs-upscaled":
    cells = 3600 * 1200
else:
    raise SystemExit(f"unknown TARGET_CASE: {case_name}")

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
print(int(estimated))
PY
}

available_bytes() {
  df -PB1 "$1" | awk 'NR==2 {print $4}'
}

human_bytes() {
  numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "${1} B"
}

required_bytes="${TWO_SCALE_REQUIRED_BYTES:-$(estimate_bytes)}"
scratch_available="$(available_bytes "$work_dir")"
archive_available="$(available_bytes "$archive_dir")"

echo "=== Disk/quota preflight ==="
echo "TARGET_CASE=$TARGET_CASE"
echo "TARGET_PE=$TARGET_PE"
echo "RT_CHECKPOINT_COUNT=$RT_CHECKPOINT_COUNT"
echo "estimated_required=$(human_bytes "$required_bytes")"
echo "scratch_available=$(human_bytes "$scratch_available") at $work_dir"
echo "archive_available=$(human_bytes "$archive_available") at $archive_dir"

if [ "$scratch_available" -lt "$required_bytes" ]; then
  echo "Insufficient scratch space for estimated run output." >&2
  exit 3
fi
if [ "$archive_available" -lt "$required_bytes" ]; then
  echo "Insufficient archive space for estimated synchronized output." >&2
  exit 3
fi

sync_back() {
  rc=$?
  mkdir -p "$archive_dir"
  if [ -d "$work_dir/results" ]; then
    rsync -a "$work_dir/results/" "$archive_dir/results/" || true
  fi
  for case_dir in resolved-reference dbs-upscaled; do
    if [ -d "$work_dir/$case_dir" ]; then
      mkdir -p "$archive_dir/$case_dir"
      rsync -a \
        --include='*/' \
        --include='*.out' \
        --include='poroPerm.csv' \
        --include='system/controlDict' \
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
  done
  echo "$rc" > "$archive_dir/slurm_exit_code.txt"
  exit "$rc"
}
trap sync_back EXIT

cd "$submit_dir"

rsync -a \
  --exclude='results/' \
  --exclude='archer_work/' \
  --exclude='*/0/' \
  --exclude='*/processor*/' \
  --exclude='*/constant/polyMesh/' \
  --exclude='*/constant/triSurface/' \
  --exclude='*/constant/aSurfReconstructionDict' \
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

# Load the site/project environment here if it is not already available in the
# submission shell, for example:
# module load ...
# source /path/to/GeoChemFoam/etc/bashrc

export TARGET_CASE
export TARGET_PE

# The submit-all helper overrides node count by case: resolved jobs use 50
# nodes and DBS jobs use 2 nodes. Keep NPZ=1 because the benchmark is a
# one-cell-thick 2D extrusion.
export RESOLVED_NPX="${RESOLVED_NPX:-160}"
export RESOLVED_NPY="${RESOLVED_NPY:-40}"
export RESOLVED_NPZ="${RESOLVED_NPZ:-1}"
export DBS_NPX="${DBS_NPX:-32}"
export DBS_NPY="${DBS_NPY:-8}"
export DBS_NPZ="${DBS_NPZ:-1}"

export RT_TIMESTEP_REF_PE="${RT_TIMESTEP_REF_PE:-1}"
export RT_TIMESTEP_REF="${RT_TIMESTEP_REF:-0.01}"
export RT_TIMESTEP_MAX="${RT_TIMESTEP_MAX:-0.1}"
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
