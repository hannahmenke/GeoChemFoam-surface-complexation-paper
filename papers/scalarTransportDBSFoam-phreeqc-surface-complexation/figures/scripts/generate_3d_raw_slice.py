#!/usr/bin/env python3

from __future__ import annotations

import argparse
import os
import re
import subprocess
import tarfile
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import to_rgba
from matplotlib.patches import Patch
from mpl_toolkits.mplot3d.art3d import Poly3DCollection


def parse_metadata(metadata_path: Path) -> tuple[tuple[int, int, int], str | None, dict[int, str]]:
    text = metadata_path.read_text()

    size_match = re.search(r"Size:\s+(\d+)\s+(\d+)\s+(\d+)", text)
    if not size_match:
        raise RuntimeError(f"Could not parse size from {metadata_path}")
    size = tuple(int(size_match.group(index)) for index in range(1, 4))

    res_match = re.search(r"res\s+([^\n]+)", text)
    resolution = res_match.group(1).strip() if res_match else None

    labels: dict[int, str] = {}
    for key, value in re.findall(r"^([A-Za-z_]+)=(\d+)$", text, re.M):
        labels[int(value)] = key

    return size, resolution, labels


def apply_case_overrides(raw_tar: Path, labels: dict[int, str]) -> dict[int, str]:
    overridden = dict(labels)

    if "Kelvin1-200x200x200" in raw_tar.name:
        overridden = {1: "pore", 2: "micropore"}

    for key, value in list(overridden.items()):
        if value.lower() == "micropores":
            overridden[key] = "micropore"

    return overridden


def read_raw_from_tar(path: Path) -> bytes:
    with tarfile.open(path, "r:gz") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        if not members:
            raise RuntimeError(f"No regular file found in {path}")
        with archive.extractfile(members[0]) as handle:
            if handle is None:
                raise RuntimeError(f"Could not extract {members[0].name} from {path}")
            return handle.read()


def raw_to_volume(raw_bytes: bytes, dims: tuple[int, int, int]) -> np.ndarray:
    nx, ny, nz = dims
    volume = np.frombuffer(raw_bytes, dtype=np.uint8)
    expected = nx * ny * nz
    if volume.size != expected:
        raise RuntimeError(
            f"Raw payload size mismatch: got {volume.size} bytes, expected {expected} for {dims}"
        )
    return volume.reshape((nz, ny, nx))


def color_map(labels: dict[int, str]) -> dict[int, str]:
    colors: dict[int, str] = {}
    for label, name in labels.items():
        key = name.lower()
        if key == "pore":
            colors[label] = "#ffffff"
        elif key in {"micropore", "matrix"}:
            colors[label] = "#4f8fd6"
        elif key == "solid":
            colors[label] = "#c94f4f"
        else:
            colors[label] = "#c97b63"
    return colors


def render_order(labels: dict[int, str]) -> list[int]:
    priority = {"pore": 0, "micropore": 1, "matrix": 1, "solid": 2}
    return sorted(labels, key=lambda item: priority.get(labels[item].lower(), 99))


def edge_style(name: str) -> tuple[str, float]:
    key = name.lower()
    if key == "pore":
        return ("#7f7f7f", 0.08)
    if key in {"micropore", "matrix"}:
        return ("#37679a", 0.04)
    if key == "solid":
        return ("#8a4040", 0.03)
    return ("#909090", 0.02)


def write_temp_raw(raw_bytes: bytes, raw_path: Path) -> None:
    raw_path.write_bytes(raw_bytes)


