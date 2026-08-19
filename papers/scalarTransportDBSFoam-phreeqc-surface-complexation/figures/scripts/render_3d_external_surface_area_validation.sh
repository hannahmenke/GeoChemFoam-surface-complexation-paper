#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"

if [[ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]]; then
    # Use the same environment as the PyVista-based 3D figure renderers when it
    # is available; the Python script has a Matplotlib fallback for other shells.
    # shellcheck disable=SC1091
    source /usr/local/anaconda3/etc/profile.d/conda.sh
    conda activate gcfoam || true
fi

python "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_3d_external_surface_area_validation.py"
