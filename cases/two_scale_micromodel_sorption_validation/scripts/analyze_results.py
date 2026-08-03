#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import re
from pathlib import Path

import numpy as np


SCALAR_RE = re.compile(
    r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
    re.S,
)
UNIFORM_RE = re.compile(r"internalField\s+uniform\s+([^\s;]+)\s*;")


def read_int(path: Path) -> int:
    return int(path.read_text().strip())


def partition_sizes(n_cells: int, n_parts: int) -> list[int]:
    base, rem = divmod(n_cells, n_parts)
    return [base + (1 if i < rem else 0) for i in range(n_parts)]


def read_scalar_values(path: Path, expected_count: int) -> np.ndarray:
    text = path.read_text()
    uniform = UNIFORM_RE.search(text)
    if uniform:
        return np.full(expected_count, float(uniform.group(1)))

    match = SCALAR_RE.search(text)
    if not match:
        raise RuntimeError(f"Could not parse scalar internalField in {path}")
    count = int(match.group(1))
    values = np.fromstring(match.group(2), sep=" ")
    if len(values) != count:
        raise RuntimeError(f"Field length mismatch in {path}: got {len(values)}, expected {count}")
    if expected_count and count != expected_count:
        raise RuntimeError(f"Unexpected field length in {path}: got {count}, expected {expected_count}")
    return values


def assemble_field(case_dir: Path, time_name: str, field_name: str, fallback_time: str | None = None) -> np.ndarray:
    nx = read_int(case_dir / "system" / "Nx1")
    ny = read_int(case_dir / "system" / "Ny1")
    npx = read_int(case_dir / "system" / "NPX")
    npy = read_int(case_dir / "system" / "NPY")
    x_sizes = partition_sizes(nx, npx)
    y_sizes = partition_sizes(ny, npy)
    x_offsets = np.cumsum([0] + x_sizes[:-1])
    y_offsets = np.cumsum([0] + y_sizes[:-1])

    out = np.zeros((ny, nx), dtype=float)
    for py, y_size in enumerate(y_sizes):
        for px, x_size in enumerate(x_sizes):
            rank = py * npx + px
            proc = case_dir / f"processor{rank}"
            field_path = proc / time_name / field_name
            if not field_path.exists() and fallback_time is not None:
                field_path = proc / fallback_time / field_name
            if not field_path.exists():
                raise FileNotFoundError(field_path)
            values = read_scalar_values(field_path, x_size * y_size).reshape((y_size, x_size))
            y0, x0 = y_offsets[py], x_offsets[px]
            out[y0 : y0 + y_size, x0 : x0 + x_size] = values
    return out


def read_resolution(case_dir: Path) -> float:
    cell_size = case_dir / "system" / "cellSize"
    if cell_size.exists():
        return float(cell_size.read_text().strip())
    text = (case_dir / "createMesh.sh").read_text()
    match = re.search(r"^res=([0-9.eE+-]+)", text, re.M)
    if not match:
        raise RuntimeError(f"Could not find res= in {case_dir / 'createMesh.sh'}")
    return float(match.group(1))


def latest_numeric_time(case_dir: Path) -> str:
    times: list[tuple[float, str]] = []
    for path in (case_dir / "processor0").iterdir():
        if path.is_dir():
            try:
                times.append((float(path.name), path.name))
            except ValueError:
                pass
    if not times:
        raise RuntimeError(f"No processor0 time directories in {case_dir}")
    return max(times)[1]


def profile_to_bins(values: np.ndarray, weights: np.ndarray, n_bins: int) -> np.ndarray:
    ny, nx = values.shape
    x_bins = np.floor(np.arange(nx) * n_bins / nx).astype(int)
    x_bins = np.clip(x_bins, 0, n_bins - 1)
    out = np.zeros(n_bins, dtype=float)
    weighted = values * weights
    for x in range(nx):
        out[x_bins[x]] += float(np.sum(weighted[:, x]))
    return out


def cumulative_position(profile: np.ndarray, length_m: float, fraction: float) -> float:
    total = float(np.sum(profile))
    if total <= 0:
        return math.nan
    cumulative = np.cumsum(profile) / total
    idx = int(np.searchsorted(cumulative, fraction, side="left"))
    idx = min(max(idx, 0), len(profile) - 1)
    return (idx + 0.5) * length_m / len(profile)


