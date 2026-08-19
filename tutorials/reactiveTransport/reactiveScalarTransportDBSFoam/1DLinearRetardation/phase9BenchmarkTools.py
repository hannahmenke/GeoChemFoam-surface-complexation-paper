#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SYSTEM_DIR = ROOT / "system"
DOMAIN_LENGTH = 4.0e-5
DOMAIN_HEIGHT = 1.0e-5
DOMAIN_DEPTH = 1.0e-6


def write_text(path: Path, text: str) -> None:
    path.write_text(text)


def parse_scalar_field(path: Path) -> list[float]:
    text = path.read_text()

    uniform_match = re.search(r"internalField\s+uniform\s+([^\n;]+)\s*;", text)
    if uniform_match:
        return [float(uniform_match.group(1))]

    nonuniform_match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not nonuniform_match:
        raise RuntimeError(f"Unsupported scalar field format in {path}")

    count = int(nonuniform_match.group(1))
    values = [float(item) for item in nonuniform_match.group(2).split()]
    if len(values) != count:
        raise RuntimeError(f"Value count mismatch in {path}")
    return values


def write_decompose(np: int) -> None:
    if np <= 0:
        raise RuntimeError("np must be positive")

    text = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      decomposeParDict;
}}

numberOfSubdomains {np};

method          simple;

simpleCoeffs
{{
    n               ({np} 1 1);
    delta           0.001;
}}

distributed     no;

roots           ();
"""
    write_text(SYSTEM_DIR / "decomposeParDict", text)


def write_block_mesh(nx: int) -> None:
    if nx <= 0:
        raise RuntimeError("nx must be positive")

    text = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}}

scale 1;

vertices
(
    (0 0 0)
    ({DOMAIN_LENGTH:.16e} 0 0)
    ({DOMAIN_LENGTH:.16e} {DOMAIN_HEIGHT:.16e} 0)
    (0 {DOMAIN_HEIGHT:.16e} 0)
    (0 0 {DOMAIN_DEPTH:.16e})
    ({DOMAIN_LENGTH:.16e} 0 {DOMAIN_DEPTH:.16e})
    ({DOMAIN_LENGTH:.16e} {DOMAIN_HEIGHT:.16e} {DOMAIN_DEPTH:.16e})
    (0 {DOMAIN_HEIGHT:.16e} {DOMAIN_DEPTH:.16e})
);

blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} 1 1) simpleGrading (1 1 1)
);

edges
(
);

boundary
(
    walls
    {{
        type wall;
        faces
        (
            (3 7 6 2)
        );
    }}
    fixedWalls
    {{
        type wall;
        faces
        (
            (0 1 5 4)
        );
    }}
    inlet
    {{
        type patch;
        faces
        (
            (0 4 7 3)
        );
    }}
    outlet
    {{
        type patch;
        faces
        (
            (1 2 6 5)
        );
    }}
    frontandback
    {{
        type empty;
        faces
        (
            (0 3 2 1)
            (4 5 6 7)
        );
    }}
);
"""
    write_text(SYSTEM_DIR / "blockMeshDict", text)


def write_control(end_time: float, delta_t: float, write_interval: float) -> None:
    text = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      controlDict;
}}

application     reactiveScalarTransportDBSFoam;

startFrom       startTime;

startTime       0;

stopAt          endTime;

endTime         {end_time:.16e};

deltaT          {delta_t:.16e};

writeControl    adjustableRunTime;

writeInterval   {write_interval:.16e};

purgeWrite      0;

writeFormat     ascii;

writePrecision  8;

writeCompression off;

timeFormat      general;

timePrecision   8;

