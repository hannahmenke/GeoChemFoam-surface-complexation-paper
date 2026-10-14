#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path


CASE_DIR = Path(__file__).resolve().parents[1]
PAPER_DIR = CASE_DIR.parents[1]
DEFAULT_MANIFEST = CASE_DIR / "paper_validation_runs.json"
DEFAULT_OUTPUT = CASE_DIR / "results" / "paper_figures"
DEFAULT_FIGURES = PAPER_DIR / "figures" / "png"


def run(command: list[str]) -> None:
    print("+ " + " ".join(command), flush=True)
    subprocess.run(command, check=True)


def resolve_case(path_text: str) -> Path:
    path = Path(path_text)
    return path if path.is_absolute() else CASE_DIR / path


def pe_slug(peclet: float) -> str:
    return f"{peclet:g}".replace(".", "p")


def decimal_slug(value: float) -> str:
    return f"{value:g}".replace(".", "p")


def publication_pngs(field_stem: str) -> tuple[tuple[str, str], ...]:
    return (
        (f"{field_stem}.png", "fig10_two_scale_pe1_fields.png"),
        ("paper_error_vs_peclet.png", "fig09_two_scale_error_vs_peclet.png"),
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Regenerate two-scale validation metrics and publication figures."
    )
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--figure-dir", type=Path, default=DEFAULT_FIGURES)
    parser.add_argument(
        "--skip-publish",
        action="store_true",
        help="Do not copy the final publication PNGs into the paper figures directory.",
    )
    args = parser.parse_args()

    manifest = json.loads(args.manifest.read_text())
    if manifest.get("schema_version") != 1:
        raise ValueError("Unsupported paper-validation manifest schema")
    runs = manifest["runs"]
    pe1 = next(run_spec for run_spec in runs if float(run_spec["peclet"]) == 1.0)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    metric_specs: list[str] = []
    for run_spec in runs:
        peclet = float(run_spec["peclet"])
        metric_dir = args.output_dir / "metrics" / f"pe{pe_slug(peclet)}"
        run(
            [
                sys.executable,
                str(CASE_DIR / "scripts" / "compare_resolved_dbs_production.py"),
                "--resolved", str(resolve_case(run_spec["resolved_case"])),
                "--resolved-time", run_spec["resolved_time"],
                "--dbs", str(resolve_case(run_spec["dbs_case"])),
                "--dbs-time", run_spec["dbs_time"],
                "--peclet", f"{peclet:g}",
                "--transits", str(manifest["metrics_x_over_L"]),
                "--output-dir", str(metric_dir),
            ]
        )
        metric_file = metric_dir / (
            f"resolved_vs_dbs_pe{pe_slug(peclet)}_metrics.json"
        )
        metric_specs.extend(["--metric", f"{peclet:g}={metric_file}"])

    field_spec = manifest["pe1_field_figure"]
    field_stem = (
        "paper_pe1_resolved_vs_dbs_fields_"
        f"xL{decimal_slug(float(field_spec['x_over_L']))}"
    )
    run(
        [
            sys.executable,
            str(CASE_DIR / "scripts" / "plot_paper_validation_figures.py"),
            "--pe1-resolved", str(resolve_case(pe1["resolved_case"])),
            "--pe1-resolved-time", field_spec["resolved_time"],
            "--pe1-dbs", str(resolve_case(pe1["dbs_case"])),
            "--pe1-dbs-time", field_spec["dbs_time"],
            "--transits", str(field_spec["x_over_L"]),
            "--metric-transits", str(manifest["metrics_x_over_L"]),
            "--acceptance-config", str(args.manifest),
            "--field-stem", field_stem,
            "--assert-acceptance",
            *metric_specs,
            "--output-dir", str(args.output_dir),
        ]
    )

    front_dir = args.output_dir / "front_acceptance"
    front_spec = manifest["pe1_front_acceptance"]
    run(
        [
            sys.executable,
            str(CASE_DIR / "scripts" / "plot_paper_validation_figures.py"),
            "--pe1-resolved", str(resolve_case(pe1["resolved_case"])),
            "--pe1-resolved-time", front_spec["resolved_time"],
            "--pe1-dbs", str(resolve_case(pe1["dbs_case"])),
            "--pe1-dbs-time", front_spec["dbs_time"],
            "--transits", str(front_spec["x_over_L"]),
            "--metric-transits", str(manifest["metrics_x_over_L"]),
            "--acceptance-config", str(args.manifest),
            "--field-stem", "pe1_front_acceptance",
            "--assert-acceptance",
            *metric_specs,
            "--output-dir", str(front_dir),
        ]
    )
    run(
        [
            sys.executable,
            str(CASE_DIR / "scripts" / "diagnose_pe1_front_match.py"),
            str(front_dir / "pe1_front_acceptance_native_fields.npz"),
            "--output", str(front_dir / "pe1_front_acceptance_metrics.json"),
            "--assert-match",
        ]
    )

    if not args.skip_publish:
        args.figure_dir.mkdir(parents=True, exist_ok=True)
        for source_name, target_name in publication_pngs(field_stem):
            shutil.copy2(args.output_dir / source_name, args.figure_dir / target_name)


if __name__ == "__main__":
    main()
