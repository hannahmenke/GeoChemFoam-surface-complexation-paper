#!/usr/bin/env bash

set -euo pipefail

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
    # Do not trust a stored time-zero flux from an earlier flow attempt.
    rm -f 0/phi processor*/0/phi
    echo "Removed stored phi fields; reactive transport will rebuild phi from U."
fi
echo "Reactive transport controls: endTime=${TotalTime}, writeInterval=${WriteTimestep}, deltaT=${runTimestep}"

solver_args=()
if [ "${RT_DRY_RUN_ONLY:-0}" = "1" ]; then
    solver_args=(-dry-run)
fi

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print | wc -l)"
    echo -e "Run reactiveScalarTransportDBSFoam in parallel on $NP processors"
    if [[ "${PLATFORM:-}" == "ARCHER2" ]]; then
        srun --ntasks="$NP" reactiveScalarTransportDBSFoam -parallel "${solver_args[@]}" > reactiveScalarTransportDBSFoamRT.out
    else
        mpirun -np "$NP" reactiveScalarTransportDBSFoam -parallel "${solver_args[@]}" > reactiveScalarTransportDBSFoamRT.out
    fi
else
    reactiveScalarTransportDBSFoam "${solver_args[@]}" > reactiveScalarTransportDBSFoamRT.out
fi
