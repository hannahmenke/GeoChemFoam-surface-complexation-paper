#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"

case_dir="$repo_root/tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DEstailladesMicroporeAsSolidSurfaceComplexation"
output_png="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig04_3d_estaillades_micropore_as_solid_streamlines_t100.png"

if [[ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]]; then
  # shellcheck disable=SC1091
  source /usr/local/anaconda3/etc/profile.d/conda.sh
  conda activate gcfoam
fi

export DISPLAY=
export VTK_DEFAULT_OPENGL_WINDOW="${VTK_DEFAULT_OPENGL_WINDOW:-vtkEGLRenderWindow}"

python "$script_dir/generate_estaillades_streamlines.py" \
  --case-dir "$case_dir" \
  --time-name 100 \
  --output "$output_png"

stat -c '%y %s %n' "$output_png"
