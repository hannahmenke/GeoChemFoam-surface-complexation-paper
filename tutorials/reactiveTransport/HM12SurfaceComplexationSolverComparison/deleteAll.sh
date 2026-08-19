#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

repo_root="$(cd ../../.. && pwd)"
paper_output="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/hm12_fourcase_solver_comparison_t200.png"

for case_dir in legacy-snappy legacy-subset dbs-file dbs-fallback; do
  if [ -x "$case_dir/deleteAll.sh" ]; then
    ( cd "$case_dir" && ./deleteAll.sh )
  fi
done

rm -f "$paper_output"
