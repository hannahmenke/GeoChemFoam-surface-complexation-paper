#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


CASES = [
    ("Pe 1", "pe1", Path("/scratch-nvme/n03/n03/gcfoam_n03/archive_ts_fix_full_pe1_128n/full_case")),
    ("Pe 0.3", "pe0p3", Path("/scratch-nvme/n03/n03/gcfoam_n03/archive_ts_fix_full_pe0p3_128n/full_case")),
    ("Pe 0.1", "pe0p1", Path("/scratch-nvme/n03/n03/gcfoam_n03/archive_ts_fix_full_pe0p1_128n/full_case")),
]
SPECIES = ("Li+", "Na+", "Cl-", "Sor_aLi")


def read_int(path: Path) -> int:
    return int(path.read_text().strip().split()[-1])


def read_config(path: Path) -> dict[str, str]:
    config: dict[str, str] = {}
    for line in path.read_text().splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            config[key] = value
    return config


def partition_sizes(n_total: int, n_parts: int) -> tuple[list[int], list[int]]:
    base, rem = divmod(n_total, n_parts)
    sizes: list[int] = []
    starts: list[int] = []
    start = 0
    for idx in range(n_parts):
        size = base + (1 if idx < rem else 0)
        sizes.append(size)
        starts.append(start)
        start += size
    return sizes, starts


def latest_time(case_dir: Path, field: str = "Li+") -> str:
    candidates: list[tuple[float, str]] = []
    for child in (case_dir / "processor0").iterdir():
        if not child.is_dir():
            continue
        try:
            value = float(child.name)
        except ValueError:
            continue
        if value > 0.0 and (child / field).exists():
            candidates.append((value, child.name))
    if not candidates:
        raise FileNotFoundError(f"No saved {field} timesteps under {case_dir / 'processor0'}")
    return max(candidates)[1]


def read_scalar(path: Path, expected_count: int) -> np.ndarray:
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
    if count != expected_count or values.size != expected_count:
        raise RuntimeError(f"{path}: expected {expected_count} values, got {values.size}/{count}")
    return values


def finite_or_none(value: float) -> float | None:
    return value if math.isfinite(value) else None


