#!/usr/bin/env python3
from __future__ import annotations

import json
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
        "case_dir": Path(
            "/scratch-nvme/n03/n03/gcfoam_n03/two_scale_resolved-reference_pe_1_13528073/resolved-reference"
        ),
    },
    {
        "label": "Pe 0.3",
        "job": "13528075",
        "case_dir": Path(
            "/scratch-nvme/n03/n03/gcfoam_n03/two_scale_resolved-reference_pe_0.3_13528075/resolved-reference"
        ),
    },
    {
        "label": "Pe 0.1",
        "job": "13528074",
        "case_dir": Path(
            "/scratch-nvme/n03/n03/gcfoam_n03/two_scale_resolved-reference_pe_0.1_13528074/resolved-reference"
        ),
    },
]

FIELDS = ["Li+", "Na+", "Cl-", "Sor_aLi"]
NX = 18000
NY = 6000
X_CELLS = 1000
LENGTH_MM = 18.0
HEIGHT_MM = 6.0


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
        if value > 0 and any((child / field).exists() for field in FIELDS):
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
    if data.size != count or data.size != expected_count:
        raise ValueError(f"{path}: expected {expected_count}/{count} values, got {data.size}")
    return data


def reconstruct_first_x(case_dir: Path, time_name: str, field: str) -> np.ndarray:
    npx = read_int(case_dir / "system" / "NPX")
    npy = read_int(case_dir / "system" / "NPY")
    npz = read_int(case_dir / "system" / "NPZ")
    if npz != 1:
        raise ValueError(f"Expected NPZ=1, got {npz}")

    image = np.full((NY, X_CELLS), np.nan, dtype=np.float32)
    for ipy in range(npy):
        y_start, nyp = local_extent(NY, npy, ipy)
        for ipx in range(npx):
            x_start, nxp = local_extent(NX, npx, ipx)
            x_end = x_start + nxp
            if x_start >= X_CELLS:
                continue
            overlap_start = max(x_start, 0)
            overlap_end = min(x_end, X_CELLS)
            if overlap_start >= overlap_end:
                continue
            rank = ipy * npx + ipx
            values = read_internal_scalar(
                case_dir / f"processor{rank}" / time_name / field,
                expected_count=nxp * nyp,
            ).reshape((nyp, nxp))
            local_start = overlap_start - x_start
            local_end = overlap_end - x_start
            image[y_start : y_start + nyp, overlap_start:overlap_end] = values[
                :, local_start:local_end
            ]
    return image


def main() -> None:
    out_dir = Path("results/quick_plots")
    out_dir.mkdir(parents=True, exist_ok=True)
    summary = []

    for case in CASES:
        case_dir = case["case_dir"]
        time_name = latest_time(case_dir)
        print(f"Plotting {case['label']} at t={time_name}", flush=True)
        fig, axes = plt.subplots(
            len(FIELDS),
            1,
            figsize=(3.8, 16),
            sharex=True,
            constrained_layout=True,
        )
        item = {
            "label": case["label"],
            "job": case["job"],
            "case_dir": str(case_dir),
            "latest_time": time_name,
            "x_cells": X_CELLS,
            "fields": {},
        }
        for ax, field in zip(axes, FIELDS):
            image = reconstruct_first_x(case_dir, time_name, field)
            item["fields"][field] = {
                "min": float(np.nanmin(image)),
                "max": float(np.nanmax(image)),
                "mean": float(np.nanmean(image)),
            }
            if field in {"Li+", "Sor_aLi"}:
                vmax = np.nanpercentile(image, 99.9)
            else:
                vmax = np.nanpercentile(image, 99.5)
            if not np.isfinite(vmax) or vmax <= 0:
                vmax = np.nanmax(image)
            im = ax.imshow(
                image,
                origin="lower",
                aspect="equal",
                extent=[0, X_CELLS * LENGTH_MM / NX, 0, HEIGHT_MM],
                vmin=0,
                vmax=vmax,
                cmap="viridis",
                interpolation="nearest",
            )
            ax.set_ylabel(f"{field}\ny (mm)")
            fig.colorbar(im, ax=ax, fraction=0.022, pad=0.01)
        axes[-1].set_xlabel("x (mm), first 1000 resolved cells")
        fig.suptitle(f"{case['label']} latest actual fields, t={time_name}")
        png = out_dir / f"resolved_first_1000_actual_fields_{case['job']}.png"
        fig.savefig(png, dpi=180)
        plt.close(fig)
        item["png"] = str(png)
        summary.append(item)

    summary_path = out_dir / "resolved_first_1000_actual_fields_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(summary_path)


if __name__ == "__main__":
    main()
