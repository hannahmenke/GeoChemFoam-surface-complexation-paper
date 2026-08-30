#!/usr/bin/env python3

from __future__ import annotations

import csv
import argparse
import json
import sys
import tempfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib import colormaps
from matplotlib.colors import LogNorm, TwoSlopeNorm
from mpl_toolkits.mplot3d.art3d import Poly3DCollection
from skimage.measure import marching_cubes


REPO_ROOT = Path(__file__).resolve().parents[4]
CASE_ROOT = (
    REPO_ROOT
    / "papers"
    / "scalarTransportDBSFoam-phreeqc-surface-complexation"
    / "cases"
    / "3d_external_surface_flow_validation"
)
OUTPUT = (
    REPO_ROOT
    / "papers"
    / "scalarTransportDBSFoam-phreeqc-surface-complexation"
    / "figures"
    / "png"
    / "fig11_3d_external_surface_area_validation.png"
)
METRICS_JSON = CASE_ROOT / "results" / "fig11_3d_external_surface_area_validation_metrics.json"

SCRIPTS = REPO_ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from createASurfMarchingCubes import build_field, marching_cubes_for_pair
from createWallCellASurf import polygon_area, read_faces as parse_faces, read_points as parse_points

if str(Path(__file__).resolve().parent) not in sys.path:
    sys.path.insert(0, str(Path(__file__).resolve().parent))
from hm12_case_tools import parse_boundary_metadata

try:
    import vtk
    import pyvista.plotting._vtk as _pv_vtk

    _pv_vtk.vtkRenderWindow = vtk.vtkEGLRenderWindow
    import pyvista as pv
    from generate_3d_volume_render_pyvista import camera_position

    HAS_PYVISTA = True
except ModuleNotFoundError:
    HAS_PYVISTA = False


PORE_LABEL = 1
SOLID_LABEL = 3
VOXEL_SIZE = 4e-6
SIGMA_VOX = 0.74
NX = NY = NZ = 128
SNAPPY_COLOR = "#d98f00"
SMOOTH_COLOR = "#1b6b73"


def crop_rendered_image(image: np.ndarray, pad_fraction: float = 0.055) -> np.ndarray:
    rgb = image[..., :3]
    non_background = np.any(rgb < 0.985, axis=2)
    if not np.any(non_background):
        return image
    rows, cols = np.where(non_background)
    height, width = image.shape[:2]
    pad = int(round(max(height, width) * pad_fraction))
    r0 = max(int(rows.min()) - pad, 0)
    r1 = min(int(rows.max()) + pad + 1, height)
    c0 = max(int(cols.min()) - pad, 0)
    c1 = min(int(cols.max()) + pad + 1, width)
    return image[r0:r1, c0:c1]


def load_crop() -> np.ndarray:
    path = CASE_ROOT / "shared" / "estaillades_external_crop_phase.raw"
    raw = np.fromfile(path, dtype=np.uint8)
    expected = NX * NY * NZ
    if raw.size != expected:
        raise RuntimeError(f"Unexpected crop size: {raw.size} != {expected}")
    return raw.reshape((NZ, NY, NX))


def smooth_area_field(image: np.ndarray) -> tuple[np.ndarray, int]:
    owner_mask = image == PORE_LABEL
    pair_mask = owner_mask | (image == SOLID_LABEL)
    verts, faces, _ = marching_cubes_for_pair(
        owner_mask,
        pair_mask,
        VOXEL_SIZE,
        "occupancyGaussian",
        SIGMA_VOX,
    )
    asurf, _ = build_field(
        verts,
        faces,
        image,
        NX,
        NY,
        NZ,
        1,
        1,
        1,
        VOXEL_SIZE,
        PORE_LABEL,
    )
    return asurf * VOXEL_SIZE**3, int(faces.shape[0])


def snappy_area_field() -> tuple[np.ndarray, int]:
    poly_mesh = CASE_ROOT / "snappy" / "constant" / "polyMesh"
    points = parse_points(poly_mesh / "points")
    faces = parse_faces(poly_mesh / "faces")
    boundary = parse_boundary_metadata(poly_mesh / "boundary")
    patch = boundary["solidwalls"]
    start = patch["startFace"]
    end = start + patch["nFaces"]
    field = np.zeros((NZ, NY, NX), dtype=float)
    for face in faces[start:end]:
        face_points = points[np.array(face, dtype=int)]
        centroid = np.mean(face_points, axis=0)
        ix = int(np.clip(np.floor(centroid[0] / VOXEL_SIZE), 0, NX - 1))
        iy = int(np.clip(np.floor(centroid[1] / VOXEL_SIZE), 0, NY - 1))
        iz = int(np.clip(np.floor(centroid[2] / VOXEL_SIZE), 0, NZ - 1))
        field[iz, iy, ix] += polygon_area(face_points)
    return field, patch["nFaces"]


