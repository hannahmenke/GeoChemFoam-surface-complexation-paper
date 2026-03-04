#!/usr/bin/env python3
"""Generate 1D breakthrough curve figure (fig06).

Reads postProcessing outlet-probe data written by OpenFOAM surfaceFieldValue
from both the surface-enabled and aqueous-only transport runs, overlays
finite-domain analytical breakthrough curves, and writes the figure PNG.

The Ogata-Banks formula assumes a semi-infinite domain.  The simulation uses
a finite domain [0, L] with a Dirichlet (fixedValue) inlet and Neumann
(zeroGradient) outlet.  The correct reference is therefore the finite-domain
solution, which is computed here via a fine-grid 1-D implicit-Euler solver
with the same boundary conditions.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from scipy.linalg import solve_banded


# ── Physical constants (must match phase8AnalyticalTools.py) ─────────────────
BASE_THETA = 0.5
BASE_ASURF = 1.0e5
BASE_U     = 1.0e-6
BASE_D     = 1.0e-11
DOMAIN_LENGTH = 4.0e-5


# ── Finite-domain reference solution ─────────────────────────────────────────

def finite_domain_outlet(
    t_query: np.ndarray,
    v: float,
    D: float,
    L: float = DOMAIN_LENGTH,
    nx: int = 800,
    dt: float = 0.05,
) -> np.ndarray:
    """
    Solve 1-D advection-diffusion on [0, L] with implicit Euler and return
    C(x=L, t) / C_in for each t in t_query.

    Matches the OpenFOAM setup exactly:
      - time scheme : first-order implicit Euler (ddt Euler)
      - advection   : first-order upwind  (bounded Gauss upwind)
      - diffusion   : second-order central (Gauss linear)
      - inlet BC    : Dirichlet  C = C_in  (fixedValue, normalised to 1)
      - outlet BC   : Neumann    dC/dx = 0 (zeroGradient)
      - IC          : C = 0

    nx is chosen large enough that numerical diffusion v*dx/2 << D.
    """
    dx = L / nx
    # Check numerical diffusion is negligible
    # nu_diff = v * dx / 2  <<  D  =>  dx << 2D/v
    # With nx=800: dx = 5e-8, v*dx/2 = 5e-14 << D=1e-11  ✓

    rd = D * dt / dx**2   # diffusion number  (central, implicit)
    ru = v * dt / dx      # advection number  (upwind,  implicit)

    # ── Build tridiagonal A for system  A * C^{n+1} = C^n + bc_contrib ────
    # Interior cell i (1 … nx-2):
    #   lower[i] = -(rd + ru)   [coeff of C_{i-1}^{n+1}]
    #   main [i] =  1 + 2*rd + ru
    #   upper[i] = -rd           [coeff of C_{i+1}^{n+1}]
    #
    # Cell 0  (Dirichlet, left ghost = 1):
    #   lower[0] removed (→ add (rd+ru)*1 to rhs[0])
    #   main [0] = 1 + 2*rd + ru   (unchanged)
    #   upper[0] = -rd
    #
    # Cell nx-1  (Neumann, right ghost = C_{nx-1}, diffusion only):
    #   upper[nx-1] term folds into diagonal (upwind advection uses no right ghost)
    #   main [nx-1] = 1 + 2*rd + ru - rd = 1 + rd + ru
    #   lower[nx-1] = -(rd + ru)

    lower = np.full(nx, -(rd + ru))
    main  = np.full(nx,  1.0 + 2.0 * rd + ru)
    upper = np.full(nx, -rd)

    # Neumann outlet: fold ghost diffusion into diagonal
    main[-1] = 1.0 + rd + ru

    # scipy solve_banded banded format: rows = [upper-diag, main, lower-diag]
    ab = np.zeros((3, nx))
    ab[0, 1:]  = upper[:-1]   # upper diagonal (shifted right)
    ab[1, :]   = main
    ab[2, :-1] = lower[1:]    # lower diagonal (shifted left)

    # Dirichlet inlet contribution to rhs[0] at every step
    dirichlet_rhs = (rd + ru) * 1.0  # C_in normalised = 1

    C = np.zeros(nx)
    t_curr = 0.0

    t_sorted = np.sort(np.asarray(t_query, dtype=float))
    results: dict[float, float] = {}
    idx = 0

    while idx < len(t_sorted):
        t_tgt = t_sorted[idx]
        if t_curr >= t_tgt - 1e-12:
            results[t_tgt] = float(C[-1])
            idx += 1
            continue

        # rhs = C^n  (just copy)
        rhs = C.copy()
        # Add Dirichlet contribution for cell 0
        rhs[0] += dirichlet_rhs

        C = solve_banded((1, 1), ab, rhs)
        t_curr += dt

    return np.array([results[t] for t in t_sorted])


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
    parser.add_argument("--surface-dir", type=Path, required=True)
    parser.add_argument("--aqueous-dir", type=Path, required=True)
    parser.add_argument("--k-s", type=float, required=True,
                        help="Calibrated K_s_field value")
    parser.add_argument("--ca-in", type=float, default=2.0e-9,
                        help="Inlet Ca2+ concentration C_in (mol/m3)")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    # Effective velocities and diffusivities
    r_field = 1.0 + BASE_ASURF * args.k_s / (BASE_THETA ** 2)
    v_aq    = BASE_U / BASE_THETA
    D_aq    = BASE_D
    v_surf  = BASE_U / (BASE_THETA * r_field)
    D_surf  = BASE_D / r_field

    # Analytical breakthrough times (for vertical markers)
    t_bt_aq   = DOMAIN_LENGTH / v_aq
    t_bt_surf = DOMAIN_LENGTH / v_surf

    # Read numerical breakthrough data
    dat_surf = find_postprocessing_dat(args.surface_dir)
    dat_aq   = find_postprocessing_dat(args.aqueous_dir)
    t_surf, c_surf = read_breakthrough_dat(dat_surf)
    t_aq,   c_aq   = read_breakthrough_dat(dat_aq)

    t_max = max(t_surf[-1] if len(t_surf) else 0.0,
                t_aq[-1]   if len(t_aq)   else 0.0,
                80.0)

    # Dense time grid for reference curves
    t_ref = np.linspace(0.0, t_max, 500)

    print("Computing finite-domain reference for aqueous-only case …")
    c_ref_aq   = finite_domain_outlet(t_ref, v_aq,   D_aq)
    print("Computing finite-domain reference for surface-enabled case …")
    c_ref_surf = finite_domain_outlet(t_ref, v_surf, D_surf)

    C_in = args.ca_in

    # ── Plot ─────────────────────────────────────────────────────────────────
    fig, ax = plt.subplots(figsize=(6.5, 4.2))

    # Aqueous-only
    ax.plot(
        t_aq, c_aq / C_in,
        label="Numerical (aq. only)",
        color="#c55a11", linewidth=1.5,
        marker="o", markersize=2.2,
        markevery=max(1, len(t_aq) // 25),
    )
    ax.plot(
        t_ref, c_ref_aq,
        "--", label="Analytical (aq. only)",
        color="#f2a65a", linewidth=1.6,
    )

    # Surface-enabled
    ax.plot(
        t_surf, c_surf / C_in,
        label="Numerical (surface)",
        color="#0b4f6c", linewidth=1.8,
        marker="o", markersize=2.4,
        markevery=max(1, len(t_surf) // 25),
    )
    ax.plot(
        t_ref, c_ref_surf,
        "--", label="Analytical (surface)",
        color="#4f9da6", linewidth=1.6,
    )

    # Mark analytical breakthrough times
    ax.axvline(t_bt_aq,   color="#c55a11", linewidth=0.7, linestyle=":", alpha=0.6)
    ax.axvline(t_bt_surf, color="#0b4f6c", linewidth=0.7, linestyle=":", alpha=0.6)

    ax.set_xlabel("Time [s]")
    ax.set_ylabel("Outlet Ca$^{2+}$ / $C_{\\mathrm{in}}$")
    ax.set_xlim(0.0, t_max)
    ax.set_ylim(-0.02, 1.10)
    ax.legend(fontsize=9)
    ax.grid(True, alpha=0.25)

    annotation_lines = [
        f"$R_{{\\mathrm{{field}}}}$ = {r_field:.3f}",
        f"$t_{{\\mathrm{{BT,aq}}}}$ = {t_bt_aq:.1f} s",
        f"$t_{{\\mathrm{{BT,surf}}}}$ = {t_bt_surf:.1f} s",
    ]
    ax.text(
        0.97, 0.05, "\n".join(annotation_lines),
        transform=ax.transAxes, fontsize=8.5, ha="right", va="bottom",
        bbox={"facecolor": "white", "edgecolor": "#bdbdbd",
              "boxstyle": "round,pad=0.25"},
    )

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(args.output, dpi=200)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
