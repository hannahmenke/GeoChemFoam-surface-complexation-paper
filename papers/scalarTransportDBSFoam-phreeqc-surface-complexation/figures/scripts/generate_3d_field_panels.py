#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib import cm
from matplotlib.colors import Normalize
import numpy as np


def parse_scalar_field(path: Path) -> list[float]:
    text = path.read_text()

    uniform_match = re.search(r"internalField\s+uniform\s+([^\n;]+)\s*;", text)
    if uniform_match:
        return [float(uniform_match.group(1))]

    nonuniform_match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not nonuniform_match:
        raise RuntimeError(f"Unsupported scalar field format in {path}")

    count = int(nonuniform_match.group(1))
    values = [float(item) for item in nonuniform_match.group(2).split()]
    if len(values) != count:
        raise RuntimeError(f"Value count mismatch in {path}")
    return values


def partition_sizes(total: int, n_parts: int) -> tuple[list[int], list[int]]:
    base = total // n_parts
    rem = total % n_parts
    sizes: list[int] = []
    starts: list[int] = []
    start = 0
    for idx in range(n_parts):
        size = base + (1 if idx < rem else 0)
        sizes.append(size)
        starts.append(start)
        start += size
    return sizes, starts


def stitch_parallel_scalar(case_dir: Path, time_name: str, field_name: str) -> tuple[list[float], int, int, int]:
    npx = int((case_dir / "system" / "NPX").read_text().strip())
    npy = int((case_dir / "system" / "NPY").read_text().strip())
    npz = int((case_dir / "system" / "NPZ").read_text().strip())
    nx = int((case_dir / "system" / "Nx1").read_text().strip())
    ny = int((case_dir / "system" / "Ny1").read_text().strip())
    nz = int((case_dir / "system" / "Nz1").read_text().strip())

    size_x, start_x = partition_sizes(nx, npx)
    size_y, start_y = partition_sizes(ny, npy)
    size_z, start_z = partition_sizes(nz, npz)

    global_values = [0.0] * (nx * ny * nz)

    for pz in range(npz):
        for py in range(npy):
            for px in range(npx):
                pid = px + npx * (py + npy * pz)
                local_values = parse_scalar_field(
                    case_dir / f"processor{pid}" / time_name / field_name
                )

                local_nx = size_x[px]
                local_ny = size_y[py]
                local_nz = size_z[pz]
                expected = local_nx * local_ny * local_nz
                if len(local_values) != expected:
                    raise RuntimeError(
                        f"{field_name} length mismatch in processor{pid}: expected {expected}, got {len(local_values)}"
                    )

                idx = 0
                for kk in range(local_nz):
                    for jj in range(local_ny):
                        for ii in range(local_nx):
                            gi = start_x[px] + ii
                            gj = start_y[py] + jj
                            gk = start_z[pz] + kk
                            global_idx = gi + nx * (gj + ny * gk)
                            global_values[global_idx] = local_values[idx]
                            idx += 1

    return global_values, nx, ny, nz


def compute_range(values: list[float], lower_q: float, upper_q: float) -> tuple[float, float]:
    if not values:
        return (0.0, 1.0)

    sorted_values = sorted(values)

    def pick(q: float) -> float:
        pos = max(0, min(len(sorted_values) - 1, int(round(q * (len(sorted_values) - 1)))))
        return sorted_values[pos]

    low = pick(lower_q)
    high = pick(upper_q)
    if high <= low:
        high = max(sorted_values)
    if high <= low:
        high = low + 1.0
    return low, high


def reshape_field(values: list[float], nx: int, ny: int, nz: int) -> np.ndarray:
    array = np.asarray(values, dtype=float)
    return array.reshape((nz, ny, nx), order="C")


