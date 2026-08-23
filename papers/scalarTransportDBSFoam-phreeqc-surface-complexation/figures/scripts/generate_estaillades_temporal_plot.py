#!/usr/bin/env python3
"""Generate the weighted Estaillades temporal-evolution figure.

Reads parallel ASCII or binary OpenFOAM fields from the full-resolution
Estaillades case. Dissolved concentrations are averaged by pore volume and
surface loadings by reactive area, so the plotted histories represent aqueous
and sorbed inventories rather than unweighted voxel counts.
"""

from __future__ import annotations

import argparse
import json
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np

from openfoam_field_io import read_internal_scalar


def parse_weighted_moments(paths: tuple[Path, Path]) -> tuple[float, float]:
    field_path, weight_path = paths
    values = read_internal_scalar(field_path)
    weights = read_internal_scalar(weight_path)

    if isinstance(values, float) and isinstance(weights, float):
        if not np.isfinite(values) or not np.isfinite(weights) or weights < 0.0:
            raise RuntimeError(f"Invalid scalar data in {field_path} or {weight_path}")
        return values * weights, weights
    if isinstance(values, float):
        assert isinstance(weights, np.ndarray)
        if not np.isfinite(values) or not np.all(np.isfinite(weights)) or np.any(weights < 0.0):
            raise RuntimeError(f"Invalid scalar data in {field_path} or {weight_path}")
        return values * float(np.sum(weights)), float(np.sum(weights))
    if isinstance(weights, float):
        if not np.all(np.isfinite(values)) or not np.isfinite(weights) or weights < 0.0:
            raise RuntimeError(f"Invalid scalar data in {field_path} or {weight_path}")
        return float(np.sum(values)) * weights, values.size * weights
    if values.size != weights.size:
        raise RuntimeError(
            f"Field/weight size mismatch: {field_path} and {weight_path}"
        )
    if not np.all(np.isfinite(values)):
        raise RuntimeError(f"Non-finite values in {field_path}")
    if not np.all(np.isfinite(weights)) or np.any(weights < 0.0):
        raise RuntimeError(f"Invalid weights in {weight_path}")
    return float(np.dot(values, weights)), float(np.sum(weights))


def available_times(case_dir: Path) -> list[float]:
    proc0 = case_dir / "processor0"
    if not proc0.exists():
        raise FileNotFoundError(f"processor0 not found in {case_dir}")

    times: list[float] = []
    for directory in proc0.iterdir():
        if directory.is_dir():
            try:
                times.append(float(directory.name))
            except ValueError:
                pass
    return sorted(times)


