#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap
import numpy as np

from plot_latest_concentration_field import stitch_field


INLET_LI = 1.0e-3
LENGTH_M = 18.0e-3


def field_with_fallback(case_dir: Path, time: str, field: str) -> np.ndarray:
    selected_time = time if (case_dir / "processor0" / time / field).exists() else "0"
    return stitch_field(case_dir, selected_time, field).astype(np.float64)


def porosity_field(case_dir: Path, time: str) -> np.ndarray:
    # Current scalar PHREEQC runs write epsNum at every checkpoint. Legacy
    # outputs retain eps instead, so preserve support for both datasets.
    field = "epsNum" if (case_dir / "processor0" / time / "epsNum").exists() else "eps"
    return field_with_fallback(case_dir, time, field)


def load(case_dir: Path, time: str) -> dict[str, np.ndarray]:
    li = stitch_field(case_dir, time, "Li+").astype(np.float64)
    theta = porosity_field(case_dir, time)
    sor = stitch_field(case_dir, time, "Sor_aLi").astype(np.float64)
    asurf = stitch_field(case_dir, time, "aSurf").astype(np.float64)
    # The solver assembles intrinsic matrix area into the written aSurf field
    # before chemistry. aSurfIntrinsic is a diagnostic input and must not be
    # added again during post-processing.
    area = asurf
    return {
        "li": li,
        "eps": theta,
        "sor": sor,
        "area": area,
        "aqueous_density": li * theta,
        "sorbed_density": sor * area,
    }


