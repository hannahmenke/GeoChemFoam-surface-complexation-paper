#!/usr/bin/env python3
"""Generate Kelvin temporal exchange figure (fig07)."""

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


# ── Field reader ──────────────────────────────────────────────────────────────

def parse_scalar_field_values(path: Path) -> float | np.ndarray:
    text = path.read_text()
    uniform_match = re.search(r"internalField\s+uniform\s+([^\n;]+)\s*;", text)
    if uniform_match:
        return float(uniform_match.group(1))
    nonuniform_match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text, re.S,
    )
    if not nonuniform_match:
        raise RuntimeError(f"Unsupported scalar field format in {path}")
    count = int(nonuniform_match.group(1))
    values = np.fromstring(nonuniform_match.group(2), sep=" ", count=count)
    if values.size != count:
        raise RuntimeError(f"Value count mismatch in {path}")
    return values


def weighted_mean(values: float | np.ndarray, weights: float | np.ndarray) -> tuple[float, float]:
    if isinstance(values, float) and isinstance(weights, float):
        return values * weights, weights
    if isinstance(values, float):
        assert isinstance(weights, np.ndarray)
        return values * float(weights.sum()), float(weights.sum())
    if isinstance(weights, float):
        return float(values.sum()) * weights, values.size * weights
    if values.size != weights.size:
        raise RuntimeError("Value and weight fields have different sizes")
    return float(np.dot(values, weights)), float(weights.sum())


def read_weighted_domain_mean(
    case_dir: Path,
    time_name: str,
    field_name: str,
    weight_field: str,
) -> float:
    """Average a field over all processor sub-domains using a local weight."""
    numerator = 0.0
    denominator = 0.0
    for proc_dir in sorted(case_dir.glob("processor*")):
        field_path = proc_dir / time_name / field_name
        weight_path = proc_dir / time_name / weight_field
        if not field_path.exists():
            raise FileNotFoundError(f"Missing field: {field_path}")
        if not weight_path.exists():
            raise FileNotFoundError(f"Missing weight field: {weight_path}")
        field_values = parse_scalar_field_values(field_path)
        weight_values = parse_scalar_field_values(weight_path)
        current_num, current_den = weighted_mean(field_values, weight_values)
        numerator += current_num
        denominator += current_den
    if denominator == 0.0:
        raise RuntimeError(f"No data found for {field_name} at t={time_name}")
    return numerator / denominator


def read_weighted_domain_mean_sum(
    case_dir: Path,
    time_name: str,
    field_names: str,
    weight_field: str,
) -> float:
    values = [
        read_weighted_domain_mean(case_dir, time_name, name.strip(), weight_field)
        for name in field_names.split(",")
        if name.strip()
    ]
    if not values:
        raise ValueError("At least one field name is required")
    return float(np.sum(values))


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


