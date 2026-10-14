#!/usr/bin/env bash
#SBATCH --job-name=plot_res_1000
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --time=01:00:00
#SBATCH --partition=standard
#SBATCH --qos=standard

set -Eeuo pipefail

cd "$SLURM_SUBMIT_DIR"
export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"
export MPLCONFIGDIR="${TMPDIR:-/tmp}/matplotlib-${SLURM_JOB_ID}"
mkdir -p "$MPLCONFIGDIR"

if [ -n "${GCFOAM_ENV_FILE:-}" ]; then
    module purge
    # shellcheck disable=SC1090
    source "$GCFOAM_ENV_FILE"
fi

python scripts/plot_resolved_first_1000_fields.py
