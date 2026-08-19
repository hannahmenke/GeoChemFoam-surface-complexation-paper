#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import numpy as np
from scipy import ndimage

from plot_latest_concentration_field import partition_sizes, read_int, stitch_field


VECTOR_RE = re.compile(
    r"internalField\s+nonuniform\s+List<vector>\s*(\d+)\s*\((.*?)\)\s*;",
    re.S,
)
UNIFORM_VECTOR_RE = re.compile(r"internalField\s+uniform\s*\(([^)]*)\)\s*;")


def read_vector(path: Path, expected: int) -> np.ndarray:
    text = path.read_text()
    uniform = UNIFORM_VECTOR_RE.search(text)
    if uniform:
        row = np.fromstring(uniform.group(1), sep=" ")
        return np.tile(row, (expected, 1))
    match = VECTOR_RE.search(text)
    if not match:
        raise RuntimeError(f"Cannot parse vector field {path}")
    count = int(match.group(1))
    values = np.fromstring(match.group(2).replace("(", " ").replace(")", " "), sep=" ")
    if count != expected or values.size != 3 * count:
        raise RuntimeError(f"Vector size mismatch in {path}: {count}, {values.size}, expected {expected}")
    return values.reshape(count, 3)


def stitch_vector(case_dir: Path, time: str, field: str) -> np.ndarray:
    system = case_dir / "system"
    npx, npy = read_int(system / "NPX"), read_int(system / "NPY")
    nx, ny = read_int(system / "Nx1"), read_int(system / "Ny1")
    xs, x0s = partition_sizes(nx, npx)
    ys, y0s = partition_sizes(ny, npy)
    out = np.empty((ny, nx, 3), dtype=np.float64)
    for py in range(npy):
        for px in range(npx):
            rank = py * npx + px
            values = read_vector(case_dir / f"processor{rank}" / time / field, xs[px] * ys[py])
            out[y0s[py] : y0s[py] + ys[py], x0s[px] : x0s[px] + xs[px], :] = values.reshape(ys[py], xs[px], 3)
    return out


def volume_fraction_for_flux(speed: np.ndarray, storage: np.ndarray, fraction: float) -> float:
    valid = storage > 1.0e-3
    flux_proxy = speed[valid] * storage[valid]
    volumes = storage[valid]
    order = np.argsort(flux_proxy)[::-1]
    cumulative = np.cumsum(flux_proxy[order])
    if cumulative[-1] <= 0:
        return float("nan")
    count = int(np.searchsorted(cumulative, fraction * cumulative[-1], side="left")) + 1
    return float(np.sum(volumes[order[:count]]) / np.sum(volumes))


def diagnose(case_dir: Path, time: str, resolved: bool) -> dict[str, float | int]:
    theta = stitch_field(case_dir, time, "eps").astype(np.float64)
    velocity = stitch_vector(case_dir, time, "U")
    speed = np.linalg.norm(velocity[:, :, :2], axis=2)
    ux = velocity[:, :, 0]
    active = theta > 1.0e-3
    storage = np.where(active, theta, 0.0)
    weighted_mean_speed = float(np.sum(speed * storage) / np.sum(storage))
    result: dict[str, float | int] = {
        "nx": theta.shape[1],
        "ny": theta.shape[0],
        "porosity_mean": float(np.mean(theta)),
        "storage_active_fraction": float(np.mean(active)),
        "storage_weighted_mean_speed_m_s": weighted_mean_speed,
        "storage_weighted_mean_ux_m_s": float(np.sum(ux * storage) / np.sum(storage)),
        "speed_max_m_s": float(np.max(speed)),
        "storage_fraction_carrying_50pct_flux_proxy": volume_fraction_for_flux(speed, storage, 0.5),
        "storage_fraction_carrying_90pct_flux_proxy": volume_fraction_for_flux(speed, storage, 0.9),
        "storage_fraction_below_1pct_mean_speed": float(np.sum(storage[speed < 0.01 * weighted_mean_speed]) / np.sum(storage)),
    }
    if resolved:
        pore = theta > 0.5
        labels, count = ndimage.label(pore, structure=np.array([[0, 1, 0], [1, 1, 1], [0, 1, 0]]))
        left = set(int(x) for x in np.unique(labels[:, 0]) if x)
        right = set(int(x) for x in np.unique(labels[:, -1]) if x)
        spanning = left & right
        spanning_mask = np.isin(labels, list(spanning)) if spanning else np.zeros_like(pore)
        result.update(
            {
                "pore_component_count": int(count),
                "spanning_component_count": len(spanning),
                "pore_cells_in_spanning_components_fraction": float(np.sum(spanning_mask) / np.sum(pore)),
                "total_cells_in_spanning_components_fraction": float(np.mean(spanning_mask)),
            }
        )
    return result


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolved", type=Path, required=True)
    parser.add_argument("--dbs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    summary = {
        "resolved": diagnose(args.resolved, "0", True),
        "dbs": diagnose(args.dbs, "0", False),
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
