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

TotalTime="${RT_TOTAL_TIME:-200}"
WriteTimestep="${RT_WRITE_TIMESTEP:-$TotalTime}"
runTimestep="${RT_TIMESTEP:-0.01}"

cp system/controlDict1 system/controlDict
sed -i "s/TotalTime/$TotalTime/g" system/controlDict
sed -i "s/WriteTimestep/$WriteTimestep/g" system/controlDict
sed -i "s/runTimestep/$runTimestep/g" system/controlDict

cp system/fvSolution1 system/fvSolution

# Do not trust a stored reactive-transport phi. Deleting it forces createPhi.H
# to rebuild the advective flux from the current U field at solver startup.
rm -f 0/phi processor*/0/phi
echo "Removed stored phi fields; reactive transport will rebuild phi from U."
echo "Reactive transport controls: endTime=${TotalTime}, writeInterval=${WriteTimestep}, deltaT=${runTimestep}"

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print | wc -l)"
    echo -e "Run reactiveScalarTransportDBSFoam in parallel on $NP processors"
    if [[ "${PLATFORM:-}" == "ARCHER2" ]]; then
        srun reactiveScalarTransportDBSFoam -parallel > reactiveScalarTransportDBSFoamRT.out
    else
        mpirun -np "$NP" reactiveScalarTransportDBSFoam -parallel > reactiveScalarTransportDBSFoamRT.out
    fi
else
    reactiveScalarTransportDBSFoam > reactiveScalarTransportDBSFoamRT.out
fi
