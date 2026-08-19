#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np


LENGTH_MM = 18.0


def crossing_x(field: np.ndarray, threshold: float) -> np.ndarray:
    """First streamwise cell below threshold for each row."""
    below = field < threshold
    present = np.any(below, axis=1)
    index = np.argmax(below, axis=1)
    x = (index.astype(float) + 0.5) * LENGTH_MM / field.shape[1]
    x[~present] = LENGTH_MM
    return x


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("fields", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--assert-match", action="store_true")
    args = parser.parse_args()

    data = np.load(args.fields)
    resolved = data["resolved_aqueous"].astype(float)
    dbs = data["dbs_aqueous"].astype(float)
    valid = np.isfinite(resolved) & np.isfinite(dbs)
    difference = np.abs(dbs - resolved)

    thresholds: dict[str, dict[str, float]] = {}
    fronts: dict[float, tuple[np.ndarray, np.ndarray]] = {}
    for threshold in (0.1, 0.5, 0.9):
        resolved_front = crossing_x(resolved, threshold)
        dbs_front = crossing_x(dbs, threshold)
        fronts[threshold] = (resolved_front, dbs_front)
        displacement = dbs_front - resolved_front
        thresholds[f"c_over_cin_{threshold:g}"] = {
            "mean_resolved_front_mm": float(np.mean(resolved_front)),
            "mean_dbs_front_mm": float(np.mean(dbs_front)),
            "front_mean_absolute_difference_mm": float(np.mean(np.abs(displacement))),
            "front_max_absolute_difference_mm": float(np.max(np.abs(displacement))),
        }

    resolved_width = fronts[0.1][0] - fronts[0.9][0]
    dbs_width = fronts[0.1][1] - fronts[0.9][1]
    summary = {
        "threshold_fronts": thresholds,
        "transition_width": {
            "mean_resolved_10_to_90_width_mm": float(np.mean(resolved_width)),
            "mean_dbs_10_to_90_width_mm": float(np.mean(dbs_width)),
            "mean_absolute_width_difference_mm": float(np.mean(np.abs(dbs_width - resolved_width))),
        },
        "cellwise": {
            "mean_absolute_concentration_difference": float(np.mean(difference[valid])),
            "root_mean_square_concentration_difference": float(
                np.sqrt(np.mean(difference[valid] ** 2))
            ),
            "fraction_with_absolute_difference_over_0.1": float(np.mean(difference[valid] > 0.1)),
            "maximum_absolute_concentration_difference": float(np.max(difference[valid])),
        },
    }
    text = json.dumps(summary, indent=2) + "\n"
    if args.output:
        args.output.write_text(text)
    print(text, end="")
    if args.assert_match:
        failures = []
        mid_front_mad = thresholds["c_over_cin_0.5"]["front_mean_absolute_difference_mm"]
        width_mad = summary["transition_width"]["mean_absolute_width_difference_mm"]
        material_fraction = summary["cellwise"]["fraction_with_absolute_difference_over_0.1"]
        if mid_front_mad > 0.1:
            failures.append(f"C/Cin=0.5 front MAD {mid_front_mad:.3f} mm > 0.100 mm")
        if width_mad > 0.25:
            failures.append(f"10-90% width MAD {width_mad:.3f} mm > 0.250 mm")
        if material_fraction > 0.05:
            failures.append(f"material-error fraction {material_fraction:.3%} > 5.000%")
        if failures:
            print("FRONT_MATCH: FAIL\n- " + "\n- ".join(failures), file=sys.stderr)
            raise SystemExit(1)
        print("FRONT_MATCH: PASS")


if __name__ == "__main__":
    main()
