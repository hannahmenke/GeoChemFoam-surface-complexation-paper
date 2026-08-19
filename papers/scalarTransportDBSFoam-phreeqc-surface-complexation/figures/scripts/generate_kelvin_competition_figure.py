#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
import vtk
import pyvista.plotting._vtk as _pv_vtk

_pv_vtk.vtkRenderWindow = vtk.vtkEGLRenderWindow
import pyvista as pv

from generate_3d_volume_render_pyvista import (
    build_image_data,
    camera_position,
    classify_geometry,
    normalized_field,
    stitch_parallel_scalar,
)


def add_geometry_scene(
    plotter: pv.Plotter,
    labels: np.ndarray,
    nx: int,
    ny: int,
    nz: int,
) -> None:
    plotter.set_background("white")

    image = pv.ImageData(dimensions=(nx + 1, ny + 1, nz + 1))
    image.cell_data["phase"] = labels.flatten(order="F")

    phase_defs = [
        (0, "Solid", "#c94f4f", 0.30),
        (1, "Micropore", "#1a5caa", 0.24),
        (2, "Pore", "#555555", 0.14),
    ]

    for phase_value, name, color, opacity in phase_defs:
        thresholded = image.threshold(
            [phase_value - 0.1, phase_value + 0.1],
            scalars="phase",
            preference="cell",
        )
        if thresholded.n_cells == 0:
            continue
        plotter.add_mesh(
            thresholded.extract_surface(algorithm="dataset_surface"),
            color=color,
            opacity=opacity,
            smooth_shading=False,
            show_scalar_bar=False,
            ambient=0.35,
            diffuse=0.75,
            specular=0.05,
        )

    plotter.add_mesh(
        image.outline(),
        color="#444444",
        line_width=1.0,
        opacity=0.35,
    )
    plotter.show_bounds(
        grid="back",
        location="outer",
        all_edges=False,
        xtitle="x cell",
        ytitle="y cell",
        ztitle="z cell",
        font_size=14,
        color="black",
    )
    plotter.camera_position = camera_position(nx, ny, nz)


def add_volume_scene(
    plotter: pv.Plotter,
    dataset: pv.ImageData,
    title: str,
    nx: int,
    ny: int,
    nz: int,
    cmap: str,
) -> None:
    plotter.set_background("white")
    plotter.add_volume(
        dataset,
        scalars="value",
        cmap=cmap,
        clim=(0.0, 1.0),
        opacity=[0.0, 0.0, 0.03, 0.10, 0.24, 0.45, 0.75, 1.0],
        shade=True,
        ambient=0.25,
        diffuse=0.85,
        specular=0.10,
        scalar_bar_args={
            "title": title,
            "vertical": True,
            "fmt": "%.1f",
            "title_font_size": 22,
            "label_font_size": 18,
            "n_labels": 5,
            "bold": True,
            "position_x": 0.87,
            "position_y": 0.23,
            "height": 0.52,
        },
    )
    plotter.add_mesh(
        dataset.outline(),
        color="#444444",
        line_width=1.0,
        opacity=0.35,
    )
    plotter.show_bounds(
        grid="back",
        location="outer",
        all_edges=False,
        xtitle="x cell",
        ytitle="y cell",
        ztitle="z cell",
        font_size=14,
        color="black",
    )
    plotter.camera_position = camera_position(nx, ny, nz)


def stitch_field_sum(
    case_dir: Path,
    time_name: str,
    field_names: str,
) -> tuple[np.ndarray, int, int, int]:
    names = [name.strip() for name in field_names.split(",") if name.strip()]
    if not names:
        raise ValueError("At least one field name is required")

    total: np.ndarray | None = None
    dims: tuple[int, int, int] | None = None
    for name in names:
        values, nx, ny, nz = stitch_parallel_scalar(case_dir, time_name, name)
        current_dims = (nx, ny, nz)
        if dims is None:
            dims = current_dims
            total = values.copy()
        elif current_dims != dims:
            raise RuntimeError(f"Field mesh mismatch for {name}")
        else:
            total = total + values
    assert total is not None and dims is not None
    return total, *dims


def render_scene(
    plot_builder,
    width: int,
    height: int,
) -> np.ndarray:
    plotter = pv.Plotter(off_screen=True, window_size=(width, height))
    plot_builder(plotter)
    image = plotter.screenshot(return_img=True)
    plotter.close()
    return image


