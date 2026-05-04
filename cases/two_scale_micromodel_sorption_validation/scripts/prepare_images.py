#!/usr/bin/env python3
from __future__ import annotations

import json
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

# Full-model REV used to build the synthetic transport domain.
DBS_FULL_REV = {"x_min": 0, "x_max": 1200, "y_min": 0, "y_max": 1200}
FULL_MODEL_REV = {"x_min": 0, "x_max": 6000, "y_min": 0, "y_max": 6000}
X_MIRROR_COPIES = 2

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


def write_raw(path: Path, array2d: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.ascontiguousarray(array2d[None, :, :], dtype=np.uint8).tofile(path)


def main() -> None:
    full = extract_raw(SOURCE / f"{FULL_NAME}.raw.tar.gz", f"{FULL_NAME}.raw").reshape(FULL_SHAPE)
    dbs = extract_raw(SOURCE / f"{DBS_NAME}.raw.tar.gz", f"{DBS_NAME}.raw").reshape(DBS_SHAPE)

    resolved_base_gray = crop2d(full, FULL_MODEL_REV)
    dbs_base = crop2d(dbs, DBS_FULL_REV)
    matrix_rev_gray = crop2d(full, MATRIX_REV)
    resolved_base = np.where(resolved_base_gray > 127, 255, 0).astype(np.uint8)
    matrix_rev = np.where(matrix_rev_gray > 127, 255, 0).astype(np.uint8)

    resolved_full_reference = mirror_extend_x(resolved_base, X_MIRROR_COPIES)
    dbs_full_upscaled = mirror_extend_x(dbs_base, X_MIRROR_COPIES)
    dbs_full_upscaled_phase = np.where(dbs_full_upscaled > 127, 255, 0).astype(np.uint8)

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
            "description": (
                "The full resolved REV and the full DBS REV are extended in "
                "the streamwise direction by appending mirrored copies. This "
                "creates equal-size synthetic transport domains while avoiding "
                "a hard repeated seam at the first join."
            ),
        },
        "resolved_full_model_rev": {
            **FULL_MODEL_REV,
            "z_dim": 1,
            "voxel_size_m": FULL_RES_M,
            "shape": [6000, 6000, 1],
            "pore_value": 255,
            "solid_value": 0,
            "porosity": float((resolved_base == 255).mean()),
        },
        "resolved_full_reference": {
            "file": "resolved_full_reference.raw",
            "z_dim": 1,
            "voxel_size_m": FULL_RES_M,
            "shape": [
                int(resolved_full_reference.shape[1]),
                int(resolved_full_reference.shape[0]),
                1,
            ],
            "physical_size_m": [
                resolved_full_reference.shape[1] * FULL_RES_M,
                resolved_full_reference.shape[0] * FULL_RES_M,
                FULL_RES_M,
            ],
            "pore_value": 255,
            "solid_value": 0,
            "porosity": float((resolved_full_reference == 255).mean()),
        },
        "dbs_full_model_rev": {
            **DBS_FULL_REV,
            "z_dim": 1,
            "voxel_size_m": DBS_RES_M,
            "shape": [1200, 1200, 1],
            "pore_value": 255,
            "matrix_value": 0,
            "vug_porosity": float((np.where(dbs_base > 127, 255, 0) == 255).mean()),
        },
        "dbs_full_upscaled": {
            "file": "dbs_full_upscaled.raw",
            "phase_file": "dbs_full_upscaled_phase.raw",
            "z_dim": 1,
            "voxel_size_m": DBS_RES_M,
            "shape": [
                int(dbs_full_upscaled.shape[1]),
                int(dbs_full_upscaled.shape[0]),
                1,
            ],
            "physical_size_m": [
                dbs_full_upscaled.shape[1] * DBS_RES_M,
                dbs_full_upscaled.shape[0] * DBS_RES_M,
                DBS_RES_M,
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
