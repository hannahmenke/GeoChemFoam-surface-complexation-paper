#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from dataclasses import dataclass
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from plot_latest_concentration_field import stitch_field


INLET_LI = 1.0e-3
DOMAIN_LENGTH_M = 18.0e-3


@dataclass
class Case:
    label: str
    cell_um: int
    directory: Path
    time: str
    theta: np.ndarray
    aqueous_density: np.ndarray
    sorbed_density: np.ndarray
    li: np.ndarray
    sor_li_mol_m2: np.ndarray
    total_asurf: np.ndarray


def field_with_fallback(case_dir: Path, time: str, field: str) -> np.ndarray:
    path = case_dir / "processor0" / time / field
    return stitch_field(case_dir, time if path.exists() else "0", field)


def load_case(label: str, cell_um: int, directory: Path, time: str) -> Case:
    li = stitch_field(directory, time, "Li+").astype(np.float64)
    theta = stitch_field(directory, time, "eps").astype(np.float64)
    sor_li = stitch_field(directory, time, "Sor_aLi").astype(np.float64)
    asurf = stitch_field(directory, time, "aSurf").astype(np.float64)
    asurf_intrinsic = field_with_fallback(directory, time, "aSurfIntrinsic").astype(np.float64)
    total_asurf = asurf + asurf_intrinsic
    return Case(
        label=label,
        cell_um=cell_um,
        directory=directory,
        time=time,
        theta=theta,
        aqueous_density=li * theta,
        sorbed_density=sor_li * total_asurf,
        li=li,
        # OpenFOAM surface amount is kmol/m2; display in mol/m2.
        sor_li_mol_m2=sor_li * 1000.0,
        total_asurf=total_asurf,
    )


