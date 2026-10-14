#!/usr/bin/env python3
"""Fail closed unless the selected runtime is the reviewed production build."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import subprocess
from pathlib import Path


IDENTITY = Path(__file__).resolve().parent.parent / "production_runtime_identity.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.rstrip()


def load_identity(path: Path = IDENTITY) -> dict[str, object]:
    identity = json.loads(path.read_text())
    if identity.get("schema_version") not in (1, 2):
        raise SystemExit(f"Unsupported runtime identity schema: {path}")
    return identity


def resolved_library_paths(solver: Path) -> dict[str, Path]:
    output = subprocess.run(
        ["ldd", str(solver)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    resolved: dict[str, Path] = {}
    for line in output.splitlines():
        fields = line.strip().split()
        if "=>" not in fields:
            continue
        if len(fields) < 4 or fields[2] == "not":
            raise SystemExit(f"Unresolved solver library: {line.strip()}")
        resolved[fields[0]] = Path(fields[2]).resolve()
    return resolved


def verify_runtime(
    root: Path,
    identity_path: Path = IDENTITY,
    expected_solver: Path | None = None,
) -> dict[str, object]:
    root = root.resolve()
    identity = load_identity(identity_path)
    commit = git(root, "rev-parse", "HEAD")
    tree = git(root, "show", "-s", "--format=%T", "HEAD")
    if commit != identity["runtime_commit"] or tree != identity["runtime_tree"]:
        raise SystemExit(
            f"Runtime identity mismatch: commit={commit}, tree={tree}; "
            f"required commit={identity['runtime_commit']}, tree={identity['runtime_tree']}"
        )

    source_status = [
        line
        for line in git(root, "status", "--porcelain=v1", "--untracked-files=all").splitlines()
        if not (len(line) > 3 and line[:2] == " M" and line[3:] == "ThirdParty/PhreeqcRM")
    ]
    if source_status:
        raise SystemExit(f"Runtime source checkout is dirty: {source_status}")

    phreeqcrm_tree = git(root, "rev-parse", "HEAD:ThirdParty/PhreeqcRM")
    if identity["schema_version"] == 1:
        submodule = root / "ThirdParty" / "PhreeqcRM"
        submodule_commit = git(submodule, "rev-parse", "HEAD")
        required_submodule = identity["phreeqcrm_commit"]
        if phreeqcrm_tree != required_submodule or submodule_commit != required_submodule:
            raise SystemExit(
                "PhreeqcRM identity mismatch: "
                f"gitlink={phreeqcrm_tree}, checkout={submodule_commit}, required={required_submodule}"
            )
        tracked = git(submodule, "status", "--porcelain=v1", "--untracked-files=no")
        if tracked:
            raise SystemExit(f"PhreeqcRM tracked source is dirty: {tracked.splitlines()}")
    elif phreeqcrm_tree != identity["phreeqcrm_tree"]:
        raise SystemExit(
            "PhreeqcRM source tree mismatch: "
            f"tree={phreeqcrm_tree}, required={identity['phreeqcrm_tree']}"
        )

    artifacts = []
    for relative, required_hash in identity["artifacts"].items():
        path = root / relative
        if not path.is_file():
            raise SystemExit(f"Missing required runtime artifact: {path}")
        actual_hash = sha256(path)
        if actual_hash != required_hash:
            raise SystemExit(
                f"Runtime artifact hash mismatch for {relative}: "
                f"actual={actual_hash}, required={required_hash}"
            )
        artifacts.append(
            {"path": relative, "bytes": path.stat().st_size, "sha256": actual_hash}
        )

    solver = (root / "bin" / "reactiveScalarTransportDBSFoam").resolve()
    if expected_solver is not None and expected_solver.resolve() != solver:
        raise SystemExit(f"Wrong solver selected: {expected_solver}; required {solver}")
    resolved = resolved_library_paths(solver)
    required_resolutions = {
        "libreactionThermophysicalModelsGCFOAM.so": (
            root / "lib" / "libreactionThermophysicalModelsGCFOAM.so"
        ).resolve(),
        "libPhreeqcRM.so": (
            root / "ThirdParty" / "PhreeqcRM" / "lib" / "libPhreeqcRM.so"
        ).resolve(),
    }
    for name, required_path in required_resolutions.items():
        if resolved.get(name) != required_path:
            raise SystemExit(
                f"Solver resolves {name} to {resolved.get(name)}, required {required_path}"
            )

    return {
        "schema_version": identity["schema_version"],
        "validated_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runtime_root": str(root),
        "runtime_commit": commit,
        "runtime_tree": tree,
        "phreeqcrm_tree": phreeqcrm_tree,
        "required_identity": identity,
        "artifacts": artifacts,
        "resolved_required_libraries": {
            name: str(path) for name, path in required_resolutions.items()
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--runtime-root",
        type=Path,
        default=os.environ.get("GCFOAM_RUNTIME_ROOT") or os.environ.get("GCFOAM_DIR"),
    )
    parser.add_argument("--identity", type=Path, default=IDENTITY)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if args.runtime_root is None:
        raise SystemExit("Set GCFOAM_RUNTIME_ROOT/GCFOAM_DIR or pass --runtime-root")
    result = verify_runtime(args.runtime_root, args.identity)
    payload = json.dumps(result, indent=2, sort_keys=True) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(payload)
        print(f"Verified production runtime: {args.output}")
    else:
        print(payload, end="")


if __name__ == "__main__":
    main()
