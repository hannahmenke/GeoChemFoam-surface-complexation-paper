#!/usr/bin/env python3
from __future__ import annotations

import argparse
import math
import re
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("log", type=Path)
    parser.add_argument("--flow-component", choices=("Ux", "Uy", "Uz"), default="Ux")
    parser.add_argument("--max-u-initial-residual", type=float, default=1e-4)
    parser.add_argument("--max-global-continuity", type=float, default=1e-6)
    args = parser.parse_args()

    text = args.log.read_text(errors="replace")
    if re.search(
        r"\bFOAM FATAL|segmentation fault|^\s*floating point exception",
        text,
        re.I | re.M,
    ):
        raise SystemExit(f"Flow solver reported a fatal error in {args.log}")
    if not re.search(r"^\s*End\s*$", text, re.M):
        raise SystemExit(f"Flow solver did not reach End in {args.log}")

    u_residuals = [
        float(value)
        for value in re.findall(
            rf"Solving for {args.flow_component}, Initial residual = ([0-9.eE+-]+)",
            text,
        )
    ]
    continuity = [
        abs(float(value))
        for value in re.findall(
            r"time step continuity errors.*?global = ([0-9.eE+-]+)", text
        )
    ]
    if not u_residuals or not continuity:
        raise SystemExit(f"Could not parse flow convergence metrics from {args.log}")

    final_u = u_residuals[-1]
    final_continuity = continuity[-1]
    if not math.isfinite(final_u) or final_u > args.max_u_initial_residual:
        raise SystemExit(
            f"Flow velocity is not converged: final max initial residual "
            f"{final_u:.6g} > {args.max_u_initial_residual:.6g}"
        )
    if (
        not math.isfinite(final_continuity)
        or final_continuity > args.max_global_continuity
    ):
        raise SystemExit(
            f"Flow continuity is not converged: final global error "
            f"{final_continuity:.6g} > {args.max_global_continuity:.6g}"
        )

    print(
        f"Flow convergence passed: final {args.flow_component} initial residual={final_u:.6g}, "
        f"final global continuity={final_continuity:.6g}"
    )


if __name__ == "__main__":
    main()
