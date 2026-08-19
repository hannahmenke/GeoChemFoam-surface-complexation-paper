#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
  set +e
  set +u
  # shellcheck disable=SC1091
  source /usr/local/anaconda3/etc/profile.d/conda.sh
  conda activate gcfoam
  set -e
  set -u
fi

python "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_hm12_2d_comparison.py" \
  --solid-case "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/hm12_2d_legacy/solid-grains" \
  --micropore-case "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/hm12_2d_legacy/microporous-grains" \
  --raw-tar "$repo_root/images/raw/HM12_2_4.raw.tar.gz" \
  --output-dir "$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/hm12_2d_comparison_pe10" \
  --times 10 20 40 100
