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


CASE_ROOT = Path(
    os.environ.get(
        "RESOLVED_GEOMETRY_ROOT",
        "results/archer/two_scale_resolved-reference_pe_1_13528073",
    )
)
CASE_DIR = CASE_ROOT / "resolved-reference"
RAW_PATH = CASE_ROOT / "shared" / "resolved_full_reference.raw"
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


def reconstruct_first_x(field: str) -> np.ndarray:
    npx = read_int(CASE_DIR / "system" / "NPX")
    npy = read_int(CASE_DIR / "system" / "NPY")
    image = np.full((NY, X_CELLS), np.nan, dtype=np.float32)
    for ipy in range(npy):
        y_start, nyp = local_extent(NY, npy, ipy)
        for ipx in range(npx):
            x_start, nxp = local_extent(NX, npx, ipx)
            if x_start >= X_CELLS:
                continue
            overlap_start = max(x_start, 0)
            overlap_end = min(x_start + nxp, X_CELLS)
            if overlap_start >= overlap_end:
                continue
            rank = ipy * npx + ipx
            values = read_internal_scalar(
                CASE_DIR / f"processor{rank}" / "0" / field,
                expected_count=nxp * nyp,
            ).reshape((nyp, nxp))
            local_start = overlap_start - x_start
            local_end = overlap_end - x_start
            image[y_start : y_start + nyp, overlap_start:overlap_end] = values[
                :, local_start:local_end
            ]
    return image


def read_raw_first_x() -> np.ndarray:
    raw = np.memmap(RAW_PATH, dtype=np.uint8, mode="r", shape=(NY, NX))
    return np.asarray(raw[:, :X_CELLS])


def main() -> None:
    out_dir = Path("results/quick_plots")
    out_dir.mkdir(parents=True, exist_ok=True)

    raw = read_raw_first_x()
    eps = reconstruct_first_x("eps")
    eps_num = reconstruct_first_x("epsNum")

    fig, axes = plt.subplots(3, 1, figsize=(3.8, 12), sharex=True, constrained_layout=True)
    images = [
        ("source raw resolved_full_reference", raw, "gray", 0, 255),
        ("processor field eps", eps, "viridis", 0, 1),
        ("processor field epsNum", eps_num, "viridis", 0, 1),
    ]
    for ax, (title, image, cmap, vmin, vmax) in zip(axes, images):
        im = ax.imshow(
            image,
            origin="lower",
            aspect="equal",
            extent=[0, X_CELLS * LENGTH_MM / NX, 0, HEIGHT_MM],
            interpolation="nearest",
            cmap=cmap,
            vmin=vmin,
            vmax=vmax,
        )
        ax.set_title(title)
        ax.set_ylabel("y (mm)")
        fig.colorbar(im, ax=ax, fraction=0.025, pad=0.01)
    axes[-1].set_xlabel("x (mm), first 1000 resolved cells")

    png = out_dir / "resolved_first_1000_geometry_check.png"
    summary = out_dir / "resolved_first_1000_geometry_check_summary.json"
    fig.savefig(png, dpi=180)
    summary.write_text(
        json.dumps(
            {
                "raw_path": str(RAW_PATH),
                "case_dir": str(CASE_DIR),
                "raw_unique": sorted(int(v) for v in np.unique(raw)),
                "eps_min": float(np.nanmin(eps)),
                "eps_max": float(np.nanmax(eps)),
                "eps_num_min": float(np.nanmin(eps_num)),
                "eps_num_max": float(np.nanmax(eps_num)),
                "png": str(png),
            },
            indent=2,
        )
        + "\n"
    )
    print(png)
    print(summary)


if __name__ == "__main__":
    main()