def slice_for_normal(values_3d: np.ndarray, normal: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    nz, ny, nx = values_3d.shape
    if normal == "z":
        kk = nz // 2
        xx, yy = np.meshgrid(np.arange(nx + 1), np.arange(ny + 1))
        zz = np.full_like(xx, kk + 0.5, dtype=float)
        cell_values = values_3d[kk, :, :]
    elif normal == "y":
        jj = ny // 2
        xx, zz = np.meshgrid(np.arange(nx + 1), np.arange(nz + 1))
        yy = np.full_like(xx, jj + 0.5, dtype=float)
        cell_values = values_3d[:, jj, :]
    else:
        ii = nx // 2
        yy, zz = np.meshgrid(np.arange(ny + 1), np.arange(nz + 1))
        xx = np.full_like(yy, ii + 0.5, dtype=float)
        cell_values = values_3d[:, :, ii]
        return xx, yy, zz, cell_values

    if normal == "z":
        return xx, yy, zz, cell_values
    if normal == "y":
        return xx, yy, zz, cell_values
    raise RuntimeError("Unreachable")


def draw_box(ax, nx: int, ny: int, nz: int) -> None:
    edges = [
        ((0, 0, 0), (nx, 0, 0)),
        ((0, ny, 0), (nx, ny, 0)),
        ((0, 0, nz), (nx, 0, nz)),
        ((0, ny, nz), (nx, ny, nz)),
        ((0, 0, 0), (0, ny, 0)),
        ((nx, 0, 0), (nx, ny, 0)),
        ((0, 0, nz), (0, ny, nz)),
        ((nx, 0, nz), (nx, ny, nz)),
        ((0, 0, 0), (0, 0, nz)),
        ((nx, 0, 0), (nx, 0, nz)),
        ((0, ny, 0), (0, ny, nz)),
        ((nx, ny, 0), (nx, ny, nz)),
    ]
    for start, end in edges:
        ax.plot(
            [start[0], end[0]],
            [start[1], end[1]],
            [start[2], end[2]],
            color="#555555",
            linewidth=0.9,
            alpha=0.55,
        )


def add_slice_panel(
    ax,
    values_3d: np.ndarray,
    title: str,
    cmap: str,
    clim: tuple[float, float],
    scalar_bar_title: str,
    normal: str,
) -> tuple[object, str]:
    nz, ny, nx = values_3d.shape
    if normal == "x":
        xx, yy, zz, cell_values = slice_for_normal(values_3d, normal)
        plot_x = xx
        plot_y = yy
        plot_z = zz
    elif normal == "y":
        xx, yy, zz, cell_values = slice_for_normal(values_3d, normal)
        plot_x = xx
        plot_y = yy
        plot_z = zz
    else:
        xx, yy, zz, cell_values = slice_for_normal(values_3d, normal)
        plot_x = xx
        plot_y = yy
        plot_z = zz

    norm = Normalize(vmin=clim[0], vmax=clim[1])
    cmap_obj = plt.colormaps[cmap]
    facecolors = cmap_obj(norm(cell_values))
    surface = ax.plot_surface(
        plot_x,
        plot_y,
        plot_z,
        rstride=1,
        cstride=1,
        facecolors=facecolors,
        shade=False,
        linewidth=0,
        antialiased=False,
    )

    draw_box(ax, nx, ny, nz)
    ax.set_title(title, fontsize=11, pad=10)
    ax.set_xlabel("x cell", labelpad=6)
    ax.set_ylabel("y cell", labelpad=6)
    ax.set_zlabel("z cell", labelpad=6)
    ax.view_init(elev=23, azim=-58)
    ax.set_box_aspect((nx, ny, nz))
    ax.xaxis.pane.set_alpha(0.0)
    ax.yaxis.pane.set_alpha(0.0)
    ax.zaxis.pane.set_alpha(0.0)
    ax.grid(False)
    return cm.ScalarMappable(norm=norm, cmap=cmap_obj), scalar_bar_title


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--time-name", required=True)
    parser.add_argument("--aqueous-field", default="Ca+2")
    parser.add_argument("--surface-field", default="Surf_aCa+")
    parser.add_argument("--aqueous-label", default=None,
        help="Panel label for the aqueous field (default: derived from --aqueous-field)")
    parser.add_argument("--surface-label", default=None,
        help="Panel label for the surface field (default: derived from --surface-field)")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="3D DBS Surface Complexation")
    parser.add_argument("--slice-normal", choices=["x", "y", "z"], default="z")
    parser.add_argument("--lower-quantile", type=float, default=0.02)
    parser.add_argument("--upper-quantile", type=float, default=0.98)
    args = parser.parse_args()

    aqueous_values, nx, ny, nz = stitch_parallel_scalar(
        args.case_dir, args.time_name, args.aqueous_field
    )
    surface_values, sx, sy, sz = stitch_parallel_scalar(
        args.case_dir, args.time_name, args.surface_field
    )
    if (sx, sy, sz) != (nx, ny, nz):
        raise RuntimeError("Field meshes do not match")

    aqueous_range = compute_range(aqueous_values, args.lower_quantile, args.upper_quantile)
    surface_range = compute_range(surface_values, args.lower_quantile, args.upper_quantile)

    aqueous_3d = reshape_field(aqueous_values, nx, ny, nz)
    surface_3d = reshape_field(surface_values, nx, ny, nz)

    fig = plt.figure(figsize=(13.5, 6.5), constrained_layout=True)
    ax1 = fig.add_subplot(1, 2, 1, projection="3d")
    ax2 = fig.add_subplot(1, 2, 2, projection="3d")

    aqueous_panel_label = args.aqueous_label if args.aqueous_label is not None else f"Dissolved {args.aqueous_field}"
    surface_panel_label = args.surface_label if args.surface_label is not None else f"Adsorbed ({args.surface_field})"

    sm1, title1 = add_slice_panel(
        ax1,
        aqueous_3d,
        aqueous_panel_label,
        "viridis",
        aqueous_range,
        args.aqueous_field,
        args.slice_normal,
    )

    sm2, title2 = add_slice_panel(
        ax2,
        surface_3d,
        surface_panel_label,
        "magma",
        surface_range,
        args.surface_field,
        args.slice_normal,
    )

    cbar1 = fig.colorbar(sm1, ax=ax1, fraction=0.03, pad=0.04)
    cbar1.set_label(title1)
    cbar2 = fig.colorbar(sm2, ax=ax2, fraction=0.03, pad=0.04)
    cbar2.set_label(title2)

    fig.suptitle(args.title, fontsize=14)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=220, bbox_inches="tight")
    plt.close(fig)


if __name__ == "__main__":
    main()
