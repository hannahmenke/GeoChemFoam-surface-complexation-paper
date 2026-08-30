#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import ListedColormap, to_hex, to_rgb
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Circle, Patch
from matplotlib.ticker import FuncFormatter
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


REPO_ROOT = Path(__file__).resolve().parents[4]
PYTOOLS = REPO_ROOT / "scripts"
if str(PYTOOLS) not in sys.path:
    sys.path.insert(0, str(PYTOOLS))

from createASurfMarchingCubes import contour_total_length, contours_for_pair


METHOD_STYLE = {
    "dbs-smoothed-mc": {
        "label": "DBS smoothSurface",
        "color": "#1b6b73",
        "marker": "o",
        "linestyle": "-",
    },
    "snappy": {
        "label": "snappyHexMesh",
        "color": "#d98f00",
        "marker": "^",
        "linestyle": "-",
    },
}

GEOMETRY_CMAP = ListedColormap(["#7d8b94", "#ffffff"])
VOXEL_OUTSIDE_COLOR = "#35789a"
VOXEL_INSIDE_COLOR = "#d99a32"
ANALYTIC_SPHERE_COLOR = "#c62828"

def percent_fmt(value: float, _: int) -> str:
    return f"{100.0 * value:.0f}%"


def percent_fmt_decimal(value: float, _: int) -> str:
    return f"{100.0 * value:.1f}%"