def diagnose_case(label: str, tag: str, root: Path, out_dir: Path, block: int) -> dict[str, object]:
    case_dir = root / "resolved-reference"
    time_name = latest_time(case_dir)
    config = read_config(root / "results" / "current_run_config.env")

    nx = read_int(case_dir / "system" / "Nx1")
    ny = read_int(case_dir / "system" / "Ny1")
    npx = read_int(case_dir / "system" / "NPX")
    npy = read_int(case_dir / "system" / "NPY")
    x_sizes, x_starts = partition_sizes(nx, npx)
    y_sizes, _ = partition_sizes(ny, npy)

    col_count = np.zeros(nx, dtype=np.int64)
    col_sum = {name: np.zeros(nx, dtype=np.float64) for name in SPECIES}
    col_max = {name: np.full(nx, -np.inf, dtype=np.float32) for name in SPECIES}

    img_nx = (nx + block - 1) // block
    img_ny = (ny + block - 1) // block
    li_img_sum = np.zeros((img_ny, img_nx), dtype=np.float64)
    cl_img_sum = np.zeros((img_ny, img_nx), dtype=np.float64)
    img_count = np.zeros((img_ny, img_nx), dtype=np.int64)

    for ipy in range(npy):
        local_ny = y_sizes[ipy]
        for ipx in range(npx):
            rank = ipy * npx + ipx
            local_nx = x_sizes[ipx]
            expected = local_nx * local_ny
            proc = case_dir / f"processor{rank}"
            theta = read_scalar(proc / "0" / "eps", expected).reshape((local_ny, local_nx))
            pore = theta > 0.5
            if not np.any(pore):
                continue

            x0 = x_starts[ipx]
            x_slice = slice(x0, x0 + local_nx)
            pore_counts = pore.sum(axis=0).astype(np.int64)
            col_count[x_slice] += pore_counts

            fields = {
                name: read_scalar(proc / time_name / name, expected).reshape((local_ny, local_nx))
                for name in SPECIES
            }
            for name, values in fields.items():
                masked = np.where(pore, values, np.nan)
                col_sum[name][x_slice] += np.nansum(masked, axis=0)
                with np.errstate(all="ignore"):
                    local_max = np.nanmax(masked, axis=0)
                col_max[name][x_slice] = np.maximum(col_max[name][x_slice], local_max)

            # Downsample pore-only mean for visual QA without allocating full fields.
            global_y0 = sum(y_sizes[:ipy])
            yy = (np.arange(local_ny) + global_y0) // block
            xx = (np.arange(local_nx) + x0) // block
            li_norm = np.where(pore, fields["Li+"] / 1e-3, np.nan)
            cl_excess = np.where(pore, (fields["Cl-"] - 0.13) / 1e-3, np.nan)
            for row_idx, gy in enumerate(yy):
                valid = pore[row_idx]
                if not np.any(valid):
                    continue
                xbins = xx[valid]
                np.add.at(li_img_sum[gy], xbins, li_norm[row_idx, valid])
                np.add.at(cl_img_sum[gy], xbins, cl_excess[row_idx, valid])
                np.add.at(img_count[gy], xbins, 1)

    with np.errstate(divide="ignore", invalid="ignore"):
        col_mean = {
            name: np.divide(col_sum[name], col_count, where=col_count > 0)
            for name in SPECIES
        }
        li_img = np.divide(li_img_sum, img_count, where=img_count > 0)
        cl_img = np.divide(cl_img_sum, img_count, where=img_count > 0)
    li_img[img_count == 0] = np.nan
    cl_img[img_count == 0] = np.nan

    x_mm = (np.arange(nx) + 0.5) * 18.0 / nx

    def front(values: np.ndarray, threshold: float) -> float | None:
        valid = np.isfinite(values) & (values >= threshold)
        if not np.any(valid):
            return None
        return float(x_mm[np.where(valid)[0].max()])

    li_mean_norm = col_mean["Li+"] / 1e-3
    li_max_norm = col_max["Li+"] / 1e-3
    cl_mean_excess = (col_mean["Cl-"] - 0.13) / 1e-3
    cl_max_excess = (col_max["Cl-"] - 0.13) / 1e-3

    summary: dict[str, object] = {
        "label": label,
        "tag": tag,
        "case_root": str(root),
        "case_dir": str(case_dir),
        "latest_time": time_name,
        "config": config,
        "pore_cell_count": int(col_count.sum()),
        "field_stats": {},
        "fronts_mm": {},
    }
    for name in SPECIES:
        finite_mean = col_mean[name][np.isfinite(col_mean[name])]
        finite_max = col_max[name][np.isfinite(col_max[name])]
        summary["field_stats"][name] = {
            "column_mean_min": finite_or_none(float(np.nanmin(finite_mean))),
            "column_mean_mean": finite_or_none(float(np.nanmean(finite_mean))),
            "column_mean_max": finite_or_none(float(np.nanmax(finite_mean))),
            "column_max_max": finite_or_none(float(np.nanmax(finite_max))),
        }

    for metric_name, values in [
        ("Li_mean_norm", li_mean_norm),
        ("Li_max_norm", li_max_norm),
        ("Cl_excess_mean_norm", cl_mean_excess),
        ("Cl_excess_max_norm", cl_max_excess),
    ]:
        summary["fronts_mm"][metric_name] = {
            f"ge_{threshold:g}": front(values, threshold)
            for threshold in (0.5, 0.1, 0.01)
        }

    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = out_dir / f"{tag}_final_pore_column_profiles.csv"
    table = np.column_stack(
        [
            x_mm,
            col_count,
            li_mean_norm,
            li_max_norm,
            cl_mean_excess,
            cl_max_excess,
            col_mean["Na+"],
            col_mean["Sor_aLi"],
        ]
    )
    np.savetxt(
        csv_path,
        table,
        delimiter=",",
        header="x_mm,pore_count,Li_mean_norm,Li_max_norm,Cl_excess_mean_norm,Cl_excess_max_norm,Na_mean,Sor_aLi_mean",
        comments="",
    )
    summary["profile_csv"] = str(csv_path)

    fig, axes = plt.subplots(3, 1, figsize=(11, 8), sharex=True, constrained_layout=True)
    axes[0].plot(x_mm, li_mean_norm, label="pore mean", lw=1.2)
    axes[0].plot(x_mm, li_max_norm, label="pore max", lw=0.9, alpha=0.7)
    axes[0].set_ylabel("Li / inlet")
    axes[0].set_ylim(-0.05, 1.1)
    axes[0].legend(fontsize=8)
    axes[1].plot(x_mm, cl_mean_excess, label="pore mean", lw=1.2)
    axes[1].plot(x_mm, cl_max_excess, label="pore max", lw=0.9, alpha=0.7)
    axes[1].set_ylabel("(Cl - 0.13) / 0.001")
    axes[1].set_ylim(-0.2, 1.3)
    axes[1].legend(fontsize=8)
    axes[2].plot(x_mm, col_mean["Sor_aLi"], lw=1.2)
    axes[2].set_ylabel("Sor_aLi")
    axes[2].set_xlabel("x [mm]")
    for ax in axes:
        ax.grid(True, alpha=0.25)
    fig.suptitle(f"{label} final pore-only profiles, t={time_name} s")
    profile_png = out_dir / f"{tag}_final_pore_profiles.png"
    fig.savefig(profile_png, dpi=180)
    plt.close(fig)
    summary["profile_png"] = str(profile_png)

    extent = (0.0, 18.0, 0.0, 6.0)
    fig, axes = plt.subplots(2, 1, figsize=(12, 6), constrained_layout=True)
    for ax, image, title, vmax in [
        (axes[0], li_img, "Pore mean Li / inlet", 1.0),
        (axes[1], cl_img, "Pore mean (Cl - 0.13) / 0.001", 1.0),
    ]:
        im = ax.imshow(
            image,
            origin="lower",
            extent=extent,
            aspect="equal",
            cmap="viridis",
            vmin=0.0,
            vmax=vmax,
            interpolation="nearest",
        )
        ax.set_title(title)
        ax.set_xlabel("x [mm]")
        ax.set_ylabel("y [mm]")
        fig.colorbar(im, ax=ax, fraction=0.025, pad=0.02)
    fig.suptitle(f"{label} final downsampled pore-only fields, block={block} voxels")
    field_png = out_dir / f"{tag}_final_pore_fields_downsampled.png"
    fig.savefig(field_png, dpi=180)
    plt.close(fig)
    summary["field_png"] = str(field_png)

    json_path = out_dir / f"{tag}_final_diagnostics.json"
    json_path.write_text(json.dumps(summary, indent=2) + "\n")
    return summary


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--block", type=int, default=12)
    args = parser.parse_args()

    summaries = [diagnose_case(label, tag, root, args.output_dir, args.block) for label, tag, root in CASES]
    combined = args.output_dir / "final_diagnostics_summary.json"
    combined.write_text(json.dumps(summaries, indent=2) + "\n")
    print(json.dumps(summaries, indent=2))


if __name__ == "__main__":
    main()
