#!/usr/bin/env python3

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch


ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "png" / "fig05_solver_workflow.png"


def add_box(ax, xy, width, height, text, *, fc, ec="#1f1f1f", fontsize=11):
    x, y = xy
    patch = FancyBboxPatch(
        (x, y),
        width,
        height,
        boxstyle="round,pad=0.01,rounding_size=0.03",
        linewidth=1.4,
        facecolor=fc,
        edgecolor=ec,
    )
    ax.add_patch(patch)
    ax.text(
        x + width / 2.0,
        y + height / 2.0,
        text,
        ha="center",
        va="center",
        fontsize=fontsize,
        color="#111111",
        wrap=True,
    )
    return patch


def add_arrow(
    ax,
    start,
    end,
    *,
    text=None,
    text_offset=(0.0, 0.0),
    arrowstyle="-|>",
):
    arrow = FancyArrowPatch(
        start,
        end,
        arrowstyle=arrowstyle,
        mutation_scale=14,
        linewidth=1.4,
        color="#2b2b2b",
        shrinkA=4,
        shrinkB=4,
    )
    ax.add_patch(arrow)
    if text:
        mx = 0.5 * (start[0] + end[0]) + text_offset[0]
        my = 0.5 * (start[1] + end[1]) + text_offset[1]
        ax.text(mx, my, text, ha="center", va="center", fontsize=10, color="#222222")


def main() -> None:
    fig = plt.figure(figsize=(12.4, 10.0), dpi=220)
    ax = fig.add_axes([0.03, 0.03, 0.94, 0.94])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")

    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    ax.text(
        0.5,
        0.985,
        "Full Solution Procedure For reactiveScalarTransportDBSFoam",
        ha="center",
        va="top",
        fontsize=16,
        fontweight="bold",
        color="#111111",
    )

    left_x = 0.04
    mid_x = 0.375
    right_x = 0.71
    box_w = 0.24
    box_h = 0.112

    b0 = add_box(
        ax,
        (mid_x, 0.79),
        box_w,
        box_h,
        "Read case, mesh, fields\n$\\theta$, $\\epsilon_{num}$, $a_{surf}$,\n$\\phi$, aqueous and surface states",
        fc="#d9e8fb",
        fontsize=10,
    )
    b1 = add_box(
        ax,
        (mid_x, 0.63),
        box_w,
        box_h,
        "Initialise phreeqcDBSMixture\nLoad database, map components,\nset porosity and surface mode",
        fc="#d9e8fb",
        fontsize=10,
    )
    b2 = add_box(
        ax,
        (mid_x, 0.455),
        box_w,
        0.075,
        "Start timestep loop\n(current time < end time)",
        fc="#e8e8e8",
        fontsize=10,
    )
    b3 = add_box(
        ax,
        (left_x, 0.275),
        box_w,
        0.125,
        "Conservative DBS transport\nSolve each aqueous species in\nmobile-water form:\n$\\partial_t(\\theta C_i)+\\nabla\\!\\cdot(\\phi C_i)-$\n$\\nabla\\!\\cdot(\\theta D_i\\nabla C_i)=0$",
        fc="#dff3df",
        fontsize=9,
    )
    b4 = add_box(
        ax,
        (mid_x, 0.275),
        box_w,
        0.125,
        "Assemble chemistry state\nPush updated aqueous fields,\n$\\theta$, and $a_{surf}$ into\nphreeqcDBSMixture",
        fc="#fff1cc",
        fontsize=9,
    )
    b5 = add_box(
        ax,
        (right_x, 0.275),
        box_w,
        0.125,
        "Local PHREEQC reaction step\nRun cellwise chemistry and\nsurface complexation for\nactive cells",
        fc="#ffd9cc",
        fontsize=9,
    )
    b6 = add_box(
        ax,
        (mid_x, 0.14),
        box_w,
        0.10,
        "Pull back updated state\nAqueous species, surface species,\nionic strength, $\\psi$,\nand inventory diagnostics",
        fc="#fff1cc",
        fontsize=9,
    )
    b7 = add_box(
        ax,
        (mid_x, 0.02),
        box_w,
        0.065,
        "Write fields and diagnostics\nAdvance time and repeat",
        fc="#e8e8e8",
        fontsize=10,
    )

    note1 = add_box(
        ax,
        (0.045, 0.645),
        0.255,
        0.115,
        "Cell-centred chemistry state:\n$C_i$, $\\theta$, $\\epsilon_{num}$,\n$a_{surf}$, Surf_*",
        fc="#f7f7f7",
        fontsize=9,
    )
    note2 = add_box(
        ax,
        (0.70, 0.645),
        0.255,
        0.115,
        "Operator split used here:\ntransport first, then local\nPHREEQC chemistry (Lie split)",
        fc="#f7f7f7",
        fontsize=9,
    )

    add_arrow(ax, (0.495, 0.79), (0.495, 0.742))
    add_arrow(ax, (0.495, 0.63), (0.495, 0.582))
    add_arrow(ax, (0.495, 0.455), (0.16, 0.385))
    add_arrow(ax, (0.28, 0.337), (0.375, 0.337))
    add_arrow(ax, (0.615, 0.337), (0.71, 0.337))
    add_arrow(ax, (0.83, 0.275), (0.57, 0.19))
    add_arrow(ax, (0.495, 0.14), (0.495, 0.095))

    loop_x = 0.665
    add_arrow(ax, (0.615, 0.05), (loop_x, 0.05), arrowstyle="-")
    add_arrow(ax, (loop_x, 0.05), (loop_x, 0.492), arrowstyle="-")
    add_arrow(ax, (loop_x, 0.492), (0.615, 0.492))

    add_arrow(ax, (0.30, 0.705), (0.375, 0.685))
    add_arrow(ax, (0.70, 0.705), (0.615, 0.685))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=220, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
