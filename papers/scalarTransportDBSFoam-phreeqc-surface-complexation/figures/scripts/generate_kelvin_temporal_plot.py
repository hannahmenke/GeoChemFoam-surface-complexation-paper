#!/usr/bin/env python3
"""Generate Kelvin domain-mean temporal evolution figure (fig07).

Reads the parallel OpenFOAM field data at each saved timestep from the
3DKelvinSurfaceComplexation case and plots domain-mean Zn2+ and Ca2+ / C_in
(left panel) and incremental domain-mean Surf_aZn+ and Surf_aCa+ (right panel),
illustrating competitive sorption between the two species.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


# ── Field reader ──────────────────────────────────────────────────────────────

def parse_scalar_field(path: Path) -> list[float]:
    text = path.read_text()
    uniform_match = re.search(r"internalField\s+uniform\s+([^\n;]+)\s*;", text)
    if uniform_match:
        return [float(uniform_match.group(1))]
    nonuniform_match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text, re.S,
    )
    if not nonuniform_match:
        raise RuntimeError(f"Unsupported scalar field format in {path}")
    count = int(nonuniform_match.group(1))
    values = [float(item) for item in nonuniform_match.group(2).split()]
    if len(values) != count:
        raise RuntimeError(f"Value count mismatch in {path}")
    return values


def read_domain_mean(case_dir: Path, time_name: str, field_name: str) -> float:
    """Average a field over all processor sub-domains."""
    all_values: list[float] = []
    for proc_dir in sorted(case_dir.glob("processor*")):
        field_path = proc_dir / time_name / field_name
        if not field_path.exists():
            raise FileNotFoundError(f"Missing field: {field_path}")
        all_values.extend(parse_scalar_field(field_path))
    if not all_values:
        raise RuntimeError(f"No data found for {field_name} at t={time_name}")
    return float(np.mean(all_values))


def available_times(case_dir: Path) -> list[float]:
    """Return sorted list of numeric time directories present in processor0."""
    proc0 = case_dir / "processor0"
    if not proc0.exists():
        raise FileNotFoundError(f"processor0 not found in {case_dir}")
    times: list[float] = []
    for d in proc0.iterdir():
        if d.is_dir():
            try:
                times.append(float(d.name))
            except ValueError:
                pass
    return sorted(times)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot domain-mean Zn2+/Ca2+ competitive sorption vs time for Kelvin case"
    )
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument(
        "--ca-in", type=float, default=1.0e-4,
        help="Inlet Ca2+ concentration C_in [mol/m3]"
    )
    parser.add_argument(
        "--zn-in", type=float, default=1.0e-5,
        help="Inlet Zn2+ concentration C_in [mol/m3]"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    times = available_times(args.case_dir)
    print(f"Found time steps: {times}")

    ca_means: list[float] = []
    zn_means: list[float] = []
    surf_ca_means: list[float] = []
    surf_zn_means: list[float] = []

    for t in times:
        t_str = str(int(t)) if t == int(t) else str(t)
        print(f"  Reading t = {t_str} ...")
        ca_means.append(read_domain_mean(args.case_dir, t_str, "Ca+2"))
        zn_means.append(read_domain_mean(args.case_dir, t_str, "Zn+2"))
        surf_ca_means.append(read_domain_mean(args.case_dir, t_str, "Surf_aCa+"))
        surf_zn_means.append(read_domain_mean(args.case_dir, t_str, "Surf_aZn+"))

    t_arr = np.array(times)
    ca_norm = np.array(ca_means) / args.ca_in
    zn_norm = np.array(zn_means) / args.zn_in

    surf_ca = np.array(surf_ca_means)
    surf_zn = np.array(surf_zn_means)
    surf_ca_incr = surf_ca - surf_ca[0]
    surf_zn_incr = surf_zn - surf_zn[0]
    surf_scale = max(surf_zn_incr.max(), surf_ca_incr.max(), 1.0e-40)
    surf_ca_norm = surf_ca_incr / surf_scale
    surf_zn_norm = surf_zn_incr / surf_scale

    # ── Plot ─────────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.9))

    ax1 = axes[0]
    ax1.plot(
        t_arr, ca_norm,
        color="#0b4f6c", linewidth=1.8,
        marker="o", markersize=4.5,
        label="Ca$^{2+}$",
    )
    ax1.plot(
        t_arr, zn_norm,
        color="#c0392b", linewidth=1.8,
        marker="^", markersize=4.5,
        label="Zn$^{2+}$",
    )
    ax1.set_xlabel("Time [s]")
    ax1.set_ylabel("Domain-mean $C$ / $C_{\\mathrm{in}}$")
    ax1.set_ylim(bottom=0.0)
    ax1.set_title("Dissolved species")
    ax1.legend(fontsize=9)
    ax1.grid(True, alpha=0.25)

    ax2 = axes[1]
    ax2.plot(
        t_arr, surf_ca_norm,
        color="#0b4f6c", linewidth=1.8,
        marker="o", markersize=4.5,
        label="Surf$_a$Ca$^+$",
    )
    ax2.plot(
        t_arr, surf_zn_norm,
        color="#c0392b", linewidth=1.8,
        marker="^", markersize=4.5,
        label="Surf$_a$Zn$^+$",
    )
    ax2.set_xlabel("Time [s]")
    ax2.set_ylabel("Normalised domain-mean $\\Delta$Surf loading")
    ax2.set_ylim(bottom=0.0)
    ax2.set_title("Surface loading")
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.25)

    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=200)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
