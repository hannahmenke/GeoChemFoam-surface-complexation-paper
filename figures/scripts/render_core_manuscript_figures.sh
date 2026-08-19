#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"

"$script_dir/render_1d_validation_figures.sh"
"$script_dir/render_2d_fractures_figure.sh"
"$script_dir/render_kelvin_cuzn_figures.sh"
"$script_dir/render_estaillades_figures.sh"
"$script_dir/render_surface_area_validation_figures.sh"
python "$script_dir/generate_solver_workflow.py"
