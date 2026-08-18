#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

# This launcher intentionally previews by default. Each non-baseline production
# pair is expensive, and resolved-reference must stay pinned to the selected
# binary 5 um geometry rather than the native 1 um default.
export PE_SWEEP="${OTHER_PE_SWEEP:-0.3 0.1}"
case " $PE_SWEEP " in
    *" 1 "*)
        echo "Pe=1 is the completed baseline; select a non-baseline Pe." >&2
        exit 2
        ;;
esac
for pe in $PE_SWEEP; do
    case "$pe" in
        0.3|0.1|3|10) ;;
        *) echo "Unsupported OTHER_PE_SWEEP value: $pe" >&2; exit 2 ;;
    esac
done
export CASE_SWEEP="resolved-reference dbs-upscaled"
export RESOLVED_COARSEN_FACTOR=5
export RESOLVED_NODES=8
export RESOLVED_NPX=40
export RESOLVED_NPY=24
export RESOLVED_NPZ=1
export DBS_NODES=2
export DBS_NPX=32
export DBS_NPY=8
export DBS_NPZ=1
export RT_CHECKPOINT_COUNT=10
export TWO_SCALE_ARCHIVE_MODE="${TWO_SCALE_ARCHIVE_MODE:-metadata}"
export GCFOAM_SLURM_ACCOUNT="${GCFOAM_SLURM_ACCOUNT:-n03-hw}"
export GCFOAM_SLURM_QOS="${GCFOAM_SLURM_QOS:-standard}"

unset RT_TOTAL_TIME RT_WRITE_TIMESTEP RT_TIMESTEP RT_TIMESTEP_OVERRIDE
unset RT_CFL_TARGET RT_LOCAL_VELOCITY_FACTOR RT_FACE_VELOCITY_SAFETY
unset RT_TIMESTEP_MAX FLOW_TOTAL_TIME RT_INIT_ONLY RT_DRY_RUN_ONLY
unset RT_RESTART RT_RESTART_TIME

if [ "${CONFIRM_OTHER_PE_SUBMIT:-0}" = "1" ]; then
    unset SUBMIT_DRY_RUN
    echo "Submitting matched 5 um Pe=$PE_SWEEP resolved/DBS cases."
else
    export SUBMIT_DRY_RUN=1
    echo "Preview only. No jobs will be submitted."
    echo "Set CONFIRM_OTHER_PE_SUBMIT=1 to submit the selected resolved/DBS pair(s)."
fi

exec ./submit_archer_two_scale_all.sh
