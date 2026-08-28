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
ASURF_SURFACE_MODE="${ASURF_SURFACE_MODE:-occupancyGaussian}"
SURFACE_RECONSTRUCTION_LABEL="${SURFACE_RECONSTRUCTION_LABEL:-production}"
if [[ ! "$SURFACE_RECONSTRUCTION_LABEL" =~ ^[a-z0-9][a-z0-9-]*$ ]]; then
  echo "Invalid SURFACE_RECONSTRUCTION_LABEL=$SURFACE_RECONSTRUCTION_LABEL" >&2
  exit 2
fi
PAPER_SOURCE_COMMIT="$(git -C "$submit_dir" rev-parse HEAD)"
if [ -n "$(git -C "$submit_dir" status --porcelain --untracked-files=no)" ]; then
  echo "Production submission requires a clean paper checkout." >&2
  exit 2
fi
case_root_name="two_scale_${TARGET_CASE}_pe_${TARGET_PE}_${SURFACE_RECONSTRUCTION_LABEL}_${SLURM_JOB_ID}"
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
  python "$submit_dir/scripts/estimate_archer_storage.py" \
    --case "$TARGET_CASE" \
    --checkpoint-count "$RT_CHECKPOINT_COUNT" \
    --scope "$1" \
    --archive-mode "$archive_mode" \
    --override "${2:-}"
}

available_bytes() {
  df -PB1 "$1" | awk 'NR==2 {print $4}'
}

human_bytes() {
  numfmt --to=iec --suffix=B "$1" 2>/dev/null || echo "${1} B"
}

modeled_scratch_required_bytes="$(estimate_bytes scratch)"
modeled_archive_required_bytes="$(estimate_bytes archive)"
scratch_required_bytes="$(estimate_bytes scratch "${TWO_SCALE_REQUIRED_BYTES:-}")"
archive_required_bytes="$(estimate_bytes archive "${TWO_SCALE_ARCHIVE_REQUIRED_BYTES:-}")"
scratch_available="$(available_bytes "$work_dir")"
archive_available="$(available_bytes "$archive_dir")"
matched_pair_scratch_required_bytes=$((2 * scratch_required_bytes))
matched_pair_archive_required_bytes=$((2 * archive_required_bytes))

echo "=== Disk/quota preflight ==="
echo "TARGET_CASE=$TARGET_CASE"
echo "TARGET_PE=$TARGET_PE"
echo "RT_CHECKPOINT_COUNT=$RT_CHECKPOINT_COUNT"
echo "TWO_SCALE_ARCHIVE_MODE=$archive_mode"
echo "modeled_scratch_required=$(human_bytes "$modeled_scratch_required_bytes")"
echo "modeled_archive_required=$(human_bytes "$modeled_archive_required_bytes")"
echo "estimated_scratch_required=$(human_bytes "$scratch_required_bytes")"
echo "estimated_archive_required=$(human_bytes "$archive_required_bytes")"
echo "estimated_matched_pair_scratch_required=$(human_bytes "$matched_pair_scratch_required_bytes")"
echo "estimated_matched_pair_archive_required=$(human_bytes "$matched_pair_archive_required_bytes")"
echo "scratch_available=$(human_bytes "$scratch_available") at $work_dir"
echo "archive_available=$(human_bytes "$archive_available") at $archive_dir"

mkdir -p "$work_dir/results"
cat > "$work_dir/results/storage_preflight.env" <<EOF
STORAGE_ESTIMATE_MODEL=retained-checkpoints-v2
TARGET_CASE=$TARGET_CASE
TARGET_PE=$TARGET_PE
RT_CHECKPOINT_COUNT=$RT_CHECKPOINT_COUNT
TWO_SCALE_ARCHIVE_MODE=$archive_mode
MODELED_SCRATCH_REQUIRED_BYTES=$modeled_scratch_required_bytes
MODELED_ARCHIVE_REQUIRED_BYTES=$modeled_archive_required_bytes
REQUIRED_SCRATCH_BYTES=$scratch_required_bytes
REQUIRED_ARCHIVE_BYTES=$archive_required_bytes
MATCHED_PAIR_REQUIRED_SCRATCH_BYTES=$matched_pair_scratch_required_bytes
MATCHED_PAIR_REQUIRED_ARCHIVE_BYTES=$matched_pair_archive_required_bytes
SCRATCH_AVAILABLE_BYTES=$scratch_available
ARCHIVE_AVAILABLE_BYTES=$archive_available
EOF

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
        --include='system/Nx1' \
        --include='system/Ny1' \
        --include='system/NPX' \
        --include='system/NPY' \
        --include='system/NPZ' \
        --include='system/cellSize' \
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
        --include='processor*/[0-9]*/eps' \
        --include='processor*/[0-9]*/*aLi' \
        --include='processor*/[0-9]*/*aNa' \
        --include='processor*/[0-9]*/*aK' \
        --include='processor*/[0-9]*/*aMg+' \
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

export TARGET_CASE TARGET_PE ASURF_SURFACE_MODE SURFACE_RECONSTRUCTION_LABEL
export PAPER_SOURCE_COMMIT

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
echo "SURFACE_RECONSTRUCTION_LABEL=$SURFACE_RECONSTRUCTION_LABEL"
echo "ASURF_SURFACE_MODE=$ASURF_SURFACE_MODE"
echo "PAPER_SOURCE_COMMIT=$PAPER_SOURCE_COMMIT"
echo "SLURM_NNODES=${SLURM_NNODES:-unknown}"
echo "SLURM_NTASKS=${SLURM_NTASKS:-unknown}"

./runSingleCase.sh
