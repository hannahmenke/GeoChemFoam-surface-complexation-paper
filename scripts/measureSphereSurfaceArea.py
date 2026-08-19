#!/usr/bin/env python3

"""Measure the two surface representations used by the sphere benchmark."""

from __future__ import annotations

import argparse
import csv
import json
import re
from pathlib import Path

import numpy as np

from createASurfMarchingCubes import marching_cubes_for_pair


def _foam_list(path: Path) -> tuple[int, str]:
    text = path.read_text()
    match = re.search(r"\n\s*(\d+)\s*\((.*?)\)\s*(?:;|\n// \*)", text, re.S)
    if not match:
        raise RuntimeError(f"Could not parse OpenFOAM list in {path}")
    return int(match.group(1)), match.group(2)


def parse_scalar_field(path: Path) -> np.ndarray:
    text = path.read_text()
    uniform = re.search(r"internalField\s+uniform\s+([^\n;]+)\s*;", text)
    if uniform:
        return np.asarray([float(uniform.group(1))])
    values = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not values:
        raise RuntimeError(f"Unsupported scalar field in {path}")
    result = np.asarray([float(value) for value in values.group(2).split()])
    if result.size != int(values.group(1)):
        raise RuntimeError(f"Scalar count mismatch in {path}")
    return result


def parse_points(path: Path) -> np.ndarray:
    count, body = _foam_list(path)
    raw = re.findall(r"\(([^()]+)\)", body)
    if len(raw) != count:
        raise RuntimeError(f"Point count mismatch in {path}")
    return np.asarray([[float(value) for value in point.split()] for point in raw])


def parse_faces(path: Path) -> list[list[int]]:
    count, body = _foam_list(path)
    faces = [[int(value) for value in face.split()] for _, face in re.findall(r"(\d+)\(([^()]*)\)", body)]
    if len(faces) != count:
        raise RuntimeError(f"Face count mismatch in {path}")
    return faces


def parse_boundary(path: Path) -> dict[str, dict[str, int]]:
    result: dict[str, dict[str, int]] = {}
    for name, body in re.findall(
        r'^\s*([A-Za-z0-9_".]+)\s*\n\s*\{(.*?)^\s*\}',
        path.read_text(),
        re.M | re.S,
    ):
        start = re.search(r"startFace\s+(\d+)\s*;", body)
        count = re.search(r"nFaces\s+(\d+)\s*;", body)
        if start and count:
            result[name.strip('"')] = {"startFace": int(start.group(1)), "nFaces": int(count.group(1))}
    return result


def polygon_area(points: np.ndarray) -> float:
    return float(
        sum(
            0.5 * np.linalg.norm(np.cross(points[index] - points[0], points[index + 1] - points[0]))
            for index in range(1, len(points) - 1)
        )
    )


def patch_area(poly_mesh: Path, patch_name: str) -> float:
    points = parse_points(poly_mesh / "points")
    faces = parse_faces(poly_mesh / "faces")
    boundary = parse_boundary(poly_mesh / "boundary")
    if patch_name not in boundary:
        raise RuntimeError(f"Patch {patch_name!r} not found")
    start = boundary[patch_name]["startFace"]
    count = boundary[patch_name]["nFaces"]

    return float(sum(polygon_area(points[np.asarray(face)]) for face in faces[start : start + count]))


def smooth_area(raw_path: Path, metadata: dict, sigma: float) -> tuple[float, int]:
    shape = (int(metadata["nz"]), int(metadata["ny"]), int(metadata["nx"]))
    volume = np.fromfile(raw_path, dtype=np.uint8).reshape(shape)
    owner = volume == int(metadata["pore_value"])
    vertices, faces, mode = marching_cubes_for_pair(
        owner,
        np.ones_like(owner, dtype=bool),
        float(metadata["dx"]),
        "occupancyGaussian",
        sigma,
    )
    if mode != "occupancyGaussian":
        raise RuntimeError(f"Unexpected reconstruction fallback: {mode}")
    triangles = vertices[faces]
    areas = 0.5 * np.linalg.norm(
        np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]),
        axis=1,
    )
    return float(areas.sum()), int(len(faces))


def metric(method: str, area: float, metadata: dict, triangles: int | None = None) -> dict:
    analytic = float(metadata["analytic_area"])
    voxel = float(metadata["voxel_face_area"])
    row = {
        "method": method,
        "area": area,
        "rel_err_vs_analytic": (area - analytic) / analytic,
        "rel_err_vs_voxel": (area - voxel) / voxel,
        "triangles": "" if triangles is None else triangles,
    }
    return row


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference-json", type=Path, required=True)
    parser.add_argument("--snappy-case", type=Path, required=True)
    parser.add_argument("--snappy-patch", default="sphere")
    parser.add_argument("--sigma", type=float, default=0.75)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    metadata = json.loads(args.reference_json.read_text())
    raw_path = args.reference_json.parent / metadata["raw_path"]
    snappy = patch_area(args.snappy_case / "constant/polyMesh", args.snappy_patch)
    smooth, triangles = smooth_area(raw_path, metadata, args.sigma)
    rows = [
        metric("snappy", snappy, metadata),
        metric("dbs-smoothed-mc", smooth, metadata, triangles),
    ]

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "area_metrics.json").write_text(
        json.dumps({"metadata": metadata, "rows": rows}, indent=2) + "\n"
    )
    with (args.output_dir / "area_metrics.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    for row in rows:
        print(f"{row['method']}: area={row['area']:.12e}, error={row['rel_err_vs_analytic']:+.6%}")


if __name__ == "__main__":
    main()
