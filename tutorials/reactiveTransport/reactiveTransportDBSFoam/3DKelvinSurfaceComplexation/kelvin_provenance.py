#!/usr/bin/env python3
"""Fail-closed provenance for the canonical Kelvin paper case."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import subprocess
from pathlib import Path


REQUIRED_INITIAL_FIELDS = (
    "Cl-", "H+", "Kinv", "Mg+2", "Mn+2", "OH-", "Surf_s", "Surf_sO-",
    "Surf_sOH", "Surf_sOMn+", "Surf_w", "Surf_wO-", "Surf_wOH",
    "Surf_wOMg+", "Surf_wOMn+", "U", "aSurf", "aSurfIntrinsic", "eps", "p",
    "phi",
)
REQUIRED_POLYMESH_FILES = ("boundary", "faces", "neighbour", "owner", "points")
REQUIRED_REALIZED_DICTIONARIES = (
    Path("constant/transportProperties"),
    Path("constant/thermoPhysicalProperties"),
    Path("system/postProcessDict"),
    Path("system/controlDict"),
    Path("system/fvSolution"),
)
IDENTITY_ENV = (
    "FOAM_API", "WM_ARCH", "WM_COMPILER", "WM_COMPILER_TYPE",
    "WM_COMPILE_OPTION", "WM_LABEL_OPTION", "WM_MPLIB", "WM_OPTIONS",
    "WM_PRECISION_OPTION", "WM_PROJECT", "WM_PROJECT_VERSION",
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def command(*args: str) -> str:
    return subprocess.run(
        args, check=True, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    ).stdout.rstrip()


def git_value(root: Path, *args: str) -> str:
    return command("git", "-C", str(root), *args)


def tracked_diff(root: Path, *, ignore_submodules: bool = False) -> str:
    args = ["diff", "--binary", "HEAD"]
    if ignore_submodules:
        args.append("--ignore-submodules=all")
    return git_value(root, *args)


def commit_tree(root: Path) -> tuple[str, str]:
    return git_value(root, "rev-parse", "HEAD"), git_value(root, "rev-parse", "HEAD^{tree}")


def file_record(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise SystemExit(f"Missing provenance input: {resolved}")
    return {"path": str(resolved), "sha256": sha256(resolved)}


def runtime_git_identity(
    root: Path,
    expected_commit: str,
    expected_tree: str,
    expected_gitlink: str,
    expected_phreeqcrm_commit: str,
    expected_phreeqcrm_tree: str,
) -> dict[str, object]:
    root = root.resolve()
    commit, tree = commit_tree(root)
    if (commit, tree) != (expected_commit, expected_tree):
        raise SystemExit(
            f"GeoChemFoam identity mismatch: {(commit, tree)} != "
            f"{(expected_commit, expected_tree)}"
        )
    root_diff = tracked_diff(root, ignore_submodules=True)
    if root_diff:
        raise SystemExit("GeoChemFoam runtime has tracked source changes")
    staged_gitlink_diff = git_value(
        root, "diff", "--cached", "--binary", "HEAD", "--", "ThirdParty/PhreeqcRM"
    )
    if staged_gitlink_diff:
        raise SystemExit("GeoChemFoam runtime has a staged PHREEQCRM gitlink change")
    entry = git_value(root, "ls-tree", "HEAD", "ThirdParty/PhreeqcRM").split()
    if len(entry) < 3 or entry[1] != "commit":
        raise SystemExit("GeoChemFoam commit has no PHREEQCRM gitlink")
    gitlink = entry[2]
    if gitlink != expected_gitlink:
        raise SystemExit(f"PHREEQCRM gitlink mismatch: {gitlink} != {expected_gitlink}")

    submodule = root / "ThirdParty" / "PhreeqcRM"
    sub_commit, sub_tree = commit_tree(submodule)
    if (sub_commit, sub_tree) != (expected_phreeqcrm_commit, expected_phreeqcrm_tree):
        raise SystemExit(
            f"PHREEQCRM identity mismatch: {(sub_commit, sub_tree)} != "
            f"{(expected_phreeqcrm_commit, expected_phreeqcrm_tree)}"
        )
    sub_diff = tracked_diff(submodule)
    if sub_diff:
        raise SystemExit("PHREEQCRM runtime has tracked source changes")
    return {
        "root": str(root),
        "commit": commit,
        "tree": tree,
        "tracked_diff_sha256": sha256_text(root_diff + staged_gitlink_diff),
        "phreeqcrm_gitlink": gitlink,
        "phreeqcrm": {
            "root": str(submodule.resolve()),
            "commit": sub_commit,
            "tree": sub_tree,
            "tracked_diff_sha256": sha256_text(sub_diff),
            "differs_from_gitlink": sub_commit != gitlink,
        },
    }


def paper_identity(root: Path) -> dict[str, object]:
    commit, tree = commit_tree(root)
    diff = tracked_diff(root, ignore_submodules=True)
    return {
        "root": str(root.resolve()),
        "commit": commit,
        "tree": tree,
        "tracked_diff_sha256": sha256_text(diff),
    }


def parse_ldd(text: str) -> list[dict[str, str]]:
    dependencies: list[dict[str, str]] = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if "=> not found" in line:
            raise SystemExit(f"Unresolved solver dependency: {line}")
        linked = re.fullmatch(r"(\S+)\s+=>\s+(/\S+)\s+\(0x[0-9a-fA-F]+\)", line)
        direct = re.fullmatch(r"(/\S+)\s+\(0x[0-9a-fA-F]+\)", line)
        virtual = re.fullmatch(r"(linux-vdso\S*)\s+\(0x[0-9a-fA-F]+\)", line)
        if linked:
            name, path = linked.groups()
            dependencies.append({"name": name, **file_record(Path(path))})
        elif direct:
            path = direct.group(1)
            dependencies.append({"name": Path(path).name, **file_record(Path(path))})
        elif virtual:
            dependencies.append({"name": virtual.group(1), "kind": "virtual"})
        elif line == "statically linked":
            dependencies.append({"name": "statically linked", "kind": "static"})
        else:
            raise SystemExit(f"Unparsed ldd dependency: {line}")
    if not dependencies:
        raise SystemExit("ldd returned no dependency records")
    return sorted(dependencies, key=lambda item: (item["name"], item.get("path", "")))


def executable_identity(name: str) -> dict[str, str]:
    executable = shutil.which(name)
    if executable is None:
        raise SystemExit(f"Required identity executable is unavailable: {name}")
    resolved = Path(executable).resolve()
    version = command(str(resolved), "--version")
    return {**file_record(resolved), "version": version, "version_sha256": sha256_text(version)}


def runtime_artifacts(root: Path, solver: Path) -> dict[str, object]:
    ldd = command("ldd", str(solver))
    environment = {key: os.environ.get(key, "") for key in IDENTITY_ENV}
    missing = [key for key, value in environment.items() if not value]
    if missing:
        raise SystemExit(f"Missing compiler/OpenFOAM identity variables: {missing}")
    payload = {
        "solver": file_record(solver),
        "resolved_dependencies": parse_ldd(ldd),
        "environment": environment,
        "compiler": executable_identity("c++"),
        "mpi": executable_identity("mpirun"),
    }
    payload["identity_sha256"] = sha256_text(
        json.dumps(payload, sort_keys=True, separators=(",", ":"))
    )
    return payload


def surface_record(path: Path, mode: str, sigma: float) -> dict[str, object]:
    text = path.read_text()
    mode_match = re.search(r"\bmode=(\S+)", text)
    sigma_match = re.search(r"\bsigma_vox=([0-9.eE+-]+)", text)
    area_match = re.search(r"\bsum\(aSurf\*V\)=([0-9.eE+-]+)", text)
    if not mode_match or not sigma_match or not area_match:
        raise SystemExit(f"Incomplete surface log: {path}")
    if mode_match.group(1) != mode or float(sigma_match.group(1)) != sigma:
        raise SystemExit(f"Surface configuration mismatch: {path}")
    return {
        **file_record(path), "mode": mode, "sigma_vox": sigma,
        "integrated_area_m2": float(area_match.group(1)),
    }


def densities(path: Path) -> dict[str, float]:
    text = path.read_text()
    block = re.search(r"surfaceMasterDensities\s*\{(.*?)\}", text, re.S)
    if not block:
        raise SystemExit(f"No surfaceMasterDensities in {path}")
    result = {
        name: float(value)
        for name, value in re.findall(r"(Surf_[sw])\s+([0-9.eE+\-]+)\s*;", block.group(1))
    }
    if result != {"Surf_s": 2e-7, "Surf_w": 6e-6}:
        raise SystemExit(f"Wrong surface densities: {result}")
    return result


def snapshot_dictionaries(root: Path, paths: list[Path]) -> list[dict[str, object]]:
    if not paths:
        raise SystemExit("No realised dictionaries were supplied for snapshotting")
    if root.exists():
        raise SystemExit(f"Refusing to overwrite provenance snapshot: {root}")
    prepared: list[tuple[Path, Path]] = []
    for source in paths:
        if source.is_absolute() or ".." in source.parts:
            raise SystemExit(f"Realised dictionary path must be case-relative: {source}")
        if not source.is_file():
            raise SystemExit(f"Missing realised dictionary: {source}")
        prepared.append((source, root / source))
    records = []
    for source, destination in prepared:
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        records.append({"source": str(source), "snapshot": file_record(destination)})
    return records


def require_realized_dictionaries(paths: list[Path]) -> None:
    missing = [path for path in REQUIRED_REALIZED_DICTIONARIES if path not in paths]
    if missing:
        raise SystemExit(f"Missing required realised dictionaries: {missing}")


def runtime_from_args(args: argparse.Namespace) -> dict[str, object]:
    return runtime_git_identity(
        args.runtime, args.expected_runtime_commit, args.expected_runtime_tree,
        args.expected_phreeqcrm_gitlink, args.expected_phreeqcrm_commit,
        args.expected_phreeqcrm_tree,
    )


def record(args: argparse.Namespace) -> None:
    runtime = args.runtime.resolve()
    solver_name = shutil.which("reactiveTransportDBSFoam")
    if solver_name is None:
        raise SystemExit("reactiveTransportDBSFoam is not on PATH")
    solver = Path(solver_name).resolve()
    expected_solver = (runtime / "bin" / "reactiveTransportDBSFoam").resolve()
    if solver != expected_solver:
        raise SystemExit(f"Wrong solver: {solver} != {expected_solver}")
    runtime_identity = runtime_from_args(args)
    artifacts = runtime_artifacts(runtime, solver)
    require_realized_dictionaries(args.dictionary)
    snapshots = snapshot_dictionaries(args.snapshot_root, args.dictionary)
    payload = {
        "schema_version": 3,
        "case_id": "3d_kelvin",
        "recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "paper": paper_identity(args.paper.resolve()),
        "runtime": runtime_identity,
        "runtime_artifacts": artifacts,
        "surface": surface_record(args.surface_log, args.mode, args.sigma),
        "intrinsic_surface": surface_record(args.intrinsic_log, args.mode, args.sigma),
        "chemistry": {
            "surface_master_densities_kmol_m2": densities(args.thermo),
            "files": [file_record(path) for path in args.input],
        },
        "realized_initialization_dictionaries": snapshots,
        "transport_stages": [],
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {args.output}")


def uniform(path: Path) -> float:
    match = re.search(r"internalField\s+uniform\s+([0-9.eE+\-]+)\s*;", path.read_text())
    if not match:
        raise SystemExit(f"Expected uniform field: {path}")
    return float(match.group(1))


def scalar_file(path: Path) -> int:
    try:
        return int(path.read_text().split()[-1])
    except (IndexError, ValueError) as error:
        raise SystemExit(f"Invalid decomposition value in {path}") from error


def control_values(path: Path) -> dict[str, object]:
    text = path.read_text()
    values: dict[str, object] = {}
    for key in ("startTime", "endTime", "deltaT", "writeInterval"):
        match = re.search(rf"^\s*{key}\s+([0-9.eE+\-]+)\s*;", text, re.M)
        if not match:
            raise SystemExit(f"Missing numeric {key} in {path}")
        values[key] = float(match.group(1))
    for key in ("phreeqcRestartCheckpoints", "phreeqcRestoreCheckpoint"):
        match = re.search(rf"^\s*{key}\s+(true|false)\s*;", text, re.M)
        if not match:
            raise SystemExit(f"Missing boolean {key} in {path}")
        values[key] = match.group(1) == "true"
    if values["endTime"] <= values["startTime"]:
        raise SystemExit("endTime must be greater than startTime")
    if values["deltaT"] <= 0 or values["writeInterval"] <= 0:
        raise SystemExit("deltaT and writeInterval must be positive")
    return values


def validate_recorded_runtime(payload: dict[str, object]) -> None:
    runtime = payload.get("runtime")
    artifacts = payload.get("runtime_artifacts")
    if not isinstance(runtime, dict) or not isinstance(artifacts, dict):
        raise SystemExit("Manifest lacks runtime identity")
    submodule = runtime.get("phreeqcrm")
    if not isinstance(submodule, dict):
        raise SystemExit("Manifest lacks PHREEQCRM identity")
    current = runtime_git_identity(
        Path(str(runtime["root"])), str(runtime["commit"]), str(runtime["tree"]),
        str(runtime["phreeqcrm_gitlink"]), str(submodule["commit"]), str(submodule["tree"]),
    )
    if current != runtime:
        raise SystemExit("Runtime identity changed after initialization")
    solver_record = artifacts.get("solver")
    if not isinstance(solver_record, dict):
        raise SystemExit("Manifest lacks solver identity")
    solver = Path(str(solver_record.get("path", "")))
    if not solver.is_file() or sha256(solver) != solver_record.get("sha256"):
        raise SystemExit("Solver changed after initialization")
    if runtime_artifacts(Path(str(runtime["root"])), solver) != artifacts:
        raise SystemExit("Runtime binary, library, compiler, or OpenFOAM identity changed")


def run_config(args: argparse.Namespace) -> None:
    payload = json.loads(args.manifest.read_text())
    if payload.get("case_id") != "3d_kelvin" or payload.get("schema_version") != 3:
        raise SystemExit("Manifest is not the current Kelvin provenance schema")
    validate_recorded_runtime(payload)
    controls = control_values(args.control)
    chemistry = payload.get("chemistry")
    if not isinstance(chemistry, dict) or densities(args.thermo) != chemistry.get(
        "surface_master_densities_kmol_m2"
    ):
        raise SystemExit("Surface chemistry changed after initialization")
    require_realized_dictionaries(args.dictionary)
    expected_ranks = 1
    decomposition = {}
    for key in ("NPX", "NPY", "NPZ"):
        value = scalar_file(args.case / "system" / key)
        decomposition[key] = value
        expected_ranks *= value
    ranks = sorted(path for path in args.case.glob("processor*") if path.is_dir())
    if len(ranks) != expected_ranks:
        raise SystemExit(f"Expected {expected_ranks} ranks from decomposition, found {len(ranks)}")
    masters = []
    initial = []
    for rank in ranks:
        missing_fields = [name for name in REQUIRED_INITIAL_FIELDS if not (rank / "0" / name).is_file()]
        missing_mesh = [
            name for name in REQUIRED_POLYMESH_FILES
            if not (rank / "constant" / "polyMesh" / name).is_file()
        ]
        if missing_fields or missing_mesh:
            raise SystemExit(
                f"Incomplete initial rank inputs in {rank}: fields={missing_fields}, polyMesh={missing_mesh}"
            )
        for name, expected in (("Surf_s", 2e-7), ("Surf_w", 6e-6)):
            path = rank / "0" / name
            if uniform(path) != expected:
                raise SystemExit(f"Wrong master field: {path}")
            masters.append({**file_record(path), "value_kmol_m2": expected})
        for root in (rank / "0", rank / "constant" / "polyMesh"):
            initial.extend(file_record(path) for path in sorted(root.rglob("*")) if path.is_file())
    stage_base = f"{controls['startTime']:g}_to_{controls['endTime']:g}"
    attempt = 1
    while (args.snapshot_root / f"{stage_base}_attempt_{attempt:03d}").exists():
        attempt += 1
    stage_name = f"{stage_base}_attempt_{attempt:03d}"
    snapshots = snapshot_dictionaries(args.snapshot_root / stage_name, args.dictionary)
    stage = {
        **controls,
        "stage_id": stage_name,
        "attempt": attempt,
        "rank_count": expected_ranks,
        "decomposition": decomposition,
        "dictionaries": snapshots,
        "surface_master_fields": masters,
        "initial_rank_inputs": initial,
    }
    payload.setdefault("transport_stages", []).append(stage)
    args.manifest.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Updated {args.manifest} for stage {stage_name}")


def parser() -> argparse.ArgumentParser:
    main = argparse.ArgumentParser()
    sub = main.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--paper", type=Path, required=True)
    rec.add_argument("--runtime", type=Path, required=True)
    rec.add_argument("--expected-runtime-commit", required=True)
    rec.add_argument("--expected-runtime-tree", required=True)
    rec.add_argument("--expected-phreeqcrm-gitlink", required=True)
    rec.add_argument("--expected-phreeqcrm-commit", required=True)
    rec.add_argument("--expected-phreeqcrm-tree", required=True)
    rec.add_argument("--surface-log", type=Path, required=True)
    rec.add_argument("--intrinsic-log", type=Path, required=True)
    rec.add_argument("--mode", required=True)
    rec.add_argument("--sigma", type=float, required=True)
    rec.add_argument("--thermo", type=Path, required=True)
    rec.add_argument("--input", action="append", type=Path, default=[])
    rec.add_argument("--snapshot-root", type=Path, required=True)
    rec.add_argument("--dictionary", action="append", type=Path, default=[])
    rec.add_argument("--output", type=Path, required=True)
    rec.set_defaults(func=record)
    run = sub.add_parser("record-run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--case", type=Path, required=True)
    run.add_argument("--control", type=Path, required=True)
    run.add_argument("--thermo", type=Path, required=True)
    run.add_argument("--snapshot-root", type=Path, required=True)
    run.add_argument("--dictionary", action="append", type=Path, default=[])
    run.set_defaults(func=run_config)
    return main


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.func(arguments)
