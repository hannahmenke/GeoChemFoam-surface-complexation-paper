#!/usr/bin/env bash
#SBATCH --job-name=ts-li-scale
#SBATCH --nodes=16
#SBATCH --ntasks-per-node=128
#SBATCH --cpus-per-task=1
#SBATCH --time=02:00:00
#SBATCH --exclusive
#SBATCH --partition=standard
#SBATCH --account=YOUR_BUDGET_CODE

set -Eeuo pipefail

cd "$SLURM_SUBMIT_DIR"

export PLATFORM=ARCHER2
export OMP_NUM_THREADS=1

# Load the project environment here if it is not already available in the
# submission shell, for example:
# module load ...
# source /path/to/GeoChemFoam/etc/bashrc

# Strong-scaling points for the 108M-cell resolved reference case. Keep NPZ=1
# because the benchmark is a one-cell-thick 2D extrusion.
export SCALING_SPECS="${SCALING_SPECS:-32x16x1 32x32x1 64x32x1}"

# Short reactive window used only to estimate wall seconds per simulated second.
export TARGET_PE="${TARGET_PE:-1}"
export RT_TOTAL_TIME="${RT_TOTAL_TIME:-2}"
export RT_WRITE_TIMESTEP="${RT_WRITE_TIMESTEP:-2}"
export RT_TIMESTEP="${RT_TIMESTEP:-0.05}"

./runArcherResolvedScaling.sh