def read_weighted_domain_mean(
    case_dir: Path,
    time_name: str,
    field_name: str,
    weight_name: str,
    max_workers: int,
) -> float:
    paths: list[tuple[Path, Path]] = []
    for proc_dir in sorted(case_dir.glob("processor*")):
        field_path = proc_dir / time_name / field_name
        weight_path = proc_dir / time_name / weight_name
        if not field_path.exists():
            raise FileNotFoundError(f"Missing field: {field_path}")
        if not weight_path.exists():
            raise FileNotFoundError(f"Missing weight field: {weight_path}")
        paths.append((field_path, weight_path))

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        moments = list(executor.map(parse_weighted_moments, paths, chunksize=1))
    numerator = sum(item[0] for item in moments)
    denominator = sum(item[1] for item in moments)
    if denominator <= 0.0:
        raise RuntimeError(f"Non-positive total {weight_name} at t={time_name}")
    return numerator / denominator


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot weighted Sr2+/Ca2+ chromatographic exchange vs time for the Estaillades case"
    )
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument(
        "--sr-in",
        type=float,
        default=1.0e-4,
        help="Inlet Sr2+ concentration C_in [mol/L]",
    )
    parser.add_argument(
        "--ca-init",
        type=float,
        default=1.0e-3,
        help="Initial Ca2+ concentration C_init [mol/L]",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Parallel workers used to read processor field files",
    )
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--metrics-output",
        type=Path,
        default=None,
        help="JSON output path (default: figure path with .json suffix)",
    )
    args = parser.parse_args()

    times = available_times(args.case_dir)
    print(f"Found time steps: {times}")

    ca_means: list[float] = []
    sr_means: list[float] = []
    surf_ca_means: list[float] = []
    surf_sr_means: list[float] = []

    for time_value in times:
        time_name = str(int(time_value)) if time_value == int(time_value) else str(time_value)
        print(f"  Reading t = {time_name} ...")
        ca_means.append(
            read_weighted_domain_mean(
                args.case_dir, time_name, "Ca+2", "eps", args.max_workers
            )
        )
        sr_means.append(
            read_weighted_domain_mean(
                args.case_dir, time_name, "Sr+2", "eps", args.max_workers
            )
        )
        surf_ca_means.append(
            read_weighted_domain_mean(
                args.case_dir, time_name, "Surf_aCa+", "aSurf", args.max_workers
            )
        )
        surf_sr_means.append(
            read_weighted_domain_mean(
                args.case_dir, time_name, "Surf_aSr+", "aSurf", args.max_workers
            )
        )

    time_array = np.array(times)
    ca_norm = np.array(ca_means) / args.ca_init
    sr_norm = np.array(sr_means) / args.sr_in

    surf_ca = np.array(surf_ca_means)
    surf_sr = np.array(surf_sr_means)
    surf_ca_delta = surf_ca - surf_ca[0]
    surf_sr_delta = surf_sr - surf_sr[0]
    surf_scale = max(np.max(np.abs(surf_ca_delta)), np.max(np.abs(surf_sr_delta)), 1.0e-40)
    surf_ca_norm = surf_ca_delta / surf_scale
    surf_sr_norm = surf_sr_delta / surf_scale

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.9))

    ax1 = axes[0]
    ax1.plot(
        time_array,
        ca_norm,
        color="#0b4f6c",
        linewidth=1.8,
        marker="o",
        markersize=4.5,
        label="Ca$^{2+}$ / $C_{\\mathrm{init}}$",
    )
    ax1.plot(
        time_array,
        sr_norm,
        color="#c0392b",
        linewidth=1.8,
        marker="^",
        markersize=4.5,
        label="Sr$^{2+}$ / $C_{\\mathrm{in}}$",
    )
    ax1.set_xlabel("Time [s]")
    ax1.set_ylabel("Porosity-weighted dissolved concentration")
    ax1.set_ylim(bottom=0.0)
    ax1.set_title("Dissolved species")
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.25)

    ax2 = axes[1]
    ax2.plot(
        time_array,
        surf_ca_norm,
        color="#0b4f6c",
        linewidth=1.8,
        marker="o",
        markersize=4.5,
        label="$\\Delta$Surf$_a$Ca$^+$",
    )
    ax2.plot(
        time_array,
        surf_sr_norm,
        color="#c0392b",
        linewidth=1.8,
        marker="^",
        markersize=4.5,
        label="$\\Delta$Surf$_a$Sr$^+$",
    )
    ax2.axhline(0.0, color="#666666", linewidth=0.8, alpha=0.6)
    ax2.set_xlabel("Time [s]")
    ax2.set_ylabel("Normalised area-weighted $\\Delta$Surf loading")
    ax2.set_title("Surface exchange")
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.25)

    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=200)
    plt.close(fig)

    metrics_path = args.metrics_output or args.output.with_suffix(".json")
    repo_root = Path(__file__).resolve().parents[4]
    case_path = args.case_dir.resolve()
    try:
        case_reference = str(case_path.relative_to(repo_root))
    except ValueError:
        case_reference = str(case_path)
    metrics = {
        "case": case_reference,
        "weighting": {
            "dissolved": "porosity-weighted domain mean",
            "surface": "reactive-area-weighted domain mean",
        },
        "normalisation": {
            "sr_in_mol_per_litre": args.sr_in,
            "ca_init_mol_per_litre": args.ca_init,
            "surface_delta_scale_kmol_per_square_metre": surf_scale,
        },
        "samples": [
            {
                "time_s": float(time_value),
                "ca_mean_mol_per_litre": float(ca_means[index]),
                "sr_mean_mol_per_litre": float(sr_means[index]),
                "ca_over_c_init": float(ca_norm[index]),
                "sr_over_c_in": float(sr_norm[index]),
                "surface_ca_mean_kmol_per_square_metre": float(surf_ca[index]),
                "surface_sr_mean_kmol_per_square_metre": float(surf_sr[index]),
                "surface_ca_delta_normalised": float(surf_ca_norm[index]),
                "surface_sr_delta_normalised": float(surf_sr_norm[index]),
            }
            for index, time_value in enumerate(times)
        ],
    }
    metrics_path.parent.mkdir(parents=True, exist_ok=True)
    metrics_path.write_text(json.dumps(metrics, indent=2) + "\n")
    print(f"Wrote {args.output}")
    print(f"Wrote {metrics_path}")


if __name__ == "__main__":
    main()
