#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"
case_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/1d_linear_retardation"
png_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png"
scripts_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts"

required_files=(
  "$case_dir/results/transport_surface/Ca+2"
  "$case_dir/results/transport_surface/Surf_aCa+"
  "$case_dir/results/transport_aqueous/Ca+2"
  "$case_dir/phase8_batch_secant.out"
)

missing=0
for path in "${required_files[@]}"; do
  if [ ! -f "$path" ]; then
    echo "Missing required 1D validation output: $path" >&2
    missing=1
  fi
done

if [ "$missing" -ne 0 ]; then
  echo "Run $case_dir/runAll.sh to completion before regenerating 1D figures." >&2
  exit 1
fi

k_s="$(awk -F= '/^K_s_field=/{print $2}' "$case_dir/phase8_batch_secant.out" | tail -n 1)"
if [ -z "$k_s" ]; then
  echo "Could not read K_s_field from $case_dir/phase8_batch_secant.out" >&2
  exit 1
fi

python "$scripts_dir/generate_1d_retardation_plot.py" \
  --surface-ca "$case_dir/results/transport_surface/Ca+2" \
  --surface-loading "$case_dir/results/transport_surface/Surf_aCa+" \
  --aqueous-ca "$case_dir/results/transport_aqueous/Ca+2" \
  --k-s-field "$k_s" \
  --c-in 2e-9 \
  --theta 0.5 \
  --asurf 1e5 \
  --diffusion 1e-11 \
  --length 8e-5 \
  --time 10 \
  --u 1e-6 \
  --output "$png_dir/fig01_1d_retardation.png"

python "$scripts_dir/generate_1d_breakthrough_plot.py" \
  --surface-dir "$case_dir/results/transport_surface" \
  --aqueous-dir "$case_dir/results/transport_aqueous" \
  --k-s "$k_s" \
  --ca-in 2e-9 \
  --output "$png_dir/fig06_1d_breakthrough.png"

echo "Wrote $png_dir/fig01_1d_retardation.png"
echo "Wrote $png_dir/fig06_1d_breakthrough.png"
