#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import tarfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap, LogNorm


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


def assemble_parallel_field(case_dir: Path, time_name: str, field_name: str) -> np.ndarray:
    coarse_nx = int((case_dir / "system" / "Nx1").read_text().strip())
    coarse_ny = int((case_dir / "system" / "Ny1").read_text().strip())
    npx = int((case_dir / "system" / "NPX").read_text().strip())
    npy = int((case_dir / "system" / "NPY").read_text().strip())

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


def read_thresholded_crop(raw_tar: Path, x_min: int, x_max: int, y_min: int, y_max: int, z_layer: int, threshold: int) -> np.ndarray:
    with tarfile.open(raw_tar, "r:gz") as archive:
        member = next(member for member in archive.getmembers() if member.isfile())
        with archive.extractfile(member) as handle:
            if handle is None:
                raise RuntimeError(f"Could not extract {member.name}")
            raw = handle.read()
    array = np.frombuffer(raw, dtype=np.uint8).reshape((10, 2000, 2000))
    image = array[z_layer, y_min:y_max, x_min:x_max]
    return np.where(image > threshold, 255, 0).astype(np.uint8)


def downsample_labels(image: np.ndarray, coarse_ny: int, coarse_nx: int) -> np.ndarray:
    ny, nx = image.shape
    qy = ny // coarse_ny
    qx = nx // coarse_nx
    coarse = np.empty((coarse_ny, coarse_nx), dtype=np.uint8)
    for j in range(coarse_ny):
        for i in range(coarse_nx):
            block = image[j * qy:(j + 1) * qy, i * qx:(i + 1) * qx]
            values, counts = np.unique(block, return_counts=True)
            coarse[j, i] = values[np.argmax(counts)]
    return coarse


def interface_asurf_from_binary(image: np.ndarray, coarse_ny: int, coarse_nx: int, res_m: float) -> np.ndarray:
    ny, nx = image.shape
    qy = ny // coarse_ny
    qx = nx // coarse_nx
    is_grain = image == 0
    counts = np.zeros_like(image, dtype=np.uint8)
    diff_x = is_grain[:, 1:] != is_grain[:, :-1]
    counts[:, 1:] += diff_x
    counts[:, :-1] += diff_x
    diff_y = is_grain[1:, :] != is_grain[:-1, :]
    counts[1:, :] += diff_y
    counts[:-1, :] += diff_y

    field = np.zeros((coarse_ny, coarse_nx), dtype=float)
    coeff = 0.5 / (qx * qy * res_m)
    for j in range(coarse_ny):
        for i in range(coarse_nx):
            block = counts[j * qy:(j + 1) * qy, i * qx:(i + 1) * qx]
            field[j, i] = block.sum() * coeff
    return field


