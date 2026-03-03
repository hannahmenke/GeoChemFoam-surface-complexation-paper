#!/usr/bin/env python3
"""Generate Kelvin domain-mean temporal evolution figure (fig07).

Reads the parallel OpenFOAM field data at each saved timestep from the
3DKelvinSurfaceComplexation case and plots domain-mean Ca2+ / C_in and
incremental domain-mean Surf_aCa+ versus time.
"""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


# ── Field reader (mirrors generate_3d_volume_render_pyvista.py) ───────────────

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
        description="Plot domain-mean Ca2+ and Surf_aCa+ vs time for the Kelvin case"
    )
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument(
        "--ca-in", type=float, default=2.0e-9,
        help="Inlet Ca2+ concentration C_in (mol/m3)"
    )
    parser.add_argument(
        "--aqueous-field", default="Ca+2",
        help="Name of aqueous Ca field"
    )
    parser.add_argument(
        "--surface-field", default="Surf_aCa+",
        help="Name of surface Ca field"
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    times = available_times(args.case_dir)
    print(f"Found time steps: {times}")

    ca_means: list[float] = []
    surf_means: list[float] = []

    for t in times:
        t_str = str(int(t)) if t == int(t) else str(t)
        print(f"  Reading t = {t_str} ...")
        ca_means.append(read_domain_mean(args.case_dir, t_str, args.aqueous_field))
        surf_means.append(read_domain_mean(args.case_dir, t_str, args.surface_field))

    t_arr = np.array(times)
    ca_arr = np.array(ca_means)
    surf_arr = np.array(surf_means)

    # Normalise aqueous by C_in; surface as incremental from t=0
    ca_norm = ca_arr / args.ca_in
    surf_incr = surf_arr - surf_arr[0]
    surf_scale = max(surf_incr.max(), 1.0e-40)
    surf_norm = surf_incr / surf_scale

    # ── Plot ─────────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.9))

    ax1 = axes[0]
    ax1.plot(
        t_arr, ca_norm,
        color="#0b4f6c", linewidth=1.8,
        marker="o", markersize=4.5,
        label="Domain-mean Ca$^{2+}$ / $C_{\\mathrm{in}}$",
    )
    ax1.set_xlabel("Time [s]")
    ax1.set_ylabel("Domain-mean Ca$^{2+}$ / $C_{\\mathrm{in}}$")
    ax1.set_ylim(bottom=0.0)
    ax1.set_title("Dissolved calcium")
    ax1.grid(True, alpha=0.25)

    ax2 = axes[1]
    ax2.plot(
        t_arr, surf_norm,
        color="#6b2d5c", linewidth=1.8,
        marker="s", markersize=4.5,
        label="Domain-mean $\\Delta$Surf$_a$Ca$^+$ (norm.)",
    )
    ax2.set_xlabel("Time [s]")
    ax2.set_ylabel("Normalised domain-mean $\\Delta$Surf$_a$Ca$^+$")
    ax2.set_ylim(bottom=0.0)
    ax2.set_title("Surface loading")
    ax2.grid(True, alpha=0.25)

    fig.tight_layout()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=200)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
