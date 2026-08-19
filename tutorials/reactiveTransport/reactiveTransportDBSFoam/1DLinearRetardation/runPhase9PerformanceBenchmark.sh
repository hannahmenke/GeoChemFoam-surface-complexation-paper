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

mkdir -p benchmarks/phase9
summary_file="benchmarks/phase9/summary.txt"
: > "$summary_file"

rank_list=(2 4 8)

for mode in surface aqueous; do
    if [ "$mode" = surface ]; then
        python phase8AnalyticalTools.py prepare --mode transport --surface on --ca 2e-9
    else
        python phase8AnalyticalTools.py prepare --mode transport --surface off --ca 2e-9
    fi

    for np in "${rank_list[@]}"; do
        clean_runtime
        python phase9BenchmarkTools.py write-decompose --np "$np"

        blockMesh > "benchmarks/phase9/blockMesh_${mode}_${np}.out" 2>&1
        decomposePar -force > "benchmarks/phase9/decomposePar_${mode}_${np}.out" 2>&1

        log_path="benchmarks/phase9/reactiveTransportDBSFoam_${mode}_${np}.out"
        mpirun -np "$np" reactiveTransportDBSFoam -parallel > "$log_path"

        {
            echo "[${mode}:${np}]"
            python phase9BenchmarkTools.py summarize-log --log "$log_path" --ranks "$np" --mode "$mode"
            echo
        } >> "$summary_file"
    done
done

python phase8AnalyticalTools.py prepare --mode transport --surface on --ca 2e-9
python phase9BenchmarkTools.py write-decompose --np 2
clean_runtime

cat "$summary_file"
