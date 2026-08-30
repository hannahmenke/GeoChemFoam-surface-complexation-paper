#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"

python3 "$script_dir/figures/scripts/test_verify_accepted_figure_provenance.py"
python3 "$script_dir/figures/scripts/verify_accepted_figure_provenance.py"
