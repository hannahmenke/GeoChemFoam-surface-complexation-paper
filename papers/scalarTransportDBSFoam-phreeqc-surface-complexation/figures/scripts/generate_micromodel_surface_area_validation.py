#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from matplotlib.patches import Rectangle

from hm12_case_tools import (
    add_scale_bar,
    assemble_parallel_structured,
    boundary_patch_segments,
    gather_parallel_unstructured,
    masked_structured,
    points_to_grid,
)


def mean_profile_over_pore(field: np.ndarray) -> np.ndarray:
    return np.nanmean(np.where(np.isfinite(field), field, np.nan), axis=0)


def column_inventory_profile(field: np.ndarray) -> np.ndarray:
    return np.sum(np.nan_to_num(field, nan=0.0), axis=0)


def masked_nonzero(field: np.ndarray) -> np.ma.MaskedArray:
    return np.ma.masked_where(field <= 0.0, field)


def nonzero_percentile_limits(fields: list[np.ma.MaskedArray], lo: float, hi: float) -> tuple[float, float]:
    values = []
    for field in fields:
        arr = np.ma.compressed(field)
        arr = arr[np.isfinite(arr) & (arr > 0.0)]
        if arr.size:
            values.append(arr)
    if not values:
        return 0.0, 1.0
    all_values = np.concatenate(values)
    vmin = float(np.percentile(all_values, lo))
    vmax = float(np.percentile(all_values, hi))
    if not np.isfinite(vmin) or vmin <= 0.0:
        vmin = float(np.nanmin(all_values))
    if not np.isfinite(vmax) or vmax <= vmin:
        vmax = float(np.nanmax(all_values))
    return vmin, vmax


def nonzero_percentile_limit(field: np.ma.MaskedArray, hi: float) -> float:
    values = np.ma.compressed(field)
    values = values[np.isfinite(values) & (values > 0.0)]
    if values.size == 0:
        return 1.0
    return float(np.percentile(values, hi))


def assemble_structured_with_fallback(case_dir: Path, time_name: str, fallback_time: str, field_name: str) -> np.ndarray:
    try:
        return assemble_parallel_structured(case_dir, time_name, field_name)
    except (FileNotFoundError, RuntimeError):
        return assemble_parallel_structured(case_dir, fallback_time, field_name)


def points_to_sum_grid(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    nx: int,
    ny: int,
    res: float,
) -> np.ndarray:
    grid = np.zeros((ny, nx), dtype=float)
    ix = np.rint(x / res - 0.5).astype(int)
    iy = np.rint(y / res - 0.5).astype(int)
    valid = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    np.add.at(grid, (iy[valid], ix[valid]), values[valid])
    return grid


def wall_segment_area_values(segments: np.ndarray, res: float) -> np.ndarray:
    if segments.size == 0:
        return np.zeros(0, dtype=float)
    lengths = np.linalg.norm(segments[:, 1, :] - segments[:, 0, :], axis=1)
    return lengths * res


def add_wall_line_collection(
    ax,
    segments_mm: np.ndarray,
    values: np.ndarray,
    cmap,
    norm,
    linewidth: float = 1.15,
) -> LineCollection | None:
    if segments_mm.size == 0 or values.size == 0:
        return None
    collection = LineCollection(
        segments_mm,
        array=values,
        cmap=cmap,
        norm=norm,
        linewidths=linewidth,
        alpha=1.0,
        capstyle="round",
        joinstyle="round",
    )
    ax.add_collection(collection)
    return collection


def dbs_inventory_grid(
    surface_density: np.ndarray,
    a_surf: np.ndarray,
    pore_mask: np.ndarray,
    cell_volume: float | np.ndarray,
) -> np.ndarray:
    return np.where(pore_mask & (a_surf > 0.0), surface_density * a_surf * cell_volume, 0.0)


def add_axis_scale_bar(ax, length_mm: float = 2.0) -> None:
    xmin, xmax = ax.get_xlim()
    ymin, ymax = ax.get_ylim()
    x0 = xmin + (xmax - xmin) * 0.06
    y0 = ymin + (ymax - ymin) * 0.06
    ax.plot([x0, x0 + length_mm], [y0, y0], color="white", lw=3, solid_capstyle="butt")
    ax.text(
        x0 + 0.5 * length_mm,
        y0 + 0.18,
        f"{length_mm:g} mm",
        color="white",
        ha="center",
        va="bottom",
        fontsize=16,
        bbox=dict(facecolor="black", alpha=0.35, edgecolor="none", pad=1.5),
    )


