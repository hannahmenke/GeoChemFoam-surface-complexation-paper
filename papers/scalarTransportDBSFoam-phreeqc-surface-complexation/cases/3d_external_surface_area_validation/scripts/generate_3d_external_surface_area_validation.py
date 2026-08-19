#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import tarfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import LogNorm


REPO_ROOT = Path(__file__).resolve().parents[5]
PYTOOLS = REPO_ROOT / "applications" / "utilities" / "pyTools"
if str(PYTOOLS) not in sys.path:
    sys.path.insert(0, str(PYTOOLS))

from createASurfMarchingCubes import build_field, marching_cubes_for_pair


PORE_LABEL = 1
MICROPORE_LABEL = 2
SOLID_LABEL = 3


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a 3D external pore-solid surface-area validation figure."
    )
    parser.add_argument("--image-name", default="Est_3phase500cubed4micron")
    parser.add_argument("--image-dims", nargs=3, type=int, default=(500, 500, 500))
    parser.add_argument("--crop-min", nargs=3, type=int, default=(300, 340, 40))
    parser.add_argument("--crop-size", nargs=3, type=int, default=(128, 128, 128))
    parser.add_argument("--voxel-size", type=float, default=4e-6)
    parser.add_argument("--sigma-vox", type=float, default=1.5)
    parser.add_argument("--surface-mode", default="occupancyGaussian")
    parser.add_argument(
        "--exclude-boundary-cells",
        type=int,
        default=1,
        help="Zero this many crop-boundary cell layers before computing plotted metrics.",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    return parser.parse_args()


def raw_candidates(image_name: str) -> list[Path]:
    candidates: list[Path] = []
    for base in (
        os.environ.get("GCFOAM_IMG"),
        str(REPO_ROOT / "images"),
    ):
        if not base:
            continue
        root = Path(base)
        candidates.extend(
            [
                root / f"{image_name}.raw",
                root / "raw" / f"{image_name}.raw",
                root / f"{image_name}.raw.tar.gz",
                root / "raw" / f"{image_name}.raw.tar.gz",
            ]
        )
    return candidates


def load_raw_image(image_name: str, dims_xyz: tuple[int, int, int]) -> np.ndarray:
    nx, ny, nz = dims_xyz
    expected = nx * ny * nz
    for path in raw_candidates(image_name):
        if not path.exists():
            continue
        if path.suffixes[-2:] == [".tar", ".gz"]:
            with tarfile.open(path, "r:gz") as archive:
                member = archive.getmember(f"{image_name}.raw")
                handle = archive.extractfile(member)
                if handle is None:
                    raise RuntimeError(f"Could not extract {image_name}.raw from {path}")
                raw = np.frombuffer(handle.read(), dtype=np.uint8)
        else:
            raw = np.fromfile(path, dtype=np.uint8)
        if raw.size != expected:
            raise RuntimeError(f"Raw size mismatch for {path}: {raw.size} != {expected}")
        return raw.reshape((nz, ny, nx))
    raise FileNotFoundError(f"Could not find {image_name}.raw or .raw.tar.gz")


def crop_image(image: np.ndarray, crop_min_xyz: tuple[int, int, int], crop_size_xyz: tuple[int, int, int]) -> np.ndarray:
    x0, y0, z0 = crop_min_xyz
    sx, sy, sz = crop_size_xyz
    return image[z0:z0 + sz, y0:y0 + sy, x0:x0 + sx].copy()


def remap_external_only(crop: np.ndarray) -> np.ndarray:
    remapped = crop.copy()
    remapped[remapped == MICROPORE_LABEL] = SOLID_LABEL
    return remapped


def staircase_area_field(image: np.ndarray, voxel_size: float) -> np.ndarray:
    pore = image == PORE_LABEL
    solid = image == SOLID_LABEL
    counts = np.zeros(image.shape, dtype=np.float64)

    contacts = pore[:, :, :-1] & solid[:, :, 1:]
    counts[:, :, :-1] += contacts
    contacts = solid[:, :, :-1] & pore[:, :, 1:]
    counts[:, :, 1:] += contacts

    contacts = pore[:, :-1, :] & solid[:, 1:, :]
    counts[:, :-1, :] += contacts
    contacts = solid[:, :-1, :] & pore[:, 1:, :]
    counts[:, 1:, :] += contacts

    contacts = pore[:-1, :, :] & solid[1:, :, :]
    counts[:-1, :, :] += contacts
    contacts = solid[:-1, :, :] & pore[1:, :, :]
    counts[1:, :, :] += contacts

    return counts * voxel_size * voxel_size


def smooth_area_field(image: np.ndarray, voxel_size: float, surface_mode: str, sigma_vox: float) -> tuple[np.ndarray, int, str]:
    owner_mask = image == PORE_LABEL
    pair_mask = owner_mask | (image == SOLID_LABEL)
    verts, faces, used_mode = marching_cubes_for_pair(
        owner_mask,
        pair_mask,
        voxel_size,
        surface_mode,
        sigma_vox,
    )
    nz, ny, nx = image.shape
    asurf, _ = build_field(
        verts,
        faces,
        image,
        nx,
        ny,
        nz,
        1,
        1,
        1,
        voxel_size,
        PORE_LABEL,
    )
    return asurf * voxel_size**3, int(faces.shape[0]), used_mode


def remove_boundary_shell(field: np.ndarray, layers: int) -> np.ndarray:
    if layers <= 0:
        return field
    if 2 * layers >= min(field.shape):
        raise ValueError("Boundary exclusion is too large for the selected crop.")
    trimmed = field.copy()
    trimmed[:layers, :, :] = 0.0
    trimmed[-layers:, :, :] = 0.0
    trimmed[:, :layers, :] = 0.0
    trimmed[:, -layers:, :] = 0.0
    trimmed[:, :, :layers] = 0.0
    trimmed[:, :, -layers:] = 0.0
    return trimmed


def projection(field: np.ndarray) -> np.ndarray:
    return np.sum(field, axis=0)


def profile_x(field: np.ndarray) -> np.ndarray:
    return np.sum(field, axis=(0, 1))


def write_metrics(csv_path: Path, rows: list[dict[str, float | int | str]]) -> None:
    csv_path.parent.mkdir(parents=True, exist_ok=True)
    with csv_path.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["method", "area", "relative_to_smooth", "active_cells", "triangles"],
        )
        writer.writeheader()
        writer.writerows(rows)


