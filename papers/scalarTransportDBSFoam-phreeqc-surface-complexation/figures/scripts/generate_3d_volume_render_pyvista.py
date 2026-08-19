#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import tarfile
from pathlib import Path

from matplotlib.colors import LinearSegmentedColormap
import numpy as np
from scipy.ndimage import gaussian_filter
from scipy import ndimage as ndi
from scipy.spatial import cKDTree
import vtk
import pyvista.plotting._vtk as _pv_vtk
_pv_vtk.vtkRenderWindow = vtk.vtkEGLRenderWindow
import pyvista as pv


SOFT_BLUE_CMAP = LinearSegmentedColormap.from_list(
    "soft_blues_continuous",
    [
        "#eef5ff",
        "#dbeafe",
        "#bfdbfe",
        "#93c5fd",
        "#60a5fa",
        "#3b82f6",
        "#2563eb",
        "#1d4ed8",
        "#1e3a8a",
    ],
)
YELLOW_FADE_CMAP = LinearSegmentedColormap.from_list(
    "yellow_fade",
    [
        "#ffffff",
        "#fff7cc",
        "#ffe97a",
        "#ffd84a",
        "#f4c400",
    ],
)
SECOND_AQUEOUS_OPACITY = [0.0, 0.0, 0.004, 0.010, 0.022, 0.045, 0.085, 0.140]
AQUEOUS_OPACITY_SOFT = [0.0, 0.002, 0.006, 0.015, 0.035, 0.070, 0.120, 0.180]
AQUEOUS_OPACITY_FLAT = [0.015, 0.020, 0.030, 0.045, 0.065, 0.090, 0.120, 0.160]
AQUEOUS_OPACITY_DENSE = [0.040, 0.055, 0.075, 0.100, 0.130, 0.165, 0.205, 0.250]


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
                if len(local_values) == 1:
                    local_values = local_values * expected
                elif len(local_values) != expected:
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


