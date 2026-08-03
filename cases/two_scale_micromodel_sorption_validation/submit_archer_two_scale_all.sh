#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

if [ "${ALLOW_RT_OVERRIDES:-0}" != "1" ]; then
  for name in \
    RT_TOTAL_TIME RT_WRITE_TIMESTEP RT_TIMESTEP RT_TIMESTEP_OVERRIDE \
    RT_CFL_TARGET RT_LOCAL_VELOCITY_FACTOR RT_FACE_VELOCITY_SAFETY \
    RT_TIMESTEP_MAX FLOW_TOTAL_TIME \
    RT_INIT_ONLY RT_DRY_RUN_ONLY RT_RESTART RT_RESTART_TIME
  do
    if [ -n "${!name:-}" ]; then
      echo "Refusing production sweep with inherited $name=${!name}." >&2
      echo "Unset smoke/restart overrides, or set ALLOW_RT_OVERRIDES=1 deliberately." >&2
      exit 2
    fi
  done
fi

pes="${PE_SWEEP:-1 0.3 0.1}"
# Default to the validated, low-cost DBS cases. The 128-node resolved
# reference must be requested explicitly with CASE_SWEEP=resolved-reference.
cases="${CASE_SWEEP:-dbs-upscaled}"
submit_script="${SUBMIT_SCRIPT:-submit_archer_two_scale_case.slurm}"
account="${GCFOAM_SLURM_ACCOUNT:-n03-hw}"
qos="${GCFOAM_SLURM_QOS:-standard}"

for pe in $pes; do
  pe_tag="${pe//./p}"
  for case_name in $cases; do
    case_tag="${case_name//-/_}"
    if [ "$case_name" = "resolved-reference" ]; then
      resolved_factor="${RESOLVED_COARSEN_FACTOR:-1}"
      if [ "$resolved_factor" -eq 1 ]; then
        nodes="${RESOLVED_NODES:-128}"
        resolved_npx="${RESOLVED_NPX:-256}"
        resolved_npy="${RESOLVED_NPY:-64}"
      else
        nodes="${RESOLVED_NODES:-8}"
        resolved_npx="${RESOLVED_NPX:-40}"
        resolved_npy="${RESOLVED_NPY:-24}"
      fi
      tasks=$((resolved_npx * resolved_npy * ${RESOLVED_NPZ:-1}))
      export_args="TARGET_CASE=${case_name},TARGET_PE=${pe},RESOLVED_COARSEN_FACTOR=${resolved_factor},RESOLVED_NPX=${resolved_npx},RESOLVED_NPY=${resolved_npy},RESOLVED_NPZ=${RESOLVED_NPZ:-1}"
    elif [ "$case_name" = "dbs-upscaled" ]; then
      nodes="${DBS_NODES:-2}"
      tasks=$(( ${DBS_NPX:-32} * ${DBS_NPY:-8} * ${DBS_NPZ:-1} ))
      export_args="TARGET_CASE=${case_name},TARGET_PE=${pe},DBS_NPX=${DBS_NPX:-32},DBS_NPY=${DBS_NPY:-8},DBS_NPZ=${DBS_NPZ:-1}"
    else
      echo "Unknown case in CASE_SWEEP: ${case_name}" >&2
      exit 2
    fi
    if [ $((tasks % nodes)) -ne 0 ] || [ $((tasks / nodes)) -gt 128 ]; then
      echo "Invalid decomposition: ${tasks} ranks across ${nodes} nodes." >&2
      exit 2
    fi
    tasks_per_node=$((tasks / nodes))
    echo "Submitting ${case_name} Pe=${pe} on ${nodes} nodes"
    sbatch_args=(
      --job-name="ts_${case_tag}_${pe_tag}" \
      --account="$account" \
      --qos="$qos" \
      --nodes="$nodes" \
      --ntasks="$tasks" \
      --ntasks-per-node="$tasks_per_node" \
      --export="ALL,${export_args}" \
      "$submit_script"
    )
    if [ "${SUBMIT_DRY_RUN:-0}" = "1" ]; then
      printf 'sbatch'
      printf ' %q' "${sbatch_args[@]}"
      printf '\n'
    else
      sbatch "${sbatch_args[@]}"
    fi
  done
done
