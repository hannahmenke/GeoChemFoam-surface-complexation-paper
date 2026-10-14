#!/usr/bin/env python3

from __future__ import annotations

import argparse
import json
import math
import tarfile
from pathlib import Path

import numpy as np


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a perfectly symmetric voxelized sphere, an analytic STL, "
            "and reference surface-area metrics."
        )
    )
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--name", required=True)
    parser.add_argument("--nx", type=int, required=True)
    parser.add_argument("--ny", type=int, required=True)
    parser.add_argument("--nz", type=int, required=True)
    parser.add_argument("--dx", type=float, required=True)
    parser.add_argument(
        "--radius",
        type=float,
        required=True,
        help="Physical sphere radius in the same units as dx.",
    )
    parser.add_argument(
        "--solid-value",
        type=int,
        default=0,
        help="Voxel value for solid sphere cells.",
    )
    parser.add_argument(
        "--pore-value",
        type=int,
        default=255,
        help="Voxel value for the pore/background phase.",
    )
    parser.add_argument(
        "--stl-subdivisions",
        type=int,
        default=3,
        help="Icosphere subdivision level for the analytic STL.",
    )
    return parser.parse_args()


def assert_odd(name: str, value: int) -> None:
    if value <= 0 or value % 2 == 0:
        raise ValueError(f"{name} must be a positive odd integer, got {value}")


def build_centered_coords(n: int, dx: float) -> np.ndarray:
    indices = np.arange(n, dtype=float)
    centre_index = (n - 1) / 2.0
    return (indices - centre_index) * dx


def build_solid_mask(nx: int, ny: int, nz: int, dx: float, radius: float) -> np.ndarray:
    x = build_centered_coords(nx, dx)
    y = build_centered_coords(ny, dx)
    z = build_centered_coords(nz, dx)
    xx, yy, zz = np.meshgrid(x, y, z, indexing="ij")
    return (xx * xx + yy * yy + zz * zz) <= radius * radius


def symmetry_report(mask: np.ndarray) -> dict[str, bool]:
    return {
        "x_mirror": bool(np.array_equal(mask, mask[::-1, :, :])),
        "y_mirror": bool(np.array_equal(mask, mask[:, ::-1, :])),
        "z_mirror": bool(np.array_equal(mask, mask[:, :, ::-1])),
    }


def voxel_face_area(mask: np.ndarray, dx: float) -> float:
    area_faces = 0
    area_faces += int(np.count_nonzero(mask[1:, :, :] != mask[:-1, :, :]))
    area_faces += int(np.count_nonzero(mask[:, 1:, :] != mask[:, :-1, :]))
    area_faces += int(np.count_nonzero(mask[:, :, 1:] != mask[:, :, :-1]))
    return area_faces * dx * dx


def make_icosahedron() -> tuple[list[np.ndarray], list[tuple[int, int, int]]]:
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    raw_vertices = [
        (-1, phi, 0),
        (1, phi, 0),
        (-1, -phi, 0),
        (1, -phi, 0),
        (0, -1, phi),
        (0, 1, phi),
        (0, -1, -phi),
        (0, 1, -phi),
        (phi, 0, -1),
        (phi, 0, 1),
        (-phi, 0, -1),
        (-phi, 0, 1),
    ]
    vertices = []
    for vec in raw_vertices:
        arr = np.array(vec, dtype=float)
        vertices.append(arr / np.linalg.norm(arr))

    faces = [
        (0, 11, 5),
        (0, 5, 1),
        (0, 1, 7),
        (0, 7, 10),
        (0, 10, 11),
        (1, 5, 9),
        (5, 11, 4),
        (11, 10, 2),
        (10, 7, 6),
        (7, 1, 8),
        (3, 9, 4),
        (3, 4, 2),
        (3, 2, 6),
        (3, 6, 8),
        (3, 8, 9),
        (4, 9, 5),
        (2, 4, 11),
        (6, 2, 10),
        (8, 6, 7),
        (9, 8, 1),
    ]
    return vertices, faces


def midpoint(
    vertices: list[np.ndarray],
    cache: dict[tuple[int, int], int],
    i: int,
    j: int,
) -> int:
    key = (i, j) if i < j else (j, i)
    if key in cache:
        return cache[key]
    vec = vertices[i] + vertices[j]
    vec /= np.linalg.norm(vec)
    vertices.append(vec)
    index = len(vertices) - 1
    cache[key] = index
    return index


