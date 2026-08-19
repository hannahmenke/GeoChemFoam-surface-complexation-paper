#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np


def optional_float_env(name: str) -> float | None:
    value = os.environ.get(name)
    if value in (None, ""):
        return None
    return float(value)


def float_env_or_default(name: str, default: float) -> float:
    value = optional_float_env(name)
    return default if value is None else value


def load_raw_2d(path: Path, shape_x: int, shape_y: int) -> np.ndarray:
    raw = np.fromfile(path, dtype=np.uint8)
    expected = shape_x * shape_y
    if raw.size != expected:
        raise RuntimeError(f"Unexpected raw size for {path}: {raw.size} != {expected}")
    return raw.reshape((shape_y, shape_x))


def interface_length_2d(binary: np.ndarray, voxel_size: float) -> float:
    horizontal = np.count_nonzero(binary[:, 1:] != binary[:, :-1])
    vertical = np.count_nonzero(binary[1:, :] != binary[:-1, :])
    return float(horizontal + vertical) * voxel_size


def main() -> None:
    if len(sys.argv) != 4:
        raise SystemExit(
            "Usage: compute_matrix_rev_properties.py METADATA_JSON MATRIX_RAW OUT_JSON"
        )

    metadata_path = Path(sys.argv[1])
    matrix_raw_path = Path(sys.argv[2])
    out_path = Path(sys.argv[3])
    metadata = json.loads(metadata_path.read_text())
    matrix_metadata = metadata["matrix_rev"]
    shape_x, shape_y, _ = [int(value) for value in matrix_metadata["shape"]]
    voxel_size = float(matrix_metadata["voxel_size_m"])
    pore_value = int(matrix_metadata.get("pore_value", 255))

    matrix = load_raw_2d(matrix_raw_path, shape_x, shape_y)
    pore = matrix == pore_value
    porosity = float(pore.mean())
    bulk_area = shape_x * shape_y * voxel_size**2
    interface_length = interface_length_2d(pore, voxel_size)
    intrinsic_asurf = interface_length / bulk_area

    properties = {
        "source": {
            "metadata_file": str(metadata_path),
            "matrix_raw_file": str(matrix_raw_path),
            "source_image": metadata["source_images"]["resolved"],
            "crop": {
                key: matrix_metadata[key]
                for key in ("x_min", "x_max", "y_min", "y_max")
                if key in matrix_metadata
            },
            "voxel_size_m": voxel_size,
        },
        "computed_from_matrix_rev": {
            "porosity": porosity,
            "interface_length_per_unit_depth_m": interface_length,
            "intrinsic_asurf_per_bulk_volume_m-1": intrinsic_asurf,
            "method": "binary 2D voxel-edge interface length divided by REV bulk area",
        },
        "imported_transport_closure": {
            "porosity_from_dispersivity_paper": float_env_or_default(
                "MATRIX_REV_PAPER_POROSITY", 0.429
            ),
            "permeability_m2": float_env_or_default(
                "MATRIX_REV_PERMEABILITY_M2", 4.04e-12
            ),
            "effective_dispersion_model": {
                "quantity": "D_eff / D",
                "source_equation": "Maes and Menke (2024), multiscale micromodel matrix REV fit",
                "piecewise": [
                    {
                        "condition": "Pe < 1",
                        "D_ex_over_D": "0.5995 * (1 + 0.228 * Pe**1.1187)",
                        "D_ey_over_D": "0.5995 * (1 + 1.629 * Pe**1.663)",
                    },
                    {
                        "condition": "1 <= Pe < 10",
                        "D_ex_over_D": "0.5995 * (1 + 0.228 * Pe**1.1187)",
                        "D_ey_over_D": "0.5995 * (1 + 1.629 * Pe**0.546)",
                    },
                    {
                        "condition": "Pe >= 10",
                        "D_ex_over_D": "0.5995 * (1 + 0.088 * Pe**1.599)",
                        "D_ey_over_D": "0.5995 * (1 + 2.667 * Pe**0.332)",
                    },
                ],
            },
            "source": os.environ.get(
                "MATRIX_REV_TRANSPORT_SOURCE",
                "https://doi.org/10.1016/j.jece.2024.113729; arXiv:2405.06155 Eq. (51)",
            ),
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(properties, indent=2) + "\n")
    print(f"Wrote {out_path}")


if __name__ == "__main__":
    main()
