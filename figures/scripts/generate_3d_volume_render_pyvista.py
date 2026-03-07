#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np
import vtk
import pyvista.plotting._vtk as _pv_vtk
_pv_vtk.vtkRenderWindow = vtk.vtkEGLRenderWindow
import pyvista as pv


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


def stitch_parallel_scalar(
    case_dir: Path, time_name: str, field_name: str
) -> tuple[np.ndarray, int, int, int]:
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
                        f"{field_name} length mismatch in processor{pid}: "
                        f"expected {expected}, got {len(local_values)}"
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

    array = np.asarray(global_values, dtype=float).reshape((nx, ny, nz), order="F")
    return array, nx, ny, nz


def normalized_field(
    values: np.ndarray,
    lower_q: float,
    upper_q: float,
    log_scale: bool,
    zero_mask: bool,
) -> tuple[np.ndarray, tuple[float, float]]:
    field = values.astype(float).copy()

    if zero_mask:
        active = field > 0.0
    else:
        active = np.isfinite(field)

    if not np.any(active):
        return np.zeros_like(field), (0.0, 1.0)

    working = field[active]
    if log_scale:
        floor = max(np.min(working[working > 0.0]), 1.0e-300)
        transformed = np.zeros_like(field)
        transformed[active] = np.log10(np.maximum(field[active], floor))
        field = transformed
        working = field[active]

    low = float(np.quantile(working, lower_q))
    high = float(np.quantile(working, upper_q))
    if high <= low:
        high = float(np.max(working))
    if high <= low:
        high = low + 1.0

    scaled = np.zeros_like(field)
    scaled[active] = np.clip((field[active] - low) / (high - low), 0.0, 1.0)
    return scaled, (low, high)


def build_image_data(values: np.ndarray) -> pv.ImageData:
    nx, ny, nz = values.shape
    image = pv.ImageData(dimensions=(nx + 1, ny + 1, nz + 1))
    image.cell_data["value"] = values.flatten(order="F")
    return image


def classify_geometry(
    theta: np.ndarray, solid_threshold: float, pore_threshold: float
) -> np.ndarray:
    labels = np.ones_like(theta, dtype=np.uint8)
    labels[theta <= solid_threshold] = 0
    labels[theta >= pore_threshold] = 2
    return labels


def add_geometry_panel(
    plotter: pv.Plotter,
    labels: np.ndarray,
    subplot: tuple[int, int],
    nx: int,
    ny: int,
    nz: int,
) -> None:
    plotter.subplot(*subplot)
    plotter.set_background("white")

    image = pv.ImageData(dimensions=(nx + 1, ny + 1, nz + 1))
    image.cell_data["phase"] = labels.flatten(order="F")

    phase_defs = [
        (0, "solid", "#c94f4f", 0.28),
        (1, "micropore", "#4f8fd6", 0.22),
        (2, "pore", "#ffffff", 0.14),
    ]

    for phase_value, _, color, opacity in phase_defs:
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
    plotter.add_text("Geometry", position="upper_left", font_size=15, color="black")
    plotter.show_bounds(
        grid="back",
        location="outer",
        all_edges=False,
        xtitle="x cell",
        ytitle="y cell",
        ztitle="z cell",
        font_size=12,
        color="black",
    )
    plotter.camera_position = camera_position(nx, ny, nz)


def camera_position(nx: int, ny: int, nz: int) -> list[tuple[float, float, float]]:
    centre = (0.5 * nx, 0.5 * ny, 0.5 * nz)
    position = (2.1 * nx, -1.65 * ny, 1.45 * nz)
    view_up = (0.0, 0.0, 1.0)
    return [position, centre, view_up]


