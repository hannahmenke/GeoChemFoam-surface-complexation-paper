#!/usr/bin/env bash

set -Eeuo pipefail

usage() {
    cat >&2 <<'EOF'
Usage:
  ./submit_archer_restart.sh WORK_CASE_DIR FINAL_END_TIME

WORK_CASE_DIR is an existing ARCHER work case ending in dbs-upscaled or
resolved-reference. FINAL_END_TIME is the absolute simulation end time, not
the duration of this allocation.

Optional environment:
  RT_RESTART_TIME=<complete checkpoint time>
  RT_ALIGN_FINAL_WRITE=1
  GCFOAM_SLURM_ACCOUNT=n03-hw
  GCFOAM_SLURM_QOS=standard
  GCFOAM_SLURM_TIME=24:00:00
  DBS_NODES=2
  RESOLVED_NODES=<override inferred node count>
EOF
    exit 2
}

[ "$#" -eq 2 ] || usage

work_case_dir="$1"
final_end_time="$2"
[ -d "$work_case_dir" ] || {
    echo "Work case does not exist: $work_case_dir" >&2
    exit 2
}
work_case_dir="$(cd "$work_case_dir" && pwd -P)"

case "$work_case_dir" in
    /tmp|/tmp/*)
        echo "Restart work directory must be on shared Lustre, not $work_case_dir" >&2
        exit 2
        ;;
esac

case_name="$(basename "$work_case_dir")"
case "$case_name" in
    dbs-upscaled|resolved-reference) ;;
    *)
        echo "Work case must end in dbs-upscaled or resolved-reference: $work_case_dir" >&2
        exit 2
        ;;
esac

config_file="$(dirname "$work_case_dir")/results/current_run_config.env"
[ -f "$config_file" ] || {
    echo "Missing saved run configuration: $config_file" >&2
    exit 2
}

# The saved timestep and write interval must match the checkpointed run.
# shellcheck disable=SC1090
source "$config_file"
: "${RT_TIMESTEP:?Missing RT_TIMESTEP in $config_file}"
: "${RT_WRITE_TIMESTEP:?Missing RT_WRITE_TIMESTEP in $config_file}"
: "${ASURF_SURFACE_MODE:?Missing ASURF_SURFACE_MODE in $config_file}"
: "${SURFACE_RECONSTRUCTION_LABEL:?Missing SURFACE_RECONSTRUCTION_LABEL in $config_file}"
: "${PAPER_SOURCE_COMMIT:?Missing PAPER_SOURCE_COMMIT in $config_file}"

expected=1
if [ -d "$work_case_dir/processor0" ]; then
    expected="$(find "$work_case_dir"/processor* -maxdepth 0 -type d | wc -l)"
fi
inferred_nodes=$(( (expected + 127) / 128 ))
if [ "$case_name" = "dbs-upscaled" ]; then
    nodes="${DBS_NODES:-$inferred_nodes}"
else
    nodes="${RESOLVED_NODES:-$inferred_nodes}"
fi
if [ "$nodes" -lt "$inferred_nodes" ]; then
    echo "Requested $nodes nodes cannot host $expected ranks at 128 ranks/node." >&2
    exit 2
fi

restart_time="${RT_RESTART_TIME:-}"
if [ -z "$restart_time" ]; then
    if [ "$expected" -gt 1 ]; then
        while read -r candidate; do
            [ -n "$candidate" ] || continue
            dumps="$(find "$work_case_dir"/processor* -path "*/$candidate/phreeqc.dmp" -type f | wc -l)"
            markers="$(find "$work_case_dir"/processor* -path "*/$candidate/phreeqc.complete" -type f | wc -l)"
            if [ "$dumps" -eq "$expected" ] && [ "$markers" -eq "$expected" ]; then
                restart_time="$candidate"
                break
            fi
        done < <(find "$work_case_dir/processor0" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -gr)
    else
        while read -r candidate; do
            if [ -f "$work_case_dir/$candidate/phreeqc.dmp" ] \
                && [ -f "$work_case_dir/$candidate/phreeqc.complete" ]; then
                restart_time="$candidate"
                break
            fi
        done < <(find "$work_case_dir" -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort -gr)
    fi
fi
[ -n "$restart_time" ] || {
    echo "No complete PHREEQC checkpoint is available in $work_case_dir" >&2
    exit 5
}
if [ "$expected" -gt 1 ]; then
    dumps="$(find "$work_case_dir"/processor* -path "*/$restart_time/phreeqc.dmp" -type f | wc -l)"
    markers="$(find "$work_case_dir"/processor* -path "*/$restart_time/phreeqc.complete" -type f | wc -l)"
