#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.ticker import FuncFormatter
import numpy as np

from plot_latest_concentration_field import stitch_field


INLET_LI = 1.0e-3
LENGTH_MM = 18.0
EXTENT_MM = (0.0, 18.0, 0.0, 6.0)


def configure_style() -> None:
    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9.0,
            "axes.titlesize": 10.5,
            "axes.labelsize": 9.5,
            "axes.linewidth": 0.8,
            "xtick.labelsize": 8.5,
            "ytick.labelsize": 8.5,
            "legend.fontsize": 8.5,
            "lines.linewidth": 1.8,
            "lines.markersize": 5.5,
            "savefig.facecolor": "white",
        }
    )


def load_native_fields(
    case_dir: Path, time_name: str, *, resolved: bool
) -> dict[str, np.ndarray]:
    theta = stitch_field(case_dir, time_name, "eps")
    area = stitch_field(case_dir, time_name, "aSurf")
    aqueous = stitch_field(case_dir, time_name, "Li+").astype(np.float32) / INLET_LI
    sorbed = stitch_field(case_dir, time_name, "Sor_aLi").astype(np.float32) * 1000.0
    if resolved:
        aqueous = np.where(theta > 0.5, aqueous, np.nan)
    else:
        aqueous = np.where(theta > 0.0, aqueous, np.nan)
    sorbed = np.where(area > 0.0, sorbed, np.nan)
    return {"aqueous": aqueous, "sorbed": sorbed}


def panel_label(ax: plt.Axes, label: str, color: str = "white") -> None:
    ax.text(
        0.015,
        0.95,
        label,
        transform=ax.transAxes,
        va="top",
        ha="left",
        color=color,
        weight="bold",
        fontsize=10,
        bbox={"facecolor": "black", "edgecolor": "none", "alpha": 0.55, "pad": 2.2},
    )


def save_figure(fig: plt.Figure, stem: Path) -> None:
    stem.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(stem.with_suffix(".png"), dpi=360, bbox_inches="tight")
    fig.savefig(stem.with_suffix(".pdf"), bbox_inches="tight")
    plt.close(fig)


