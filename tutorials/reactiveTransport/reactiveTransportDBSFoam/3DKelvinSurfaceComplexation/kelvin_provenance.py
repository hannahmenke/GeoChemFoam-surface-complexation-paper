#!/usr/bin/env python3
"""Fail-closed provenance for the canonical Kelvin paper case."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import math
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
    Path("constant/dynamicMeshDict"),
    Path("constant/turbulenceProperties"),
    Path("system/postProcessDict"),
    Path("system/controlDict"),
    Path("system/fvSolution"),
    Path("system/fvSchemes"),
)
IDENTITY_ENV = (
    "FOAM_API", "WM_ARCH", "WM_COMPILER", "WM_COMPILER_TYPE",
    "WM_COMPILE_OPTION", "WM_LABEL_OPTION", "WM_MPLIB", "WM_OPTIONS",
    "WM_PRECISION_OPTION", "WM_PROJECT", "WM_PROJECT_VERSION",
)
SCHEMA_VERSION = 6


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


def solver_artifact(root: Path, name: str) -> dict[str, object]:
    selected = shutil.which(name)
    expected = (root / "bin" / name).resolve()
    if selected is None or Path(selected).resolve() != expected:
        raise SystemExit(f"Wrong {name} executable: {selected or 'not found'} != {expected}")
    return {
        "executable": file_record(expected),
        "resolved_dependencies": parse_ldd(command("ldd", str(expected))),
    }


def runtime_artifacts(root: Path) -> dict[str, object]:
    environment = {key: os.environ.get(key, "") for key in IDENTITY_ENV}
    missing = [key for key, value in environment.items() if not value]
    if missing:
        raise SystemExit(f"Missing compiler/OpenFOAM identity variables: {missing}")
    payload = {
        "solvers": {
            name: solver_artifact(root, name)
            for name in ("simpleDBSFoam", "reactiveTransportDBSFoam")
        },
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
    required = set(REQUIRED_REALIZED_DICTIONARIES)
    supplied = set(paths)
    if supplied != required or len(paths) != len(required):
        raise SystemExit(
            "Realised dictionary set differs from the required Kelvin set: "
            f"missing={sorted(required - supplied)}, extra={sorted(supplied - required)}"
        )


def immutable_dictionary_digest(paths: list[Path]) -> str:
    records = [
        {"path": str(path), "sha256": sha256(path)}
        for path in sorted(paths)
        if path != Path("system/controlDict")
    ]
    return records_digest(records)


def runtime_from_args(args: argparse.Namespace) -> dict[str, object]:
    return runtime_git_identity(
        args.runtime, args.expected_runtime_commit, args.expected_runtime_tree,
        args.expected_phreeqcrm_gitlink, args.expected_phreeqcrm_commit,
        args.expected_phreeqcrm_tree,
    )


def record(args: argparse.Namespace) -> None:
    runtime = args.runtime.resolve()
    runtime_identity = runtime_from_args(args)
    artifacts = runtime_artifacts(runtime)
    require_realized_dictionaries(args.dictionary)
    snapshots = snapshot_dictionaries(args.snapshot_root, args.dictionary)
    payload = {
        "schema_version": SCHEMA_VERSION,
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
    start_from = re.findall(r"^\s*startFrom\s+(\S+)\s*;", text, re.M)
    if len(start_from) != 1 or start_from[0] != "startTime":
        raise SystemExit(f"{path} must use startFrom startTime")
    values["startFrom"] = "startTime"
    for key in ("startTime", "endTime", "deltaT", "writeInterval"):
        matches = re.findall(rf"^\s*{key}\s+([0-9.eE+\-]+)\s*;", text, re.M)
        if len(matches) != 1:
            raise SystemExit(f"Expected exactly one numeric {key} in {path}")
        values[key] = float(matches[0])
    for key in ("phreeqcRestartCheckpoints", "phreeqcRestoreCheckpoint"):
        matches = re.findall(rf"^\s*{key}\s+(true|false)\s*;", text, re.M)
        if len(matches) != 1:
            raise SystemExit(f"Expected exactly one boolean {key} in {path}")
        values[key] = matches[0] == "true"
    if values["endTime"] <= values["startTime"]:
        raise SystemExit("endTime must be greater than startTime")
    if values["deltaT"] <= 0 or values["writeInterval"] <= 0:
        raise SystemExit("deltaT and writeInterval must be positive")
    if not math.isclose(
        float(values["writeInterval"]),
        float(values["endTime"]) - float(values["startTime"]),
        rel_tol=0.0,
        abs_tol=1.0e-12,
    ):
        raise SystemExit("writeInterval must equal endTime - startTime")
    return values


def immutable_control_digest(path: Path) -> str:
    text = path.read_text()
    for key in ("startTime", "endTime", "writeInterval", "phreeqcRestoreCheckpoint"):
        pattern = rf"(^\s*{key}\s+)[^;]+(;)"
        text, count = re.subn(pattern, rf"\1<stage-value>\2", text, flags=re.M)
        if count != 1:
            raise SystemExit(f"Expected exactly one {key} in {path}, found {count}")
    return sha256_text(text)


def verify_file_records(records: object) -> None:
    if not isinstance(records, list) or not records:
        raise SystemExit("Manifest has no immutable input records")
    for record in records:
        if not isinstance(record, dict):
            raise SystemExit("Malformed immutable input record")
        path = Path(str(record.get("path", "")))
        if not path.is_file() or sha256(path) != record.get("sha256"):
            raise SystemExit(f"Immutable case input changed or disappeared: {path}")


def verify_dictionary_snapshots(records: object) -> None:
    if not isinstance(records, list) or not records:
        raise SystemExit("Manifest has no realised dictionary snapshots")
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("snapshot"), dict):
            raise SystemExit("Malformed realised dictionary snapshot")
        snapshot = record["snapshot"]
        path = Path(str(snapshot.get("path", "")))
        if not path.is_file() or sha256(path) != snapshot.get("sha256"):
            raise SystemExit(f"Realised dictionary snapshot changed or disappeared: {path}")


def verify_initial_dictionary_anchors(records: object, current: list[Path]) -> None:
    if not isinstance(records, list):
        raise SystemExit("Manifest has no initialization dictionary anchors")
    anchors = {}
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("snapshot"), dict):
            raise SystemExit("Malformed initialization dictionary anchor")
        source = Path(str(record.get("source", "")))
        snapshot = Path(str(record["snapshot"].get("path", "")))
        if source in anchors:
            raise SystemExit(f"Duplicate initialization dictionary anchor: {source}")
        anchors[source] = snapshot
    if set(anchors) != set(REQUIRED_REALIZED_DICTIONARIES):
        raise SystemExit("Initialization dictionary anchors are incomplete")
    for path in current:
        snapshot = anchors[path]
        if path == Path("system/controlDict"):
            # Initialization follows the flow stage.  The first transport
            # attempt establishes the transport-control anchor; later stages
            # are pinned to that recorded digest by validate_stage_invariants.
            continue
        matches = sha256(path) == sha256(snapshot)
        if not matches:
            raise SystemExit(f"Realised dictionary drifted from initialization: {path}")


def exact_ranks(case: Path, count: int) -> list[Path]:
    if count <= 0:
        raise SystemExit("Kelvin decomposition entries must be positive")
    actual = {path.name: path for path in case.glob("processor*") if path.is_dir()}
    expected = [f"processor{rank}" for rank in range(count)]
    if set(actual) != set(expected):
        raise SystemExit(
            f"Kelvin processor directories are not contiguous: expected={expected}, "
            f"actual={sorted(actual)}"
        )
    return [actual[name] for name in expected]


def numeric_time_directory(rank: Path, value: float) -> Path:
    matches = []
    for path in rank.iterdir():
        if not path.is_dir():
            continue
        try:
            candidate = float(path.name)
        except ValueError:
            continue
        if math.isclose(candidate, value, rel_tol=0.0, abs_tol=1.0e-12):
            matches.append(path)
    if len(matches) != 1:
        raise SystemExit(f"Expected one time directory for {value:g} in {rank}, found {matches}")
    return matches[0]


def checkpoint_record(time_dir: Path, expected_time: float) -> dict[str, object]:
    dump = time_dir / "phreeqc.dmp"
    marker = time_dir / "phreeqc.complete"
    pending = time_dir / "phreeqc.complete.tmp"
    if pending.exists():
        raise SystemExit(f"Pending PHREEQCRM checkpoint marker exists: {pending}")
    if not dump.is_file() or not marker.is_file():
        raise SystemExit(f"Incomplete PHREEQCRM checkpoint pair in {time_dir}")
    lines = marker.read_text().splitlines()
    if len(lines) != 4 or lines[0] != "GeoChemFoam-PHREEQCRM-checkpoint 1":
        raise SystemExit(f"Malformed PHREEQCRM checkpoint marker: {marker}")
    parsed: dict[str, str] = {}
    for line in lines[1:]:
        parts = line.split(maxsplit=1)
        if len(parts) != 2 or parts[0] in parsed:
            raise SystemExit(f"Malformed PHREEQCRM checkpoint marker: {marker}")
        parsed[parts[0]] = parts[1]
    if set(parsed) != {"time", "dumpSize", "dumpSHA256"}:
        raise SystemExit(f"Incomplete PHREEQCRM checkpoint marker: {marker}")
    try:
        marker_time = float(parsed["time"])
        marker_size = int(parsed["dumpSize"])
    except ValueError as error:
        raise SystemExit(f"Invalid PHREEQCRM checkpoint marker values: {marker}") from error
    if not math.isclose(marker_time, expected_time, rel_tol=0.0, abs_tol=1.0e-12):
        raise SystemExit(f"PHREEQCRM checkpoint time mismatch in {marker}")
    if dump.stat().st_size != marker_size:
        raise SystemExit(f"PHREEQCRM checkpoint size mismatch in {marker}")
    dump_sha = sha256(dump)
    if dump_sha != parsed["dumpSHA256"]:
        raise SystemExit(f"PHREEQCRM checkpoint hash mismatch in {marker}")
    return {
        "time": marker_time,
        "dump": {
            "path": str(dump.resolve()),
            "size": dump.stat().st_size,
            "sha256": dump_sha,
        },
        "marker": {**file_record(marker), "size": marker.stat().st_size},
    }


def tree_records(
    root: Path, case: Path, excluded: set[str] | None = None
) -> list[dict[str, object]]:
    excluded = excluded or set()
    records = []
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        if path.name in excluded:
            continue
        records.append(
            {
                "path": str(path.relative_to(case)),
                "size": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return records


def records_digest(records: list[dict[str, object]]) -> str:
    return sha256_text(json.dumps(records, sort_keys=True, separators=(",", ":")))


def validate_stage_invariants(
    payload: dict[str, object],
    controls: dict[str, object],
    rank_count: int,
    decomposition: dict[str, int],
    initial_identity: str,
    dictionary_identity: str,
    control_identity: str,
) -> str:
    stages = payload.get("transport_stages")
    if not isinstance(stages, list):
        raise SystemExit("Manifest has no transport stage list")
    start = float(controls["startTime"])
    restore = bool(controls["phreeqcRestoreCheckpoint"])
    if not controls["phreeqcRestartCheckpoints"]:
        raise SystemExit("Kelvin production stages require restart checkpoints")
    if math.isclose(start, 0.0, rel_tol=0.0, abs_tol=1.0e-12):
        if restore:
            raise SystemExit("The initial Kelvin stage must not restore a checkpoint")
    elif not restore:
        raise SystemExit("A nonzero Kelvin stage must restore its start checkpoint")
    if not stages:
        if not math.isclose(start, 0.0, rel_tol=0.0, abs_tol=1.0e-12):
            raise SystemExit("The first recorded Kelvin stage must start at zero")
        return "initial"
    first = stages[0]
    if not isinstance(first, dict):
        raise SystemExit("Malformed first Kelvin stage record")
    invariant_pairs = (
        (float(controls["deltaT"]), float(first["deltaT"]), "deltaT"),
        (rank_count, int(first["rank_count"]), "rank count"),
        (decomposition, first["decomposition"], "decomposition"),
        (initial_identity, first["initial_case_identity_sha256"], "initial case identity"),
        (dictionary_identity, first["immutable_dictionary_sha256"], "immutable dictionaries"),
        (control_identity, first["immutable_control_sha256"], "immutable control settings"),
    )
    for actual, expected, label in invariant_pairs:
        if actual != expected:
            raise SystemExit(f"Kelvin stage {label} changed: {actual} != {expected}")
    previous = stages[-1]
    if not isinstance(previous, dict):
        raise SystemExit("Malformed previous Kelvin stage record")
    status = previous.get("status")
    previous_start = float(previous["startTime"])
    previous_end = float(previous["endTime"])
    same_attempt = (
        previous_start == start
        and previous_end == float(controls["endTime"])
    )
    if status == "completed":
        if not math.isclose(start, previous_end, rel_tol=0.0, abs_tol=1.0e-12):
            raise SystemExit("Kelvin stage backtracks or skips the last completed endpoint")
        return "continuation"
    if status != "attempted":
        raise SystemExit("Previous Kelvin stage has an invalid lifecycle status")
    if same_attempt:
        return "retry"
    if start <= previous_start or start >= previous_end:
        raise SystemExit(
            "Interrupted Kelvin stage recovery must start within its attempted interval"
        )
    if float(controls["endTime"]) != previous_end:
        raise SystemExit("Interrupted Kelvin recovery must preserve the attempted endpoint")
    return "recovery"


def checkpoint_chain_identity(records: object) -> list[dict[str, object]]:
    if not isinstance(records, list):
        raise SystemExit("Malformed Kelvin checkpoint chain records")
    identities = []
    for record in records:
        if not isinstance(record, dict):
            raise SystemExit("Malformed Kelvin checkpoint chain record")
        dump = record.get("dump")
        marker = record.get("marker")
        if not isinstance(dump, dict) or not isinstance(marker, dict):
            raise SystemExit("Malformed Kelvin checkpoint artifact record")
        rank = str(record.get("rank", ""))
        time_name = str(record.get("time_name", ""))
        identities.append(
            {
                "rank": rank,
                "time": record.get("time"),
                "dump_path": f"{rank}/{time_name}/phreeqc.dmp",
                "dump_size": dump.get("size"),
                "dump_sha256": dump.get("sha256"),
                "marker_path": f"{rank}/{time_name}/phreeqc.complete",
                "marker_size": marker.get("size"),
                "marker_sha256": marker.get("sha256"),
            }
        )
    return sorted(identities, key=lambda item: str(item["rank"]))


def validate_start_handoff(
    relation: str,
    start_records: list[dict[str, object]],
    checkpoints: list[dict[str, object]],
    previous: object,
) -> None:
    if relation not in {"continuation", "retry"}:
        return
    if not isinstance(previous, dict):
        raise SystemExit("Missing authoritative Kelvin handoff stage")
    if relation == "continuation":
        authoritative_fields = previous.get("endpoint_rank_outputs")
        authoritative_checkpoints = previous.get("endpoint_checkpoints")
    else:
        authoritative_fields = previous.get("start_rank_inputs")
        authoritative_checkpoints = previous.get("restart_checkpoints")
    if start_records != authoritative_fields:
        raise SystemExit("Kelvin start fields do not match the authoritative prior state")
    if checkpoint_chain_identity(checkpoints) != checkpoint_chain_identity(
        authoritative_checkpoints
    ):
        raise SystemExit("Kelvin start checkpoint does not match the authoritative prior state")


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
    if runtime_artifacts(Path(str(runtime["root"]))) != artifacts:
        raise SystemExit("Runtime binary, library, compiler, or OpenFOAM identity changed")


def run_config(args: argparse.Namespace) -> None:
    payload = json.loads(args.manifest.read_text())
    if (
        payload.get("case_id") != "3d_kelvin"
        or payload.get("schema_version") != SCHEMA_VERSION
    ):
        raise SystemExit("Manifest is not the current Kelvin provenance schema")
    validate_recorded_runtime(payload)
    controls = control_values(args.control)
    control_identity = immutable_control_digest(args.control)
    chemistry = payload.get("chemistry")
    if not isinstance(chemistry, dict) or densities(args.thermo) != chemistry.get(
        "surface_master_densities_kmol_m2"
    ):
        raise SystemExit("Surface chemistry changed after initialization")
    verify_file_records(chemistry.get("files"))
    initialization_dictionaries = payload.get("realized_initialization_dictionaries")
    verify_dictionary_snapshots(initialization_dictionaries)
    stages = payload.get("transport_stages")
    if not isinstance(stages, list):
        raise SystemExit("Manifest has no transport stage list")
    for stage in stages:
        if not isinstance(stage, dict):
            raise SystemExit("Malformed Kelvin stage record")
        verify_dictionary_snapshots(stage.get("dictionaries"))
    require_realized_dictionaries(args.dictionary)
    verify_initial_dictionary_anchors(initialization_dictionaries, args.dictionary)
    dictionary_identity = immutable_dictionary_digest(args.dictionary)
    case = args.case.resolve()
    expected_ranks = 1
    decomposition = {}
    for key in ("NPX", "NPY", "NPZ"):
        value = scalar_file(case / "system" / key)
        decomposition[key] = value
        expected_ranks *= value
    ranks = exact_ranks(case, expected_ranks)
    start_time = float(controls["startTime"])
    masters = []
    initial_records = []
    start_records = []
    start_directories = []
    checkpoints = []
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
        initial_records.extend(tree_records(rank / "0", case))
        initial_records.extend(tree_records(rank / "constant" / "polyMesh", case))
        start_dir = numeric_time_directory(rank, start_time)
        start_directories.append(
            {"rank": rank.name, "path": str(start_dir.resolve()), "time_name": start_dir.name}
        )
        missing_start = [name for name in REQUIRED_INITIAL_FIELDS if not (start_dir / name).is_file()]
        if missing_start:
            raise SystemExit(f"Incomplete restart fields in {start_dir}: {missing_start}")
        for name, expected in (("Surf_s", 2e-7), ("Surf_w", 6e-6)):
            path = start_dir / name
            if uniform(path) != expected:
                raise SystemExit(f"Wrong master field: {path}")
            masters.append({**file_record(path), "value_kmol_m2": expected})
        start_records.extend(
            tree_records(
                start_dir,
                case,
                {"phreeqc.dmp", "phreeqc.complete", "phreeqc.complete.tmp"},
            )
        )
        if math.isclose(start_time, 0.0, rel_tol=0.0, abs_tol=1.0e-12):
            stale = [
                start_dir / name
                for name in ("phreeqc.dmp", "phreeqc.complete", "phreeqc.complete.tmp")
                if (start_dir / name).exists()
            ]
            if stale:
                raise SystemExit(f"Stale checkpoint files in fresh-start directory: {stale}")
        else:
            checkpoints.append(
                {
                    "rank": rank.name,
                    "time_name": start_dir.name,
                    **checkpoint_record(start_dir, start_time),
                }
            )
    initial_identity = records_digest(initial_records)
    chain_relation = validate_stage_invariants(
        payload,
        controls,
        expected_ranks,
        decomposition,
        initial_identity,
        dictionary_identity,
        control_identity,
    )
    previous_stage = stages[-1] if stages else None
    validate_start_handoff(
        chain_relation, start_records, checkpoints, previous_stage
    )
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
        "status": "attempted",
        "chain_relation": chain_relation,
        "recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "rank_count": expected_ranks,
        "decomposition": decomposition,
        "initial_case_identity_sha256": initial_identity,
        "immutable_dictionary_sha256": dictionary_identity,
        "immutable_control_sha256": control_identity,
        "dictionaries": snapshots,
        "surface_master_fields": masters,
        "selected_start_time_directories": start_directories,
        "start_rank_inputs": start_records,
        "restart_checkpoints": checkpoints,
    }
    if not payload["transport_stages"]:
        payload["initial_case"] = {
            "sha256": initial_identity,
            "records": initial_records,
        }
    payload.setdefault("transport_stages", []).append(stage)
    args.manifest.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Updated {args.manifest} for stage {stage_name}")


def clean_solver_log(path: Path, endpoint: float) -> dict[str, str]:
    if not path.is_file():
        raise SystemExit(f"Missing Kelvin solver log: {path}")
    text = path.read_text(errors="replace")
    if re.search(r"FOAM FATAL|MPI_ABORT|Segmentation fault|Floating point exception", text):
        raise SystemExit(f"Kelvin solver log contains a fatal error: {path}")
    times = list(re.finditer(r"^\s*Time\s*=\s*([0-9.eE+\-]+)\s*$", text, re.M))
    if not times or not math.isclose(
        float(times[-1].group(1)), endpoint, rel_tol=0.0, abs_tol=1.0e-12
    ):
        raise SystemExit(f"Kelvin solver log does not reach endpoint {endpoint:g}: {path}")
    ends = list(re.finditer(r"^\s*End\s*$", text, re.M))
    if not ends or ends[-1].start() < times[-1].start():
        raise SystemExit(f"Kelvin solver log has no clean End after its endpoint: {path}")
    return file_record(path)


def finalise_run(args: argparse.Namespace) -> None:
    payload = json.loads(args.manifest.read_text())
    if (
        payload.get("case_id") != "3d_kelvin"
        or payload.get("schema_version") != SCHEMA_VERSION
    ):
        raise SystemExit("Manifest is not the current Kelvin provenance schema")
    validate_recorded_runtime(payload)
    controls = control_values(args.control)
    stages = payload.get("transport_stages")
    if not isinstance(stages, list) or not stages or not isinstance(stages[-1], dict):
        raise SystemExit("Manifest has no Kelvin stage to finalise")
    stage = stages[-1]
    if stage.get("status") != "attempted":
        raise SystemExit("Latest Kelvin stage is not an uncompleted attempt")
    chemistry = payload.get("chemistry")
    if not isinstance(chemistry, dict):
        raise SystemExit("Manifest has no immutable Kelvin inputs")
    verify_file_records(chemistry.get("files"))
    initialization_dictionaries = payload.get("realized_initialization_dictionaries")
    verify_dictionary_snapshots(initialization_dictionaries)
    verify_dictionary_snapshots(stage.get("dictionaries"))
    dictionaries = list(REQUIRED_REALIZED_DICTIONARIES)
    verify_initial_dictionary_anchors(initialization_dictionaries, dictionaries)
    if immutable_dictionary_digest(dictionaries) != stage.get("immutable_dictionary_sha256"):
        raise SystemExit("Kelvin immutable dictionaries changed before finalisation")
    if immutable_control_digest(args.control) != stage.get("immutable_control_sha256"):
        raise SystemExit("Kelvin immutable control settings changed before finalisation")
    for key in (
        "startFrom", "startTime", "endTime", "deltaT", "writeInterval",
        "phreeqcRestartCheckpoints", "phreeqcRestoreCheckpoint",
    ):
        if controls[key] != stage.get(key):
            raise SystemExit(f"Kelvin controls changed before finalisation: {key}")
    endpoint = float(controls["endTime"])
    log_record = clean_solver_log(args.solver_log, endpoint)
    case = args.case.resolve()
    decomposition = {
        key: scalar_file(case / "system" / key) for key in ("NPX", "NPY", "NPZ")
    }
    if decomposition != stage.get("decomposition"):
        raise SystemExit("Kelvin decomposition changed before finalisation")
    ranks = exact_ranks(case, int(stage["rank_count"]))
    initial_records = []
    for rank in ranks:
        initial_records.extend(tree_records(rank / "0", case))
        initial_records.extend(tree_records(rank / "constant" / "polyMesh", case))
    if records_digest(initial_records) != stage.get("initial_case_identity_sha256"):
        raise SystemExit("Kelvin initial fields or mesh changed before finalisation")
    outputs = []
    checkpoints = []
    endpoint_directories = []
    for rank in ranks:
        endpoint_dir = numeric_time_directory(rank, endpoint)
        endpoint_directories.append(
            {"rank": rank.name, "path": str(endpoint_dir.resolve()), "time_name": endpoint_dir.name}
        )
        missing = [
            name for name in REQUIRED_INITIAL_FIELDS if not (endpoint_dir / name).is_file()
        ]
        if missing:
            raise SystemExit(f"Incomplete Kelvin endpoint fields in {endpoint_dir}: {missing}")
        outputs.extend(
            tree_records(
                endpoint_dir,
                case,
                {"phreeqc.dmp", "phreeqc.complete", "phreeqc.complete.tmp"},
            )
        )
        checkpoints.append(
            {
                "rank": rank.name,
                "time_name": endpoint_dir.name,
                **checkpoint_record(endpoint_dir, endpoint),
            }
        )
    stage.update(
        {
            "status": "completed",
            "solver_exit_status": 0,
            "completed_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "solver_log": log_record,
            "endpoint_time_directories": endpoint_directories,
            "endpoint_rank_outputs": outputs,
            "endpoint_checkpoints": checkpoints,
        }
    )
    args.manifest.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Finalised {stage['stage_id']} in {args.manifest}")


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
    finalise = sub.add_parser("finalise-run")
    finalise.add_argument("--manifest", type=Path, required=True)
    finalise.add_argument("--case", type=Path, required=True)
    finalise.add_argument("--control", type=Path, required=True)
    finalise.add_argument("--solver-log", type=Path, required=True)
    finalise.set_defaults(func=finalise_run)
    return main


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.func(arguments)
