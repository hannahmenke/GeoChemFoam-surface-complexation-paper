#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
import tarfile
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import BoundaryNorm, ListedColormap


def parse_size(metadata_path: Path) -> tuple[int, int, int]:
    text = metadata_path.read_text()
    match = re.search(r"Size:\s+(\d+)\s+(\d+)\s+(\d+)", text)
    if not match:
        raise RuntimeError(f"Could not parse size from {metadata_path}")
    return tuple(int(match.group(index)) for index in range(1, 4))


def read_raw_from_tar(path: Path) -> bytes:
    with tarfile.open(path, "r:gz") as archive:
        members = [member for member in archive.getmembers() if member.isfile()]
        if not members:
            raise RuntimeError(f"No regular file found in {path}")
        with archive.extractfile(members[0]) as handle:
            if handle is None:
                raise RuntimeError(f"Could not extract {members[0].name} from {path}")
            return handle.read()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--raw-tar", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--title", default="4StraightFractures geometry")
    args = parser.parse_args()

    nx, ny, nz = parse_size(args.metadata)
    raw = read_raw_from_tar(args.raw_tar)
    array = np.frombuffer(raw, dtype=np.uint8)

    expected = nx * ny * nz
    if array.size != expected:
        raise RuntimeError(
            f"Voxel count mismatch for {args.raw_tar}: expected {expected}, got {array.size}"
        )

    volume = array.reshape((nz, ny, nx))
    image = volume[0, :, :]

    # Paper geometry palette:
    # solid = red, intermediate porous phase = blue, pore = white
    cmap = ListedColormap(["#c94f4f", "#4f8fd6", "#ffffff"])
    norm = BoundaryNorm([-0.5, 0.5, 1.5, 2.5], cmap.N)

    fig, ax = plt.subplots(figsize=(6.2, 6.2))
    mesh = ax.imshow(image, cmap=cmap, norm=norm, origin="lower", interpolation="nearest")
    ax.set_title(args.title)
    ax.set_xlabel("x voxel")
    ax.set_ylabel("y voxel")

    colorbar = fig.colorbar(mesh, ax=ax, ticks=[0, 1, 2], fraction=0.046, pad=0.04)
    colorbar.ax.set_yticklabels(["solid", "matrix", "pore"])

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(args.output, dpi=200)


if __name__ == "__main__":
    main()