def prepared_field(
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

    display = np.full_like(field, low)
    display[active] = np.clip(field[active], low, high)
    return display, (low, high)


def build_image_data(values: np.ndarray) -> pv.ImageData:
    nx, ny, nz = values.shape
    image = pv.ImageData(dimensions=(nx + 1, ny + 1, nz + 1))
    image.cell_data["value"] = values.flatten(order="F")
    return image


def smooth_supported_field(
    values: np.ndarray,
    support_mask: np.ndarray,
    sigma: float,
) -> tuple[np.ndarray, np.ndarray]:
    weights = gaussian_filter(support_mask.astype(float), sigma=sigma, mode="nearest")
    numerator = gaussian_filter(
        np.where(support_mask, values, 0.0),
        sigma=sigma,
        mode="nearest",
    )

    smoothed = np.full_like(values, np.nan, dtype=float)
    valid = weights > 1.0e-6
    smoothed[valid] = numerator[valid] / weights[valid]
    expanded_support = weights > (0.02 * float(np.max(weights)))
    return smoothed, expanded_support


def load_inlet_connected_pore_mask(
    image_path: Path,
    nx: int,
    ny: int,
    nz: int,
    pore_value: int,
    remap_from: int | None,
    remap_to: int | None,
) -> np.ndarray:
    if image_path.suffixes[-2:] == [".raw", ".tar.gz"] or str(image_path).endswith(".raw.tar.gz"):
        with tarfile.open(image_path, "r:gz") as tf:
            member = next(m for m in tf.getmembers() if m.name.endswith(".raw"))
            with tf.extractfile(member) as f:
                raw = np.frombuffer(f.read(), dtype=np.uint8).copy()
    else:
        raw = np.fromfile(image_path, dtype=np.uint8)

    if raw.size != nx * ny * nz:
        raise RuntimeError(
            f"Connectivity image size mismatch in {image_path}: "
            f"expected {nx*ny*nz}, got {raw.size}"
        )

    if remap_from is not None and remap_to is not None:
        raw[raw == remap_from] = remap_to

    labels = raw.reshape((nx, ny, nz), order="F")
    pore = labels == pore_value
    labelled, _ = ndi.label(pore, structure=ndi.generate_binary_structure(3, 1))
    inlet = np.unique(labelled[0, :, :])
    inlet = inlet[inlet > 0]
    return np.isin(labelled, inlet)


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
    panel_label: str = "a",
) -> None:
    plotter.subplot(*subplot)
    plotter.set_background("white")

    image = pv.ImageData(dimensions=(nx + 1, ny + 1, nz + 1))
    image.cell_data["phase"] = labels.flatten(order="F")

    phase_defs = [
        (0, "Solid", "#c94f4f", 0.28),
        (1, "Micropore", "#1a5caa", 0.22),
        (2, "Pore", "#555555", 0.14),
    ]

    present_phases = []
    for phase_value, name, color, opacity in phase_defs:
        thresholded = image.threshold(
            [phase_value - 0.1, phase_value + 0.1],
            scalars="phase",
            preference="cell",
        )
        if thresholded.n_cells == 0:
            continue
        present_phases.append((name, color))
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
    plotter.add_text(panel_label, position="upper_left", font_size=18, color="black", font="courier")
    # Legend: placed in upper-right of the geometry subplot viewport.
    # For 1×3 window (2520×1000): panel (a) is cols 0..839, so x=500, y tops at ~920px.
    # For 2×2 window (2800×2800): panel (a) is cols 0..1399, rows 1400..2799, so x=900, y~2700.
    # We use plotter.window_size to pick appropriate coords.
    # Place legend in white strip above the 3D bounding box (viewport y > 0.90)
    # Evenly distribute 3 items across top strip accounting for text widths.
    # "■ Solid"=8, "■ Micropore"=12, "■ Pore"=7 chars in Courier monospace.
    # Equal visual gap between end-of-item and start-of-next.
    legend_items = present_phases
    plotter.add_legend(
        labels=[[name, color] for name, color in legend_items],
        face="rectangle",
        bcolor=(0.96, 0.96, 0.96),
        border=False,
        size=(0.22, 0.12),
        loc="lower left",
        font_family="courier",
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


def camera_position(nx: int, ny: int, nz: int) -> list[tuple[float, float, float]]:
    centre = (0.5 * nx, 0.5 * ny, 0.5 * nz)
    position = (3.5 * nx, -2.8 * ny, 2.4 * nz)
    view_up = (0.0, 0.0, 1.0)
    return [position, centre, view_up]


def add_volume_panel(
    plotter: pv.Plotter,
    dataset: pv.ImageData,
    subplot: tuple[int, int],
    title: str,
    scalar_bar_title: str,
    cmap,
    clim: tuple[float, float],
    nx: int,
    ny: int,
    nz: int,
    panel_label: str = "b",
    shade: bool = True,
    opacity: list[float] | None = None,
    scalar_bar_fmt: str = "%.1f",
) -> None:
    plotter.subplot(*subplot)
    plotter.set_background("white")
    if opacity is None:
        opacity = [0.0, 0.0, 0.01, 0.04, 0.10, 0.20, 0.38, 0.62]
    plotter.add_volume(
        dataset,
        scalars="value",
        cmap=cmap,
        clim=clim,
        opacity=opacity,
        shade=shade,
        ambient=0.25,
        diffuse=0.85,
        specular=0.10,
        scalar_bar_args={
            "title": scalar_bar_title,
            "vertical": True,
            "fmt": scalar_bar_fmt,
            "title_font_size": 22,
            "label_font_size": 20,
            "n_labels": 5,
            "bold": True,
            "position_x": 0.87,
            "position_y": 0.25,
            "height": 0.50,
        },
    )
    plotter.add_mesh(
        dataset.outline(),
        color="#444444",
        line_width=1.0,
        opacity=0.35,
    )
    plotter.add_text(panel_label, position="upper_left", font_size=18, color="black", font="courier")
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


def add_interface_cells_panel(
    plotter: pv.Plotter,
    dataset: pv.ImageData,
    subplot: tuple[int, int],
    title: str,
    scalar_bar_title: str,
    cmap,
    clim: tuple[float, float],
    nx: int,
    ny: int,
    nz: int,
    panel_label: str = "d",
    scalar_bar_fmt: str = "%.1f",
) -> None:
    plotter.subplot(*subplot)
    plotter.set_background("white")
    active_cells = dataset.threshold(
        [0.5, 1.5],
        scalars="active",
        preference="cell",
    )
    reactive_shell = active_cells.clip_box(
        bounds=(0.0, 0.60 * nx, 0.0, ny, 0.0, nz),
        invert=False,
    )
    scalar_bar_args = {
        "title": scalar_bar_title,
        "vertical": True,
        "fmt": scalar_bar_fmt,
        "title_font_size": 22,
        "label_font_size": 20,
        "n_labels": 5,
        "bold": True,
        "position_x": 0.87,
        "position_y": 0.25,
        "height": 0.50,
    }
    if reactive_shell.n_cells > 0 and "value" in reactive_shell.array_names:
        plotter.add_mesh(
            reactive_shell,
            scalars="value",
            cmap=cmap,
            clim=clim,
            opacity=1.0,
            show_edges=False,
            smooth_shading=False,
            scalar_bar_args=scalar_bar_args,
        )
    else:
        dummy = pv.PolyData(np.array([[0.0, 0.0, 0.0]]))
        dummy["value"] = np.array([clim[0]], dtype=float)
        plotter.add_mesh(
            dummy,
            scalars="value",
            cmap=cmap,
            clim=clim,
            opacity=0.0,
            point_size=1.0,
            render_points_as_spheres=False,
            scalar_bar_args=scalar_bar_args,
        )
    plotter.add_mesh(
        dataset.outline(),
        color="#444444",
        line_width=1.0,
        opacity=0.35,
    )
    plotter.add_text(panel_label, position="upper_left", font_size=18, color="black", font="courier")
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


def build_interface_surface_mesh(
    pore_mask: np.ndarray,
    values: np.ndarray,
    active: np.ndarray,
    nx: int,
    ny: int,
    nz: int,
    connectivity_mask: np.ndarray | None = None,
    clip_x_fraction: float | None = 0.60,
    projection_radius: float = 0.95,
) -> pv.PolyData:
    render_pore_mask = pore_mask.copy()
    if connectivity_mask is not None:
        render_pore_mask &= connectivity_mask

    # Build a dense pore-side interface shell from the connected pore phase.
    # The chemistry is stored on sparse pore-side support cells, so project
    # those values onto the full local wall shell before extracting the
    # geometry. This keeps the rendering tied to the actual pore-solid
    # interface but avoids isolated single-cell speckles.
    struct = ndi.generate_binary_structure(3, 1)
    eroded = ndi.binary_erosion(render_pore_mask, structure=struct, border_value=0)
    interface_shell = render_pore_mask & (~eroded)

    render_cell_values = np.full(values.shape, np.nan, dtype=float)
    active_indices = np.argwhere(active)
    interface_indices = np.argwhere(interface_shell)
    if active_indices.size > 0 and interface_indices.size > 0:
        active_centres = active_indices.astype(float) + 0.5
        active_values = values[active]
        tree = cKDTree(active_centres)
        query_points = interface_indices.astype(float) + 0.5
        k = min(8, active_values.size)
        distance, nearest = tree.query(
            query_points,
            k=k,
            distance_upper_bound=projection_radius,
            workers=-1,
        )
        if k == 1:
            distance = distance[:, np.newaxis]
            nearest = nearest[:, np.newaxis]

        valid = np.isfinite(distance) & (nearest < active_values.size)
        shell_values = np.full(interface_indices.shape[0], np.nan, dtype=float)
        if np.any(valid):
            weights = np.zeros_like(distance, dtype=float)
            weights[valid] = 1.0 / np.maximum(distance[valid], 0.35) ** 2
            neighbour_values = np.zeros_like(distance, dtype=float)
            neighbour_values[valid] = active_values[nearest[valid]]
            denom = np.sum(weights, axis=1)
            ok = denom > 0.0
            shell_values[ok] = np.sum(weights[ok] * neighbour_values[ok], axis=1) / denom[ok]
        render_cell_values[
            interface_indices[:, 0],
            interface_indices[:, 1],
            interface_indices[:, 2],
        ] = shell_values

    image = pv.ImageData(dimensions=(nx + 1, ny + 1, nz + 1))
    image.cell_data["pore"] = render_pore_mask.flatten(order="F").astype(np.uint8)
    image.cell_data["value"] = render_cell_values.flatten(order="F")

    pore_cells = image.threshold(
        [0.5, 1.5],
        scalars="pore",
        preference="cell",
    )
    surface = pore_cells.extract_surface(algorithm="dataset_surface")

    # Remove the open sample faces so only the internal pore-solid wall remains.
    eps = 1.0e-3
    surface = surface.clip_box(
        bounds=(eps, nx - eps, eps, ny - eps, eps, nz - eps),
        invert=False,
    )

    if clip_x_fraction is not None:
        surface = surface.clip_box(
            bounds=(0.0, clip_x_fraction * nx, 0.0, ny, 0.0, nz),
            invert=False,
        )

    return surface


def add_interface_surface_panel(
    plotter: pv.Plotter,
    surface_mesh: pv.PolyData,
    subplot: tuple[int, int],
    title: str,
    scalar_bar_title: str,
    cmap,
    clim: tuple[float, float],
    nx: int,
    ny: int,
    nz: int,
    panel_label: str = "d",
    scalar_bar_fmt: str = "%.1f",
) -> None:
    plotter.subplot(*subplot)
    plotter.set_background("white")

    scalar_bar_args = {
        "title": scalar_bar_title,
        "vertical": True,
        "fmt": scalar_bar_fmt,
        "title_font_size": 22,
        "label_font_size": 20,
        "n_labels": 5,
        "bold": True,
        "position_x": 0.87,
        "position_y": 0.25,
        "height": 0.50,
    }

    if surface_mesh.n_cells > 0:
        plotter.add_mesh(
            surface_mesh,
            scalars="value",
            preference="cell",
            cmap=cmap,
            clim=clim,
            opacity=1.0,
            smooth_shading=False,
            show_edges=False,
            nan_color="#d8d8d8",
            nan_opacity=0.02,
            scalar_bar_args=scalar_bar_args,
        )
        plotter.add_mesh(
            surface_mesh,
            color="#b5b5b5",
            opacity=0.008,
            style="wireframe",
            line_width=0.35,
            smooth_shading=False,
        )
    else:
        dummy = pv.PolyData(np.array([[0.0, 0.0, 0.0]]))
        dummy["value"] = np.array([clim[0]], dtype=float)
        plotter.add_mesh(
            dummy,
            scalars="value",
            cmap=cmap,
            clim=clim,
            opacity=0.0,
            point_size=1.0,
            render_points_as_spheres=False,
            scalar_bar_args=scalar_bar_args,
        )

    plotter.add_mesh(
        pv.Cube(bounds=(0.0, nx, 0.0, ny, 0.0, nz)),
        style="wireframe",
        color="#444444",
        line_width=1.0,
        opacity=0.35,
    )
    plotter.add_text(panel_label, position="upper_left", font_size=18, color="black", font="courier")
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


def add_active_cells_panel(
    plotter: pv.Plotter,
    dataset: pv.ImageData,
    subplot: tuple[int, int],
    title: str,
    scalar_bar_title: str,
    cmap,
    clim: tuple[float, float],
    nx: int,
    ny: int,
    nz: int,
    panel_label: str = "b",
    scalar_bar_fmt: str = "%.1f",
) -> None:
    plotter.subplot(*subplot)
    plotter.set_background("white")
    active_cells = dataset.threshold(
        [0.5, 1.5],
        scalars="active",
        preference="cell",
    )
    plotter.add_mesh(
        active_cells,
        scalars="value",
        cmap=cmap,
        clim=clim,
        opacity=1.0,
        show_edges=False,
        smooth_shading=False,
        scalar_bar_args={
            "title": scalar_bar_title,
            "vertical": True,
            "fmt": scalar_bar_fmt,
            "title_font_size": 22,
            "label_font_size": 20,
            "n_labels": 5,
            "bold": True,
            "position_x": 0.87,
            "position_y": 0.25,
            "height": 0.50,
        },
    )
    plotter.add_mesh(
        dataset.outline(),
        color="#444444",
        line_width=1.0,
        opacity=0.35,
    )
    plotter.add_text(panel_label, position="upper_left", font_size=18, color="black", font="courier")
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


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--time-name", required=True)
    parser.add_argument("--aqueous-field", default="Ca+2")
    parser.add_argument("--aqueous-scale", type=float, default=None)
    parser.add_argument("--aqueous-mask-to-pore", action="store_true")
    parser.add_argument("--aqueous-log-scale", action="store_true")
    parser.add_argument("--aqueous-normalized-floor", type=float, default=0.0)
    parser.add_argument(
        "--aqueous-render-mode",
        choices=("volume", "cells"),
        default="volume",
    )
    parser.add_argument("--surface-field", default="Surf_aCa+")
    parser.add_argument("--geometry-field", default="eps")
    parser.add_argument("--surface-baseline-time")
    parser.add_argument("--surface-mask-field", default=None)
    parser.add_argument("--connectivity-image", type=Path, default=None)
    parser.add_argument("--connectivity-pore-value", type=int, default=1)
    parser.add_argument("--connectivity-remap-from", type=int, default=None)
    parser.add_argument("--connectivity-remap-to", type=int, default=None)
    parser.add_argument("--surface-floor", type=float, default=0.0)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="3D DBS Surface Complexation")
    parser.add_argument("--lower-quantile", type=float, default=0.01)
    parser.add_argument("--upper-quantile", type=float, default=0.995)
    parser.add_argument("--surface-log-scale", action="store_true")
    parser.add_argument("--solid-threshold", type=float, default=1.0e-3)
    parser.add_argument("--pore-threshold", type=float, default=0.9)
    parser.add_argument("--aqueous-title", default=None)
    parser.add_argument("--aqueous-cmap", default="cividis")
    parser.add_argument("--aqueous-no-shade", action="store_true")
    parser.add_argument(
        "--aqueous-opacity-profile",
        choices=("default", "soft", "flat", "dense"),
        default="default",
    )
    parser.add_argument("--surface-title", default=None)
    parser.add_argument(
        "--surface-render-mode",
        choices=("auto", "volume", "interface_cells", "interface_surface"),
        default="auto",
    )
    parser.add_argument("--surface-interface-clip-fraction", type=float, default=0.60)
    parser.add_argument("--second-aqueous-field", default=None)
    parser.add_argument("--second-aqueous-scale", type=float, default=None)
    parser.add_argument("--second-aqueous-title", default=None)
    parser.add_argument("--second-aqueous-normalized-floor", type=float, default=0.0)
    parser.add_argument("--second-aqueous-log-scale", action="store_true")
    parser.add_argument("--second-aqueous-cmap", default="soft_blues")
    parser.add_argument("--second-aqueous-no-shade", action="store_true")
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

    second_aqueous = None
    if args.second_aqueous_field:
        second_aqueous, ax2, ay2, az2 = stitch_parallel_scalar(
            args.case_dir, args.time_name, args.second_aqueous_field
        )
        if (ax2, ay2, az2) != (nx, ny, nz):
            raise RuntimeError("Second aqueous field mesh does not match")

    if args.surface_baseline_time:
        surface_baseline, bx, by, bz = stitch_parallel_scalar(
            args.case_dir, args.surface_baseline_time, args.surface_field
        )
        if (bx, by, bz) != (nx, ny, nz):
            raise RuntimeError("Surface baseline field mesh does not match")
        surface = np.maximum(surface - surface_baseline, 0.0)

    if args.surface_floor > 0.0:
        surface = np.where(surface >= args.surface_floor, surface, 0.0)

    pore_mask = geometry_field >= args.pore_threshold
    if args.aqueous_mask_to_pore:
        aqueous = np.where(pore_mask, aqueous, 0.0)
        if second_aqueous is not None:
            second_aqueous = np.where(pore_mask, second_aqueous, 0.0)

    if args.aqueous_scale is not None:
        aqueous_display = np.clip(aqueous / args.aqueous_scale, 0.0, 1.0)
    else:
        aqueous_display, _ = normalized_field(
            aqueous,
            lower_q=args.lower_quantile,
            upper_q=args.upper_quantile,
            log_scale=args.aqueous_log_scale,
            zero_mask=args.aqueous_mask_to_pore,
        )
    if args.aqueous_normalized_floor > 0.0:
        aqueous_display = np.where(
            aqueous_display >= args.aqueous_normalized_floor,
            aqueous_display,
            0.0,
        )
    aqueous_active = np.isfinite(aqueous_display)
    if args.aqueous_render_mode == "cells":
        if args.aqueous_mask_to_pore:
            aqueous_active = pore_mask
        else:
            aqueous_active = np.isfinite(aqueous_display)
    surface_display, surface_clim = prepared_field(
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

    aqueous_img = build_image_data(aqueous_display)
    aqueous_img.cell_data["active"] = aqueous_active.flatten(order="F").astype(np.uint8)
    solid_img = build_image_data((geometry_field <= args.solid_threshold).astype(float))
    solid_img.cell_data["solid"] = (geometry_field <= args.solid_threshold).flatten(order="F").astype(np.uint8)
    if args.surface_mask_field:
        surface_mask_values, mx, my, mz = stitch_parallel_scalar(
            args.case_dir, args.time_name, args.surface_mask_field
        )
        if (mx, my, mz) != (nx, ny, nz):
            raise RuntimeError("Surface mask field mesh does not match")
        surface_active = surface_mask_values > 0.0
    else:
        surface_active = surface > 0.0
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
        surface_active = surface_active & inlet_connected_mask
    surface_active_fraction = float(np.count_nonzero(surface_active)) / float(surface_active.size)
    if args.surface_render_mode == "auto":
        surface_render_mode = "interface_surface" if (args.surface_log_scale and surface_active_fraction < 2.0e-3) else "volume"
    else:
        surface_render_mode = args.surface_render_mode
    use_sparse_surface_panel = surface_render_mode == "interface_cells"
    surface_render_values = surface_display
    surface_render_active = surface_active
    if use_sparse_surface_panel:
        surface_render_values, surface_render_active = smooth_supported_field(
            surface_display,
            surface_active,
            sigma=4.0,
        )
        surface_render_values = np.where(
            np.isfinite(surface_render_values),
            surface_render_values,
            surface_clim[0],
        )
    surface_img = build_image_data(surface_render_values)
    surface_img.cell_data["active"] = surface_render_active.flatten(order="F").astype(np.uint8)
    interface_surface_mesh = None
    if surface_render_mode == "interface_surface":
        interface_surface_mesh = build_interface_surface_mesh(
            pore_mask=pore_mask,
            values=surface_display,
            active=surface_active,
            nx=nx,
            ny=ny,
            nz=nz,
            connectivity_mask=inlet_connected_mask,
            clip_x_fraction=args.surface_interface_clip_fraction,
        )

    use_2x2 = second_aqueous is not None
    shape = (2, 2) if use_2x2 else (1, 3)
    win_size = (3200, 3200) if use_2x2 else (2400, 960)
    plotter = pv.Plotter(shape=shape, off_screen=True, window_size=win_size)

    add_geometry_panel(
        plotter=plotter,
        labels=geometry_labels,
        subplot=(0, 0),
        nx=nx,
        ny=ny,
        nz=nz,
        panel_label="(a)",
    )

    aq_title = args.aqueous_title if args.aqueous_title else f"{args.aqueous_field} / C_in"
    aq_bar = args.aqueous_title if args.aqueous_title else f"Norm. {args.aqueous_field}"
    surf_title = args.surface_title if args.surface_title else f"\u0394{args.surface_field}"
    surf_bar = args.surface_title if args.surface_title else f"Norm. \u0394{args.surface_field}"
    if args.surface_log_scale:
        surf_title = f"log10({surf_title})"
        surf_bar = surf_title

    aqueous_opacity = None
    if args.aqueous_opacity_profile == "soft":
        aqueous_opacity = AQUEOUS_OPACITY_SOFT
    elif args.aqueous_opacity_profile == "flat":
        aqueous_opacity = AQUEOUS_OPACITY_FLAT
    elif args.aqueous_opacity_profile == "dense":
        aqueous_opacity = AQUEOUS_OPACITY_DENSE

    aqueous_cmap = YELLOW_FADE_CMAP if args.aqueous_cmap == "yellow_fade" else args.aqueous_cmap

    if args.aqueous_render_mode == "cells":
        add_active_cells_panel(
            plotter=plotter,
            dataset=aqueous_img,
            subplot=(0, 1),
            title=aq_title,
            scalar_bar_title=aq_title,
            cmap=aqueous_cmap,
            clim=(0.0, 1.0),
            nx=nx,
            ny=ny,
            nz=nz,
            panel_label="(b)",
        )
    else:
        add_volume_panel(
            plotter=plotter,
            dataset=aqueous_img,
            subplot=(0, 1),
            title=aq_title,
            scalar_bar_title=aq_title,
                cmap=aqueous_cmap,
                clim=(0.0, 1.0),
                nx=nx,
                ny=ny,
            nz=nz,
            panel_label="(b)",
            shade=not args.aqueous_no_shade,
            opacity=aqueous_opacity,
        )

    if use_2x2:
        if args.second_aqueous_scale is not None:
            second_display = np.clip(second_aqueous / args.second_aqueous_scale, 0.0, 1.0)
        else:
            second_display, _ = normalized_field(
                second_aqueous,
                lower_q=args.lower_quantile,
                upper_q=args.upper_quantile,
                log_scale=args.second_aqueous_log_scale,
                zero_mask=args.aqueous_mask_to_pore,
            )
        if args.second_aqueous_normalized_floor > 0.0:
            second_display = np.where(
                second_display >= args.second_aqueous_normalized_floor,
                second_display,
                0.0,
            )
        # Most of the Ca field sits near the upper end, so darken the upper range
        # to recover visible tonal structure instead of a single pale block.
        second_display = np.power(second_display, 2.0)
        second_active = np.isfinite(second_display)
        if args.aqueous_render_mode == "cells":
            if args.aqueous_mask_to_pore:
                second_active = pore_mask
            else:
                second_active = np.isfinite(second_display)
        second_img = build_image_data(second_display)
        second_img.cell_data["active"] = second_active.flatten(order="F").astype(np.uint8)
        aq2_title = args.second_aqueous_title if args.second_aqueous_title else f"{args.second_aqueous_field} / C_in"
        second_cmap = SOFT_BLUE_CMAP if args.second_aqueous_cmap == "soft_blues" else args.second_aqueous_cmap
        if args.aqueous_render_mode == "cells":
            add_active_cells_panel(
                plotter=plotter,
                dataset=second_img,
                subplot=(1, 0),
                title=aq2_title,
                scalar_bar_title=aq2_title,
                cmap=second_cmap,
                clim=(0.0, 1.0),
                nx=nx,
                ny=ny,
                nz=nz,
                panel_label="(c)",
            )
        else:
            add_volume_panel(
                plotter=plotter,
                dataset=second_img,
                subplot=(1, 0),
                title=aq2_title,
                scalar_bar_title=aq2_title,
                cmap=second_cmap,
                clim=(0.0, 1.0),
                nx=nx,
                ny=ny,
                nz=nz,
                panel_label="(c)",
                shade=not args.second_aqueous_no_shade,
                opacity=SECOND_AQUEOUS_OPACITY,
            )
        if surface_render_mode == "interface_surface":
            add_interface_surface_panel(
                plotter=plotter,
                surface_mesh=interface_surface_mesh,
                subplot=(1, 1),
                title=surf_title,
                scalar_bar_title=surf_bar,
                cmap="magma",
                clim=surface_clim,
                nx=nx,
                ny=ny,
                nz=nz,
                panel_label="(d)",
                scalar_bar_fmt="%.0f" if args.surface_log_scale else "%.1f",
            )
        elif use_sparse_surface_panel:
            add_interface_cells_panel(
                plotter=plotter,
                dataset=surface_img,
                subplot=(1, 1),
                title=surf_title,
                scalar_bar_title=surf_bar,
                cmap="magma",
                clim=surface_clim,
                nx=nx,
                ny=ny,
                nz=nz,
                panel_label="(d)",
                scalar_bar_fmt="%.0f" if args.surface_log_scale else "%.1f",
            )
        else:
            add_volume_panel(
                plotter=plotter,
                dataset=surface_img,
                subplot=(1, 1),
                title=surf_title,
                scalar_bar_title=surf_bar,
                cmap="magma",
                clim=surface_clim,
                nx=nx,
                ny=ny,
                nz=nz,
                panel_label="(d)",
                scalar_bar_fmt="%.0f" if args.surface_log_scale else "%.1f",
            )
    else:
        if surface_render_mode == "interface_surface":
            add_interface_surface_panel(
                plotter=plotter,
                surface_mesh=interface_surface_mesh,
                subplot=(0, 2),
                title=surf_title,
                scalar_bar_title=surf_bar,
                cmap="magma",
                clim=surface_clim,
                nx=nx,
                ny=ny,
                nz=nz,
                panel_label="(c)",
                scalar_bar_fmt="%.0f" if args.surface_log_scale else "%.1f",
            )
        elif use_sparse_surface_panel:
            add_interface_cells_panel(
                plotter=plotter,
                dataset=surface_img,
                subplot=(0, 2),
                title=surf_title,
                scalar_bar_title=surf_bar,
                cmap="magma",
                clim=surface_clim,
                nx=nx,
                ny=ny,
                nz=nz,
                panel_label="(c)",
                scalar_bar_fmt="%.0f" if args.surface_log_scale else "%.1f",
            )
        else:
            add_volume_panel(
                plotter=plotter,
                dataset=surface_img,
                subplot=(0, 2),
                title=surf_title,
                scalar_bar_title=surf_bar,
                cmap="magma",
                clim=surface_clim,
                nx=nx,
                ny=ny,
                nz=nz,
                panel_label="(c)",
                scalar_bar_fmt="%.0f" if args.surface_log_scale else "%.1f",
            )

    plotter.link_views()
    plotter.screenshot(str(args.output))


if __name__ == "__main__":
    main()
