#!/bin/bash

set -e

###### USERS INPUT ############################################################

## Define the total number of iterations of the simulation
TotalTime=25
WriteTimestep=5
runTimestep=5
BalanceRelTol=5e-8

#### END OF USER INPUT #######################################################

./deleteAll.sh
./createMesh.sh
./initCaseFlow.sh
./initCaseTransportThetaSplitClosed.sh

cp system/controlDict1 system/controlDict
sed -i "s/startFrom       latestTime;/startFrom       startTime;/" system/controlDict
sed -i "s/TotalTime/$TotalTime/g" system/controlDict
sed -i "s/WriteTimestep/$WriteTimestep/g" system/controlDict
sed -i "s/runTimestep/$runTimestep/g" system/controlDict

cp system/fvSolution1 system/fvSolution

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print| wc -l)"
    echo -e "Run theta-split closed multiScalarTransportDBSFoam in parallel on $NP processors"

    if [[ "${PLATFORM}" == "ARCHER2" ]]; then
        srun multiScalarTransportDBSFoam -parallel > multiScalarTransportDBSFoamT_closed_thetaSplit.out
    else
        mpirun -np $NP multiScalarTransportDBSFoam -parallel > multiScalarTransportDBSFoamT_closed_thetaSplit.out
    fi
else
    echo -e "Run theta-split closed multiScalarTransportDBSFoam"
    multiScalarTransportDBSFoam > multiScalarTransportDBSFoamT_closed_thetaSplit.out
fi

./checkClosedSystemSpeciesBalance.sh multiScalarTransportDBSFoamT_closed_thetaSplit.out "$BalanceRelTol"
