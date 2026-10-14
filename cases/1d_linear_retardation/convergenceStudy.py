#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from pathlib import Path

import phase8AnalyticalTools as analytical


ROOT = Path(__file__).resolve().parent
LENGTH = analytical.DOMAIN_LENGTH
THETA = analytical.BASE_THETA
ASURF = analytical.BASE_ASURF
U = analytical.BASE_U
D = analytical.BASE_D


def configure(nx: int, delta_t: float, surface: bool, ca_in: float) -> None:
    analytical.prepare("transport", surface, ca_in)
    analytical.write_control(10.0, delta_t, 10.0)

    path = ROOT / "system" / "blockMeshDict"
    text = path.read_text()
    updated, count = re.subn(
        r"(hex\s*\([^\n]+\)\s*\()\s*\d+\s+1\s+1\s*(\))",
        rf"\g<1>{nx} 1 1\g<2>",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError("Could not set the 1D mesh resolution")
    path.write_text(updated)

    control = ROOT / "system" / "controlDict"
    control.write_text(
        control.read_text().replace(
            "phreeqcRestartCheckpoints true;", "phreeqcRestartCheckpoints false;"
        )
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def relative_e1(values: list[float], reference: list[float]) -> float:
    if len(values) != len(reference):
        raise ValueError("Relative E1 inputs must have equal lengths")
    return sum(abs(a - b) for a, b in zip(values, reference)) / max(
        sum(abs(value) for value in reference), 1.0e-30
    )


def project_to_count(values: list[float], count: int) -> list[float]:
    if len(values) == count:
        return values
    if len(values) % count:
        raise ValueError(f"Cannot conservatively project {len(values)} cells to {count}")
    ratio = len(values) // count
    return [
        sum(values[index * ratio : (index + 1) * ratio]) / ratio
        for index in range(count)
    ]


def load_manifest(path: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    with path.open(newline="") as stream:
        for row in csv.DictReader(stream):
            rows.append(
                {
                    "study": row["study"],
                    "label": row["label"],
                    "nx": int(row["nx"]),
                    "delta_t": float(row["delta_t"]),
                    "mode": row["mode"],
                    "directory": row["directory"],
                }
            )
    return rows


def analyze(manifest_path: Path, k_s: float, ca_in: float, output: Path) -> None:
    rows = load_manifest(manifest_path)
    r_factor = 1.0 + ASURF * k_s / THETA
    profiles: dict[tuple[str, str, str], list[float]] = {}
    results: list[dict[str, object]] = []

    for row in rows:
        directory = ROOT / str(row["directory"])
        ca_path = directory / "Ca+2"
        ca = analytical.parse_scalar_field(ca_path)
        surface = row["mode"] == "surface"
        velocity = U / (THETA * r_factor) if surface else U / THETA
        diffusion = D / r_factor if surface else D
        l1, linf = analytical.profile_metrics(ca, ca_in, velocity, diffusion, 10.0)
        expected = analytical.analytical_profile(
            len(ca), ca_in, velocity, diffusion, 10.0
        )
        numeric_inventory = THETA * analytical.mean(ca)
        expected_inventory = THETA * analytical.mean(expected)
        hashes = {"Ca+2": sha256(ca_path)}

        if surface:
            surf_path = directory / "Surf_aCa+"
            surf = analytical.parse_scalar_field(surf_path)
            numeric_inventory += ASURF * analytical.mean(surf)
            expected_inventory *= r_factor
            hashes["Surf_aCa+"] = sha256(surf_path)

        result = {
            **row,
            "dx": LENGTH / int(row["nx"]),
            "courant_darcy": U * float(row["delta_t"]) / (LENGTH / int(row["nx"])),
            "e1_analytical": l1,
            "linf_analytical": linf,
            "inventory_error": abs(numeric_inventory - expected_inventory)
            / max(abs(expected_inventory), 1.0e-30),
            "field_sha256": hashes,
        }
        results.append(result)
        profiles[(str(row["study"]), str(row["label"]), str(row["mode"]))] = ca

    for study in ("mesh", "timestep"):
        study_rows = [row for row in results if row["study"] == study]
        for mode in ("surface", "aqueous"):
            mode_rows = [row for row in study_rows if row["mode"] == mode]
            if study == "mesh":
                mode_rows.sort(key=lambda row: int(row["nx"]))
                reference_row = max(mode_rows, key=lambda row: int(row["nx"]))
            else:
                mode_rows.sort(key=lambda row: float(row["delta_t"]), reverse=True)
                reference_row = min(mode_rows, key=lambda row: float(row["delta_t"]))
            reference = profiles[(study, str(reference_row["label"]), mode)]
            for row in mode_rows:
                values = profiles[(study, str(row["label"]), mode)]
                projected_reference = project_to_count(reference, len(values))
                row["e1_finest"] = relative_e1(values, projected_reference)

            pairwise: list[float] = []
            for row, finer_row in zip(mode_rows, mode_rows[1:]):
                values = profiles[(study, str(row["label"]), mode)]
                finer = profiles[(study, str(finer_row["label"]), mode)]
                difference = relative_e1(values, project_to_count(finer, len(values)))
                row["e1_next_finer"] = difference
                pairwise.append(difference)
            mode_rows[-1]["e1_next_finer"] = None
            for index, row in enumerate(mode_rows):
                row["observed_order"] = (
                    math.log(pairwise[index] / pairwise[index + 1], 2.0)
                    if index + 1 < len(pairwise)
                    else None
                )

    for mode in ("surface", "aqueous"):
        reference = profiles[("mesh", "nx320", mode)]
        reported = next(
            row
            for row in results
            if row["study"] == "reported" and row["mode"] == mode
        )
        values = profiles[("reported", str(reported["label"]), mode)]
        reported["e1_finest"] = relative_e1(
            values, project_to_count(reference, len(values))
        )
        reported["e1_next_finer"] = None
        reported["observed_order"] = None

    output.write_text(json.dumps({"K_s": k_s, "R": r_factor, "runs": results}, indent=2) + "\n")

    csv_path = output.with_suffix(".csv")
    fields = [
        "study",
        "label",
        "mode",
        "nx",
        "dx",
        "delta_t",
        "courant_darcy",
        "e1_analytical",
        "linf_analytical",
        "inventory_error",
        "e1_finest",
        "e1_next_finer",
        "observed_order",
    ]
    with csv_path.open("w", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        writer.writerows({key: row[key] for key in fields} for row in results)


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    configure_parser = subparsers.add_parser("configure")
    configure_parser.add_argument("--nx", type=int, required=True)
    configure_parser.add_argument("--delta-t", type=float, required=True)
    configure_parser.add_argument("--surface", choices=("on", "off"), required=True)
    configure_parser.add_argument("--ca-in", type=float, default=2.0e-9)

    analyze_parser = subparsers.add_parser("analyze")
    analyze_parser.add_argument("--manifest", type=Path, required=True)
    analyze_parser.add_argument("--k-s", type=float, required=True)
    analyze_parser.add_argument("--ca-in", type=float, default=2.0e-9)
    analyze_parser.add_argument("--output", type=Path, required=True)

    args = parser.parse_args()
    if args.command == "configure":
        configure(args.nx, args.delta_t, args.surface == "on", args.ca_in)
    else:
        analyze(args.manifest, args.k_s, args.ca_in, args.output)


if __name__ == "__main__":
    main()
