#!/usr/bin/env python3
"""Validate concentration bounds in full-resolution Estaillades checkpoints."""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import numpy as np

from openfoam_field_io import read_internal_scalar


def active_field_extrema(
    paths: tuple[Path, Path, float],
) -> tuple[float, float, int]:
    field_path, eps_path, eps_min = paths
    values = read_internal_scalar(field_path)
    eps = read_internal_scalar(eps_path)
    if isinstance(values, float):
        if not np.isfinite(values):
            raise RuntimeError(f"Non-finite value in {field_path}")
    elif not np.all(np.isfinite(values)):
        raise RuntimeError(f"Non-finite values in {field_path}")

    if isinstance(eps, float):
        if not np.isfinite(eps):
            raise RuntimeError(f"Non-finite value in {eps_path}")
        if eps <= eps_min:
            raise RuntimeError(f"No chemistry-active cells in {eps_path}")
        count = 1 if isinstance(values, float) else values.size
        minimum = values if isinstance(values, float) else float(np.min(values))
        maximum = values if isinstance(values, float) else float(np.max(values))
        return float(minimum), float(maximum), count

    if not np.all(np.isfinite(eps)):
        raise RuntimeError(f"Non-finite values in {eps_path}")
    active = eps > eps_min
    active_count = int(np.count_nonzero(active))
    if active_count == 0:
        raise RuntimeError(f"No chemistry-active cells in {eps_path}")
    if isinstance(values, float):
        return values, values, active_count
    if values.size != eps.size:
        raise RuntimeError(f"Field/eps size mismatch: {field_path} and {eps_path}")
    active_values = values[active]
    return float(np.min(active_values)), float(np.max(active_values)), active_count


def time_name(value: float) -> str:
    return str(int(value)) if value == int(value) else str(value)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check conservative-species bounds in Estaillades outputs"
    )
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--times", type=float, nargs="+", required=True)
    parser.add_argument("--expected-ranks", type=int, default=64)
    parser.add_argument("--max-workers", type=int, default=8)
    parser.add_argument("--eps-min", type=float, default=1.0e-3)
    parser.add_argument("--lower-bound", type=float, default=-1.0e-10)
    parser.add_argument(
        "--cl-upper-bound",
        type=float,
        default=2.002e-3,
        help="Maximum Cl- concentration [mol/L]; default allows 0.1%% overshoot",
    )
    parser.add_argument(
        "--sr-upper-bound",
        type=float,
        default=1.001e-4,
        help="Maximum Sr+2 concentration [mol/L]; default allows 0.1%% overshoot",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    processor_dirs = sorted(
        args.case_dir.glob("processor*"),
        key=lambda path: int(path.name.removeprefix("processor")),
    )
    if len(processor_dirs) != args.expected_ranks:
        raise RuntimeError(
            f"Expected {args.expected_ranks} processor directories, "
            f"found {len(processor_dirs)}"
        )

    limits = {
        "Cl-": (args.lower_bound, args.cl_upper_bound),
        "Sr+2": (args.lower_bound, args.sr_upper_bound),
    }
    samples: list[dict[str, object]] = []
    failed: list[str] = []

    with ProcessPoolExecutor(max_workers=args.max_workers) as executor:
        for time_value in args.times:
            directory = time_name(time_value)
            sample: dict[str, object] = {"time_s": time_value, "fields": {}}
            for field, (lower, upper) in limits.items():
                field_paths = [proc / directory / field for proc in processor_dirs]
                eps_paths = [proc / directory / "eps" for proc in processor_dirs]
                missing = [
                    str(path)
                    for path in field_paths + eps_paths
                    if not path.is_file()
                ]
                if missing:
                    raise FileNotFoundError(
                        f"Missing {len(missing)} field/eps files at t={directory}; "
                        f"first missing: {missing[0]}"
                    )
                inputs = [
                    (field_path, eps_path, args.eps_min)
                    for field_path, eps_path in zip(field_paths, eps_paths)
                ]
                extrema = list(
                    executor.map(active_field_extrema, inputs, chunksize=1)
                )
                minimum = min(value[0] for value in extrema)
                maximum = max(value[1] for value in extrema)
                active_cells = sum(value[2] for value in extrema)
                passed = minimum >= lower and maximum <= upper
                sample["fields"][field] = {
                    "chemistry_active_cells": active_cells,
                    "minimum_mol_per_litre": minimum,
                    "maximum_mol_per_litre": maximum,
                    "lower_bound_mol_per_litre": lower,
                    "upper_bound_mol_per_litre": upper,
                    "passed": passed,
                }
                if not passed:
                    failed.append(
                        f"t={directory} {field}: [{minimum:.9g}, {maximum:.9g}] "
                        f"outside [{lower:.9g}, {upper:.9g}]"
                    )
            samples.append(sample)

    repo_root = Path(__file__).resolve().parents[4]
    case_path = args.case_dir.resolve()
    try:
        case_reference = str(case_path.relative_to(repo_root))
    except ValueError:
        case_reference = str(case_path)
    result = {
        "case": case_reference,
        "criterion": (
            "Finite Cl- and Sr+2 fields in chemistry-active cells with no "
            "more than 0.1% overshoot above their imposed maximum concentrations"
        ),
        "chemistry_active_eps_min": args.eps_min,
        "expected_ranks": args.expected_ranks,
        "passed": not failed,
        "samples": samples,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Wrote {args.output}")
    if failed:
        raise SystemExit("\n".join(failed))
    print("PASS: Estaillades concentration bounds")


if __name__ == "__main__":
    main()
