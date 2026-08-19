#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np

from generate_hm12_fourcase_conc_sorbed_diff import (
    assemble_parallel_structured,
    boundary_patch_segments,
    gather_parallel_unstructured,
    masked_structured,
    points_to_grid,
)
from generate_micromodel_surface_area_validation import (
    assemble_structured_with_fallback,
    dbs_inventory_grid,
    mean_profile_over_pore,
    wall_inventory_grid,
)


@dataclass(frozen=True)
class ClipBox:
    name: str
    x0_mm: float
    x1_mm: float
    y0_mm: float
    y1_mm: float

    def to_index_bounds(self, res_mm: float, nx: int, ny: int) -> tuple[int, int, int, int]:
        ix0 = max(0, min(nx, int(np.floor(self.x0_mm / res_mm))))
        ix1 = max(0, min(nx, int(np.ceil(self.x1_mm / res_mm))))
        iy0 = max(0, min(ny, int(np.floor(self.y0_mm / res_mm))))
        iy1 = max(0, min(ny, int(np.ceil(self.y1_mm / res_mm))))
        if ix1 <= ix0 or iy1 <= iy0:
            raise ValueError(f"Clip '{self.name}' is empty after discretization")
        return ix0, ix1, iy0, iy1


def parse_clip(spec: str) -> ClipBox:
    parts = [part.strip() for part in spec.split(",")]
    if len(parts) != 5:
        raise argparse.ArgumentTypeError(
            "clip must be NAME,x0_mm,x1_mm,y0_mm,y1_mm"
        )
    name = parts[0]
    try:
        x0_mm, x1_mm, y0_mm, y1_mm = [float(value) for value in parts[1:]]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "clip bounds must be numeric: NAME,x0_mm,x1_mm,y0_mm,y1_mm"
        ) from exc
    if x1_mm <= x0_mm or y1_mm <= y0_mm:
        raise argparse.ArgumentTypeError("clip bounds must satisfy x1>x0 and y1>y0")
    return ClipBox(name, x0_mm, x1_mm, y0_mm, y1_mm)


def relative_l1(candidate: np.ndarray, reference: np.ndarray) -> float:
    valid = np.isfinite(candidate) & np.isfinite(reference)
    if not np.any(valid):
        return np.nan
    scale = float(np.mean(np.abs(reference[valid])))
    if scale <= 0.0:
        return np.nan
    return float(np.mean(np.abs(candidate[valid] - reference[valid])) / scale)


def relative_l2(candidate: np.ndarray, reference: np.ndarray) -> float:
    valid = np.isfinite(candidate) & np.isfinite(reference)
    if not np.any(valid):
        return np.nan
    scale = float(np.sqrt(np.mean(reference[valid] ** 2)))
    if scale <= 0.0:
        return np.nan
    return float(np.sqrt(np.mean((candidate[valid] - reference[valid]) ** 2)) / scale)


def masked_rect(field: np.ndarray, ix0: int, ix1: int, iy0: int, iy1: int) -> np.ndarray:
    return field[iy0:iy1, ix0:ix1]


def pore_profile_in_clip(field: np.ndarray, mask: np.ndarray, ix0: int, ix1: int, iy0: int, iy1: int) -> np.ndarray:
    clipped = masked_structured(field, mask)[iy0:iy1, ix0:ix1]
    return mean_profile_over_pore(np.ma.filled(clipped, np.nan))


def total_nonnegative(field: np.ndarray, ix0: int, ix1: int, iy0: int, iy1: int) -> float:
    return float(np.sum(np.nan_to_num(field[iy0:iy1, ix0:ix1], nan=0.0)))