def block_mean(values: np.ndarray, factor: int) -> np.ndarray:
    ny, nx = values.shape
    if ny % factor or nx % factor:
        raise ValueError(f"Factor {factor} does not divide shape {values.shape}")
    return values.reshape(ny // factor, factor, nx // factor, factor).mean(axis=(1, 3))


def cosine(a: np.ndarray, b: np.ndarray) -> float:
    av = a.ravel()
    bv = b.ravel()
    denominator = float(np.linalg.norm(av) * np.linalg.norm(bv))
    return float(np.dot(av, bv) / denominator) if denominator else math.nan


def profile(values: np.ndarray, bins: int) -> np.ndarray:
    ny, nx = values.shape
    if nx % bins:
        raise ValueError(f"{bins} bins do not divide nx={nx}")
    return values.reshape(ny, bins, nx // bins).sum(axis=(0, 2))


def normalized_l1(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.sum(np.abs(a / np.sum(a) - b / np.sum(b))))


def cumulative_x50(values: np.ndarray) -> float:
    p = np.sum(values, axis=0)
    idx = int(np.searchsorted(np.cumsum(p), 0.5 * np.sum(p), side="left"))
    return (idx + 0.5) * DOMAIN_LENGTH_M / len(p)


def threshold_front(li: np.ndarray, theta: np.ndarray, threshold: float) -> float:
    column_mean = np.divide(
        np.sum(li * theta, axis=0),
        np.sum(theta, axis=0),
        out=np.zeros(li.shape[1]),
        where=np.sum(theta, axis=0) > 0,
    )
    hits = np.flatnonzero(column_mean >= threshold * INLET_LI)
    return float((hits[-1] + 0.5) * DOMAIN_LENGTH_M / li.shape[1]) if hits.size else math.nan


def relative(candidate: float, reference: float) -> float:
    return (candidate - reference) / reference


def metrics(reference: Case, candidate: Case) -> dict[str, float | bool]:
    factor = candidate.cell_um // reference.cell_um
    ref_aq_map = block_mean(reference.aqueous_density, factor)
    ref_sor_map = block_mean(reference.sorbed_density, factor)
    if ref_aq_map.shape != candidate.aqueous_density.shape:
        raise ValueError(f"Aqueous map shape mismatch: {ref_aq_map.shape} vs {candidate.aqueous_density.shape}")

    ref_x50_aq = cumulative_x50(reference.aqueous_density)
    ref_x50_sor = cumulative_x50(reference.sorbed_density)
    cand_x50_aq = cumulative_x50(candidate.aqueous_density)
    cand_x50_sor = cumulative_x50(candidate.sorbed_density)
    ref_front_1pct = threshold_front(reference.li, reference.theta, 0.01)
    cand_front_1pct = threshold_front(candidate.li, candidate.theta, 0.01)

    result: dict[str, float | bool] = {
        "cell_size_um": float(candidate.cell_um),
        "nx": float(candidate.li.shape[1]),
        "ny": float(candidate.li.shape[0]),
        "porosity_relative_difference": relative(float(np.mean(candidate.theta)), float(np.mean(reference.theta))),
        "reactive_area_density_relative_difference": relative(float(np.mean(candidate.total_asurf)), float(np.mean(reference.total_asurf))),
        "aqueous_li_inventory_density_relative_difference": relative(float(np.mean(candidate.aqueous_density)), float(np.mean(reference.aqueous_density))),
        "sorbed_li_inventory_density_relative_difference": relative(float(np.mean(candidate.sorbed_density)), float(np.mean(reference.sorbed_density))),
        "aqueous_li_profile_l1_100_bins": normalized_l1(profile(candidate.aqueous_density, 100), profile(reference.aqueous_density, 100)),
        "sorbed_li_profile_l1_100_bins": normalized_l1(profile(candidate.sorbed_density, 100), profile(reference.sorbed_density, 100)),
        "aqueous_li_profile_l1_600_bins": normalized_l1(profile(candidate.aqueous_density, 600), profile(reference.aqueous_density, 600)),
        "sorbed_li_profile_l1_600_bins": normalized_l1(profile(candidate.sorbed_density, 600), profile(reference.sorbed_density, 600)),
        "aqueous_li_map_cosine": cosine(candidate.aqueous_density, ref_aq_map),
        "sorbed_li_map_cosine": cosine(candidate.sorbed_density, ref_sor_map),
        "aqueous_x50_m": cand_x50_aq,
        "aqueous_x50_difference_m": cand_x50_aq - ref_x50_aq,
        "aqueous_x50_difference_candidate_cells": (cand_x50_aq - ref_x50_aq) / (candidate.cell_um * 1.0e-6),
        "sorbed_x50_m": cand_x50_sor,
        "sorbed_x50_difference_m": cand_x50_sor - ref_x50_sor,
        "sorbed_x50_difference_candidate_cells": (cand_x50_sor - ref_x50_sor) / (candidate.cell_um * 1.0e-6),
        "aqueous_1pct_front_m": cand_front_1pct,
        "aqueous_1pct_front_difference_m": cand_front_1pct - ref_front_1pct,
        "aqueous_1pct_front_difference_candidate_cells": (cand_front_1pct - ref_front_1pct) / (candidate.cell_um * 1.0e-6),
    }
    result["passes_predeclared_acceptance"] = bool(
        abs(result["porosity_relative_difference"]) <= 0.02
        and abs(result["reactive_area_density_relative_difference"]) <= 0.02
        and abs(result["aqueous_li_inventory_density_relative_difference"]) <= 0.02
        and abs(result["sorbed_li_inventory_density_relative_difference"]) <= 0.02
        and result["aqueous_li_profile_l1_100_bins"] <= 0.05
        and result["sorbed_li_profile_l1_100_bins"] <= 0.05
        and abs(result["aqueous_x50_difference_candidate_cells"]) <= 1.0
        and abs(result["sorbed_x50_difference_candidate_cells"]) <= 1.0
        and result["sorbed_li_map_cosine"] >= 0.95
    )
    return result


def plot_fields(cases: list[Case], output: Path) -> None:
    fig, axes = plt.subplots(3, len(cases), figsize=(16, 8.2), constrained_layout=True)
    extent = (0.0, 18.0, 0.0, 6.0)
    sor_vmax = float(np.percentile(np.concatenate([c.sor_li_mol_m2.ravel() for c in cases]), 99.8))
    for col, case in enumerate(cases):
        geometry = axes[0, col].imshow(case.theta, origin="lower", extent=extent, cmap="gray_r", vmin=0.4, vmax=1.0, interpolation="nearest")
        aqueous = axes[1, col].imshow(case.li / INLET_LI, origin="lower", extent=extent, cmap="viridis", vmin=0.0, vmax=1.0, interpolation="nearest")
        sorbed = axes[2, col].imshow(case.sor_li_mol_m2, origin="lower", extent=extent, cmap="magma", vmin=0.0, vmax=sor_vmax, interpolation="nearest")
        axes[0, col].set_title(f"{case.label} — t={float(case.time):.3f} s")
        for row in range(3):
            axes[row, col].set_aspect("equal")
            axes[row, col].set_xlabel("x [mm]")
            if col == 0:
                axes[row, col].set_ylabel("y [mm]")
    fig.colorbar(geometry, ax=axes[0, :], label="Porosity, θ", shrink=0.8)
    fig.colorbar(aqueous, ax=axes[1, :], label="Aqueous Li / inlet Li", shrink=0.8)
    fig.colorbar(sorbed, ax=axes[2, :], label="Sorbed Li [mol m$^{-2}$], linear scale", shrink=0.8)
    fig.suptitle("Full-domain DBS grid-convergence checkpoint (Pe=1, ~0.75 transit)")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220)
    plt.close(fig)


def plot_profiles(cases: list[Case], output: Path) -> None:
    fig, axes = plt.subplots(2, 1, figsize=(10.5, 7.0), sharex=True, constrained_layout=True)
    x = (np.arange(600) + 0.5) * 18.0 / 600
    for case in cases:
        aq = profile(case.aqueous_density, 600)
        sor = profile(case.sorbed_density, 600)
        axes[0].plot(x, aq / np.sum(aq), label=case.label, lw=1.2)
        axes[1].plot(x, sor / np.sum(sor), label=case.label, lw=1.2)
    axes[0].set_ylabel("Normalized aqueous-Li inventory")
    axes[1].set_ylabel("Normalized sorbed-Li inventory")
    axes[1].set_xlabel("x [mm]")
    axes[0].legend()
    axes[1].legend()
    fig.suptitle("DBS streamwise profiles on common 30 µm bins")
    output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output, dpi=220)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-5", type=Path, required=True)
    parser.add_argument("--time-5", required=True)
    parser.add_argument("--case-10", type=Path, required=True)
    parser.add_argument("--time-10", required=True)
    parser.add_argument("--case-15", type=Path, required=True)
    parser.add_argument("--time-15", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    cases = [
        load_case("5 µm reference", 5, args.case_5, args.time_5),
        load_case("10 µm", 10, args.case_10, args.time_10),
        load_case("15 µm", 15, args.case_15, args.time_15),
    ]
    comparison = {
        "reference": {
            "label": cases[0].label,
            "time_s": float(cases[0].time),
            "cell_size_um": cases[0].cell_um,
            "nx": cases[0].li.shape[1],
            "ny": cases[0].li.shape[0],
            "aqueous_x50_m": cumulative_x50(cases[0].aqueous_density),
            "sorbed_x50_m": cumulative_x50(cases[0].sorbed_density),
            "aqueous_1pct_front_m": threshold_front(cases[0].li, cases[0].theta, 0.01),
        },
        "10um_vs_5um": metrics(cases[0], cases[1]),
        "15um_vs_5um": metrics(cases[0], cases[2]),
        "acceptance": {
            "porosity_relative_difference_max": 0.02,
            "reactive_area_density_relative_difference_max": 0.02,
            "aqueous_and_sorbed_inventory_density_relative_difference_max": 0.02,
            "normalized_profile_l1_100_bins_max": 0.05,
            "x50_front_difference_candidate_cells_max": 1.0,
            "sorbed_map_cosine_min": 0.95,
        },
    }
    args.output_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = args.output_dir / "dbs_5_10_15_checkpoint_metrics.json"
    metrics_path.write_text(json.dumps(comparison, indent=2) + "\n")
    plot_fields(cases, args.output_dir / "dbs_5_10_15_checkpoint_fields.png")
    plot_profiles(cases, args.output_dir / "dbs_5_10_15_checkpoint_profiles.png")
    print(json.dumps(comparison, indent=2))


if __name__ == "__main__":
    main()
