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


def cell_average_ogata_banks(
    c_in: float,
    velocity: float,
    diffusion: float,
    time_value: float,
    x_left: float,
    x_right: float,
    samples: int = 32,
) -> float:
    if x_right <= x_left:
        return ogata_banks(c_in, velocity, diffusion, time_value, x_left)

    total = 0.0
    for index in range(samples):
        xi = x_left + (index + 0.5) * (x_right - x_left) / samples
        total += ogata_banks(c_in, velocity, diffusion, time_value, xi)
    return total / samples


def profile_errors(numeric: list[float], analytical: list[float], scale: float) -> tuple[float, float]:
    diffs = [abs(a - b) for a, b in zip(numeric, analytical)]
    if not diffs:
        return 0.0, 0.0
    return (sum(diffs) / len(diffs)) / scale, max(diffs) / scale


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--surface-ca", type=Path, required=True)
    parser.add_argument("--surface-loading", type=Path, required=True)
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
    surface_loading_values = parse_scalar_field(args.surface_loading)
    aqueous_values = parse_scalar_field(args.aqueous_ca) if args.aqueous_ca else None
    n = len(surface_values)
    dx = args.length / max(n, 1)
    x = [(i + 0.5) * dx for i in range(n)]
    x_left = [i * dx for i in range(n)]
    x_right = [(i + 1.0) * dx for i in range(n)]
    x_um = [1.0e6 * value for value in x]

    r_field = 1.0 + args.asurf * args.k_s_field / (args.theta * args.theta)
    v_surface = args.u / (args.theta * r_field)
    d_surface = args.diffusion / r_field
    analytical_surface = [
        cell_average_ogata_banks(
            args.c_in, v_surface, d_surface, args.time, xl, xr
        )
        for xl, xr in zip(x_left, x_right)
    ]
    analytical_surface_loading = [args.k_s_field * value for value in analytical_surface]
    numerical_surface_loading = surface_loading_values
    analytical_aqueous = None
    if aqueous_values is not None:
        v_aqueous = args.u / args.theta
        analytical_aqueous = [
            cell_average_ogata_banks(
                args.c_in, v_aqueous, args.diffusion, args.time, xl, xr
            )
            for xl, xr in zip(x_left, x_right)
        ]

    l1_surface, linf_surface = profile_errors(surface_values, analytical_surface, max(abs(args.c_in), 1.0e-30))
    l1_aqueous = None
    if aqueous_values is not None and analytical_aqueous is not None:
        l1_aqueous, _ = profile_errors(aqueous_values, analytical_aqueous, max(abs(args.c_in), 1.0e-30))

    surface_scale = max(abs(args.c_in), 1.0e-30)
    loading_scale = max(max(numerical_surface_loading), max(analytical_surface_loading), 1.0e-30)

    fig, axes = plt.subplots(1, 2, figsize=(9.2, 3.9), sharex=True)
    ax = axes[0]
    if aqueous_values is not None:
        ax.plot(
            x_um,
            [value / surface_scale for value in aqueous_values],
            label="Numerical aqueous-only",
            linewidth=1.4,
            color="#c55a11",
            marker="o",
            markersize=2.2,
            markevery=max(1, n // 20),
        )
        ax.plot(
            x_um,
            [value / surface_scale for value in analytical_aqueous],
            "--",
            label="Cell-averaged analytical aqueous-only",
            linewidth=1.5,
            color="#f2a65a",
        )
    ax.plot(
        x_um,
        [value / surface_scale for value in surface_values],
        label="Numerical surface-enabled",
        linewidth=1.8,
        color="#0b4f6c",
        marker="o",
        markersize=2.4,
        markevery=max(1, n // 20),
    )
    ax.plot(
        x_um,
        [value / surface_scale for value in analytical_surface],
        "--",
        label="Cell-averaged analytical surface-enabled",
        linewidth=1.6,
        color="#4f9da6",
    )
    ax.set_xlabel("x [$\\mu$m]")
    ax.set_ylabel("Normalized Ca$^{2+}$ concentration")
    ax.set_title("Aqueous profile")
    ax.set_ylim(-0.02, 1.05)
    ax.legend()
    ax.grid(True, alpha=0.25)

    ax2 = axes[1]
    ax2.plot(
        x_um,
        [value / loading_scale for value in numerical_surface_loading],
        label="Numerical surface loading",
        linewidth=1.8,
        color="#6b2d5c",
        marker="o",
        markersize=2.4,
        markevery=max(1, n // 20),
    )
    ax2.plot(
        x_um,
        [value / loading_scale for value in analytical_surface_loading],
        "--",
        label="Cell-averaged analytical linear limit",
        linewidth=1.6,
        color="#b565a7",
    )
    ax2.set_xlabel("x [$\\mu$m]")
    ax2.set_ylabel("Normalized Surf$_{a}$Ca$^{+}$")
    ax2.set_title("Surface loading")
    ax2.set_ylim(-0.02, 1.05)
    ax2.legend()
    ax2.grid(True, alpha=0.25)

    annotation_lines = [
        f"$R_{{field}}={r_field:.3f}$",
        f"surface L1 = {100.0 * l1_surface:.2f}%",
        f"surface $L_\\infty$ = {100.0 * linf_surface:.2f}%",
    ]
    if l1_aqueous is not None:
        annotation_lines.append(f"aqueous L1 = {100.0 * l1_aqueous:.2f}%")
    ax.text(
        0.03,
        0.04,
        "\n".join(annotation_lines),
        transform=ax.transAxes,
        fontsize=8.5,
        bbox={"facecolor": "white", "edgecolor": "#bdbdbd", "boxstyle": "round,pad=0.25"},
    )

    fig.suptitle("1D Linear Retardation Benchmark")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.tight_layout(rect=(0.0, 0.0, 1.0, 0.95))
    fig.savefig(args.output, dpi=200)


if __name__ == "__main__":
    main()
