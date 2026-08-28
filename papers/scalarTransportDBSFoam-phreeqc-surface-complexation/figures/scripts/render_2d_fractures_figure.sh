#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"
case_dir="${ITEM2_CASE_DIR:-$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/2d_4StraightFractures}"
png_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png"
scripts_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts"
provenance_tool="$scripts_dir/figure2_provenance.py"
run_manifest="$case_dir/run_provenance.json"
figure_manifest="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/figure_provenance.json"
numerical_validator="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/2d_4StraightFractures/validate_item2_outputs.py"
validation_metrics="$png_dir/fig02_item2_validation_metrics.json"
validator_sha256="85754589f4e398173664e09aa3435541e5db1c9cc17b8ea4f9ddf04bd23da718"

required_fields=(
  "$case_dir/processor0/20000/Pb+2"
  "$case_dir/processor0/20000/Surf_sOPb+"
  "$case_dir/processor0/0/aSurf"
  "$case_dir/createASurfReactive.out"
  "$case_dir/reactiveTransportDBSFoamRT.out"
  "$numerical_validator"
  "$run_manifest"
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

if [ "$(sha256sum "$numerical_validator" | awk '{print $1}')" != "$validator_sha256" ]; then
  echo "The item-2 numerical validator does not match its pinned SHA256." >&2
  exit 1
fi

python "$provenance_tool" check-run \
  --manifest "$run_manifest" \
  --case-dir "$case_dir" \
  --paper-commit 103685cb597e75c4bdceb84adb9d26ade8604928 \
  --runtime-commit 464dd93606c753269bbd33006510203e46119bd9 \
  --solver-sha256 d7a55047bee24211730e05e6ba7c00752e8c6a07ceb4510572bb8912a6435b10 \
  --library-sha256 libfiniteVolumeGCFOAM.so=e13af080edca54982d9950378ab27d1c0df5cc1b26d384eb6bb64845348502ad \
  --library-sha256 libreactionThermophysicalModelsGCFOAM.so=d3b74ea7cafc3e37935df8752599a4e6cd068b0ac84b046aced6c98f5448a0be \
  --library-sha256 libPhreeqcRM.so=cfa877676ec21145ad60390c992dc7d80773ac4151c3c7c297d3de8ea8cc330a \
  --phreeqcrm-commit 8ce64cf64b3c26ff7fdc41dbf5ae4fb7269b3a92 \
  --surface-mode occupancyGaussian \
  --surface-sigma 0.75 \
  --surface-area 0.021990199701030694 \
  --intrinsic-area 0.021960000000000004 \
  --strong-density 2e-7 \
  --weak-density 6e-6 \
  --time 20000 \
  --delta-t 0.25 \
  --write-interval 2000 \
  --chemistry-input-count 30 \
  --initial-input-count 224

python "$numerical_validator" \
  --case "$case_dir" \
  --log reactiveTransportDBSFoamRT.out \
  --output "$validation_metrics" \
  --end-time 20000 \
  --times 0 2000 4000 6000 8000 10000 12000 14000 16000 18000 20000

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
  --surface-field-name "Surf_sOPb+" \
  --asurf-field-name "aSurf" \
  --aqueous-label 'Pb$^{2+}$' \
  --surface-label 'Hfo$_s$OPb$^+$ / Hfo$_s$' \
  --surface-transform occupancy \
  --surface-site-density 2e-7 \
  --log-scale \
  --surface-log-scale on \
  --time-label "t = 20000 s" \
  --output "$png_dir/fig02_2d_fractures.png"

python "$provenance_tool" record-figure \
  --manifest "$run_manifest" \
  --figure "$png_dir/fig02_2d_fractures.png" \
  --time 20000 \
  --figure-input "$scripts_dir/render_2d_fractures_figure.sh" \
  --figure-input "$scripts_dir/generate_2d_raw_geometry.py" \
  --figure-input "$provenance_tool" \
  --figure-input "$numerical_validator" \
  --figure-input "$validation_metrics" \
  --figure-input "$repo_root/images/raw/4StraightFractures.raw.tar.gz" \
  --figure-input "$repo_root/images/raw/4StraightFractures.txt" \
  --output "$figure_manifest"

echo "Wrote $png_dir/fig02_2d_fractures.png"
