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


def read_thresholded_hm12(raw_tar: Path, x_min: int, x_max: int, y_min: int, y_max: int, z_layer: int, threshold: int) -> np.ndarray:
    with tarfile.open(raw_tar, "r:gz") as archive:
        member = next(member for member in archive.getmembers() if member.isfile())
        with archive.extractfile(member) as handle:
            if handle is None:
                raise RuntimeError(f"Could not extract {member.name} from {raw_tar}")
            raw = handle.read()

    nx, ny, nz = 2000, 2000, 10
    array = np.frombuffer(raw, dtype=np.uint8).reshape((nz, ny, nx))
    image = array[z_layer, y_min:y_max, x_min:x_max]
    return np.where(image > threshold, 255, 0).astype(np.uint8)


def downsample_labels(image: np.ndarray, coarse_ny: int, coarse_nx: int) -> np.ndarray:
    ny, nx = image.shape
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


def extent_mm(nx: int, ny: int, res_m: float) -> list[float]:
    return [0.0, nx * res_m * 1.0e3, 0.0, ny * res_m * 1.0e3]


def geometry_for_case(binary_labels: np.ndarray, mode: str) -> np.ndarray:
    if mode == "solid":
        return np.where(binary_labels == 255, 1, 0)
    if mode == "micropore":
        return np.where(binary_labels == 255, 1, 2)
    raise ValueError(mode)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--solid-case", type=Path, required=True)
    parser.add_argument("--micropore-case", type=Path, required=True)
    parser.add_argument("--raw-tar", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--times", nargs="+", default=["10", "20", "40", "100"])
    parser.add_argument("--threshold", type=int, default=120)
    parser.add_argument("--x-min", type=int, default=700)
    parser.add_argument("--x-max", type=int, default=1300)
    parser.add_argument("--y-min", type=int, default=700)
    parser.add_argument("--y-max", type=int, default=1300)
    parser.add_argument("--z-layer", type=int, default=1)
    parser.add_argument("--res-m", type=float, default=3.0e-5)
    parser.add_argument("--sr-inlet", type=float, default=1.0e-4)
    parser.add_argument("--ca-init", type=float, default=1.0e-3)
    parser.add_argument("--surface-vmin", type=float, default=1.0e-14)
    parser.add_argument("--surface-vmax", type=float, default=1.0e-10)
    args = parser.parse_args()

    coarse_nx = int((args.solid_case / "system" / "Nx1").read_text().strip())
    coarse_ny = int((args.solid_case / "system" / "Ny1").read_text().strip())
    binary = read_thresholded_hm12(
        args.raw_tar, args.x_min, args.x_max, args.y_min, args.y_max, args.z_layer, args.threshold
    )
    coarse_binary = downsample_labels(binary, coarse_ny, coarse_nx)
    mm_extent = extent_mm(args.x_max - args.x_min, args.y_max - args.y_min, args.res_m)

    geom_cmap = ListedColormap(["#ffffff", "#111111", "#9a9a9a"])
    geom_norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], geom_cmap.N)

    sr_cmap = plt.get_cmap("YlOrBr")
    ca_cmap = plt.get_cmap("Blues")
    surf_cmap = plt.get_cmap("magma").copy()
    surf_cmap.set_bad((1.0, 1.0, 1.0, 0.0))

    case_specs = [
        ("Solid grains", args.solid_case, "solid"),
        ("Microporous grains", args.micropore_case, "micropore"),
    ]

    args.output_dir.mkdir(parents=True, exist_ok=True)

    for time_name in args.times:
        fig, axes = plt.subplots(2, 4, figsize=(15.2, 7.4), sharex=True, sharey=True)

        field_handles = {}
        for row, (row_label, case_dir, geom_mode) in enumerate(case_specs):
            geom = geometry_for_case(coarse_binary, geom_mode)
            sr = assemble_parallel_field(case_dir, time_name, "Sr+2") / args.sr_inlet
            ca = assemble_parallel_field(case_dir, time_name, "Ca+2") / args.ca_init
            surf = assemble_parallel_field(case_dir, time_name, "Surf_aSr+")
            asurf = assemble_parallel_field(case_dir, "0", "aSurf")
            surf = np.where(asurf > 0.0, surf, np.nan)

            field_handles["geom"] = axes[row, 0].imshow(
                geom,
                cmap=geom_cmap,
                norm=geom_norm,
                origin="lower",
                interpolation="nearest",
                extent=mm_extent,
            )
            field_handles["sr"] = axes[row, 1].imshow(
                sr,
                cmap=sr_cmap,
                origin="lower",
                interpolation="nearest",
                extent=mm_extent,
                vmin=0.0,
                vmax=1.0,
            )
            field_handles["ca"] = axes[row, 2].imshow(
                ca,
                cmap=ca_cmap,
                origin="lower",
                interpolation="nearest",
                extent=mm_extent,
                vmin=0.0,
                vmax=1.0,
            )
            field_handles["surf"] = axes[row, 3].imshow(
                surf,
                cmap=surf_cmap,
                norm=LogNorm(vmin=args.surface_vmin, vmax=args.surface_vmax),
                origin="lower",
                interpolation="nearest",
                extent=mm_extent,
            )

            axes[row, 0].set_ylabel(f"{row_label}\ny [mm]")

        for ax in axes[-1, :]:
            ax.set_xlabel("x [mm]")

        for ax, title in zip(
            axes[0],
            ["Geometry", "Sr+2 / C_in", "Ca+2 / C_init", "Surf_aSr+"],
        ):
            ax.set_title(title)

        cbar0 = fig.colorbar(field_handles["geom"], ax=axes[:, 0], fraction=0.030, pad=0.02, ticks=[0, 1, 2])
        cbar0.ax.set_yticklabels(["solid", "pore", "micropore"])
        fig.colorbar(field_handles["sr"], ax=axes[:, 1], fraction=0.030, pad=0.02)
        fig.colorbar(field_handles["ca"], ax=axes[:, 2], fraction=0.030, pad=0.02)
        fig.colorbar(field_handles["surf"], ax=axes[:, 3], fraction=0.030, pad=0.02)

        fig.suptitle(f"HM12 comparison at t = {time_name} s, Pe ≈ 10", y=0.98)
        fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.96))
        fig.savefig(args.output_dir / f"hm12_compare_t{int(time_name):03d}.png", dpi=220)
        plt.close(fig)


if __name__ == "__main__":
    main()
