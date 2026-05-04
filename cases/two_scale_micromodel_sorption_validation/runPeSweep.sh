#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

PE_SWEEP="${PE_SWEEP:-1 0.3 0.1}"
RT_TIMESTEP_REF_PE="${RT_TIMESTEP_REF_PE:-1}"
RT_TIMESTEP_REF="${RT_TIMESTEP_REF:-0.01}"
RT_TIMESTEP_MAX="${RT_TIMESTEP_MAX:-0.1}"
RT_CHECKPOINT_COUNT="${RT_CHECKPOINT_COUNT:-4}"

mkdir -p results/pe_sweep

for pe in $PE_SWEEP; do
  tag="$(python - <<'PY' "$pe"
import sys
print(("pe_" + sys.argv[1].replace(".", "p").replace("-", "m")).replace("+", ""))
PY
)"
  echo "=== Pe sweep: ${pe} (${tag}) ==="
  if [ -n "${RT_TIMESTEP_OVERRIDE:-}" ]; then
    rt_timestep="$RT_TIMESTEP_OVERRIDE"
  else
    rt_timestep="$(python - <<'PY' "$pe" "$RT_TIMESTEP_REF_PE" "$RT_TIMESTEP_REF" "$RT_TIMESTEP_MAX"
import sys

pe = float(sys.argv[1])
reference_pe = float(sys.argv[2])
reference_dt = float(sys.argv[3])
max_dt = float(sys.argv[4])
if pe <= 0 or reference_pe <= 0:
    raise SystemExit("Pe must be positive")
print(f"{min(reference_dt * reference_pe / pe, max_dt):.12g}")
PY
)"
  fi
  echo "Reactive transport timestep for Pe=${pe}: RT_TIMESTEP=${rt_timestep}"
  echo "Timestep policy: RT_TIMESTEP=min(${RT_TIMESTEP_REF}*${RT_TIMESTEP_REF_PE}/Pe, ${RT_TIMESTEP_MAX}) unless RT_TIMESTEP_OVERRIDE is set."
  TARGET_PE="$pe" \
    RT_TIMESTEP="$rt_timestep" \
    RT_CHECKPOINT_COUNT="$RT_CHECKPOINT_COUNT" \
    ./runAll.sh

  out_dir="results/pe_sweep/${tag}"
  mkdir -p "$out_dir"
  {
    echo "TARGET_PE=${pe}"
    echo "RT_TIMESTEP=${rt_timestep}"
    echo "RT_TIMESTEP_REF_PE=${RT_TIMESTEP_REF_PE}"
    echo "RT_TIMESTEP_REF=${RT_TIMESTEP_REF}"
    echo "RT_TIMESTEP_MAX=${RT_TIMESTEP_MAX}"
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