def filter_times(times: list[float], stride: float | None) -> list[float]:
    if stride is None or stride <= 0.0:
        return times
    selected = [
        t for t in times
        if np.isclose((t / stride) - round(t / stride), 0.0, atol=1.0e-8)
    ]
    if times and times[-1] not in selected:
        selected.append(times[-1])
    return sorted(set(selected))


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        description="Plot domain-mean Mn2+/Mg2+ competitive sorption vs time for Kelvin case"
    )
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument(
        "--target-in", type=float, default=1.0e-5,
        help="Inlet target-species concentration C_in [mol/L]"
    )
    parser.add_argument(
        "--background-in", type=float, default=1.0e-3,
        help="Initial/background species concentration [mol/L]"
    )
    parser.add_argument("--target-field", default="Mn+2")
    parser.add_argument("--background-field", default="Mg+2")
    parser.add_argument("--surf-target-fields", default="Hfo_sOMn+,Hfo_wOMn+")
    parser.add_argument("--surf-background-fields", default="Hfo_wOMg+")
    parser.add_argument("--aqueous-weight-field", default="eps")
    parser.add_argument("--surface-weight-field", default="aSurf")
    parser.add_argument("--target-label", default="Mn$^{2+}$")
    parser.add_argument("--background-label", default="Mg$^{2+}$")
    parser.add_argument("--surf-target-label", default="HFO-Mn")
    parser.add_argument("--surf-background-label", default="HFO-Mg")
    parser.add_argument(
        "--time-stride",
        type=float,
        default=None,
        help="Optional stride for subsampling output times in seconds.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    times = filter_times(available_times(args.case_dir), args.time_stride)
    print(f"Found time steps: {times}")

    target_means: list[float] = []
    background_means: list[float] = []
    surf_target_means: list[float] = []
    surf_background_means: list[float] = []

    for t in times:
        t_str = str(int(t)) if t == int(t) else str(t)
        print(f"  Reading t = {t_str} ...")
        target_means.append(
            read_weighted_domain_mean(
                args.case_dir, t_str, args.target_field, args.aqueous_weight_field
            )
        )
        background_means.append(
            read_weighted_domain_mean(
                args.case_dir, t_str, args.background_field, args.aqueous_weight_field
            )
        )
        surf_target_means.append(
            read_weighted_domain_mean_sum(
                args.case_dir, t_str, args.surf_target_fields, args.surface_weight_field
            )
        )
        surf_background_means.append(
            read_weighted_domain_mean_sum(
                args.case_dir, t_str, args.surf_background_fields, args.surface_weight_field
            )
        )

    t_arr = np.array(times)
    target_norm = np.array(target_means) / args.target_in
    background_excess_percent = 100.0 * (
        np.array(background_means) / args.background_in - 1.0
    )

    surf_target = np.array(surf_target_means)
    surf_background = np.array(surf_background_means)
    surf_target_incr = surf_target - surf_target[0]
    surf_background_incr = surf_background - surf_background[0]
    surf_scale = max(
        np.abs(surf_target_incr).max(),
        np.abs(surf_background_incr).max(),
        1.0e-40,
    )
    surf_target_norm = surf_target_incr / surf_scale
    surf_background_norm = surf_background_incr / surf_scale

    # ── Plot ─────────────────────────────────────────────────────────────────
    fig, axes = plt.subplots(1, 2, figsize=(10.4, 3.8), constrained_layout=True)

    ax1 = axes[0]
    line_target, = ax1.plot(
        t_arr, target_norm,
        color="#c0392b", linewidth=1.8,
        marker="^", markersize=4.5,
        label=f"{args.target_label} arrival",
    )
    ax1.set_xlabel("Time [s]")
    ax1.set_ylabel(f"{args.target_label} / $C_{{\\mathrm{{in}}}}$")
    ax1.set_ylim(bottom=0.0)
    ax1.set_title("Aqueous response")
    ax1.grid(True, alpha=0.25)

    ax1b = ax1.twinx()
    line_background, = ax1b.plot(
        t_arr, background_excess_percent,
        color="#0b4f6c", linewidth=1.8,
        marker="o", markersize=4.5,
        label=f"{args.background_label} release",
    )
    ax1b.axhline(0.0, color="0.25", linewidth=0.9)
    ax1b.set_ylabel(f"{args.background_label} excess [%]")
    ax1b.set_ylim(bottom=0.0)
    ax1.legend(
        [line_target, line_background],
        [line_target.get_label(), line_background.get_label()],
        fontsize=9,
        loc="lower right",
    )

    ax2 = axes[1]
    ax2.plot(
        t_arr, surf_background_norm,
        color="#0b4f6c", linewidth=1.8,
        marker="o", markersize=4.5,
        label=f"$\\Delta${args.surf_background_label}",
    )
    ax2.plot(
        t_arr, surf_target_norm,
        color="#c0392b", linewidth=1.8,
        marker="^", markersize=4.5,
        label=f"$\\Delta${args.surf_target_label}",
    )
    ax2.set_xlabel("Time [s]")
    ax2.set_ylabel("Normalised $\\Delta$ surface loading")
    ax2.axhline(0.0, color="0.25", linewidth=0.9)
    ax2.set_ylim(-1.05, 1.05)
    ax2.set_title("Surface loading")
    ax2.legend(fontsize=9)
    ax2.grid(True, alpha=0.25)

    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=200)
    print(f"Wrote {args.output}")


if __name__ == "__main__":
    main()
