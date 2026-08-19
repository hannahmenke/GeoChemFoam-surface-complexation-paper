#!/bin/bash

###### USERS INPUT ############################################################

## Define the total number of iterations of the simulation
TotalTime="${FLOW_TOTAL_TIME:-300}"

#### END OF USER INPUT #######################################################

cp system/controlDict1 system/controlDict
sed -i "s/TotalTime/$TotalTime/g" system/controlDict
sed -i "s/WriteTimestep/$TotalTime/g" system/controlDict
sed -i "s/runTimestep/1/g" system/controlDict

cp system/fvSolution1 system/fvSolution

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print| wc -l)"
    # Run simpleFoam in parallel
    echo -e "Run simpleDBSFoam in parallel on $NP processors"
    # if PLATFORM is ARCHER2 then use srun, otherwise use serial version
    if [[ "${PLATFORM}" == "ARCHER2" ]]; then
        flow_log="simpleDBSFoam.out"
        srun --ntasks="$NP" simpleDBSFoam -parallel  > "$flow_log"
    else
        flow_log="simpleDBSFoamFlow.out"
        mpirun -np $NP simpleDBSFoam -parallel  > "$flow_log"
    fi
else
    echo -e "Run simpleDBSFoam"
    flow_log="simpleDBSFoamFlow.out"
    simpleDBSFoam > "$flow_log"
fi 

python ../scripts/check_flow_convergence.py "$flow_log"