def projection(field: np.ndarray) -> np.ndarray:
    return np.sum(field, axis=0)


def profile_x(field: np.ndarray) -> np.ndarray:
    return np.sum(field, axis=(0, 1))


def read_summary() -> dict[str, dict[str, float | str]]:
    path = CASE_ROOT / "results" / "summary.csv"
    with path.open(newline="") as handle:
        rows = list(csv.DictReader(handle))
    parsed: dict[str, dict[str, float | str]] = {}
    for row in rows:
        method = row["method"]
        parsed[method] = {}
        for key, value in row.items():
            if key == "method":
                continue
            if value == "":
                parsed[method][key] = value
            else:
                try:
                    parsed[method][key] = float(value)
                except ValueError:
                    parsed[method][key] = value
    return parsed


def panel_label(ax: plt.Axes, label: str) -> None:
    text = ax.text2D if hasattr(ax, "text2D") else ax.text
    text(
        0.015,
        0.985,
        label,
        transform=ax.transAxes,
        ha="left",
        va="top",
        fontsize=16,
        fontweight="bold",
        bbox={"facecolor": "white", "edgecolor": "none", "alpha": 0.75, "pad": 2},
    )


def render_geometry_image(image: np.ndarray) -> np.ndarray:
    if not HAS_PYVISTA:
        return render_geometry_image_matplotlib(image)

    pv.OFF_SCREEN = True
    pore_xyz = np.transpose(image == PORE_LABEL, (2, 1, 0))
    solid_xyz = np.transpose(image == SOLID_LABEL, (2, 1, 0))
    data = pv.ImageData(dimensions=(NX + 1, NY + 1, NZ + 1))
    data.cell_data["pore"] = pore_xyz.flatten(order="F").astype(np.uint8)
    data.cell_data["solid"] = solid_xyz.flatten(order="F").astype(np.uint8)
    pore_cells = data.threshold([0.5, 1.5], scalars="pore", preference="cell")
    solid_cells = data.threshold([0.5, 1.5], scalars="solid", preference="cell")
    pore_surface = pore_cells.extract_surface(algorithm="dataset_surface")
    solid_surface = solid_cells.extract_surface(algorithm="dataset_surface")
    eps = 1.0e-3
    pore_surface = pore_surface.clip_box(bounds=(eps, NX - eps, eps, NY - eps, eps, NZ - eps), invert=False)
    solid_surface = solid_surface.clip_box(bounds=(eps, NX - eps, eps, NY - eps, eps, NZ - eps), invert=False)

    plotter = pv.Plotter(off_screen=True, window_size=(1500, 1500))
    plotter.set_background("white")
    plotter.add_mesh(
        solid_surface,
        color="#c5a268",
        opacity=0.60,
        smooth_shading=True,
        show_edges=False,
        ambient=0.28,
        diffuse=0.86,
        specular=0.18,
        specular_power=18,
    )
    plotter.add_mesh(
        pore_surface,
        color="#59646d",
        opacity=0.30,
        smooth_shading=True,
        show_edges=False,
        ambient=0.36,
        diffuse=0.78,
        specular=0.08,
    )
    plotter.add_mesh(
        pv.Cube(bounds=(0.0, NX, 0.0, NY, 0.0, NZ)),
        style="wireframe",
        color="#333333",
        line_width=1.4,
        opacity=0.48,
    )
    plotter.add_light(pv.Light(position=(2 * NX, -1.5 * NY, 2.2 * NZ), focal_point=(NX / 2, NY / 2, NZ / 2), intensity=0.55))
    plotter.camera_position = camera_position(NX, NY, NZ)
    plotter.camera.zoom(1.72)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "external_surface_geometry.png"
        plotter.screenshot(str(path))
        rendered = crop_rendered_image(plt.imread(path))
    plotter.close()
    return rendered


