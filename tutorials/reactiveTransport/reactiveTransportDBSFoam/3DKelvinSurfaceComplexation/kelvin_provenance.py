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
TRACKED_CONTROL_TEMPLATE = Path(
    "tutorials/reactiveTransport/reactiveTransportDBSFoam/"
    "3DKelvinSurfaceComplexation/system/controlDict1"
)
REALIZED_TRACKED_CASE_PATHS = (
    "tutorials/reactiveTransport/reactiveTransportDBSFoam/"
    "3DKelvinSurfaceComplexation/constant/thermoPhysicalProperties",
    "tutorials/reactiveTransport/reactiveTransportDBSFoam/"
    "3DKelvinSurfaceComplexation/constant/transportProperties",
    "tutorials/reactiveTransport/reactiveTransportDBSFoam/"
    "3DKelvinSurfaceComplexation/system/controlDict",
    "tutorials/reactiveTransport/reactiveTransportDBSFoam/"
    "3DKelvinSurfaceComplexation/system/fvSolution",
    "tutorials/reactiveTransport/reactiveTransportDBSFoam/"
    "3DKelvinSurfaceComplexation/system/postProcessDict",
)
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
SCHEMA_VERSION = 9


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
    diff = git_value(
        root,
        "diff", "--binary", "HEAD", "--ignore-submodules=all", "--", ".",
        *(f":(exclude){path}" for path in REALIZED_TRACKED_CASE_PATHS),
    )
    if diff:
        raise SystemExit("Kelvin paper/case source has tracked changes")
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
    case = Path.cwd().resolve()
    root = root if root.is_absolute() else case / root
    validate_case_path(root, case)
    if root.exists():
        raise SystemExit(f"Refusing to overwrite provenance snapshot: {root}")
    prepared: list[tuple[Path, Path]] = []
    for source in paths:
        if source.is_absolute() or ".." in source.parts:
            raise SystemExit(f"Realised dictionary path must be case-relative: {source}")
        source_path = case / source
        validate_case_artifact(source_path, case, expect_directory=False)
        destination = root / source
        validate_case_path(destination, case)
        prepared.append((source_path, destination))
    records = []
    for source_path, destination in prepared:
        destination.parent.mkdir(parents=True, exist_ok=True)
        validate_case_artifact(destination.parent, case, expect_directory=True)
        shutil.copyfile(source_path, destination)
        validate_case_artifact(destination, case, expect_directory=False)
        records.append(
            {
                "source": str(source_path.relative_to(case)),
                "snapshot": file_record(destination),
            }
        )
    return records


