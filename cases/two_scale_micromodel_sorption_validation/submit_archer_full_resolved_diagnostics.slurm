#!/usr/bin/env bash
#SBATCH --job-name=ts_full_diag
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
#SBATCH --partition=standard
#SBATCH --qos=standard
#SBATCH --account=n03-hw

set -Eeuo pipefail

cd "$SLURM_SUBMIT_DIR"

module purge
# shellcheck disable=SC1091
source /mnt/lustre/a2fs-work3/work/n03/n03/gcfoam_n03/GeoChemFoam-v-dev/.archer2-tools/gcfoam-env.sh

export OMP_NUM_THREADS=1

out_dir="${DIAGNOSTICS_OUTPUT_DIR:-/scratch-nvme/n03/n03/gcfoam_n03/full_run_diagnostics_20260510}"
block="${DIAGNOSTICS_BLOCK:-12}"

python scripts/diagnose_full_resolved_runs.py \
  --output-dir "$out_dir" \
  --block "$block"
