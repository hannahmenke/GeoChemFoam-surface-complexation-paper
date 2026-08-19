#!/usr/bin/env python3

from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path

import matplotlib
import numpy as np
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import TwoSlopeNorm

from generate_hm12_fourcase_conc_sorbed_diff import assemble_parallel_structured, boundary_patch_segments
from generate_micromodel_surface_area_validation import assemble_structured_with_fallback, wall_inventory_grid


@dataclass(frozen=True)
class ClipBox:
    name: str
    x0_mm: float
    x1_mm: float
    y0_mm: float
    y1_mm: float

    def to_index_bounds(self, res_mm: float, nx: int, ny: int) -> tuple[int, int, int, int]:
        ix0 = max(0, min(nx, int(np.floor(self.x0_mm / res_mm))))
        ix1 = max(0, min(nx, int(np.ceil(self.x1_mm / res_mm))))
        iy0 = max(0, min(ny, int(np.floor(self.y0_mm / res_mm))))
        iy1 = max(0, min(ny, int(np.ceil(self.y1_mm / res_mm))))
        if ix1 <= ix0 or iy1 <= iy0:
            raise ValueError(f"Clip '{self.name}' is empty after discretization")
        return ix0, ix1, iy0, iy1


PRESET_CLIPS: dict[str, list[ClipBox]] = {
    "bad_fronts": [
        ClipBox("front_a", 3.0, 4.2, 5.4, 6.6),
        ClipBox("front_b", 2.4, 3.6, 5.4, 6.6),
        ClipBox("front_f", 4.2, 5.4, 6.6, 7.8),
    ],
}


def parse_clip(spec: str) -> ClipBox:
    parts = [part.strip() for part in spec.split(",")]
    if len(parts) != 5:
        raise argparse.ArgumentTypeError("clip must be NAME,x0_mm,x1_mm,y0_mm,y1_mm")
    try:
        x0_mm, x1_mm, y0_mm, y1_mm = [float(value) for value in parts[1:]]
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            "clip bounds must be numeric: NAME,x0_mm,x1_mm,y0_mm,y1_mm"
        ) from exc
    if x1_mm <= x0_mm or y1_mm <= y0_mm:
        raise argparse.ArgumentTypeError("clip bounds must satisfy x1>x0 and y1>y0")
    return ClipBox(parts[0], x0_mm, x1_mm, y0_mm, y1_mm)


def clip_segments_mm(segments_mm: np.ndarray, clip: ClipBox) -> np.ndarray:
    if segments_mm.size == 0:
        return np.empty((0, 2, 2), dtype=float)
    mins = np.minimum(segments_mm[:, 0, :], segments_mm[:, 1, :])
    maxs = np.maximum(segments_mm[:, 0, :], segments_mm[:, 1, :])
    overlap = (
        (maxs[:, 0] >= clip.x0_mm)
        & (mins[:, 0] <= clip.x1_mm)
        & (maxs[:, 1] >= clip.y0_mm)
        & (mins[:, 1] <= clip.y1_mm)
    )
    return segments_mm[overlap]


def clip_field(field: np.ndarray, bounds: tuple[int, int, int, int]) -> np.ndarray:
    ix0, ix1, iy0, iy1 = bounds
    return field[iy0:iy1, ix0:ix1]


