#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../.." && pwd)"

if [[ $# -lt 1 ]]; then
    echo "Usage: $0 <generate_3d_volume_render_pyvista.py args...>" >&2
    exit 2
fi

if [[ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]]; then
    # shellcheck disable=SC1091
    source /usr/local/anaconda3/etc/profile.d/conda.sh
    conda activate gcfoam
fi

export DISPLAY=
export VTK_DEFAULT_OPENGL_WINDOW="${VTK_DEFAULT_OPENGL_WINDOW:-vtkEGLRenderWindow}"

python "$repo_root/figures/scripts/generate_3d_volume_render_pyvista.py" "$@"
