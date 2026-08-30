#!/usr/bin/env bash

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
"$script_dir/validate_accepted_nonkelvin_artifacts.sh"
cd "$script_dir"

build_document() {
    local document="$1"

    pdflatex -interaction=nonstopmode -halt-on-error "$document.tex" >/dev/null
    bibtex "$document"
    pdflatex -interaction=nonstopmode -halt-on-error "$document.tex" >/dev/null
    for _ in 1 2; do
        pdflatex -interaction=nonstopmode -halt-on-error "$document.tex"
    done
}

build_document main
build_document supplementary
