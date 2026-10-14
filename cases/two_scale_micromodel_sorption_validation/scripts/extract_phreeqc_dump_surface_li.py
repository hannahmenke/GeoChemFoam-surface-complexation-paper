#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import re
from pathlib import Path

import numpy as np

SURFACE_RE = re.compile(r"^\s*SURFACE_RAW\s+(\d+)\s*$")
LI_RE = re.compile(r"^\s*Li\s+([-+0-9.eE]+)\s*$")


def read_scalar(path: Path, expected_count: int) -> np.ndarray:
    text = path.read_text()
    uniform = re.search(r"internalField\s+uniform\s+([^;\s]+)\s*;", text)
    if uniform:
        return np.full(expected_count, float(uniform.group(1)), dtype=np.float64)
    match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not match:
        raise RuntimeError(f"Expected a nonuniform decomposed theta field: {path}")
    count = int(match.group(1))
    if count != expected_count:
        raise RuntimeError(f"{path}: expected {expected_count} cells, found {count}")
    values = np.fromstring(match.group(2), sep=" ", count=count, dtype=np.float64)
    if values.size != count:
        raise RuntimeError(f"{path}: expected {count} theta values, got {values.size}")
    return values


def parse_partition(
    task: tuple[Path, str, str | None, int, int, float]
) -> tuple[float, int, float | None]:
    case_dir, time_name, written_time, rank, n_cells, chemistry_min = task
    proc = case_dir / f"processor{rank}"
    theta_path = proc / time_name / "eps"
    theta = read_scalar(theta_path, n_cells)
    active_grid_cells = np.flatnonzero((theta > 1.0e-300) & (theta >= chemistry_min))

    weighted_li = 0.0
    surfaces = 0
    chemistry_id: int | None = None
    in_master_totals = False
    dump = proc / time_name / "phreeqcDBS.dmp"
    with dump.open(errors="replace") as stream:
        for line in stream:
            surface_match = SURFACE_RE.match(line)
            if surface_match:
                chemistry_id = int(surface_match.group(1))
                in_master_totals = False
                continue
            if chemistry_id is None:
                continue
            stripped = line.strip()
            if stripped.startswith("-component"):
                in_master_totals = stripped.split()[-1] == "Sor_a"
                continue
            if in_master_totals:
                li_match = LI_RE.match(line)
                if li_match:
                    if chemistry_id >= active_grid_cells.size:
                        raise RuntimeError(
                            f"{dump}: chemistry id {chemistry_id} exceeds "
                            f"{active_grid_cells.size} active cells"
                        )
                    grid_cell = int(active_grid_cells[chemistry_id])
                    weighted_li += float(li_match.group(1)) * theta[grid_cell]
                    surfaces += 1
                    chemistry_id = None
                    in_master_totals = False
    written_density_sum = None
    if written_time is not None:
        written_sor = read_scalar(proc / written_time / "Sor_aLi", n_cells)
        written_area = read_scalar(proc / written_time / "aSurf", n_cells)
        written_density_sum = float(np.sum(written_sor * written_area))
    return weighted_li, surfaces, written_density_sum


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--time", required=True)
    parser.add_argument("--chemistry-min", type=float, default=1.0e-3)
    parser.add_argument("--written-time")
    parser.add_argument("--workers", type=int, default=32)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()

    ranks = sorted(
        int(path.name.removeprefix("processor"))
        for path in args.case_dir.glob("processor*")
        if path.name.removeprefix("processor").isdigit()
    )
    def read_int(name: str) -> int:
        return int((args.case_dir / name).read_text().strip().split()[-1])

    nx, ny, nz = (read_int(name) for name in ("system/Nx1", "system/Ny1", "system/Nz1"))
    npx, npy, npz = (read_int(name) for name in ("system/NPX", "system/NPY", "system/NPZ"))

    def size(total: int, parts: int, index: int) -> int:
        return total // parts + (1 if index < total % parts else 0)

    tasks = []
    for rank in ranks:
        ipx = rank % npx
        ipy = (rank // npx) % npy
        ipz = rank // (npx * npy)
        n_cells = size(nx, npx, ipx) * size(ny, npy, ipy) * size(nz, npz, ipz)
        tasks.append(
            (
                args.case_dir,
                args.time,
                args.written_time,
                rank,
                n_cells,
                args.chemistry_min,
            )
        )
    with mp.Pool(min(args.workers, len(tasks))) as pool:
        parts = pool.map(parse_partition, tasks)

    total_cells = nx * ny * nz
    weighted_sum = sum(item[0] for item in parts)
    summary = {
        "case_dir": str(args.case_dir),
        "time": args.time,
        "partitions": len(ranks),
        "surface_cells_in_dump": sum(item[1] for item in parts),
        "internal_surface_li_inventory_density": weighted_sum / total_cells,
        "units": "kmol Li per m3 bulk (numerically mol/L-water times theta)",
    }
    if args.written_time is not None:
        summary["written_time"] = args.written_time
        summary["written_surface_li_inventory_density"] = (
            sum(float(item[2]) for item in parts if item[2] is not None) / total_cells
        )
    encoded = json.dumps(summary, indent=2) + "\n"
    print(encoded, end="")
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded)


if __name__ == "__main__":
    main()