def add_volume_panel(
    plotter: pv.Plotter,
    dataset: pv.ImageData,
    subplot: tuple[int, int],
    title: str,
    scalar_bar_title: str,
    cmap: str,
    nx: int,
    ny: int,
    nz: int,
) -> None:
    plotter.subplot(*subplot)
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
            "title": scalar_bar_title,
            "vertical": True,
            "fmt": "%.1f",
            "title_font_size": 15,
            "label_font_size": 12,
        },
    )
    plotter.add_mesh(
        dataset.outline(),
        color="#444444",
        line_width=1.0,
        opacity=0.35,
    )
    plotter.add_text(title, position="upper_left", font_size=15, color="black")
    plotter.show_bounds(
        grid="back",
        location="outer",
        all_edges=False,
        xtitle="x cell",
        ytitle="y cell",
        ztitle="z cell",
        font_size=12,
        color="black",
    )
    plotter.camera_position = camera_position(nx, ny, nz)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--time-name", required=True)
    parser.add_argument("--aqueous-field", default="Ca+2")
    parser.add_argument("--surface-field", default="Surf_aCa+")
    parser.add_argument("--geometry-field", default="theta")
    parser.add_argument("--surface-baseline-time")
    parser.add_argument("--surface-floor", type=float, default=0.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="3D DBS Surface Complexation")
    parser.add_argument("--lower-quantile", type=float, default=0.01)
    parser.add_argument("--upper-quantile", type=float, default=0.995)
    parser.add_argument("--surface-log-scale", action="store_true")
    parser.add_argument("--solid-threshold", type=float, default=1.0e-3)
    parser.add_argument("--pore-threshold", type=float, default=0.9)
    parser.add_argument("--aqueous-title", default=None)
    parser.add_argument("--surface-title", default=None)
    args = parser.parse_args()

    pv.OFF_SCREEN = True

    aqueous, nx, ny, nz = stitch_parallel_scalar(
        args.case_dir, args.time_name, args.aqueous_field
    )
    surface, sx, sy, sz = stitch_parallel_scalar(
        args.case_dir, args.time_name, args.surface_field
    )
    geometry_field, gx, gy, gz = stitch_parallel_scalar(
        args.case_dir, args.time_name, args.geometry_field
    )
    if (sx, sy, sz) != (nx, ny, nz):
        raise RuntimeError("Field meshes do not match")
    if (gx, gy, gz) != (nx, ny, nz):
        raise RuntimeError("Geometry field mesh does not match")

    if args.surface_baseline_time:
        surface_baseline, bx, by, bz = stitch_parallel_scalar(
            args.case_dir, args.surface_baseline_time, args.surface_field
        )
        if (bx, by, bz) != (nx, ny, nz):
            raise RuntimeError("Surface baseline field mesh does not match")
        surface = np.maximum(surface - surface_baseline, 0.0)

    if args.surface_floor > 0.0:
        surface = np.where(surface >= args.surface_floor, surface, 0.0)

    aqueous_scaled, _ = normalized_field(
        aqueous,
        lower_q=args.lower_quantile,
        upper_q=args.upper_quantile,
        log_scale=False,
        zero_mask=False,
    )
    surface_scaled, _ = normalized_field(
        surface,
        lower_q=args.lower_quantile,
        upper_q=args.upper_quantile,
        log_scale=args.surface_log_scale,
        zero_mask=True,
    )
    geometry_labels = classify_geometry(
        geometry_field,
        solid_threshold=args.solid_threshold,
        pore_threshold=args.pore_threshold,
    )

    aqueous_img = build_image_data(aqueous_scaled)
    surface_img = build_image_data(surface_scaled)

    plotter = pv.Plotter(shape=(1, 3), off_screen=True, window_size=(2520, 820))

    add_geometry_panel(
        plotter=plotter,
        labels=geometry_labels,
        subplot=(0, 0),
        nx=nx,
        ny=ny,
        nz=nz,
    )

    aq_title = args.aqueous_title if args.aqueous_title else f"{args.aqueous_field} / C_in  (t = {args.time_name})"
    aq_bar = args.aqueous_title if args.aqueous_title else f"Norm. {args.aqueous_field} / C_in"
    surf_title = args.surface_title if args.surface_title else f"\u0394{args.surface_field}  (t = {args.time_name})"
    surf_bar = args.surface_title if args.surface_title else f"Norm. \u0394{args.surface_field}"

    add_volume_panel(
        plotter=plotter,
        dataset=aqueous_img,
        subplot=(0, 1),
        title=aq_title,
        scalar_bar_title=aq_bar,
        cmap="cividis",
        nx=nx,
        ny=ny,
        nz=nz,
    )
    add_volume_panel(
        plotter=plotter,
        dataset=surface_img,
        subplot=(0, 2),
        title=surf_title,
        scalar_bar_title=surf_bar,
        cmap="magma",
        nx=nx,
        ny=ny,
        nz=nz,
    )

    plotter.link_views()
    plotter.screenshot(str(args.output))


if __name__ == "__main__":
    main()
