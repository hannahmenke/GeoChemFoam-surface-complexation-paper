#!/usr/bin/env python3
"""Fail closed before the expensive Item 1 reactive-transport stage."""

import json
import re
from pathlib import Path


root = Path(__file__).resolve().parent
manifest = json.loads((root / "run_provenance.json").read_text())
expected = {
    "surface": 0.021990199701030694,
    "intrinsic_surface": 0.021960000000000004,
}
for key, area in expected.items():
    actual = manifest[key]["integrated_area_m2"]
    if actual != area:
        raise SystemExit(f"{key} area mismatch: {actual} != {area}")
density = manifest["chemistry"]["surface_master_densities_kmol_m2"]
if density != {"Surf_s": 2e-7, "Surf_w": 6e-6}:
    raise SystemExit(f"Surface-density mismatch: {density}")
control = (root / "system" / "controlDict1").read_text()
if not re.search(r"^\s*phreeqcRestoreCheckpoint\s+false\s*;", control, re.M):
    raise SystemExit("Fresh chemistry restore is not explicitly disabled")
print("Fresh Item 1 setup validated: areas, densities, and restore policy")
