#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from generate_hm12_fourcase_conc_sorbed_diff import (
    assemble_parallel_structured,
    gather_parallel_unstructured,
)
from generate_micromodel_surface_area_validation import (
    mean_profile_over_pore,
    points_to_grid,
)


def as_plain_array(values: np.ndarray | np.ma.MaskedArray) -> np.ndarray:
    if np.ma.isMaskedArray(values):
        return np.asarray(values.filled(np.nan), dtype=float)
    return np.asarray(values, dtype=float)


def snappy_profile(case_dir: Path, time_name: str, cin: float, nx: int, ny: int, res: float) -> np.ndarray:
    x, y, values = gather_parallel_unstructured(case_dir, time_name, "Sr+2")
    field = points_to_grid(x, y, values / cin, nx, ny, res)
    return as_plain_array(mean_profile_over_pore(np.ma.masked_invalid(field)))


def dbs_profile(case_dir: Path, time_name: str, cin: float) -> np.ndarray:
    theta = assemble_parallel_structured(case_dir, "0", "theta")
    field = assemble_parallel_structured(case_dir, time_name, "Sr+2") / cin
    return as_plain_array(mean_profile_over_pore(np.where(theta > 0.5, field, np.nan)))


def front_position_mm(x_mm: np.ndarray, profile: np.ndarray, threshold: float) -> float:
    valid = np.isfinite(profile)
    above = np.where(valid & (profile >= threshold))[0]
    if above.size == 0:
        return np.nan

    i = int(above[-1])
    if i >= profile.size - 1 or not np.isfinite(profile[i + 1]):
        return float(x_mm[i])

    y0 = float(profile[i])
    y1 = float(profile[i + 1])
    if y0 == y1:
        return float(x_mm[i])

    frac = (threshold - y0) / (y1 - y0)
    return float(x_mm[i] + frac * (x_mm[i + 1] - x_mm[i]))


def relative_l1(candidate: np.ndarray, reference: np.ndarray, mask: np.ndarray) -> float:
    denom = float(np.sum(np.abs(reference[mask])))
    if denom <= 0.0:
        return np.nan
    return float(np.sum(np.abs(candidate[mask] - reference[mask])) / denom)


def relative_l2(candidate: np.ndarray, reference: np.ndarray, mask: np.ndarray) -> float:
    denom = float(np.sqrt(np.mean(reference[mask] ** 2)))
    if denom <= 0.0:
        return np.nan
    return float(np.sqrt(np.mean((candidate[mask] - reference[mask]) ** 2)) / denom)


def scaled_profile(x_mm: np.ndarray, profile: np.ndarray, scale: float) -> np.ndarray:
    return np.interp(x_mm / scale, x_mm, profile, left=profile[0], right=profile[-1])


