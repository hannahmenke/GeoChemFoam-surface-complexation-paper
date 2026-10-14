#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


CASES = [
    {
        "label": "Pe 1",
        "job": "13528073",
        "target_front_time": 145.81044,
        "case_dir": Path(os.environ.get("RESOLVED_CASES_ROOT", "results/archer"))
        / "two_scale_resolved-reference_pe_1_13528073/resolved-reference",
    },
    {
        "label": "Pe 0.3",
        "job": "13528075",
        "target_front_time": 486.031,
        "case_dir": Path(os.environ.get("RESOLVED_CASES_ROOT", "results/archer"))
        / "two_scale_resolved-reference_pe_0.3_13528075/resolved-reference",
    },
    {
        "label": "Pe 0.1",
        "job": "13528074",
        "target_front_time": 1458.10,
        "case_dir": Path(os.environ.get("RESOLVED_CASES_ROOT", "results/archer"))
        / "two_scale_resolved-reference_pe_0.1_13528074/resolved-reference",
    },
]

AQUEOUS_FIELDS = ["Li+", "Na+", "Cl-"]
SURFACE_FIELDS = ["Sor_aLi"]
FIELDS = AQUEOUS_FIELDS + SURFACE_FIELDS
NX = 18000
NY = 6000
LENGTH_MM = 18.0


def read_int(path: Path) -> int:
    return int(path.read_text().strip())


def local_extent(global_n: int, parts: int, index: int) -> tuple[int, int]:
    base = global_n // parts
    rem = global_n % parts
    if index < rem:
        size = base + 1
        start = index * size
    else:
        size = base
        start = rem * (base + 1) + (index - rem) * base
    return start, size


def latest_time(case_dir: Path) -> str:
    candidates: list[tuple[float, str]] = []
    for child in (case_dir / "processor0").iterdir():
        if not child.is_dir():
            continue
        try:
            value = float(child.name)
        except ValueError:
            continue
        if value > 0 and all((child / field).exists() for field in AQUEOUS_FIELDS):
            candidates.append((value, child.name))
    if not candidates:
        raise FileNotFoundError(f"No saved timestep found under {case_dir / 'processor0'}")
    return max(candidates)[1]


def read_internal_scalar(path: Path, expected_count: int) -> np.ndarray:
    text = path.read_text()
    uniform = re.search(r"internalField\s+uniform\s+([0-9.eE+-]+)", text)
    if uniform:
        return np.full(expected_count, float(uniform.group(1)), dtype=float)
    match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\(\s*(.*?)\s*\)\s*;",
        text,
        flags=re.S,
    )
    if not match:
        raise ValueError(f"Could not parse scalar field: {path}")
    count = int(match.group(1))
    data = np.fromstring(match.group(2), sep=" ", dtype=float)
    if data.size != count:
        raise ValueError(f"{path}: expected {count} values, got {data.size}")
    if data.size != expected_count:
        raise ValueError(f"{path}: expected local count {expected_count}, got {data.size}")
    return data


