#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"

case_dir="$repo_root/tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DEstailladesMicroporeAsSolidSurfaceComplexation"
output_png="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig04_3d_estaillades_micropore_as_solid_t100.png"
connectivity_image="$repo_root/images/raw/Est_3phase500cubed4micron.raw.tar.gz"

"$script_dir/render_3d_volume_pyvista_egl.sh" \
  --case-dir "$case_dir" \
  --time-name 100 \
  --aqueous-field Sr+2 \
  --aqueous-title "Sr+2 / C_in" \
  --second-aqueous-field Ca+2 \
  --second-aqueous-title "Ca+2 / C_init" \
  --second-aqueous-cmap soft_blues \
  --surface-field Surf_aSr+ \
  --surface-mask-field aSurf \
  --connectivity-image "$connectivity_image" \
  --connectivity-pore-value 1 \
  --connectivity-remap-from 2 \
  --connectivity-remap-to 3 \
  --surface-render-mode interface_surface \
  --surface-interface-clip-fraction 1.00 \
  --surface-log-scale \
  --surface-title "Surf_aSr+" \
  --output "$output_png"

stat -c '%y %s %n' "$output_png"