def block_sum(a: np.ndarray, stride: int) -> np.ndarray:
    ny, nx = a.shape
    if ny % stride or nx % stride:
        raise ValueError(f"Stride {stride} does not divide {a.shape}")
    return a.reshape(ny // stride, stride, nx // stride, stride).sum(axis=(1, 3))


def weighted_blocks(values: np.ndarray, weights: np.ndarray, stride: int) -> np.ndarray:
    numerator = block_sum(values * weights, stride)
    denominator = block_sum(weights, stride)
    return np.divide(numerator, denominator, out=np.full_like(numerator, np.nan), where=denominator > 0)


def profile(a: np.ndarray, bins: int) -> np.ndarray:
    ny, nx = a.shape
    if nx % bins:
        raise ValueError(f"{bins} bins do not divide nx={nx}")
    return a.reshape(ny, bins, nx // bins).sum(axis=(0, 2))


def normalized_l1(candidate: np.ndarray, reference: np.ndarray) -> float:
    return float(np.sum(np.abs(candidate / np.sum(candidate) - reference / np.sum(reference))))


def cosine(candidate: np.ndarray, reference: np.ndarray) -> float:
    valid = np.isfinite(candidate) & np.isfinite(reference)
    a = candidate[valid]
    b = reference[valid]
    denom = float(np.linalg.norm(a) * np.linalg.norm(b))
    return float(np.dot(a, b) / denom) if denom else math.nan


def x50(density: np.ndarray) -> float:
    p = np.sum(density, axis=0)
    idx = int(np.searchsorted(np.cumsum(p), 0.5 * np.sum(p), side="left"))
    return (idx + 0.5) * LENGTH_M / density.shape[1]


def rel(candidate: float, reference: float) -> float:
    return (candidate - reference) / reference


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--resolved", type=Path, required=True)
    parser.add_argument("--resolved-time", required=True)
    parser.add_argument("--dbs", type=Path, required=True)
    parser.add_argument("--dbs-time", required=True)
    parser.add_argument("--peclet", type=float, default=1.0)
    parser.add_argument("--stride", type=int, default=20, help="5 um cells per macro display block")
    parser.add_argument("--transits", type=float, default=1.25, help="Matched advective distance x/L")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    pe_label = f"{args.peclet:g}"
    pe_slug = pe_label.replace(".", "p")

    resolved = load(args.resolved, args.resolved_time)
    dbs = load(args.dbs, args.dbs_time)
    for key in resolved:
        if resolved[key].shape != dbs[key].shape:
            raise ValueError(f"Shape mismatch for {key}: {resolved[key].shape} vs {dbs[key].shape}")

    resolved_aq_macro = weighted_blocks(resolved["li"], resolved["eps"], args.stride)
    dbs_aq_macro = weighted_blocks(dbs["li"], dbs["eps"], args.stride)
    resolved_sor_macro = weighted_blocks(resolved["sor"], resolved["area"], args.stride) * 1000.0
    dbs_sor_macro = weighted_blocks(dbs["sor"], dbs["area"], args.stride) * 1000.0

    resolved_aq_x50 = x50(resolved["aqueous_density"])
    dbs_aq_x50 = x50(dbs["aqueous_density"])
    resolved_sor_x50 = x50(resolved["sorbed_density"])
    dbs_sor_x50 = x50(dbs["sorbed_density"])
    summary = {
        "alignment": {
            "basis": f"Pe={pe_label} and x/L={args.transits:g} advective transits",
            "resolved_case_dir": str(args.resolved),
            "dbs_case_dir": str(args.dbs),
            "resolved_time_s": float(args.resolved_time),
            "dbs_time_s": float(args.dbs_time),
            "macro_block_um": args.stride * 5,
        },
        "resolved": {
            "porosity": float(np.mean(resolved["eps"])),
            "reactive_area_density_m-1": float(np.mean(resolved["area"])),
            "aqueous_li_inventory_density": float(np.mean(resolved["aqueous_density"])),
            "sorbed_li_inventory_density": float(np.mean(resolved["sorbed_density"])),
            "aqueous_x50_m": resolved_aq_x50,
            "sorbed_x50_m": resolved_sor_x50,
        },
        "dbs": {
            "porosity": float(np.mean(dbs["eps"])),
            "reactive_area_density_m-1": float(np.mean(dbs["area"])),
            "aqueous_li_inventory_density": float(np.mean(dbs["aqueous_density"])),
            "sorbed_li_inventory_density": float(np.mean(dbs["sorbed_density"])),
            "aqueous_x50_m": dbs_aq_x50,
            "sorbed_x50_m": dbs_sor_x50,
        },
        "dbs_vs_resolved": {
            "porosity_relative_difference": rel(float(np.mean(dbs["eps"])), float(np.mean(resolved["eps"]))),
            "reactive_area_density_relative_difference": rel(float(np.mean(dbs["area"])), float(np.mean(resolved["area"]))),
            "aqueous_li_inventory_density_relative_difference": rel(float(np.mean(dbs["aqueous_density"])), float(np.mean(resolved["aqueous_density"]))),
            "sorbed_li_inventory_density_relative_difference": rel(float(np.mean(dbs["sorbed_density"])), float(np.mean(resolved["sorbed_density"]))),
            "aqueous_li_profile_normalized_l1_100_bins": normalized_l1(profile(dbs["aqueous_density"], 100), profile(resolved["aqueous_density"], 100)),
            "sorbed_li_profile_normalized_l1_100_bins": normalized_l1(profile(dbs["sorbed_density"], 100), profile(resolved["sorbed_density"], 100)),
            "aqueous_li_macro_map_cosine": cosine(dbs_aq_macro, resolved_aq_macro),
            "sorbed_li_macro_map_cosine": cosine(dbs_sor_macro, resolved_sor_macro),
            "aqueous_x50_difference_m": dbs_aq_x50 - resolved_aq_x50,
            "sorbed_x50_difference_m": dbs_sor_x50 - resolved_sor_x50,
        },
    }

    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / f"resolved_vs_dbs_pe{pe_slug}_metrics.json").write_text(json.dumps(summary, indent=2) + "\n")

    fig, axes = plt.subplots(3, 2, figsize=(12.5, 8.5), constrained_layout=True)
    extent = (0.0, 18.0, 0.0, 6.0)
    resolved_phase = (resolved["eps"] > 0.5).astype(float)
    dbs_phase = (dbs["eps"] > 0.999).astype(float)
    phase_cmap = ListedColormap(["black", "white"])
    axes[0, 0].imshow(resolved_phase, origin="lower", extent=extent, cmap=phase_cmap, vmin=0, vmax=1, interpolation="nearest")
    axes[0, 1].imshow(dbs_phase, origin="lower", extent=extent, cmap=phase_cmap, vmin=0, vmax=1, interpolation="nearest")
    aq0 = axes[1, 0].imshow(resolved_aq_macro / INLET_LI, origin="lower", extent=extent, cmap="viridis", vmin=0, vmax=1, interpolation="nearest")
    axes[1, 1].imshow(dbs_aq_macro / INLET_LI, origin="lower", extent=extent, cmap="viridis", vmin=0, vmax=1, interpolation="nearest")
    sor_vmax = float(np.nanpercentile(np.concatenate([resolved_sor_macro.ravel(), dbs_sor_macro.ravel()]), 99.5))
    sor0 = axes[2, 0].imshow(resolved_sor_macro, origin="lower", extent=extent, cmap="magma", vmin=0, vmax=sor_vmax, interpolation="nearest")
    axes[2, 1].imshow(dbs_sor_macro, origin="lower", extent=extent, cmap="magma", vmin=0, vmax=sor_vmax, interpolation="nearest")
    axes[0, 0].set_title(f"Resolved 5 µm — t={float(args.resolved_time):.3f} s")
    axes[0, 1].set_title(f"DBS 5 µm — t={float(args.dbs_time):.3f} s")
    axes[0, 0].set_ylabel("Categorical pore/grain")
    axes[0, 1].set_ylabel("Categorical vug/matrix")
    axes[1, 0].set_ylabel("Aqueous Li")
    axes[2, 0].set_ylabel("Sorbed Li")
    for ax in axes.ravel():
        ax.set_xlabel("x [mm]")
        ax.set_aspect("equal")
    fig.colorbar(aq0, ax=axes[1, :], label="100 µm pore-volume-weighted Li / inlet Li", shrink=0.8)
    fig.colorbar(sor0, ax=axes[2, :], label="100 µm area-weighted sorbed Li [mol m$^{-2}$], linear", shrink=0.8)
    fig.suptitle(f"Pe={pe_label} endpoint comparison at matched x/L={args.transits:g}")
    fig.savefig(args.output_dir / f"resolved_vs_dbs_pe{pe_slug}_fields.png", dpi=220)
    plt.close(fig)

    x = (np.arange(100) + 0.5) * 18.0 / 100
    fig, axes = plt.subplots(2, 1, figsize=(10, 7), sharex=True, constrained_layout=True)
    for label, data in (("Resolved 5 µm", resolved), ("DBS 5 µm", dbs)):
        aq = profile(data["aqueous_density"], 100)
        sor = profile(data["sorbed_density"], 100)
        axes[0].plot(x, aq / np.sum(aq), label=label)
        axes[1].plot(x, sor / np.sum(sor), label=label)
    axes[0].set_ylabel("Normalized aqueous-Li inventory")
    axes[1].set_ylabel("Normalized sorbed-Li inventory")
    axes[1].set_xlabel("x [mm]")
    axes[0].legend()
    axes[1].legend()
    fig.suptitle("Resolved versus DBS streamwise profiles")
    fig.savefig(args.output_dir / f"resolved_vs_dbs_pe{pe_slug}_profiles.png", dpi=220)
    plt.close(fig)
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
