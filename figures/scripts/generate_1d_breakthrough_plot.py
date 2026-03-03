#!/usr/bin/env python3
"""Generate 1D breakthrough curve figure (fig06).

Reads postProcessing outlet-probe data written by OpenFOAM surfaceFieldValue
from both the surface-enabled and aqueous-only transport runs, overlays the
analytical Ogata-Banks breakthrough curves, and writes the figure PNG.
"""

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


# ── Physical constants (must match phase8AnalyticalTools.py) ─────────────────
BASE_THETA = 0.5
BASE_ASURF = 1.0e5
BASE_U = 1.0e-6
BASE_D = 1.0e-11
DOMAIN_LENGTH = 4.0e-5


# ── Analytical solution ───────────────────────────────────────────────────────

def ogata_banks_bt(t: float, v: float, D: float) -> float:
    """Ogata-Banks solution C(L,t)/C_in at x = DOMAIN_LENGTH."""
    if t <= 0.0:
        return 0.0
    L = DOMAIN_LENGTH
    sqrt_Dt = math.sqrt(D * t)
    arg1 = (L - v * t) / (2.0 * sqrt_Dt)
    arg2 = (L + v * t) / (2.0 * sqrt_Dt)
    term1 = 0.5 * math.erfc(arg1)
    # Use log-space arithmetic to avoid exp(v*L/D) overflow for high Pe
    log_factor = v * L / D - arg2 * arg2
    if log_factor < -500.0:
        term2 = 0.0
    else:
        # erfcx(x) = exp(x^2) * erfc(x)  →  erfc(x) = erfcx(x) * exp(-x^2)
        # exp(v*L/D) * erfc(arg2) = erfcx(arg2) * exp(v*L/D - arg2^2)
        from math import exp
        try:
            erfcx_arg2 = math.erfc(arg2) * math.exp(arg2 * arg2)
        except OverflowError:
            erfcx_arg2 = 1.0 / (arg2 * math.sqrt(math.pi))  # asymptotic
        term2 = 0.5 * erfcx_arg2 * math.exp(log_factor)
    return term1 + term2


def analytical_breakthrough(
    t_arr: np.ndarray, v: float, D: float
) -> np.ndarray:
    return np.array([ogata_banks_bt(t, v, D) for t in t_arr])


# ── Data readers ──────────────────────────────────────────────────────────────

def find_postprocessing_dat(results_dir: Path) -> Path:
    """Locate the surfaceFieldValue .dat file inside the postProcessing tree."""
    pp_root = results_dir / "postProcessing"
    if not pp_root.exists():
        raise FileNotFoundError(f"No postProcessing directory in {results_dir}")
    candidates = sorted(pp_root.rglob("*.dat"))
    if not candidates:
        raise FileNotFoundError(f"No .dat file found under {pp_root}")
    return candidates[0]


def read_breakthrough_dat(dat_path: Path) -> tuple[np.ndarray, np.ndarray]:
    """Parse OpenFOAM surfaceFieldValue .dat output → (time, concentration)."""
    times: list[float] = []
    values: list[float] = []
    for raw_line in dat_path.read_text().splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2:
            try:
                times.append(float(parts[0]))
                values.append(float(parts[1]))
            except ValueError:
                continue
    return np.array(times), np.array(values)


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate 1D breakthrough curve figure"
    )
    parser.add_argument(
        "--surface-dir",
        type=Path,
        required=True,
        help="results/transport_surface directory",
    )
    parser.add_argument(
        "--aqueous-dir",
        type=Path,
        required=True,
        help="results/transport_aqueous directory",
    )
    parser.add_argument(
        "--k-s",
        type=float,
        required=True,
        help="Calibrated K_s_field value",
    )
    parser.add_argument(
        "--ca-in",
        type=float,
        default=2.0e-9,
        help="Inlet Ca2+ concentration C_in (mol/m3)",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    # Effective velocities and diffusivities
    r_field = 1.0 + BASE_ASURF * args.k_s / (BASE_THETA ** 2)
    v_aq = BASE_U / BASE_THETA
    D_aq = BASE_D
    v_surf = BASE_U / (BASE_THETA * r_field)
    D_surf = BASE_D / r_field

    # Read numerical breakthrough data
    dat_surf = find_postprocessing_dat(args.surface_dir)
    dat_aq = find_postprocessing_dat(args.aqueous_dir)
    t_surf, c_surf = read_breakthrough_dat(dat_surf)
    t_aq, c_aq = read_breakthrough_dat(dat_aq)

    # Analytical breakthrough curves on a dense time grid
    t_max = max(t_surf[-1] if len(t_surf) else 0.0,
                t_aq[-1] if len(t_aq) else 0.0,
                80.0)
    t_anal = np.linspace(0.0, t_max, 800)
    c_anal_aq = analytical_breakthrough(t_anal, v_aq, D_aq)
    c_anal_surf = analytical_breakthrough(t_anal, v_surf, D_surf)

    C_in = args.ca_in

    # ── Plot ─────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(6.5, 4.2))

    # Aqueous-only
    ax.plot(
        t_aq,
        c_aq / C_in,
        label="Numerical (aq. only)",
        color="#c55a11",
        linewidth=1.5,
        marker="o",
        markersize=2.2,
        markevery=max(1, len(t_aq) // 25),
    )
    ax.plot(
        t_anal,
        c_anal_aq,
        "--",
        label="Analytical (aq. only)",
        color="#f2a65a",
        linewidth=1.6,
    )

    # Surface-enabled
    ax.plot(
        t_surf,
        c_surf / C_in,
        label="Numerical (surface)",
        color="#0b4f6c",
        linewidth=1.8,
        marker="o",
        markersize=2.4,
        markevery=max(1, len(t_surf) // 25),
    )
    ax.plot(
        t_anal,
        c_anal_surf,
        "--",
        label="Analytical (surface)",
        color="#4f9da6",
        linewidth=1.6,
    )

    # Mark analytical breakthrough times
    t_bt_aq = DOMAIN_LENGTH / v_aq
    t_bt_surf = DOMAIN_LENGTH / v_surf
    ax.axvline(t_bt_aq, color="#c55a11", linewidth=0.7, linestyle=":", alpha=0.6)
    ax.axvline(t_bt_surf, color="#0b4f6c", linewidth=0.7, linestyle=":", alpha=0.6)

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Outlet Ca$^{2+}$ / $C_{\\mathrm{in}}$")
    ax.set_xlim(0.0, t_max)
    ax.set_ylim(-0.02, 1.10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    # Annotation box
    annotation_lines = [
        f"$R_{{\\mathrm{{field}}}}$ = {r_field:.3f}",
        f"$t_{{\\mathrm{{BT,aq}}}}$ = {t_bt_aq:.1f} s",
        f"$t_{{\\mathrm{{BT,surf}}}}$ = {t_bt_surf:.1f} s",
    ]
    ax.text(
        0.97,
        0.05,
        "\n".join(annotation_lines),
        transform=ax.transAxes,
        fontsize=8.5,
        ha="right",
        va="bottom",
        bbox={"facecolor": "white", "edgecolor": "#bdbdbd", "boxstyle": "round,pad=0.25"},
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(args.output, dpi=200)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