def add_mask_outline(ax, pore_mask: np.ndarray, x_extent: float, y_extent: float) -> None:
    ny, nx = pore_mask.shape
    x = (np.arange(nx) + 0.5) * x_extent / nx
    y = (np.arange(ny) + 0.5) * y_extent / ny
    ax.contour(
        x,
        y,
        pore_mask.astype(float),
        levels=[0.5],
        colors="#8a8a8a",
        linewidths=0.35,
        alpha=0.45,
    )


def profile_error_metrics(candidate: np.ndarray, reference: np.ndarray) -> tuple[float, float]:
    diff = candidate - reference
    valid = np.isfinite(diff)
    if not np.any(valid):
        return np.nan, np.nan
    return (
        float(np.nanmean(np.abs(diff[valid]))),
        float(np.sqrt(np.nanmean(diff[valid] ** 2))),
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolved-snappy-case", required=True)
    parser.add_argument("--dbs-smoothsurface-case", required=True)
    parser.add_argument("--time", default="200")
    parser.add_argument("--asurf-time", default=None)
    parser.add_argument("--cin", type=float, default=1e-4)
    parser.add_argument("--nx", type=int, default=600)
    parser.add_argument("--ny", type=int, default=600)
    parser.add_argument("--res", type=float, default=3e-5)
    parser.add_argument("--detail-xmin-mm", type=float, default=0.0)
    parser.add_argument("--detail-xmax-mm", type=float, default=7.2)
    parser.add_argument("--detail-ymin-mm", type=float, default=3.6)
    parser.add_argument("--detail-ymax-mm", type=float, default=10.8)
    parser.add_argument("--output-png", required=True)
    parser.add_argument("--output-metrics", default=None)
    args = parser.parse_args()

    # The 10.2-inch source prints at 4.64 inches. Typography is therefore
    # authored at 16 pt or larger to retain at least 7 pt in the SI.
    plt.rcParams.update(
        {
            "font.size": 16,
            "axes.labelsize": 16,
            "xtick.labelsize": 15,
            "ytick.labelsize": 15,
        }
    )

    time_name = args.time
    asurf_time_name = args.asurf_time or time_name
    res_mm = args.res * 1e3
    x_extent = args.nx * res_mm
    y_extent = args.ny * res_mm
    resolved_snappy_case = Path(args.resolved_snappy_case)
    dbs_smooth_case = Path(args.dbs_smoothsurface_case)

    theta_smooth = assemble_parallel_structured(dbs_smooth_case, "0", "eps")
    pore_mask_smooth = theta_smooth > 1.0e-3

    smooth_sr = assemble_parallel_structured(dbs_smooth_case, time_name, "Sr+2") / args.cin
    smooth_sorbed = assemble_parallel_structured(dbs_smooth_case, time_name, "Surf_aSr+")
    smooth_asurf = assemble_structured_with_fallback(dbs_smooth_case, asurf_time_name, "0", "aSurf")
    smooth_volumes = assemble_parallel_structured(dbs_smooth_case, "0", "V")

    snappy_x, snappy_y, snappy_sr_vals = gather_parallel_unstructured(resolved_snappy_case, time_name, "Sr+2")
    snappy_sr = points_to_grid(snappy_x, snappy_y, snappy_sr_vals / args.cin, args.nx, args.ny, args.res)
    snappy_pore_mask = np.isfinite(snappy_sr)
    snappy_wall_segments, _ = boundary_patch_segments(
        resolved_snappy_case,
        time_name,
    )
    snappy_wall_segments_mm = snappy_wall_segments * 1e3
    area_x, area_y, snappy_asurf = gather_parallel_unstructured(
        resolved_snappy_case, "0", "aSurf", centers_time=time_name
    )
    _, _, snappy_volumes = gather_parallel_unstructured(
        resolved_snappy_case, "0", "V", centers_time=time_name
    )
    _, _, snappy_sorbed_density = gather_parallel_unstructured(
        resolved_snappy_case, time_name, "Surf_aSr+"
    )
    snappy_area_values = snappy_asurf * snappy_volumes
    snappy_sorbed_values = snappy_sorbed_density * snappy_area_values
    snappy_area_grid = points_to_sum_grid(
        area_x, area_y, snappy_area_values, args.nx, args.ny, args.res
    )
    snappy_sorbed_inventory = points_to_sum_grid(
        area_x, area_y, snappy_sorbed_values, args.nx, args.ny, args.res
    )
    smooth_sorbed_inventory = dbs_inventory_grid(
        smooth_sorbed, smooth_asurf, pore_mask_smooth, smooth_volumes
    )
    smooth_area_grid = np.where(
        pore_mask_smooth & (smooth_asurf > 0.0), smooth_asurf * smooth_volumes, 0.0
    )

    sr_fields = [
        np.ma.masked_invalid(snappy_sr),
        masked_structured(smooth_sr, pore_mask_smooth),
    ]
    pore_masks = [
        snappy_pore_mask,
        pore_mask_smooth,
    ]
    area_fields = [
        masked_nonzero(snappy_area_grid),
        masked_nonzero(smooth_area_grid),
    ]
    sorbed_fields = [
        masked_nonzero(snappy_sorbed_inventory),
        masked_nonzero(smooth_sorbed_inventory),
    ]

    column_titles = [
        "snappyHexMesh",
        "DBS smooth interface",
    ]

    sr_vmin = 0.0
    sr_vmax = max(float(np.nanmax(np.ma.filled(field, np.nan))) for field in sr_fields)
    area_vmax = nonzero_percentile_limit(area_fields[0], 99.5)
    sorbed_vmax = nonzero_percentile_limit(sorbed_fields[0], 99.5)
    area_norm = Normalize(vmin=0.0, vmax=area_vmax)
    sorbed_norm = Normalize(vmin=0.0, vmax=sorbed_vmax)

    sr_cmap = plt.get_cmap("viridis").copy()
    sr_cmap.set_bad(color="#d9d9d9")
    area_cmap = plt.get_cmap("cividis").copy()
    area_cmap.set_bad(color=(0.0, 0.0, 0.0, 0.0))
    area_cmap.set_over("#ff4b5c")
    sorbed_cmap = plt.get_cmap("magma").copy()
    sorbed_cmap.set_bad(color=(0.0, 0.0, 0.0, 0.0))
    sorbed_cmap.set_over("#00d5ff")

    fig = plt.figure(figsize=(10.2, 13.8), constrained_layout=False)
    panel = 0.31
    col_x = [0.10, 0.54]
    row_y = [0.695, 0.385, 0.075]

    top_axes = np.empty((3, 2), dtype=object)
    im_sr = None
    im_area = None
    im_sorbed = None
    for col, title in enumerate(column_titles):
        ax_sr = fig.add_axes([col_x[col], row_y[0], panel, panel])
        ax_area = fig.add_axes([col_x[col], row_y[1], panel, panel])
        ax_sorbed = fig.add_axes([col_x[col], row_y[2], panel, panel])
        top_axes[0, col] = ax_sr
        top_axes[1, col] = ax_area
        top_axes[2, col] = ax_sorbed

        im_sr = ax_sr.imshow(
            sr_fields[col],
            origin="lower",
            extent=(0.0, x_extent, 0.0, y_extent),
            cmap=sr_cmap,
            vmin=sr_vmin,
            vmax=sr_vmax,
            interpolation="nearest",
            aspect="equal",
        )
        ax_sr.add_patch(
            Rectangle(
                (args.detail_xmin_mm, args.detail_ymin_mm),
                args.detail_xmax_mm - args.detail_xmin_mm,
                args.detail_ymax_mm - args.detail_ymin_mm,
                fill=False,
                edgecolor="white",
                linewidth=1.2,
                linestyle="--",
                alpha=0.95,
            )
        )
        for ax in (ax_area, ax_sorbed):
            ax.set_facecolor("black")
        im_area = ax_area.imshow(
            area_fields[col],
            origin="lower",
            extent=(0.0, x_extent, 0.0, y_extent),
            cmap=area_cmap,
            norm=area_norm,
            interpolation="nearest",
            aspect="equal",
        )
        im_sorbed = ax_sorbed.imshow(
            sorbed_fields[col],
            origin="lower",
            extent=(0.0, x_extent, 0.0, y_extent),
            cmap=sorbed_cmap,
            norm=sorbed_norm,
            interpolation="nearest",
            aspect="equal",
        )
        if col == 0 and snappy_wall_segments_mm.size:
            ax_sr.add_collection(
                LineCollection(
                    snappy_wall_segments_mm,
                    colors="#111111",
                    linewidths=0.55,
                    alpha=0.9,
                )
            )

        for ax in (ax_sr,):
            ax.set_xlim(0.0, x_extent)
            ax.set_ylim(0.0, y_extent)
            ax.set_aspect("equal", adjustable="box")
            ax.set_box_aspect(1)
            ax.set_xlabel("x [mm]")
            ax.set_ylabel("y [mm]")
            add_scale_bar(ax, x_extent, y_extent)
        for ax in (ax_area, ax_sorbed):
            ax.set_xlim(args.detail_xmin_mm, args.detail_xmax_mm)
            ax.set_ylim(args.detail_ymin_mm, args.detail_ymax_mm)
            ax.set_aspect("equal", adjustable="box")
            ax.set_box_aspect(1)
            ax.set_xlabel("x [mm]")
            ax.set_ylabel("y [mm]")
            add_axis_scale_bar(ax)

        ax_sr.set_title(title, fontsize=17, pad=8)
        for ax in (ax_sr, ax_area, ax_sorbed):
            ax.tick_params(labelsize=16, length=5, width=1.0)

    top_axes[0, 0].text(
        0.025,
        row_y[0] + 0.5 * panel,
        r"Aqueous Sr/$C_{\mathrm{in}}$",
        transform=fig.transFigure,
        rotation=90,
        ha="center",
        va="center",
        fontsize=16,
    )
    top_axes[1, 0].text(
        0.025,
        row_y[1] + 0.5 * panel,
        r"Reactive area detail [m$^2$ cell$^{-1}$]",
        transform=fig.transFigure,
        rotation=90,
        ha="center",
        va="center",
        fontsize=16,
    )
    top_axes[2, 0].text(
        0.025,
        row_y[2] + 0.5 * panel,
        "Sorbed inventory detail",
        transform=fig.transFigure,
        rotation=90,
        ha="center",
        va="center",
        fontsize=16,
    )

    cbar_sr = fig.colorbar(im_sr, cax=fig.add_axes([0.880, row_y[0], 0.020, panel]))
    cbar_sr.set_label(r"Sr/$C_{\mathrm{in}}$", fontsize=16)
    cbar_area = fig.colorbar(im_area, cax=fig.add_axes([0.880, row_y[1], 0.020, panel]), extend="max")
    cbar_area.set_label(r"$a_{\mathrm{surf}} V$ [m$^2$ cell$^{-1}$]", fontsize=16)
    cbar_sorbed = fig.colorbar(im_sorbed, cax=fig.add_axes([0.880, row_y[2], 0.020, panel]), extend="max")
    cbar_sorbed.set_label(r"$n_{\mathrm{Surf\_aSr+}}$ [kmol cell$^{-1}$]", fontsize=16)
    for cbar in (cbar_sr, cbar_area, cbar_sorbed):
        cbar.ax.tick_params(labelsize=16, length=5, width=1.0)

    output_png = Path(args.output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=220)
    plt.close(fig)

    smooth_sr_raw = assemble_parallel_structured(dbs_smooth_case, time_name, "Sr+2")
    _, _, snappy_sr_raw = gather_parallel_unstructured(
        resolved_snappy_case, time_name, "Sr+2"
    )
    metrics = {
        "time_s": float(time_name),
        "resolved_snappy": {
            "surface_area_m2": float(np.sum(snappy_area_values)),
            "sorbed_inventory_kmol": float(np.sum(snappy_sorbed_values)),
            "dissolved_inventory_kmol": float(np.sum(snappy_sr_raw * snappy_volumes)),
        },
        "dbs_smoothsurface": {
            "surface_area_m2": float(np.sum(smooth_area_grid)),
            "sorbed_inventory_kmol": float(np.sum(smooth_sorbed_inventory)),
            "dissolved_inventory_kmol": float(
                np.sum(theta_smooth * smooth_sr_raw * smooth_volumes)
            ),
        },
    }
    reference = metrics["resolved_snappy"]
    candidate = metrics["dbs_smoothsurface"]
    metrics["relative_errors_percent"] = {
        name: 100.0 * (candidate[name] - reference[name]) / reference[name]
        for name in ("surface_area_m2", "sorbed_inventory_kmol", "dissolved_inventory_kmol")
    }
    snappy_profile = mean_profile_over_pore(snappy_sr)
    smooth_profile = mean_profile_over_pore(masked_structured(smooth_sr, pore_mask_smooth).filled(np.nan))
    snappy_x_profile = (np.arange(snappy_profile.size) + 0.5) / snappy_profile.size
    smooth_x_profile = (np.arange(smooth_profile.size) + 0.5) / smooth_profile.size
    valid_smooth = np.isfinite(smooth_profile)
    smooth_on_snappy = np.interp(
        snappy_x_profile,
        smooth_x_profile[valid_smooth],
        smooth_profile[valid_smooth],
    )
    metrics["aqueous_profile_l1_percent"] = float(
        100.0 * np.nanmean(np.abs(smooth_on_snappy - snappy_profile))
    )
    metrics_path = Path(args.output_metrics) if args.output_metrics else output_png.with_suffix(".json")
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n")


if __name__ == "__main__":
    main()
