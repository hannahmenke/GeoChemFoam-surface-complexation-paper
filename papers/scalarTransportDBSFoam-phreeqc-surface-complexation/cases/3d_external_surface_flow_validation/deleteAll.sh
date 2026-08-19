#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

rm -rf shared results

for case_dir in snappy dbs-gradeps dbs-smoothsurface; do
  if [ -x "$case_dir/deleteAll.sh" ]; then
    (cd "$case_dir" && ./deleteAll.sh)
  fi
  rm -f "$case_dir"/*.out "$case_dir"/*.csv "$case_dir"/*.log
  rm -rf "$case_dir"/processor* "$case_dir"/[1-9]* "$case_dir"/0
  rm -rf "$case_dir"/constant/polyMesh
  find "$case_dir/constant/triSurface" -maxdepth 1 -type f ! -name raw2stl.py -delete 2>/dev/null || true
done
