#!/usr/bin/env python3

from __future__ import annotations

import json
import os
import tarfile
from collections import deque
from pathlib import Path

import numpy as np


CASE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[3]

IMAGE_NAME = "Est_3phase500cubed4micron"
IMAGE_DIMS = (500, 500, 500)
CROP_MIN = (300, 340, 40)
CROP_SIZE = (128, 128, 128)
PORE_LABEL = 1
MICROPORE_LABEL = 2
SOLID_LABEL = 3


def raw_candidates() -> list[Path]:
    candidates: list[Path] = []
    for base in (os.environ.get("GCFOAM_IMG"), REPO_ROOT / "images", REPO_ROOT / "images" / "raw"):
        if not base:
            continue
        root = Path(base)
        candidates.extend(
            [
                root / f"{IMAGE_NAME}.raw",
                root / "raw" / f"{IMAGE_NAME}.raw",
                root / f"{IMAGE_NAME}.raw.tar.gz",
                root / "raw" / f"{IMAGE_NAME}.raw.tar.gz",
            ]
        )
    return candidates


def load_raw() -> np.ndarray:
    expected = int(np.prod(IMAGE_DIMS))
    for path in raw_candidates():
        if not path.exists():
            continue
        if path.suffixes[-2:] == [".tar", ".gz"]:
            with tarfile.open(path, "r:gz") as archive:
                handle = archive.extractfile(f"{IMAGE_NAME}.raw")
                if handle is None:
                    raise RuntimeError(f"Could not extract {IMAGE_NAME}.raw from {path}")
                raw = np.frombuffer(handle.read(), dtype=np.uint8)
        else:
            raw = np.fromfile(path, dtype=np.uint8)
        if raw.size != expected:
            raise RuntimeError(f"Raw size mismatch for {path}: {raw.size} != {expected}")
        return raw.reshape((IMAGE_DIMS[2], IMAGE_DIMS[1], IMAGE_DIMS[0]))
    raise FileNotFoundError(f"Could not find {IMAGE_NAME}.raw or .raw.tar.gz")


def inlet_connected_pore(pore: np.ndarray) -> np.ndarray:
    nz, ny, nx = pore.shape
    connected = np.zeros_like(pore, dtype=bool)
    queue: deque[tuple[int, int, int]] = deque()

    inlet = np.argwhere(pore[:, :, 0])
    for z, y in inlet:
        connected[z, y, 0] = True
        queue.append((int(z), int(y), 0))

    neighbors = (
        (-1, 0, 0),
        (1, 0, 0),
        (0, -1, 0),
        (0, 1, 0),
        (0, 0, -1),
        (0, 0, 1),
    )
    while queue:
        z, y, x = queue.popleft()
        for dz, dy, dx in neighbors:
            zz = z + dz
            yy = y + dy
            xx = x + dx
            if (
                0 <= zz < nz
                and 0 <= yy < ny
                and 0 <= xx < nx
                and pore[zz, yy, xx]
                and not connected[zz, yy, xx]
            ):
                connected[zz, yy, xx] = True
                queue.append((zz, yy, xx))
    return connected


def main() -> None:
    x0, y0, z0 = CROP_MIN
    sx, sy, sz = CROP_SIZE
    raw = load_raw()
    crop = raw[z0 : z0 + sz, y0 : y0 + sy, x0 : x0 + sx].copy()

    external = crop.copy()
    external[external == MICROPORE_LABEL] = SOLID_LABEL

    pore = external == PORE_LABEL
    connected = inlet_connected_pore(pore)
    if not np.any(connected[:, :, -1]):
        raise RuntimeError("Selected crop does not contain an inlet-to-outlet pore path.")

    phase = np.where(connected, PORE_LABEL, SOLID_LABEL).astype(np.uint8)
    binary = np.where(connected, 255, 0).astype(np.uint8)

    shared = CASE_ROOT / "shared"
    shared.mkdir(parents=True, exist_ok=True)
    phase.tofile(shared / "estaillades_external_crop_phase.raw")
    binary.tofile(shared / "estaillades_external_crop_binary.raw")

    metadata = {
        "source_image": IMAGE_NAME,
        "source_dims_xyz": list(IMAGE_DIMS),
        "crop_min_xyz": list(CROP_MIN),
        "crop_size_xyz": list(CROP_SIZE),
        "labels": {
            "pore": PORE_LABEL,
            "micropore_remapped_to_solid": MICROPORE_LABEL,
            "solid": SOLID_LABEL,
            "snappy_pore": 255,
            "snappy_solid": 0,
        },
        "porosity": float(np.mean(connected)),
        "connected_pore_voxels": int(np.count_nonzero(connected)),
        "inlet_pore_voxels": int(np.count_nonzero(connected[:, :, 0])),
        "outlet_pore_voxels": int(np.count_nonzero(connected[:, :, -1])),
    }
    (shared / "metadata.json").write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
