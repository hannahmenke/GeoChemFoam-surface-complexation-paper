#!/usr/bin/env bash

set -euo pipefail

if [ -d processor0 ]; then
    NP="$(find processor* -maxdepth 0 -type d -print | wc -l)"
    echo "Write cell centers in parallel on $NP processors"
    mpirun -np "$NP" processMeshCellCenters -parallel > processMeshCellCenters.out
else
    echo "Write cell centers"
    processMeshCellCenters > processMeshCellCenters.out
fi
