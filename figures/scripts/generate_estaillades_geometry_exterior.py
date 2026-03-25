#!/usr/bin/env python3

from __future__ import annotations

import argparse
from pathlib import Path

from matplotlib.colors import ListedColormap
import numpy as np
import vtk
import pyvista.plotting._vtk as _pv_vtk

_pv_vtk.vtkRenderWindow = vtk.vtkEGLRenderWindow
import pyvista as pv

from generate_3d_volume_render_pyvista import (
    camera_position,
    classify_geometry,
    stitch_parallel_scalar,
)


PHASE_CMAP = ListedColormap(["#fafafa", "#9a9a9a", "#111111"])


def make_face_mesh(labels_2d: np.ndarray, axis: str, index: int, nx: int, ny: int, nz: int) -> pv.StructuredGrid:
    if axis == "x":
        nu, nv = ny, nz
        y, z = np.meshgrid(np.arange(nu + 1), np.arange(nv + 1), indexing="ij")
        x = np.full_like(y, index, dtype=np.float32)
        y = y.astype(np.float32)
        z = z.astype(np.float32)
        grid = pv.StructuredGrid(x, y, z)
    elif axis == "y":
        nu, nv = nx, nz
        x, z = np.meshgrid(np.arange(nu + 1), np.arange(nv + 1), indexing="ij")
        y = np.full_like(x, index, dtype=np.float32)
        x = x.astype(np.float32)
        z = z.astype(np.float32)
        grid = pv.StructuredGrid(x, y, z)
    elif axis == "z":
        nu, nv = nx, ny
        x, y = np.meshgrid(np.arange(nu + 1), np.arange(nv + 1), indexing="ij")
        z = np.full_like(x, index, dtype=np.float32)
        x = x.astype(np.float32)
        y = y.astype(np.float32)
        grid = pv.StructuredGrid(x, y, z)
    else:
        raise ValueError(axis)

    grid.cell_data["phase"] = labels_2d.astype(float).flatten(order="F")
    return grid


def add_face(plotter: pv.Plotter, mesh: pv.StructuredGrid) -> None:
    plotter.add_mesh(
        mesh,
        scalars="phase",
        rgb=False,
        categories=True,
        cmap=PHASE_CMAP,
        clim=(0.0, 2.0),
        opacity=1.0,
        show_scalar_bar=False,
        smooth_shading=False,
        show_edges=False,
        lighting=True,
        ambient=0.35,
        diffuse=0.75,
        specular=0.02,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render opaque exterior-only Estaillades geometry at the same angle as fig04."
    )
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--time-name", default="0")
    parser.add_argument("--geometry-field", default="theta")
    parser.add_argument("--solid-threshold", type=float, default=1.0e-3)
    parser.add_argument("--pore-threshold", type=float, default=0.9)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    pv.OFF_SCREEN = True

    theta, nx, ny, nz = stitch_parallel_scalar(args.case_dir, args.time_name, args.geometry_field)
    labels = classify_geometry(theta, args.solid_threshold, args.pore_threshold)

    faces = [
        make_face_mesh(labels[0, :, :], "x", 0, nx, ny, nz),
        make_face_mesh(labels[nx - 1, :, :], "x", nx, nx, ny, nz),
        make_face_mesh(labels[:, 0, :], "y", 0, nx, ny, nz),
        make_face_mesh(labels[:, ny - 1, :], "y", ny, nx, ny, nz),
        make_face_mesh(labels[:, :, 0], "z", 0, nx, ny, nz),
        make_face_mesh(labels[:, :, nz - 1], "z", nz, nx, ny, nz),
    ]

    plotter = pv.Plotter(off_screen=True, window_size=(1800, 1800))
    plotter.set_background("white")

    for face in faces:
        add_face(plotter, face)

    outline = pv.Cube(bounds=(0, nx, 0, ny, 0, nz))
    plotter.add_mesh(outline, style="wireframe", color="#555555", line_width=1.0, opacity=0.35)
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

    args.output.parent.mkdir(parents=True, exist_ok=True)
    plotter.screenshot(str(args.output))


if __name__ == "__main__":
    main()