def best_velocity_scale(
    x_mm: np.ndarray,
    candidate: np.ndarray,
    reference: np.ndarray,
    scale_min: float,
    scale_max: float,
    scale_count: int,
    active_threshold: float,
) -> dict[str, float]:
    base_mask = np.isfinite(candidate) & np.isfinite(reference) & (reference >= active_threshold)
    if not np.any(base_mask):
        return {
            "base_l1": np.nan,
            "base_l2": np.nan,
            "scale": np.nan,
            "scaled_l1": np.nan,
            "scaled_l2": np.nan,
        }

    base_l1 = relative_l1(candidate, reference, base_mask)
    base_l2 = relative_l2(candidate, reference, base_mask)

    best: tuple[float, float, float] | None = None
    for scale in np.linspace(scale_min, scale_max, scale_count):
        shifted = scaled_profile(x_mm, candidate, float(scale))
        mask = np.isfinite(shifted) & np.isfinite(reference) & (reference >= active_threshold)
        if not np.any(mask):
            continue
        l2 = relative_l2(shifted, reference, mask)
        l1 = relative_l1(shifted, reference, mask)
        if best is None or l2 < best[0]:
            best = (l2, l1, float(scale))

    if best is None:
        scaled_l2 = np.nan
        scaled_l1 = np.nan
        scale = np.nan
    else:
        scaled_l2, scaled_l1, scale = best

    return {
        "base_l1": base_l1,
        "base_l2": base_l2,
        "scale": scale,
        "scaled_l1": scaled_l1,
        "scaled_l2": scaled_l2,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Estimate micromodel aqueous-front offsets and pressure/velocity scale corrections."
    )
    parser.add_argument("--snappy-case", type=Path, required=True)
    parser.add_argument("--candidate-case", action="append", type=Path, required=True)
    parser.add_argument("--candidate-name", action="append", required=True)
    parser.add_argument("--time", default="200")
    parser.add_argument("--cin", type=float, default=1.0e-4)
    parser.add_argument("--nx", type=int, default=600)
    parser.add_argument("--ny", type=int, default=600)
    parser.add_argument("--res", type=float, default=3.0e-5)
    parser.add_argument("--thresholds", default="0.9,0.75,0.5,0.25,0.1,0.05")
    parser.add_argument("--scale-min", type=float, default=0.90)
    parser.add_argument("--scale-max", type=float, default=1.10)
    parser.add_argument("--scale-count", type=int, default=161)
    parser.add_argument("--active-threshold", type=float, default=0.01)
    parser.add_argument("--output-csv", type=Path, default=None)
    args = parser.parse_args()

    if len(args.candidate_case) != len(args.candidate_name):
        raise SystemExit("--candidate-name must be provided once per --candidate-case")

    thresholds = [float(item) for item in args.thresholds.split(",") if item.strip()]
    x_mm = (np.arange(args.nx) + 0.5) * args.res * 1.0e3
    reference = snappy_profile(args.snappy_case, args.time, args.cin, args.nx, args.ny, args.res)

    rows: list[dict[str, object]] = []
    print("Front positions [mm]")
    print("case threshold snappy candidate candidate_minus_snappy")
    for name, case_dir in zip(args.candidate_name, args.candidate_case):
        candidate = dbs_profile(case_dir, args.time, args.cin)
        for threshold in thresholds:
            ref_front = front_position_mm(x_mm, reference, threshold)
            cand_front = front_position_mm(x_mm, candidate, threshold)
            row = {
                "case": name,
                "threshold": threshold,
                "snappy_front_mm": ref_front,
                "candidate_front_mm": cand_front,
                "candidate_minus_snappy_mm": cand_front - ref_front,
            }
            rows.append(row)
            print(
                f"{name} {threshold:.3g} {ref_front:.6g} "
                f"{cand_front:.6g} {cand_front - ref_front:+.6g}"
            )

        scale_metrics = best_velocity_scale(
            x_mm,
            candidate,
            reference,
            args.scale_min,
            args.scale_max,
            args.scale_count,
            args.active_threshold,
        )
        rows.append(
            {
                "case": name,
                "threshold": "profile",
                "snappy_front_mm": "",
                "candidate_front_mm": "",
                "candidate_minus_snappy_mm": "",
                "base_l1_pct": 100.0 * scale_metrics["base_l1"],
                "base_l2_pct": 100.0 * scale_metrics["base_l2"],
                "best_velocity_scale": scale_metrics["scale"],
                "scaled_l1_pct": 100.0 * scale_metrics["scaled_l1"],
                "scaled_l2_pct": 100.0 * scale_metrics["scaled_l2"],
            }
        )
        print(
            f"{name} profile: base L1={100.0 * scale_metrics['base_l1']:.4g}% "
            f"L2={100.0 * scale_metrics['base_l2']:.4g}%; "
            f"best velocity scale={scale_metrics['scale']:.6g}, "
            f"scaled L1={100.0 * scale_metrics['scaled_l1']:.4g}% "
            f"L2={100.0 * scale_metrics['scaled_l2']:.4g}%"
        )

    if args.output_csv is not None:
        keys = sorted({key for row in rows for key in row})
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.output_csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=keys)
            writer.writeheader()
            writer.writerows(rows)


if __name__ == "__main__":
    main()
