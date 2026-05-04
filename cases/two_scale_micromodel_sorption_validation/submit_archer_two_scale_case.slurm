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

export TARGET_CASE="${TARGET_CASE:-resolved-reference}"
export TARGET_PE="${TARGET_PE:-1}"

# 50 ARCHER2 nodes x 128 MPI ranks per node = 6400 ranks. These decompositions
# keep NPZ=1 because the benchmark is a one-cell-thick 2D extrusion.
export RESOLVED_NPX="${RESOLVED_NPX:-160}"
export RESOLVED_NPY="${RESOLVED_NPY:-40}"
export RESOLVED_NPZ="${RESOLVED_NPZ:-1}"
export DBS_NPX="${DBS_NPX:-160}"
export DBS_NPY="${DBS_NPY:-40}"
export DBS_NPZ="${DBS_NPZ:-1}"

export RT_TIMESTEP_REF_PE="${RT_TIMESTEP_REF_PE:-1}"
export RT_TIMESTEP_REF="${RT_TIMESTEP_REF:-0.01}"
export RT_TIMESTEP_MAX="${RT_TIMESTEP_MAX:-0.1}"
export RT_CHECKPOINT_COUNT="${RT_CHECKPOINT_COUNT:-10}"

echo "=== ARCHER2 two-scale single-case job ==="
echo "submit_dir=$submit_dir"
echo "work_dir=$work_dir"
echo "archive_dir=$archive_dir"
echo "TARGET_CASE=$TARGET_CASE"
echo "TARGET_PE=$TARGET_PE"
echo "SLURM_NNODES=${SLURM_NNODES:-unknown}"
echo "SLURM_NTASKS=${SLURM_NTASKS:-unknown}"

./runSingleCase.sh