def plot_pe1_fields(args: argparse.Namespace) -> dict[str, object]:
    field_stem = getattr(args, "field_stem", "paper_pe1_resolved_vs_dbs_fields")
    resolved = load_native_fields(args.pe1_resolved, args.pe1_resolved_time, resolved=True)
    dbs = load_native_fields(args.pe1_dbs, args.pe1_dbs_time, resolved=False)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        args.output_dir / f"{field_stem}_native_fields.npz",
        resolved_aqueous=resolved["aqueous"],
        dbs_aqueous=dbs["aqueous"],
        resolved_sorbed=resolved["sorbed"],
        dbs_sorbed=dbs["sorbed"],
    )

    positive = np.concatenate(
        [
            field[np.isfinite(field) & (field > 0)]
            for field in (resolved["sorbed"], dbs["sorbed"])
        ]
    )
    sor_min = float(np.percentile(positive, 1.0))
    sor_max = float(np.percentile(positive, 99.9))
    log_min, log_max = np.log10([sor_min, sor_max])

    fig, axes = plt.subplots(
        2,
        4,
        figsize=(10.8, 4.5),
        constrained_layout=True,
        gridspec_kw={"width_ratios": [1.5, 0.65, 1.5, 0.65]},
    )
    aqueous_cmap = plt.get_cmap("viridis").copy()
    aqueous_cmap.set_bad("#d9d9d9")
    sorbed_cmap = plt.get_cmap("magma").copy()
    sorbed_cmap.set_bad("white")
    aqueous_image = None
    sorbed_image = None
    zoom_center_x = LENGTH_MM * args.transits
    zoom_extent = (zoom_center_x - 1.0, zoom_center_x + 1.0, 2.0, 4.0)
    zoom_xticks = [float(np.floor(zoom_center_x)), float(np.ceil(zoom_center_x))]
    for full_column, zoom_column, title, fields in (
        (0, 1, "Fully resolved", resolved),
        (2, 3, "DBS-upscaled", dbs),
    ):
        aqueous_image = axes[0, full_column].imshow(
            fields["aqueous"],
            origin="lower",
            extent=EXTENT_MM,
            cmap=aqueous_cmap,
            vmin=0.0,
            vmax=1.0,
            interpolation="nearest",
            aspect="equal",
        )
        sorbed_log = np.full(fields["sorbed"].shape, np.nan, dtype=np.float32)
        np.log10(fields["sorbed"], out=sorbed_log, where=fields["sorbed"] > 0)
        sorbed_image = axes[1, full_column].imshow(
            sorbed_log,
            origin="lower",
            extent=EXTENT_MM,
            cmap=sorbed_cmap,
            vmin=log_min,
            vmax=log_max,
            interpolation="nearest",
            aspect="equal",
        )
        axes[0, full_column].set_title(title, weight="semibold")
        axes[1, full_column].set_xlabel("x [mm]")
        axes[0, zoom_column].imshow(
            fields["aqueous"], origin="lower", extent=EXTENT_MM,
            cmap=aqueous_cmap, vmin=0.0, vmax=1.0,
            interpolation="nearest", aspect="equal",
        )
        axes[1, zoom_column].imshow(
            sorbed_log, origin="lower", extent=EXTENT_MM,
            cmap=sorbed_cmap, vmin=log_min, vmax=log_max,
            interpolation="nearest", aspect="equal",
        )
        axes[0, zoom_column].set_title("Native-grid zoom", fontsize=8.5)
        axes[1, zoom_column].set_xlabel("x [mm]")
        for row in range(2):
            axes[row, zoom_column].set_xlim(zoom_extent[0], zoom_extent[1])
            axes[row, zoom_column].set_ylim(zoom_extent[2], zoom_extent[3])
            axes[row, zoom_column].set_xticks(zoom_xticks)
            axes[row, zoom_column].set_yticks([2, 3, 4])
        for row in range(2):
            axes[row, full_column].set_xlim(0, 18)
            axes[row, full_column].set_ylim(0, 6)
            axes[row, full_column].set_xticks([0, 3, 6, 9, 12, 15, 18])
            axes[row, full_column].set_yticks([0, 2, 4, 6])
            if full_column == 0:
                axes[row, full_column].set_ylabel("y [mm]")
            else:
                axes[row, full_column].tick_params(labelleft=False)
            axes[row, zoom_column].tick_params(labelleft=False)
        axes[0, full_column].tick_params(labelbottom=False)
        axes[0, zoom_column].tick_params(labelbottom=False)

    panel_label(axes[0, 0], "a")
    panel_label(axes[0, 2], "b")
    panel_label(axes[1, 0], "c")
    panel_label(axes[1, 2], "d")
    if aqueous_image is None or sorbed_image is None:
        raise RuntimeError("No field images were created")
    aq_bar = fig.colorbar(aqueous_image, ax=axes[0, :], location="right", shrink=0.88, pad=0.015)
    aq_bar.set_label("Aqueous Li / inlet Li")
    sor_bar = fig.colorbar(sorbed_image, ax=axes[1, :], location="right", shrink=0.88, pad=0.015)
    sor_bar.set_label(r"log$_{10}$(sorbed Li [mol m$^{-2}$])")
    fig.suptitle(
        rf"Lithium transport at Pe = 1 and $x/L = {args.transits:g}$",
        weight="semibold",
    )
    save_figure(fig, args.output_dir / field_stem)

    return {
        "resolved_case_dir": str(args.pe1_resolved),
        "dbs_case_dir": str(args.pe1_dbs),
        "resolved_time_s": float(args.pe1_resolved_time),
        "dbs_time_s": float(args.pe1_dbs_time),
        "normalized_advective_distance_x_over_L": float(args.transits),
        "source_cell_size_um": 5.0,
        "display_block_cells": [1, 1],
        "display_uses_native_grid": True,
        "resolved_grains_are_masked_not_averaged": True,
        "sorbed_li_shared_scale_mol_m-2": [sor_min, sor_max],
    }


def parse_metric_spec(spec: str) -> tuple[float, Path]:
    try:
        pe_text, path_text = spec.split("=", 1)
        return float(pe_text), Path(path_text)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("Metric specs must be PE=PATH") from exc


