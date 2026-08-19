#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"
paper_png_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png"
docs_fig_dir="$repo_root/docs/figures"
snappy_case="$repo_root/tutorials/reactiveTransport/HM12SurfaceComplexationSolverComparison/resolved-snappy"
smooth_case="$repo_root/tutorials/reactiveTransport/reactiveTransportDBSFoam/2DHM12SolidGrainsSurfaceComplexation"

python "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_sphere_surface_area_validation.py" \
  --results-dir "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_sphere_surface_area_benchmark/results" \
  --generated-dir "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_sphere_surface_area_benchmark/generated" \
  --circular-post-snappy-csv "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/2d_circular_post_surface_area_benchmark/results/area_metrics.csv" \
  --output "$paper_png_dir/fig09_sphere_surface_area_validation.png"

"$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_3d_external_surface_area_validation.sh"

if [ -f "$snappy_case/processor0/200/Sr+2" ] && \
   [ -f "$smooth_case/processor0/200/Sr+2" ]; then
  python "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_micromodel_surface_area_validation.py" \
    --resolved-snappy-case "$snappy_case" \
    --dbs-smoothsurface-case "$smooth_case" \
    --time 200 \
    --cin 1e-4 \
    --nx 600 \
    --ny 600 \
    --res 3e-5 \
    --output-png "$paper_png_dir/fig10_hm12_surface_area_validation.png"
else
  echo "Skipping fig10_hm12_surface_area_validation.png: waiting for resolved-wall and smooth-interface outputs"
fi

echo "Wrote $paper_png_dir/fig09_sphere_surface_area_validation.png"
echo "Wrote $paper_png_dir/fig10_hm12_surface_area_validation.png"
