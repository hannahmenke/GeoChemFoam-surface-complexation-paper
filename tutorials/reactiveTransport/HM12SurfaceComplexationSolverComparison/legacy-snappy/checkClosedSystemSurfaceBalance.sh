#!/bin/bash

set -e

log_file="reactiveScalarTransportFoamRT_closed.out"

if [ ! -f "$log_file" ]
then
    echo "ERROR: missing $log_file"
    exit 1
fi

aq_first=$(awk '/Ca\+2 integrated inventory =/ {print $5; exit}' "$log_file")
aq_last=$(awk '/Ca\+2 integrated inventory =/ {value=$5} END {print value}' "$log_file")
surf_first=$(awk '/Surf_aCa\+ integrated surface inventory =/ {print $6; exit}' "$log_file")
surf_last=$(awk '/Surf_aCa\+ integrated surface inventory =/ {value=$6} END {print value}' "$log_file")

if [ -z "$aq_first" ] || [ -z "$aq_last" ] || [ -z "$surf_first" ] || [ -z "$surf_last" ]
then
    echo "ERROR: failed to parse Ca balance terms from $log_file"
    exit 1
fi

python3 - "$aq_first" "$aq_last" "$surf_first" "$surf_last" <<'PY'
import math
import sys

aq_first = float(sys.argv[1])
aq_last = float(sys.argv[2])
surf_first = float(sys.argv[3])
surf_last = float(sys.argv[4])

total_first = aq_first + surf_first
total_last = aq_last + surf_last
delta = total_last - total_first
rel = abs(delta) / abs(total_first) if total_first else math.inf

print(f"Ca_aqueous_initial={aq_first:.16e}")
print(f"Ca_aqueous_final={aq_last:.16e}")
print(f"Ca_surface_initial={surf_first:.16e}")
print(f"Ca_surface_final={surf_last:.16e}")
print(f"Ca_total_initial={total_first:.16e}")
print(f"Ca_total_final={total_last:.16e}")
print(f"Ca_total_delta={delta:.16e}")
print(f"Ca_total_relative_delta={rel:.16e}")
PY
