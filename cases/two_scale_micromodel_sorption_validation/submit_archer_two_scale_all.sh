#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

pes="${PE_SWEEP:-1 0.3 0.1}"
cases="${CASE_SWEEP:-resolved-reference dbs-upscaled}"
submit_script="${SUBMIT_SCRIPT:-submit_archer_two_scale_case.slurm}"

for pe in $pes; do
  pe_tag="${pe//./p}"
  for case_name in $cases; do
    case_tag="${case_name//-/_}"
    if [ "$case_name" = "resolved-reference" ]; then
      nodes="${RESOLVED_NODES:-50}"
      export_args="TARGET_CASE=${case_name},TARGET_PE=${pe},RESOLVED_NPX=${RESOLVED_NPX:-160},RESOLVED_NPY=${RESOLVED_NPY:-40},RESOLVED_NPZ=${RESOLVED_NPZ:-1}"
    elif [ "$case_name" = "dbs-upscaled" ]; then
      nodes="${DBS_NODES:-2}"
      export_args="TARGET_CASE=${case_name},TARGET_PE=${pe},DBS_NPX=${DBS_NPX:-32},DBS_NPY=${DBS_NPY:-8},DBS_NPZ=${DBS_NPZ:-1}"
    else
      echo "Unknown case in CASE_SWEEP: ${case_name}" >&2
      exit 2
    fi
    echo "Submitting ${case_name} Pe=${pe} on ${nodes} nodes"
    sbatch \
      --job-name="ts_${case_tag}_${pe_tag}" \
      --nodes="$nodes" \
      --export="ALL,${export_args}" \
      "$submit_script"
  done
done