def extract_surface_with_paraview(raw_path: Path, vtp_path: Path, dims: tuple[int, int, int]) -> None:
    nx, ny, nz = dims
    script = f"""
from paraview.simple import *
r = ImageReader(FileNames=[r'{raw_path}'])
r.DataExtent = [0, {nx - 1}, 0, {ny - 1}, 0, {nz - 1}]
r.FileDimensionality = 3
r.DataScalarType = 'unsigned char'
r.DataByteOrder = 'LittleEndian'
r.NumberOfScalarComponents = 1
r.ScalarArrayName = 'phase'
r.DataOrigin = [0.0, 0.0, 0.0]
r.DataSpacing = [1.0, 1.0, 1.0]
s = ExtractSurface(Input=r)
SaveData(r'{vtp_path}', proxy=s, DataMode='Ascii')
"""
    env = os.environ.copy()
    env["PYTHONPATH"] = "/usr/lib/python3/dist-packages"
    result = subprocess.run(
        ["pvbatch", "-"],
        input=script,
        text=True,
        env=env,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "ParaView extraction failed:\n"
            + result.stdout
            + ("\n" if result.stdout and result.stderr else "")
            + result.stderr
        )


def parse_data_array(piece: ET.Element, section: str, name: str | None = None) -> np.ndarray:
    parent = piece.find(section)
    if parent is None:
        raise RuntimeError(f"Missing XML section {section}")

    data_array = None
    if name is None:
        data_array = parent.find("DataArray")
    else:
        for candidate in parent.findall("DataArray"):
            if candidate.get("Name") == name:
                data_array = candidate
                break
    if data_array is None or data_array.text is None:
        raise RuntimeError(f"Missing DataArray {name or '<first>'} in {section}")

    text = data_array.text.split()
    if data_array.get("type") in {"Float32", "Float64"}:
        return np.array([float(item) for item in text], dtype=float)
    return np.array([int(item) for item in text], dtype=int)


def parse_vtp_ascii(vtp_path: Path) -> tuple[np.ndarray, list[list[int]], np.ndarray]:
    root = ET.parse(vtp_path).getroot()
    piece = root.find("./PolyData/Piece")
    if piece is None:
        raise RuntimeError(f"Invalid VTP file {vtp_path}")

    points_data = parse_data_array(piece, "Points", "Points")
    points = points_data.reshape((-1, 3))

    phase = parse_data_array(piece, "PointData", "phase")

    polys = piece.find("Polys")
    if polys is None:
        raise RuntimeError("Missing Polys section")
    connectivity = parse_data_array(piece, "Polys", "connectivity")
    offsets = parse_data_array(piece, "Polys", "offsets")

    faces: list[list[int]] = []
    start = 0
    for stop in offsets:
        faces.append(connectivity[start:stop].tolist())
        start = int(stop)

    return points, faces, phase


def face_labels(faces: list[list[int]], phase: np.ndarray) -> list[int]:
    labels: list[int] = []
    for face in faces:
        values = phase[np.array(face, dtype=int)]
        unique, counts = np.unique(values, return_counts=True)
        labels.append(int(unique[np.argmax(counts)]))
    return labels


def configure_axis(ax, points: np.ndarray, subtitle: str | None, elev: float, azim: float) -> None:
    mins = points.min(axis=0)
    maxs = points.max(axis=0)
    lengths = np.maximum(maxs - mins, 1.0)

    ax.set_xlim(mins[0], maxs[0])
    ax.set_ylim(mins[1], maxs[1])
    ax.set_zlim(mins[2], maxs[2])
    ax.set_box_aspect((lengths[0], lengths[1], lengths[2]))
    ax.view_init(elev=elev, azim=azim)
    ax.set_facecolor("white")
    ax.grid(False)

    ax.set_xticks([mins[0], maxs[0]])
    ax.set_yticks([mins[1], maxs[1]])
    ax.set_zticks([mins[2], maxs[2]])
    ax.tick_params(axis="both", which="major", labelsize=8, pad=0)
    ax.set_xlabel("x voxel", labelpad=6, fontsize=9)
    ax.set_ylabel("y voxel", labelpad=6, fontsize=9)
    ax.set_zlabel("z voxel", labelpad=6, fontsize=9)

    if subtitle:
        ax.set_title(subtitle, fontsize=11)