def load_series_from_results(results_dir: Path) -> dict[str, list[tuple[float, float]]]:
    series: dict[str, list[tuple[float, float]]] = {}
    for metrics_path in sorted(results_dir.glob("sphere_r*/area_metrics.csv")):
        radius_token = metrics_path.parent.name.replace("sphere_r", "")
        radius_over_dx = float(radius_token)
        with metrics_path.open(newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                method = row["method"].strip()
                rel_err = float(row["rel_err_vs_analytic"])
                series.setdefault(method, []).append((radius_over_dx, rel_err))

    for values in series.values():
        values.sort(key=lambda item: item[0])
    return series


def load_generated_case(case_dir: Path) -> tuple[np.ndarray, dict]:
    json_path = next(case_dir.glob("*.json"))
    with json_path.open() as handle:
        meta = json.load(handle)

    raw_path = case_dir / meta["raw_path"]
    volume = np.fromfile(raw_path, dtype=np.uint8).reshape((meta["nz"], meta["ny"], meta["nx"]))
    return volume, meta


def crop_mask(mask: np.ndarray, pad: int = 1) -> tuple[np.ndarray, tuple[int, int, int]]:
    coords = np.argwhere(mask)
    mins = np.maximum(coords.min(axis=0) - pad, 0)
    maxs = np.minimum(coords.max(axis=0) + pad + 1, mask.shape)
    cropped = mask[mins[0]:maxs[0], mins[1]:maxs[1], mins[2]:maxs[2]]
    return cropped, (int(mins[0]), int(mins[1]), int(mins[2]))


def exposed_voxel_faces(
    mask_xyz: np.ndarray,
    center: tuple[float, float, float],
    radius: float,
) -> tuple[list[list[tuple[float, float, float]]], list[str]]:
    """Return exterior faces colored by signed offset from the exact sphere."""
    faces: list[list[tuple[float, float, float]]] = []
    colors: list[str] = []
    directions = (
        ((-1, 0, 0), lambda x, y, z: [(x, y, z), (x, y + 1, z), (x, y + 1, z + 1), (x, y, z + 1)], 0.86),
        ((1, 0, 0), lambda x, y, z: [(x + 1, y, z), (x + 1, y, z + 1), (x + 1, y + 1, z + 1), (x + 1, y + 1, z)], 1.06),
        ((0, -1, 0), lambda x, y, z: [(x, y, z), (x, y, z + 1), (x + 1, y, z + 1), (x + 1, y, z)], 0.78),
        ((0, 1, 0), lambda x, y, z: [(x, y + 1, z), (x + 1, y + 1, z), (x + 1, y + 1, z + 1), (x, y + 1, z + 1)], 0.96),
        ((0, 0, -1), lambda x, y, z: [(x, y, z), (x + 1, y, z), (x + 1, y + 1, z), (x, y + 1, z)], 0.72),
        ((0, 0, 1), lambda x, y, z: [(x, y, z + 1), (x, y + 1, z + 1), (x + 1, y + 1, z + 1), (x + 1, y, z + 1)], 1.15),
    )
    center_array = np.asarray(center)
    nx, ny, nz = mask_xyz.shape
    for x, y, z in np.argwhere(mask_xyz):
        for (dx, dy, dz), vertices, light_factor in directions:
            xn, yn, zn = x + dx, y + dy, z + dz
            if not (0 <= xn < nx and 0 <= yn < ny and 0 <= zn < nz) or not mask_xyz[xn, yn, zn]:
                face = vertices(float(x), float(y), float(z))
                face_center = np.mean(face, axis=0)
                base_color = (
                    VOXEL_OUTSIDE_COLOR
                    if np.linalg.norm(face_center - center_array) >= radius
                    else VOXEL_INSIDE_COLOR
                )
                shaded = np.clip(np.asarray(to_rgb(base_color)) * light_factor, 0.0, 1.0)
                faces.append(face)
                colors.append(to_hex(shaded))
    return faces, colors


def make_circle_image(radius_over_dx: float, sigma_vox: float = 1.5) -> tuple[np.ndarray, dict[str, float]]:
    pad = max(8, int(np.ceil(4.0 * sigma_vox)) + 4)
    n = 2 * int(radius_over_dx) + 2 * pad + 1
    yy, xx = np.indices((n, n))
    center = (n - 1) / 2.0
    solid = ((xx + 0.5 - center) ** 2 + (yy + 0.5 - center) ** 2) <= radius_over_dx**2
    return solid, {"n": float(n), "center": center, "radius_over_dx": float(radius_over_dx)}


def smooth_circle_perimeter(solid_mask: np.ndarray, sigma_vox: float) -> float:
    image = np.where(solid_mask[np.newaxis, :, :], 0, 255).astype(np.uint8)
    owner_mask = image == 255
    pair_mask = np.ones_like(owner_mask, dtype=bool)
    contours, _ = contours_for_pair(owner_mask, pair_mask, 1.0, "occupancyGaussian", sigma_vox)
    return contour_total_length(contours)


def circular_post_series(
    radii: list[int] | tuple[int, ...] = (8, 16, 32, 64),
    sigma_vox: float = 1.5,
    snappy_csv: Path | None = None,
) -> dict[str, list[tuple[float, float]]]:
    series: dict[str, list[tuple[float, float]]] = {"dbs-smoothed-mc": []}
    for radius in radii:
        solid_mask, _ = make_circle_image(radius, sigma_vox)
        analytic = 2.0 * np.pi * radius
        smooth_length = smooth_circle_perimeter(solid_mask, sigma_vox)
        series["dbs-smoothed-mc"].append((float(radius), (smooth_length - analytic) / analytic))
    if snappy_csv is not None and snappy_csv.exists():
        with snappy_csv.open(newline="") as handle:
            reader = csv.DictReader(handle)
            series["snappy"] = [
                (float(row["radius_over_dx"]), float(row["rel_err_vs_analytic"]))
                for row in reader
                if row["method"].strip() == "snappy"
            ]
        series["snappy"].sort(key=lambda item: item[0])
    return series


def plot_sphere_render(ax, case_dir: Path) -> None:
    """Render the exterior faces of the voxelized sphere."""
    ax.computed_zorder = False
    volume, meta = load_generated_case(case_dir)
    solid_mask = volume == int(meta["solid_value"])
    cropped, (z0, y0, x0) = crop_mask(solid_mask, pad=1)
    solid_xyz = np.transpose(cropped, (2, 1, 0))

    radius = float(meta["radius_over_dx"])
    cx = meta["nx"] / 2.0 - x0
    cy = meta["ny"] / 2.0 - y0
    cz = meta["nz"] / 2.0 - z0
    faces, facecolors = exposed_voxel_faces(solid_xyz, (cx, cy, cz), radius)
    ax.add_collection3d(
        Poly3DCollection(
            faces,
            facecolors=facecolors,
            edgecolors="#56636c",
            linewidths=0.08,
            zsort="average",
            zorder=2,
        )
    )

    u = np.linspace(0.0, 2.0 * np.pi, 49)
    v = np.linspace(0.0, np.pi, 25)
    sphere_x = cx + radius * np.outer(np.cos(u), np.sin(v))
    sphere_y = cy + radius * np.outer(np.sin(u), np.sin(v))
    sphere_z = cz + radius * np.outer(np.ones_like(u), np.cos(v))
    ax.plot_surface(
        sphere_x,
        sphere_y,
        sphere_z,
        color=ANALYTIC_SPHERE_COLOR,
        alpha=0.14,
        linewidth=0.0,
        antialiased=True,
        shade=True,
        zorder=4,
    )
    margin = 1.5
    ax.set_xlim(cx - radius - margin, cx + radius + margin)
    ax.set_ylim(cy - radius - margin, cy + radius + margin)
    ax.set_zlim(cz - radius - margin, cz + radius + margin)
    ax.set_box_aspect((1, 1, 1), zoom=1.35)
    ax.set_proj_type("ortho")
    ax.view_init(elev=24, azim=-52)
    ax.set_axis_off()
    ax.text2D(
        0.03,
        0.92,
        rf"$R/\Delta x = {int(meta['radius_over_dx'])}$",
        transform=ax.transAxes,
        fontsize=14.0,
        bbox=dict(facecolor="white", edgecolor="#cccccc", alpha=0.92, boxstyle="round,pad=0.25"),
    )


def plot_circle_slice(ax, radius_over_dx: int, sigma_vox: float = 1.5) -> None:
    solid_mask, meta = make_circle_image(radius_over_dx, sigma_vox)
    cropped, (_, y0, x0) = crop_mask(solid_mask[np.newaxis, :, :], pad=2)
    circle_crop = cropped[0]

    ny, nx = circle_crop.shape
    image = np.where(circle_crop, 0.0, 1.0)
    ax.imshow(
        image,
        cmap=GEOMETRY_CMAP,
        origin="lower",
        interpolation="nearest",
        extent=(0, nx, 0, ny),
        vmin=0.0,
        vmax=1.0,
    )

    cx = meta["center"] - x0
    cy = meta["center"] - y0
    ax.add_patch(
        Circle(
            (cx, cy),
            radius_over_dx,
            facecolor="none",
            edgecolor="#c62828",
            linewidth=2.0,
        )
    )

    ax.set_xlim(0, nx)
    ax.set_ylim(0, ny)
    ax.set_aspect("equal")
    ax.set_axis_off()
    ax.text(
        0.03,
        0.92,
        rf"$R/\Delta x = {radius_over_dx}$",
        transform=ax.transAxes,
        fontsize=14.0,
        bbox=dict(facecolor="white", edgecolor="#cccccc", alpha=0.92, boxstyle="round,pad=0.25"),
    )


def plot_error_series(
    ax,
    series: dict[str, list[tuple[float, float]]],
    method_order: list[str],
    title: str,
    xlabel: str,
    ylabel: str,
    ylim: tuple[float, float],
) -> None:
    ax.axhline(0.0, color="#8a8a8a", lw=0.9, ls=(0, (4, 3)), zorder=0)
    for method in method_order:
        if method not in series:
            continue
        values = series[method]
        style = METHOD_STYLE[method]
        xs = [item[0] for item in values]
        ys = [item[1] for item in values]
        ax.plot(
            xs,
            ys,
            label=style["label"],
            color=style["color"],
            marker=style["marker"],
            linestyle=style["linestyle"],
            lw=2.2,
            ms=7.5,
        )

    ax.set_xscale("log", base=2)
    ax.set_xticks([8, 16, 32, 64], labels=["8", "16", "32", "64"])
    ax.set_xlabel(xlabel)
    ax.set_ylabel(ylabel)
    ax.yaxis.set_major_formatter(FuncFormatter(percent_fmt_decimal))
    ax.set_ylim(*ylim)
    ax.grid(False)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_color("#4a4a4a")
    ax.spines["bottom"].set_color("#4a4a4a")
    ax.tick_params(direction="out", length=5, width=1.0, colors="#333333")
    ax.set_title(title, fontsize=14.0, fontweight="bold", pad=8)

def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--generated-dir", type=Path, required=True)
    parser.add_argument("--circular-post-snappy-csv", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    series = load_series_from_results(args.results_dir)
    circle_series = circular_post_series(snappy_csv=args.circular_post_snappy_csv)

    plt.rcParams.update(
        {
            "font.size": 14.0,
            "axes.labelsize": 14.0,
            "xtick.labelsize": 14.0,
            "ytick.labelsize": 14.0,
            "legend.fontsize": 14.0,
        }
    )
    fig = plt.figure(figsize=(8.0, 6.4), constrained_layout=True)
    grid = GridSpec(
        3,
        3,
        figure=fig,
        width_ratios=[1.0, 1.0, 1.65],
        height_ratios=[1.0, 1.0, 0.24],
    )

    post_grid = grid[0, 0:2].subgridspec(1, 2, wspace=0.08)
    for col, radius in enumerate((8, 16)):
        circle_ax = fig.add_subplot(post_grid[0, col])
        plot_circle_slice(circle_ax, radius)

    sphere_grid = grid[1, 0:2].subgridspec(1, 2, wspace=0.08)
    for col, level in enumerate(("sphere_r08", "sphere_r16")):
        sphere_ax = fig.add_subplot(sphere_grid[0, col], projection="3d")
        plot_sphere_render(sphere_ax, args.generated_dir / level)

    fig.text(0.29, 0.975, "2D post slices", ha="center", va="top", fontsize=14.0, fontweight="bold")
    fig.text(0.29, 0.627, "3D voxelized spheres", ha="center", va="top", fontsize=14.0, fontweight="bold")

    circle_error_ax = fig.add_subplot(grid[0, 2])
    plot_error_series(
        circle_error_ax,
        circle_series,
        ["snappy", "dbs-smoothed-mc"],
        "2D post area error",
        r"Post $R / \Delta x$",
        "Relative error",
        (-0.0025, 0.0025),
    )

    sphere_error_ax = fig.add_subplot(grid[1, 2])
    plot_error_series(
        sphere_error_ax,
        series,
        ["snappy", "dbs-smoothed-mc"],
        "3D sphere area error",
        r"Sphere $R / \Delta x$",
        "Relative error",
        (-0.028, 0.012),
    )

    legend_ax = fig.add_subplot(grid[2, :])
    legend_ax.set_axis_off()
    handles, labels = circle_error_ax.get_legend_handles_labels()
    geometry_handles = [
        Patch(facecolor=VOXEL_OUTSIDE_COLOR, label="outside sphere"),
        Patch(facecolor=VOXEL_INSIDE_COLOR, label="inside sphere"),
        Patch(facecolor=ANALYTIC_SPHERE_COLOR, alpha=0.22, label="analytic sphere"),
    ]
    geometry_legend = legend_ax.legend(
        handles=geometry_handles,
        loc="center",
        bbox_to_anchor=(0.5, 0.75),
        ncol=3,
        frameon=False,
        columnspacing=1.2,
        handlelength=1.3,
        fontsize=14.0,
    )
    legend_ax.add_artist(geometry_legend)
    legend_ax.legend(
        handles,
        labels,
        loc="center",
        bbox_to_anchor=(0.5, 0.18),
        ncol=len(labels),
        frameon=False,
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=360)
    plt.close(fig)


if __name__ == "__main__":
    main()
