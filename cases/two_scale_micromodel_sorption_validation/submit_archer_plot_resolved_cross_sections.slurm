#!/usr/bin/env bash
#SBATCH --job-name=plot_resolved_xsec
#SBATCH --nodes=1
#SBATCH --ntasks-per-node=1
#SBATCH --cpus-per-task=8
#SBATCH --time=02:00:00
#SBATCH --partition=standard
#SBATCH --qos=standard
#SBATCH --account=n03-hw

set -Eeuo pipefail

cd "$SLURM_SUBMIT_DIR"

export OMP_NUM_THREADS="${SLURM_CPUS_PER_TASK:-1}"

module purge
# shellcheck disable=SC1091
source /mnt/lustre/a2fs-work3/work/n03/n03/gcfoam_n03/GeoChemFoam-v-dev/.archer2-tools/gcfoam-env.sh

python scripts/plot_resolved_cross_section_profiles.py
