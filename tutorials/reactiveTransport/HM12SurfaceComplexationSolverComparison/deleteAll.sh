#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

repo_root="$(cd ../../.. && pwd)"
paper_output="$repo_root/figures/png/fig10_hm12_surface_area_validation.png"
smooth_case="$repo_root/tutorials/reactiveTransport/reactiveTransportDBSFoam/2DHM12SolidGrainsSurfaceComplexation"

for case_dir in resolved-snappy "$smooth_case"; do
  if [ -x "$case_dir/deleteAll.sh" ]; then
    ( cd "$case_dir" && ./deleteAll.sh )
  fi
done

rm -f "$paper_output"