def case_metrics(case_dir: Path, time_name: str, n_profile_bins: int) -> dict[str, object]:
    dx = read_resolution(case_dir)
    dy = dx
    depth = dx
    cell_volume = dx * dy * depth

    li = assemble_field(case_dir, time_name, "Li+")
    na = assemble_field(case_dir, time_name, "Na+")
    theta = assemble_field(case_dir, time_name, "theta")
    asurf = assemble_field(case_dir, time_name, "aSurf", fallback_time="0")
    try:
        asurf_intrinsic = assemble_field(case_dir, time_name, "aSurfIntrinsic", fallback_time="0")
    except FileNotFoundError:
        asurf_intrinsic = np.zeros_like(asurf)
    sor_li = assemble_field(case_dir, time_name, "Sor_aLi")
    sor_na = assemble_field(case_dir, time_name, "Sor_aNa")

    total_asurf = asurf + asurf_intrinsic
    bulk_volume = li.size * cell_volume
    pore_volume = float(np.sum(theta) * cell_volume)
    reactive_area = float(np.sum(total_asurf) * cell_volume)
    aqueous_li_inventory = float(np.sum(li * theta) * cell_volume)
    aqueous_na_inventory = float(np.sum(na * theta) * cell_volume)
    sorbed_li_inventory = float(np.sum(sor_li * total_asurf) * cell_volume)
    sorbed_na_inventory = float(np.sum(sor_na * total_asurf) * cell_volume)

    aqueous_li_profile = profile_to_bins(li, theta * cell_volume, n_profile_bins)
    sorbed_li_profile = profile_to_bins(sor_li, total_asurf * cell_volume, n_profile_bins)
    pore_profile = profile_to_bins(np.ones_like(theta), theta * cell_volume, n_profile_bins)
    area_profile = profile_to_bins(np.ones_like(total_asurf), total_asurf * cell_volume, n_profile_bins)

    length_m = li.shape[1] * dx
    return {
        "time": float(time_name),
        "nx": int(li.shape[1]),
        "ny": int(li.shape[0]),
        "cell_size_m": dx,
        "bulk_volume_m3": bulk_volume,
        "pore_volume_m3": pore_volume,
        "porosity_volume_weighted": pore_volume / bulk_volume,
        "reactive_area_m2": reactive_area,
        "reactive_area_per_bulk_volume_m-1": reactive_area / bulk_volume,
        "aqueous_li_inventory_mol": aqueous_li_inventory,
        "aqueous_li_per_bulk_volume_mol_m-3": aqueous_li_inventory / bulk_volume,
        "aqueous_li_pore_mean_mol_m-3": aqueous_li_inventory / pore_volume,
        "aqueous_na_inventory_mol": aqueous_na_inventory,
        "aqueous_na_pore_mean_mol_m-3": aqueous_na_inventory / pore_volume,
        "sorbed_li_inventory_mol": sorbed_li_inventory,
        "sorbed_li_per_bulk_volume_mol_m-3": sorbed_li_inventory / bulk_volume,
        "sorbed_li_per_area_mol_m-2": sorbed_li_inventory / reactive_area if reactive_area else math.nan,
        "sorbed_na_inventory_mol": sorbed_na_inventory,
        "sorbed_na_per_area_mol_m-2": sorbed_na_inventory / reactive_area if reactive_area else math.nan,
        "total_li_inventory_mol": aqueous_li_inventory + sorbed_li_inventory,
        "li_sorbed_fraction": sorbed_li_inventory / (aqueous_li_inventory + sorbed_li_inventory),
        "aqueous_li_front_x50_m": cumulative_position(aqueous_li_profile, length_m, 0.5),
        "sorbed_li_front_x50_m": cumulative_position(sorbed_li_profile, length_m, 0.5),
        "profiles": {
            "aqueous_li_inventory_mol": aqueous_li_profile,
            "sorbed_li_inventory_mol": sorbed_li_profile,
            "pore_volume_m3": pore_profile,
            "reactive_area_m2": area_profile,
        },
    }


def relative_difference(value: float, reference: float) -> float:
    return (value - reference) / reference if reference else math.nan