def aggregate_case(case: dict[str, object]) -> dict[str, object]:
    case_dir = Path(case["case_dir"])
    time_name = latest_time(case_dir)
    npx = read_int(case_dir / "system" / "NPX")
    npy = read_int(case_dir / "system" / "NPY")
    npz = read_int(case_dir / "system" / "NPZ")
    if npz != 1:
        raise ValueError(f"Expected NPZ=1 for plotting, got {npz}")

    x = (np.arange(NX) + 0.5) * LENGTH_MM / NX
    denominators = {field: np.zeros(NX, dtype=float) for field in FIELDS}
    numerators = {field: np.zeros(NX, dtype=float) for field in FIELDS}

    for ipy in range(npy):
        _, nyp = local_extent(NY, npy, ipy)
        for ipx in range(npx):
            x_start, nxp = local_extent(NX, npx, ipx)
            rank = ipy * npx + ipx
            cell_count = nxp * nyp
            time_dir = case_dir / f"processor{rank}" / time_name
            eps_path = time_dir / "epsNum"
            if not eps_path.exists():
                eps_path = case_dir / f"processor{rank}" / "0" / "epsNum"
            eps = read_internal_scalar(eps_path, cell_count).reshape((nyp, nxp))
            eps_x = eps.sum(axis=0)

            a_surf_path = time_dir / "aSurf"
            if a_surf_path.exists():
                a_surf = read_internal_scalar(a_surf_path, cell_count).reshape((nyp, nxp))
                a_surf_x = a_surf.sum(axis=0)
            else:
                a_surf = None
                a_surf_x = eps_x

            for field in AQUEOUS_FIELDS:
                values = read_internal_scalar(time_dir / field, cell_count).reshape((nyp, nxp))
                numerators[field][x_start : x_start + nxp] += (values * eps).sum(axis=0)
                denominators[field][x_start : x_start + nxp] += eps_x

            for field in SURFACE_FIELDS:
                values = read_internal_scalar(time_dir / field, cell_count).reshape((nyp, nxp))
                if a_surf is not None:
                    numerators[field][x_start : x_start + nxp] += (values * a_surf).sum(axis=0)
                    denominators[field][x_start : x_start + nxp] += a_surf_x
                else:
                    numerators[field][x_start : x_start + nxp] += (values * eps).sum(axis=0)
                    denominators[field][x_start : x_start + nxp] += eps_x

    profiles = {}
    for field in FIELDS:
        with np.errstate(divide="ignore", invalid="ignore"):
            profile = np.where(denominators[field] > 0, numerators[field] / denominators[field], np.nan)
        profiles[field] = profile

    npz_path = Path("results/quick_plots") / f"resolved_cross_section_{case['job']}.npz"
    np.savez_compressed(npz_path, x_mm=x, **profiles)

    simulated_time = float(time_name)
    expected_x_mm = LENGTH_MM * simulated_time / float(case["target_front_time"])
    return {
        "label": case["label"],
        "job": case["job"],
        "case_dir": str(case_dir),
        "latest_time": time_name,
        "expected_front_x_mm": expected_x_mm,
        "npz": str(npz_path),
        "profiles": {
            field: {
                "min": float(np.nanmin(profile)),
                "max": float(np.nanmax(profile)),
                "mean": float(np.nanmean(profile)),
            }
            for field, profile in profiles.items()
        },
    }


def main() -> None:
    out_dir = Path("results/quick_plots")
    out_dir.mkdir(parents=True, exist_ok=True)

    summaries = []
    loaded_profiles = []
    for case in CASES:
        print(f"Aggregating {case['label']} from {case['case_dir']}", flush=True)
        summary = aggregate_case(case)
        summaries.append(summary)
        data = np.load(summary["npz"])
        loaded_profiles.append((summary, data))

    fig, axes = plt.subplots(len(FIELDS), 1, figsize=(11, 10), sharex=True)
    colors = ["#1b6ca8", "#d95f02", "#1b9e77"]
    for case_index, (summary, data) in enumerate(loaded_profiles):
        x = data["x_mm"]
        label = f"{summary['label']} t={summary['latest_time']}"
        for ax, field in zip(axes, FIELDS):
            ax.plot(x, data[field], lw=1.3, color=colors[case_index], label=label)
            ax.axvline(summary["expected_front_x_mm"], color=colors[case_index], alpha=0.22, lw=1)

    for ax, field in zip(axes, FIELDS):
        ax.set_ylabel(field)
        ax.grid(True, alpha=0.25)
        if field in {"Li+", "Sor_aLi"}:
            ax.ticklabel_format(axis="y", style="sci", scilimits=(-2, 2))
    axes[0].legend(loc="best", fontsize=8)
    axes[-1].set_xlabel("x position along resolved domain (mm), pore/surface weighted cross-section")
    fig.suptitle("Resolved-reference cross-sectional profiles; vertical lines = expected advective front")
    fig.tight_layout(rect=(0, 0, 1, 0.97))

    png = out_dir / "resolved_latest_cross_section_profiles.png"
    json_path = out_dir / "resolved_latest_cross_section_profiles_summary.json"
    fig.savefig(png, dpi=180)
    json_path.write_text(json.dumps(summaries, indent=2) + "\n")
    print(png)
    print(json_path)


if __name__ == "__main__":
    main()
