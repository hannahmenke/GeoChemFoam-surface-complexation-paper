#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import tarfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap
from matplotlib.patches import Rectangle


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


def read_raw_from_tar(path: Path) -> bytes:
    with tarfile.open(path, "r:gz") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        if not members:
            raise RuntimeError(f"No regular file found in {path}")
        with archive.extractfile(members[0]) as handle:
            if handle is None:
                raise RuntimeError(f"Could not extract {members[0].name} from {path}")
            return handle.read()


def extract_slice(volume: np.ndarray, axis: str, index: int) -> np.ndarray:
    if axis == "x":
        return volume[:, :, index]
    if axis == "y":
        return volume[:, index, :]
    if axis == "z":
        return volume[index, :, :]
    raise RuntimeError(f"Unsupported axis {axis}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-tar", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", required=True)
    parser.add_argument("--slice-axis", choices=("x", "y", "z"), default="z")
    parser.add_argument("--slice-index", type=int)
    parser.add_argument("--zoom", nargs=4, type=int, metavar=("X0", "X1", "Y0", "Y1"))
    args = parser.parse_args()

    (nx, ny, nz), resolution, label_map = parse_metadata(args.metadata)
    raw = read_raw_from_tar(args.raw_tar)
    array = np.frombuffer(raw, dtype=np.uint8)

    expected = nx * ny * nz
    if array.size != expected:
        raise RuntimeError(
            f"Voxel count mismatch for {args.raw_tar}: expected {expected}, got {array.size}"
        )

    volume = array.reshape((nz, ny, nx))
    axis_size = {"x": nx, "y": ny, "z": nz}[args.slice_axis]
    slice_index = args.slice_index if args.slice_index is not None else axis_size // 2
    image = extract_slice(volume, args.slice_axis, slice_index)

    max_value = int(image.max())
    colors = ["#101010", "#f4f4f4", "#7aa6c2", "#c75c5c", "#6a994e"]
    if max_value >= len(colors):
        raise RuntimeError("Not enough colors configured for this segmentation")
    cmap = ListedColormap(colors[: max_value + 1])
    norm = BoundaryNorm(np.arange(-0.5, max_value + 1.5, 1.0), cmap.N)

    if args.zoom:
        x0, x1, y0, y1 = args.zoom
        fig, axes = plt.subplots(1, 2, figsize=(10.0, 4.8), constrained_layout=True)
        panels = [(axes[0], image, "overview"), (axes[1], image[y0:y1, x0:x1], "zoom")]
    else:
        fig, axis = plt.subplots(figsize=(6.4, 5.4), constrained_layout=True)
        axes = [axis]
        panels = [(axis, image, None)]

    for axis, panel, subtitle in panels:
        mesh = axis.imshow(panel, cmap=cmap, norm=norm, origin="lower", interpolation="nearest")
        axis.set_xlabel("x voxel")
        axis.set_ylabel("y voxel")
        if subtitle:
            axis.set_title(subtitle)

    if args.zoom:
        x0, x1, y0, y1 = args.zoom
        axes[0].add_patch(
            Rectangle((x0, y0), x1 - x0, y1 - y0, fill=False, edgecolor="#ffcc00", linewidth=1.5)
        )

    title = args.title
    if resolution:
        title += f" ({resolution})"
    fig.suptitle(title)

    tick_values = sorted(set(int(value) for value in np.unique(image)))
    cbar = fig.colorbar(mesh, ax=axes, ticks=tick_values, fraction=0.046, pad=0.04)
    cbar.ax.set_yticklabels([label_map.get(value, str(value)) for value in tick_values])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=200)


if __name__ == "__main__":
    main()
