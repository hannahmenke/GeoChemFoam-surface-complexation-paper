#!/usr/bin/env python3

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from PIL import Image

from generate_estaillades_temporal_plot import (
    available_times,
    read_weighted_domain_mean,
)


def compute_temporal_data(case_dir: Path, max_workers: int) -> dict[str, np.ndarray]:
    times = available_times(case_dir)

    ca_means: list[float] = []
    sr_means: list[float] = []
    surf_ca_means: list[float] = []
    surf_sr_means: list[float] = []

    for time_value in times:
        time_name = str(int(time_value)) if time_value == int(time_value) else str(time_value)
        ca_means.append(
            read_weighted_domain_mean(
                case_dir, time_name, "Ca+2", "eps", max_workers
            )
        )
        sr_means.append(
            read_weighted_domain_mean(
                case_dir, time_name, "Sr+2", "eps", max_workers
            )
        )
        surf_ca_means.append(
            read_weighted_domain_mean(
                case_dir, time_name, "Surf_aCa+", "aSurf", max_workers
            )
        )
        surf_sr_means.append(
            read_weighted_domain_mean(
                case_dir, time_name, "Surf_aSr+", "aSurf", max_workers
            )
        )

    time_array = np.array(times)
    ca_norm = np.array(ca_means) / 1.0e-3
    sr_norm = np.array(sr_means) / 1.0e-4

    surf_ca = np.array(surf_ca_means)
    surf_sr = np.array(surf_sr_means)
    surf_ca_delta = surf_ca - surf_ca[0]
    surf_sr_delta = surf_sr - surf_sr[0]
    surf_scale = max(np.max(np.abs(surf_ca_delta)), np.max(np.abs(surf_sr_delta)), 1.0e-40)
    surf_ca_norm = surf_ca_delta / surf_scale
    surf_sr_norm = surf_sr_delta / surf_scale

    return {
        "times": time_array,
        "ca_norm": ca_norm,
        "sr_norm": sr_norm,
        "surf_ca_norm": surf_ca_norm,
        "surf_sr_norm": surf_sr_norm,
    }


def render_temporal_panel(data: dict[str, np.ndarray], current_time: float, output_path: Path) -> None:
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 8.0), dpi=200)

    times = data["times"]
    upto = times <= current_time + 1.0e-12
    times_upto = times[upto]
    x_left = float(times[0])
    x_right = float(times[-1]) if float(times[-1]) > x_left else x_left + 1.0

    ax1 = axes[0]
    ax1.plot(
        times_upto,
        data["ca_norm"][upto],
        color="#0b4f6c",
        linewidth=2.0,
        marker="o",
        markersize=4.0,
        label="Ca$^{2+}$ / $C_{\\mathrm{init}}$",
    )
    ax1.plot(
        times_upto,
        data["sr_norm"][upto],
        color="#c0392b",
        linewidth=2.0,
        marker="^",
        markersize=4.0,
        label="Sr$^{2+}$ / $C_{\\mathrm{in}}$",
    )
    ax1.axvline(current_time, color="#333333", linewidth=1.3, alpha=0.7)
    ax1.scatter(
        [current_time],
        [np.interp(current_time, times, data["sr_norm"])],
        color="#c0392b",
        s=36,
        zorder=5,
    )
    ax1.scatter(
        [current_time],
        [np.interp(current_time, times, data["ca_norm"])],
        color="#0b4f6c",
        s=36,
        zorder=5,
    )
    ax1.set_xlabel("Time [s]")
    ax1.set_ylabel("Domain-mean dissolved concentration")
    ax1.set_ylim(bottom=0.0)
    ax1.set_xlim(left=x_left, right=x_right)
    ax1.set_title("Dissolved species")
    ax1.grid(True, alpha=0.25)
    ax1.legend(fontsize=9, loc="best")

    ax2 = axes[1]
    ax2.plot(
        times_upto,
        data["surf_ca_norm"][upto],
        color="#0b4f6c",
        linewidth=2.0,
        marker="o",
        markersize=4.0,
        label="$\\Delta$Surf$_a$Ca$^+$",
    )
    ax2.plot(
        times_upto,
        data["surf_sr_norm"][upto],
        color="#c0392b",
        linewidth=2.0,
        marker="^",
        markersize=4.0,
        label="$\\Delta$Surf$_a$Sr$^+$",
    )
    ax2.axhline(0.0, color="#666666", linewidth=0.8, alpha=0.6)
    ax2.axvline(current_time, color="#333333", linewidth=1.3, alpha=0.7)
    ax2.scatter(
        [current_time],
        [np.interp(current_time, times, data["surf_ca_norm"])],
        color="#0b4f6c",
        s=36,
        zorder=5,
    )
    ax2.scatter(
        [current_time],
        [np.interp(current_time, times, data["surf_sr_norm"])],
        color="#c0392b",
        s=36,
        zorder=5,
    )
    ax2.set_xlabel("Time [s]")
    ax2.set_ylabel("Normalised domain-mean $\\Delta$Surf loading")
    ax2.set_xlim(left=x_left, right=x_right)
    ax2.set_title("Surface exchange")
    ax2.grid(True, alpha=0.25)
    ax2.legend(fontsize=9, loc="best")

    fig.text(0.01, 0.985, "(a)", ha="left", va="top", fontsize=18)
    fig.tight_layout(rect=(0.02, 0.02, 0.98, 0.97))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_path, dpi=200, facecolor="white")
    plt.close(fig)


