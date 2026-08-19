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


def parse_vector_field(path: Path) -> np.ndarray:
    text = path.read_text()
    uniform_match = re.search(r"internalField\s+uniform\s+\(([^)]+)\)\s*;", text)
    if uniform_match:
        values = [float(x) for x in uniform_match.group(1).split()]
        return np.asarray([values], dtype=float)

    nonuniform_match = re.search(
        r"internalField\s+nonuniform\s+List<vector>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not nonuniform_match:
        raise RuntimeError(f"Unsupported vector field format in {path}")

    count = int(nonuniform_match.group(1))
    triples = re.findall(r"\(([^)]+)\)", nonuniform_match.group(2))
    values = np.asarray([[float(x) for x in triple.split()] for triple in triples], dtype=float)
    if values.shape != (count, 3):
        raise RuntimeError(f"Vector count mismatch in {path}: expected {count}, got {values.shape[0]}")
    return values


def parse_scalar_field(path: Path) -> np.ndarray:
    text = path.read_text()
    uniform_match = re.search(r"internalField\s+uniform\s+([^\n;]+)\s*;", text)
    if uniform_match:
        return np.asarray([float(uniform_match.group(1))], dtype=float)

    nonuniform_match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not nonuniform_match:
        raise RuntimeError(f"Unsupported scalar field format in {path}")

    count = int(nonuniform_match.group(1))
    values = np.asarray([float(item) for item in nonuniform_match.group(2).split()], dtype=float)
    if values.size != count:
        raise RuntimeError(f"Scalar count mismatch in {path}: expected {count}, got {values.size}")
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


def stitch_parallel_scalar(case_dir: Path, time_name: str, field_name: str) -> tuple[np.ndarray, int, int, int]:
    npx = int((case_dir / "system" / "NPX").read_text().strip())
    npy = int((case_dir / "system" / "NPY").read_text().strip())
    npz = int((case_dir / "system" / "NPZ").read_text().strip())
    nx = int((case_dir / "system" / "Nx1").read_text().strip())
    ny = int((case_dir / "system" / "Ny1").read_text().strip())
    nz = int((case_dir / "system" / "Nz1").read_text().strip())

    size_x, start_x = partition_sizes(nx, npx)
    size_y, start_y = partition_sizes(ny, npy)
    size_z, start_z = partition_sizes(nz, npz)

    global_values = np.zeros((nx, ny, nz), dtype=float, order="F")

    for pz in range(npz):
        for py in range(npy):
            for px in range(npx):
                pid = px + npx * (py + npy * pz)
                local_values = parse_scalar_field(case_dir / f"processor{pid}" / time_name / field_name)
                local_nx = size_x[px]
                local_ny = size_y[py]
                local_nz = size_z[pz]
                expected = local_nx * local_ny * local_nz
                if local_values.size != expected:
                    raise RuntimeError(f"{field_name} length mismatch in processor{pid}: expected {expected}, got {local_values.size}")
                block = local_values.reshape((local_nx, local_ny, local_nz), order="F")
                global_values[
                    start_x[px]:start_x[px] + local_nx,
                    start_y[py]:start_y[py] + local_ny,
                    start_z[pz]:start_z[pz] + local_nz,
                ] = block

    return global_values, nx, ny, nz


def stitch_parallel_vector(case_dir: Path, time_name: str, field_name: str) -> tuple[np.ndarray, int, int, int]:
    npx = int((case_dir / "system" / "NPX").read_text().strip())
    npy = int((case_dir / "system" / "NPY").read_text().strip())
    npz = int((case_dir / "system" / "NPZ").read_text().strip())
    nx = int((case_dir / "system" / "Nx1").read_text().strip())
    ny = int((case_dir / "system" / "Ny1").read_text().strip())
    nz = int((case_dir / "system" / "Nz1").read_text().strip())

    size_x, start_x = partition_sizes(nx, npx)
    size_y, start_y = partition_sizes(ny, npy)
    size_z, start_z = partition_sizes(nz, npz)

    global_values = np.zeros((nx, ny, nz, 3), dtype=float, order="F")

    for pz in range(npz):
        for py in range(npy):
            for px in range(npx):
                pid = px + npx * (py + npy * pz)
                local_values = parse_vector_field(case_dir / f"processor{pid}" / time_name / field_name)
                local_nx = size_x[px]
                local_ny = size_y[py]
                local_nz = size_z[pz]
                expected = local_nx * local_ny * local_nz
                if local_values.shape[0] != expected:
                    raise RuntimeError(f"{field_name} length mismatch in processor{pid}: expected {expected}, got {local_values.shape[0]}")
                block = local_values.reshape((local_nx, local_ny, local_nz, 3), order="F")
                global_values[
                    start_x[px]:start_x[px] + local_nx,
                    start_y[py]:start_y[py] + local_ny,
                    start_z[pz]:start_z[pz] + local_nz,
                    :,
                ] = block

    return global_values, nx, ny, nz


def build_grid(theta: np.ndarray, velocity: np.ndarray) -> pv.ImageData:
    nx, ny, nz = theta.shape
    grid = pv.ImageData(dimensions=(nx + 1, ny + 1, nz + 1))
    grid.cell_data["eps"] = theta.flatten(order="F")
    grid.cell_data["U"] = velocity.reshape((-1, 3), order="F")
    grid.cell_data["Umag"] = np.linalg.norm(velocity, axis=3).flatten(order="F")
    grid = grid.cell_data_to_point_data()
    return grid


def build_seed_points(theta: np.ndarray, velocity: np.ndarray, n_seed: int) -> pv.PolyData:
    nx, ny, nz = theta.shape
    speed = np.linalg.norm(velocity, axis=3)
    inlet_mask = (theta > 0.5) & (speed > 0.0)
    inlet_mask[3:, :, :] = False
    idx = np.argwhere(inlet_mask)
    if idx.size == 0:
        raise RuntimeError("No inlet pore cells with nonzero velocity were found for seeding.")

    order = np.argsort(speed[inlet_mask])[::-1]
    idx = idx[order]
    stride = max(1, idx.shape[0] // n_seed)
    chosen = idx[::stride][:n_seed]
    points = chosen.astype(float) + 0.5
    return pv.PolyData(points)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--time-name", default="100")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--n-seed", type=int, default=180)
    args = parser.parse_args()

    pv.OFF_SCREEN = True

    theta, nx, ny, nz = stitch_parallel_scalar(args.case_dir, args.time_name, "eps")
    velocity, vx, vy, vz = stitch_parallel_vector(args.case_dir, args.time_name, "U")
    if (vx, vy, vz) != (nx, ny, nz):
        raise RuntimeError("theta/U mesh mismatch")

    velocity = np.where(theta[..., None] > 0.5, velocity, 0.0)
    grid = build_grid(theta, velocity)

    seeds = build_seed_points(theta, velocity, args.n_seed)
    streamlines = grid.streamlines_from_source(
        seeds,
        vectors="U",
        integration_direction="forward",
        integrator_type=45,
        max_steps=4000,
        initial_step_length=0.5,
        step_unit="cl",
        terminal_speed=1.0e-14,
    )

    solid = pv.ImageData(dimensions=(nx + 1, ny + 1, nz + 1))
    solid.cell_data["solid"] = (theta <= 1.0e-3).flatten(order="F").astype(np.uint8)
    solid_surface = solid.threshold([0.5, 1.5], scalars="solid", preference="cell").extract_surface(algorithm="dataset_surface")
    solid_surface = solid_surface.clip_box(bounds=(0.0, 0.35 * nx, 0.0, ny, 0.0, nz), invert=False)

    plotter = pv.Plotter(off_screen=True, window_size=(2200, 1800))
    plotter.set_background("white")
    plotter.add_mesh(
        solid_surface,
        color="#b15a5a",
        opacity=0.18,
        smooth_shading=False,
        show_scalar_bar=False,
    )
    plotter.add_mesh(
        streamlines.tube(radius=0.35),
        scalars="Umag",
        cmap="viridis",
        clim=(float(np.nanmin(grid["Umag"][grid["Umag"] > 0])), float(np.nanmax(grid["Umag"]))),
        scalar_bar_args={
            "title": "|U| (m/s)",
            "vertical": True,
            "fmt": "%.1e",
            "title_font_size": 20,
            "label_font_size": 18,
            "n_labels": 5,
            "position_x": 0.88,
            "position_y": 0.22,
            "height": 0.55,
        },
    )
    plotter.add_text("(a)", position="upper_left", font_size=20, color="black", font="courier")
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
    centre = (0.5 * nx, 0.5 * ny, 0.5 * nz)
    position = (3.0 * nx, -2.4 * ny, 1.8 * nz)
    plotter.camera_position = [position, centre, (0.0, 0.0, 1.0)]
    plotter.screenshot(str(args.output))


if __name__ == "__main__":
    main()
