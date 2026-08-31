#!/usr/bin/env bash

set -euo pipefail

# Explicit-aSurf, fixed-eps cases do not use the solver's auxiliary normalized gradient.
export FOAM_SIGFPE="${FOAM_SIGFPE:-false}"

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
    set +e
    set +u
    # shellcheck disable=SC1091
    source /usr/local/anaconda3/etc/profile.d/conda.sh
    conda activate gcfoam
    set -e
    set -u
fi

# shellcheck disable=SC1090
source "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/configure_runtime.sh"

use_prepared_control="${KELVIN_USE_PREPARED_CONTROL:-false}"
case "$use_prepared_control" in
    true)
        test -f system/controlDict
        test -f system/fvSolution
        ;;
    false)
        TotalTime="${TOTAL_TIME:?Set TOTAL_TIME to the reviewed stage endpoint}"
        WriteTimestep="${WRITE_TIMESTEP:?Set WRITE_TIMESTEP to the reviewed stage interval}"
        runTimestep="${RUN_TIMESTEP:?Set RUN_TIMESTEP to the accepted timestep}"
        cp system/controlDict1 system/controlDict
        sed -i "s/TotalTime/$TotalTime/g" system/controlDict
        sed -i "s/WriteTimestep/$WriteTimestep/g" system/controlDict
        sed -i "s/runTimestep/$runTimestep/g" system/controlDict
        cp system/fvSolution1 system/fvSolution
        ;;
    *)
        echo "KELVIN_USE_PREPARED_CONTROL must be true or false" >&2
        exit 2
        ;;
esac

solver_log="${KELVIN_SOLVER_LOG:-reactiveTransportDBSFoamRT.out}"
read -r -a mpi_args <<< "${KELVIN_MPI_ARGS:-}"

python kelvin_provenance.py record-run \
    --manifest run_provenance.json \
    --case . \
    --control system/controlDict \
    --thermo constant/thermoPhysicalProperties \
    --snapshot-root provenance/stages \
    --dictionary constant/transportProperties \
    --dictionary constant/thermoPhysicalProperties \
    --dictionary constant/dynamicMeshDict \
    --dictionary constant/turbulenceProperties \
    --dictionary system/postProcessDict \
    --dictionary system/controlDict \
    --dictionary system/fvSolution \
    --dictionary system/fvSchemes

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print | wc -l)"
    echo -e "Run reactiveTransportDBSFoam in parallel on $NP processors"
    if [[ "${PLATFORM:-}" == "ARCHER2" ]]; then
        srun reactiveTransportDBSFoam -parallel > "$solver_log" 2>&1
    else
        mpirun "${mpi_args[@]}" -np "$NP" reactiveTransportDBSFoam -parallel > "$solver_log" 2>&1
    fi
else
    reactiveTransportDBSFoam > "$solver_log" 2>&1
fi

python kelvin_provenance.py finalise-run \
    --manifest run_provenance.json \
    --case . \
    --control system/controlDict \
    --solver-log "$solver_log"
