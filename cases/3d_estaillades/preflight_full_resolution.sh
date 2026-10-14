#!/usr/bin/env bash

set -euo pipefail
cd "$(dirname "$0")"

runtime_root="${GCFOAM_RUNTIME_ROOT:-}"
if [[ -z "$runtime_root" || ! -f "$runtime_root/etc/bashrc" ]]; then
    echo "FAIL: set GCFOAM_RUNTIME_ROOT to the GeoChemFoam runtime checkout" >&2
    exit 1
fi

set +e
set +u
# shellcheck disable=SC1090
source "$runtime_root/etc/bashrc"
set -e
set -u

# Re-anchor paths because an existing runtime checkout may retain the original
# developer path in its local etc/bashrc.
repo_root="$(cd ../../../.. && pwd)"
export GCFOAM_DIR="$runtime_root"
export GCFOAM_SRC="$GCFOAM_DIR/src"
export GCFOAM_APPBIN="$GCFOAM_DIR/bin"
export GCFOAM_LIBBIN="$GCFOAM_DIR/lib"
export GCFOAM_TUTORIALS="$GCFOAM_DIR/tutorials"
export GCFOAM_IMG="$repo_root/images"
export PATH="$GCFOAM_APPBIN:$PATH"
export LD_LIBRARY_PATH="$GCFOAM_LIBBIN:${LD_LIBRARY_PATH:-}"
set +u
# shellcheck disable=SC1090
source "$GCFOAM_DIR/ThirdParty/bashrc"
export LD_LIBRARY_PATH="$GCFOAM_DIR/ThirdParty/PhreeqcRM/lib:$GCFOAM_LIBBIN:${LD_LIBRARY_PATH:-}"
set -u

solver="$(command -v reactiveTransportDBSFoam || true)"
if [[ -z "$solver" ]]; then
    echo "FAIL: reactiveTransportDBSFoam is not available from $runtime_root" >&2
    exit 1
fi
solver="$(readlink -f "$solver")"
reaction_library="$GCFOAM_LIBBIN/libreactionThermophysicalModelsGCFOAM.so"
phreeqc_library="$(ldd "$reaction_library" | awk '/libPhreeqcRM\.so/ && !found {print $3; found=1}')"

physical_cores="$(lscpu -p=CORE,SOCKET | awk -F, '!/^#/ {seen[$1 FS $2]=1} END {print length(seen)}')"
available_kib="$(awk '/MemAvailable:/ {print $2}' /proc/meminfo)"
available_gib="$((available_kib / 1024 / 1024))"
available_disk_gib="$(df -Pk . | awk 'NR==2 {print int($4/1024/1024)}')"
active_ranks="$(ps -eo args= | awk '/reactiveTransportDBSFoam -parallel/ && !/awk/ {n++} END {print n+0}')"

printf 'solver=%s\n' "$solver"
printf 'phreeqcrm=%s\n' "${phreeqc_library:-unresolved}"
printf 'grid_cells=%s\n' 125000000
printf 'chemistry_active_cells=%s\n' 94031005
printf 'decomposition=%s\n' '4x4x4 (64 ranks)'
printf 'physical_cores=%s\n' "$physical_cores"
printf 'available_memory_gib=%s\n' "$available_gib"
printf 'available_disk_gib=%s\n' "$available_disk_gib"
printf 'active_reactive_transport_ranks=%s\n' "$active_ranks"

failed=0
if [[ "$solver" != "$runtime_root"/* ]]; then
    echo "FAIL: solver resolves outside GCFOAM_RUNTIME_ROOT" >&2
    failed=1
fi
if [[ -z "$phreeqc_library" || "$phreeqc_library" != "$runtime_root"/ThirdParty/PhreeqcRM/lib/* ]]; then
    echo "FAIL: reaction library resolves an incompatible PhreeqcRM" >&2
    failed=1
elif ! nm -D "$phreeqc_library" | grep ' RM_GetSurfaceSpeciesConcentrations$' >/dev/null; then
    echo "FAIL: PhreeqcRM lacks surface-species restart support" >&2
    failed=1
fi
if ! grep -Eq '^[[:space:]]*-status[[:space:]]+false([[:space:]]|$)' constant/phreeqcReactions; then
    echo "FAIL: PHREEQC status output is enabled and can overflow during full-resolution surface initialization" >&2
    failed=1
fi
if (( physical_cores < 64 )); then
    echo "FAIL: fewer than 64 physical cores" >&2
    failed=1
fi
if (( available_gib < 800 )); then
    echo "FAIL: less than 800 GiB memory is currently available" >&2
    failed=1
fi
if (( available_disk_gib < 500 )); then
    echo "FAIL: less than 500 GiB disk space is currently available" >&2
    failed=1
fi
if (( active_ranks > 0 )); then
    echo "WAIT: another reactiveTransportDBSFoam run is active" >&2
    failed=1
fi

if (( failed != 0 )); then
    exit 1
fi

echo "PASS: workstation resources and runtime are ready for the full-resolution launch"
