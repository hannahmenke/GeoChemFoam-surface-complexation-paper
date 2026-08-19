#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"
paper_png_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png"
docs_fig_dir="$repo_root/docs/figures"
micromodel_case_root="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/hm12_fourcase_solver_comparison"

python "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_sphere_surface_area_validation.py" \
  --results-dir "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_sphere_surface_area_benchmark/results" \
  --generated-dir "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_sphere_surface_area_benchmark/generated" \
  --circular-post-snappy-csv "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/2d_circular_post_surface_area_benchmark/results/area_metrics.csv" \
  --output "$paper_png_dir/fig09_sphere_surface_area_validation.png"

"$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_3d_external_surface_area_validation.sh"

if [ -f "$micromodel_case_root/legacy-snappy/processor0/200/Sr+2" ] && \
   [ -f "$micromodel_case_root/dbs-fallback/processor0/200/Sr+2" ] && \
   [ -f "$micromodel_case_root/dbs-smoothinterface/processor0/200/Sr+2" ]; then
  python "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_micromodel_surface_area_validation.py" \
    --legacy-snappy-case "$micromodel_case_root/legacy-snappy" \
    --dbs-gradeps-case "$micromodel_case_root/dbs-fallback" \
    --dbs-smoothsurface-case "$micromodel_case_root/dbs-smoothinterface" \
    --time 200 \
    --cin 1e-4 \
    --nx 600 \
    --ny 600 \
    --res 3e-5 \
    --output-png "$paper_png_dir/fig10_hm12_surface_area_validation.png"
else
  echo "Skipping fig10_hm12_surface_area_validation.png: waiting for snappy, grad-eps, and smoothSurface outputs"
fi

echo "Wrote $paper_png_dir/fig09_sphere_surface_area_validation.png"
echo "Wrote $paper_png_dir/fig10_hm12_surface_area_validation.png"