runTimeModifiable yes;
"""
    write_text(SYSTEM_DIR / "controlDict", text)


def summarize_log(log_path: Path, rank_count: int, mode: str) -> None:
    text = log_path.read_text()

    execution_matches = re.findall(r"ExecutionTime = ([0-9.eE+-]+) s", text)
    if not execution_matches:
        raise RuntimeError(f"Missing ExecutionTime in {log_path}")
    execution_time = float(execution_matches[-1])

    chemistry_match = re.search(
        r"PhreeqcRM chemistry timing summary: calls=(\d+), total_s=([0-9.eE+-]+)",
        text,
    )
    if not chemistry_match:
        raise RuntimeError(f"Missing chemistry timing summary in {log_path}")

    chemistry_calls = int(chemistry_match.group(1))
    chemistry_time = float(chemistry_match.group(2))

    timestep_count = len(re.findall(r"^Time = ", text, re.M))
    if timestep_count <= 0:
        raise RuntimeError(f"Missing timestep markers in {log_path}")

    step_time = execution_time / timestep_count
    chemistry_step_time = chemistry_time / max(chemistry_calls, 1)
    chemistry_fraction = chemistry_time / max(execution_time, 1e-30)
    transport_plus_overhead = max(0.0, execution_time - chemistry_time)

    print(f"mode={mode}")
    print(f"ranks={rank_count}")
    print(f"timesteps={timestep_count}")
    print(f"execution_time_s={execution_time:.16e}")
    print(f"time_per_timestep_s={step_time:.16e}")
    print(f"chemistry_calls={chemistry_calls}")
    print(f"chemistry_total_s={chemistry_time:.16e}")
    print(f"chemistry_per_call_s={chemistry_step_time:.16e}")
    print(f"chemistry_fraction={chemistry_fraction:.16e}")
    print(f"transport_plus_overhead_s={transport_plus_overhead:.16e}")


def compare_fields(ref_path: Path, candidate_path: Path, label: str) -> None:
    ref_values = parse_scalar_field(ref_path)
    candidate_values = parse_scalar_field(candidate_path)

    if len(ref_values) != len(candidate_values):
        raise RuntimeError(f"Field length mismatch for {label}")

    abs_diffs = [abs(a - b) for a, b in zip(ref_values, candidate_values)]
    max_abs_diff = max(abs_diffs) if abs_diffs else 0.0
    mean_abs_diff = sum(abs_diffs) / max(len(abs_diffs), 1)

    ref_scale = max(max(abs(v) for v in ref_values), 1e-30)
    max_rel_diff = max_abs_diff / ref_scale

    print(f"label={label}")
    print(f"points={len(ref_values)}")
    print(f"max_abs_diff={max_abs_diff:.16e}")
    print(f"mean_abs_diff={mean_abs_diff:.16e}")
    print(f"max_rel_diff={max_rel_diff:.16e}")


def report_surface_state(ca_path: Path, surf_path: Path, theta: float, asurf: float) -> None:
    ca_values = parse_scalar_field(ca_path)
    surf_values = parse_scalar_field(surf_path)

    if len(ca_values) != len(surf_values):
        raise RuntimeError("Ca and surface field lengths do not match")

    mean_ca = sum(ca_values) / max(len(ca_values), 1)
    mean_surf = sum(surf_values) / max(len(surf_values), 1)
    total_equiv = theta * mean_ca + (asurf / theta) * mean_surf

    print(f"points={len(ca_values)}")
    print(f"ca_min={min(ca_values):.16e}")
    print(f"ca_max={max(ca_values):.16e}")
    print(f"ca_mean={mean_ca:.16e}")
    print(f"surf_min={min(surf_values):.16e}")
    print(f"surf_max={max(surf_values):.16e}")
    print(f"surf_mean={mean_surf:.16e}")
    print(f"total_equiv={total_equiv:.16e}")


def report_profile_metrics(
    ca_path: Path,
    surf_path: Path,
    theta: float,
    asurf: float,
    c_in: float,
    length: float,
) -> None:
    ca_values = parse_scalar_field(ca_path)
    surf_values = parse_scalar_field(surf_path)

    if len(ca_values) != len(surf_values):
        raise RuntimeError("Ca and surface field lengths do not match")

    n = len(ca_values)
    dx = length / max(n, 1)
    threshold = 0.5 * c_in

    front_index = -1
    for idx, value in enumerate(ca_values):
        if value >= threshold:
            front_index = idx

    if front_index >= 0:
        front_x = (front_index + 0.5) * dx
    else:
        front_x = 0.0

    mean_ca = sum(ca_values) / max(n, 1)
    mean_surf = sum(surf_values) / max(n, 1)
    total_equiv = theta * mean_ca + (asurf / theta) * mean_surf

    print(f"points={n}")
    print(f"dx={dx:.16e}")
    print(f"front_threshold={threshold:.16e}")
    print(f"front_x={front_x:.16e}")
    print(f"ca_mean={mean_ca:.16e}")
    print(f"surf_mean={mean_surf:.16e}")
    print(f"total_equiv={total_equiv:.16e}")


def compute_total_equiv(ca_path: Path, surf_path: Path, theta: float, asurf: float) -> float:
    ca_values = parse_scalar_field(ca_path)
    surf_values = parse_scalar_field(surf_path)

    if len(ca_values) != len(surf_values):
        raise RuntimeError("Ca and surface field lengths do not match")

    mean_ca = sum(ca_values) / max(len(ca_values), 1)
    mean_surf = sum(surf_values) / max(len(surf_values), 1)
    return theta * mean_ca + (asurf / theta) * mean_surf


def check_total_equiv(
    ref_ca: Path,
    ref_surf: Path,
    candidate_ca: Path,
    candidate_surf: Path,
    theta: float,
    asurf: float,
    rel_tol: float,
) -> None:
    ref_total = compute_total_equiv(ref_ca, ref_surf, theta, asurf)
    candidate_total = compute_total_equiv(candidate_ca, candidate_surf, theta, asurf)
    rel_diff = abs(candidate_total - ref_total) / max(abs(ref_total), 1e-30)

    print(f"ref_total_equiv={ref_total:.16e}")
    print(f"candidate_total_equiv={candidate_total:.16e}")
    print(f"rel_diff={rel_diff:.16e}")
    print(f"rel_tol={rel_tol:.16e}")

    if rel_diff > rel_tol:
        raise RuntimeError("Total equivalent drift exceeded tolerance")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    write_parser = subparsers.add_parser("write-decompose")
    write_parser.add_argument("--np", type=int, required=True)

    mesh_parser = subparsers.add_parser("write-block-mesh")
    mesh_parser.add_argument("--nx", type=int, required=True)

    control_parser = subparsers.add_parser("write-control")
    control_parser.add_argument("--end-time", type=float, required=True)
    control_parser.add_argument("--delta-t", type=float, required=True)
    control_parser.add_argument("--write-interval", type=float, required=True)

    summary_parser = subparsers.add_parser("summarize-log")
    summary_parser.add_argument("--log", type=Path, required=True)
    summary_parser.add_argument("--ranks", type=int, required=True)
    summary_parser.add_argument("--mode", choices=("surface", "aqueous"), required=True)

    compare_parser = subparsers.add_parser("compare-fields")
    compare_parser.add_argument("--ref", type=Path, required=True)
    compare_parser.add_argument("--candidate", type=Path, required=True)
    compare_parser.add_argument("--label", required=True)

    state_parser = subparsers.add_parser("report-surface-state")
    state_parser.add_argument("--ca", type=Path, required=True)
    state_parser.add_argument("--surf", type=Path, required=True)
    state_parser.add_argument("--theta", type=float, required=True)
    state_parser.add_argument("--asurf", type=float, required=True)

    profile_parser = subparsers.add_parser("report-profile-metrics")
    profile_parser.add_argument("--ca", type=Path, required=True)
    profile_parser.add_argument("--surf", type=Path, required=True)
    profile_parser.add_argument("--theta", type=float, required=True)
    profile_parser.add_argument("--asurf", type=float, required=True)
    profile_parser.add_argument("--c-in", type=float, required=True)
    profile_parser.add_argument("--length", type=float, required=True)

    total_parser = subparsers.add_parser("check-total-equiv")
    total_parser.add_argument("--ref-ca", type=Path, required=True)
    total_parser.add_argument("--ref-surf", type=Path, required=True)
    total_parser.add_argument("--candidate-ca", type=Path, required=True)
    total_parser.add_argument("--candidate-surf", type=Path, required=True)
    total_parser.add_argument("--theta", type=float, required=True)
    total_parser.add_argument("--asurf", type=float, required=True)
    total_parser.add_argument("--rel-tol", type=float, required=True)

    args = parser.parse_args()

    if args.command == "write-decompose":
        write_decompose(args.np)
    elif args.command == "write-block-mesh":
        write_block_mesh(args.nx)
    elif args.command == "write-control":
        write_control(args.end_time, args.delta_t, args.write_interval)
    elif args.command == "summarize-log":
        summarize_log(args.log, args.ranks, args.mode)
    elif args.command == "compare-fields":
        compare_fields(args.ref, args.candidate, args.label)
    elif args.command == "report-surface-state":
        report_surface_state(args.ca, args.surf, args.theta, args.asurf)
    elif args.command == "report-profile-metrics":
        report_profile_metrics(
            args.ca,
            args.surf,
            args.theta,
            args.asurf,
            args.c_in,
            args.length,
        )
    elif args.command == "check-total-equiv":
        check_total_equiv(
            args.ref_ca,
            args.ref_surf,
            args.candidate_ca,
            args.candidate_surf,
            args.theta,
            args.asurf,
            args.rel_tol,
        )


if __name__ == "__main__":
    main()
