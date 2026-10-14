#!/usr/bin/env bash

set -euo pipefail

cd "${0%/*}" || exit 1

repo_root="${PAPER_REPO_ROOT:-$(cd ../../../.. && pwd)}"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
    set +e
    set +u
    # shellcheck disable=SC1091
    source /usr/local/anaconda3/etc/profile.d/conda.sh
    set -e
    set -u
    conda activate gcfoam
fi

# shellcheck disable=SC1090
source "$repo_root/cases/configure_runtime.sh"

runtime_commit="$(git -C "$GCFOAM_RUNTIME_ROOT" rev-parse HEAD)"
phreeqcrm_commit="$(git -C "$GCFOAM_RUNTIME_ROOT/ThirdParty/PhreeqcRM" rev-parse HEAD)"
solver_path="$(readlink -f "$(command -v reactiveTransportDBSFoam)")"
echo "Runtime: $GCFOAM_RUNTIME_ROOT ($runtime_commit)"
echo "Solver: $solver_path"
echo "CFL preflight: Co_Darcy = U*dt/dx; maximum tested value is 2.0."
echo "The coarse high-Co runs are intentional members of the timestep-refinement sequence."

output_root="benchmarks/convergence"
raw_root="$output_root/raw"
manifest="$output_root/run_manifest.csv"
mkdir -p "$raw_root"

backup_dir="$(mktemp -d)"
cp constant/thermoPhysicalProperties "$backup_dir/thermoPhysicalProperties"
cp system/blockMeshDict "$backup_dir/blockMeshDict"
cp system/controlDict "$backup_dir/controlDict"

restore_inputs() {
    cp "$backup_dir/thermoPhysicalProperties" constant/thermoPhysicalProperties
    cp "$backup_dir/blockMeshDict" system/blockMeshDict
    cp "$backup_dir/controlDict" system/controlDict
    rm -r "$backup_dir"
}
trap restore_inputs EXIT

clean_runtime() {
    rm -rf constant/polyMesh processor0 processor1 processor2 processor3 \
        processor4 processor5 processor6 processor7 postProcessing
    find . -maxdepth 1 -type d -regextype posix-extended \
        -regex './[0-9]+([.][0-9]+)?' ! -name 0 -exec rm -r {} +
}

printf 'study,label,nx,delta_t,mode,directory\n' > "$manifest"

run_case() {
    local study="$1"
    local label="$2"
    local nx="$3"
    local delta_t="$4"
    local mode="$5"
    local destination="$raw_root/${study}_${label}/${mode}"
    local log_prefix="$output_root/${study}_${label}_${mode}"

    echo "=== $study $label: nx=$nx, deltaT=$delta_t, mode=$mode ==="
    python convergenceStudy.py configure \
        --nx "$nx" --delta-t "$delta_t" \
        --surface "$([ "$mode" = surface ] && echo on || echo off)"
    clean_runtime
    blockMesh > "${log_prefix}_blockMesh.out" 2>&1
    decomposePar -force > "${log_prefix}_decomposePar.out" 2>&1
    mpirun -np 2 reactiveTransportDBSFoam -parallel > "${log_prefix}_solver.out" 2>&1
    reconstructPar -latestTime > "${log_prefix}_reconstructPar.out" 2>&1

    if rg -n "FOAM FATAL|PHREEQC error" "${log_prefix}_solver.out"; then
        echo "Fatal solver output detected for $study $label $mode" >&2
        return 1
    fi

    rm -rf "$destination"
    mkdir -p "$destination"
    cp 10/Ca+2 "$destination/Ca+2"
    if [ "$mode" = surface ]; then
        cp 10/Surf_aCa+ "$destination/Surf_aCa+"
    fi
    printf '%s,%s,%s,%s,%s,%s\n' \
        "$study" "$label" "$nx" "$delta_t" "$mode" "$destination" >> "$manifest"
}

for mode in surface aqueous; do
    run_case reported nx80_dt025 80 0.25 "$mode"

    run_case mesh nx40 40 0.015625 "$mode"
    run_case mesh nx80 80 0.015625 "$mode"
    run_case mesh nx160 160 0.015625 "$mode"
    run_case mesh nx320 320 0.015625 "$mode"

    run_case timestep dt025 320 0.25 "$mode"
    run_case timestep dt0125 320 0.125 "$mode"
    run_case timestep dt00625 320 0.0625 "$mode"
    run_case timestep dt003125 320 0.03125 "$mode"
    run_case timestep dt0015625 320 0.015625 "$mode"
done

python convergenceStudy.py analyze \
    --manifest "$manifest" \
    --k-s 4.2526322996537766e-06 \
    --output convergence_results.json

python - <<PY
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

payload = {
    "schema_version": 1,
    "completed_utc": datetime.now(timezone.utc).isoformat(),
    "runtime_root": "$GCFOAM_RUNTIME_ROOT",
    "runtime_commit": "$runtime_commit",
    "phreeqcrm_commit": "$phreeqcrm_commit",
    "solver_executable": "$solver_path",
    "solver_sha256": hashlib.sha256(Path("$solver_path").read_bytes()).hexdigest(),
    "results_sha256": hashlib.sha256(Path("convergence_results.json").read_bytes()).hexdigest(),
    "study_script_sha256": hashlib.sha256(Path("runConvergenceStudy.sh").read_bytes()).hexdigest(),
    "analysis_script_sha256": hashlib.sha256(Path("convergenceStudy.py").read_bytes()).hexdigest(),
}
Path("convergence_provenance.json").write_text(json.dumps(payload, indent=2) + "\n")
PY

clean_runtime
echo "Convergence study completed."
column -s, -t convergence_results.csv || cat convergence_results.csv
