#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

PE_SWEEP="${PE_SWEEP:-1 0.3 0.1}"
RT_CHECKPOINT_COUNT="${RT_CHECKPOINT_COUNT:-10}"

mkdir -p results/pe_sweep

for pe in $PE_SWEEP; do
  tag="$(python - <<'PY' "$pe"
import sys
print(("pe_" + sys.argv[1].replace(".", "p").replace("-", "m")).replace("+", ""))
PY
)"
  echo "=== Pe sweep: ${pe} (${tag}) ==="
  echo "Reactive transport timestep is computed after flow calibration unless RT_TIMESTEP or RT_TIMESTEP_OVERRIDE is set."
  TARGET_PE="$pe" RT_CHECKPOINT_COUNT="$RT_CHECKPOINT_COUNT" ./runAll.sh

  out_dir="results/pe_sweep/${tag}"
  mkdir -p "$out_dir"
  {
    echo "TARGET_PE=${pe}"
    echo "RT_TIMESTEP=${RT_TIMESTEP:-auto}"
    echo "RT_TIMESTEP_OVERRIDE=${RT_TIMESTEP_OVERRIDE:-unset}"
    echo "RT_CHECKPOINT_COUNT=${RT_CHECKPOINT_COUNT}"
    echo "RT_WRITE_TIMESTEP=${RT_WRITE_TIMESTEP:-auto}"
    echo "RT_TOTAL_TIME=${RT_TOTAL_TIME:-auto}"
  } > "$out_dir/run_config.env"
  cp results/matched_pe_flow_rates.json "$out_dir/"
  cp results/matched_pe_flow_rates.env "$out_dir/"
  cp results/current_run_config.env "$out_dir/"
  cp results/preflight_summary.md "$out_dir/"
  cp results/analysis_summary.json "$out_dir/"
  cp results/analysis_summary.csv "$out_dir/"
  cp results/analysis_profiles.csv "$out_dir/"
done

echo "=== Completed Pe sweep: ${PE_SWEEP} ==="
