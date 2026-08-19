#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from plot_latest_concentration_field import stitch_field


LENGTH_M = 18.0e-3
INLET = 1.0e-3


def profile(a: np.ndarray, bins: int = 100) -> np.ndarray:
    ny, nx = a.shape
    return a.reshape(ny, bins, nx // bins).sum(axis=(0, 2))


def x50(a: np.ndarray) -> float:
    p = np.sum(a, axis=0)
    i = int(np.searchsorted(np.cumsum(p), 0.5 * np.sum(p), side="left"))
    return (i + 0.5) * LENGTH_M / a.shape[1]


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    av, bv = a.ravel(), b.ravel()
    return float(np.dot(av, bv) / (np.linalg.norm(av) * np.linalg.norm(bv)))


def case_metrics(reactive: Path, passive: Path, time: str) -> tuple[dict[str, float], dict[str, np.ndarray]]:
    theta = stitch_field(reactive, time, "theta").astype(np.float64)
    area = stitch_field(reactive, time, "aSurf").astype(np.float64)
    reactive_li = stitch_field(reactive, time, "Li+").astype(np.float64)
    passive_li = stitch_field(passive, time, "Li+").astype(np.float64)
    sor = stitch_field(reactive, time, "Sor_aLi").astype(np.float64)
    reactive_aq = reactive_li * theta
    passive_aq = passive_li * theta
    reactive_sor = sor * area
    passive_total = float(np.mean(passive_aq))
    reactive_aq_total = float(np.mean(reactive_aq))
    reactive_sor_total = float(np.mean(reactive_sor))
    reactive_total = reactive_aq_total + reactive_sor_total
    pa = profile(passive_aq)
    ra = profile(reactive_aq)
    metrics = {
        "passive_aqueous_inventory_density": passive_total,
        "reactive_aqueous_inventory_density": reactive_aq_total,
        "reactive_sorbed_inventory_density": reactive_sor_total,
        "reactive_total_li_inventory_density": reactive_total,
        "reactive_total_vs_passive_relative_difference": (reactive_total - passive_total) / passive_total,
        "reactive_aqueous_vs_passive_relative_difference": (reactive_aq_total - passive_total) / passive_total,
        "passive_aqueous_x50_m": x50(passive_aq),
        "reactive_aqueous_x50_m": x50(reactive_aq),
        "reactive_sorbed_x50_m": x50(reactive_sor),
        "reactive_vs_passive_aqueous_profile_l1": float(np.sum(np.abs(ra / np.sum(ra) - pa / np.sum(pa)))),
        "reactive_vs_passive_aqueous_map_cosine": cosine(reactive_aq, passive_aq),
    }
    fields = {
        "theta": theta,
        "passive_li": passive_li,
        "reactive_li": reactive_li,
        "reactive_sor_mol_m2": sor * 1000.0,
    }
    return metrics, fields


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--resolved-reactive", type=Path, required=True)
    p.add_argument("--resolved-passive", type=Path, required=True)
    p.add_argument("--resolved-time", required=True)
    p.add_argument("--dbs-reactive", type=Path, required=True)
    p.add_argument("--dbs-passive", type=Path, required=True)
    p.add_argument("--dbs-time", required=True)
    p.add_argument("--output-dir", type=Path, required=True)
    args = p.parse_args()

    resolved_metrics, resolved = case_metrics(args.resolved_reactive, args.resolved_passive, args.resolved_time)
    dbs_metrics, dbs = case_metrics(args.dbs_reactive, args.dbs_passive, args.dbs_time)
    summary = {
        "alignment": "Pe=1, x/L=0.125; passive and reactive use identical mesh, U, theta, D, dt, and inlet",
        "resolved": resolved_metrics,
        "dbs": dbs_metrics,
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / "passive_vs_reactive_xL0p125_metrics.json").write_text(json.dumps(summary, indent=2) + "\n")

    fig, axes = plt.subplots(2, 2, figsize=(12, 5.6), constrained_layout=True)
    extent = (0, 18, 0, 6)
    for row, (label, fields, time) in enumerate(
        (("Resolved 5 µm", resolved, args.resolved_time), ("DBS 5 µm", dbs, args.dbs_time))
    ):
        im = axes[row, 0].imshow(fields["passive_li"] / INLET, origin="lower", extent=extent, cmap="viridis", vmin=0, vmax=1, interpolation="nearest")
        axes[row, 1].imshow(fields["reactive_li"] / INLET, origin="lower", extent=extent, cmap="viridis", vmin=0, vmax=1, interpolation="nearest")
        axes[row, 0].set_ylabel(f"{label}\ny [mm]")
        axes[row, 0].set_title(f"Passive tracer — t={float(time):.3f} s")
        axes[row, 1].set_title(f"Reactive aqueous Li — t={float(time):.3f} s")
        for col in range(2):
            axes[row, col].set_xlabel("x [mm]")
            axes[row, col].set_aspect("equal")
    fig.colorbar(im, ax=axes, label="Li / inlet Li", shrink=0.85)
    fig.suptitle("Chemistry-free versus reactive transport at x/L=0.125")
    fig.savefig(args.output_dir / "passive_vs_reactive_xL0p125_fields.png", dpi=220)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
