#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.gridspec import GridSpec
from matplotlib.patches import Circle
from matplotlib.ticker import FuncFormatter
from mpl_toolkits.axes_grid1.inset_locator import inset_axes


REPO_ROOT = Path(__file__).resolve().parents[4]
PYTOOLS = REPO_ROOT / "applications" / "utilities" / "pyTools"
if str(PYTOOLS) not in sys.path:
    sys.path.insert(0, str(PYTOOLS))

from createASurfMarchingCubes import contour_total_length, contours_for_pair


METHOD_STYLE = {
    "dbs-file": {
        "label": r"DBS $|\nabla \varepsilon|$",
        "color": "#8f2d2d",
        "marker": "s",
        "linestyle": "-",
    },
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


def boundary_mask(mask: np.ndarray) -> np.ndarray:
    interior = mask.copy()
    for axis in range(3):
        forward = np.roll(mask, -1, axis=axis)
        backward = np.roll(mask, 1, axis=axis)
        slicer_first = [slice(None)] * 3
        slicer_last = [slice(None)] * 3
        slicer_first[axis] = 0
        slicer_last[axis] = -1
        forward[tuple(slicer_last)] = False
        backward[tuple(slicer_first)] = False
        interior &= forward & backward
    return mask & ~interior


def crop_mask(mask: np.ndarray, pad: int = 1) -> tuple[np.ndarray, tuple[int, int, int]]:
    coords = np.argwhere(mask)
    mins = np.maximum(coords.min(axis=0) - pad, 0)
    maxs = np.minimum(coords.max(axis=0) + pad + 1, mask.shape)
    cropped = mask[mins[0]:maxs[0], mins[1]:maxs[1], mins[2]:maxs[2]]
    return cropped, (int(mins[0]), int(mins[1]), int(mins[2]))


def make_circle_image(radius_over_dx: float, sigma_vox: float = 1.5) -> tuple[np.ndarray, dict[str, float]]:
    pad = max(8, int(np.ceil(4.0 * sigma_vox)) + 4)
    n = 2 * int(radius_over_dx) + 2 * pad + 1
    yy, xx = np.indices((n, n))
    center = (n - 1) / 2.0
    solid = ((xx + 0.5 - center) ** 2 + (yy + 0.5 - center) ** 2) <= radius_over_dx**2
    return solid, {"n": float(n), "center": center, "radius_over_dx": float(radius_over_dx)}


def staircase_perimeter(solid_mask: np.ndarray) -> float:
    pore_mask = ~solid_mask
    vertical = np.count_nonzero(pore_mask[:, :-1] & solid_mask[:, 1:])
    vertical += np.count_nonzero(solid_mask[:, :-1] & pore_mask[:, 1:])
    horizontal = np.count_nonzero(pore_mask[:-1, :] & solid_mask[1:, :])
    horizontal += np.count_nonzero(solid_mask[:-1, :] & pore_mask[1:, :])
    return float(vertical + horizontal)


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
    series: dict[str, list[tuple[float, float]]] = {"dbs-file": [], "dbs-smoothed-mc": []}
    for radius in radii:
        solid_mask, _ = make_circle_image(radius, sigma_vox)
        analytic = 2.0 * np.pi * radius
        series["dbs-file"].append((float(radius), (staircase_perimeter(solid_mask) - analytic) / analytic))
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


def plot_center_slice(ax, case_dir: Path) -> None:
    volume, meta = load_generated_case(case_dir)
    solid_mask = volume == int(meta["solid_value"])
    zc = meta["nz"] // 2
    slice_mask = solid_mask[zc, :, :]
    cropped, (_, y0, x0) = crop_mask(slice_mask[np.newaxis, :, :], pad=2)
    slice_crop = cropped[0]

    ny, nx = slice_crop.shape
    extent = (0, nx, 0, ny)
    image = np.where(slice_crop, 0.0, 1.0)
    ax.imshow(
        image,
        cmap="gray",
        origin="lower",
        interpolation="nearest",
        extent=extent,
        vmin=0.0,
        vmax=1.0,
    )

    cx = meta["nx"] / 2.0 - x0
    cy = meta["ny"] / 2.0 - y0
    radius_vox = float(meta["radius_over_dx"])
    ax.add_patch(
        Circle(
            (cx, cy),
            radius_vox,
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
        rf"$R/\Delta x = {int(meta['radius_over_dx'])}$",
        transform=ax.transAxes,
        fontsize=9,
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
        cmap="gray",
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
        fontsize=9,
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
    zoom_ylim: tuple[float, float] | None = None,
) -> None:
    ax.axhline(0.0, color="#666666", lw=1.0, ls="--", zorder=0)
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
    ax.yaxis.set_major_formatter(FuncFormatter(percent_fmt))
    ax.set_ylim(*ylim)
    ax.grid(True, axis="y", color="#dddddd", lw=0.8)
    ax.grid(False, axis="x")
    ax.set_title(title, fontsize=12, fontweight="bold")

    if zoom_ylim is None:
        return

    detail_ax = inset_axes(ax, width="47%", height="43%", loc="center right", borderpad=1.15)
    detail_ax.axhline(0.0, color="#666666", lw=0.8, ls="--", zorder=0)
    for method in method_order:
        if method not in series:
            continue
        values = series[method]
        style = METHOD_STYLE[method]
        xs = [item[0] for item in values]
        ys = [item[1] for item in values]
        detail_ax.plot(
            xs,
            ys,
            color=style["color"],
            marker=style["marker"],
            linestyle=style["linestyle"],
            lw=1.45,
            ms=4.5,
        )

    detail_ax.set_xscale("log", base=2)
    detail_ax.set_xticks([8, 16, 32, 64], labels=["8", "16", "32", "64"])
    detail_ax.set_ylim(*zoom_ylim)
    detail_ax.yaxis.set_major_formatter(FuncFormatter(percent_fmt_decimal))
    detail_ax.tick_params(axis="both", labelsize=7, length=2.5, pad=1)
    detail_ax.grid(True, axis="y", color="#e4e4e4", lw=0.6)
    detail_ax.grid(False, axis="x")
    detail_ax.set_title("near-zero detail", fontsize=8, pad=2)
    detail_ax.set_facecolor("white")
    for spine in detail_ax.spines.values():
        spine.set_edgecolor("#999999")
        spine.set_linewidth(0.8)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--results-dir", type=Path, required=True)
    parser.add_argument("--generated-dir", type=Path, required=True)
    parser.add_argument("--circular-post-snappy-csv", type=Path, default=None)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    series = load_series_from_results(args.results_dir)
    circle_series = circular_post_series(snappy_csv=args.circular_post_snappy_csv)

    fig = plt.figure(figsize=(13.4, 10.0), constrained_layout=True)
    grid = GridSpec(2, 3, figure=fig, width_ratios=[1.0, 1.0, 1.7])

    post_grid = grid[0, 0:2].subgridspec(1, 2, wspace=0.08)
    for col, radius in enumerate((8, 16)):
        circle_ax = fig.add_subplot(post_grid[0, col])
        plot_circle_slice(circle_ax, radius)
        if col == 0:
            circle_ax.set_title("2D circular-post slices", fontsize=10, fontweight="bold", pad=10)

    sphere_grid = grid[1, 0:2].subgridspec(1, 2, wspace=0.08)
    for col, level in enumerate(("sphere_r08", "sphere_r16")):
        sphere_ax = fig.add_subplot(sphere_grid[0, col])
        plot_center_slice(sphere_ax, args.generated_dir / level)
        if col == 0:
            sphere_ax.set_title("3D sphere centre slices", fontsize=10, fontweight="bold", pad=10)

    circle_error_ax = fig.add_subplot(grid[0, 2])
    plot_error_series(
        circle_error_ax,
        circle_series,
        ["snappy", "dbs-smoothed-mc", "dbs-file"],
        "2D circular-post area error",
        r"Post resolution $R / \Delta x$",
        "Relative error",
        (-0.04, 0.32),
        zoom_ylim=(-0.004, 0.004),
    )

    sphere_error_ax = fig.add_subplot(grid[1, 2])
    plot_error_series(
        sphere_error_ax,
        series,
        ["snappy", "dbs-smoothed-mc", "dbs-file"],
        "3D sphere area error",
        r"Sphere resolution $R / \Delta x$",
        "Relative error",
        (-0.06, 0.56),
        zoom_ylim=(-0.035, 0.02),
    )

    legend = sphere_error_ax.legend(loc="center left", frameon=True)
    legend.get_frame().set_edgecolor("#cccccc")
    legend.get_frame().set_alpha(0.95)
    legend = circle_error_ax.legend(loc="center left", frameon=True)
    legend.get_frame().set_edgecolor("#cccccc")
    legend.get_frame().set_alpha(0.95)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=360)
    plt.close(fig)


if __name__ == "__main__":
    main()
