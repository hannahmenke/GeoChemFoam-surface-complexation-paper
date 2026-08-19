#!/usr/bin/env python3
"""Generate Estaillades domain-mean temporal evolution figure.

Reads the parallel OpenFOAM field data at each saved timestep from the
3DEstailladesSurfaceComplexation case and plots domain-mean dissolved Sr2+/Ca2+
and incremental surface loadings Surf_aSr+/Surf_aCa+, illustrating the
chromatographic exchange between the invading Sr plume and Ca-preloaded sites.
"""

from __future__ import annotations

import argparse
import re
from concurrent.futures import ProcessPoolExecutor
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def parse_scalar_field_mean(path: Path) -> float:
    text = path.read_text()
    uniform_match = re.search(r"internalField\s+uniform\s+([^\n;]+)\s*;", text)
    if uniform_match:
        return float(uniform_match.group(1))

    nonuniform_match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not nonuniform_match:
        raise RuntimeError(f"Unsupported scalar field format in {path}")

    count = int(nonuniform_match.group(1))
    values = np.fromstring(nonuniform_match.group(2), sep=" ", dtype=float)
    if values.size != count:
        raise RuntimeError(f"Value count mismatch in {path}")
    return float(np.mean(values))


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


def read_domain_mean(
    case_dir: Path, time_name: str, field_name: str, max_workers: int
) -> float:
    paths = []
    for proc_dir in sorted(case_dir.glob("processor*")):
        field_path = proc_dir / time_name / field_name
        if not field_path.exists():
            raise FileNotFoundError(f"Missing field: {field_path}")
        paths.append(field_path)

    with ProcessPoolExecutor(max_workers=max_workers) as executor:
        means = list(executor.map(parse_scalar_field_mean, paths, chunksize=1))
    return float(np.mean(means))


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot domain-mean Sr2+/Ca2+ chromatographic exchange vs time for Estaillades case"
    )
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument(
        "--sr-in",
        type=float,
        default=1.0e-4,
        help="Inlet Sr2+ concentration C_in [mol/m3]",
    )
    parser.add_argument(
        "--ca-init",
        type=float,
        default=1.0e-3,
        help="Initial Ca2+ concentration C_init [mol/m3]",
    )
    parser.add_argument(
        "--max-workers",
        type=int,
        default=8,
        help="Parallel workers used to read processor field files",
    )
    parser.add_argument("--output", type=Path, required=True)
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
        ca_means.append(read_domain_mean(args.case_dir, time_name, "Ca+2", args.max_workers))
        sr_means.append(read_domain_mean(args.case_dir, time_name, "Sr+2", args.max_workers))
        surf_ca_means.append(
            read_domain_mean(args.case_dir, time_name, "Surf_aCa+", args.max_workers)
        )
        surf_sr_means.append(
            read_domain_mean(args.case_dir, time_name, "Surf_aSr+", args.max_workers)
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
    ax1.set_ylabel("Domain-mean dissolved concentration")
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
    ax2.set_ylabel("Normalised domain-mean $\\Delta$Surf loading")
    ax2.set_title("Surface exchange")
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.25)

    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=200)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
