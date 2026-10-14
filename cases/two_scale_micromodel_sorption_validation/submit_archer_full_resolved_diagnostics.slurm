#!/usr/bin/env bash
#SBATCH --job-name=ts_full_diag
#SBATCH --nodes=1
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
#SBATCH --partition=standard
#SBATCH --qos=standard

set -Eeuo pipefail

cd "$SLURM_SUBMIT_DIR"

if [ -n "${GCFOAM_ENV_FILE:-}" ]; then
    module purge
    # shellcheck disable=SC1090
    source "$GCFOAM_ENV_FILE"
fi

export OMP_NUM_THREADS=1

out_dir="${DIAGNOSTICS_OUTPUT_DIR:-$SLURM_SUBMIT_DIR/results/archer/full_run_diagnostics_${SLURM_JOB_ID:-manual}}"
mkdir -p -- "$out_dir"
block="${DIAGNOSTICS_BLOCK:-12}"

python scripts/diagnose_full_resolved_runs.py \
  --output-dir "$out_dir" \
  --block "$block"
