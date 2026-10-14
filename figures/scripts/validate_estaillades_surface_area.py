#!/usr/bin/env python3
"""Validate integrated reactive area in parallel Estaillades checkpoints."""

from __future__ import annotations

import argparse
import json
import math
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from openfoam_field_io import read_internal_scalar


def partition_area(args: tuple[Path, float]) -> float:
    path, cell_volume = args
    values = read_internal_scalar(path)
    if isinstance(values, float):
        raise RuntimeError(f"Expected a nonuniform aSurf field in {path}")
    if not np.all(np.isfinite(values)) or np.any(values < 0.0):
        raise RuntimeError(f"Invalid aSurf values in {path}")
    return float(np.sum(values, dtype=np.float64)) * cell_volume


def reference_area(surface_log: Path) -> float:
    match = re.search(
        r"sum\(aSurf\*V\)=([0-9.eE+-]+)", surface_log.read_text()
    )
    if not match:
        raise RuntimeError(f"Could not read integrated area from {surface_log}")
    return float(match.group(1))


def time_name(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--surface-log", type=Path, required=True)
    parser.add_argument("--times", type=float, nargs="+", required=True)
    parser.add_argument("--expected-ranks", type=int, default=64)
    parser.add_argument("--voxel-size", type=float, default=4.0e-6)
    parser.add_argument("--relative-tolerance", type=float, default=1.0e-12)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    processors = sorted(
        args.case_dir.glob("processor*"),
        key=lambda path: int(path.name.removeprefix("processor")),
    )
    if len(processors) != args.expected_ranks:
        raise RuntimeError(
            f"Expected {args.expected_ranks} processor directories, "
            f"found {len(processors)}"
        )

    expected_area = reference_area(args.surface_log)
    cell_volume = args.voxel_size**3
    samples: list[dict[str, object]] = []
    passed = True
    with ProcessPoolExecutor(max_workers=args.max_workers) as executor:
        for value in args.times:
            directory = time_name(value)
            paths = [processor / directory / "aSurf" for processor in processors]
            missing = [str(path) for path in paths if not path.is_file()]
            if missing:
                raise FileNotFoundError(
                    f"Missing {len(missing)} aSurf files at t={directory}; "
                    f"first missing: {missing[0]}"
                )
            area = sum(
                executor.map(
                    partition_area,
                    [(path, cell_volume) for path in paths],
                    chunksize=1,
                )
            )
            relative_difference = abs(area - expected_area) / expected_area
            sample_passed = math.isfinite(area) and (
                relative_difference <= args.relative_tolerance
            )
            passed = passed and sample_passed
            samples.append(
                {
                    "time_s": value,
                    "integrated_area_m2": area,
                    "relative_difference_from_surface_log": relative_difference,
                    "passed": sample_passed,
                }
            )

    result = {
        "case": (
            ""
            "cases/3d_estaillades"
        ),
        "criterion": (
            "Integrated aSurf at every retained checkpoint agrees with the "
            "surface-construction record within the stated relative tolerance"
        ),
        "expected_ranks": args.expected_ranks,
        "voxel_size_m": args.voxel_size,
        "reference_area_m2": expected_area,
        "relative_tolerance": args.relative_tolerance,
        "passed": passed,
        "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {args.output}")
    if not passed:
        raise SystemExit("Integrated surface-area validation failed")
    print("PASS: Estaillades integrated surface area")


if __name__ == "__main__":
    main()
