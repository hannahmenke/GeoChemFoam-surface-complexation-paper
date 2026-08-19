#!/usr/bin/env python3
"""Map selected boundary-face area to owner-cell aSurf values."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import numpy as np


def clean(text: str) -> str:
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.S)
    return re.sub(r"//.*", "", text)


def list_body(path: Path) -> tuple[int, str]:
    text = clean(path.read_text())
    matches = list(re.finditer(r"(?:^|\n)\s*(\d+)\s*\(\s*", text))
    if not matches:
        raise RuntimeError(f"No OpenFOAM list found in {path}")
    # The first counted list is the mesh payload. Face entries such as
    # ``4(0 1 2 3)`` also match this pattern and must not be mistaken for the
    # outer list header.
    match = matches[0]
    count = int(match.group(1))
    start = match.end()
    depth = 1
    cursor = start
    while cursor < len(text) and depth:
        depth += (text[cursor] == "(") - (text[cursor] == ")")
        cursor += 1
    if depth:
        raise RuntimeError(f"Unterminated OpenFOAM list in {path}")
    return count, text[start : cursor - 1]


def read_labels(path: Path) -> np.ndarray:
    count, body = list_body(path)
    values = np.fromstring(body, dtype=np.int64, sep=" ")
    if values.size != count:
        raise RuntimeError(f"Expected {count} labels in {path}, found {values.size}")
    return values


def read_points(path: Path) -> np.ndarray:
    count, body = list_body(path)
    rows = re.findall(r"\(\s*([^()]+?)\s*\)", body)
    points = np.asarray([[float(value) for value in row.split()] for row in rows])
    if points.shape != (count, 3):
        raise RuntimeError(f"Expected {count} points in {path}, found {points.shape}")
    return points


def read_faces(path: Path) -> list[np.ndarray]:
    count, body = list_body(path)
    rows = re.findall(r"\d*\s*\(\s*([^()]+?)\s*\)", body)
    faces = [np.fromstring(row, dtype=np.int64, sep=" ") for row in rows]
    if len(faces) != count:
        raise RuntimeError(f"Expected {count} faces in {path}, found {len(faces)}")
    return faces


def read_scalar_field(path: Path, count: int) -> np.ndarray:
    text = clean(path.read_text())
    uniform = re.search(r"internalField\s+uniform\s+([^;]+);", text)
    if uniform:
        return np.full(count, float(uniform.group(1)))
    match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        flags=re.S,
    )
    if not match:
        raise RuntimeError(f"No scalar internalField found in {path}")
    values = np.fromstring(match.group(2), dtype=float, sep=" ")
    if int(match.group(1)) != count or values.size != count:
        raise RuntimeError(f"Expected {count} scalar values in {path}, found {values.size}")
    return values


def boundary_ranges(path: Path, patch_pattern: re.Pattern[str]) -> list[tuple[str, int, int]]:
    text = clean(path.read_text())
    ranges: list[tuple[str, int, int]] = []
    for match in re.finditer(r"(?:^|\n)\s*([^\s{}()]+|\"[^\"]+\")\s*\{(.*?)\}", text, flags=re.S):
        name = match.group(1).strip('"')
        body = match.group(2)
        n_faces = re.search(r"\bnFaces\s+(\d+)\s*;", body)
        start_face = re.search(r"\bstartFace\s+(\d+)\s*;", body)
        if n_faces and start_face and patch_pattern.fullmatch(name):
            ranges.append((name, int(start_face.group(1)), int(n_faces.group(1))))
    if not ranges:
        raise RuntimeError(f"No boundary patch matching {patch_pattern.pattern!r} in {path}")
    return ranges


def polygon_area(vertices: np.ndarray) -> float:
    if len(vertices) < 3:
        return 0.0
    origin = vertices[0]
    cross_sum = np.zeros(3)
    for index in range(1, len(vertices) - 1):
        cross_sum += np.cross(vertices[index] - origin, vertices[index + 1] - origin)
    return 0.5 * float(np.linalg.norm(cross_sum))


def write_field(template_path: Path, output_path: Path, values: np.ndarray) -> None:
    text = template_path.read_text()
    text = re.sub(r"object\s+\S+;", "object      aSurf;", text, count=1)
    text = re.sub(r"dimensions\s+\[[^\]]+\];", "dimensions      [0 -1 0 0 0 0 0];", text, count=1)
    block = (
        "internalField   nonuniform List<scalar>\n"
        f"{values.size}\n(\n"
        + "\n".join(f"{value:.16g}" for value in values)
        + "\n)\n;"
    )
    text, replacements = re.subn(
        r"internalField\s+(?:uniform\s+[^;]+|nonuniform\s+List<scalar>\s*\d+\s*\(.*?\))\s*;",
        block,
        text,
        count=1,
        flags=re.S,
    )
    if replacements != 1:
        raise RuntimeError(f"Could not replace internalField in {template_path}")
    output_path.write_text(text)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path, nargs="?", default=Path("."))
    parser.add_argument("--time", default="0")
    parser.add_argument("--patch", default=r"(?:wall_.*|walls|solid)")
    parser.add_argument("--template", default="eps")
    args = parser.parse_args()

    case = args.case.resolve()
    mesh = case / "constant" / "polyMesh"
    time_dir = case / args.time
    points = read_points(mesh / "points")
    faces = read_faces(mesh / "faces")
    owner = read_labels(mesh / "owner")
    volumes = read_scalar_field(time_dir / "V", int(owner.max()) + 1)
    area = np.zeros_like(volumes)
    selected = boundary_ranges(mesh / "boundary", re.compile(args.patch))
    for _, start, count in selected:
        for face_index in range(start, start + count):
            area[owner[face_index]] += polygon_area(points[faces[face_index]])
    if np.any(volumes <= 0.0):
        raise RuntimeError("Cell volumes must be positive")
    values = area / volumes
    write_field(time_dir / args.template, time_dir / "aSurf", values)
    print(
        f"Created {time_dir / 'aSurf'} from {len(selected)} wall patches: "
        f"area={area.sum():.16e} m2 activeCells={np.count_nonzero(area)}"
    )


if __name__ == "__main__":
    main()
