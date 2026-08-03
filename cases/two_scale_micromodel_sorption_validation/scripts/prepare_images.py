#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import tarfile
from pathlib import Path

import numpy as np


ROOT = Path(__file__).resolve().parents[1]
SHARED = ROOT / "shared"
SOURCE = SHARED / "source"

FULL_NAME = "TSmicromodel6000"
DBS_NAME = "TSmicromodelDBS1200"

FULL_SHAPE = (6000, 6000)
DBS_SHAPE = (1200, 1200)

FULL_RES_M = 1.0e-6
DBS_RES_M = 5.0e-6

def env_int(name: str, default: int) -> int:
    return int(os.environ.get(name, str(default)))


RESOLVED_COARSEN_FACTOR = env_int("RESOLVED_COARSEN_FACTOR", 1)
DBS_COARSEN_FACTOR = env_int("DBS_COARSEN_FACTOR", 1)
FULL_MODEL_REV = {
    "x_min": env_int("RESOLVED_CROP_X_MIN", 0),
    "x_max": env_int("RESOLVED_CROP_X_MAX", 6000),
    "y_min": env_int("RESOLVED_CROP_Y_MIN", 0),
    "y_max": env_int("RESOLVED_CROP_Y_MAX", 6000),
}
X_MIRROR_COPIES = env_int("X_MIRROR_COPIES", 2)
DBS_FULL_REV = {
    "x_min": env_int("DBS_CROP_X_MIN", 0),
    "x_max": env_int("DBS_CROP_X_MAX", 1200),
    "y_min": env_int("DBS_CROP_Y_MIN", 0),
    "y_max": env_int("DBS_CROP_Y_MAX", 1200),
}
RESOLVED_INLET_PAD_VOXELS = int(os.environ.get("RESOLVED_INLET_PAD_VOXELS", "4"))
DBS_INLET_PAD_VOXELS = int(os.environ.get("DBS_INLET_PAD_VOXELS", "1"))
RESOLVED_INLET_PAD_CELLS = max(
    1,
    (RESOLVED_INLET_PAD_VOXELS + RESOLVED_COARSEN_FACTOR - 1)
    // RESOLVED_COARSEN_FACTOR,
)
DBS_INLET_PAD_CELLS = max(
    1, (DBS_INLET_PAD_VOXELS + DBS_COARSEN_FACTOR - 1) // DBS_COARSEN_FACTOR
)

# Matrix REV used in the dispersivity benchmark.
MATRIX_REV = {"x_min": 0, "x_max": 300, "y_min": 2200, "y_max": 2500}


def extract_raw(tar_path: Path, raw_name: str) -> np.ndarray:
    with tarfile.open(tar_path, "r:gz") as archive:
        member = next(m for m in archive.getmembers() if Path(m.name).name == raw_name)
        handle = archive.extractfile(member)
        if handle is None:
            raise RuntimeError(f"Could not extract {raw_name} from {tar_path}")
        return np.frombuffer(handle.read(), dtype=np.uint8).copy()


def crop2d(img: np.ndarray, crop: dict[str, int]) -> np.ndarray:
    height, width = img.shape
    if not (0 <= crop["x_min"] < crop["x_max"] <= width):
        raise ValueError(f"Invalid x crop {crop} for image width {width}")
    if not (0 <= crop["y_min"] < crop["y_max"] <= height):
        raise ValueError(f"Invalid y crop {crop} for image height {height}")
    return img[crop["y_min"] : crop["y_max"], crop["x_min"] : crop["x_max"]]


def interface_length_2d(binary: np.ndarray, voxel_size: float) -> float:
    horizontal = np.count_nonzero(binary[:, 1:] != binary[:, :-1])
    vertical = np.count_nonzero(binary[1:, :] != binary[:-1, :])
    return float(horizontal + vertical) * voxel_size


def mirror_extend_x(array: np.ndarray, n_extra_copies: int) -> np.ndarray:
    copies = [array]
    for i in range(n_extra_copies):
        source = array if i % 2 else np.fliplr(array)
        copies.append(source)
    return np.concatenate(copies, axis=1)


