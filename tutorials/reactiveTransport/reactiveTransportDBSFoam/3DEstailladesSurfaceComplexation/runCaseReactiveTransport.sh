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

if [ -f "$repo_root/etc/bashrc" ]; then
    set +e
    set +u
    # shellcheck disable=SC1090
    source "$repo_root/etc/bashrc"
    set -e
    set -u
fi

TotalTime="${TOTAL_TIME:-100}"
WriteTimestep="${WRITE_TIMESTEP:-20}"
runTimestep="${RUN_TIMESTEP:-5}"

cp system/controlDict1 system/controlDict
sed -i "s/TotalTime/$TotalTime/g" system/controlDict
sed -i "s/WriteTimestep/$WriteTimestep/g" system/controlDict
sed -i "s/runTimestep/$runTimestep/g" system/controlDict

cp system/fvSolution1 system/fvSolution

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print | wc -l)"
    echo -e "Run reactiveTransportDBSFoam in parallel on $NP processors"
    if [[ "${PLATFORM:-}" == "ARCHER2" ]]; then
        srun reactiveTransportDBSFoam -parallel > reactiveTransportDBSFoamRT.out
    else
        mpirun -np "$NP" reactiveTransportDBSFoam -parallel > reactiveTransportDBSFoamRT.out
    fi
else
    reactiveTransportDBSFoam > reactiveTransportDBSFoamRT.out
fi