def render_geometry_image_matplotlib(image: np.ndarray) -> np.ndarray:
    solid = image == SOLID_LABEL
    verts_zyx, faces, _normals, _values = marching_cubes(
        solid.astype(np.float32),
        level=0.5,
        spacing=(VOXEL_SIZE * 1e6, VOXEL_SIZE * 1e6, VOXEL_SIZE * 1e6),
        step_size=2,
        allow_degenerate=False,
    )
    verts_xyz = verts_zyx[:, [2, 1, 0]]
    max_faces = 70000
    if faces.shape[0] > max_faces:
        faces = faces[np.linspace(0, faces.shape[0] - 1, max_faces, dtype=int)]
    face_z = np.mean(verts_xyz[faces, 2], axis=1)
    face_z = (face_z - face_z.min()) / max(float(np.ptp(face_z)), 1.0)
    grey = 0.48 + 0.28 * face_z
    facecolors = np.column_stack([grey, grey, grey, np.ones_like(grey)])

    tmp_fig = plt.figure(figsize=(3.0, 3.0), dpi=260)
    ax = tmp_fig.add_subplot(111, projection="3d")
    mesh = Poly3DCollection(
        verts_xyz[faces],
        facecolors=facecolors,
        edgecolor="none",
        linewidth=0.0,
        alpha=1.0,
    )
    ax.add_collection3d(mesh)
    domain_um = NX * VOXEL_SIZE * 1e6
    ax.set_xlim(0.0, domain_um)
    ax.set_ylim(0.0, domain_um)
    ax.set_zlim(0.0, domain_um)
    ax.set_box_aspect((1, 1, 1))
    ax.view_init(elev=24, azim=-56)
    ax.set_axis_off()
    tmp_fig.subplots_adjust(0, 0, 1, 1)
    with tempfile.TemporaryDirectory() as tmpdir:
        path = Path(tmpdir) / "external_surface_geometry_fallback.png"
        tmp_fig.savefig(path, dpi=260)
        rendered = crop_rendered_image(plt.imread(path))
    plt.close(tmp_fig)
    return rendered


def add_geometry_render(fig: plt.Figure, spec, image: np.ndarray) -> None:
    ax = fig.add_subplot(spec)
    ax.imshow(render_geometry_image(image))
    ax.set_box_aspect(1)
    ax.set_title("external-surface geometry", fontsize=16, pad=5)
    ax.set_axis_off()
    panel_label(ax, "a")


