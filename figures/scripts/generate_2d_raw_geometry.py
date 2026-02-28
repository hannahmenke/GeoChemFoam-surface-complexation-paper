#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import tarfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap


def parse_size(metadata_path: Path) -> tuple[int, int, int]:
    text = metadata_path.read_text()
    match = re.search(r"Size:\s+(\d+)\s+(\d+)\s+(\d+)", text)
    if not match:
        raise RuntimeError(f"Could not parse size from {metadata_path}")
    return tuple(int(match.group(index)) for index in range(1, 4))


def read_raw_from_tar(path: Path) -> bytes:
    with tarfile.open(path, "r:gz") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        if not members:
            raise RuntimeError(f"No regular file found in {path}")
        with archive.extractfile(members[0]) as handle:
            if handle is None:
                raise RuntimeError(f"Could not extract {members[0].name} from {path}")
            return handle.read()


def parse_scalar_field(path: Path) -> np.ndarray:
    text = path.read_text()

    uniform_match = re.search(r"internalField\s+uniform\s+([^\n;]+)\s*;", text)
    if uniform_match:
        return np.array([float(uniform_match.group(1))], dtype=float)

    nonuniform_match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not nonuniform_match:
        raise RuntimeError(f"Unsupported scalar field format in {path}")

    count = int(nonuniform_match.group(1))
    values = np.array([float(item) for item in nonuniform_match.group(2).split()], dtype=float)
    if values.size != count:
        raise RuntimeError(f"Value count mismatch in {path}")
    return values


def local_partition_sizes(n_total: int, n_proc: int) -> tuple[list[int], list[int]]:
    base = n_total // n_proc
    rem = n_total % n_proc
    sizes = []
    starts = []
    start = 0
    for idx in range(n_proc):
        size = base + (1 if idx < rem else 0)
        sizes.append(size)
        starts.append(start)
        start += size
    return sizes, starts


def assemble_parallel_field(
    case_dir: Path, time_name: str, field_name: str, coarse_nx: int, coarse_ny: int, npx: int, npy: int
) -> np.ndarray:
    grid = np.zeros((coarse_ny, coarse_nx), dtype=float)
    x_sizes, x_starts = local_partition_sizes(coarse_nx, npx)
    y_sizes, y_starts = local_partition_sizes(coarse_ny, npy)

    for rank in range(npx * npy):
        ipy = rank // npx
        ipx = rank % npx
        field_path = case_dir / f"processor{rank}" / time_name / field_name
        values = parse_scalar_field(field_path)
        local = values.reshape((y_sizes[ipy], x_sizes[ipx]))
        ys = y_starts[ipy]
        ye = ys + y_sizes[ipy]
        xs = x_starts[ipx]
        xe = xs + x_sizes[ipx]
        grid[ys:ye, xs:xe] = local

    return grid


def downsample_labels(image: np.ndarray, coarse_ny: int, coarse_nx: int) -> np.ndarray:
    ny, nx = image.shape
    if ny % coarse_ny or nx % coarse_nx:
        raise RuntimeError(
            f"Cannot downsample {image.shape} cleanly to {(coarse_ny, coarse_nx)}"
        )

    block_y = ny // coarse_ny
    block_x = nx // coarse_nx
    coarse = np.empty((coarse_ny, coarse_nx), dtype=np.uint8)

    for row in range(coarse_ny):
        y0 = row * block_y
        y1 = (row + 1) * block_y
        for col in range(coarse_nx):
            x0 = col * block_x
            x1 = (col + 1) * block_x
            block = image[y0:y1, x0:x1]
            values, counts = np.unique(block, return_counts=True)
            coarse[row, col] = values[np.argmax(counts)]

    return coarse


