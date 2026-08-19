#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

repo_root="$(cd ../../../.. && pwd)"

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

run_case() {
  local case_dir="$1"
  echo "=== Running $case_dir ==="
  (cd "$case_dir" && ./runAll.sh)
  echo "=== Completed $case_dir ==="
}

./deleteAll.sh
mkdir -p results

python scripts/prepare_external_crop.py

run_case snappy
run_case dbs-gradeps
run_case dbs-smoothsurface

python scripts/analyze_external_flow_validation.py \
  --output-csv results/summary.csv \
  --output-json results/summary.json

echo "Wrote results/summary.csv"
echo "Wrote results/summary.json"
