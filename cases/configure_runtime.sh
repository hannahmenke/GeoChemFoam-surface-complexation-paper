#!/usr/bin/env bash

# Source this file from a paper case to select an explicit, isolated
# GeoChemFoam runtime without changing the paper repository or upstream main.

if [ -z "${GCFOAM_RUNTIME_ROOT:-}" ]; then
    echo "Set GCFOAM_RUNTIME_ROOT to the isolated GeoChemFoam runtime checkout." >&2
    return 1 2>/dev/null || exit 1
fi

runtime_root="$(cd "$GCFOAM_RUNTIME_ROOT" && pwd)"
paper_repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [ "$runtime_root" = "$paper_repo_root" ]; then
    echo "The GeoChemFoam runtime must be separate from the paper repository." >&2
    return 1 2>/dev/null || exit 1
fi
if [ ! -f "$runtime_root/etc/bashrc" ]; then
    echo "Invalid GCFOAM_RUNTIME_ROOT: $runtime_root" >&2
    return 1 2>/dev/null || exit 1
fi

set +e
set +u
# shellcheck disable=SC1090
source "$runtime_root/etc/bashrc"
set -e
set -u

# Re-anchor paths because an installation-local etc/bashrc may contain a
# different absolute checkout path.
export GCFOAM_RUNTIME_ROOT="$runtime_root"
export GCFOAM_DIR="$runtime_root"
export GCFOAM_SRC="$GCFOAM_DIR/src"
export GCFOAM_APPBIN="$GCFOAM_DIR/bin"
export GCFOAM_LIBBIN="$GCFOAM_DIR/lib"
export GCFOAM_TUTORIALS="$GCFOAM_DIR/tutorials"
export GCFOAM_IMG="$paper_repo_root/images"
export PATH="$GCFOAM_APPBIN:$PATH"
export LD_LIBRARY_PATH="$GCFOAM_LIBBIN:${LD_LIBRARY_PATH:-}"

set +e
set +u
# shellcheck disable=SC1090
source "$GCFOAM_DIR/ThirdParty/bashrc"
export LD_LIBRARY_PATH="$GCFOAM_DIR/ThirdParty/PhreeqcRM/lib:$GCFOAM_LIBBIN:${LD_LIBRARY_PATH:-}"
set -e
set -u

solver_path="$(command -v reactiveTransportDBSFoam || true)"
if [ -z "$solver_path" ] || [ "$(readlink -f "$solver_path")" != "$(readlink -f "$GCFOAM_APPBIN/reactiveTransportDBSFoam")" ]; then
    echo "reactiveTransportDBSFoam is not the executable from $runtime_root." >&2
    return 1 2>/dev/null || exit 1
fi
