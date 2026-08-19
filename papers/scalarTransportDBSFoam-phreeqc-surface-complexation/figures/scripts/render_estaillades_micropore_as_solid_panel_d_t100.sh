#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"

case_dir="$repo_root/tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DEstailladesMicroporeAsSolidSurfaceComplexation"
panel_png="/tmp/fig04_3d_estaillades_micropore_as_solid_panel_d_t100.png"
output_png="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig04_3d_estaillades_micropore_as_solid_t100.png"
connectivity_image="$repo_root/images/raw/Est_3phase500cubed4micron.raw.tar.gz"

python "$script_dir/generate_estaillades_micropore_as_solid_surface_panel.py" \
  --case-dir "$case_dir" \
  --time-name 100 \
  --surface-field Surf_aSr+ \
  --surface-mask-field aSurf \
  --connectivity-image "$connectivity_image" \
  --connectivity-pore-value 1 \
  --connectivity-remap-from 2 \
  --connectivity-remap-to 3 \
  --lower-quantile 0.25 \
  --upper-quantile 0.999 \
  --surface-interface-clip-fraction 1.0 \
  --surface-projection-radius 8.0 \
  --clip-xmax-frac 0.82 \
  --clip-ymin-frac 0.18 \
  --clip-zmax-frac 0.92 \
  --surface-log-scale \
  --surface-title "Surf_aSr+" \
  --output "$panel_png"

python "$script_dir/composite_panel_d_into_estaillades_binary.py" \
  --base-figure "$output_png" \
  --panel-d "$panel_png" \
  --output "$output_png"

stat -c '%y %s %n' "$output_png"
