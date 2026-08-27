#!/usr/bin/env python3
"""Validate the completed 2D paper run and emit compact numerical metrics."""

from __future__ import annotations

import argparse
import json
import math
import re
from pathlib import Path


def field_values(path: Path, count: int | None = None) -> list[float]:
    text = path.read_text()
    uniform = re.search(r"internalField\s+uniform\s+([0-9.eE+\-]+)\s*;", text)
    if uniform:
        if count is None:
            raise RuntimeError(f"Cell count required for uniform field {path}")
        return [float(uniform.group(1))] * count
    nonuniform = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not nonuniform:
        raise RuntimeError(f"Unsupported field format: {path}")
    expected = int(nonuniform.group(1))
    values = [float(item) for item in nonuniform.group(2).split()]
    if len(values) != expected or (count is not None and len(values) != count):
        raise RuntimeError(f"Field-size mismatch: {path}")
    return values


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", type=Path, default=Path("."))
    parser.add_argument("--log", type=Path, default=Path("reactiveTransportDBSFoamRT.out"))
    parser.add_argument("--output", type=Path, default=Path("item2_validation_metrics.json"))
    parser.add_argument("--end-time", type=int, default=20000)
    parser.add_argument("--times", nargs="*", default=None)
    args = parser.parse_args()
    case = args.case.resolve()
    if args.times is None:
        args.times = [str(value) for value in range(0, args.end_time + 1, 2000)]
    ranks = sorted(case.glob("processor*"), key=lambda path: int(path.name[9:]))
    if len(ranks) != 8:
        raise SystemExit(f"Expected 8 processor directories, found {len(ranks)}")

    log_path = case / args.log
    if not log_path.is_file():
        raise SystemExit(f"Missing solver log: {log_path}")
    log_text = log_path.read_text()
    if not re.search(rf"^Time = {args.end_time}(?:\.0*)?$", log_text, re.M) or not re.search(
        r"^End$", log_text, re.M
    ):
        raise SystemExit(f"Solver log does not prove completion at t={args.end_time}")
    bad = re.search(r"FOAM FATAL|PHREEQC.*(?:error|failed)|\b(?:nan|inf)\b", log_text, re.I)
    if bad:
        raise SystemExit(f"Solver log contains failure marker: {bad.group(0)}")

    metrics: dict[str, object] = {"ranks": len(ranks), "times": {}}
    for time_name in args.times:
        summary = {
            "Pb+2_min": math.inf,
            "Pb+2_max": -math.inf,
            "Cl-_min": math.inf,
            "Cl-_max": -math.inf,
            "H+_min": math.inf,
            "H+_max": -math.inf,
            "OH-_min": math.inf,
            "OH-_max": -math.inf,
            "strong_Pb_occupancy_max": 0.0,
            "weak_Pb_occupancy_max": 0.0,
            "aqueous_Pb_bulk_cell_sum": 0.0,
            "sorbed_Pb_bulk_cell_sum": 0.0,
        }
        for rank in ranks:
            zero = rank / "0"
            timed = rank / time_name
            eps = field_values(zero / "eps")
            count = len(eps)
            asurf = field_values(zero / "aSurf", count)
            strong_master = field_values(zero / "Surf_s", count)
            weak_master = field_values(zero / "Surf_w", count)
            fields = {
                name: field_values(timed / name, count)
                for name in ("Pb+2", "Cl-", "H+", "OH-", "Surf_sOPb+", "Surf_wOPb+")
            }
            for name, values in fields.items():
                if not all(math.isfinite(value) for value in values):
                    raise SystemExit(f"Non-finite value in {timed / name}")
                if min(values) < -1.0e-15:
                    raise SystemExit(f"Negative value in {timed / name}: {min(values)}")
            if max(fields["Pb+2"]) > 1.01e-3 or max(fields["Cl-"]) > 2.02e-3:
                raise SystemExit(f"Aqueous inlet overshoot exceeds 1% at {timed}")
            strong_occ = [
                value / master if master > 0.0 else 0.0
                for value, master in zip(fields["Surf_sOPb+"], strong_master)
            ]
            weak_occ = [
                value / master if master > 0.0 else 0.0
                for value, master in zip(fields["Surf_wOPb+"], weak_master)
            ]
            if max(strong_occ + weak_occ) > 1.0 + 1.0e-8:
                raise SystemExit(f"Surface occupancy exceeds unity at {timed}")
            for name in ("Pb+2", "Cl-", "H+", "OH-"):
                summary[f"{name}_min"] = min(summary[f"{name}_min"], min(fields[name]))
                summary[f"{name}_max"] = max(summary[f"{name}_max"], max(fields[name]))
            summary["strong_Pb_occupancy_max"] = max(
                summary["strong_Pb_occupancy_max"], max(strong_occ)
            )
            summary["weak_Pb_occupancy_max"] = max(
                summary["weak_Pb_occupancy_max"], max(weak_occ)
            )
            summary["aqueous_Pb_bulk_cell_sum"] += sum(
                porosity * value for porosity, value in zip(eps, fields["Pb+2"])
            )
            summary["sorbed_Pb_bulk_cell_sum"] += sum(
                area * (strong + weak)
                for area, strong, weak in zip(
                    asurf, fields["Surf_sOPb+"], fields["Surf_wOPb+"]
                )
            )
            if time_name != "0":
                for checkpoint in ("phreeqc.dmp", "phreeqc.complete"):
                    if not (timed / checkpoint).is_file():
                        raise SystemExit(f"Missing checkpoint: {timed / checkpoint}")
        metrics["times"][time_name] = summary

    args.output.write_text(json.dumps(metrics, indent=2) + "\n")
    print(f"Validated completed run; wrote {args.output}")


if __name__ == "__main__":
    main()