def compose_frame(base_png: Path, panel_png: Path, output_png: Path) -> None:
    base = Image.open(base_png).convert("RGBA")
    panel = Image.open(panel_png).convert("RGBA")

    panel = panel.resize((1600, 1600), Image.Resampling.LANCZOS)
    base.paste(panel, (0, 0))
    base.save(output_png)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Render the Estaillades 3D figure style at all saved times into a new folder with the temporal plot replacing panel (a)."
    )
    parser.add_argument("--repo-root", type=Path, required=True)
    parser.add_argument("--max-workers", type=int, default=8)
    args = parser.parse_args()

    repo_root = args.repo_root.resolve()
    script_dir = repo_root / "papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts"
    render_wrapper = script_dir / "render_3d_volume_pyvista_egl.sh"
    case_dir = (
        repo_root
        / "papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_estaillades"
    )
    output_dir = (
        repo_root
        / "papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig04_3d_estaillades_timeseries"
    )
    base_dir = output_dir / "_base"
    panel_dir = output_dir / "_panel_a"
    output_dir.mkdir(parents=True, exist_ok=True)
    base_dir.mkdir(parents=True, exist_ok=True)
    panel_dir.mkdir(parents=True, exist_ok=True)

    temporal_data = compute_temporal_data(case_dir, args.max_workers)
    time_dirs = [str(int(t)) if float(t).is_integer() else str(t) for t in temporal_data["times"]]

    for time_name in time_dirs:
        time_value = float(time_name)
        base_png = base_dir / f"fig04_3d_estaillades_t{int(time_value):03d}_base.png"
        panel_png = panel_dir / f"fig04_3d_estaillades_t{int(time_value):03d}_panel_a.png"
        output_png = output_dir / f"fig04_3d_estaillades_t{int(time_value):03d}.png"

        cmd = [
            str(render_wrapper),
            "--case-dir",
            str(case_dir),
            "--time-name",
            time_name,
            "--aqueous-field",
            "Sr+2",
            "--aqueous-scale",
            "1e-4",
            "--aqueous-mask-to-pore",
            "--aqueous-cmap",
            "yellow_fade",
            "--aqueous-title",
            "Sr+2 / C_in",
            "--aqueous-no-shade",
            "--aqueous-opacity-profile",
            "soft",
            "--second-aqueous-field",
            "Ca+2",
            "--second-aqueous-scale",
            "1e-3",
            "--second-aqueous-title",
            "Ca+2 / C_init",
            "--second-aqueous-cmap",
            "soft_blues",
            "--second-aqueous-no-shade",
            "--surface-field",
            "Surf_aSr+",
            "--surface-floor",
            "1e-18",
            "--surface-log-scale",
            "--surface-title",
            "Surf_aSr+",
            "--output",
            str(base_png),
        ]
        subprocess.run(cmd, check=True)

        render_temporal_panel(temporal_data, time_value, panel_png)
        compose_frame(base_png, panel_png, output_png)


if __name__ == "__main__":
    main()
