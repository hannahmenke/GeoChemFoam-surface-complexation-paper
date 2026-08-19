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

mkdir -p benchmarks/phase9_mesh
summary_file="benchmarks/phase9_mesh/summary.txt"
: > "$summary_file"

run_case() {
    local label="$1"
    local nx="$2"

    python phase8AnalyticalTools.py prepare --mode transport --surface on --ca 2e-9
    python phase9BenchmarkTools.py write-control --end-time 10 --delta-t 0.25 --write-interval 10
    python phase9BenchmarkTools.py write-decompose --np 4
    python phase9BenchmarkTools.py write-block-mesh --nx "$nx"
    clean_runtime

    blockMesh > "benchmarks/phase9_mesh/blockMesh_${label}.out" 2>&1
    decomposePar -force > "benchmarks/phase9_mesh/decomposePar_${label}.out" 2>&1
    mpirun -np 4 reactiveTransportDBSFoam -parallel > "benchmarks/phase9_mesh/reactiveTransportDBSFoam_${label}.out"
    reconstructPar -latestTime > "benchmarks/phase9_mesh/reconstructPar_${label}.out" 2>&1

    mkdir -p "benchmarks/phase9_mesh/${label}"
    cp 10/Ca+2 "benchmarks/phase9_mesh/${label}/Ca+2"
    cp 10/Surf_aCa+ "benchmarks/phase9_mesh/${label}/Surf_aCa+"
}

run_case nx40 40
run_case nx80 80

{
    echo "[nx40]"
    python phase9BenchmarkTools.py summarize-log \
        --log benchmarks/phase9_mesh/reactiveTransportDBSFoam_nx40.out \
        --ranks 4 \
        --mode surface
    python phase9BenchmarkTools.py report-profile-metrics \
        --ca benchmarks/phase9_mesh/nx40/Ca+2 \
        --surf benchmarks/phase9_mesh/nx40/Surf_aCa+ \
        --theta 0.5 \
        --asurf 1e5 \
        --c-in 2e-9 \
        --length 4e-5
    echo
    echo "[nx80]"
    python phase9BenchmarkTools.py summarize-log \
        --log benchmarks/phase9_mesh/reactiveTransportDBSFoam_nx80.out \
        --ranks 4 \
        --mode surface
    python phase9BenchmarkTools.py report-profile-metrics \
        --ca benchmarks/phase9_mesh/nx80/Ca+2 \
        --surf benchmarks/phase9_mesh/nx80/Surf_aCa+ \
        --theta 0.5 \
        --asurf 1e5 \
        --c-in 2e-9 \
        --length 4e-5
    echo
} > "$summary_file"

python phase8AnalyticalTools.py prepare --mode transport --surface on --ca 2e-9
python phase9BenchmarkTools.py write-control --end-time 10 --delta-t 0.25 --write-interval 10
python phase9BenchmarkTools.py write-decompose --np 2
python phase9BenchmarkTools.py write-block-mesh --nx 40
clean_runtime

cat "$summary_file"