def main() -> None:
    global CASE_ROOT, OUTPUT, METRICS_JSON
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-root", type=Path, default=CASE_ROOT)
    parser.add_argument("--output", type=Path, default=OUTPUT)
    parser.add_argument("--metrics-json", type=Path, default=METRICS_JSON)
    args = parser.parse_args()

    CASE_ROOT = args.case_root.resolve()
    OUTPUT = args.output.resolve()
    METRICS_JSON = args.metrics_json.resolve()

    image = load_crop()
    summary = read_summary()
    snappy_field, snappy_faces = snappy_area_field()
    smooth_field, smooth_triangles = smooth_area_field(image)

    fields = {"snappy": snappy_field, "smooth": smooth_field}
    projections = {key: projection(value) for key, value in fields.items()}
    profiles = {key: profile_x(value) for key, value in fields.items()}

    positive = np.concatenate([value[value > 0.0] for value in projections.values()])
    vmin = max(float(np.percentile(positive, 2.0)), VOXEL_SIZE**2 * 0.05)
    vmax = float(np.percentile(positive, 99.2))
    difference = projections["smooth"] - projections["snappy"]
    diff_lim = max(float(np.percentile(np.abs(difference), 99.0)), VOXEL_SIZE**2)
    diff_scale = 1.0e-10
    difference_scaled = difference / diff_scale
    diff_lim_scaled = diff_lim / diff_scale

    area_cmap = colormaps["magma"].copy()
    area_cmap.set_bad("#e5e5e5")
    diff_cmap = colormaps["coolwarm"].copy()

    # A two-column, three-row layout gives every map a physically meaningful
    # footprint at its final SI width. The 10.8-inch source prints at 4.94
    # inches; the 16-pt minimum authored label therefore remains at least 7 pt.
    plt.rcParams.update(
        {
            "font.size": 16,
            "axes.labelsize": 16,
            "xtick.labelsize": 16,
            "ytick.labelsize": 16,
        }
    )
    fig = plt.figure(figsize=(10.8, 15.6), constrained_layout=True)
    grid = fig.add_gridspec(3, 2, width_ratios=[1, 1], height_ratios=[1, 1, 1])
    add_geometry_render(fig, grid[0, 0], image)

    extent_um = (0, NX * VOXEL_SIZE * 1e6, 0, NY * VOXEL_SIZE * 1e6)
    area_handle = None
    for spec, label, title, data in (
        (grid[0, 1], "b", "snappyHexMesh wall area", projections["snappy"]),
        (grid[1, 0], "c", "DBS smooth area", projections["smooth"]),
    ):
        ax = fig.add_subplot(spec)
        area_handle = ax.imshow(
            np.ma.masked_less_equal(data, 0.0),
            origin="lower",
            extent=extent_um,
            norm=LogNorm(vmin=vmin, vmax=vmax),
            cmap=area_cmap,
        )
        ax.set_title(title, fontsize=16, pad=5)
        ax.set_box_aspect(1)
        ax.set_xlabel(r"$x$ [$\mu$m]")
        ax.set_ylabel(r"$y$ [$\mu$m]")
        panel_label(ax, label)

    ax_diff = fig.add_subplot(grid[1, 1])
    diff_handle = ax_diff.imshow(
        difference_scaled,
        origin="lower",
        extent=extent_um,
        norm=TwoSlopeNorm(vmin=-diff_lim_scaled, vcenter=0.0, vmax=diff_lim_scaled),
        cmap=diff_cmap,
    )
    ax_diff.set_title("DBS smooth area $-$ snappyHexMesh", fontsize=16, pad=5)
    ax_diff.set_box_aspect(1)
    ax_diff.set_xlabel(r"$x$ [$\mu$m]")
    ax_diff.set_ylabel(r"$y$ [$\mu$m]")
    panel_label(ax_diff, "d")

    ax_profile = fig.add_subplot(grid[2, 0])
    x_um = (np.arange(NX) + 0.5) * VOXEL_SIZE * 1e6
    ax_profile.plot(x_um, profiles["snappy"], color=SNAPPY_COLOR, lw=2.4, label="snappyHexMesh")
    ax_profile.plot(x_um, profiles["smooth"], color=SMOOTH_COLOR, lw=2.4, label="DBS smooth interface")
    ax_profile.set_xlabel(r"$x$ [$\mu$m]")
    ax_profile.set_ylabel(r"area per $x$ slice [m$^2$]")
    ax_profile.set_box_aspect(1)
    ax_profile.grid(True, axis="y", color="#dddddd", lw=0.8)
    ax_profile.legend(frameon=False, fontsize=16)
    panel_label(ax_profile, "e")

    ax_scales = fig.add_subplot(grid[2, 1])
    ax_scales.set_axis_off()
    area_cax = ax_scales.inset_axes([0.10, 0.66, 0.80, 0.075])
    diff_cax = ax_scales.inset_axes([0.10, 0.28, 0.80, 0.075])
    area_cbar = fig.colorbar(area_handle, cax=area_cax, orientation="horizontal")
    area_cbar.set_label(r"projected external area [m$^2$]", fontsize=16)
    diff_cbar = fig.colorbar(diff_handle, cax=diff_cax, orientation="horizontal")
    diff_cbar.set_label(r"projected area difference [$10^{-10}$ m$^2$]", fontsize=16)
    for cbar in (area_cbar, diff_cbar):
        cbar.ax.tick_params(labelsize=16, length=5, width=1.0)

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUTPUT, dpi=360)
    plt.close(fig)

    metrics = {
        "output": str(OUTPUT.relative_to(REPO_ROOT)),
        "case_root": str(CASE_ROOT.relative_to(REPO_ROOT)),
        "sigma_vox": SIGMA_VOX,
        "voxel_size": VOXEL_SIZE,
        "snappy_wall_faces": snappy_faces,
        "smooth_triangles": smooth_triangles,
        "areas_from_fields": {key: float(np.sum(value)) for key, value in fields.items()},
        "summary": {key: value for key, value in summary.items() if key in {"snappy", "dbs-smoothsurface"}},
    }
    METRICS_JSON.write_text(json.dumps(metrics, indent=2))
    print(json.dumps(metrics, indent=2))


if __name__ == "__main__":
    main()
