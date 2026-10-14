#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

repo_root="$(cd ../../.. && pwd)"
paper_script="$repo_root/figures/scripts/generate_micromodel_surface_area_validation.py"
paper_output="$repo_root/figures/png/fig10_hm12_surface_area_validation.png"
smooth_case="$repo_root/tutorials/reactiveTransport/reactiveTransportDBSFoam/2DHM12SolidGrainsSurfaceComplexation"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
  set +e
  set +u
  # shellcheck disable=SC1091
  source /usr/local/anaconda3/etc/profile.d/conda.sh
  conda activate gcfoam
  set -e
  set -u
fi

if [ -f "$repo_root/etc/bashrc" ]; then
  set +e
  set +u
  # shellcheck disable=SC1090
  source "$repo_root/etc/bashrc"
  set -e
  set -u
fi

run_task() {
  local path="$1"
  echo "--- Running: $path ---"
  ( cd "$path" && ./runAll.sh )
  echo "--- Done: $path ---"
}

echo "=== HM12 resolved-wall/DBS comparison ==="
run_task resolved-snappy
run_task "$smooth_case"

echo "--- Rendering paper figure ---"
python "$paper_script" \
  --resolved-snappy-case "$PWD/resolved-snappy" \
  --dbs-smoothsurface-case "$smooth_case" \
  --time 200 \
  --cin 1e-4 \
  --nx 600 \
  --ny 600 \
  --res 3e-5 \
  --output-png "$paper_output"
echo "--- Figure written to: $paper_output ---"
echo "=== Completed HM12 resolved-wall/DBS comparison ==="
