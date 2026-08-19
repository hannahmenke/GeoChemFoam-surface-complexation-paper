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
        -o -path './20' \
        \) -prune -exec rm -r {} + 2>/dev/null || true
}

mkdir -p benchmarks/phase9_long
summary_file="benchmarks/phase9_long/summary.txt"
: > "$summary_file"

python phase8AnalyticalTools.py prepare --mode transport --surface on --ca 2e-9
python phase9BenchmarkTools.py write-control --end-time 20 --delta-t 0.25 --write-interval 20
python phase9BenchmarkTools.py write-decompose --np 4
clean_runtime

blockMesh > "benchmarks/phase9_long/blockMesh_4.out" 2>&1
decomposePar -force > "benchmarks/phase9_long/decomposePar_4.out" 2>&1
mpirun -np 4 reactiveTransportDBSFoam -parallel > "benchmarks/phase9_long/reactiveTransportDBSFoam_surface_4.out"
reconstructPar -latestTime > "benchmarks/phase9_long/reconstructPar_4.out" 2>&1

time_dir="$(
    find . -maxdepth 1 -type d -regextype posix-egrep -regex './[0-9]+([.][0-9]+)?([eE][-+]?[0-9]+)?' \
    | sed 's#^./##' \
    | sort -g \
    | tail -n 1
)"

{
    echo "[surface:4:long]"
    python phase9BenchmarkTools.py summarize-log \
        --log benchmarks/phase9_long/reactiveTransportDBSFoam_surface_4.out \
        --ranks 4 \
        --mode surface
    echo
    python phase9BenchmarkTools.py report-surface-state \
        --ca "$time_dir/Ca+2" \
        --surf "$time_dir/Surf_aCa+" \
        --theta 0.5 \
        --asurf 1e5
    echo
} > "$summary_file"

python phase8AnalyticalTools.py prepare --mode transport --surface on --ca 2e-9
python phase9BenchmarkTools.py write-decompose --np 2
clean_runtime

cat "$summary_file"
