#!/usr/bin/env bash

# Delete solver log files
rm -f *RT.out createASurfReactive.out createASurfIntrinsicReactive.out run_provenance.json

# Delete floating-point time directories at the case root (serial/reconstructed)
rm -rf *e-* 0.*

# Delete integer time directories at the case root (>0) for serial runs
find . -maxdepth 1 -type d -name '[0-9]*' ! -name '0' -exec rm -rf {} +

# Delete integer time directories (>0) from all processor subdirs (parallel runs)
if ls -d processor* > /dev/null 2>&1; then
    find processor* -maxdepth 1 -type d -name '[0-9]*' ! -name '0' -exec rm -rf {} +
fi

# Delete generated species field files from parallel processor/0 dirs
rm -f processor*/0/Pb+2 processor*/0/Cl- processor*/0/H+ processor*/0/OH- \
      processor*/0/Surf_sOH processor*/0/Surf_sO- processor*/0/Surf_sOPb+ \
      processor*/0/Surf_wOH processor*/0/Surf_wO- processor*/0/Surf_wOPb+ \
      processor*/0/Surf_s processor*/0/Surf_w \
      processor*/0/epsNum processor*/0/theta processor*/0/aSurf processor*/0/T

# Delete generated species field files from serial 0/ dir
rm -f 0/T 0/Pb+2 0/Cl- 0/H+ 0/OH- \
      0/Surf_sOH 0/Surf_sO- 0/Surf_sOPb+ \
      0/Surf_wOH 0/Surf_wO- 0/Surf_wOPb+ \
      0/Surf_s 0/Surf_w \
      0/epsNum 0/theta 0/aSurf
