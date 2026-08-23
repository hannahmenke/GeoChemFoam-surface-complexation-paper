#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

import numpy as np


CASE_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = Path(__file__).resolve().parents[5]
PYTOOLS = REPO_ROOT / "applications" / "utilities" / "pyTools"
SCRIPTS = REPO_ROOT / "scripts"
if str(PYTOOLS) not in sys.path:
    sys.path.insert(0, str(PYTOOLS))
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from measureSphereSurfaceArea import parse_boundary, parse_faces, parse_points, parse_scalar_field, polygon_area
from createASurfMarchingCubes import build_field, marching_cubes_for_pair


PORE_LABEL = 1
SOLID_LABEL = 3
VOXEL_SIZE = 4e-6
SIGMA_VOX = 0.74
TRANSPORT_TIME = "2.5"
DOMAIN_LENGTH = 128 * VOXEL_SIZE
SNAPPY_PRESSURE_DROP = 0.0112
DBS_PRESSURE_DROP = 0.00925406150930
KINEMATIC_VISCOSITY = 1e-6


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Analyze the 3D external surface flow validation.")
    parser.add_argument("--output-csv", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    return parser.parse_args()


def load_phase_crop() -> np.ndarray:
    path = CASE_ROOT / "shared" / "estaillades_external_crop_phase.raw"
    raw = np.fromfile(path, dtype=np.uint8)
    expected = 128 * 128 * 128
    if raw.size != expected:
        raise RuntimeError(f"Unexpected crop size: {raw.size} != {expected}")
    return raw.reshape((128, 128, 128))


def smoothsurface_area(image: np.ndarray) -> tuple[float, int, str]:
    owner_mask = image == PORE_LABEL
    pair_mask = owner_mask | (image == SOLID_LABEL)
    verts, faces, used_mode = marching_cubes_for_pair(
        owner_mask,
        pair_mask,
        VOXEL_SIZE,
        "occupancyGaussian",
        SIGMA_VOX,
    )
    nz, ny, nx = image.shape
    asurf, _ = build_field(
        verts,
        faces,
        image,
        nx,
        ny,
        nz,
        1,
        1,
        1,
        VOXEL_SIZE,
        PORE_LABEL,
    )
    return float(np.sum(asurf) * VOXEL_SIZE**3), int(faces.shape[0]), used_mode


def read_poro_perm(case_dir: Path, pressure_drop: float) -> dict[str, float | None]:
    path = case_dir / "poroPerm.csv"
    if not path.exists():
        return dbs_flow_metrics_from_fields(case_dir, pressure_drop)
    with path.open() as handle:
        rows = [line.split() for line in handle if line.strip()]
    if len(rows) < 2:
        return dbs_flow_metrics_from_fields(case_dir, pressure_drop)
    header = rows[0]
    values = rows[-1]
    data = {key: float(value) for key, value in zip(header, values)}
    return {
        "porosity": data.get("poro"),
        "permeability": data.get("perm"),
        "darcy_velocity": data.get("UD"),
        "reynolds": data.get("Re"),
        "tau": data.get("tau"),
    }


def parse_vector_field(path: Path) -> np.ndarray:
    text = path.read_text()
    match = re.search(
        r"internalField\s+nonuniform\s+List<vector>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if match:
        count = int(match.group(1))
        triples = re.findall(r"\(([^()]+)\)", match.group(2))
        values = np.array([[float(x) for x in triple.split()] for triple in triples], dtype=float)
        if values.shape != (count, 3):
            raise RuntimeError(f"Vector field count mismatch in {path}: {values.shape} != {(count, 3)}")
        return values
    uniform = re.search(r"internalField\s+uniform\s+\(([^()]+)\)\s*;", text)
    if uniform:
        return np.array([[float(x) for x in uniform.group(1).split()]], dtype=float)
    raise RuntimeError(f"Could not parse vector field {path}")


def dbs_flow_metrics_from_fields(case_dir: Path, pressure_drop: float) -> dict[str, float | None]:
    eps_paths = sorted(case_dir.glob("processor*/0/eps"))
    u_paths = sorted(case_dir.glob("processor*/0/U"))
    if not eps_paths or not u_paths or len(eps_paths) != len(u_paths):
        return {"porosity": None, "permeability": None, "darcy_velocity": None, "reynolds": None, "tau": None}

    eps_sum = 0.0
    ux_sum = 0.0
    mag_u_sum = 0.0
    n_cells = 0
    for eps_path, u_path in zip(eps_paths, u_paths):
        eps = parse_scalar_field(eps_path)
        u = parse_vector_field(u_path)
        if u.shape[0] == 1 and eps.size != 1:
            u = np.repeat(u, eps.size, axis=0)
        if eps.size != u.shape[0]:
            raise RuntimeError(f"eps/U size mismatch in {case_dir}: {eps.size} != {u.shape[0]}")
        eps_sum += float(np.sum(eps))
        ux_sum += float(np.sum(u[:, 0]))
        mag_u_sum += float(np.sum(np.linalg.norm(u, axis=1)))
        n_cells += int(eps.size)

    if n_cells == 0:
        return {"porosity": None, "permeability": None, "darcy_velocity": None, "reynolds": None, "tau": None}

    porosity = eps_sum / n_cells
    darcy_velocity = ux_sum / n_cells
    abs_darcy_velocity = abs(darcy_velocity)
    pressure_gradient = pressure_drop / DOMAIN_LENGTH
    permeability = abs_darcy_velocity * KINEMATIC_VISCOSITY / pressure_gradient
    tau = (mag_u_sum / n_cells) / (abs_darcy_velocity + 1e-30)
    lpore = np.sqrt(8.0 * permeability / porosity) if porosity > 0 and permeability >= 0 else None
    reynolds = abs_darcy_velocity / porosity * lpore / KINEMATIC_VISCOSITY if lpore is not None else None
    return {
        "porosity": porosity,
        "permeability": permeability,
        "darcy_velocity": abs_darcy_velocity,
        "reynolds": reynolds,
        "tau": tau,
    }


def latest_field_path(case_dir: Path, time_name: str, field_name: str, fallback_time: str = "0") -> Path | None:
    path = case_dir / time_name / field_name
    if path.exists():
        return path
    path = case_dir / fallback_time / field_name
    if path.exists():
        return path
    return None


def processor_field_paths(case_dir: Path, time_name: str, field_name: str, fallback_time: str = "0") -> list[Path]:
    paths = sorted(case_dir.glob(f"processor*/{time_name}/{field_name}"))
    if paths:
        return paths
    return sorted(case_dir.glob(f"processor*/{fallback_time}/{field_name}"))


def cell_reactive_area(case_dir: Path, time_name: str = "0") -> float:
    """Return the area used by cell-based surface reactions: sum(aSurf * V)."""
    cell_volume = VOXEL_SIZE**3
    a_surf_paths = processor_field_paths(case_dir, time_name, "aSurf")
    if a_surf_paths:
        total = 0.0
        for a_surf_path in a_surf_paths:
            a_surf = parse_scalar_field(a_surf_path)
            volume_path = a_surf_path.parent / "V"
            if not volume_path.exists():
                volume_path = a_surf_path.parents[1] / "0" / "V"
            volumes = parse_scalar_field(volume_path) if volume_path.exists() else cell_volume
            if volumes.size not in (1, a_surf.size):
                raise RuntimeError(
                    f"aSurf/V size mismatch in {a_surf_path.parent}: "
                    f"{a_surf.size} != {volumes.size}"
                )
            total += float(np.sum(a_surf * volumes))
        return total

    a_surf_path = latest_field_path(case_dir, time_name, "aSurf")
    if a_surf_path is None:
        raise RuntimeError(f"No aSurf field found in {case_dir}")
    a_surf = parse_scalar_field(a_surf_path)
    volume_path = latest_field_path(case_dir, "0", "V")
    volumes = parse_scalar_field(volume_path) if volume_path is not None else cell_volume
    if volumes.size not in (1, a_surf.size):
        raise RuntimeError(
            f"aSurf/V size mismatch in {case_dir}: {a_surf.size} != {volumes.size}"
        )
    return float(np.sum(a_surf * volumes))


def cell_sorbed_inventory(case_dir: Path, time_name: str = TRANSPORT_TIME) -> float | None:
    cell_volume = VOXEL_SIZE**3
    internal_paths = processor_field_paths(case_dir, time_name, "Surf_aSr+")
    if internal_paths:
        total = 0.0
        for sorbed_path in internal_paths:
            proc_zero = sorbed_path.parents[1] / "0"
            a_surf_path = sorbed_path.parent / "aSurf"
            if not a_surf_path.exists():
                a_surf_path = proc_zero / "aSurf"
            if not a_surf_path.exists():
                return None
            sorbed = parse_scalar_field(sorbed_path)
            a_surf = parse_scalar_field(a_surf_path)
            volume_path = proc_zero / "V"
            volumes = parse_scalar_field(volume_path) if volume_path.exists() else cell_volume
            total += float(np.sum(sorbed * a_surf * volumes))
        return total

    sorbed_path = latest_field_path(case_dir, time_name, "Surf_aSr+")
    a_surf_path = latest_field_path(case_dir, time_name, "aSurf")
    if a_surf_path is None:
        a_surf_path = latest_field_path(case_dir, "0", "aSurf")
    if sorbed_path is None or a_surf_path is None:
        return None
    volume_path = latest_field_path(case_dir, "0", "V")
    volumes = parse_scalar_field(volume_path) if volume_path is not None else cell_volume
    return float(
        np.sum(parse_scalar_field(sorbed_path) * parse_scalar_field(a_surf_path) * volumes)
    )


def patch_face_areas(poly_mesh_dir: Path, patch_name: str) -> np.ndarray:
    points = parse_points(poly_mesh_dir / "points")
    faces = parse_faces(poly_mesh_dir / "faces")
    boundary = parse_boundary(poly_mesh_dir / "boundary")
    if patch_name not in boundary:
        return np.zeros(0, dtype=float)
    patch = boundary[patch_name]
    start = patch["startFace"]
    end = start + patch["nFaces"]
    return np.array(
        [polygon_area(points[np.array(face, dtype=int)]) for face in faces[start:end]],
        dtype=float,
    )


def patch_scalar_values(field_path: Path, patch_name: str, n_faces: int) -> np.ndarray:
    text = field_path.read_text()
    pattern = rf"^\s*{re.escape(patch_name)}\s*\n\s*\{{\n(.*?)^\s*\}}"
    match = re.search(pattern, text, re.M | re.S)
    if not match:
        return np.zeros(0, dtype=float)
    body = match.group(1)
    uniform_match = re.search(r"value\s+uniform\s+([^;]+);", body)
    if uniform_match:
        return np.full(n_faces, float(uniform_match.group(1)), dtype=float)
    nonuniform_match = re.search(
        r"value\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        body,
        re.S,
    )
    if not nonuniform_match:
        return np.zeros(n_faces, dtype=float)
    count = int(nonuniform_match.group(1))
    values = np.array([float(item) for item in nonuniform_match.group(2).split()], dtype=float)
    if values.size != count:
        raise RuntimeError(f"Patch value count mismatch in {field_path}:{patch_name}")
    if values.size != n_faces:
        raise RuntimeError(f"Patch values/faces mismatch in {field_path}:{patch_name}: {values.size} != {n_faces}")
    return values


def snappy_sorbed_inventory(case_dir: Path, time_name: str = TRANSPORT_TIME, patch_name: str = "solidwalls") -> float | None:
    field_paths = processor_field_paths(case_dir, time_name, "Surf_aSr+")
    if not field_paths:
        field_path = latest_field_path(case_dir, time_name, "Surf_aSr+")
        if field_path is None:
            return None
        areas = patch_face_areas(case_dir / "constant" / "polyMesh", patch_name)
        values = patch_scalar_values(field_path, patch_name, areas.size)
        return float(np.sum(values * areas))

    total = 0.0
    found = False
    for field_path in field_paths:
        proc_dir = field_path.parents[1]
        areas = patch_face_areas(proc_dir / "constant" / "polyMesh", patch_name)
        if areas.size == 0:
            continue
        values = patch_scalar_values(field_path, patch_name, areas.size)
        total += float(np.sum(values * areas))
        found = True
    return total if found else None


def rel(value: float | None, reference: float | None) -> float | None:
    if value is None or reference is None or reference == 0.0:
        return None
    return (value - reference) / reference


def main() -> None:
    args = parse_args()
    image = load_phase_crop()

    # Use the discretized area supplied to the chemistry rather than the sum of
    # a triangle fan over each warped wall face. This is the same sum(aSurf*V)
    # measure used to form the cell sorbed inventory below.
    snappy_area = cell_reactive_area(CASE_ROOT / "snappy")
    smooth_area, triangles, used_mode = smoothsurface_area(image)

    flow = {
        "snappy": read_poro_perm(CASE_ROOT / "snappy", SNAPPY_PRESSURE_DROP),
        "dbs-smoothsurface": read_poro_perm(CASE_ROOT / "dbs-smoothsurface", DBS_PRESSURE_DROP),
    }
    sorbed_inventory = {
        "snappy": cell_sorbed_inventory(CASE_ROOT / "snappy"),
        "dbs-smoothsurface": cell_sorbed_inventory(CASE_ROOT / "dbs-smoothsurface"),
    }

    rows = [
        {
            "method": "snappy",
            "surface_area": snappy_area,
            "surface_area_relative_to_snappy": 0.0,
            "surface_triangles": None,
            "surface_mode": "resolved-wall-cell-aSurf",
            "sorbed_sr_inventory": sorbed_inventory["snappy"],
            "sorbed_sr_inventory_relative_to_snappy": 0.0 if sorbed_inventory["snappy"] is not None else None,
            **flow["snappy"],
        },
        {
            "method": "dbs-smoothsurface",
            "surface_area": smooth_area,
            "surface_area_relative_to_snappy": rel(smooth_area, snappy_area),
            "surface_triangles": triangles,
            "surface_mode": used_mode,
            "sorbed_sr_inventory": sorbed_inventory["dbs-smoothsurface"],
            "sorbed_sr_inventory_relative_to_snappy": rel(sorbed_inventory["dbs-smoothsurface"], sorbed_inventory["snappy"]),
            **flow["dbs-smoothsurface"],
        },
    ]

    for row in rows:
        row["permeability_relative_to_snappy"] = rel(row["permeability"], flow["snappy"]["permeability"])
        row["darcy_velocity_relative_to_snappy"] = rel(row["darcy_velocity"], flow["snappy"]["darcy_velocity"])

    args.output_csv.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = [
        "method",
        "surface_mode",
        "surface_area",
        "surface_area_relative_to_snappy",
        "surface_triangles",
        "sorbed_sr_inventory",
        "sorbed_sr_inventory_relative_to_snappy",
        "porosity",
        "permeability",
        "permeability_relative_to_snappy",
        "darcy_velocity",
        "darcy_velocity_relative_to_snappy",
        "reynolds",
        "tau",
    ]
    with args.output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)

    metadata = {
        "voxel_size": VOXEL_SIZE,
        "smooth_sigma_vox": SIGMA_VOX,
        "pressure_drop_pa": {
            "snappy": SNAPPY_PRESSURE_DROP,
            "dbs-smoothsurface": DBS_PRESSURE_DROP,
        },
        "transport_time": TRANSPORT_TIME,
        "rows": rows,
    }
    args.output_json.write_text(json.dumps(metadata, indent=2))
    print(json.dumps(metadata, indent=2))


if __name__ == "__main__":
    main()
