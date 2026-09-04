#!/usr/bin/env bash

set -euo pipefail
case_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
paper_dir="$(cd -- "$case_dir/../.." && pwd)"

python3 "$paper_dir/figures/scripts/run_2d_circular_post_snappy_benchmark.py" \
  --output-dir "$case_dir/results"
