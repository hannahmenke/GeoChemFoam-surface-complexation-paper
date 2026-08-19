#!/usr/bin/env bash

set -euo pipefail

cd "${0%/*}" || exit 1

pdflatex -interaction=nonstopmode -halt-on-error main.tex
pdflatex -interaction=nonstopmode -halt-on-error main.tex
