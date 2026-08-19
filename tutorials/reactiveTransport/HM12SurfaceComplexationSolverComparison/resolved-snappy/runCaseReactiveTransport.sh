#!/usr/bin/env bash

set -Eeo pipefail

# Explicit-aSurf, fixed-eps cases do not use the solver's auxiliary normalized gradient.
export FOAM_SIGFPE="${FOAM_SIGFPE:-false}"

###### USERS INPUT ############################################################

## Define the total time of the simulation and how often to output concentration fields
TotalTime="${TOTAL_TIME:-200}"
WriteTimestep="${WRITE_TIMESTEP:-200}"
runTimestep="${RUN_TIMESTEP:-0.1}"

#### END OF USER INPUT #######################################################

cp system/controlDictReactiveTransport system/controlDict
sed -i "s/TotalTime/$TotalTime/g" system/controlDict
sed -i "s/WriteTimestep/$WriteTimestep/g" system/controlDict
sed -i "s/runTimestep/$runTimestep/g" system/controlDict

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print| wc -l)"

    echo -e "Run reactiveTransportDBSFoam in parallel on $NP processors"
    mpirun -np $NP reactiveTransportDBSFoam -parallel > reactiveTransportDBSFoamRT.out
else
    echo -e "Run reactiveTransportDBSFoam"
    reactiveTransportDBSFoam > reactiveTransportDBSFoamRT.out
fi
