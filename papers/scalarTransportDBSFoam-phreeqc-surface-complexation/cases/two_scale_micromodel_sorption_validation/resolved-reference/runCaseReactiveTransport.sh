#!/usr/bin/env bash

set -euo pipefail

# Explicit-aSurf, fixed-eps cases do not use the solver's auxiliary normalized gradient.
export FOAM_SIGFPE="${FOAM_SIGFPE:-false}"

repo_root="$(cd "$(dirname "$0")"/../../../../.. && pwd)"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
    set +e
    set +u
    # shellcheck disable=SC1091
    source /usr/local/anaconda3/etc/profile.d/conda.sh
    conda activate gcfoam
    set -e
    set -u
fi

if [ -z "${GCFOAM_DIR:-}" ] && [ -f "$repo_root/etc/bashrc" ]; then
    set +e
    set +u
    # shellcheck disable=SC1090
    source "$repo_root/etc/bashrc"
    set -e
    set -u
fi

TotalTime="${RT_TOTAL_TIME:-200}"
WriteTimestep="${RT_WRITE_TIMESTEP:-$TotalTime}"
runTimestep="${RT_TIMESTEP:-0.01}"

cp system/controlDict1 system/controlDict
sed -i "s/TotalTime/$TotalTime/g" system/controlDict
sed -i "s/WriteTimestep/$WriteTimestep/g" system/controlDict
sed -i "s/runTimestep/$runTimestep/g" system/controlDict

if [ "${RT_BOUND_AQUEOUS_TRANSPORT:-0}" = "1" ]; then
    {
        echo ""
        echo "boundAqueousTransport true;"
        echo "aqueousTransportLowerBound ${RT_AQUEOUS_LOWER_BOUND:-0};"
        echo "aqueousTransportUpperBound ${RT_AQUEOUS_UPPER_BOUND:-1e30};"
    } >> system/controlDict
fi

cp system/fvSolution1 system/fvSolution

if [ "${RT_RESTART:-0}" = "1" ]; then
    latest_time=""
    requested_time="${RT_RESTART_TIME:-}"
    if [ -d processor0 ]; then
        expected="$(find processor* -maxdepth 0 -type d | wc -l)"
        if [ -n "$requested_time" ]; then
            dumps="$(find processor* -path "*/$requested_time/phreeqcDBS.dmp" -type f | wc -l)"
            markers="$(find processor* -path "*/$requested_time/phreeqcDBS.complete" -type f | wc -l)"
            if [ "$dumps" -eq "$expected" ] && [ "$markers" -eq "$expected" ]; then
                latest_time="$requested_time"
            fi
        else
            while read -r candidate; do
                [ -n "$candidate" ] || continue
                dumps="$(find processor* -path "*/$candidate/phreeqcDBS.dmp" -type f | wc -l)"
                markers="$(find processor* -path "*/$candidate/phreeqcDBS.complete" -type f | wc -l)"
                if [ "$dumps" -eq "$expected" ] && [ "$markers" -eq "$expected" ]; then
                    latest_time="$candidate"
                    break
                fi
            done < <(find processor0 -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -gr)
        fi
    elif [ -n "$requested_time" ]; then
        if [ -f "$requested_time/phreeqcDBS.dmp" ] \
            && [ -f "$requested_time/phreeqcDBS.complete" ]; then
            latest_time="$requested_time"
        fi
    else
        while read -r candidate; do
            if [ -f "$candidate/phreeqcDBS.dmp" ] \
                && [ -f "$candidate/phreeqcDBS.complete" ]; then
                latest_time="$candidate"
                break
            fi
        done < <(foamListTimes | sort -gr)
    fi
    if [ -z "$latest_time" ]; then
        if [ -n "$requested_time" ]; then
            echo "Restart requested from time $requested_time, but its PHREEQC checkpoint is incomplete." >&2
        else
            echo "Restart requested but no PHREEQC checkpoint with a completion marker was found." >&2
        fi
        exit 5
    fi
    sed -i -E 's/^startFrom[[:space:]]+[^;]+;/startFrom       startTime;/' system/controlDict
    sed -i -E "s/^startTime[[:space:]]+[^;]+;/startTime       $latest_time;/" system/controlDict
    echo "Restarting reactive transport from time $latest_time"
else
    if [ -d processor0 ]; then
        expected_phi="$(find processor* -maxdepth 0 -type d | wc -l)"
        actual_phi="$(find processor* -maxdepth 2 -path '*/0/phi' -type f | wc -l)"
        if [ "$actual_phi" -ne "$expected_phi" ]; then
            echo "Fresh reactive transport requires flow-produced processor*/0/phi ($actual_phi/$expected_phi present)." >&2
            exit 6
        fi
    elif [ ! -f 0/phi ]; then
        echo "Fresh reactive transport requires the flow-produced 0/phi field." >&2
        exit 6
    fi
    echo "Preserving the pressure-corrected time-zero phi from the flow solve."
fi
echo "Reactive transport controls: endTime=${TotalTime}, writeInterval=${WriteTimestep}, deltaT=${runTimestep}"

solver_args=()
if [ "${RT_DRY_RUN_ONLY:-0}" = "1" ]; then
    solver_args=(-dry-run)
fi

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print | wc -l)"
    echo -e "Run reactiveTransportDBSFoam in parallel on $NP processors"
    if [[ "${PLATFORM:-}" == "ARCHER2" ]]; then
        srun --ntasks="$NP" reactiveTransportDBSFoam -parallel "${solver_args[@]}" > reactiveTransportDBSFoamRT.out
    else
        mpirun -np "$NP" reactiveTransportDBSFoam -parallel "${solver_args[@]}" > reactiveTransportDBSFoamRT.out
    fi
else
    reactiveTransportDBSFoam "${solver_args[@]}" > reactiveTransportDBSFoamRT.out
fi

if [ "${RT_DRY_RUN_ONLY:-0}" != "1" ] && [ "${RT_REQUIRE_FINAL_CHECKPOINT:-1}" = "1" ]; then
    if [ -d processor0 ]; then
        final_time="$(find processor0 -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -gr | head -1)"
        expected="$NP"
        fields="$(find processor* -path "*/$final_time/Li+" -type f | wc -l)"
        dumps="$(find processor* -path "*/$final_time/phreeqcDBS.dmp" -type f | wc -l)"
        markers="$(find processor* -path "*/$final_time/phreeqcDBS.complete" -type f | wc -l)"
    else
        final_time="$(foamListTimes | sort -gr | head -1)"
        expected=1
        fields="$([ -f "$final_time/Li+" ] && echo 1 || echo 0)"
        dumps="$([ -f "$final_time/phreeqcDBS.dmp" ] && echo 1 || echo 0)"
        markers="$([ -f "$final_time/phreeqcDBS.complete" ] && echo 1 || echo 0)"
    fi
    python3 - <<'PY' "$final_time" "$TotalTime" "$runTimestep"
import math
import sys

actual, requested, timestep = map(float, sys.argv[1:])
if not math.isclose(actual, requested, rel_tol=1e-12, abs_tol=1.01 * timestep):
    raise SystemExit(
        f"Final written time {actual:.17g} is not within one timestep "
        f"({timestep:.17g}) of requested endTime {requested:.17g}"
    )
PY
    if [ "$fields" -ne "$expected" ] || [ "$dumps" -ne "$expected" ] || [ "$markers" -ne "$expected" ]; then
        echo "Final checkpoint $final_time is incomplete: Li+=$fields dumps=$dumps markers=$markers expected=$expected" >&2
        exit 7
    fi
    echo "Verified complete final checkpoint at time $final_time on $expected partition(s)."
fi
