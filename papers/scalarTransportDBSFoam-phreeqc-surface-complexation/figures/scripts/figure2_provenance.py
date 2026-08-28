#!/usr/bin/env python3
"""Fail-closed run validation and Figure 2 provenance recording."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
from pathlib import Path


EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()
FINAL_FIELDS = ("Pb+2", "Cl-", "H+", "OH-", "Surf_sOPb+", "Surf_wOPb+")
SUPPORT_FIELDS = ("eps", "aSurf", "Surf_s", "Surf_w")
PATH_KEYS = {"path", "root", "figure_path", "run_manifest_path", "solver_executable"}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def require(condition: bool, message: str) -> None:
    if not condition:
        raise SystemExit(message)


def verify_file(record: dict[str, object], label: str) -> None:
    path = Path(str(record.get("path", "")))
    expected = str(record.get("sha256", ""))
    require(path.is_file(), f"Missing {label}: {path}")
    require(bool(re.fullmatch(r"[0-9a-f]{64}", expected)), f"Invalid {label} SHA256")
    require(sha256(path) == expected, f"Hash mismatch for {label}: {path}")


def verify_records(records: object, label: str, minimum: int = 1) -> list[dict[str, object]]:
    require(isinstance(records, list) and len(records) >= minimum, f"Missing {label} records")
    for index, record in enumerate(records):
        require(isinstance(record, dict), f"Invalid {label} record {index}")
        verify_file(record, f"{label} record {index}")
    return records


def portable_path(path: Path, roots: dict[str, Path]) -> str:
    resolved = path.resolve()
    candidates = sorted(roots.items(), key=lambda item: len(str(item[1])), reverse=True)
    for label, root in candidates:
        root = root.resolve()
        if resolved == root:
            return f"${{{label}}}"
        if resolved.is_relative_to(root):
            return f"${{{label}}}/{resolved.relative_to(root).as_posix()}"
    raise SystemExit(f"Cannot make provenance path portable: {resolved}")


def portableize_paths(value: object, roots: dict[str, Path], key: str = "") -> object:
    if isinstance(value, dict):
        return {
            item_key: portableize_paths(item_value, roots, item_key)
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [portableize_paths(item, roots, key) for item in value]
    if key in PATH_KEYS and isinstance(value, str) and Path(value).is_absolute():
        return portable_path(Path(value), roots)
    return value


def file_record(path: Path, roots: dict[str, Path]) -> dict[str, str]:
    require(path.is_file(), f"Missing provenance input: {path}")
    return {"path": portable_path(path, roots), "sha256": sha256(path)}


def records_sha256(records: list[dict[str, str]]) -> str:
    digest = hashlib.sha256()
    for record in sorted(records, key=lambda item: item["path"]):
        digest.update(record["path"].encode())
        digest.update(b"\0")
        digest.update(record["sha256"].encode())
        digest.update(b"\n")
    return digest.hexdigest()


def collect_run_outputs(
    case_dir: Path, time_name: str, roots: dict[str, Path]
) -> dict[str, object]:
    final_fields = [
        file_record(case_dir / f"processor{rank}" / time_name / name, roots)
        for rank in range(8)
        for name in FINAL_FIELDS
    ]
    support_fields = [
        file_record(case_dir / f"processor{rank}" / "0" / name, roots)
        for rank in range(8)
        for name in SUPPORT_FIELDS
    ]
    return {
        "solver_log": file_record(case_dir / "reactiveTransportDBSFoamRT.out", roots),
        "final_rank_fields": final_fields,
        "final_rank_fields_sha256": records_sha256(final_fields),
        "support_rank_fields": support_fields,
        "support_rank_fields_sha256": records_sha256(support_fields),
    }


def exact_float(actual: object, expected: float, label: str) -> None:
    require(isinstance(actual, (int, float)), f"Missing numeric {label}")
    require(float(actual) == expected, f"Wrong {label}: {actual} != {expected}")


def require_within(path_value: object, root: Path, label: str) -> None:
    path = Path(str(path_value)).resolve()
    require(path.is_relative_to(root), f"{label} is outside the selected case: {path}")


def check_run(args: argparse.Namespace) -> dict[str, object]:
    manifest_path = args.manifest.resolve()
    case_dir = args.case_dir.resolve()
    require(manifest_path == case_dir / "run_provenance.json",
            "Run manifest is not the selected case manifest")
    require(manifest_path.is_file(), f"Missing run manifest: {manifest_path}")
    payload = json.loads(manifest_path.read_text())
    require(payload.get("case_id") == "2d_4StraightFractures", "Wrong case_id")

    paper = payload.get("paper", {})
    require(paper.get("commit") == args.paper_commit, "Wrong paper commit")
    require(isinstance(paper.get("status_porcelain"), list), "Paper status was not recorded")
    require(bool(re.fullmatch(r"[0-9a-f]{64}", str(paper.get("tracked_diff_sha256", "")))),
            "Paper tracked-diff hash was not recorded")

    runtime = payload.get("runtime", {})
    require(runtime.get("commit") == args.runtime_commit, "Wrong runtime commit")
    require(not runtime.get("source_dirty_paths"), "Runtime has uncommitted source changes")
    require(runtime.get("tracked_diff_sha256") == EMPTY_SHA256, "Runtime tracked diff is non-empty")

    artifacts = payload.get("runtime_artifacts", {})
    solver = artifacts.get("solver", {})
    require(solver.get("sha256") == args.solver_sha256, "Wrong solver SHA256")
    verify_file(solver, "solver")
    libraries = verify_records(artifacts.get("resolved_libraries"), "runtime library", 3)
    require(any(Path(str(item["path"])).name == "libPhreeqcRM.so" for item in libraries),
            "Resolved PhreeqcRM library was not recorded")
    expected_libraries = dict(item.split("=", 1) for item in args.library_sha256)
    actual_libraries = {Path(str(item["path"])).name: item["sha256"] for item in libraries}
    require(actual_libraries == expected_libraries, "Resolved runtime library set/hash mismatch")
    submodule = artifacts.get("phreeqcrm_submodule", {})
    require(submodule.get("commit") == args.phreeqcrm_commit, "Wrong PhreeqcRM commit")
    require(submodule.get("tracked_diff_sha256") == EMPTY_SHA256,
            "PhreeqcRM tracked diff is non-empty")

    surface = payload.get("surface", {})
    intrinsic = payload.get("intrinsic_surface", {})
    for record, label, expected_area in (
        (surface, "surface log", args.surface_area),
        (intrinsic, "intrinsic surface log", args.intrinsic_area),
    ):
        require(record.get("mode") == args.surface_mode, f"Wrong {label} mode")
        exact_float(record.get("sigma_vox"), args.surface_sigma, f"{label} sigma")
        exact_float(record.get("integrated_area_m2"), expected_area, f"{label} area")
        require_within(record.get("path"), case_dir, label)
        verify_file(record, label)

    chemistry = payload.get("chemistry", {})
    densities = chemistry.get("surface_master_densities_kmol_m2", {})
    exact_float(densities.get("Surf_s"), args.strong_density, "Surf_s density")
    exact_float(densities.get("Surf_w"), args.weak_density, "Surf_w density")
    chemistry_files = verify_records(
        chemistry.get("files"), "chemistry/source input", args.chemistry_input_count
    )
    require(len(chemistry_files) == args.chemistry_input_count,
            "Wrong chemistry/source input count")

    realized = payload.get("realized_transport", {})
    exact_float(realized.get("endTime"), args.time, "endTime")
    exact_float(realized.get("deltaT"), args.delta_t, "deltaT")
    exact_float(realized.get("writeInterval"), args.write_interval, "writeInterval")
    verify_file(realized.get("control_dict", {}), "realized controlDict")
    verify_file(realized.get("thermo_file", {}), "realized thermo file")
    require_within(realized.get("control_dict", {}).get("path"), case_dir, "controlDict")
    require_within(realized.get("thermo_file", {}).get("path"), case_dir, "thermo file")
    masters = verify_records(realized.get("surface_master_fields"), "surface master field", 16)
    require(len(masters) == 16, "Expected exactly 16 surface master fields")
    for record in masters:
        expected = args.strong_density if Path(str(record["path"])).name == "Surf_s" else args.weak_density
        exact_float(record.get("value_kmol_m2"), expected, "surface master field value")
    initial_inputs = verify_records(
        realized.get("initial_rank_inputs"), "initial rank input", args.initial_input_count
    )
    require(len(initial_inputs) == args.initial_input_count, "Wrong initial rank input count")
    for record in (*masters, *initial_inputs):
        require_within(record.get("path"), case_dir, "rank input")

    log = case_dir / "reactiveTransportDBSFoamRT.out"
    require(log.is_file(), f"Missing completed solver log: {log}")
    text = log.read_text(errors="replace")
    require(re.search(rf"^Time = {args.time:g}(?:\.0*)?$", text, re.M) is not None,
            f"Solver log does not reach t={args.time:g}")
    require(re.search(r"^End$", text, re.M) is not None, "Solver log has no clean End marker")
    for rank in range(8):
        final = case_dir / f"processor{rank}" / f"{args.time:g}"
        for name in (*FINAL_FIELDS, "phreeqc.dmp", "phreeqc.complete"):
            require((final / name).is_file(), f"Missing final rank output: {final / name}")

    return payload


def record_figure(args: argparse.Namespace) -> None:
    figure = args.figure.resolve()
    manifest = args.manifest.resolve()
    paper_root = args.paper_root.resolve()
    case_dir = args.case_dir.resolve()
    run = json.loads(manifest.read_text())
    roots = {
        "RUN_CASE_DIR": case_dir,
        "RUNTIME_REPO": Path(run["runtime"]["root"]),
        "RUN_PAPER_REPO": Path(run["paper"]["root"]),
        "PAPER_REPO": paper_root,
    }
    require(figure.is_file(), f"Missing rendered figure: {figure}")
    figure_inputs = []
    for path in args.figure_input:
        resolved = path.resolve()
        require(resolved.is_file(), f"Missing figure input: {resolved}")
        figure_inputs.append(file_record(resolved, roots))
    renderer_sources = [file_record(path.resolve(), roots) for path in args.renderer_source]
    require(len(renderer_sources) >= 3, "At least three renderer source files are required")
    if args.output.is_file():
        payload = json.loads(args.output.read_text())
        require(isinstance(payload.get("figures"), dict), "Invalid existing figure manifest")
    else:
        payload = {"schema_version": 2, "figures": {}}
    payload["schema_version"] = 3
    payload["figures"][figure.name] = {
        "path_roots": {
            "PAPER_REPO": "checkout of the paper repository",
            "RUN_PAPER_REPO": "checkout used to execute the archived run",
            "RUN_CASE_DIR": "completed 2D fracture case directory",
            "RUNTIME_REPO": "checkout used to build the solver and libraries",
        },
        "figure_path": portable_path(figure, roots),
        "figure_sha256": sha256(figure),
        "recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "output_time_s": args.time,
        "figure_inputs": figure_inputs,
        "renderer": {
            "repository": args.renderer_repository,
            "commit": args.renderer_commit,
            "source_files": renderer_sources,
            "source_files_sha256": records_sha256(renderer_sources),
        },
        "run_outputs": collect_run_outputs(case_dir, f"{args.time:g}", roots),
        "run_manifest_path": portable_path(manifest, roots),
        "run_manifest_sha256": sha256(manifest),
        "paper": portableize_paths(run["paper"], roots),
        "runtime": portableize_paths(run["runtime"], roots),
        "runtime_artifacts": portableize_paths(run["runtime_artifacts"], roots),
        "surface": portableize_paths(run["surface"], roots),
        "intrinsic_surface": portableize_paths(run["intrinsic_surface"], roots),
        "chemistry": portableize_paths(run["chemistry"], roots),
        "realized_transport": {
            key: portableize_paths(run["realized_transport"][key], roots)
            for key in (
                "endTime", "deltaT", "writeInterval", "control_dict",
                "thermo_file", "surface_master_fields",
            )
        },
    }
    args.output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Updated {args.output}")


def parser() -> argparse.ArgumentParser:
    main = argparse.ArgumentParser()
    commands = main.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check-run")
    check.add_argument("--manifest", type=Path, required=True)
    check.add_argument("--case-dir", type=Path, required=True)
    check.add_argument("--paper-commit", required=True)
    check.add_argument("--runtime-commit", required=True)
    check.add_argument("--solver-sha256", required=True)
    check.add_argument("--library-sha256", action="append", required=True)
    check.add_argument("--phreeqcrm-commit", required=True)
    check.add_argument("--surface-mode", required=True)
    check.add_argument("--surface-sigma", type=float, required=True)
    check.add_argument("--surface-area", type=float, required=True)
    check.add_argument("--intrinsic-area", type=float, required=True)
    check.add_argument("--strong-density", type=float, required=True)
    check.add_argument("--weak-density", type=float, required=True)
    check.add_argument("--time", type=float, required=True)
    check.add_argument("--delta-t", type=float, required=True)
    check.add_argument("--write-interval", type=float, required=True)
    check.add_argument("--chemistry-input-count", type=int, required=True)
    check.add_argument("--initial-input-count", type=int, required=True)
    check.set_defaults(func=lambda args: check_run(args))
    record = commands.add_parser("record-figure")
    record.add_argument("--manifest", type=Path, required=True)
    record.add_argument("--case-dir", type=Path, required=True)
    record.add_argument("--paper-root", type=Path, required=True)
    record.add_argument("--figure", type=Path, required=True)
    record.add_argument("--time", type=float, required=True)
    record.add_argument("--figure-input", action="append", type=Path, default=[])
    record.add_argument("--renderer-source", action="append", type=Path, default=[])
    record.add_argument("--renderer-repository", required=True)
    record.add_argument("--renderer-commit", required=True)
    record.add_argument("--output", type=Path, required=True)
    record.set_defaults(func=record_figure)
    return main


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.func(arguments)
