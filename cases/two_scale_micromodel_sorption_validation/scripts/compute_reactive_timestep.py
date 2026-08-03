#!/usr/bin/env python3
from __future__ import annotations

import argparse
import glob
import json
import math
import re
from pathlib import Path


VECTOR_LIST = re.compile(
    r"internalField\s+nonuniform\s+List<vector>\s*(\d+)\s*\((.*?)\)\s*;",
    re.S,
)
VECTOR = re.compile(
    r"\(\s*([0-9.eE+-]+)\s+([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*\)"
)
UNIFORM_VECTOR = re.compile(
    r"internalField\s+uniform\s+\(\s*([0-9.eE+-]+)\s+"
    r"([0-9.eE+-]+)\s+([0-9.eE+-]+)\s*\)\s*;"
)


def read_resolution(case_dir: Path) -> float:
    generated_cell_size = case_dir / "system" / "cellSize"
    if generated_cell_size.is_file():
        value = float(generated_cell_size.read_text().strip())
        if not math.isfinite(value) or value <= 0:
            raise RuntimeError(f"Invalid cell size {value} in {generated_cell_size}")
        return value
    text = (case_dir / "createMesh.sh").read_text()
    match = re.search(r"^res=([0-9.eE+-]+)", text, re.M)
    if not match:
        raise RuntimeError(f"Could not find res= in {case_dir / 'createMesh.sh'}")
    return float(match.group(1))


def velocity_files(case_dir: Path) -> list[Path]:
    processors = sorted(
        Path(path) for path in glob.glob(str(case_dir / "processor*" / "0" / "U"))
    )
    if processors:
        return processors
    serial = case_dir / "0" / "U"
    return [serial] if serial.is_file() else []


def max_cell_l1_velocity(case_dir: Path) -> float:
    paths = velocity_files(case_dir)
    if not paths:
        raise RuntimeError(
            f"No calibrated flow field found at {case_dir}/0/U or "
            f"{case_dir}/processor*/0/U; run processFlow.sh first"
        )

    maximum = 0.0
    for path in paths:
        text = path.read_text()
        listed = VECTOR_LIST.search(text)
        if listed:
            count = int(listed.group(1))
            vectors = VECTOR.findall(listed.group(2))
            if len(vectors) != count:
                raise RuntimeError(
                    f"Expected {count} internal velocity vectors in {path}, "
                    f"found {len(vectors)}"
                )
            maximum = max(
                maximum,
                max(sum(abs(float(component)) for component in vector) for vector in vectors),
            )
            continue

        uniform = UNIFORM_VECTOR.search(text)
        if uniform:
            maximum = max(
                maximum,
                sum(abs(float(component)) for component in uniform.groups()),
            )
            continue

        raise RuntimeError(f"Could not parse internalField from {path}")

    if not math.isfinite(maximum) or maximum <= 0:
        raise RuntimeError(f"Invalid maximum velocity {maximum} in {case_dir}")
    return maximum


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case_root", type=Path)
    parser.add_argument("matched_pe_json", type=Path)
    parser.add_argument("--case", action="append", dest="cases", default=[])
    parser.add_argument("--target-max-co", type=float, default=0.8)
    parser.add_argument(
        "--local-velocity-factor",
        type=float,
        default=0.0,
        help="Optional lower bound; measured calibration-field factor is used by default",
    )
    parser.add_argument(
        "--face-velocity-safety",
        type=float,
        default=1.25,
        help="Safety multiplier from maximum cell-centre L1 speed to face speed",
    )
    parser.add_argument("--max-dt", type=float, default=0.0)
    parser.add_argument(
        "--velocity-at-target-flow",
        action="store_true",
        help="Treat the stored velocity field as the final target-flow field",
    )
    parser.add_argument("--out-json", type=Path, default=None)
    args = parser.parse_args()

    if args.target_max_co <= 0:
        raise SystemExit("--target-max-co must be positive")
    if args.local_velocity_factor < 0:
        raise SystemExit("--local-velocity-factor must be non-negative")
    if args.face_velocity_safety < 1:
        raise SystemExit("--face-velocity-safety must be at least 1")

    matched = json.loads(args.matched_pe_json.read_text())
    selected_cases = args.cases or list(matched["cases"])

    per_case: dict[str, dict[str, float]] = {}
    for case_name in selected_cases:
        case = matched["cases"][case_name]
        case_dir = args.case_root / case_name
        dx = read_resolution(case_dir)
        pore_velocity = float(case["target_pore_velocity_m_per_s"])
        measured_max_velocity = max_cell_l1_velocity(case_dir)
        calibration = case["calibration"]
        calibration_pore_velocity = float(calibration["UD"]) / float(
            calibration["poro"]
        )
        reference_pore_velocity = (
            pore_velocity if args.velocity_at_target_flow else calibration_pore_velocity
        )
        measured_factor = measured_max_velocity / reference_pore_velocity
        design_factor = max(
            args.local_velocity_factor,
            args.face_velocity_safety * measured_factor,
        )
        dt = args.target_max_co * dx / (design_factor * pore_velocity)
        if args.max_dt > 0:
            dt = min(dt, args.max_dt)
        per_case[case_name] = {
            "cell_size_m": dx,
            "target_pore_velocity_m_per_s": pore_velocity,
            "calibration_pore_velocity_m_per_s": calibration_pore_velocity,
            "velocity_field_at_target_flow": args.velocity_at_target_flow,
            "measured_max_cell_l1_velocity_m_per_s": measured_max_velocity,
            "measured_local_velocity_factor": measured_factor,
            "face_velocity_safety": args.face_velocity_safety,
            "minimum_local_velocity_factor": args.local_velocity_factor,
            "design_local_velocity_factor": design_factor,
            "target_max_co": args.target_max_co,
            "recommended_timestep_s": dt,
            "predicted_max_courant": design_factor * pore_velocity * dt / dx,
        }

    timestep = min(item["recommended_timestep_s"] for item in per_case.values())
    payload = {
        "policy": (
            "scale the maximum calibrated cell-centre L1 velocity to the target "
            "flow, apply a face-velocity safety multiplier, and enforce target_max_co"
        ),
        "selected_cases": selected_cases,
        "recommended_timestep_s": timestep,
        "per_case": per_case,
    }

    if args.out_json is not None:
        args.out_json.parent.mkdir(parents=True, exist_ok=True)
        args.out_json.write_text(json.dumps(payload, indent=2) + "\n")

    print(f"{timestep:.12g}")


if __name__ == "__main__":
    main()
