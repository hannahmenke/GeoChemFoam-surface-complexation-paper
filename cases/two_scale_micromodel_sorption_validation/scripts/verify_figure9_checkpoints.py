#!/usr/bin/env python3
"""Fail-closed verification and manifest writer for manuscript Figure 9."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path


DOMAIN_LENGTH_M = 0.018
TARGET_X_OVER_L = 1.25
SPECS = (
    (0.1, "resolved-reference", 15481065, "2260.7265052181228", "dbs-upscaled", 15481066, "2035.2993634289082"),
    (1.0, "resolved-reference", 15481067, "226.07265052257375", "dbs-upscaled", 15481068, "203.52993233197378"),
    (3.0, "resolved-reference", 15481069, "75.357550174277307", "dbs-upscaled", 15481070, "67.84331284946101"),
    (10.0, "resolved-reference", 15481071, "22.607265052201129", "dbs-upscaled", 15481072, "20.352993294427328"),
)
REQUIRED_FILES = ("Li+", "Sor_aLi", "aSurf", "phreeqcDBS.dmp", "phreeqcDBS.complete")


def flow_values(path: Path) -> dict[str, float]:
    with path.open(newline="") as handle:
        row = next(csv.DictReader(handle, delimiter=" "))
    return {"UD_m_s": float(row["UD"]), "porosity": float(row["poro"])}


def verify_case(sweep_root: Path, pe: float, case_name: str, job_id: int, time_name: str) -> dict[str, object]:
    matches = list(sweep_root.glob(f"two_scale_{case_name}_pe_{pe:g}_*{job_id}"))
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {case_name} Pe={pe:g} job {job_id} root, found {matches}")
    case = matches[0] / case_name
    processors = sorted(case.glob("processor[0-9]*"))
    if not processors:
        raise RuntimeError(f"No processor directories in {case}")
    missing = {
        field: len(processors) - sum((processor / time_name / field).is_file() for processor in processors)
        for field in REQUIRED_FILES
    }
    if any(missing.values()):
        raise RuntimeError(f"Incomplete checkpoint {case} at {time_name}: {missing}")
    flow = flow_values(case / "poroPerm.csv")
    x_over_l = flow["UD_m_s"] / flow["porosity"] * float(time_name) / DOMAIN_LENGTH_M
    if abs(x_over_l - TARGET_X_OVER_L) > 1.0e-3:
        raise RuntimeError(f"Checkpoint {case} gives x/L={x_over_l:.9f}, not {TARGET_X_OVER_L:g}")
    return {
        "case": str(case.resolve()),
        "time": time_name,
        "job_id": job_id,
        "UD_m_s": flow["UD_m_s"],
        "porosity": flow["porosity"],
        "processors": len(processors),
        "x_over_L": x_over_l,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--sweep-root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    sweep_root = args.sweep_root.resolve()
    runs = []
    for pe, r_name, r_job, r_time, d_name, d_job, d_time in SPECS:
        resolved = verify_case(sweep_root, pe, r_name, r_job, r_time)
        dbs = verify_case(sweep_root, pe, d_name, d_job, d_time)
        runs.append({"peclet": pe, "resolved": resolved, "dbs": dbs})
    runtime_file = next(sweep_root.glob("*15481065/production_runtime_identity.json"))
    manifest = {
        "schema_version": 1,
        "description": "Verified completed ARCHER2 checkpoints for manuscript Figure 9.",
        "domain_length_m": DOMAIN_LENGTH_M,
        "comparison_distance_x_over_L": TARGET_X_OVER_L,
        "runtime_identity_sha256": hashlib.sha256(runtime_file.read_bytes()).hexdigest(),
        "runs": runs,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(manifest, indent=2) + "\n")
    print(json.dumps(manifest, indent=2))


if __name__ == "__main__":
    main()