def crop_white_border(image: np.ndarray, pad: int = 10) -> np.ndarray:
    rgb = image[..., :3]
    mask = np.any(rgb < 220, axis=2)
    coords = np.argwhere(mask)
    if coords.size == 0:
        return image

    y0, x0 = coords.min(axis=0)
    y1, x1 = coords.max(axis=0) + 1
    y0 = max(0, y0 - pad)
    x0 = max(0, x0 - pad)
    y1 = min(image.shape[0], y1 + pad)
    x1 = min(image.shape[1], x1 + pad)
    return image[y0:y1, x0:x1]


def add_panel_image(ax, image: np.ndarray, label: str) -> None:
    raise NotImplementedError


def fit_image(image: np.ndarray, target_width: int, target_height: int) -> Image.Image:
    pil = Image.fromarray(image)
    pil.thumbnail((target_width, target_height), Image.Resampling.LANCZOS)
    canvas = Image.new("RGBA", (target_width, target_height), (255, 255, 255, 255))
    x0 = (target_width - pil.width) // 2
    y0 = (target_height - pil.height) // 2
    canvas.paste(pil, (x0, y0))
    return canvas


def panel_label(draw: ImageDraw.ImageDraw, xy: tuple[int, int], text: str) -> None:
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 34
        )
    except OSError:
        font = ImageFont.load_default()
    x0, y0 = xy
    bbox = draw.textbbox((x0, y0), text, font=font)
    draw.rectangle(
        [bbox[0] - 8, bbox[1] - 4, bbox[2] + 8, bbox[3] + 4],
        fill=(255, 255, 255),
    )
    draw.text((x0, y0), text, fill=(0, 0, 0), font=font)


