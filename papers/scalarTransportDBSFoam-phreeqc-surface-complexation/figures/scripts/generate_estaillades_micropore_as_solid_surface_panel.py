#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

import vtk
import pyvista.plotting._vtk as _pv_vtk

_pv_vtk.vtkRenderWindow = vtk.vtkEGLRenderWindow
import pyvista as pv

from generate_3d_volume_render_pyvista import (
    add_interface_surface_panel,
    build_interface_surface_mesh,
    load_inlet_connected_pore_mask,
    prepared_field,
    stitch_parallel_scalar,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render only panel (d) for the binary Estaillades comparison using the true pore-solid interface surface."
    )
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--time-name", required=True)
    parser.add_argument("--surface-field", default="Surf_aSr+")
    parser.add_argument("--geometry-field", default="eps")
    parser.add_argument("--surface-mask-field", default="aSurf")
    parser.add_argument("--surface-floor", type=float, default=0.0)
    parser.add_argument("--surface-log-scale", action="store_true")
    parser.add_argument("--surface-title", default="Surf_aSr+")
    parser.add_argument("--lower-quantile", type=float, default=0.01)
    parser.add_argument("--upper-quantile", type=float, default=0.995)
    parser.add_argument("--pore-threshold", type=float, default=0.9)
    parser.add_argument("--connectivity-image", type=Path, default=None)
    parser.add_argument("--connectivity-pore-value", type=int, default=1)
    parser.add_argument("--connectivity-remap-from", type=int, default=None)
    parser.add_argument("--connectivity-remap-to", type=int, default=None)
    parser.add_argument("--surface-interface-clip-fraction", type=float, default=0.60)
    parser.add_argument("--surface-projection-radius", type=float, default=0.95)
    parser.add_argument("--clip-xmax-frac", type=float, default=1.0)
    parser.add_argument("--clip-ymin-frac", type=float, default=0.0)
    parser.add_argument("--clip-zmax-frac", type=float, default=1.0)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    pv.OFF_SCREEN = True

    surface, nx, ny, nz = stitch_parallel_scalar(args.case_dir, args.time_name, args.surface_field)
    geometry_field, gx, gy, gz = stitch_parallel_scalar(
        args.case_dir, args.time_name, args.geometry_field
    )
    if (gx, gy, gz) != (nx, ny, nz):
        raise RuntimeError("Geometry field mesh does not match")

    mask_values, mx, my, mz = stitch_parallel_scalar(
        args.case_dir, args.time_name, args.surface_mask_field
    )
    if (mx, my, mz) != (nx, ny, nz):
        raise RuntimeError("Surface mask field mesh does not match")

    if args.surface_floor > 0.0:
        surface = surface.copy()
        surface[surface < args.surface_floor] = 0.0

    surface_display, surface_clim = prepared_field(
        surface,
        lower_q=args.lower_quantile,
        upper_q=args.upper_quantile,
        log_scale=args.surface_log_scale,
        zero_mask=True,
    )

    pore_mask = geometry_field >= args.pore_threshold
    surface_active = mask_values > 0.0
    inlet_connected_mask = None
    if args.connectivity_image is not None:
        inlet_connected_mask = load_inlet_connected_pore_mask(
            args.connectivity_image,
            nx,
            ny,
            nz,
            args.connectivity_pore_value,
            args.connectivity_remap_from,
            args.connectivity_remap_to,
        )
        surface_active &= inlet_connected_mask

    surface_mesh = build_interface_surface_mesh(
        pore_mask=pore_mask,
        values=surface_display,
        active=surface_active,
        nx=nx,
        ny=ny,
        nz=nz,
        connectivity_mask=inlet_connected_mask,
        clip_x_fraction=args.surface_interface_clip_fraction,
        projection_radius=args.surface_projection_radius,
    )
    # Cut away the near/front/top corner so the internal wall loading is visible.
    surface_mesh = surface_mesh.clip_box(
        bounds=(
            0.0,
            args.clip_xmax_frac * nx,
            args.clip_ymin_frac * ny,
            float(ny),
            0.0,
            args.clip_zmax_frac * nz,
        ),
        invert=False,
    )

    plotter = pv.Plotter(shape=(1, 1), off_screen=True, window_size=(1600, 1600))
    scalar_bar_title = args.surface_title
    if args.surface_log_scale:
        scalar_bar_title = f"log10({scalar_bar_title})"
    add_interface_surface_panel(
        plotter=plotter,
        surface_mesh=surface_mesh,
        subplot=(0, 0),
        title=args.surface_title,
        scalar_bar_title=scalar_bar_title,
        cmap="magma",
        clim=surface_clim,
        nx=nx,
        ny=ny,
        nz=nz,
        panel_label="(d)",
        scalar_bar_fmt="%.0f" if args.surface_log_scale else "%.1f",
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    plotter.screenshot(str(args.output))


if __name__ == "__main__":
    main()
