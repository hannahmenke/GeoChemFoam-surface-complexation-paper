#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"
case_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/2d_4StraightFractures"
png_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png"
scripts_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts"

required_fields=(
  "$case_dir/processor0/20000/Pb+2"
  "$case_dir/processor0/20000/Hfo_sOPb+"
  "$case_dir/processor0/0/aSurf"
)

missing=0
for field in "${required_fields[@]}"; do
  if [ ! -f "$field" ]; then
    echo "Missing required 2D fracture output field: $field" >&2
    missing=1
  fi
done

if [ "$missing" -ne 0 ]; then
  echo "Run $case_dir/runAll.sh to completion before regenerating fig02." >&2
  exit 1
fi

python "$scripts_dir/generate_2d_raw_geometry.py" \
  --raw-tar "$repo_root/images/raw/4StraightFractures.raw.tar.gz" \
  --metadata "$repo_root/images/raw/4StraightFractures.txt" \
  --parallel-case "$case_dir" \
  --time-name 20000 \
  --npx 4 \
  --npy 2 \
  --coarse-nx 250 \
  --coarse-ny 250 \
  --res-m 0.0001 \
  --ca-inlet 1e-3 \
  --aqueous-field-name "Pb+2" \
  --surface-field-name "Hfo_sOPb+" \
  --asurf-field-name "aSurf" \
  --aqueous-label "Pb$^{2+}$" \
  --surface-label "Hfo$_s$OPb$^+$ / Hfo$_s$" \
  --surface-transform occupancy \
  --surface-site-density 2e-7 \
  --log-scale \
  --surface-log-scale on \
  --time-label "t = 20000 s" \
  --output "$png_dir/fig02_2d_fractures.png"

echo "Wrote $png_dir/fig02_2d_fractures.png"
