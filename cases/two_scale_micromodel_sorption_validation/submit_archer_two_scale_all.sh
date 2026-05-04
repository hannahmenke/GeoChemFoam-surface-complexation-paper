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
    echo "Submitting ${case_name} Pe=${pe}"
    sbatch \
      --job-name="ts_${case_tag}_${pe_tag}" \
      --export=ALL,TARGET_CASE="$case_name",TARGET_PE="$pe" \
      "$submit_script"
  done
done