def draw_geometry_legend(draw: ImageDraw.ImageDraw, xy: tuple[int, int]) -> None:
    try:
        font = ImageFont.truetype(
            "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf", 26
        )
    except OSError:
        font = ImageFont.load_default()

    x0, y0 = xy
    entries = [("Micropore", "#1a5caa"), ("Pore", "#555555")]
    line_h = 38
    max_text_w = max(draw.textbbox((0, 0), label, font=font)[2] for label, _ in entries)
    box_w = 34 + max_text_w + 26
    box_h = line_h * len(entries) + 20
    draw.rectangle(
        [x0, y0, x0 + box_w, y0 + box_h],
        fill=(245, 245, 245),
    )

    for idx, (label, color) in enumerate(entries):
        yy = y0 + 10 + idx * line_h
        draw.rectangle([x0 + 12, yy + 7, x0 + 24, yy + 19], fill=color)
        draw.text((x0 + 34, yy), label, fill=color, font=font)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--time-name", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--geometry-field", default="eps")
    parser.add_argument("--target-field", default="Mn+2")
    parser.add_argument("--background-field", default="Mg+2")
    parser.add_argument("--surf-target-fields", default="Hfo_sOMn+,Hfo_wOMn+")
    parser.add_argument("--surf-background-fields", default="Hfo_wOMg+")
    parser.add_argument("--target-label", default="Mn$^{2+}$ / C$_{in}$")
    parser.add_argument("--background-label", default="Mg$^{2+}$ / C$_{init}$")
    parser.add_argument("--surf-target-label", default="$\\Delta$HFO-Mn")
    parser.add_argument("--surf-background-label", default="HFO-Mg loss")
    parser.add_argument("--surface-baseline-time", default="0")
    parser.add_argument("--lower-quantile", type=float, default=0.01)
    parser.add_argument("--upper-quantile", type=float, default=0.995)
    parser.add_argument("--solid-threshold", type=float, default=1.0e-3)
    parser.add_argument("--pore-threshold", type=float, default=0.9)
    args = parser.parse_args()

    pv.OFF_SCREEN = True

    target, nx, ny, nz = stitch_parallel_scalar(
        args.case_dir, args.time_name, args.target_field
    )
    background, cx, cy, cz = stitch_parallel_scalar(
        args.case_dir, args.time_name, args.background_field
    )
    surf_target, sx, sy, sz = stitch_field_sum(
        args.case_dir, args.time_name, args.surf_target_fields
    )
    surf_background, tx, ty, tz = stitch_field_sum(
        args.case_dir, args.time_name, args.surf_background_fields
    )
    baseline_target, bx, by, bz = stitch_field_sum(
        args.case_dir, args.surface_baseline_time, args.surf_target_fields
    )
    baseline_background, ux, uy, uz = stitch_field_sum(
        args.case_dir, args.surface_baseline_time, args.surf_background_fields
    )
    theta, gx, gy, gz = stitch_parallel_scalar(
        args.case_dir, args.time_name, args.geometry_field
    )

    expected = (nx, ny, nz)
    for dims in ((cx, cy, cz), (sx, sy, sz), (tx, ty, tz), (bx, by, bz), (ux, uy, uz), (gx, gy, gz)):
        if dims != expected:
            raise RuntimeError("Field meshes do not match")

    delta_target = np.maximum(surf_target - baseline_target, 0.0)
    delta_background_loss = np.maximum(baseline_background - surf_background, 0.0)
    target_scaled, _ = normalized_field(
        target,
        lower_q=args.lower_quantile,
        upper_q=args.upper_quantile,
        log_scale=False,
        zero_mask=False,
    )
    background_scaled, _ = normalized_field(
        background,
        lower_q=args.lower_quantile,
        upper_q=args.upper_quantile,
        log_scale=False,
        zero_mask=False,
    )
    surf_target_scaled, _ = normalized_field(
        delta_target,
        lower_q=args.lower_quantile,
        upper_q=args.upper_quantile,
        log_scale=False,
        zero_mask=True,
    )
    surf_background_scaled, _ = normalized_field(
        delta_background_loss,
        lower_q=args.lower_quantile,
        upper_q=args.upper_quantile,
        log_scale=False,
        zero_mask=True,
    )

    labels = classify_geometry(
        theta,
        solid_threshold=args.solid_threshold,
        pore_threshold=args.pore_threshold,
    )

    geometry_img = crop_white_border(render_scene(
        lambda plotter: add_geometry_scene(plotter, labels, nx, ny, nz),
        width=1800,
        height=900,
    ), pad=0)
    target_img = crop_white_border(render_scene(
        lambda plotter: add_volume_scene(
            plotter,
            build_image_data(target_scaled),
            args.target_label,
            nx,
            ny,
            nz,
            "cividis",
        ),
        width=1200,
        height=900,
    ), pad=0)
    background_img = crop_white_border(render_scene(
        lambda plotter: add_volume_scene(
            plotter,
            build_image_data(background_scaled),
            args.background_label,
            nx,
            ny,
            nz,
            "viridis",
        ),
        width=1200,
        height=900,
    ), pad=0)
    surf_target_img = crop_white_border(render_scene(
        lambda plotter: add_volume_scene(
            plotter,
            build_image_data(surf_target_scaled),
            args.surf_target_label,
            nx,
            ny,
            nz,
            "magma",
        ),
        width=1200,
        height=900,
    ), pad=0)
    surf_background_img = crop_white_border(render_scene(
        lambda plotter: add_volume_scene(
            plotter,
            build_image_data(surf_background_scaled),
            args.surf_background_label,
            nx,
            ny,
            nz,
            "plasma",
        ),
        width=1200,
        height=900,
    ), pad=0)

    canvas_w = 2200
    gap = 12
    top_w = 1380
    top_h = 640
    cell_w = (canvas_w - 3 * gap) // 2
    cell_h = 760
    canvas_h = top_h + 2 * cell_h + 4 * gap

    canvas = Image.new("RGBA", (canvas_w, canvas_h), (255, 255, 255, 255))
    draw = ImageDraw.Draw(canvas)

    top_x = (canvas_w - top_w) // 2
    top_y = gap
    row1_y = top_y + top_h
    row2_y = row1_y + cell_h + gap
    col1_x = gap
    col2_x = 2 * gap + cell_w

    canvas.paste(fit_image(geometry_img, top_w, top_h), (top_x, top_y))
    canvas.paste(fit_image(target_img, cell_w, cell_h), (col1_x, row1_y))
    canvas.paste(fit_image(background_img, cell_w, cell_h), (col2_x, row1_y))
    canvas.paste(fit_image(surf_target_img, cell_w, cell_h), (col1_x, row2_y))
    canvas.paste(fit_image(surf_background_img, cell_w, cell_h), (col2_x, row2_y))

    panel_label(draw, (top_x + 20, top_y + 16), "(a)")
    panel_label(draw, (col1_x + 18, row1_y + 14), "(b)")
    panel_label(draw, (col2_x + 18, row1_y + 14), "(c)")
    panel_label(draw, (col1_x + 18, row2_y + 14), "(d)")
    panel_label(draw, (col2_x + 18, row2_y + 14), "(e)")
    draw_geometry_legend(draw, (top_x + 120, top_y + top_h - 86))

    args.output.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(args.output)


if __name__ == "__main__":
    main()