def make_figure(
    output: Path,
    image: np.ndarray,
    staircase_area: np.ndarray,
    smooth_area: np.ndarray,
    voxel_size: float,
    rows: list[dict[str, float | int | str]],
) -> None:
    mid = image.shape[0] // 2
    geom = image[mid]
    geom_rgb = np.ones((*geom.shape, 3), dtype=float)
    geom_rgb[geom == SOLID_LABEL] = (0.05, 0.05, 0.05)
    geom_rgb[geom == PORE_LABEL] = (0.92, 0.92, 0.92)

    grad_proj = projection(staircase_area)
    smooth_proj = projection(smooth_area)
    diff_proj = smooth_proj - grad_proj
    profile_grad = profile_x(staircase_area)
    profile_smooth = profile_x(smooth_area)

    positive = np.concatenate([grad_proj[grad_proj > 0], smooth_proj[smooth_proj > 0]])
    vmin = max(float(np.percentile(positive, 2)), voxel_size * voxel_size * 0.25)
    vmax = float(np.percentile(positive, 99.5))
    diff_lim = float(np.percentile(np.abs(diff_proj), 99.0))
    if diff_lim <= 0.0:
        diff_lim = voxel_size * voxel_size

    fig = plt.figure(figsize=(12.5, 8.0), constrained_layout=True)
    grid = fig.add_gridspec(2, 4, height_ratios=[1.0, 0.82], width_ratios=[1, 1, 1, 1.15])

    ax_geom = fig.add_subplot(grid[0, 0])
    ax_grad = fig.add_subplot(grid[0, 1])
    ax_smooth = fig.add_subplot(grid[0, 2])
    ax_diff = fig.add_subplot(grid[0, 3])
    ax_profile = fig.add_subplot(grid[1, 0:3])
    ax_table = fig.add_subplot(grid[1, 3])

    extent_um = (0, image.shape[2] * voxel_size * 1e6, 0, image.shape[1] * voxel_size * 1e6)
    ax_geom.imshow(geom_rgb, origin="lower", extent=extent_um, interpolation="nearest")
    ax_geom.set_title("external-only 3D crop")
    ax_geom.set_xlabel(r"$x$ [$\mu$m]")
    ax_geom.set_ylabel(r"$y$ [$\mu$m]")

    im_grad = ax_grad.imshow(
        grad_proj,
        origin="lower",
        extent=extent_um,
        norm=LogNorm(vmin=vmin, vmax=vmax),
        cmap="magma",
    )
    ax_grad.set_title(r"DBS $|\nabla \varepsilon|$")
    ax_grad.set_xlabel(r"$x$ [$\mu$m]")
    ax_grad.set_yticklabels([])

    im_smooth = ax_smooth.imshow(
        smooth_proj,
        origin="lower",
        extent=extent_um,
        norm=LogNorm(vmin=vmin, vmax=vmax),
        cmap="magma",
    )
    ax_smooth.set_title("DBS smoothSurface")
    ax_smooth.set_xlabel(r"$x$ [$\mu$m]")
    ax_smooth.set_yticklabels([])

    im_diff = ax_diff.imshow(
        diff_proj,
        origin="lower",
        extent=extent_um,
        vmin=-diff_lim,
        vmax=diff_lim,
        cmap="coolwarm",
    )
    ax_diff.set_title("smooth - staircase")
    ax_diff.set_xlabel(r"$x$ [$\mu$m]")
    ax_diff.set_yticklabels([])

    cbar = fig.colorbar(im_smooth, ax=[ax_grad, ax_smooth], fraction=0.05, pad=0.02)
    cbar.set_label(r"projected area [m$^2$]")
    cbar_diff = fig.colorbar(im_diff, ax=ax_diff, fraction=0.05, pad=0.02)
    cbar_diff.set_label(r"area difference [m$^2$]")

    x_um = (np.arange(image.shape[2]) + 0.5) * voxel_size * 1e6
    profile_active = (profile_grad > 0.0) | (profile_smooth > 0.0)
    ax_profile.plot(
        x_um[profile_active],
        profile_grad[profile_active],
        color="#8f2d2d",
        lw=2.0,
        label=r"DBS $|\nabla \varepsilon|$",
    )
    ax_profile.plot(
        x_um[profile_active],
        profile_smooth[profile_active],
        color="#1b6b73",
        lw=2.0,
        label="DBS smoothSurface",
    )
    ax_profile.set_xlabel(r"$x$ [$\mu$m]")
    ax_profile.set_ylabel(r"area per $x$ slice [m$^2$]")
    ax_profile.grid(True, axis="y", color="#dddddd", lw=0.8)
    ax_profile.legend(frameon=False, loc="upper right")

    ax_table.axis("off")
    grad = next(row for row in rows if row["method"] == "dbs-grad-eps")
    smooth = next(row for row in rows if row["method"] == "dbs-smoothsurface")
    table_text = (
        "Integrated area\n"
        f"DBS grad-eps: {float(grad['area']):.3e} m$^2$\n"
        f"DBS smoothSurface: {float(smooth['area']):.3e} m$^2$\n"
        f"relative difference: {float(grad['relative_to_smooth']):+.1%}\n\n"
        "Active pore-side cells\n"
        f"DBS grad-eps: {int(grad['active_cells'])}\n"
        f"DBS smoothSurface: {int(smooth['active_cells'])}"
    )
    ax_table.text(0.0, 0.98, table_text, va="top", ha="left", fontsize=10)

    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=360)
    plt.close(fig)


