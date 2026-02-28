#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
import re
from pathlib import Path

import matplotlib.pyplot as plt


def parse_scalar_field(path: Path) -> list[float]:
    text = path.read_text()

    uniform_match = re.search(r"internalField\s+uniform\s+([^\n;]+)\s*;", text)
    if uniform_match:
        return [float(uniform_match.group(1))]

    nonuniform_match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not nonuniform_match:
        raise RuntimeError(f"Unsupported scalar field format in {path}")

    count = int(nonuniform_match.group(1))
    values = [float(item) for item in nonuniform_match.group(2).split()]
    if len(values) != count:
        raise RuntimeError(f"Value count mismatch in {path}")
    return values


def ogata_banks(c_in: float, velocity: float, diffusion: float, time_value: float, x: float) -> float:
    if time_value <= 0.0:
        return c_in if x <= 0.0 else 0.0

    if diffusion <= 0.0:
        return c_in if x <= velocity * time_value else 0.0

    denom = 2.0 * math.sqrt(diffusion * time_value)
    term1 = 0.5 * math.erfc((x - velocity * time_value) / denom)
    term2 = 0.5 * math.exp(velocity * x / diffusion) * math.erfc((x + velocity * time_value) / denom)
    return c_in * (term1 + term2)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--surface-ca", type=Path, required=True)
    parser.add_argument("--aqueous-ca", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--c-in", type=float, default=2e-9)
    parser.add_argument("--theta", type=float, default=0.5)
    parser.add_argument("--asurf", type=float, default=1e5)
    parser.add_argument("--k-s-field", type=float, default=4.2412187733863601e-06)
    parser.add_argument("--diffusion", type=float, default=1e-11)
    parser.add_argument("--length", type=float, default=4e-5)
    parser.add_argument("--time", type=float, default=10.0)
    parser.add_argument("--u", type=float, default=1e-6)
    args = parser.parse_args()

    surface_values = parse_scalar_field(args.surface_ca)
    aqueous_values = parse_scalar_field(args.aqueous_ca) if args.aqueous_ca else None
    n = len(surface_values)
    dx = args.length / max(n, 1)
    x = [(i + 0.5) * dx for i in range(n)]

    r_field = 1.0 + args.asurf * args.k_s_field / (args.theta * args.theta)
    v_surface = args.u / (args.theta * r_field)
    d_surface = args.diffusion / r_field
    analytical_surface = [
        ogata_banks(args.c_in, v_surface, d_surface, args.time, xi) for xi in x
    ]
    analytical_aqueous = None
    if aqueous_values is not None:
        v_aqueous = args.u / args.theta
        analytical_aqueous = [
            ogata_banks(args.c_in, v_aqueous, args.diffusion, args.time, xi) for xi in x
        ]

    fig, ax = plt.subplots(figsize=(6.5, 3.5))
    if aqueous_values is not None:
        ax.plot(x, aqueous_values, label="Numerical aqueous-only", linewidth=1.6, color="#c55a11")
        ax.plot(
            x,
            analytical_aqueous,
            "--",
            label="Analytical aqueous-only",
            linewidth=1.2,
            color="#f2a65a",
        )
    ax.plot(x, surface_values, label="Numerical surface-enabled", linewidth=2.0, color="#0b4f6c")
    ax.plot(
        x,
        analytical_surface,
        "--",
        label="Analytical surface-enabled",
        linewidth=1.4,
        color="#4f9da6",
    )
    ax.set_xlabel("x [m]")
    ax.set_ylabel("Ca$^{2+}$ concentration")
    ax.set_title("1D Retardation Benchmark (Advection-Diffusion)")
    ax.legend()
    ax.grid(True, alpha=0.25)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout()
    fig.savefig(args.output, dpi=200)


if __name__ == "__main__":
    main()
