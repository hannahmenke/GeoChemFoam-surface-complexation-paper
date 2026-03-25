#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(cd "$script_dir/../../../.." && pwd)"

if [[ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]]; then
    # shellcheck disable=SC1091
    source /usr/local/anaconda3/etc/profile.d/conda.sh
    conda activate gcfoam
fi

python "$script_dir/generate_estaillades_3d_timeseries.py" --repo-root "$repo_root"
