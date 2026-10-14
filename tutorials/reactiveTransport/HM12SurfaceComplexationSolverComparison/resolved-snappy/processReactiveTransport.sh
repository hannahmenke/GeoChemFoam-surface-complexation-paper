#!/usr/bin/env bash

set -Eeo pipefail

###### USERS INPUT ############################################################

#### END OF USER INPUT #######################################################

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print| wc -l)"

    echo -e "Write cell centers in parallel on $NP processors"
    mpirun -np "$NP" processMeshCellCenters -parallel > processMeshCellCenters.out
else
    echo -e "Write cell centers"
    processMeshCellCenters > processMeshCellCenters.out
fi
