#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

repo_root="$(cd ../../../.. && pwd)"
case_dir="$PWD"
paper_png_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png"
script="$case_dir/scripts/generate_3d_external_surface_area_validation.py"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
  set +e
  set +u
  # shellcheck disable=SC1091
  source /usr/local/anaconda3/etc/profile.d/conda.sh
  conda activate gcfoam
  set -e
  set -u
fi

mkdir -p "$case_dir/results" "$paper_png_dir"

python "$script" \
  --output "$paper_png_dir/fig11_3d_external_surface_area_validation.png" \
  --output-csv "$case_dir/results/area_metrics.csv" \
  --output-json "$case_dir/results/area_metrics.json"

echo "Wrote $case_dir/results/area_metrics.csv"
echo "Wrote $case_dir/results/area_metrics.json"
echo "Wrote $paper_png_dir/fig11_3d_external_surface_area_validation.png"
