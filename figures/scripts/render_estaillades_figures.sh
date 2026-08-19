#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"
case_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_estaillades"
png_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png"
scripts_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts"
connectivity_image="$repo_root/images/raw/Est_3phase500cubed4micron.raw.tar.gz"

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
  "$case_dir/processor0/40/Sr+2"
  "$case_dir/processor0/40/Ca+2"
  "$case_dir/processor0/40/Surf_aSr+"
  "$case_dir/processor0/100/Sr+2"
  "$case_dir/processor0/100/Ca+2"
  "$case_dir/processor0/100/Surf_aSr+"
  "$case_dir/processor0/100/Surf_aCa+"
)

missing=0
for field in "${required_fields[@]}"; do
  if [ ! -f "$field" ]; then
    echo "Missing required Estaillades output field: $field" >&2
    missing=1
  fi
done

if [ "$missing" -ne 0 ]; then
  echo "Run $case_dir/runAll.sh to completion before regenerating Estaillades figures." >&2
  exit 1
fi

"$scripts_dir/render_3d_volume_pyvista_egl.sh" \
  --case-dir "$case_dir" \
  --time-name 40 \
  --aqueous-field Sr+2 \
  --aqueous-scale 1e-4 \
  --aqueous-mask-to-pore \
  --aqueous-cmap yellow_fade \
  --aqueous-title "Sr+2 / C_in" \
  --aqueous-no-shade \
  --aqueous-opacity-profile soft \
  --second-aqueous-field Ca+2 \
  --second-aqueous-scale 1e-3 \
  --second-aqueous-title "Ca+2 / C_init" \
  --second-aqueous-cmap soft_blues \
  --surface-field Surf_aSr+ \
  --surface-baseline-time 0 \
  --surface-mask-field aSurf \
  --connectivity-image "$connectivity_image" \
  --connectivity-pore-value 1 \
  --surface-render-mode interface_surface \
  --surface-interface-clip-fraction 0.60 \
  --surface-log-scale \
  --surface-title "Surf_aSr+" \
  --output "$png_dir/fig04_3d_estaillades.png"

python "$scripts_dir/generate_estaillades_temporal_plot.py" \
  --case-dir "$case_dir" \
  --sr-in 1e-4 \
  --ca-init 1e-3 \
  --max-workers 8 \
  --output "$png_dir/fig08_estaillades_temporal.png"

echo "Wrote $png_dir/fig04_3d_estaillades.png"
echo "Wrote $png_dir/fig08_estaillades_temporal.png"