def force_inlet_pore_pad(array: np.ndarray, width_voxels: int, pore_value: int = 255) -> np.ndarray:
    if width_voxels <= 0:
        return array
    padded = array.copy()
    padded[:, :width_voxels] = pore_value
    return padded


def downsample_categorical(array: np.ndarray, factor: int, factor_name: str) -> np.ndarray:
    if factor <= 0:
        raise ValueError(f"{factor_name} must be positive, got {factor}")
    height, width = array.shape
    if height % factor or width % factor:
        raise ValueError(
            f"Crop {width}x{height} is not divisible by "
            f"{factor_name}={factor}"
        )
    pore = array > 127
    pore_fraction = pore.reshape(
        height // factor, factor, width // factor, factor
    ).mean(axis=(1, 3))
    return np.where(pore_fraction >= 0.5, 255, 0).astype(np.uint8)


def write_raw(path: Path, array2d: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.ascontiguousarray(array2d[None, :, :], dtype=np.uint8).tofile(path)


def main() -> None:
    full = extract_raw(SOURCE / f"{FULL_NAME}.raw.tar.gz", f"{FULL_NAME}.raw").reshape(FULL_SHAPE)
    dbs = extract_raw(SOURCE / f"{DBS_NAME}.raw.tar.gz", f"{DBS_NAME}.raw").reshape(DBS_SHAPE)

    resolved_source_crop = crop2d(full, FULL_MODEL_REV)
    dbs_source_crop = crop2d(dbs, DBS_FULL_REV)
    resolved_base = downsample_categorical(
        resolved_source_crop, RESOLVED_COARSEN_FACTOR, "RESOLVED_COARSEN_FACTOR"
    )
    dbs_base = downsample_categorical(
        dbs_source_crop, DBS_COARSEN_FACTOR, "DBS_COARSEN_FACTOR"
    )
    matrix_rev_gray = crop2d(full, MATRIX_REV)
    matrix_rev = np.where(matrix_rev_gray > 127, 255, 0).astype(np.uint8)

    resolved_full_reference = mirror_extend_x(resolved_base, X_MIRROR_COPIES)
    dbs_full_upscaled = mirror_extend_x(dbs_base, X_MIRROR_COPIES)
    resolved_full_reference = force_inlet_pore_pad(
        resolved_full_reference, RESOLVED_INLET_PAD_CELLS
    )
    dbs_full_upscaled = force_inlet_pore_pad(dbs_full_upscaled, DBS_INLET_PAD_CELLS)
    dbs_full_upscaled_phase = dbs_full_upscaled.copy()

    write_raw(SHARED / "resolved_full_reference.raw", resolved_full_reference)
    write_raw(SHARED / "dbs_full_upscaled.raw", dbs_full_upscaled)
    write_raw(SHARED / "dbs_full_upscaled_phase.raw", dbs_full_upscaled_phase)
    write_raw(SHARED / "TSmicromodel_matrix_rev.raw", matrix_rev)

    matrix_pore = matrix_rev == 255
    matrix_porosity = float(matrix_pore.mean())
    matrix_bulk_area = matrix_rev.shape[0] * matrix_rev.shape[1] * FULL_RES_M**2
    matrix_interface_length = interface_length_2d(matrix_pore, FULL_RES_M)
    matrix_intrinsic_asurf = matrix_interface_length / matrix_bulk_area

    metadata = {
        "source_images": {
            "resolved": f"{FULL_NAME}.raw.tar.gz",
            "dbs": f"{DBS_NAME}.raw.tar.gz",
        },
        "geometry_generation": {
            "x_mirror_copies": X_MIRROR_COPIES,
            "x_tile_sequence": ["base", "mirror_x", "base"],
            "resolved_inlet_pore_pad_voxels": RESOLVED_INLET_PAD_VOXELS,
            "resolved_inlet_pore_pad_computational_cells": RESOLVED_INLET_PAD_CELLS,
            "dbs_inlet_pore_pad_voxels": DBS_INLET_PAD_VOXELS,
            "dbs_inlet_pore_pad_computational_cells": DBS_INLET_PAD_CELLS,
            "resolved_coarsen_factor": RESOLVED_COARSEN_FACTOR,
            "dbs_coarsen_factor": DBS_COARSEN_FACTOR,
            "resolved_downsampling": "categorical majority; output values are exactly 0 or 255",
            "dbs_downsampling": "categorical majority; output values are exactly 0 or 255",
            "description": (
                "The full resolved REV and the full DBS REV are extended in "
                "the streamwise direction by appending mirrored copies. This "
                "creates equal-size synthetic transport domains while avoiding "
                "a hard repeated seam at the first join. The first streamwise "
                "voxels are forced to pore to provide a clean inlet pad before "
                "the micromodel texture."
            ),
        },
        "resolved_full_model_rev": {
            **FULL_MODEL_REV,
            "z_dim": 1,
            "voxel_size_m": FULL_RES_M * RESOLVED_COARSEN_FACTOR,
            "shape": [
                int(resolved_base.shape[1]),
                int(resolved_base.shape[0]),
                1,
            ],
            "pore_value": 255,
            "solid_value": 0,
            "porosity": float((resolved_base == 255).mean()),
        },
        "resolved_full_reference": {
            "file": "resolved_full_reference.raw",
            "z_dim": 1,
            "voxel_size_m": FULL_RES_M * RESOLVED_COARSEN_FACTOR,
            "shape": [
                int(resolved_full_reference.shape[1]),
                int(resolved_full_reference.shape[0]),
                1,
            ],
            "physical_size_m": [
                resolved_full_reference.shape[1] * FULL_RES_M * RESOLVED_COARSEN_FACTOR,
                resolved_full_reference.shape[0] * FULL_RES_M * RESOLVED_COARSEN_FACTOR,
                FULL_RES_M * RESOLVED_COARSEN_FACTOR,
            ],
            "pore_value": 255,
            "solid_value": 0,
            "porosity": float((resolved_full_reference == 255).mean()),
        },
        "dbs_full_model_rev": {
            **DBS_FULL_REV,
            "z_dim": 1,
            "voxel_size_m": DBS_RES_M * DBS_COARSEN_FACTOR,
            "shape": [
                int(dbs_base.shape[1]),
                int(dbs_base.shape[0]),
                1,
            ],
            "pore_value": 255,
            "matrix_value": 0,
            "vug_porosity": float((np.where(dbs_base > 127, 255, 0) == 255).mean()),
        },
        "dbs_full_upscaled": {
            "file": "dbs_full_upscaled.raw",
            "phase_file": "dbs_full_upscaled_phase.raw",
            "z_dim": 1,
            "voxel_size_m": DBS_RES_M * DBS_COARSEN_FACTOR,
            "shape": [
                int(dbs_full_upscaled.shape[1]),
                int(dbs_full_upscaled.shape[0]),
                1,
            ],
            "physical_size_m": [
                dbs_full_upscaled.shape[1] * DBS_RES_M * DBS_COARSEN_FACTOR,
                dbs_full_upscaled.shape[0] * DBS_RES_M * DBS_COARSEN_FACTOR,
                DBS_RES_M * DBS_COARSEN_FACTOR,
            ],
            "pore_value": 255,
            "matrix_value": 0,
            "vug_porosity": float((dbs_full_upscaled_phase == 255).mean()),
            "matrix_porosity_from_rev": matrix_porosity,
            "matrix_intrinsic_asurf_per_bulk_volume_m-1": matrix_intrinsic_asurf,
        },
        "matrix_rev": {
            **MATRIX_REV,
            "voxel_size_m": FULL_RES_M,
            "shape": [300, 300, 1],
            "porosity": matrix_porosity,
            "interface_length_per_unit_depth_m": matrix_interface_length,
            "intrinsic_asurf_per_bulk_volume_m-1": matrix_intrinsic_asurf,
        },
    }
    (SHARED / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")

    print(f"Wrote {SHARED / 'resolved_full_reference.raw'}")
    print(f"Wrote {SHARED / 'dbs_full_upscaled.raw'}")
    print(f"Wrote {SHARED / 'metadata.json'}")


if __name__ == "__main__":
    main()