def main() -> None:
    args = parse_args()
    dims = tuple(args.image_dims)
    crop_min = tuple(args.crop_min)
    crop_size = tuple(args.crop_size)
    raw = load_raw_image(args.image_name, dims)
    image = remap_external_only(crop_image(raw, crop_min, crop_size))

    if not np.any(image == PORE_LABEL) or not np.any(image == SOLID_LABEL):
        raise RuntimeError("Selected crop must contain both pore and solid after remapping.")

    staircase = staircase_area_field(image, args.voxel_size)
    smooth, triangles, used_mode = smooth_area_field(
        image,
        args.voxel_size,
        args.surface_mode,
        args.sigma_vox,
    )
    staircase_metric = remove_boundary_shell(staircase, args.exclude_boundary_cells)
    smooth_metric = remove_boundary_shell(smooth, args.exclude_boundary_cells)

    smooth_total = float(np.sum(smooth_metric))
    rows: list[dict[str, float | int | str]] = [
        {
            "method": "dbs-grad-eps",
            "area": float(np.sum(staircase_metric)),
            "relative_to_smooth": (float(np.sum(staircase_metric)) - smooth_total) / smooth_total,
            "active_cells": int(np.count_nonzero(staircase_metric > 0.0)),
            "triangles": 0,
        },
        {
            "method": "dbs-smoothsurface",
            "area": smooth_total,
            "relative_to_smooth": 0.0,
            "active_cells": int(np.count_nonzero(smooth_metric > 0.0)),
            "triangles": triangles,
        },
    ]

    metadata = {
        "image_name": args.image_name,
        "image_dims": list(dims),
        "crop_min": list(crop_min),
        "crop_size": list(crop_size),
        "voxel_size": args.voxel_size,
        "surface_mode": args.surface_mode,
        "sigma_vox": args.sigma_vox,
        "smooth_used_mode": used_mode,
        "exclude_boundary_cells": args.exclude_boundary_cells,
        "labels": {"pore": PORE_LABEL, "micropore_remapped_to_solid": MICROPORE_LABEL, "solid": SOLID_LABEL},
        "rows": rows,
    }

    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(metadata, indent=2))
    write_metrics(args.output_csv, rows)
    make_figure(args.output, image, staircase_metric, smooth_metric, args.voxel_size, rows)

    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
