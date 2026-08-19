#!/usr/bin/env python3
"""Generate the solver-workflow figure for the paper."""

from __future__ import annotations

from pathlib import Path

import matplotlib.pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parents[1]
OUT  = ROOT / "png" / "fig05_solver_workflow.png"


def add_box(ax, xy, width, height, text, *, fc, ec="#1f1f1f", fontsize=11):
    x, y = xy
    ax.add_patch(FancyBboxPatch(
        (x, y), width, height,
        boxstyle="round,pad=0.01,rounding_size=0.03",
        linewidth=1.4, facecolor=fc, edgecolor=ec,
    ))
    ax.text(
        x + width / 2, y + height / 2, text,
        ha="center", va="center", fontsize=fontsize,
        color="#111111", wrap=True,
    )


def add_arrow(ax, start, end, *,
              arrowstyle="-|>", shrinkA=4, shrinkB=4,
              text=None, text_xy=None):
    ax.add_patch(FancyArrowPatch(
        start, end,
        arrowstyle=arrowstyle, mutation_scale=14,
        linewidth=1.4, color="#2b2b2b",
        shrinkA=shrinkA, shrinkB=shrinkB,
    ))
    if text and text_xy:
        ax.text(*text_xy, text,
                ha="center", va="center", fontsize=9, color="#444444")


def add_elbow(ax, start, corner, end, *, shrinkB=4):
    """L-shaped connector: plain line from start→corner, arrow corner→end."""
    ax.plot(
        [start[0], corner[0]], [start[1], corner[1]],
        color="#2b2b2b", linewidth=1.4, solid_capstyle="round", zorder=5,
    )
    add_arrow(ax, corner, end, shrinkA=0, shrinkB=shrinkB)


def main() -> None:
    fig = plt.figure(figsize=(12.4, 10.0), dpi=220)
    ax  = fig.add_axes([0.03, 0.03, 0.94, 0.94])
    ax.set_xlim(0, 1)
    ax.set_ylim(0, 1)
    ax.axis("off")
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")

    # ── layout constants ───────────────────────────────────────────────────────
    mid_x   = 0.375
    left_x  = 0.04
    right_x = 0.71
    w       = 0.24    # box width (all boxes share the same width)
    cx      = mid_x + w / 2   # x-centre of the middle column  (= 0.495)

    # ── initialisation blocks ─────────────────────────────────────────────────
    #  b0 – read case
    b0_y = 0.855; b0_h = 0.11
    add_box(ax, (mid_x, b0_y), w, b0_h,
            "Read case, mesh, fields\n"
            r"$\varepsilon$, $a_{\mathrm{surf}}$," + "\n"
            r"$\phi$, aqueous and surface states",
            fc="#d9e8fb", fontsize=10)

    #  b1 – initialise PHREEQC
    b1_y = 0.685; b1_h = 0.11
    add_box(ax, (mid_x, b1_y), w, b1_h,
            "Initialise phreeqcMixture\n"
            "Load database, map components,\n"
            "set porosity and surface mode",
            fc="#d9e8fb", fontsize=10)

    add_arrow(ax, (cx, b0_y), (cx, b1_y + b1_h))   # b0 bottom → b1 top

    # ── timestep loop control ─────────────────────────────────────────────────
    b2_y = 0.535; b2_h = 0.075

    add_arrow(ax, (cx, b1_y), (cx, b2_y + b2_h))   # b1 bottom → b2 top
    add_box(ax, (mid_x, b2_y), w, b2_h,
            "Start timestep loop\n(current time < end time)",
            fc="#e8e8e8", fontsize=10)

    # ── main loop: three columns ──────────────────────────────────────────────
    h3  = 0.135
    col_y = 0.275

    add_box(ax, (left_x,  col_y), w, h3,
            u"① Conservative DBS\ntransport\n"
            r"$\partial_t(\varepsilon C_i)+\nabla\!\cdot(\phi C_i)$" + "\n"
            r"$-\nabla\!\cdot(\varepsilon D_i\nabla C_i)=0$",
            fc="#dff3df", fontsize=9)

    add_box(ax, (mid_x,   col_y), w, h3,
            u"② Assemble chemistry state\n"
            r"Push updated aqueous fields," + "\n"
            r"$\varepsilon$ and $a_{\mathrm{surf}}$ into" + "\n"
            "phreeqcMixture",
            fc="#fff1cc", fontsize=9)

    add_box(ax, (right_x, col_y), w, h3,
            u"③ Local PHREEQC step\n"
            "Cellwise equilibrium chemistry\n"
            "and surface complexation\n"
            "(OpenMP parallel)",
            fc="#ffd9cc", fontsize=9)

    col_cy = col_y + h3 / 2   # vertical centre of the three boxes

    # loop entry: b2 bottom → ① top (diagonal)
    add_arrow(ax, (cx, b2_y), (left_x + w / 2, col_y + h3))

    # ① → ②  and  ② → ③
    add_arrow(ax, (left_x + w, col_cy), (mid_x,   col_cy))
    add_arrow(ax, (mid_x  + w, col_cy), (right_x, col_cy))

    # ── ③ → ④ : L-shaped (straight down, then left) ───────────────────────────
    b5_bot   = (right_x + w / 2, col_y)          # ③ bottom centre
    b6_y     = 0.125; b6_h = 0.115
    b6_cy    = b6_y + b6_h / 2                   # ④ vertical centre  (= 0.1825)
    b6_right = (mid_x + w, b6_cy)                # ④ right edge at that height
    corner   = (b5_bot[0], b6_cy)                # turn point

    add_elbow(ax, b5_bot, corner, b6_right)

    # ── pull-back box ─────────────────────────────────────────────────────────
    add_box(ax, (mid_x, b6_y), w, b6_h,
            u"④ Pull back updated state\n"
            "Aqueous species, surface species,\n"
            "and ionic strength",
            fc="#fff1cc", fontsize=9)

    # ── write / advance box ───────────────────────────────────────────────────
    b7_y = 0.018; b7_h = 0.072
    add_box(ax, (mid_x, b7_y), w, b7_h,
            u"⑤ Write fields and PHREEQC checkpoints\n"
            "Advance time and repeat",
            fc="#e8e8e8", fontsize=10)

    add_arrow(ax, (cx, b6_y), (cx, b7_y + b7_h))   # ④ → ⑤

    # ── loop-back arrow ───────────────────────────────────────────────────────
    lx         = 0.668
    b7_right_y = b7_y + b7_h / 2      # = 0.054
    b2_right_y = b2_y + b2_h / 2      # = 0.5275

    ax.plot([mid_x + w, lx], [b7_right_y, b7_right_y],
            color="#2b2b2b", linewidth=1.4)
    ax.plot([lx, lx], [b7_right_y, b2_right_y],
            color="#2b2b2b", linewidth=1.4)
    add_arrow(ax, (lx, b2_right_y), (mid_x + w, b2_right_y))

    # label placed in the clear gap between b2 bottom and the three-column tops
    ax.text(lx + 0.013, 0.44, r"next $\Delta t$",
            ha="left", va="center", fontsize=9, color="#444444")

    # ── save ──────────────────────────────────────────────────────────────────
    OUT.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT, dpi=220, facecolor="white")
    plt.close(fig)


if __name__ == "__main__":
    main()
