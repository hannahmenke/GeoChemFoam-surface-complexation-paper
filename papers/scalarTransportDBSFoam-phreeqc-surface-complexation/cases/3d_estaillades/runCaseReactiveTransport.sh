#!/usr/bin/env bash

set -euo pipefail
cd "$(dirname "$0")"

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

if [ -n "${GCFOAM_RUNTIME_ROOT:-}" ] && [ -f "$GCFOAM_RUNTIME_ROOT/etc/bashrc" ]; then
    set +e
    set +u
    # shellcheck disable=SC1090
    source "$GCFOAM_RUNTIME_ROOT/etc/bashrc"
    set -e
    export GCFOAM_DIR="$GCFOAM_RUNTIME_ROOT"
    export GCFOAM_SRC="$GCFOAM_DIR/src"
    export GCFOAM_APPBIN="$GCFOAM_DIR/bin"
    export GCFOAM_LIBBIN="$GCFOAM_DIR/lib"
    export GCFOAM_TUTORIALS="$GCFOAM_DIR/tutorials"
    export GCFOAM_IMG="$repo_root/images"
    export PATH="$GCFOAM_APPBIN:$PATH"
    export LD_LIBRARY_PATH="$GCFOAM_LIBBIN:${LD_LIBRARY_PATH:-}"
    # shellcheck disable=SC1090
    source "$GCFOAM_DIR/ThirdParty/bashrc"
    export LD_LIBRARY_PATH="$GCFOAM_DIR/ThirdParty/PhreeqcRM/lib:$GCFOAM_LIBBIN:${LD_LIBRARY_PATH:-}"
    set -u
elif [ -f "$repo_root/etc/bashrc" ]; then
    set +e
    set +u
    # shellcheck disable=SC1090
    source "$repo_root/etc/bashrc"
    set -e
    set -u
fi

TotalTime="${TOTAL_TIME:-120}"
WriteTimestep="${WRITE_TIMESTEP:-20}"
runTimestep="${RUN_TIMESTEP:-2}"

