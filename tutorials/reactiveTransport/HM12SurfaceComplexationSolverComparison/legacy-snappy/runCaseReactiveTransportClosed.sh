#!/bin/bash

set -e

cp system/controlDictReactiveTransportClosed system/controlDict

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print | wc -l)"

    echo -e "Run reactiveScalarTransportFoam closed-system case in parallel on $NP processors"
    mpirun -np "$NP" reactiveScalarTransportFoam -parallel > reactiveScalarTransportFoamRT_closed.out
else
    echo -e "Run reactiveScalarTransportFoam closed-system case"
    reactiveScalarTransportFoam > reactiveScalarTransportFoamRT_closed.out
fi
