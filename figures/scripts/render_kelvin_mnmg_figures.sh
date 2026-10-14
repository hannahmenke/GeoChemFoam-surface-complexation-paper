#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../.. && pwd)"
case_dir="$repo_root/tutorials/reactiveTransport/reactiveTransportDBSFoam/3DKelvinSurfaceComplexation"
png_dir="$repo_root/figures/png"
scripts_dir="$repo_root/figures/scripts"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
  set +e
  set +u
  # shellcheck disable=SC1091
  source /usr/local/anaconda3/etc/profile.d/conda.sh
  conda activate gcfoam
  set -e
  set -u
fi

required_fields=(
  "$case_dir/processor0/120/Mn+2"
  "$case_dir/processor0/120/Mg+2"
  "$case_dir/processor0/120/Surf_sOMn+"
  "$case_dir/processor0/120/Surf_wOMn+"
  "$case_dir/processor0/120/Surf_wOMg+"
  "$case_dir/processor0/0/Surf_sOMn+"
  "$case_dir/processor0/0/Surf_wOMn+"
  "$case_dir/processor0/0/Surf_wOMg+"
)

missing=0
for field in "${required_fields[@]}"; do
  if [ ! -f "$field" ]; then
    echo "Missing required Kelvin output field: $field" >&2
    missing=1
  fi
done

if [ "$missing" -ne 0 ]; then
  echo "Run $case_dir/runAll.sh to completion before regenerating Kelvin figures." >&2
  exit 1
fi

python "$scripts_dir/generate_kelvin_competition_figure.py" \
  --case-dir "$case_dir" \
  --time-name 120 \
  --surface-baseline-time 0 \
  --target-field "Mn+2" \
  --background-field "Mg+2" \
  --surf-target-fields "Surf_sOMn+,Surf_wOMn+" \
  --surf-background-fields "Surf_wOMg+" \
  --target-label 'Mn$^{2+}$ / C$_{in}$' \
  --background-label 'Mg$^{2+}$ / C$_{init}$' \
  --surf-target-label='$\Delta$HFO-Mn' \
  --surf-background-label='HFO-Mg loss' \
  --axis-font-size 28 \
  --axis-label-format '%.0f' \
  --output "$png_dir/fig03_3d_kelvin.png"

python "$scripts_dir/generate_kelvin_temporal_plot.py" \
  --case-dir "$case_dir" \
  --target-in 1e-5 \
  --background-in 1e-3 \
  --target-field "Mn+2" \
  --background-field "Mg+2" \
  --surf-target-fields "Surf_sOMn+,Surf_wOMn+" \
  --surf-background-fields "Surf_wOMg+" \
  --target-label 'Mn$^{2+}$' \
  --background-label 'Mg$^{2+}$' \
  --surf-target-label "HFO-Mn" \
  --surf-background-label "HFO-Mg" \
  --time-stride 12 \
  --output "$png_dir/fig07_kelvin_temporal.png"

echo "Wrote $png_dir/fig03_3d_kelvin.png"
echo "Wrote $png_dir/fig07_kelvin_temporal.png"