def make_icosphere(subdivisions: int) -> tuple[np.ndarray, list[tuple[int, int, int]]]:
    vertices, faces = make_icosahedron()
    for _ in range(subdivisions):
        cache: dict[tuple[int, int], int] = {}
        new_faces: list[tuple[int, int, int]] = []
        for i, j, k in faces:
            a = midpoint(vertices, cache, i, j)
            b = midpoint(vertices, cache, j, k)
            c = midpoint(vertices, cache, k, i)
            new_faces.extend(
                [
                    (i, a, c),
                    (j, b, a),
                    (k, c, b),
                    (a, b, c),
                ]
            )
        faces = new_faces
    return np.array(vertices, dtype=float), faces


def write_ascii_stl(path: Path, vertices: np.ndarray, faces: list[tuple[int, int, int]], radius: float) -> None:
    with path.open("w") as handle:
        handle.write("solid symmetric_sphere\n")
        for i, j, k in faces:
            tri = np.array([vertices[i], vertices[j], vertices[k]], dtype=float) * radius
            normal = np.cross(tri[1] - tri[0], tri[2] - tri[0])
            norm = np.linalg.norm(normal)
            if norm > 0.0:
                normal /= norm
            else:
                normal = np.array([0.0, 0.0, 0.0], dtype=float)
            handle.write(
                f"  facet normal {normal[0]:.12e} {normal[1]:.12e} {normal[2]:.12e}\n"
            )
            handle.write("    outer loop\n")
            for point in tri:
                handle.write(
                    f"      vertex {point[0]:.12e} {point[1]:.12e} {point[2]:.12e}\n"
                )
            handle.write("    endloop\n")
            handle.write("  endfacet\n")
        handle.write("endsolid symmetric_sphere\n")


def write_raw_assets(output_dir: Path, name: str, data_xyz: np.ndarray) -> tuple[Path, Path]:
    raw_path = output_dir / f"{name}.raw"
    # OpenFOAM helper scripts historically use raw files written in z,y,x order.
    data_zyx = np.transpose(data_xyz, (2, 1, 0)).astype(np.uint8, copy=False)
    data_zyx.tofile(raw_path)
    tar_path = output_dir / f"{name}.raw.tar.gz"
    with tarfile.open(tar_path, "w:gz") as archive:
        archive.add(raw_path, arcname=raw_path.name)
    return raw_path, tar_path


def main() -> None:
    args = parse_args()

    assert_odd("nx", args.nx)
    assert_odd("ny", args.ny)
    assert_odd("nz", args.nz)

    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    solid_mask = build_solid_mask(args.nx, args.ny, args.nz, args.dx, args.radius)
    symmetry = symmetry_report(solid_mask)
    if not all(symmetry.values()):
        raise RuntimeError(f"Generated sphere mask is not symmetric: {symmetry}")

    raw_values = np.full((args.nx, args.ny, args.nz), args.pore_value, dtype=np.uint8)
    raw_values[solid_mask] = np.uint8(args.solid_value)

    raw_path, tar_path = write_raw_assets(output_dir, args.name, raw_values)

    stl_vertices, stl_faces = make_icosphere(args.stl_subdivisions)
    stl_path = output_dir / f"{args.name}_analytic.stl"
    write_ascii_stl(stl_path, stl_vertices, stl_faces, args.radius)

    analytic_area = 4.0 * math.pi * args.radius * args.radius
    voxel_area = voxel_face_area(solid_mask, args.dx)

    metadata = {
        "name": args.name,
        "nx": args.nx,
        "ny": args.ny,
        "nz": args.nz,
        "dx": args.dx,
        "radius": args.radius,
        "solid_value": args.solid_value,
        "pore_value": args.pore_value,
        "analytic_area": analytic_area,
        "voxel_face_area": voxel_area,
        "radius_over_dx": args.radius / args.dx,
        "solid_voxel_count": int(np.count_nonzero(solid_mask)),
        "symmetry": symmetry,
        "raw_path": raw_path.name,
        "raw_tar_path": tar_path.name,
        "analytic_stl_path": stl_path.name,
        "stl_subdivisions": args.stl_subdivisions,
    }

    (output_dir / f"{args.name}.json").write_text(json.dumps(metadata, indent=2))

    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
