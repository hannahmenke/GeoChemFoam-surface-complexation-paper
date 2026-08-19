#!/usr/bin/env bash

set -euo pipefail

cd "${0%/*}" || exit 1

repo_root="$(cd ../../../.. && pwd)"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
    set +e
    set +u
    # shellcheck disable=SC1091
    source /usr/local/anaconda3/etc/profile.d/conda.sh
    set -e
    set -u
    conda activate gcfoam
fi

if [ -f "$repo_root/etc/bashrc" ]; then
    set +e
    set +u
    # shellcheck disable=SC1090
    source "$repo_root/etc/bashrc"
    set -e
    set -u
fi

clean_runtime() {
    find . \
        \( -path './constant/polyMesh' \
        -o -path './processor0' \
        -o -path './processor1' \
        -o -path './processor2' \
        -o -path './processor3' \
        -o -path './processor4' \
        -o -path './processor5' \
        -o -path './processor6' \
        -o -path './processor7' \
        -o -path './10' \
        \) -prune -exec rm -r {} + 2>/dev/null || true
}

mkdir -p benchmarks/phase9_dt
summary_file="benchmarks/phase9_dt/summary.txt"
: > "$summary_file"

run_case() {
    local label="$1"
    local dt="$2"

    python phase8AnalyticalTools.py prepare --mode transport --surface on --ca 2e-9
    python phase9BenchmarkTools.py write-control --end-time 10 --delta-t "$dt" --write-interval 10
    python phase9BenchmarkTools.py write-decompose --np 4
    clean_runtime

    blockMesh > "benchmarks/phase9_dt/blockMesh_${label}.out" 2>&1
    decomposePar -force > "benchmarks/phase9_dt/decomposePar_${label}.out" 2>&1
    mpirun -np 4 reactiveTransportDBSFoam -parallel > "benchmarks/phase9_dt/reactiveTransportDBSFoam_${label}.out"
    reconstructPar -latestTime > "benchmarks/phase9_dt/reconstructPar_${label}.out" 2>&1

    mkdir -p "benchmarks/phase9_dt/${label}"
    cp 10/Ca+2 "benchmarks/phase9_dt/${label}/Ca+2"
    cp 10/Surf_aCa+ "benchmarks/phase9_dt/${label}/Surf_aCa+"
}

run_case dt025 0.25
run_case dt0125 0.125

{
    echo "[dt025]"
    python phase9BenchmarkTools.py summarize-log \
        --log benchmarks/phase9_dt/reactiveTransportDBSFoam_dt025.out \
        --ranks 4 \
        --mode surface
    python phase9BenchmarkTools.py report-surface-state \
        --ca benchmarks/phase9_dt/dt025/Ca+2 \
        --surf benchmarks/phase9_dt/dt025/Surf_aCa+ \
        --theta 0.5 \
        --asurf 1e5
    echo
    echo "[dt0125]"
    python phase9BenchmarkTools.py summarize-log \
        --log benchmarks/phase9_dt/reactiveTransportDBSFoam_dt0125.out \
        --ranks 4 \
        --mode surface
    python phase9BenchmarkTools.py report-surface-state \
        --ca benchmarks/phase9_dt/dt0125/Ca+2 \
        --surf benchmarks/phase9_dt/dt0125/Surf_aCa+ \
        --theta 0.5 \
        --asurf 1e5
    echo
    echo "[Ca+2:dt0125-vs-dt025]"
    python phase9BenchmarkTools.py compare-fields \
        --ref benchmarks/phase9_dt/dt025/Ca+2 \
        --candidate benchmarks/phase9_dt/dt0125/Ca+2 \
        --label Ca+2_dt0125_vs_dt025
    echo
    echo "[Surf_aCa+:dt0125-vs-dt025]"
    python phase9BenchmarkTools.py compare-fields \
        --ref benchmarks/phase9_dt/dt025/Surf_aCa+ \
        --candidate benchmarks/phase9_dt/dt0125/Surf_aCa+ \
        --label Surf_aCa+_dt0125_vs_dt025
    echo
} > "$summary_file"

python phase8AnalyticalTools.py prepare --mode transport --surface on --ca 2e-9
python phase9BenchmarkTools.py write-control --end-time 10 --delta-t 0.25 --write-interval 10
python phase9BenchmarkTools.py write-decompose --np 2
clean_runtime

cat "$summary_file"
