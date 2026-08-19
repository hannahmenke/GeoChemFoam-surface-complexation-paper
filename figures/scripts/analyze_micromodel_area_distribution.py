#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from pathlib import Path

import numpy as np

from generate_hm12_fourcase_conc_sorbed_diff import (
    assemble_parallel_structured,
    boundary_patch_segments,
)
from generate_micromodel_surface_area_validation import (
    assemble_structured_with_fallback,
    wall_inventory_grid,
)


def first_shell_support(pore_mask: np.ndarray) -> np.ndarray:
    solid = ~pore_mask
    support = np.zeros_like(pore_mask, dtype=bool)
    support[:-1, :] |= pore_mask[:-1, :] & solid[1:, :]
    support[1:, :] |= pore_mask[1:, :] & solid[:-1, :]
    support[:, :-1] |= pore_mask[:, :-1] & solid[:, 1:]
    support[:, 1:] |= pore_mask[:, 1:] & solid[:, :-1]
    return support


def nearest_supported_cell(
    y: float,
    x: float,
    support: np.ndarray,
    res: float,
    search_radius: int,
) -> tuple[int, int] | None:
    ny, nx = support.shape
    j0 = int(np.clip(np.floor(y / res), 0, ny - 1))
    i0 = int(np.clip(np.floor(x / res), 0, nx - 1))
    if support[j0, i0]:
        return j0, i0

    best = None
    best_dist2 = None
    for dj in range(-search_radius, search_radius + 1):
        for di in range(-search_radius, search_radius + 1):
            j = j0 + dj
            i = i0 + di
            if j < 0 or j >= ny or i < 0 or i >= nx or not support[j, i]:
                continue
            cy = (j + 0.5) * res
            cx = (i + 0.5) * res
            dist2 = (cy - y) ** 2 + (cx - x) ** 2
            if best_dist2 is None or dist2 < best_dist2:
                best_dist2 = dist2
                best = (j, i)
    return best


def wall_area_grid_on_support(
    segments: np.ndarray,
    nx: int,
    ny: int,
    res: float,
    support: np.ndarray,
    search_radius: int,
) -> np.ndarray:
    grid = np.zeros((ny, nx), dtype=float)
    if segments.size == 0:
        return grid

    midpoints = segments.mean(axis=1)
    lengths = np.linalg.norm(segments[:, 1, :] - segments[:, 0, :], axis=1)
    for midpoint, length in zip(midpoints, lengths):
        target = nearest_supported_cell(
            y=float(midpoint[1]),
            x=float(midpoint[0]),
            support=support,
            res=res,
            search_radius=search_radius,
        )
        if target is not None:
            grid[target] += length * res
    return grid


def rel_l1(candidate: np.ndarray, reference: np.ndarray) -> float:
    scale = float(np.sum(np.abs(reference)))
    return np.nan if scale <= 0.0 else float(np.sum(np.abs(candidate - reference)) / scale)


def rel_l2(candidate: np.ndarray, reference: np.ndarray) -> float:
    scale = float(np.sqrt(np.mean(reference**2)))
    return np.nan if scale <= 0.0 else float(np.sqrt(np.mean((candidate - reference) ** 2)) / scale)


def support_metrics(candidate: np.ndarray, reference: np.ndarray) -> dict[str, float | int]:
    c = candidate > 0.0
    r = reference > 0.0
    intersection = int(np.count_nonzero(c & r))
    union = int(np.count_nonzero(c | r))
    return {
        "candidate_active_cells": int(np.count_nonzero(c)),
        "reference_active_cells": int(np.count_nonzero(r)),
        "intersection_cells": intersection,
        "union_cells": union,
        "false_positive_cells": int(np.count_nonzero(c & ~r)),
        "false_negative_cells": int(np.count_nonzero(~c & r)),
        "jaccard": float(intersection / union) if union else np.nan,
    }