solver_path="$(readlink -f "$(command -v reactiveTransportDBSFoam)")"
if [[ -n "${GCFOAM_RUNTIME_ROOT:-}" && "$solver_path" != "$GCFOAM_RUNTIME_ROOT"/* ]]; then
    echo "Refusing reactive launch: solver resolves outside GCFOAM_RUNTIME_ROOT: $solver_path" >&2
    exit 1
fi

reaction_library="$GCFOAM_LIBBIN/libreactionThermophysicalModelsGCFOAM.so"
phreeqc_library="$(ldd "$reaction_library" | awk '/libPhreeqcRM\.so/ && !found {print $3; found=1}')"
if [[ -z "$phreeqc_library" || "$phreeqc_library" != "$GCFOAM_DIR"/ThirdParty/PhreeqcRM/lib/* ]]; then
    echo "Refusing reactive launch: incompatible PhreeqcRM library: ${phreeqc_library:-unresolved}" >&2
    exit 1
fi
if ! nm -D "$phreeqc_library" | grep ' RM_GetSurfaceSpeciesConcentrations$' >/dev/null; then
    echo "Refusing reactive launch: PhreeqcRM lacks surface-species restart support" >&2
    exit 1
fi
if ! grep -Eq '^[[:space:]]*-status[[:space:]]+false([[:space:]]|$)' constant/phreeqcReactions; then
    echo "Refusing reactive launch: PHREEQC status output must be disabled for the full-resolution surface initialization" >&2
    exit 1
fi
if ! grep -Eq '^[[:space:]]*transportModel[[:space:]]+Newtonian[[:space:]]*;' constant/transportProperties \
    || ! grep -Eq '^[[:space:]]*nu[[:space:]]+nu[[:space:]]+\[0[[:space:]]+2[[:space:]]+-1' constant/transportProperties; then
    echo "Refusing reactive launch: transportProperties must define Newtonian transport and kinematic viscosity" >&2
    exit 1
fi
if ! awk -v dt="$runTimestep" -v write="$WriteTimestep" -v end="$TotalTime" '
    function abs(x) { return x < 0 ? -x : x }
    BEGIN {
        if (dt <= 0 || write <= 0 || end <= 0) exit 1
        writeSteps = write/dt
        endSteps = end/dt
        if (abs(writeSteps - int(writeSteps + 0.5)) > 1e-9) exit 1
        if (abs(endSteps - int(endSteps + 0.5)) > 1e-9) exit 1
    }
'; then
    echo "Refusing reactive launch: timestep must divide both write interval and end time exactly" >&2
    exit 1
fi

yi_tolerance="$(awk '
    $1 == "Yi" { in_yi=1; next }
    in_yi && $1 == "tolerance" { gsub(/;/, "", $2); print $2; exit }
' system/fvSolution1)"
yi_rel_tol="$(awk '
    $1 == "Yi" { in_yi=1; next }
    in_yi && $1 == "relTol" { gsub(/;/, "", $2); print $2; exit }
' system/fvSolution1)"
if ! awk -v tol="$yi_tolerance" -v rel="$yi_rel_tol" '
    BEGIN { exit !(tol == 5e-7 && rel == 1e-3) }
'; then
    echo "Refusing reactive launch: Yi must use tolerance 5e-7 and relTol 0.001 (found ${yi_tolerance:-missing}, ${yi_rel_tol:-missing})" >&2
    exit 1
fi

echo "Reactive preflight: solver=$solver_path"
echo "Reactive preflight: PhreeqcRM=$phreeqc_library"
echo "Reactive preflight: dt=$runTimestep, writeInterval=$WriteTimestep, endTime=$TotalTime"
echo "Reactive preflight: Yi tolerance=$yi_tolerance, relTol=$yi_rel_tol"
if [[ "${REACTIVE_PREFLIGHT_ONLY:-0}" == "1" ]]; then
    exit 0
fi

cp system/controlDict1 system/controlDict
sed -i "s/TotalTime/$TotalTime/g" system/controlDict
sed -i "s/WriteTimestep/$WriteTimestep/g" system/controlDict
sed -i "s/runTimestep/$runTimestep/g" system/controlDict

cp system/fvSolution1 system/fvSolution

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print | wc -l)"
    echo -e "Run reactiveTransportDBSFoam in parallel on $NP processors"
    if [[ "${PLATFORM:-}" == "ARCHER2" ]]; then
        srun reactiveTransportDBSFoam -parallel > reactiveTransportDBSFoamRT.out
    else
        mpirun -np "$NP" reactiveTransportDBSFoam -parallel > reactiveTransportDBSFoamRT.out
    fi
else
    reactiveTransportDBSFoam > reactiveTransportDBSFoamRT.out
fi

# A successful solver exit is not sufficient for a production result: require
# the complete final OpenFOAM state on every partition.
if [ -d "processor0" ]; then
    final_time="$(find processor0 -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -gr | head -1)"
    expected="$NP"
    for field in Ca+2 Sr+2 Cl- Surf_aCa+ Surf_aSr+ eps aSurf; do
        present="$(find processor* -path "*/$final_time/$field" -type f | wc -l)"
        if [ "$present" -ne "$expected" ]; then
            echo "Incomplete final fields at $final_time: $field=$present/$expected" >&2
            exit 7
        fi
    done
else
    final_time="$(foamListTimes | sort -gr | head -1)"
    expected=1
    for field in Ca+2 Sr+2 Cl- Surf_aCa+ Surf_aSr+ eps aSurf; do
        if [ ! -f "$final_time/$field" ]; then
            echo "Incomplete final fields at $final_time: missing $field" >&2
            exit 7
        fi
    done
fi

python3 - "$final_time" "$TotalTime" <<'PY'
import math
import sys

actual, expected = map(float, sys.argv[1:])
if not math.isclose(actual, expected, rel_tol=1e-12, abs_tol=1e-9):
    raise SystemExit(
        f"Final written time {actual:.17g} does not match endTime {expected:.17g}"
    )
PY
echo "Verified complete final reactive fields at time $final_time on $expected partition(s)."