def normalized_l1(candidate: np.ndarray, reference: np.ndarray) -> float:
    ref_sum = float(np.sum(reference))
    cand_sum = float(np.sum(candidate))
    if ref_sum <= 0 or cand_sum <= 0:
        return math.nan
    return float(np.sum(np.abs(candidate / cand_sum - reference / ref_sum)))


def serializable(metrics: dict[str, object]) -> dict[str, object]:
    out: dict[str, object] = {}
    for key, value in metrics.items():
        if key == "profiles":
            continue
        if isinstance(value, np.ndarray):
            out[key] = value.tolist()
        else:
            out[key] = value
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--results-dir", type=Path, default=None)
    parser.add_argument("--profile-bins", type=int, default=100)
    args = parser.parse_args()

    case_root = args.case_root
    results_dir = args.results_dir or case_root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)

    case_names = ["resolved-reference", "dbs-upscaled"]
    metrics = {}
    for case_name in case_names:
        case_dir = case_root / case_name
        time_name = latest_numeric_time(case_dir)
        metrics[case_name] = case_metrics(case_dir, time_name, args.profile_bins)

    reference = metrics["resolved-reference"]
    candidate = metrics["dbs-upscaled"]
    comparison_keys = [
        "porosity_volume_weighted",
        "reactive_area_per_bulk_volume_m-1",
        "aqueous_li_per_bulk_volume_mol_m-3",
        "aqueous_li_pore_mean_mol_m-3",
        "sorbed_li_per_bulk_volume_mol_m-3",
        "sorbed_li_per_area_mol_m-2",
        "li_sorbed_fraction",
        "aqueous_li_front_x50_m",
        "sorbed_li_front_x50_m",
    ]
    comparison = {
        f"{key}_relative_difference": relative_difference(float(candidate[key]), float(reference[key]))
        for key in comparison_keys
    }
    comparison["aqueous_li_profile_normalized_l1"] = normalized_l1(
        candidate["profiles"]["aqueous_li_inventory_mol"],
        reference["profiles"]["aqueous_li_inventory_mol"],
    )
    comparison["sorbed_li_profile_normalized_l1"] = normalized_l1(
        candidate["profiles"]["sorbed_li_inventory_mol"],
        reference["profiles"]["sorbed_li_inventory_mol"],
    )

    summary = {
        "cases": {case_name: serializable(case_metrics) for case_name, case_metrics in metrics.items()},
        "dbs_vs_resolved": comparison,
    }
    (results_dir / "analysis_summary.json").write_text(json.dumps(summary, indent=2) + "\n")

    with (results_dir / "analysis_summary.csv").open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(["case", "metric", "value"])
        for case_name in case_names:
            for key, value in serializable(metrics[case_name]).items():
                writer.writerow([case_name, key, value])
        for key, value in comparison.items():
            writer.writerow(["dbs_vs_resolved", key, value])

    profile_path = results_dir / "analysis_profiles.csv"
    with profile_path.open("w", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(
            [
                "bin",
                "x_mid_fraction",
                "case",
                "aqueous_li_inventory_mol",
                "aqueous_li_inventory_fraction",
                "sorbed_li_inventory_mol",
                "sorbed_li_inventory_fraction",
                "pore_volume_m3",
                "reactive_area_m2",
            ]
        )
        for case_name in case_names:
            profiles = metrics[case_name]["profiles"]
            aq = profiles["aqueous_li_inventory_mol"]
            sor = profiles["sorbed_li_inventory_mol"]
            aq_total = float(np.sum(aq))
            sor_total = float(np.sum(sor))
            for i in range(args.profile_bins):
                writer.writerow(
                    [
                        i,
                        (i + 0.5) / args.profile_bins,
                        case_name,
                        aq[i],
                        aq[i] / aq_total if aq_total else math.nan,
                        sor[i],
                        sor[i] / sor_total if sor_total else math.nan,
                        profiles["pore_volume_m3"][i],
                        profiles["reactive_area_m2"][i],
                    ]
                )

    print(f"Wrote {results_dir / 'analysis_summary.json'}")
    print(f"Wrote {results_dir / 'analysis_summary.csv'}")
    print(f"Wrote {profile_path}")
    print(json.dumps(summary["dbs_vs_resolved"], indent=2))


if __name__ == "__main__":
    main()