def extent_mm(width_px: int, height_px: int, res_m: float) -> list[float]:
    return [0.0, width_px * res_m * 1.0e3, 0.0, height_px * res_m * 1.0e3]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--raw-tar", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--time", default="1000")
    parser.add_argument("--threshold", type=int, default=120)
    parser.add_argument("--x-min", type=int, default=700)
    parser.add_argument("--x-max", type=int, default=1300)
    parser.add_argument("--y-min", type=int, default=700)
    parser.add_argument("--y-max", type=int, default=1300)
    parser.add_argument("--z-layer", type=int, default=1)
    parser.add_argument("--res-m", type=float, default=3.0e-5)
    parser.add_argument("--intrinsic-asurf", type=float, default=1.0e5)
    parser.add_argument("--vmin", type=float, default=1.0e-10)
    parser.add_argument("--vmax", type=float, default=1.0e-5)
    args = parser.parse_args()

    coarse_nx = int((args.case_dir / "system" / "Nx1").read_text().strip())
    coarse_ny = int((args.case_dir / "system" / "Ny1").read_text().strip())

    binary = read_thresholded_crop(
        args.raw_tar, args.x_min, args.x_max, args.y_min, args.y_max, args.z_layer, args.threshold
    )
    coarse_binary = downsample_labels(binary, coarse_ny, coarse_nx)
    interface_asurf = interface_asurf_from_binary(binary, coarse_ny, coarse_nx, args.res_m)
    surf = assemble_parallel_field(args.case_dir, args.time, "Surf_aSr+")
    runtime_asurf = assemble_parallel_field(args.case_dir, "0", "aSurf")
    intrinsic_asurf = np.clip(runtime_asurf - interface_asurf, 0.0, None)

    interface_share = np.divide(
        interface_asurf,
        runtime_asurf,
        out=np.zeros_like(interface_asurf),
        where=runtime_asurf > 0.0,
    )
    intrinsic_share = np.divide(
        intrinsic_asurf,
        runtime_asurf,
        out=np.zeros_like(intrinsic_asurf),
        where=runtime_asurf > 0.0,
    )

    total_bulk = surf * runtime_asurf
    interface_bulk = surf * runtime_asurf * interface_share
    intrinsic_bulk = surf * runtime_asurf * intrinsic_share

    total_bulk = np.where(runtime_asurf > 0.0, total_bulk, np.nan)
    interface_bulk = np.where(interface_asurf > 0.0, interface_bulk, np.nan)
    intrinsic_bulk = np.where(intrinsic_asurf > 0.0, intrinsic_bulk, np.nan)

    mm_extent = extent_mm(args.x_max - args.x_min, args.y_max - args.y_min, args.res_m)
    geom = np.where(coarse_binary == 255, 0, 1)
    geom_cmap = ListedColormap(["#111111", "#9a9a9a"])
    geom_norm = BoundaryNorm([-0.5, 0.5, 1.5], geom_cmap.N)
    surf_cmap = plt.get_cmap("magma").copy()
    surf_cmap.set_bad((1.0, 1.0, 1.0, 0.0))

    fig, axes = plt.subplots(1, 4, figsize=(15.5, 4.2), sharex=True, sharey=True)

    g = axes[0].imshow(
        geom,
        cmap=geom_cmap,
        norm=geom_norm,
        origin="lower",
        interpolation="nearest",
        extent=mm_extent,
    )
    axes[0].set_title("Geometry")
    axes[0].set_xlabel("x [mm]")
    axes[0].set_ylabel("y [mm]")

    norm = LogNorm(vmin=args.vmin, vmax=args.vmax)
    h1 = axes[1].imshow(total_bulk, cmap=surf_cmap, norm=norm, origin="lower", interpolation="nearest", extent=mm_extent)
    h2 = axes[2].imshow(interface_bulk, cmap=surf_cmap, norm=norm, origin="lower", interpolation="nearest", extent=mm_extent)
    h3 = axes[3].imshow(intrinsic_bulk, cmap=surf_cmap, norm=norm, origin="lower", interpolation="nearest", extent=mm_extent)

    axes[1].set_title("Total $a_{surf} \\, Surf_aSr+$")
    axes[2].set_title("Interface-only attributed")
    axes[3].set_title("Intrinsic-only attributed")
    for ax in axes[1:]:
        ax.set_xlabel("x [mm]")

    c0 = fig.colorbar(g, ax=axes[0], fraction=0.046, pad=0.03, ticks=[0, 1])
    c0.ax.set_yticklabels(["pore", "micropore"])
    for ax, handle in zip(axes[1:], [h1, h2, h3]):
        fig.colorbar(handle, ax=ax, fraction=0.046, pad=0.03)

    interface_total = np.nansum(interface_bulk)
    intrinsic_total = np.nansum(intrinsic_bulk)
    total = np.nansum(total_bulk)
    iface_frac = interface_total / total if total > 0 else 0.0
    intr_frac = intrinsic_total / total if total > 0 else 0.0

    fig.suptitle(
        f"Microporous HM12 case at t = {args.time} s | interface share = {iface_frac:.2%}, intrinsic share = {intr_frac:.2%}",
        y=1.02,
    )
    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=220, bbox_inches="tight")


if __name__ == "__main__":
    main()
