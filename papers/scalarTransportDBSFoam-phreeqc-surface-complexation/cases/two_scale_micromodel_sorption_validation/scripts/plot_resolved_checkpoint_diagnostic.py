#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def numeric_times(case_dir: Path) -> list[float]:
    proc0 = case_dir / "processor0"
    times: list[float] = []
    for path in proc0.iterdir():
        if path.is_dir():
            try:
                times.append(float(path.name))
            except ValueError:
                pass
    return sorted(times)


def time_name(value: float) -> str:
    return str(int(value)) if value == int(value) else f"{value:g}"


def read_scalar_values(path: Path) -> np.ndarray:
    text = path.read_text()
    uniform = re.search(r"internalField\s+uniform\s+([^;\n]+)\s*;", text)
    if uniform:
        return np.array([float(uniform.group(1))], dtype=np.float32)
    match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not match:
        raise RuntimeError(f"Unsupported scalar field format: {path}")
    count = int(match.group(1))
    values = np.fromstring(match.group(2), sep=" ", count=count, dtype=np.float32)
    if values.size != count:
        raise RuntimeError(f"Value count mismatch in {path}: {values.size} != {count}")
    return values


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


def block_mean_2d(values: np.ndarray, ny: int, nx: int, stride: int) -> np.ndarray:
    arr = values.reshape((ny, nx))
    crop_y = (ny // stride) * stride
    crop_x = (nx // stride) * stride
    arr = arr[:crop_y, :crop_x]
    return arr.reshape(crop_y // stride, stride, crop_x // stride, stride).mean(axis=(1, 3))


def stitch_downsampled(case_dir: Path, t_name: str, field: str, stride: int) -> np.ndarray:
    system = case_dir / "system"
    npx = read_int(system / "NPX")
    npy = read_int(system / "NPY")
    npz = read_int(system / "NPZ")
    nx_total = read_int(system / "Nx1")
    ny_total = read_int(system / "Ny1")
    nz_total = read_int(system / "Nz1")
    if nz_total != 1 or npz != 1:
        raise RuntimeError("This diagnostic expects the equal-domain 2D extrusion.")
    if nx_total % stride or ny_total % stride:
        raise RuntimeError(f"Stride {stride} must divide {nx_total} x {ny_total}.")

    x_sizes, x_starts = partition_sizes(nx_total, npx)
    y_sizes, y_starts = partition_sizes(ny_total, npy)
    out = np.zeros((ny_total // stride, nx_total // stride), dtype=np.float32)

    for proc_dir in sorted(case_dir.glob("processor*")):
        rank = int(proc_dir.name.replace("processor", ""))
        ipy = (rank % (npx * npy)) // npx
        ipx = rank % npx
        nx = x_sizes[ipx]
        ny = y_sizes[ipy]
        if nx % stride or ny % stride:
            raise RuntimeError(f"Stride {stride} does not divide local block {nx} x {ny}.")
        values = read_scalar_values(proc_dir / t_name / field)
        if values.size == 1:
            values = np.full(nx * ny, float(values[0]), dtype=np.float32)
        block = block_mean_2d(values, ny, nx, stride)
        x0 = x_starts[ipx] // stride
        y0 = y_starts[ipy] // stride
        out[y0 : y0 + block.shape[0], x0 : x0 + block.shape[1]] = block
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, default=Path("resolved-reference"))
    parser.add_argument("--time", default="latest")
    parser.add_argument("--stride", type=int, default=10)
    parser.add_argument("--li-inlet", type=float, default=1.0e-3)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    case_dir = args.case_dir
    if args.time == "latest":
        t_value = numeric_times(case_dir)[-1]
        t_name = time_name(t_value)
    else:
        t_name = args.time
        t_value = float(args.time)

    print(f"Reading {case_dir} at t={t_name} with stride={args.stride}")
    theta = stitch_downsampled(case_dir, t_name, "theta", args.stride)
    li = stitch_downsampled(case_dir, t_name, "Li+", args.stride)
    sor_li = stitch_downsampled(case_dir, t_name, "Sor_aLi", args.stride)
    asurf = stitch_downsampled(case_dir, t_name, "aSurf", args.stride)

    li_norm = np.clip(li / args.li_inlet, 0.0, 1.05)
    sor_display = np.where(asurf > 0.0, sor_li, np.nan)
    x_mm = np.linspace(0.0, 18.0, li.shape[1])
    pore_weights = np.maximum(theta, 0.0)
    li_profile = np.divide(
        (li_norm * pore_weights).sum(axis=0),
        np.maximum(pore_weights.sum(axis=0), 1.0e-30),
    )
    sor_profile = np.nanmean(sor_display, axis=0)

    fig, axes = plt.subplots(2, 2, figsize=(12.0, 6.8), constrained_layout=True)
    extent = (0, 18, 0, 6)

    im0 = axes[0, 0].imshow(theta, origin="upper", extent=extent, cmap="gray_r", vmin=0, vmax=1)
    axes[0, 0].set_title("Porosity/phase field")
    fig.colorbar(im0, ax=axes[0, 0], fraction=0.035, pad=0.02)

    im1 = axes[0, 1].imshow(li_norm, origin="upper", extent=extent, cmap="viridis", vmin=0, vmax=1)
    axes[0, 1].set_title(f"Li$^+$ / $C_{{in}}$ at t = {t_name} s")
    fig.colorbar(im1, ax=axes[0, 1], fraction=0.035, pad=0.02)

    finite_sor = sor_display[np.isfinite(sor_display)]
    vmax_sor = float(np.nanpercentile(finite_sor, 99.5)) if finite_sor.size else 1.0
    im2 = axes[1, 0].imshow(
        sor_display,
        origin="upper",
        extent=extent,
        cmap="magma",
        vmin=0,
        vmax=max(vmax_sor, 1.0e-30),
    )
    axes[1, 0].set_title("Sorbed Li on reactive surface")
    fig.colorbar(im2, ax=axes[1, 0], fraction=0.035, pad=0.02)

    axes[1, 1].plot(x_mm, li_profile, color="#2166ac", lw=1.8, label="pore-mean Li+/Cin")
    if np.isfinite(sor_profile).any():
        sor_norm = sor_profile / max(float(np.nanmax(sor_profile)), 1.0e-30)
        axes[1, 1].plot(x_mm, sor_norm, color="#b2182b", lw=1.8, label="sorbed Li, normalised")
    axes[1, 1].axvline((t_value / 135.74475) * 12.0, color="0.35", ls="--", lw=1.0, label="simple front estimate")
    axes[1, 1].set_xlim(0, 18)
    axes[1, 1].set_ylim(-0.03, 1.05)
    axes[1, 1].set_xlabel("x [mm]")
    axes[1, 1].set_ylabel("normalised profile")
    axes[1, 1].set_title("Streamwise diagnostic profiles")
    axes[1, 1].grid(True, alpha=0.25)
    axes[1, 1].legend(fontsize=8, loc="best")

    for ax in axes.flat[:3]:
        ax.set_xlabel("x [mm]")
        ax.set_ylabel("y [mm]")
        ax.set_aspect("equal")

    fig.suptitle(f"Resolved two-scale lithium diagnostic, latest checkpoint t = {t_name} s")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=180)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
