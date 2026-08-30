#!/usr/bin/env python3
"""Generate the source-traced solver-workflow figure for the paper.

The sequence is traced against GeoChemFoam upstream/main commit ae6026e3 using
reactiveTransportDBSFoam.C, createFields.H, YiEqn.H, and phreeqcMixture.C.
YiEqn.H advances every aqueous species and then calls
phreeqcMixture::correct(), which owns the field-to-module transfer,
runCells(), and module-to-field transfer.
"""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "png" / "fig05_solver_workflow.png"
INK = "#292929"


def add_box(ax, xy, width, height, text, *, fc, fontsize=15.0):
    """Draw a process box above the connectors."""
    x, y = xy
    ax.add_patch(
        FancyBboxPatch(
            (x, y), width, height,
            boxstyle="round,pad=0.008,rounding_size=0.018",
            linewidth=1.7, facecolor=fc, edgecolor=INK, zorder=3,
        )
    )
    ax.text(
        x + width / 2, y + height / 2, text,
        ha="center", va="center", fontsize=fontsize, color="#111111",
        linespacing=1.18, zorder=4,
    )


def add_arrow(ax, start, end, *, shrink_a=1, shrink_b=2):
    ax.add_patch(
        FancyArrowPatch(
            start, end, arrowstyle="-|>", mutation_scale=17,
        linewidth=1.7, color=INK, shrinkA=shrink_a,
            shrinkB=shrink_b, zorder=2,
        )
    )


def add_route(ax, points):
    """Draw an orthogonal route, with an arrowhead on its final segment."""
    for start, end in zip(points[:-2], points[1:-1]):
        ax.plot(
            [start[0], end[0]], [start[1], end[1]],
            color=INK, linewidth=1.7, solid_capstyle="round", zorder=1,
        )
    add_arrow(ax, points[-2], points[-1], shrink_a=0, shrink_b=2)


def main() -> None:
    # The 8-inch source prints at 4.02 inches. The 14-pt minimum source label
    # therefore remains at least 7 pt in the manuscript.
    fig = plt.figure(figsize=(8.0, 7.0), dpi=300)
    ax = fig.add_axes([0.025, 0.025, 0.95, 0.95])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # Initialisation: OpenFOAM state is read before the runtime-selected
    # mixture constructs and initialises/restores its PHREEQCRM state.
    init_y, init_h, init_w = 0.84, 0.12, 0.43
    add_box(
        ax, (0.035, init_y), init_w, init_h,
        "Read OpenFOAM fields\n"
        r"$p$, $\mathbf{U}$, $\varepsilon$, $a_{\mathrm{surf}}$, $\phi$" "\n"
        "Aqueous + surface species",
        fc="#d9e8fb",
    )
    add_box(
        ax, (0.535, init_y), init_w, init_h,
        "Construct phreeqcMixture\n"
        "Map active cells; initialise\n"
        "or restore PHREEQCRM",
        fc="#d9e8fb", fontsize=14.5,
    )
    add_arrow(ax, (0.465, 0.90), (0.535, 0.90))

    # Timestep controller. The entry route uses the clear gutter between rows.
    ctrl_x, ctrl_y, ctrl_w, ctrl_h = 0.31, 0.68, 0.38, 0.09
    add_box(
        ax, (ctrl_x, ctrl_y), ctrl_w, ctrl_h,
        "Advance timestep\n(current time < end time)",
        fc="#e8e8e8", fontsize=14.5,
    )
    add_route(ax, [(0.75, init_y), (0.75, 0.805), (0.50, 0.805), (0.50, 0.77)])

    # Fixed-porosity PHREEQC loop used by the reported cases.
    stage_h, stage_w = 0.18, 0.40
    left_x, right_x = 0.04, 0.56
    upper_y, lower_y = 0.42, 0.18
    add_box(
        ax, (left_x, upper_y), stage_w, stage_h,
        "① Transport aqueous species\n"
        "Conservative DBS update\n"
        r"$\partial_t(\varepsilon C_i)+\nabla\!\cdot(\phi C_i)$" "\n"
        r"$-\nabla\!\cdot(\varepsilon D_i\nabla C_i)=0$",
        fc="#dff3df", fontsize=14.0,
    )
    add_box(
        ax, (right_x, upper_y), stage_w, stage_h,
        "② Prepare PHREEQCRM input\n"
        "Copy states; reread porosity\n"
        "Clip negative aqueous values",
        fc="#fff1cc", fontsize=14.0,
    )
    add_box(
        ax, (right_x, lower_y), stage_w, stage_h,
        "③ PHREEQCRM runCells()\n"
        "Aqueous speciation +\n"
        "surface complexation",
        fc="#ffd9cc", fontsize=14.5,
    )
    add_box(
        ax, (left_x, lower_y), stage_w, stage_h,
        "④ Return PHREEQCRM results\n"
        "Update OpenFOAM\n"
        "aqueous + surface fields",
        fc="#fff1cc", fontsize=14.5,
    )

    add_route(ax, [(0.50, ctrl_y), (0.50, 0.64), (0.24, 0.64), (0.24, 0.60)])
    add_arrow(ax, (left_x + stage_w, upper_y + stage_h / 2),
              (right_x, upper_y + stage_h / 2))
    add_arrow(ax, (right_x + stage_w / 2, upper_y),
              (right_x + stage_w / 2, lower_y + stage_h))
    add_arrow(ax, (right_x, lower_y + stage_h / 2),
              (left_x + stage_w, lower_y + stage_h / 2))

    # Output and loop-back routes stay in dedicated gutters and never cross a
    # process connector.
    out_x, out_y, out_w, out_h = 0.31, 0.015, 0.38, 0.105
    add_box(
        ax, (out_x, out_y), out_w, out_h,
        "⑤ Scheduled output\n"
        "Write fields + complete\n"
        "PHREEQCRM checkpoint",
        fc="#e8e8e8", fontsize=14.0,
    )
    add_route(ax, [(0.24, lower_y), (0.24, 0.145), (0.50, 0.145), (0.50, 0.12)])
    add_route(
        ax,
        [(0.50, out_y), (0.50, 0.002), (0.985, 0.002), (0.985, 0.725), (0.69, 0.725)],
    )
    ax.text(
        0.835, 0.742, r"next $\Delta t$",
        ha="center", va="bottom", fontsize=14.0, color="#444444", zorder=4,
    )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=240, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