def iter_cases() -> Iterable[tuple[str, Path]]:
    yield "gradeps", Path()
    yield "smoothsurface", Path()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare local surface-area and transport errors in rectangular micromodel clips."
    )
    parser.add_argument("--legacy-snappy-case", required=True)
    parser.add_argument("--dbs-gradeps-case", required=True)
    parser.add_argument("--dbs-smoothsurface-case", required=True)
    parser.add_argument("--time", default="200")
    parser.add_argument("--cin", type=float, default=1e-4)
    parser.add_argument("--nx", type=int, default=600)
    parser.add_argument("--ny", type=int, default=600)
    parser.add_argument("--res", type=float, default=3e-5)
    parser.add_argument(
        "--clip",
        action="append",
        type=parse_clip,
        required=True,
        help="NAME,x0_mm,x1_mm,y0_mm,y1_mm; may be repeated",
    )
    parser.add_argument("--output-csv", type=Path, default=None)
    args = parser.parse_args()

    time_name = args.time
    cell_volume = args.res ** 3
    res_mm = args.res * 1e3

    legacy_snappy_case = Path(args.legacy_snappy_case)
    dbs_gradeps_case = Path(args.dbs_gradeps_case)
    dbs_smooth_case = Path(args.dbs_smoothsurface_case)

    theta_gradeps = assemble_parallel_structured(dbs_gradeps_case, "0", "theta")
    pore_mask_gradeps = theta_gradeps > 0.5
    theta_smooth = assemble_parallel_structured(dbs_smooth_case, "0", "theta")
    pore_mask_smooth = theta_smooth > 0.5

    gradeps_sr = assemble_parallel_structured(dbs_gradeps_case, time_name, "Sr+2") / args.cin
    gradeps_sorbed = assemble_parallel_structured(dbs_gradeps_case, time_name, "Surf_aSr+")
    gradeps_asurf = assemble_structured_with_fallback(dbs_gradeps_case, time_name, "0", "aSurf")

    smooth_sr = assemble_parallel_structured(dbs_smooth_case, time_name, "Sr+2") / args.cin
    smooth_sorbed = assemble_parallel_structured(dbs_smooth_case, time_name, "Surf_aSr+")
    smooth_asurf = assemble_structured_with_fallback(dbs_smooth_case, time_name, "0", "aSurf")

    snappy_x, snappy_y, snappy_sr_vals = gather_parallel_unstructured(legacy_snappy_case, time_name, "Sr+2")
    snappy_sr = points_to_grid(snappy_x, snappy_y, snappy_sr_vals / args.cin, args.nx, args.ny, args.res)
    snappy_pore_mask = np.isfinite(snappy_sr)
    snappy_wall_segments, snappy_wall_sorbed_vals = boundary_patch_segments(
        legacy_snappy_case, time_name, "Surf_aSr+"
    )
    snappy_area_grid = wall_inventory_grid(
        snappy_wall_segments,
        np.ones_like(snappy_wall_sorbed_vals),
        args.nx,
        args.ny,
        args.res,
    )
    snappy_sorbed_inventory = wall_inventory_grid(
        snappy_wall_segments,
        snappy_wall_sorbed_vals,
        args.nx,
        args.ny,
        args.res,
    )
    gradeps_sorbed_inventory = dbs_inventory_grid(
        gradeps_sorbed, gradeps_asurf, pore_mask_gradeps, cell_volume
    )
    smooth_sorbed_inventory = dbs_inventory_grid(
        smooth_sorbed, smooth_asurf, pore_mask_smooth, cell_volume
    )
    gradeps_area_grid = np.where(
        pore_mask_gradeps & (gradeps_asurf > 0.0), gradeps_asurf * cell_volume, 0.0
    )
    smooth_area_grid = np.where(
        pore_mask_smooth & (smooth_asurf > 0.0), smooth_asurf * cell_volume, 0.0
    )

    rows: list[dict[str, object]] = []
    for clip in args.clip:
        ix0, ix1, iy0, iy1 = clip.to_index_bounds(res_mm, args.nx, args.ny)

        snappy_profile = pore_profile_in_clip(snappy_sr, snappy_pore_mask, ix0, ix1, iy0, iy1)
        gradeps_profile = pore_profile_in_clip(gradeps_sr, pore_mask_gradeps, ix0, ix1, iy0, iy1)
        smooth_profile = pore_profile_in_clip(smooth_sr, pore_mask_smooth, ix0, ix1, iy0, iy1)

        snappy_area_total = total_nonnegative(snappy_area_grid, ix0, ix1, iy0, iy1)
        snappy_sorbed_total = total_nonnegative(snappy_sorbed_inventory, ix0, ix1, iy0, iy1)

        case_data = [
            (
                "gradeps",
                gradeps_profile,
                gradeps_area_grid,
                gradeps_sorbed_inventory,
            ),
            (
                "smoothsurface",
                smooth_profile,
                smooth_area_grid,
                smooth_sorbed_inventory,
            ),
        ]
        for case_name, aq_profile, area_grid, sorbed_grid in case_data:
            area_total = total_nonnegative(area_grid, ix0, ix1, iy0, iy1)
            sorbed_total = total_nonnegative(sorbed_grid, ix0, ix1, iy0, iy1)
            area_rel = np.nan if snappy_area_total <= 0.0 else abs(area_total - snappy_area_total) / snappy_area_total
            sorbed_rel = (
                np.nan if snappy_sorbed_total <= 0.0 else abs(sorbed_total - snappy_sorbed_total) / snappy_sorbed_total
            )
            rows.append(
                {
                    "clip": clip.name,
                    "x0_mm": clip.x0_mm,
                    "x1_mm": clip.x1_mm,
                    "y0_mm": clip.y0_mm,
                    "y1_mm": clip.y1_mm,
                    "case": case_name,
                    "cells_x": ix1 - ix0,
                    "cells_y": iy1 - iy0,
                    "snappy_area_m2": snappy_area_total,
                    "candidate_area_m2": area_total,
                    "area_rel_error_pct": 100.0 * area_rel if np.isfinite(area_rel) else np.nan,
                    "aqueous_profile_l1_pct": 100.0 * relative_l1(aq_profile, snappy_profile),
                    "aqueous_profile_l2_pct": 100.0 * relative_l2(aq_profile, snappy_profile),
                    "snappy_sorbed_inventory": snappy_sorbed_total,
                    "candidate_sorbed_inventory": sorbed_total,
                    "sorbed_inventory_rel_error_pct": 100.0 * sorbed_rel if np.isfinite(sorbed_rel) else np.nan,
                }
            )

    fieldnames = list(rows[0].keys()) if rows else []
    if args.output_csv is not None:
        args.output_csv.parent.mkdir(parents=True, exist_ok=True)
        with args.output_csv.open("w", newline="") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

    for row in rows:
        print(
            f"{row['clip']:>16s} | {row['case']:>13s} | "
            f"area err {row['area_rel_error_pct']:8.3f}% | "
            f"aq L1 {row['aqueous_profile_l1_pct']:8.3f}% | "
            f"aq L2 {row['aqueous_profile_l2_pct']:8.3f}% | "
            f"sorbed inv err {row['sorbed_inventory_rel_error_pct']:8.3f}%"
        )


if __name__ == "__main__":
    main()