else
    dumps="$([ -f "$work_case_dir/$restart_time/phreeqc.dmp" ] && echo 1 || echo 0)"
    markers="$([ -f "$work_case_dir/$restart_time/phreeqc.complete" ] && echo 1 || echo 0)"
fi
if [ "$dumps" -ne "$expected" ] || [ "$markers" -ne "$expected" ]; then
    echo "Requested restart checkpoint $restart_time is incomplete: dumps=$dumps markers=$markers expected=$expected" >&2
    exit 5
fi

restart_write_timestep="$RT_WRITE_TIMESTEP"
if [ "${RT_ALIGN_FINAL_WRITE:-1}" = "1" ]; then
    restart_write_timestep="$(python3 - <<'PY' "$restart_time" "$final_end_time" "$RT_WRITE_TIMESTEP"
import math
import sys

start, end, preferred = map(float, sys.argv[1:])
remaining = end - start
if remaining <= 0:
    raise SystemExit(f"Final end time {end:.17g} must be later than restart time {start:.17g}")
if preferred <= 0:
    raise SystemExit(f"Saved write interval must be positive, got {preferred:.17g}")
count = max(1, math.ceil(remaining / preferred - 1e-12))
print(f"{remaining / count:.17g}")
PY
)"
fi

account="${GCFOAM_SLURM_ACCOUNT:-n03-hw}"
qos="${GCFOAM_SLURM_QOS:-standard}"
wall_time="${GCFOAM_SLURM_TIME:-24:00:00}"
repo_root="$(cd "$(dirname "$0")/../../../.." && pwd -P)"
runtime_verifier="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/two_scale_micromodel_sorption_validation/scripts/verify_production_runtime.py"
runtime_preflight="$(dirname "$work_case_dir")/results/runtime_preflight_restart_${restart_time}.json"
env_file="${GCFOAM_ENV_FILE:-$repo_root/.archer2-tools/gcfoam-env.sh}"
if [ -f "$env_file" ]; then
    environment_export=",GCFOAM_ENV_FILE=$env_file"
    run_prefix="source '$env_file' && python3 '$runtime_verifier' --output '$runtime_preflight' && "
elif command -v reactiveTransportDBSFoam >/dev/null 2>&1 && \
     [ -n "${WM_PROJECT_DIR:-}" ]; then
    environment_export=""
    python3 "$runtime_verifier" --output "$runtime_preflight"
    run_prefix="python3 '$runtime_verifier' --output '$runtime_preflight' && "
    echo "Using the inherited GeoChemFoam/OpenFOAM environment."
else
    echo "Missing environment helper: $env_file" >&2
    echo "Load GeoChemFoam/OpenFOAM or set GCFOAM_ENV_FILE to a site helper." >&2
    exit 2
fi

export_values="ALL${environment_export},PLATFORM=ARCHER2,RT_RESTART=1,RT_RESTART_TIME=$restart_time,RT_TOTAL_TIME=$final_end_time,RT_WRITE_TIMESTEP=$restart_write_timestep,RT_TIMESTEP=$RT_TIMESTEP,RT_REQUIRE_FINAL_CHECKPOINT=1,ASURF_SURFACE_MODE=$ASURF_SURFACE_MODE,SURFACE_RECONSTRUCTION_LABEL=$SURFACE_RECONSTRUCTION_LABEL,PAPER_SOURCE_COMMIT=$PAPER_SOURCE_COMMIT"

echo "Submitting restart: case=$case_name ranks=$expected nodes=$nodes final_end_time=$final_end_time"
echo "work_case_dir=$work_case_dir"
echo "RT_TIMESTEP=$RT_TIMESTEP saved_write_interval=$RT_WRITE_TIMESTEP aligned_write_interval=$restart_write_timestep"

sbatch_args=(
    --job-name="ts_${case_name//-/_}_restart" \
    --account="$account" \
    --partition=standard \
    --qos="$qos" \
    --time="$wall_time" \
    --nodes="$nodes" \
    --ntasks="$expected" \
    --cpus-per-task=1 \
    --exclusive \
    --chdir="$work_case_dir" \
    --output="$work_case_dir/slurm-restart-%j.out" \
    --export="$export_values" \
    --wrap="${run_prefix}./runCaseReactiveTransport.sh"
)

if [ "${SUBMIT_DRY_RUN:-0}" = "1" ]; then
    printf 'sbatch'
    printf ' %q' "${sbatch_args[@]}"
    printf '\n'
    exit 0
fi

sbatch "${sbatch_args[@]}"
