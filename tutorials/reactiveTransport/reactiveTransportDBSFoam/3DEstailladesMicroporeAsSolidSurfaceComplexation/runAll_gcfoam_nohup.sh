#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"
case_dir="$(cd "$(dirname "$0")" && pwd)"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
    set +e
    set +u
    # shellcheck disable=SC1091
    source /usr/local/anaconda3/etc/profile.d/conda.sh
    conda activate gcfoam
    set -e
    set -u
fi

if [ -f "$repo_root/etc/bashrc" ]; then
    set +e
    set +u
    # shellcheck disable=SC1090
    source "$repo_root/etc/bashrc"
    set -e
    set -u
fi

cd "$case_dir"
./deleteAll.sh
TOTAL_TIME="${TOTAL_TIME:-100}" WRITE_TIMESTEP="${WRITE_TIMESTEP:-25}" RUN_TIMESTEP="${RUN_TIMESTEP:-5}" ./runAll.sh
