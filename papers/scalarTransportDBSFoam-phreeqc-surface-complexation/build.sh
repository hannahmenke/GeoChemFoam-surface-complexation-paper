#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$script_dir/validate_accepted_nonkelvin_artifacts.sh"
cd "$script_dir"

pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null
bibtex main
pdflatex -interaction=nonstopmode -halt-on-error main.tex >/dev/null
for _ in 1 2; do
    pdflatex -interaction=nonstopmode -halt-on-error main.tex
done
