#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

repo_root="$(cd ../../.. && pwd)"
paper_script="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_hm12_fourcase_conc_sorbed_diff.py"
paper_output="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/hm12_fourcase_solver_comparison_t200.png"

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

echo "=== HM12 four-case solver comparison ==="
run_task legacy-snappy
run_task legacy-subset
run_task dbs-file
run_task dbs-fallback

echo "--- Rendering paper figure ---"
python "$paper_script" \
  --legacy-snappy-case "$PWD/legacy-snappy" \
  --legacy-subset-case "$PWD/legacy-subset" \
  --dbs-file-case "$PWD/dbs-file" \
  --dbs-fallback-case "$PWD/dbs-fallback" \
  --time 200 \
  --cin 1e-4 \
  --nx 600 \
  --ny 600 \
  --res 3e-5 \
  --output-png "$paper_output"
echo "--- Figure written to: $paper_output ---"
echo "=== Completed HM12 four-case solver comparison ==="
