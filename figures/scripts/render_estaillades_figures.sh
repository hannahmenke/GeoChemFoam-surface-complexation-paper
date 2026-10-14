#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../.. && pwd)"
case_dir="$repo_root/cases/3d_estaillades"
png_dir="$repo_root/figures/png"
scripts_dir="$repo_root/figures/scripts"

nx="$(<"$case_dir/system/Nx1")"
ny="$(<"$case_dir/system/Ny1")"
nz="$(<"$case_dir/system/Nz1")"
npx="$(<"$case_dir/system/NPX")"
npy="$(<"$case_dir/system/NPY")"
npz="$(<"$case_dir/system/NPZ")"
expected_ranks=$((npx * npy * npz))
actual_ranks="$(find "$case_dir" -maxdepth 1 -type d -name 'processor*' | wc -l)"

if [[ "$nx $ny $nz" != "500 500 500" ]]; then
  echo "Refusing Estaillades render from non-production grid: $nx x $ny x $nz" >&2
  exit 1
fi
if [[ "$expected_ranks" -ne 64 || "$actual_ranks" -ne 64 ]]; then
  echo "Refusing Estaillades render: expected 64 complete processor directories, found $actual_ranks" >&2
  exit 1
fi

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
  set +e
  set +u
  # shellcheck disable=SC1091
  source /usr/local/anaconda3/etc/profile.d/conda.sh
  conda activate gcfoam
  set -e
  set -u
fi

missing=0
for ((rank = 0; rank < expected_ranks; rank++)); do
  for spec in \
    '0:Surf_aSr+' '0:Surf_aCa+' \
    '40:Sr+2' '40:Ca+2' '40:Surf_aSr+' '40:eps' '40:aSurf' \
    '100:Sr+2' '100:Ca+2' '100:Surf_aSr+' '100:Surf_aCa+' '100:eps' '100:aSurf' \
    '120:Sr+2' '120:Ca+2' '120:Surf_aSr+' '120:Surf_aCa+' '120:eps' '120:aSurf'; do
    time_name="${spec%%:*}"
    field_name="${spec#*:}"
    field="$case_dir/processor$rank/$time_name/$field_name"
    if [[ ! -s "$field" ]]; then
      echo "Missing required Estaillades output field: $field" >&2
      missing=1
    fi
  done
done

if [ "$missing" -ne 0 ]; then
  echo "Run $case_dir/runAll.sh to completion before regenerating Estaillades figures." >&2
  exit 1
fi

python "$scripts_dir/validate_estaillades_checkpoint.py" \
  --case-dir "$case_dir" \
  --times 20 40 60 80 100 120 \
  --expected-ranks 64 \
  --max-workers 8 \
  --output "$png_dir/fig08_estaillades_concentration_bounds.json"

"$scripts_dir/render_3d_volume_pyvista_egl.sh" \
  --case-dir "$case_dir" \
  --time-name 40 \
  --geometry-render-mode exterior_faces \
  --aqueous-field Sr+2 \
  --aqueous-scale 1e-4 \
  --aqueous-mask-to-mobile \
  --aqueous-cmap cividis \
  --aqueous-title "Sr+2 / C_in" \
  --aqueous-no-shade \
  --aqueous-opacity-profile soft \
  --second-aqueous-field Ca+2 \
  --second-aqueous-scale 1e-3 \
  --second-aqueous-title "Ca+2 / C_init" \
  --second-aqueous-cmap soft_blues \
  --second-aqueous-no-shade \
  --surface-field Surf_aSr+ \
  --surface-baseline-time 0 \
  --surface-render-mode volume \
  --surface-normalize-to-max \
  --surface-title "Norm. ΔSurf_aSr+" \
  --axis-font-size 36 \
  --axis-label-format '%.0f' \
  --scalar-bar-title-font-size 36 \
  --scalar-bar-label-font-size 34 \
  --output "$png_dir/fig04_3d_estaillades.png"

python "$scripts_dir/generate_estaillades_temporal_plot.py" \
  --case-dir "$case_dir" \
  --sr-in 1e-4 \
  --ca-init 1e-3 \
  --max-workers 8 \
  --metrics-output "$png_dir/fig08_estaillades_temporal.json" \
  --output "$png_dir/fig08_estaillades_temporal.png"

echo "Wrote $png_dir/fig04_3d_estaillades.png"
echo "Wrote $png_dir/fig08_estaillades_temporal.png"
echo "Wrote $png_dir/fig08_estaillades_temporal.json"
echo "Wrote $png_dir/fig08_estaillades_concentration_bounds.json"
