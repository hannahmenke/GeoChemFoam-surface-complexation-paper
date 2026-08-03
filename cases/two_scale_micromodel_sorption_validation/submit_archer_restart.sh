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
if [ -n "$restart_time" ]; then
    if [ "$expected" -gt 1 ]; then
        dumps="$(find "$work_case_dir"/processor* -path "*/$restart_time/phreeqcDBS.dmp" -type f | wc -l)"
        markers="$(find "$work_case_dir"/processor* -path "*/$restart_time/phreeqcDBS.complete" -type f | wc -l)"
    else
        dumps="$([ -f "$work_case_dir/$restart_time/phreeqcDBS.dmp" ] && echo 1 || echo 0)"
        markers="$([ -f "$work_case_dir/$restart_time/phreeqcDBS.complete" ] && echo 1 || echo 0)"
    fi
    if [ "$dumps" -ne "$expected" ] || [ "$markers" -ne "$expected" ]; then
        echo "Requested restart checkpoint $restart_time is incomplete: dumps=$dumps markers=$markers expected=$expected" >&2
        exit 5
    fi
fi

account="${GCFOAM_SLURM_ACCOUNT:-n03-hw}"
qos="${GCFOAM_SLURM_QOS:-standard}"
wall_time="${GCFOAM_SLURM_TIME:-24:00:00}"
repo_root="$(cd "$(dirname "$0")/../../../.." && pwd -P)"
env_file="$repo_root/.archer2-tools/gcfoam-env.sh"
[ -f "$env_file" ] || {
    echo "Missing ARCHER2 environment helper: $env_file" >&2
    exit 2
}

export_values="ALL,PLATFORM=ARCHER2,RT_RESTART=1,RT_TOTAL_TIME=$final_end_time,RT_WRITE_TIMESTEP=$RT_WRITE_TIMESTEP,RT_TIMESTEP=$RT_TIMESTEP"
if [ -n "$restart_time" ]; then
    export_values="$export_values,RT_RESTART_TIME=$restart_time"
fi

echo "Submitting restart: case=$case_name ranks=$expected nodes=$nodes final_end_time=$final_end_time"
echo "work_case_dir=$work_case_dir"
echo "RT_TIMESTEP=$RT_TIMESTEP RT_WRITE_TIMESTEP=$RT_WRITE_TIMESTEP"

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
    --wrap="source '$env_file' && ./runCaseReactiveTransport.sh"
)

if [ "${SUBMIT_DRY_RUN:-0}" = "1" ]; then
    printf 'sbatch'
    printf ' %q' "${sbatch_args[@]}"
    printf '\n'
    exit 0
fi

sbatch "${sbatch_args[@]}"
