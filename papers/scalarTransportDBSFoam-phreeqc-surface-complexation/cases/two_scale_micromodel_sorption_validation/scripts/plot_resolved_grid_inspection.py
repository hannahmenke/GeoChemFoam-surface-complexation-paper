#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap
from matplotlib.patches import Patch, Rectangle


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    metadata = json.loads(args.metadata.read_text())["resolved_full_reference"]
    nx, ny, nz = (int(value) for value in metadata["shape"])
    if nz != 1:
        raise RuntimeError("This inspection plot expects a one-cell-thick 2D grid.")
    dx_mm = float(metadata["voxel_size_m"]) * 1000.0
    values = np.fromfile(args.raw, dtype=np.uint8)
    if values.size != nx * ny:
        raise RuntimeError(f"Expected {nx * ny} cells, found {values.size} in {args.raw}")
    unique = np.unique(values)
    if not np.array_equal(unique, np.array([0, 255], dtype=np.uint8)):
        raise RuntimeError(f"Grid is not categorical; values are {unique.tolist()}")
    pore = (values.reshape(ny, nx) == 255).astype(np.uint8)

    cmap = ListedColormap(["#292929", "#dff5ff"])
    full_extent = [0.0, nx * dx_mm, 0.0, ny * dx_mm]
    fig = plt.figure(figsize=(15.5, 10.0), constrained_layout=True)
    grid = fig.add_gridspec(2, 3, height_ratios=[1.02, 1.0])
    overview = fig.add_subplot(grid[0, :])
    overview.imshow(
        pore,
        origin="lower",
        extent=full_extent,
        cmap=cmap,
        interpolation="nearest",
        vmin=0,
        vmax=1,
        aspect="equal",
        rasterized=True,
    )
    overview.set_title("Full 5 µm resolved grid — 3600 × 1200 cells (18 × 6 mm)")
    overview.set_xlabel("x [mm]")
    overview.set_ylabel("y [mm]")

    panels = [
        ("Macropore boundary", 360, 560, 500, 700, False),
        ("Boundary at cell scale", 415, 465, 575, 625, True),
        ("Porous matrix at cell scale", 1000, 1050, 575, 625, True),
    ]
    colors = ["#dc3545", "#ff8c00", "#7b2cbf"]
    for panel_index, (title, x0, x1, y0, y1, show_grid) in enumerate(panels):
        ax = fig.add_subplot(grid[1, panel_index])
        crop = pore[y0:y1, x0:x1]
        extent = [x0 * dx_mm, x1 * dx_mm, y0 * dx_mm, y1 * dx_mm]
        ax.imshow(
            crop,
            origin="lower",
            extent=extent,
            cmap=cmap,
            interpolation="nearest",
            vmin=0,
            vmax=1,
            aspect="equal",
        )
        ax.set_title(f"{title}\n{x1 - x0} × {y1 - y0} actual cells")
        ax.set_xlabel("x [mm]")
        ax.set_ylabel("y [mm]")
        if show_grid:
            ax.set_xticks(np.arange(x0, x1 + 1) * dx_mm, minor=True)
            ax.set_yticks(np.arange(y0, y1 + 1) * dx_mm, minor=True)
            ax.grid(which="minor", color="#c84b31", linewidth=0.18, alpha=0.45)
            ax.tick_params(which="minor", bottom=False, left=False)
        overview.add_patch(
            Rectangle(
                (x0 * dx_mm, y0 * dx_mm),
                (x1 - x0) * dx_mm,
                (y1 - y0) * dx_mm,
                fill=False,
                edgecolor=colors[panel_index],
                linewidth=1.5,
            )
        )

    fig.legend(
        handles=[
            Patch(facecolor=cmap(0), label="solid grain (0)"),
            Patch(facecolor=cmap(1), edgecolor="#777777", label="pore (255)"),
        ],
        loc="outside upper right",
        frameon=True,
    )
    fig.suptitle(
        "Human inspection of the categorical 5 µm geometry\n"
        "No averaging or intermediate porosity values; zoom-panel red lines mark individual cells",
        fontsize=15,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=220)
    plt.close(fig)
    print(
        json.dumps(
            {
                "output": str(args.output),
                "shape": [nx, ny],
                "cell_size_um": dx_mm * 1000.0,
                "unique_values": unique.tolist(),
                "porosity": float(pore.mean()),
            },
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