def configure_outer_skin_axis(
    ax, dims: tuple[int, int, int], subtitle: str | None, elev: float, azim: float
) -> None:
    nx, ny, nz = dims
    ax.set_xlim(0.0, float(nx))
    ax.set_ylim(0.0, float(ny))
    ax.set_zlim(0.0, float(nz))
    ax.set_box_aspect((max(nx, 1), max(ny, 1), max(nz, 1)))
    ax.view_init(elev=elev, azim=azim)
    ax.set_facecolor("white")
    ax.grid(False)

    ax.set_xticks([0, nx])
    ax.set_yticks([0, ny])
    ax.set_zticks([0, nz])
    ax.tick_params(axis="both", which="major", labelsize=8, pad=0)
    ax.set_xlabel("x voxel", labelpad=6, fontsize=9)
    ax.set_ylabel("y voxel", labelpad=6, fontsize=9)
    ax.set_zlabel("z voxel", labelpad=6, fontsize=9)

    if subtitle:
        ax.set_title(subtitle, fontsize=11)


def block_mode_downsample(face: np.ndarray, target_cells: int = 180) -> np.ndarray:
    height, width = face.shape
    stride = max(1, int(np.ceil(max(height, width) / target_cells)))
    if stride == 1:
        return face

    out_h = int(np.ceil(height / stride))
    out_w = int(np.ceil(width / stride))
    result = np.empty((out_h, out_w), dtype=face.dtype)

    for row in range(out_h):
        y0 = row * stride
        y1 = min((row + 1) * stride, height)
        for col in range(out_w):
            x0 = col * stride
            x1 = min((col + 1) * stride, width)
            block = face[y0:y1, x0:x1]
            values, counts = np.unique(block, return_counts=True)
            result[row, col] = values[np.argmax(counts)]

    return result


def label_to_rgba(face: np.ndarray, labels: dict[int, str]) -> np.ndarray:
    colors = color_map(labels)
    rgba = np.empty(face.shape + (4,), dtype=float)
    default = to_rgba("#c97b63")
    for label in np.unique(face):
        rgba[face == label] = to_rgba(colors.get(int(label), default))
    return rgba


def plot_face_x(ax, x_value: float, face: np.ndarray, dims: tuple[int, int, int], labels: dict[int, str]) -> None:
    ny = face.shape[1]
    nz = face.shape[0]
    y = np.linspace(0.0, float(dims[1]), ny + 1)
    z = np.linspace(0.0, float(dims[2]), nz + 1)
    Y, Z = np.meshgrid(y, z)
    X = np.full_like(Y, x_value)
    ax.plot_surface(
        X,
        Y,
        Z,
        facecolors=label_to_rgba(face, labels),
        linewidth=0,
        antialiased=False,
        shade=False,
    )


def plot_face_y(ax, y_value: float, face: np.ndarray, dims: tuple[int, int, int], labels: dict[int, str]) -> None:
    nx = face.shape[1]
    nz = face.shape[0]
    x = np.linspace(0.0, float(dims[0]), nx + 1)
    z = np.linspace(0.0, float(dims[2]), nz + 1)
    X, Z = np.meshgrid(x, z)
    Y = np.full_like(X, y_value)
    ax.plot_surface(
        X,
        Y,
        Z,
        facecolors=label_to_rgba(face, labels),
        linewidth=0,
        antialiased=False,
        shade=False,
    )


def plot_face_z(ax, z_value: float, face: np.ndarray, dims: tuple[int, int, int], labels: dict[int, str]) -> None:
    nx = face.shape[1]
    ny = face.shape[0]
    x = np.linspace(0.0, float(dims[0]), nx + 1)
    y = np.linspace(0.0, float(dims[1]), ny + 1)
    X, Y = np.meshgrid(x, y)
    Z = np.full_like(X, z_value)
    ax.plot_surface(
        X,
        Y,
        Z,
        facecolors=label_to_rgba(face, labels),
        linewidth=0,
        antialiased=False,
        shade=False,
    )