def require_snapshot_root(root: Path, case: Path, expected: Path) -> Path:
    candidate = root if root.is_absolute() else case / root
    validate_case_path(candidate, case)
    if candidate.resolve(strict=False) != expected.resolve(strict=False):
        raise SystemExit(f"Kelvin provenance snapshot root must be {expected}")
    return candidate


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
    case = Path.cwd().resolve()
    paper_root = args.paper.resolve()
    runtime_identity = runtime_from_args(args)
    artifacts = runtime_artifacts(runtime)
    require_realized_dictionaries(args.dictionary)
    snapshot_root = require_snapshot_root(
        args.snapshot_root, case, case / "provenance" / "initialization"
    )
    control_template = Path("system/controlDict1")
    local_template = case / control_template
    tracked_template = paper_root / TRACKED_CONTROL_TEMPLATE
    validate_case_artifact(local_template, case, expect_directory=False)
    validate_case_artifact(tracked_template, paper_root, expect_directory=False)
    if local_template.read_bytes() != tracked_template.read_bytes():
        raise SystemExit("Case-local controlDict1 differs from the tracked Kelvin template")
    paper = paper_identity(paper_root)
    snapshots = snapshot_dictionaries(snapshot_root, args.dictionary)
    payload = {
        "schema_version": SCHEMA_VERSION,
        "case_id": "3d_kelvin",
        "recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "paper": paper,
        "transport_control_template": file_record(control_template),
        "tracked_transport_control_template": file_record(tracked_template),
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
    text = strip_foam_comments(path.read_text(), path)
    values: dict[str, object] = {}
    required_words = {
        "application": "reactiveTransportDBSFoam",
        "startFrom": "startTime",
        "stopAt": "endTime",
        "writeControl": "adjustableRunTime",
        "writeFormat": "ascii",
        "writeCompression": "off",
        "timeFormat": "general",
        "runTimeModifiable": "yes",
    }
    for key, expected in required_words.items():
        matches = re.findall(rf"^\s*{key}\s+(\S+)\s*;", text, re.M)
        if len(matches) != 1 or matches[0] != expected:
            raise SystemExit(f"{path} must contain exactly one {key} {expected}")
        values[key] = expected
    required_integers = {"purgeWrite": 0, "writePrecision": 16, "timePrecision": 8}
    for key, expected in required_integers.items():
        matches = re.findall(rf"^\s*{key}\s+([+\-]?\d+)\s*;", text, re.M)
        if len(matches) != 1 or int(matches[0]) != expected:
            raise SystemExit(f"{path} must contain exactly one {key} {expected}")
        values[key] = expected
    for forbidden in ("adjustTimeStep", "maxCo"):
        if re.search(rf"^\s*{forbidden}\s+", text, re.M):
            raise SystemExit(f"{path} must not define {forbidden}")
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
    if not all(
        math.isfinite(float(values[key]))
        for key in ("startTime", "endTime", "deltaT", "writeInterval")
    ):
        raise SystemExit("Kelvin transport times and timestep must be finite")
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


def strip_foam_comments(text: str, path: Path) -> str:
    result = []
    index = 0
    block = False
    while index < len(text):
        pair = text[index:index + 2]
        if block:
            if pair == "*/":
                block = False
                index += 2
            else:
                result.append("\n" if text[index] == "\n" else " ")
                index += 1
        elif pair == "/*":
            block = True
            result.extend("  ")
            index += 2
        elif pair == "//":
            while index < len(text) and text[index] != "\n":
                result.append(" ")
                index += 1
        else:
            result.append(text[index])
            index += 1
    if block:
        raise SystemExit(f"Unterminated block comment in {path}")
    return "".join(result)


def canonical_control_contract(path: Path) -> str:
    text = strip_foam_comments(path.read_text(), path)
    if "#" in text:
        raise SystemExit(f"OpenFOAM preprocessing directives are forbidden in {path}")
    protected = (
        "application", "startFrom", "startTime", "stopAt", "endTime", "deltaT",
        "writeControl", "writeInterval", "purgeWrite", "writeFormat",
        "writePrecision", "writeCompression", "timeFormat", "timePrecision",
        "runTimeModifiable", "phreeqcRestartCheckpoints", "phreeqcRestoreCheckpoint",
    )
    for key in protected:
        count = len(re.findall(rf"(?<![A-Za-z0-9_]){key}\s+[^;]*;", text))
        if count != 1:
            raise SystemExit(f"Expected exactly one active {key} in {path}, found {count}")
    for key in (
        "startTime", "endTime", "deltaT", "writeInterval", "phreeqcRestoreCheckpoint",
    ):
        pattern = rf"(^\s*{key}\s+)[^;]+(;)"
        text, count = re.subn(pattern, rf"\1<stage-value>\2", text, flags=re.M)
        if count != 1:
            raise SystemExit(f"Cannot mask the singleton {key} in {path}")
    return " ".join(text.split())


def validate_control_template(control: Path, template: Path) -> None:
    if canonical_control_contract(control) != canonical_control_contract(template):
        raise SystemExit(f"{control} differs from the tracked Kelvin transport template")


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


def verify_dictionary_snapshots(
    records: object, case: Path, expected_root: Path
) -> None:
    if not isinstance(records, list) or len(records) != len(REQUIRED_REALIZED_DICTIONARIES):
        raise SystemExit("Manifest has no realised dictionary snapshots")
    case = case.resolve()
    expected_root = expected_root if expected_root.is_absolute() else case / expected_root
    validate_case_artifact(expected_root, case, expect_directory=True)
    seen = set()
    for record in records:
        if not isinstance(record, dict) or not isinstance(record.get("snapshot"), dict):
            raise SystemExit("Malformed realised dictionary snapshot")
        source = Path(str(record.get("source", "")))
        if source in seen or source not in REQUIRED_REALIZED_DICTIONARIES:
            raise SystemExit(f"Unexpected or duplicate realised dictionary source: {source}")
        seen.add(source)
        validate_case_artifact(case / source, case, expect_directory=False)
        snapshot = record["snapshot"]
        path = Path(str(snapshot.get("path", "")))
        expected_path = expected_root / source
        validate_case_artifact(expected_path, case, expect_directory=False)
        if (
            path != expected_path.resolve()
            or sha256(expected_path) != snapshot.get("sha256")
        ):
            raise SystemExit(f"Realised dictionary snapshot changed or disappeared: {path}")
    if seen != set(REQUIRED_REALIZED_DICTIONARIES):
        raise SystemExit("Realised dictionary snapshot source set is incomplete")


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
    symlinks = [name for name in expected if actual[name].is_symlink()]
    if symlinks:
        raise SystemExit(f"Kelvin processor directories must not be symlinks: {symlinks}")
    return [actual[name] for name in expected]


def numeric_time_directory(rank: Path, value: float) -> Path:
    matches = []
    for path in rank.iterdir():
        if not path.is_dir():
            continue
        if path.is_symlink():
            raise SystemExit(f"Kelvin time directory must not be a symlink: {path}")
        try:
            candidate = float(path.name)
        except ValueError:
            continue
        if math.isclose(candidate, value, rel_tol=0.0, abs_tol=1.0e-12):
            matches.append(path)
    if len(matches) != 1:
        raise SystemExit(f"Expected one time directory for {value:g} in {rank}, found {matches}")
    return matches[0]


def checkpoint_record(
    time_dir: Path, expected_time: float, case: Path, rank: str
) -> dict[str, object]:
    dump = time_dir / "phreeqc.dmp"
    marker = time_dir / "phreeqc.complete"
    pending = time_dir / "phreeqc.complete.tmp"
    for artifact in (dump, marker, pending):
        if artifact.is_symlink():
            raise SystemExit(f"Kelvin checkpoint artifact must not be a symlink: {artifact}")
    if pending.exists():
        raise SystemExit(f"Pending PHREEQCRM checkpoint marker exists: {pending}")
    if not dump.is_file() or not marker.is_file():
        raise SystemExit(f"Incomplete PHREEQCRM checkpoint pair in {time_dir}")
    try:
        marker_time = float(time_dir.name)
    except ValueError as error:
        raise SystemExit(f"Invalid PHREEQCRM checkpoint time directory: {time_dir}") from error
    if not math.isclose(marker_time, expected_time, rel_tol=0.0, abs_tol=1.0e-12):
        raise SystemExit(f"PHREEQCRM checkpoint time-directory mismatch in {marker}")
    dump_sha = sha256(dump)
    expected_marker = (
        f"PHREEQCRM and OpenFOAM fields written for time {time_dir.name}\n"
    ).encode("ascii")
    try:
        actual_marker = marker.read_bytes()
    except OSError as error:
        raise SystemExit(f"Unreadable PHREEQCRM checkpoint marker: {marker}") from error
    if actual_marker != expected_marker:
        raise SystemExit(
            f"PHREEQCRM checkpoint marker does not match the expected completion marker: {marker}"
        )
    expected_parent = case / rank / time_dir.name
    if time_dir != expected_parent:
        raise SystemExit(f"Kelvin checkpoint directory is not canonical: {time_dir}")
    try:
        dump_relative = dump.relative_to(case)
        marker_relative = marker.relative_to(case)
        dump.resolve().relative_to(case.resolve())
        marker.resolve().relative_to(case.resolve())
    except ValueError as error:
        raise SystemExit(f"Kelvin checkpoint path escapes the case: {time_dir}") from error
    return {
        "time": marker_time,
        "surface_model": "NO_EDL",
        "dump": {
            "path": str(dump_relative),
            "size": dump.stat().st_size,
            "sha256": dump_sha,
        },
        "marker": {
            "path": str(marker_relative),
            "size": marker.stat().st_size,
            "sha256": sha256(marker),
        },
    }


def tree_records(
    root: Path, case: Path, excluded: set[str] | None = None
) -> list[dict[str, object]]:
    validate_case_artifact(root, case, expect_directory=True)
    excluded = excluded or set()
    records = []
    for path in sorted(root.rglob("*")):
        validate_case_artifact(path, case, expect_directory=path.is_dir())
        if path.is_dir():
            continue
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


def validate_case_path(path: Path, case: Path) -> None:
    case = case.resolve()
    try:
        relative = path.relative_to(case)
    except ValueError as error:
        raise SystemExit(f"Kelvin artifact is outside the case: {path}") from error
    cursor = case
    for part in relative.parts:
        cursor = cursor / part
        if cursor.is_symlink():
            raise SystemExit(f"Kelvin artifact path contains a symlink: {cursor}")
    try:
        path.resolve(strict=False).relative_to(case)
    except ValueError as error:
        raise SystemExit(f"Kelvin artifact resolves outside the case: {path}") from error


def validate_case_artifact(
    path: Path, case: Path, *, expect_directory: bool
) -> None:
    validate_case_path(path, case)
    valid_type = path.is_dir() if expect_directory else path.is_file()
    if not valid_type:
        expected = "directory" if expect_directory else "regular file"
        raise SystemExit(f"Kelvin artifact is not a {expected}: {path}")


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
    if not same_attempt:
        raise SystemExit("An attempted Kelvin stage permits only an exact retry")
    return "retry"


def checkpoint_chain_identity(records: object) -> list[dict[str, object]]:
    if not isinstance(records, list):
        raise SystemExit("Malformed Kelvin checkpoint chain records")
    identities = []
    ranks = set()
    paths = set()
    for record in records:
        if not isinstance(record, dict):
            raise SystemExit("Malformed Kelvin checkpoint chain record")
        dump = record.get("dump")
        marker = record.get("marker")
        if not isinstance(dump, dict) or not isinstance(marker, dict):
            raise SystemExit("Malformed Kelvin checkpoint artifact record")
        rank = str(record.get("rank", ""))
        time_name = str(record.get("time_name", ""))
        dump_path = f"{rank}/{time_name}/phreeqc.dmp"
        marker_path = f"{rank}/{time_name}/phreeqc.complete"
        if dump.get("path") != dump_path or marker.get("path") != marker_path:
            raise SystemExit("Kelvin checkpoint record has a noncanonical path")
        if not re.fullmatch(r"processor\d+", rank) or not time_name:
            raise SystemExit("Kelvin checkpoint record has an invalid rank or time")
        try:
            named_time = float(time_name)
            recorded_time = float(record["time"])
            dump_size = int(dump["size"])
            marker_size = int(marker["size"])
        except (KeyError, TypeError, ValueError) as error:
            raise SystemExit("Kelvin checkpoint record has invalid identity values") from error
        if not math.isclose(named_time, recorded_time, rel_tol=0.0, abs_tol=1.0e-12):
            raise SystemExit("Kelvin checkpoint record time and path disagree")
        if record.get("surface_model") != "NO_EDL":
            raise SystemExit("Kelvin checkpoint record is not explicitly NO_EDL")
        if dump_size < 0 or marker_size <= 0:
            raise SystemExit("Kelvin checkpoint record has invalid artifact sizes")
        for artifact in (dump, marker):
            if not re.fullmatch(r"[0-9a-f]{64}", str(artifact.get("sha256", ""))):
                raise SystemExit("Kelvin checkpoint record has an invalid artifact hash")
        if rank in ranks or dump_path in paths or marker_path in paths:
            raise SystemExit("Kelvin checkpoint record has a duplicate rank or path")
        ranks.add(rank)
        paths.update((dump_path, marker_path))
        identities.append(
            {
                "rank": rank,
                "time": record.get("time"),
                "surface_model": record.get("surface_model"),
                "dump_path": dump_path,
                "dump_size": dump.get("size"),
                "dump_sha256": dump.get("sha256"),
                "marker_path": marker_path,
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


def validate_recorded_paper(payload: dict[str, object]) -> None:
    recorded = payload.get("paper")
    if not isinstance(recorded, dict):
        raise SystemExit("Manifest lacks Kelvin paper/case identity")
    if paper_identity(Path(str(recorded.get("root", "")))) != recorded:
        raise SystemExit("Kelvin paper/case identity changed after initialization")


def validate_control_template_record(payload: dict[str, object], template: Path) -> None:
    record = payload.get("transport_control_template")
    source_record = payload.get("tracked_transport_control_template")
    paper = payload.get("paper")
    if not isinstance(record, dict) or not isinstance(source_record, dict):
        raise SystemExit("Manifest lacks the Kelvin transport-control template records")
    if not isinstance(paper, dict):
        raise SystemExit("Manifest lacks Kelvin paper/case identity")
    case = template.parents[1]
    paper_root = Path(str(paper.get("root", "")))
    source = paper_root / TRACKED_CONTROL_TEMPLATE
    validate_case_artifact(template, case, expect_directory=False)
    validate_case_artifact(source, paper_root, expect_directory=False)
    if (
        Path(str(record.get("path", ""))) != template.resolve()
        or sha256(template) != record.get("sha256")
        or Path(str(source_record.get("path", ""))) != source.resolve()
        or sha256(source) != source_record.get("sha256")
        or template.read_bytes() != source.read_bytes()
    ):
        raise SystemExit("Kelvin transport-control templates changed after initialization")


def run_config(args: argparse.Namespace) -> None:
    payload = json.loads(args.manifest.read_text())
    if (
        payload.get("case_id") != "3d_kelvin"
        or payload.get("schema_version") != SCHEMA_VERSION
    ):
        raise SystemExit("Manifest is not the current Kelvin provenance schema")
    validate_recorded_runtime(payload)
    validate_recorded_paper(payload)
    control_template = args.case.resolve() / "system" / "controlDict1"
    validate_control_template_record(payload, control_template)
    validate_control_template(args.control, control_template)
    controls = control_values(args.control)
    control_identity = immutable_control_digest(args.control)
    chemistry = payload.get("chemistry")
    if not isinstance(chemistry, dict) or densities(args.thermo) != chemistry.get(
        "surface_master_densities_kmol_m2"
    ):
        raise SystemExit("Surface chemistry changed after initialization")
    verify_file_records(chemistry.get("files"))
    case = args.case.resolve()
    snapshot_root = require_snapshot_root(
        args.snapshot_root, case, case / "provenance" / "stages"
    )
    initialization_dictionaries = payload.get("realized_initialization_dictionaries")
    verify_dictionary_snapshots(
        initialization_dictionaries, case, case / "provenance" / "initialization"
    )
    stages = payload.get("transport_stages")
    if not isinstance(stages, list):
        raise SystemExit("Manifest has no transport stage list")
    for stage in stages:
        if not isinstance(stage, dict):
            raise SystemExit("Malformed Kelvin stage record")
        verify_dictionary_snapshots(
            stage.get("dictionaries"), case,
            case / "provenance" / "stages" / str(stage.get("stage_id", "")),
        )
    require_realized_dictionaries(args.dictionary)
    verify_initial_dictionary_anchors(initialization_dictionaries, args.dictionary)
    dictionary_identity = immutable_dictionary_digest(args.dictionary)
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
                    **checkpoint_record(start_dir, start_time, case, rank.name),
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
    while (snapshot_root / f"{stage_base}_attempt_{attempt:03d}").exists():
        attempt += 1
    stage_name = f"{stage_base}_attempt_{attempt:03d}"
    snapshots = snapshot_dictionaries(snapshot_root / stage_name, args.dictionary)
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
    validate_recorded_paper(payload)
    control_template = args.case.resolve() / "system" / "controlDict1"
    validate_control_template_record(payload, control_template)
    validate_control_template(args.control, control_template)
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
    case = args.case.resolve()
    initialization_dictionaries = payload.get("realized_initialization_dictionaries")
    verify_dictionary_snapshots(
        initialization_dictionaries, case, case / "provenance" / "initialization"
    )
    verify_dictionary_snapshots(
        stage.get("dictionaries"), case,
        case / "provenance" / "stages" / str(stage.get("stage_id", "")),
    )
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
                **checkpoint_record(endpoint_dir, endpoint, case, rank.name),
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
