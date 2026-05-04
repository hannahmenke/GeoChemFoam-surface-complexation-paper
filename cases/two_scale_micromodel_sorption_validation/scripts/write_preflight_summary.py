#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import sys
from pathlib import Path


def fmt(value: float, digits: int = 6) -> str:
    if not math.isfinite(value):
        return "nan"
    return f"{value:.{digits}g}"


def main() -> None:
    if len(sys.argv) not in (5, 6):
        raise SystemExit(
            "Usage: write_preflight_summary.py METADATA MATCHED_PE_JSON OUT_MD WRITE_INTERVAL [TIMESTEP]"
        )

    metadata = json.loads(Path(sys.argv[1]).read_text())
    matched = json.loads(Path(sys.argv[2]).read_text())
    out_path = Path(sys.argv[3])
    write_interval = float(sys.argv[4])
    timestep = float(sys.argv[5]) if len(sys.argv) == 6 else math.nan

    resolved_size = metadata["resolved_full_reference"]["physical_size_m"]
    dbs_size = metadata["dbs_full_upscaled"]["physical_size_m"]
    same_xy = all(abs(resolved_size[i] - dbs_size[i]) < 1e-12 for i in (0, 1))
    target_pe = float(matched["target_pe"])
    rt_time = float(matched["recommended_reactive_transport_time_s"])
    front_fraction = float(matched["target_front_fraction"])

    lines = [
        "# Two-scale sorption preflight",
        "",
        f"- Target Pe: `{fmt(target_pe)}`",
        f"- Pe definition: `{matched['pe_definition']['formula']}`",
        f"- Domain length: `{fmt(matched['domain_length_m'])} m`",
        f"- Target front position: `{fmt(front_fraction)} L`",
        f"- Recommended reactive-transport time: `{fmt(rt_time)} s`",
        f"- Reactive-transport write interval: `{fmt(write_interval)} s`",
        f"- Reactive-transport timestep: `{fmt(timestep)} s`",
        f"- Geometry xy sizes match: `{'yes' if same_xy else 'no'}`",
        f"- Resolved physical size: `{resolved_size[0]} x {resolved_size[1]} m`",
        f"- DBS physical size: `{dbs_size[0]} x {dbs_size[1]} m`",
        "",
        "| Case | Pe check | Darcy velocity (m/s) | Pore velocity (m/s) | Flow rate (m3/s) | t to front (s) | x/L at run end |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]

    checks_ok = same_xy
    for name, case in matched["cases"].items():
        pe_check = float(case["target_pe_check"])
        front_time = float(case["advective_time_to_target_front_s"])
        x_over_l = front_fraction * rt_time / front_time
        checks_ok = checks_ok and abs(pe_check - target_pe) <= max(1e-6, 1e-6 * target_pe)
        lines.append(
            "| "
            + " | ".join(
                [
                    name,
                    fmt(pe_check),
                    fmt(float(case["target_darcy_velocity_m_per_s"])),
                    fmt(float(case["target_pore_velocity_m_per_s"])),
                    fmt(float(case["target_flow_rate_m3_per_s"])),
                    fmt(front_time),
                    fmt(x_over_l),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            f"Preflight status: `{'pass' if checks_ok else 'check required'}`",
            "",
        ]
    )
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text("\n".join(lines))
    print("\n".join(lines))


if __name__ == "__main__":
    main()