def add_local_scale_bar(ax, clip: ClipBox, length_mm: float = 0.5) -> None:
    width = clip.x1_mm - clip.x0_mm
    height = clip.y1_mm - clip.y0_mm
    x0 = clip.x0_mm + 0.08 * width
    y0 = clip.y0_mm + 0.08 * height
    ax.plot([x0, x0 + length_mm], [y0, y0], color="white", lw=2.4, solid_capstyle="butt")
    ax.text(
        x0 + 0.5 * length_mm,
        y0 + 0.06 * height,
        f"{length_mm:g} mm",
        color="white",
        ha="center",
        va="bottom",
        fontsize=7,
        bbox=dict(facecolor="black", alpha=0.35, edgecolor="none", pad=1.0),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render local wall-support and aSurf mismatch overlays for selected micromodel boxes."
    )
    parser.add_argument("--legacy-snappy-case", required=True)
    parser.add_argument("--dbs-gradeps-case", required=True)
    parser.add_argument("--dbs-smoothsurface-case", required=True)
    parser.add_argument("--time", default="200")
    parser.add_argument("--nx", type=int, default=600)
    parser.add_argument("--ny", type=int, default=600)
    parser.add_argument("--res", type=float, default=3e-5)
    parser.add_argument("--preset", choices=sorted(PRESET_CLIPS), default="bad_fronts")
    parser.add_argument(
        "--clip",
        action="append",
        type=parse_clip,
        default=None,
        help="NAME,x0_mm,x1_mm,y0_mm,y1_mm; may be repeated",
    )
    parser.add_argument("--output-png", required=True)
    args = parser.parse_args()

    clips = list(PRESET_CLIPS[args.preset])
    if args.clip:
        clips.extend(args.clip)

    res_mm = args.res * 1e3
    cell_volume = args.res ** 3

    legacy_snappy_case = Path(args.legacy_snappy_case)
    dbs_gradeps_case = Path(args.dbs_gradeps_case)
    dbs_smooth_case = Path(args.dbs_smoothsurface_case)

    theta_gradeps = assemble_parallel_structured(dbs_gradeps_case, "0", "theta")
    pore_mask_gradeps = theta_gradeps > 0.5
    theta_smooth = assemble_parallel_structured(dbs_smooth_case, "0", "theta")
    pore_mask_smooth = theta_smooth > 0.5

    gradeps_asurf = assemble_structured_with_fallback(dbs_gradeps_case, args.time, "0", "aSurf")
    smooth_asurf = assemble_structured_with_fallback(dbs_smooth_case, args.time, "0", "aSurf")

    gradeps_area_grid = np.where(
        pore_mask_gradeps & (gradeps_asurf > 0.0), gradeps_asurf * cell_volume, 0.0
    )
    smooth_area_grid = np.where(
        pore_mask_smooth & (smooth_asurf > 0.0), smooth_asurf * cell_volume, 0.0
    )

    snappy_wall_segments, _ = boundary_patch_segments(legacy_snappy_case, args.time, None)
    snappy_wall_segments_mm = snappy_wall_segments * 1e3
    snappy_support_grid = wall_inventory_grid(
        snappy_wall_segments,
        np.ones(snappy_wall_segments.shape[0], dtype=float),
        args.nx,
        args.ny,
        args.res,
    )
    area_vmax = max(
        float(np.nanmax(snappy_support_grid)),
        float(np.nanmax(gradeps_area_grid)),
        float(np.nanmax(smooth_area_grid)),
    )
    diff_vmax = max(
        float(np.nanmax(np.abs(gradeps_area_grid - snappy_support_grid))),
        float(np.nanmax(np.abs(smooth_area_grid - snappy_support_grid))),
    )
    if diff_vmax <= 0.0:
        diff_vmax = 1.0

    support_cmap = plt.get_cmap("Greys").copy()
    area_cmap = plt.get_cmap("magma").copy()
    diff_cmap = plt.get_cmap("RdBu_r").copy()
    diff_norm = TwoSlopeNorm(vmin=-diff_vmax, vcenter=0.0, vmax=diff_vmax)

    column_titles = [
        "snappy wall support",
        r"DBS $|\nabla \varepsilon|$ aSurf",
        "smoothSurface aSurf",
        r"$|\nabla \varepsilon|$ - snappy",
        "smoothSurface - snappy",
    ]

    fig, axes = plt.subplots(
        len(clips),
        len(column_titles),
        figsize=(16.0, 3.2 * len(clips)),
        constrained_layout=True,
        squeeze=False,
    )

    im_area = None
    im_diff = None
    im_support = None

    for row, clip in enumerate(clips):
        bounds = clip.to_index_bounds(res_mm, args.nx, args.ny)
        ix0, ix1, iy0, iy1 = bounds
        extent = (clip.x0_mm, clip.x1_mm, clip.y0_mm, clip.y1_mm)

        support_clip = clip_field(snappy_support_grid, bounds)
        gradeps_clip = clip_field(gradeps_area_grid, bounds)
        smooth_clip = clip_field(smooth_area_grid, bounds)
        gradeps_diff = clip_field(gradeps_area_grid - snappy_support_grid, bounds)
        smooth_diff = clip_field(smooth_area_grid - snappy_support_grid, bounds)
        local_segments = clip_segments_mm(snappy_wall_segments_mm, clip)

        panel_data = [
            (support_clip, support_cmap, 0.0, 1.0, None),
            (gradeps_clip, area_cmap, 0.0, area_vmax, None),
            (smooth_clip, area_cmap, 0.0, area_vmax, None),
            (gradeps_diff, diff_cmap, None, None, diff_norm),
            (smooth_diff, diff_cmap, None, None, diff_norm),
        ]

        for col, (field, cmap, vmin, vmax, norm) in enumerate(panel_data):
            ax = axes[row, col]
            im = ax.imshow(
                field,
                origin="lower",
                extent=extent,
                cmap=cmap,
                vmin=vmin,
                vmax=vmax,
                norm=norm,
                interpolation="nearest",
                aspect="equal",
            )
            if col == 0:
                im_support = im
            elif col in (1, 2):
                im_area = im
            else:
                im_diff = im

            if local_segments.size:
                line_color = "#00d4ff" if col == 0 else "white"
                ax.add_collection(
                    LineCollection(local_segments, colors=line_color, linewidths=0.8, alpha=0.95)
                )

            ax.set_xlim(clip.x0_mm, clip.x1_mm)
            ax.set_ylim(clip.y0_mm, clip.y1_mm)
            ax.set_xlabel("x [mm]")
            if col == 0:
                ax.set_ylabel(f"{clip.name}\ny [mm]")
            else:
                ax.set_ylabel("y [mm]")
            if row == 0:
                ax.set_title(column_titles[col])
            add_local_scale_bar(ax, clip, length_mm=0.5)

    cbar_support = fig.colorbar(im_support, ax=axes[:, 0].tolist(), location="right", shrink=0.92, pad=0.01)
    cbar_support.set_label("snappy wall support")
    cbar_area = fig.colorbar(im_area, ax=axes[:, 1:3].ravel().tolist(), location="right", shrink=0.92, pad=0.01)
    cbar_area.set_label(r"local area per cell [m$^2$]")
    cbar_diff = fig.colorbar(im_diff, ax=axes[:, 3:].ravel().tolist(), location="right", shrink=0.92, pad=0.01)
    cbar_diff.set_label(r"signed area mismatch [m$^2$]")

    output_png = Path(args.output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=240)
    plt.close(fig)


if __name__ == "__main__":
    main()