def add_outer_skin_panel(
    ax,
    volume: np.ndarray,
    dims: tuple[int, int, int],
    labels: dict[int, str],
    subtitle: str | None,
    elev: float,
    azim: float,
) -> None:
    x0 = block_mode_downsample(volume[:, :, 0])
    x1 = block_mode_downsample(volume[:, :, -1])
    y0 = block_mode_downsample(volume[:, 0, :])
    y1 = block_mode_downsample(volume[:, -1, :])
    z0 = block_mode_downsample(volume[0, :, :])
    z1 = block_mode_downsample(volume[-1, :, :])

    plot_face_x(ax, 0.0, np.flipud(x0), dims, labels)
    plot_face_x(ax, float(dims[0]), np.flipud(x1), dims, labels)
    plot_face_y(ax, 0.0, np.flipud(y0), dims, labels)
    plot_face_y(ax, float(dims[1]), np.flipud(y1), dims, labels)
    plot_face_z(ax, 0.0, z0, dims, labels)
    plot_face_z(ax, float(dims[2]), z1, dims, labels)

    configure_outer_skin_axis(ax, dims, subtitle, elev, azim)


def add_panel(
    ax,
    points: np.ndarray,
    faces: list[list[int]],
    labels_for_faces: list[int],
    labels: dict[int, str],
    subtitle: str | None,
    elev: float,
    azim: float,
) -> None:
    colors = color_map(labels)
    face_groups: dict[int, list[list[tuple[float, float, float]]]] = {label: [] for label in labels}

    for indices, label in zip(faces, labels_for_faces):
        if label not in face_groups:
            continue
        face_groups[label].append(points[np.array(indices, dtype=int)].tolist())

    for label in render_order(labels):
        polys = face_groups.get(label, [])
        if not polys:
            continue
        name = labels[label]
        edgecolor, linewidth = edge_style(name)
        collection = Poly3DCollection(
            polys,
            facecolor=colors[label],
            edgecolor=edgecolor,
            linewidth=linewidth,
            alpha=1.0,
        )
        ax.add_collection3d(collection)

    configure_axis(ax, points, subtitle, elev, azim)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-tar", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--elev", type=float, default=24.0)
    parser.add_argument("--azim", type=float, default=35.0)
    parser.add_argument("--outer-skin-only", action="store_true")
    parser.add_argument("--crop", nargs=6, type=int, metavar=("X0", "X1", "Y0", "Y1", "Z0", "Z1"))
    args = parser.parse_args()

    dims, resolution, label_map = parse_metadata(args.metadata)
    label_map = apply_case_overrides(args.raw_tar, label_map)

    raw_bytes = read_raw_from_tar(args.raw_tar)
    volume = raw_to_volume(raw_bytes, dims)

    if args.outer_skin_only:
        fig = plt.figure(figsize=(10.5, 5.4))
        axes = [
            fig.add_subplot(1, 2, 1, projection="3d"),
            fig.add_subplot(1, 2, 2, projection="3d"),
        ]
        add_outer_skin_panel(axes[0], volume, dims, label_map, "overview", args.elev, args.azim)
        add_outer_skin_panel(
            axes[1], volume, dims, label_map, "alternate view", args.elev + 8.0, args.azim + 55.0
        )
    else:
        with tempfile.TemporaryDirectory() as tmp_dir_name:
            tmp_dir = Path(tmp_dir_name)
            raw_path = tmp_dir / "image.raw"
            vtp_path = tmp_dir / "outer_surface.vtp"
            write_temp_raw(raw_bytes, raw_path)
            extract_surface_with_paraview(raw_path, vtp_path, dims)
            points, faces, phase = parse_vtp_ascii(vtp_path)
        labels_for_faces = face_labels(faces, phase)
        fig = plt.figure(figsize=(7.0, 5.8))
        axes = [fig.add_subplot(1, 1, 1, projection="3d")]
        add_panel(axes[0], points, faces, labels_for_faces, label_map, None, args.elev, args.azim)

    legend_handles = [
        Patch(
            facecolor=color_map(label_map)[label],
            edgecolor="#808080" if label_map[label].lower() == "pore" else "none",
            label=label_map[label],
            alpha=1.0,
        )
        for label in render_order(label_map)
    ]
    fig.legend(handles=legend_handles, loc="upper right", frameon=False)

    title = args.title
    if resolution:
        title += f" ({resolution})"
    fig.suptitle(title)

    fig.subplots_adjust(left=0.02, right=0.92, top=0.88, bottom=0.02, wspace=0.02)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=220, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
