#!/usr/bin/env bash
#SBATCH --job-name=ts-li-scale
#SBATCH --nodes=16
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
#SBATCH --exclusive
#SBATCH --partition=standard
#SBATCH --qos=standard
#SBATCH --account=n03-hw

set -Eeuo pipefail

submit_dir="$SLURM_SUBMIT_DIR"
scratch_parent="${RESOLVED_SCALING_WORK_PARENT:-/scratch-nvme/n03/n03/gcfoam_n03}"
work_dir="${RESOLVED_SCALING_WORK_DIR:-$scratch_parent/resolved_scaling_${SLURM_JOB_ID}}"
archive_dir="${RESOLVED_SCALING_ARCHIVE_DIR:-$submit_dir/results/archer/resolved_scaling_${SLURM_JOB_ID}}"

case "$work_dir" in
  /tmp|/tmp/*)
    echo "Resolved scaling work_dir resolves to node-local $work_dir; use shared scratch-nvme or Lustre." >&2
    exit 4
    ;;
esac

mkdir -p "$work_dir" "$archive_dir"

rsync -a \
  --exclude 'archer_work' \
  --exclude 'results/archer' \
  --exclude 'results/scaling' \
  --exclude 'processor*' \
  --exclude '0' \
  --exclude '*.out' \
  --exclude 'log.*' \
  "$submit_dir"/ "$work_dir"/

cd "$work_dir"

export PLATFORM=ARCHER2
export OMP_NUM_THREADS=1

if [ -n "${GCFOAM_ENV_FILE:-}" ]; then
  module purge
  # shellcheck disable=SC1090
  source "$GCFOAM_ENV_FILE"
elif ! command -v reactiveScalarTransportDBSFoam >/dev/null 2>&1 || \
     [ -z "${WM_PROJECT_DIR:-}" ]; then
  echo "Load GeoChemFoam/OpenFOAM before sbatch or set GCFOAM_ENV_FILE." >&2
  exit 2
fi

# Strong-scaling points for the 108M-cell resolved reference case. Keep NPZ=1
# because the benchmark is a one-cell-thick 2D extrusion.
export SCALING_SPECS="${SCALING_SPECS:-32x16x1 32x32x1 64x32x1}"

# Short reactive window used only to estimate wall seconds per simulated second.
export TARGET_PE="${TARGET_PE:-1}"
export RT_TOTAL_TIME="${RT_TOTAL_TIME:-2}"
export RT_WRITE_TIMESTEP="${RT_WRITE_TIMESTEP:-2}"
export RT_CFL_TARGET="${RT_CFL_TARGET:-0.8}"
export RT_LOCAL_VELOCITY_FACTOR="${RT_LOCAL_VELOCITY_FACTOR:-2.5}"
export RT_TIMESTEP_MAX="${RT_TIMESTEP_MAX:-0}"

echo "=== ARCHER2 resolved scaling job ==="
echo "submit_dir=$submit_dir"
echo "work_dir=$work_dir"
echo "archive_dir=$archive_dir"
echo "SCALING_SPECS=$SCALING_SPECS"
echo "TARGET_PE=$TARGET_PE"
echo "RT_TOTAL_TIME=$RT_TOTAL_TIME"
echo "RT_CFL_TARGET=$RT_CFL_TARGET"
echo "RT_LOCAL_VELOCITY_FACTOR=$RT_LOCAL_VELOCITY_FACTOR"

./runArcherResolvedScaling.sh

rsync -a results/scaling/ "$archive_dir/scaling/"

echo "=== Archived resolved scaling timing artifacts to $archive_dir ==="
echo "=== Scratch working directory retained at $work_dir (scratch-nvme purge policy applies) ==="
