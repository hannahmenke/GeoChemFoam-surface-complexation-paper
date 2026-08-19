#!/bin/bash

set -e

###### USERS INPUT ############################################################

log_file="${1:-multiScalarTransportDBSFoamT_closed.out}"
rel_tol="${2:-5e-8}"

#### END OF USER INPUT #######################################################

python - "$log_file" "$rel_tol" <<'PY'
from pathlib import Path
import re
import sys

log_path = Path(sys.argv[1])
rel_tol = float(sys.argv[2])

if not log_path.exists():
    raise SystemExit(f"Missing log file: {log_path}")

pattern = re.compile(r'^(\S+)\s+integrated aqueous inventory =\s+([\-+0-9.eE]+)$')
series = {}

for line in log_path.read_text().splitlines():
    match = pattern.match(line.strip())
    if not match:
        continue
    species = match.group(1)
    value = float(match.group(2))
    series.setdefault(species, []).append(value)

if not series:
    raise SystemExit(f"No species inventory lines found in {log_path}")

failed = False

for species in sorted(series):
    values = series[species]

    if len(values) < 2:
        raise SystemExit(f"Need at least two inventory samples for {species} in {log_path}")

    initial = values[0]
    final = values[-1]
    abs_drift = abs(final - initial)
    denom = max(abs(initial), 1e-30)
    rel_drift = abs_drift / denom

    print(
        f"{species}: initial={initial:.16e} final={final:.16e} "
        f"abs_drift={abs_drift:.16e} rel_drift={rel_drift:.16e}"
    )

    if rel_drift > rel_tol:
        failed = True

if failed:
    raise SystemExit(f"Closed-system species balance failed: rel_tol = {rel_tol}")

print(f"Closed-system species balance passed: rel_tol = {rel_tol}")
PY
