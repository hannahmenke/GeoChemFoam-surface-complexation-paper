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


def block_weighted_mean(values: np.ndarray, weights: np.ndarray, stride: int) -> np.ndarray:
    ny, nx = values.shape
    if ny % stride or nx % stride:
        raise RuntimeError(f"Stride {stride} must divide field shape {nx} x {ny}.")
    shape = (ny // stride, stride, nx // stride, stride)
    numerator = (values * weights).reshape(shape).sum(axis=(1, 3))
    denominator = weights.reshape(shape).sum(axis=(1, 3))
    return np.divide(
        numerator,
        denominator,
        out=np.full(numerator.shape, np.nan, dtype=np.float32),
        where=denominator > 0,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--times", nargs=3, required=True)
    parser.add_argument("--labels", nargs=3, default=["beginning", "middle", "end"])
    parser.add_argument("--stride", type=int, default=5)
    parser.add_argument("--li-inlet", type=float, default=1.0e-3)
    parser.add_argument("--peclet", type=float, default=1.0)
    parser.add_argument("--case-label", default="Fully resolved 5 µm")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    theta = stitch_field(args.case_dir, args.times[0], "eps")
    asurf = stitch_field(args.case_dir, args.times[0], "aSurf")
    aqueous: list[np.ndarray] = []
    sorbed: list[np.ndarray] = []
    summaries: dict[str, dict[str, float]] = {}

    for time_name, label in zip(args.times, args.labels):
        li = stitch_field(args.case_dir, time_name, "Li+")
        sor_li = stitch_field(args.case_dir, time_name, "Sor_aLi")
        li_display = block_weighted_mean(li, theta, args.stride) / args.li_inlet
        # Sor_aLi is stored in OpenFOAM amount units (kmol/m2). Convert to mol/m2.
        sor_display = block_weighted_mean(sor_li, asurf, args.stride) * 1000.0
        aqueous.append(li_display)
        sorbed.append(sor_display)
        positive_sorbed = sor_display[np.isfinite(sor_display) & (sor_display > 0)]
        summaries[label] = {
            "time_s": float(time_name),
            "aqueous_li_over_inlet_min": float(np.nanmin(li_display)),
            "aqueous_li_over_inlet_max": float(np.nanmax(li_display)),
            "sorbed_li_mol_m-2_min_positive": (
                float(np.min(positive_sorbed)) if positive_sorbed.size else 0.0
            ),
            "sorbed_li_mol_m-2_max": float(np.nanmax(sor_display)),
        }

    all_positive = np.concatenate(
        [field[np.isfinite(field) & (field > 0)] for field in sorbed]
    )
    sor_vmin = float(np.percentile(all_positive, 1.0))
    sor_vmax = float(np.percentile(all_positive, 99.9))
    if sor_vmax <= sor_vmin:
        raise RuntimeError("Sorbed-Li range is insufficient for a shared log scale.")
    sor_log_vmin = float(np.log10(sor_vmin))
    sor_log_vmax = float(np.log10(sor_vmax))

    fig, axes = plt.subplots(2, 3, figsize=(16.0, 6.8), constrained_layout=True)
    extent = (0.0, 18.0, 0.0, 6.0)
    aqueous_image = None
    sorbed_image = None
    for column, (time_name, label) in enumerate(zip(args.times, args.labels)):
        aqueous_image = axes[0, column].imshow(
            aqueous[column],
            origin="lower",
            extent=extent,
            cmap="viridis",
            interpolation="nearest",
            vmin=0.0,
            vmax=1.0,
            aspect="equal",
        )
        sorbed_log = np.full(sorbed[column].shape, np.nan, dtype=np.float32)
        np.log10(sorbed[column], out=sorbed_log, where=sorbed[column] > 0)
        sorbed_image = axes[1, column].imshow(
            sorbed_log,
            origin="lower",
            extent=extent,
            cmap="magma",
            interpolation="nearest",
            vmin=sor_log_vmin,
            vmax=sor_log_vmax,
            aspect="equal",
        )
        axes[0, column].set_title(f"{label.capitalize()} — t = {float(time_name):.3f} s")
        axes[1, column].set_title(f"{label.capitalize()} — t = {float(time_name):.3f} s")
        for row in range(2):
            axes[row, column].set_xlabel("x [mm]")
            if column == 0:
                axes[row, column].set_ylabel("y [mm]")

    if aqueous_image is None or sorbed_image is None:
        raise RuntimeError("No fields were plotted.")
    aqueous_bar = fig.colorbar(
        aqueous_image, ax=axes[0, :], orientation="horizontal", fraction=0.08, pad=0.12
    )
    aqueous_bar.set_label("Pore-volume-weighted aqueous Li / inlet Li")
    sorbed_bar = fig.colorbar(
        sorbed_image, ax=axes[1, :], orientation="horizontal", fraction=0.08, pad=0.12
    )
    sorbed_bar.set_label("log10(area-weighted sorbed Li [mol m$^{-2}$])")
    fig.suptitle(
        f"{args.case_label} Pe={args.peclet:g} production run: aqueous and sorbed lithium progression",
        fontsize=14,
    )
    args.output.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.output, dpi=220)
    plt.close(fig)

    summary = {
        "case_dir": str(args.case_dir),
        "source_cell_size_um": 5.0,
        "display_block_cells": [args.stride, args.stride],
        "times": summaries,
        "sorbed_li_shared_scale_mol_m-2": [sor_vmin, sor_vmax],
        "output": str(args.output),
    }
    args.output.with_suffix(".json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