def extent_mm(coarse_nx: int, coarse_ny: int, res_m: float, raw_nx: int, raw_ny: int) -> list[float]:
    width_m = raw_nx * res_m
    height_m = raw_ny * res_m
    return [0.0, 1.0e3 * width_m, 0.0, 1.0e3 * height_m]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-tar", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="4StraightFractures")
    parser.add_argument("--ca-field", type=Path)
    parser.add_argument("--surf-field", type=Path)
    parser.add_argument("--parallel-case", type=Path)
    parser.add_argument("--time-name")
    parser.add_argument("--npx", type=int, default=1)
    parser.add_argument("--npy", type=int, default=1)
    parser.add_argument("--coarse-nx", type=int, default=250)
    parser.add_argument("--coarse-ny", type=int, default=250)
    parser.add_argument("--res-m", type=float, default=1.0e-4)
    parser.add_argument("--ca-inlet", type=float, default=2.0e-9)
    parser.add_argument("--time-label", default="t = 50")
    args = parser.parse_args()

    raw_nx, raw_ny, raw_nz = parse_size(args.metadata)
    if raw_nz != 1:
        raise RuntimeError("This script expects a 2D single-slice image")

    raw = read_raw_from_tar(args.raw_tar)
    array = np.frombuffer(raw, dtype=np.uint8)
    expected = raw_nx * raw_ny * raw_nz
    if array.size != expected:
        raise RuntimeError(
            f"Voxel count mismatch for {args.raw_tar}: expected {expected}, got {array.size}"
        )

    image = array.reshape((raw_nz, raw_ny, raw_nx))[0, :, :]
    coarse_labels = downsample_labels(image, args.coarse_ny, args.coarse_nx)
    mm_extent = extent_mm(args.coarse_nx, args.coarse_ny, args.res_m, raw_nx, raw_ny)

    geometry_cmap = ListedColormap(["#c94f4f", "#4f8fd6", "#ffffff"])
    geometry_norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], geometry_cmap.N)

    if args.ca_field and args.surf_field:
        ca_values = parse_scalar_field(args.ca_field).reshape((args.coarse_ny, args.coarse_nx))
        surf_values = parse_scalar_field(args.surf_field).reshape((args.coarse_ny, args.coarse_nx))
    elif args.parallel_case and args.time_name:
        ca_values = assemble_parallel_field(
            args.parallel_case, args.time_name, "Ca+2", args.coarse_nx, args.coarse_ny, args.npx, args.npy
        )
        surf_values = assemble_parallel_field(
            args.parallel_case, args.time_name, "Surf_aCa+", args.coarse_nx, args.coarse_ny, args.npx, args.npy
        )
    else:
        ca_values = None
        surf_values = None

    if ca_values is not None and surf_values is not None:
        ca_norm = ca_values / max(args.ca_inlet, 1.0e-30)
        positive_surf = surf_values[surf_values > 0.0]
        surf_scale = (
            np.percentile(positive_surf, 99.0)
            if positive_surf.size
            else 1.0
        )
        surf_scale = max(float(surf_scale), 1.0e-30)
        surf_norm = np.clip(surf_values / surf_scale, 0.0, 1.0)

        fig, axes = plt.subplots(1, 3, figsize=(13.2, 4.4), sharex=True, sharey=True)

        mesh = axes[0].imshow(
            coarse_labels,
            cmap=geometry_cmap,
            norm=geometry_norm,
            origin="lower",
            interpolation="nearest",
            extent=mm_extent,
        )
        axes[0].set_title("Geometry")
        axes[0].set_xlabel("x [mm]")
        axes[0].set_ylabel("y [mm]")
        cbar0 = fig.colorbar(mesh, ax=axes[0], ticks=[0, 1, 2], fraction=0.046, pad=0.04)
        cbar0.ax.set_yticklabels(["solid", "matrix", "pore"])

        axes[1].imshow(
            coarse_labels,
            cmap=geometry_cmap,
            norm=geometry_norm,
            origin="lower",
            interpolation="nearest",
            extent=mm_extent,
            alpha=0.20,
        )
        field1 = axes[1].imshow(
            ca_norm,
            cmap="cividis",
            origin="lower",
            interpolation="nearest",
            extent=mm_extent,
            vmin=0.0,
            vmax=1.0,
        )
        axes[1].contour(
            coarse_labels,
            levels=[1.5],
            colors="white",
            linewidths=0.35,
            origin="lower",
            extent=mm_extent,
        )
        axes[1].set_title(f"Ca$^{{2+}}$ / C$_{{in}}$ ({args.time_label})")
        axes[1].set_xlabel("x [mm]")
        cbar1 = fig.colorbar(field1, ax=axes[1], fraction=0.046, pad=0.04)
        cbar1.set_label("Normalized Ca$^{2+}$")

        axes[2].imshow(
            coarse_labels,
            cmap=geometry_cmap,
            norm=geometry_norm,
            origin="lower",
            interpolation="nearest",
            extent=mm_extent,
            alpha=0.20,
        )
        field2 = axes[2].imshow(
            surf_norm,
            cmap="magma",
            origin="lower",
            interpolation="nearest",
            extent=mm_extent,
            vmin=0.0,
            vmax=1.0,
        )
        axes[2].contour(
            coarse_labels,
            levels=[1.5],
            colors="white",
            linewidths=0.35,
            origin="lower",
            extent=mm_extent,
        )
        axes[2].set_title(f"Surf$_a$Ca$^+$ / P99 ({args.time_label})")
        axes[2].set_xlabel("x [mm]")
        cbar2 = fig.colorbar(field2, ax=axes[2], fraction=0.046, pad=0.04)
        cbar2.set_label("Normalized surface loading")

        fig.suptitle(args.title)
    else:
        fig, ax = plt.subplots(figsize=(6.2, 6.2))
        mesh = ax.imshow(
            image,
            cmap=geometry_cmap,
            norm=geometry_norm,
            origin="lower",
            interpolation="nearest",
        )
        ax.set_title(args.title)
        ax.set_xlabel("x voxel")
        ax.set_ylabel("y voxel")

        colorbar = fig.colorbar(mesh, ax=ax, ticks=[0, 1, 2], fraction=0.046, pad=0.04)
        colorbar.ax.set_yticklabels(["solid", "matrix", "pore"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95) if args.ca_field and args.surf_field else None)
    fig.savefig(args.output, dpi=220)


if __name__ == "__main__":
    main()
