#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


def numeric_times(case_dir: Path, field: str) -> list[tuple[float, str]]:
    times: list[tuple[float, str]] = []
    for child in (case_dir / "processor0").iterdir():
        if not child.is_dir():
            continue
        try:
            value = float(child.name)
        except ValueError:
            continue
        if value > 0 and (child / field).exists():
            times.append((value, child.name))
    return sorted(times)


def read_int(path: Path) -> int:
    return int(path.read_text().strip().split()[-1])


def partition_sizes(n_total: int, n_proc: int) -> tuple[list[int], list[int]]:
    base = n_total // n_proc
    rem = n_total % n_proc
    sizes: list[int] = []
    starts: list[int] = []
    start = 0
    for idx in range(n_proc):
        size = base + (1 if idx < rem else 0)
        sizes.append(size)
        starts.append(start)
        start += size
    return sizes, starts


def read_scalar_values(path: Path, expected_count: int) -> np.ndarray:
    text = path.read_text()
    uniform = re.search(r"internalField\s+uniform\s+([^;\n]+)\s*;", text)
    if uniform:
        return np.full(expected_count, float(uniform.group(1)), dtype=np.float32)
    match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not match:
        raise RuntimeError(f"Unsupported scalar field format: {path}")
    count = int(match.group(1))
    values = np.fromstring(match.group(2), sep=" ", count=count, dtype=np.float32)
    if values.size != count or values.size != expected_count:
        raise RuntimeError(
            f"{path}: expected {expected_count}/{count} values, got {values.size}"
        )
    return values


def stitch_field(case_dir: Path, time_name: str, field: str) -> np.ndarray:
    system = case_dir / "system"
    npx = read_int(system / "NPX")
    npy = read_int(system / "NPY")
    npz = read_int(system / "NPZ")
    nx_total = read_int(system / "Nx1")
    ny_total = read_int(system / "Ny1")
    nz_total = read_int(system / "Nz1")
    if nz_total != 1 or npz != 1:
        raise RuntimeError("This plotter expects a one-cell-thick 2D case.")

    x_sizes, x_starts = partition_sizes(nx_total, npx)
    y_sizes, y_starts = partition_sizes(ny_total, npy)
    image = np.full((ny_total, nx_total), np.nan, dtype=np.float32)

    for ipy in range(npy):
        for ipx in range(npx):
            rank = ipy * npx + ipx
            nx = x_sizes[ipx]
            ny = y_sizes[ipy]
            values = read_scalar_values(
                case_dir / f"processor{rank}" / time_name / field,
                expected_count=nx * ny,
            ).reshape((ny, nx))
            x0 = x_starts[ipx]
            y0 = y_starts[ipy]
            image[y0 : y0 + ny, x0 : x0 + nx] = values
    return image


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--metadata", type=Path, required=True)
    parser.add_argument("--field", default="Li+")
    parser.add_argument("--time", default="latest")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--inlet", type=float, default=1.0e-3)
    parser.add_argument("--x-max-mm", type=float)
    parser.add_argument("--log-scale", action="store_true")
    args = parser.parse_args()

    if args.time == "latest":
        time_value, time_name = numeric_times(args.case_dir, args.field)[-1]
    else:
        time_name = args.time
        time_value = float(args.time)

    image = stitch_field(args.case_dir, time_name, args.field)
    metadata = json.loads(args.metadata.read_text())
    geometry_key = (
        "dbs_full_upscaled"
        if args.case_dir.resolve().name == "dbs-upscaled"
        else "resolved_full_reference"
    )
    physical_size = metadata[geometry_key]["physical_size_m"]
    extent_mm = (0.0, physical_size[0] * 1000.0, 0.0, physical_size[1] * 1000.0)
    display = image / args.inlet if args.field == "Li+" else image
    visible = display
    if args.x_max_mm is not None:
        visible_nx = max(
            1,
            min(
                display.shape[1],
                int(np.ceil(display.shape[1] * args.x_max_mm / extent_mm[1])),
            ),
        )
        visible = display[:, :visible_nx]

    vmin = 0.0
    vmax = 1.0 if args.field == "Li+" else float(np.nanpercentile(visible, 99.5))
    if args.log_scale:
        positive = visible[np.isfinite(visible) & (visible > 0)]
        if positive.size == 0:
            raise RuntimeError("Log scaling requires at least one positive field value.")
        log_display = np.full(display.shape, np.nan, dtype=np.float32)
        np.log10(display, out=log_display, where=display > 0)
        display = log_display
        positive_log = np.log10(positive)
        vmin = float(np.nanmin(positive_log))
        vmax = float(np.nanmax(positive_log))
        if vmax <= vmin:
            raise RuntimeError("Log scaling requires more than one positive value.")

    fig, ax = plt.subplots(figsize=(7.0, 6.0), constrained_layout=True)
    im = ax.imshow(
        display,
        origin="lower",
        extent=extent_mm,
        cmap="viridis",
        interpolation="nearest",
        vmin=vmin,
        vmax=vmax,
    )
    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    if args.log_scale:
        cbar.set_label(f"log10({args.field})")
    else:
        cbar.set_label("Li+ / inlet concentration" if args.field == "Li+" else args.field)
    ax.set_title(f"{args.field} concentration field, t = {time_name} s")
    ax.set_xlabel("x [mm]")
    ax.set_ylabel("y [mm]")
    ax.set_aspect("auto" if args.x_max_mm is not None else "equal")
    if args.x_max_mm is not None:
        ax.set_xlim(0.0, args.x_max_mm)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=220)
    plt.close(fig)

    summary = {
        "case_dir": str(args.case_dir),
        "field": args.field,
        "time": time_name,
        "time_value": time_value,
        "shape": list(image.shape),
        "geometry": geometry_key,
        "physical_size_m": physical_size,
        "min": float(np.nanmin(image)),
        "max": float(np.nanmax(image)),
        "mean": float(np.nanmean(image)),
        "output": str(args.output),
    }
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