def plot_error_summary(
    metric_specs: list[str],
    output_dir: Path,
    transits: float,
    limits: dict[str, float],
) -> list[dict[str, float]]:
    records: list[dict[str, float]] = []
    for spec in metric_specs:
        pe, path = parse_metric_spec(spec)
        metrics = json.loads(path.read_text())["dbs_vs_resolved"]
        records.append(
            {
                "pe": pe,
                "aqueous_inventory_percent": 100.0
                * metrics["aqueous_li_inventory_density_relative_difference"],
                "sorbed_inventory_percent": 100.0
                * metrics["sorbed_li_inventory_density_relative_difference"],
                "aqueous_profile_l1_percent": 100.0
                * metrics["aqueous_li_profile_normalized_l1_100_bins"],
                "sorbed_profile_l1_percent": 100.0
                * metrics["sorbed_li_profile_normalized_l1_100_bins"],
                "aqueous_map_dissimilarity": 1.0 - metrics["aqueous_li_macro_map_cosine"],
                "sorbed_map_dissimilarity": 1.0 - metrics["sorbed_li_macro_map_cosine"],
            }
        )
    records.sort(key=lambda row: row["pe"])
    if not records:
        raise ValueError("At least one metric file is required")
    pe = np.array([row["pe"] for row in records])

    aqueous_color = "#0072B2"
    sorbed_color = "#CC79A7"
    fig, axes = plt.subplots(1, 3, figsize=(7.5, 2.65), constrained_layout=True)
    series = (
        ("aqueous_inventory_percent", "sorbed_inventory_percent"),
        ("aqueous_profile_l1_percent", "sorbed_profile_l1_percent"),
        ("aqueous_map_dissimilarity", "sorbed_map_dissimilarity"),
    )
    for ax, (aq_key, sor_key) in zip(axes, series):
        ax.plot(pe, [row[aq_key] for row in records], "o-", color=aqueous_color, label="Aqueous Li")
        ax.plot(pe, [row[sor_key] for row in records], "s-", color=sorbed_color, label="Sorbed Li")
        ax.set_xscale("log")
        ax.set_xticks(pe)
        ax.xaxis.set_major_formatter(FuncFormatter(lambda value, _: f"{value:g}"))
        ax.grid(True, which="major", color="#d9d9d9", linewidth=0.7)
        ax.set_xlabel("Péclet number")

    inventory_limit = limits["inventory_percent_absolute"]
    profile_limit = limits["profile_l1_percent"]
    map_limit = limits["map_dissimilarity"]
    axes[0].axhspan(
        -inventory_limit, inventory_limit, color="#009E73", alpha=0.10, zorder=-2
    )
    axes[0].axhline(0, color="#555555", linewidth=0.8)
    axes[0].set_ylabel("Inventory difference [%]")
    axes[0].set_title("a   Integrated inventory", loc="left", weight="semibold")

    axes[1].axhspan(0, profile_limit, color="#009E73", alpha=0.10, zorder=-2)
    axes[1].set_ylim(bottom=0)
    axes[1].set_ylabel("Normalized profile L1 [%]")
    axes[1].set_title("b   Streamwise placement", loc="left", weight="semibold")

    axes[2].axhspan(1.0e-8, map_limit, color="#009E73", alpha=0.10, zorder=-2)
    axes[2].axhline(map_limit, color="#009E73", linestyle="--", linewidth=0.9)
    axes[2].set_yscale("log")
    axes[2].set_ylabel("Map error (1 − cosine)", labelpad=3)
    axes[2].set_title("c   Spatial overlap", loc="left", weight="semibold")
    axes[0].legend(frameon=False, loc="best")
    fig.suptitle(
        rf"DBS error at $x/L={transits:g}$ relative to fully resolved",
        weight="semibold",
        fontsize=10.5,
    )
    save_figure(fig, output_dir / "paper_error_vs_peclet")

    output_dir.mkdir(parents=True, exist_ok=True)
    with (output_dir / "paper_error_vs_peclet.csv").open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(records[0]))
        writer.writeheader()
        writer.writerows(records)
    return records


def assert_acceptance(
    records: list[dict[str, float]], scientific_limits: dict[str, float]
) -> None:
    limits = {
        "aqueous_inventory_percent": scientific_limits["inventory_percent_absolute"],
        "sorbed_inventory_percent": scientific_limits["inventory_percent_absolute"],
        "aqueous_profile_l1_percent": scientific_limits["profile_l1_percent"],
        "sorbed_profile_l1_percent": scientific_limits["profile_l1_percent"],
        "aqueous_map_dissimilarity": scientific_limits["map_dissimilarity"],
        "sorbed_map_dissimilarity": scientific_limits["map_dissimilarity"],
    }
    failures = []
    for record in records:
        for key, limit in limits.items():
            value = abs(record[key]) if "inventory" in key else record[key]
            if not np.isfinite(value) or value > limit:
                failures.append(
                    f"Pe={record['pe']:g} {key}={value:.6g} exceeds {limit:g}"
                )
    if failures:
        raise RuntimeError("PAPER_ACCEPTANCE: FAIL\n- " + "\n- ".join(failures))
    print("PAPER_ACCEPTANCE: PASS")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pe1-resolved", type=Path, required=True)
    parser.add_argument("--pe1-resolved-time", required=True)
    parser.add_argument("--pe1-dbs", type=Path, required=True)
    parser.add_argument("--pe1-dbs-time", required=True)
    parser.add_argument("--metric", action="append", required=True, help="PE=metrics.json")
    parser.add_argument("--transits", type=float, default=0.125)
    parser.add_argument("--metric-transits", type=float, default=0.125)
    parser.add_argument("--acceptance-config", type=Path, required=True)
    parser.add_argument("--field-stem", default="paper_pe1_resolved_vs_dbs_fields")
    parser.add_argument("--assert-acceptance", action="store_true")
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()

    configure_style()
    limits = json.loads(args.acceptance_config.read_text())["acceptance_limits"]
    field_metadata = plot_pe1_fields(args)
    error_records = plot_error_summary(
        args.metric, args.output_dir, args.metric_transits, limits
    )
    if args.assert_acceptance:
        assert_acceptance(error_records, limits)
    summary = {"pe1_field_figure": field_metadata, "error_records": error_records}
    (args.output_dir / "paper_validation_figures.json").write_text(
        json.dumps(summary, indent=2) + "\n"
    )
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
