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

mkdir -p benchmarks/phase9_consistency
summary_file="benchmarks/phase9_consistency/summary.txt"
: > "$summary_file"

rank_list=(2 4 8)

python phase8AnalyticalTools.py prepare --mode transport --surface on --ca 2e-9

for np in "${rank_list[@]}"; do
    clean_runtime
    python phase9BenchmarkTools.py write-decompose --np "$np"

    blockMesh > "benchmarks/phase9_consistency/blockMesh_${np}.out" 2>&1
    decomposePar -force > "benchmarks/phase9_consistency/decomposePar_${np}.out" 2>&1

    log_path="benchmarks/phase9_consistency/reactiveScalarTransportDBSFoam_surface_${np}.out"
    mpirun -np "$np" reactiveScalarTransportDBSFoam -parallel > "$log_path"
    reconstructPar -latestTime > "benchmarks/phase9_consistency/reconstructPar_${np}.out" 2>&1

    mkdir -p "benchmarks/phase9_consistency/${np}"
    cp 10/Ca+2 "benchmarks/phase9_consistency/${np}/Ca+2"
    cp 10/Surf_aCa+ "benchmarks/phase9_consistency/${np}/Surf_aCa+"
done

for np in 4 8; do
    {
        echo "[Ca+2:${np}-vs-2]"
        python phase9BenchmarkTools.py compare-fields \
            --ref benchmarks/phase9_consistency/2/Ca+2 \
            --candidate "benchmarks/phase9_consistency/${np}/Ca+2" \
            --label "Ca+2_${np}_vs_2"
        echo
        echo "[Surf_aCa+:${np}-vs-2]"
        python phase9BenchmarkTools.py compare-fields \
            --ref benchmarks/phase9_consistency/2/Surf_aCa+ \
            --candidate "benchmarks/phase9_consistency/${np}/Surf_aCa+" \
            --label "Surf_aCa+_${np}_vs_2"
        echo
    } >> "$summary_file"
done

python phase8AnalyticalTools.py prepare --mode transport --surface on --ca 2e-9
python phase9BenchmarkTools.py write-decompose --np 2
clean_runtime

cat "$summary_file"
