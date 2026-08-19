#!/bin/bash

###### USERS INPUT ############################################################

## Define the total time of the simulation and how often to output concentration fields
TotalTime=200
WriteTimestep=200
runTimestep=0.1

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
