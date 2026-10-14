#!/usr/bin/env python3
"""Record and validate paper-case and figure provenance."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def git_value(root: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    )
    return result.stdout.rstrip()


def git_state(root: Path) -> dict[str, object]:
    status = git_value(root, "status", "--porcelain").splitlines()
    tracked_diff = git_value(root, "diff", "--binary")
    dirty_paths = [line[3:] for line in status if len(line) > 3]
    allowed = {"etc/bashrc", "ThirdParty/PhreeqcRM"}
    return {
        "root": str(root.resolve()),
        "commit": git_value(root, "rev-parse", "HEAD"),
        "branch": git_value(root, "branch", "--show-current"),
        "dirty": bool(status),
        "status_porcelain": status,
        "tracked_diff_sha256": sha256_text(tracked_diff),
        "dirty_paths": dirty_paths,
        "source_dirty_paths": [path for path in dirty_paths if path not in allowed],
    }


def runtime_artifacts(runtime_root: Path, solver: Path) -> dict[str, object]:
    result = subprocess.run(
        ["ldd", str(solver)], check=True, text=True, stdout=subprocess.PIPE
    )
    libraries = []
    for line in result.stdout.splitlines():
        match = re.search(r"=>\s+(/\S+)\s+\(", line)
        if match:
            path = Path(match.group(1)).resolve()
            if path.is_relative_to(runtime_root) and path.is_file():
                libraries.append({"path": str(path), "sha256": sha256(path)})
    submodule_root = runtime_root / "ThirdParty" / "PhreeqcRM"
    return {
        "solver": {"path": str(solver.resolve()), "sha256": sha256(solver)},
        "resolved_libraries": libraries,
        "ldd_sha256": sha256_text(result.stdout),
        "phreeqcrm_submodule": git_state(submodule_root),
    }


def surface_record(path: Path, expected_mode: str, expected_sigma: float) -> dict[str, object]:
    if not path.is_file():
        raise SystemExit(f"Missing surface-construction log: {path}")
    text = path.read_text()
    mode_match = re.search(r"\bmode=(\S+)", text)
    sigma_match = re.search(r"\bsigma_vox=([0-9.eE+-]+)", text)
    area_match = re.search(r"\bsum\(aSurf\*V\)=([0-9.eE+-]+)", text)
    if not mode_match or not sigma_match or not area_match:
        raise SystemExit(f"Could not parse surface provenance from {path}")
    mode = mode_match.group(1)
    sigma = float(sigma_match.group(1))
    if mode != expected_mode or abs(sigma - expected_sigma) > 1.0e-12:
        raise SystemExit(
            f"Surface method mismatch in {path}: got {mode}, sigma={sigma}; "
            f"expected {expected_mode}, sigma={expected_sigma}"
        )
    return {
        "path": str(path.resolve()),
        "sha256": sha256(path),
        "mode": mode,
        "sigma_vox": sigma,
        "integrated_area_m2": float(area_match.group(1)),
    }


def chemistry_record(thermo_file: Path, inputs: list[Path]) -> dict[str, object]:
    text = thermo_file.read_text()
    block = re.search(r"surfaceMasterDensities\s*\{(.*?)\}", text, re.S)
    if not block:
        raise SystemExit(f"Missing surfaceMasterDensities in {thermo_file}")
    densities = {
        name: float(value)
        for name, value in re.findall(
            r"([A-Za-z0-9_+\-]+)\s+([0-9.eE+\-]+)\s*;", block.group(1)
        )
    }
    if not densities:
        raise SystemExit(f"No surface master densities found in {thermo_file}")
    records = []
    for input_path in inputs:
        resolved = input_path.resolve()
        if not resolved.is_file():
            raise SystemExit(f"Missing provenance input: {resolved}")
        records.append({"path": str(resolved), "sha256": sha256(resolved)})
    return {"surface_master_densities_kmol_m2": densities, "files": records}


def uniform_value(path: Path) -> float:
    match = re.search(r"internalField\s+uniform\s+([0-9.eE+\-]+)\s*;", path.read_text())
    if not match:
        raise SystemExit(f"Expected a uniform internalField in {path}")
    return float(match.group(1))


def control_values(path: Path) -> dict[str, float]:
    text = path.read_text()
    values: dict[str, float] = {}
    for key in ("endTime", "deltaT", "writeInterval"):
        match = re.search(rf"^\s*{key}\s+([0-9.eE+\-]+)\s*;", text, re.M)
        if not match:
            raise SystemExit(f"Missing numeric {key} in {path}")
        values[key] = float(match.group(1))
    return values


def record_run_config(args: argparse.Namespace) -> None:
    payload = json.loads(args.manifest.read_text())
    chemistry = chemistry_record(args.thermo_file, [args.thermo_file])
    expected = chemistry["surface_master_densities_kmol_m2"]
    rank_dirs = sorted(args.case_dir.glob("processor*/0"))
    zero_dirs = rank_dirs or [args.case_dir / "0"]
    masters = []
    for zero_dir in zero_dirs:
        for name, expected_value in expected.items():
            field = zero_dir / name
            actual = uniform_value(field)
            if abs(actual - expected_value) > 1.0e-15 * max(1.0, abs(expected_value)):
                raise SystemExit(f"Surface master mismatch in {field}: {actual} != {expected_value}")
            masters.append({"path": str(field.resolve()), "value_kmol_m2": actual, "sha256": sha256(field)})
    initial_inputs = []
    for rank_dir in sorted(args.case_dir.glob("processor*")):
        for input_root in (rank_dir / "0", rank_dir / "constant" / "polyMesh"):
            if input_root.is_dir():
                for path in sorted(item for item in input_root.rglob("*") if item.is_file()):
                    initial_inputs.append({"path": str(path.resolve()), "sha256": sha256(path)})
    payload["realized_transport"] = {
        **control_values(args.control_dict),
        "control_dict": {"path": str(args.control_dict.resolve()), "sha256": sha256(args.control_dict)},
        "thermo_file": {"path": str(args.thermo_file.resolve()), "sha256": sha256(args.thermo_file)},
        "surface_master_fields": masters,
        "initial_rank_inputs": initial_inputs,
    }
    args.manifest.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Updated realized run configuration in {args.manifest}")


def record(args: argparse.Namespace) -> None:
    case_dir = args.case_dir.resolve()
    paper_root = args.paper_root.resolve()
    runtime_root = args.runtime_root.resolve()
    if runtime_root == paper_root:
        raise SystemExit("Runtime checkout must be separate from the paper repository")
    runtime = git_state(runtime_root)
    if runtime["source_dirty_paths"]:
        raise SystemExit(
            f"Runtime source checkout has uncommitted changes: {runtime['source_dirty_paths']}"
        )
    solver = shutil.which("reactiveTransportDBSFoam")
    if solver is None:
        raise SystemExit("reactiveTransportDBSFoam is not on PATH")
    expected_solver = runtime_root / "bin" / "reactiveTransportDBSFoam"
    if Path(solver).resolve() != expected_solver.resolve():
        raise SystemExit(
            f"Wrong solver selected: {Path(solver).resolve()} (expected {expected_solver.resolve()})"
        )
    payload = {
        "schema_version": 1,
        "case_id": args.case_id,
        "recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "paper": git_state(paper_root),
        "runtime": runtime,
        "solver_executable": str(Path(solver).resolve()),
        "runtime_artifacts": runtime_artifacts(runtime_root, Path(solver)),
        "surface": surface_record(args.surface_log, args.mode, args.sigma),
        "intrinsic_surface": surface_record(args.intrinsic_log, args.mode, args.sigma),
        "chemistry": chemistry_record(args.thermo_file, args.input),
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {args.output}")


def record_basic(args: argparse.Namespace) -> None:
    paper_root = args.paper_root.resolve()
    runtime_root = args.runtime_root.resolve()
    if runtime_root == paper_root:
        raise SystemExit("Runtime checkout must be separate from the paper repository")
    runtime = git_state(runtime_root)
    if runtime["source_dirty_paths"]:
        raise SystemExit(
            f"Runtime source checkout has uncommitted changes: {runtime['source_dirty_paths']}"
        )
    solver = shutil.which(args.solver)
    expected_solver = runtime_root / "bin" / args.solver
    if solver is None or Path(solver).resolve() != expected_solver.resolve():
        raise SystemExit(
            f"Wrong solver selected: {solver or 'not found'} "
            f"(expected {expected_solver.resolve()})"
        )
    inputs = []
    for input_path in args.input:
        resolved = input_path.resolve()
        if not resolved.is_file():
            raise SystemExit(f"Missing provenance input: {resolved}")
        inputs.append({"path": str(resolved), "sha256": sha256(resolved)})
    surface: dict[str, object] = {"mode": args.surface_mode}
    if args.surface_sigma is not None:
        surface["sigma_vox"] = args.surface_sigma
    payload = {
        "schema_version": 1,
        "case_id": args.case_id,
        "recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "paper": git_state(paper_root),
        "runtime": runtime,
        "solver_executable": str(Path(solver).resolve()),
        "runtime_artifacts": runtime_artifacts(runtime_root, Path(solver)),
        "surface": surface,
        "inputs": inputs,
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {args.output}")


def check(args: argparse.Namespace) -> None:
    payload = json.loads(args.manifest.read_text())
    if payload.get("case_id") != args.case_id:
        raise SystemExit(
            f"Case provenance mismatch: {payload.get('case_id')} != {args.case_id}"
        )
    surface = surface_record(args.surface_log, args.mode, args.sigma)
    recorded = payload.get("surface", {})
    if surface["sha256"] != recorded.get("sha256"):
        raise SystemExit("Surface-construction log differs from the recorded run provenance")
    runtime = payload.get("runtime", {})
    if runtime.get("source_dirty_paths") or not runtime.get("commit"):
        raise SystemExit("Run provenance does not identify an unmodified runtime source commit")
    print(
        f"Validated {args.case_id}: {args.mode}, sigma={args.sigma:g}, "
        f"runtime={runtime['commit']}"
    )


def record_figure(args: argparse.Namespace) -> None:
    runs = [json.loads(path.read_text()) for path in args.run_manifest]
    figure_path = args.figure.resolve()
    output_path = args.output.resolve()
    if not figure_path.is_file():
        raise SystemExit(f"Missing rendered figure: {figure_path}")
    if output_path.exists():
        payload = json.loads(output_path.read_text())
    else:
        payload = {"schema_version": 1, "figures": {}}
    run_records = [
        {
            "case_id": run["case_id"],
            "runtime_commit": run["runtime"]["commit"],
            "paper_commit_at_run": run["paper"]["commit"],
            "surface_mode": run["surface"]["mode"],
            "surface_sigma_vox": run["surface"].get("sigma_vox"),
            "surface_log_sha256": run["surface"].get("sha256"),
        }
        for run in runs
    ]
    entry = {
        "recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "figure_sha256": sha256(figure_path),
        "output_time": args.time,
    }
    if len(run_records) == 1:
        entry.update(run_records[0])
    else:
        entry["cases"] = run_records
    payload["figures"][figure_path.name] = entry
    output_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Updated {output_path}")


def parser() -> argparse.ArgumentParser:
    main = argparse.ArgumentParser()
    commands = main.add_subparsers(dest="command", required=True)

    rec = commands.add_parser("record")
    rec.add_argument("--case-id", required=True)
    rec.add_argument("--case-dir", type=Path, required=True)
    rec.add_argument("--paper-root", type=Path, required=True)
    rec.add_argument("--runtime-root", type=Path, required=True)
    rec.add_argument("--surface-log", type=Path, required=True)
    rec.add_argument("--intrinsic-log", type=Path, required=True)
    rec.add_argument("--thermo-file", type=Path, required=True)
    rec.add_argument("--input", action="append", type=Path, default=[])
    rec.add_argument("--mode", required=True)
    rec.add_argument("--sigma", type=float, required=True)
    rec.add_argument("--output", type=Path, required=True)
    rec.set_defaults(func=record)

    run_cfg = commands.add_parser("record-run-config")
    run_cfg.add_argument("--manifest", type=Path, required=True)
    run_cfg.add_argument("--case-dir", type=Path, required=True)
    run_cfg.add_argument("--control-dict", type=Path, required=True)
    run_cfg.add_argument("--thermo-file", type=Path, required=True)
    run_cfg.set_defaults(func=record_run_config)

    basic = commands.add_parser("record-basic")
    basic.add_argument("--case-id", required=True)
    basic.add_argument("--paper-root", type=Path, required=True)
    basic.add_argument("--runtime-root", type=Path, required=True)
    basic.add_argument("--solver", default="reactiveTransportDBSFoam")
    basic.add_argument("--surface-mode", required=True)
    basic.add_argument("--surface-sigma", type=float)
    basic.add_argument("--input", action="append", type=Path, default=[])
    basic.add_argument("--output", type=Path, required=True)
    basic.set_defaults(func=record_basic)

    chk = commands.add_parser("check")
    chk.add_argument("--manifest", type=Path, required=True)
    chk.add_argument("--case-id", required=True)
    chk.add_argument("--surface-log", type=Path, required=True)
    chk.add_argument("--mode", required=True)
    chk.add_argument("--sigma", type=float, required=True)
    chk.set_defaults(func=check)

    fig = commands.add_parser("record-figure")
    fig.add_argument("--run-manifest", action="append", type=Path, required=True)
    fig.add_argument("--figure", type=Path, required=True)
    fig.add_argument("--time", required=True)
    fig.add_argument("--output", type=Path, required=True)
    fig.set_defaults(func=record_figure)
    return main


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.func(arguments)
