#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../../.. && pwd)"

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

###### USERS INPUT ############################################################

## Define the total time of the simulation and how often to output concentration fields
TotalTime="${TOTAL_TIME:-2.5}"
WriteTimestep="${WRITE_TIMESTEP:-2.5}"
runTimestep="${RUN_TIMESTEP:-0.01}"

#### END OF USER INPUT #######################################################

cp system/controlDictReactiveTransport system/controlDict
sed -i "s/TotalTime/$TotalTime/g" system/controlDict
sed -i "s/WriteTimestep/$WriteTimestep/g" system/controlDict
sed -i "s/runTimestep/$runTimestep/g" system/controlDict

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print| wc -l)"

    # Run reactiveScalarTransportFoam in parallel
    echo -e "Run reactiveScalarTransportFoam in parallel on $NP processors"
    mpirun -np $NP reactiveScalarTransportFoam -parallel  > reactiveScalarTransportFoamRT.out
else
    echo -e "Run reactiveScalarTransportFoam"
    reactiveScalarTransportFoam > reactiveScalarTransportFoamRT.out
fi
