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

run_case_async() {
  local case_dir="$1"
  local log_dir="$2"
  (
    cd "$case_dir"
    echo "=== Run: $case_dir ==="
    ./runAll.sh
    echo "=== Completed: $case_dir ==="
  ) > "$log_dir/${case_dir}.log" 2>&1 &
  echo "$!" > "$log_dir/${case_dir}.pid"
  echo "started $case_dir pid=$(cat "$log_dir/${case_dir}.pid") log=$log_dir/${case_dir}.log"
}

./deleteAll.sh
mkdir -p results/parallel-logs

python scripts/prepare_external_crop.py

cases=(snappy dbs-gradeps dbs-smoothsurface)
for case_dir in "${cases[@]}"; do
  run_case_async "$case_dir" "results/parallel-logs"
done

failed=0
for case_dir in "${cases[@]}"; do
  pid="$(cat "results/parallel-logs/${case_dir}.pid")"
  if wait "$pid"; then
    echo "completed $case_dir"
    echo "0" > "results/parallel-logs/${case_dir}.status"
  else
    rc="$?"
    echo "failed $case_dir rc=$rc"
    echo "$rc" > "results/parallel-logs/${case_dir}.status"
    failed=1
  fi
done

if [ "$failed" -ne 0 ]; then
  echo "At least one case failed; skipping summary analysis."
  exit 1
fi

python scripts/analyze_external_flow_validation.py \
  --output-csv results/summary.csv \
  --output-json results/summary.json

echo "Wrote results/summary.csv"
echo "Wrote results/summary.json"