def distribution_metrics(candidate: np.ndarray, reference: np.ndarray) -> dict[str, float | int]:
    col_c = np.sum(candidate, axis=0)
    col_r = np.sum(reference, axis=0)
    row_c = np.sum(candidate, axis=1)
    row_r = np.sum(reference, axis=1)
    total_r = float(np.sum(reference))
    total_c = float(np.sum(candidate))
    col_corr = np.nan
    row_corr = np.nan
    if np.std(col_c) > 0.0 and np.std(col_r) > 0.0:
        col_corr = float(np.corrcoef(col_c, col_r)[0, 1])
    if np.std(row_c) > 0.0 and np.std(row_r) > 0.0:
        row_corr = float(np.corrcoef(row_c, row_r)[0, 1])

    result: dict[str, float | int] = {
        "reference_area": total_r,
        "candidate_area": total_c,
        "total_rel_error": np.nan if total_r <= 0.0 else float((total_c - total_r) / total_r),
        "global_l1": rel_l1(candidate, reference),
        "global_l2": rel_l2(candidate, reference),
        "column_profile_l1": rel_l1(col_c, col_r),
        "row_profile_l1": rel_l1(row_c, row_r),
        "column_corr": col_corr,
        "row_corr": row_corr,
    }
    result.update(support_metrics(candidate, reference))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare DBS aSurf area distribution against a resolved-wall snappy reference."
    )
    parser.add_argument("--legacy-snappy-case", type=Path, required=True)
    parser.add_argument("--candidate-case", action="append", type=Path, required=True)
    parser.add_argument("--candidate-name", action="append", required=True)
    parser.add_argument("--candidate-field", action="append", default=[])
    parser.add_argument("--time", default="200")
    parser.add_argument("--fallback-time", default="0")
    parser.add_argument("--nx", type=int, default=600)
    parser.add_argument("--ny", type=int, default=600)
    parser.add_argument("--res", type=float, default=3e-5)
    parser.add_argument(
        "--reference-mapping",
        choices=("midpoint", "nearest-support"),
        default="nearest-support",
    )
    parser.add_argument("--support-radius", type=int, default=2)
    parser.add_argument("--output-csv", type=Path, default=None)
    args = parser.parse_args()

    if len(args.candidate_name) != len(args.candidate_case):
        raise SystemExit("--candidate-name must be provided once per --candidate-case")
    if args.candidate_field and len(args.candidate_field) != len(args.candidate_case):
        raise SystemExit("--candidate-field must be omitted or provided once per --candidate-case")

    candidate_fields = args.candidate_field or ["aSurf"] * len(args.candidate_case)
    cell_volume = args.res ** 3

    segments, _ = boundary_patch_segments(args.legacy_snappy_case, args.time, None)

    rows: list[dict[str, object]] = []
    for name, case_dir, field_name in zip(args.candidate_name, args.candidate_case, candidate_fields):
        theta = assemble_parallel_structured(case_dir, "0", "theta")
        pore_mask = theta > 0.5
        a_surf = assemble_structured_with_fallback(case_dir, args.time, args.fallback_time, field_name)
        candidate = np.where(pore_mask & (a_surf > 0.0), a_surf * cell_volume, 0.0)

        if args.reference_mapping == "nearest-support":
            reference = wall_area_grid_on_support(
                segments,
                args.nx,
                args.ny,
                args.res,
                first_shell_support(pore_mask),
                args.support_radius,
            )
        else:
            reference = wall_inventory_grid(
                segments,
                np.ones(segments.shape[0], dtype=float),
                args.nx,
                args.ny,
                args.res,
            )

        row = {"case": name, "field": field_name, "reference_mapping": args.reference_mapping}
        row.update(distribution_metrics(candidate, reference))
        rows.append(row)

    fieldnames = list(rows[0].keys()) if rows else []
    if args.output_csv is not None:
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.output_csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    for row in rows:
        print(
            f"{row['case']:>18s} {row['field']:>16s} "
            f"area={row['candidate_area']:.12e} "
            f"rel={row['total_rel_error']:+.3%} "
            f"L1={row['global_l1']:.3f} "
            f"colL1={row['column_profile_l1']:.3f} "
            f"J={row['jaccard']:.3f} "
            f"FP={row['false_positive_cells']} "
            f"FN={row['false_negative_cells']}"
        )


if __name__ == "__main__":
    main()
