#!/usr/bin/env python3
"""Record reproducible inputs and checkpoints for a matched DBS run."""

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

from verify_production_runtime import verify_runtime


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def record(path: Path, root: Path) -> dict[str, object]:
    return {
        "path": str(path.resolve().relative_to(root.resolve())),
        "bytes": path.stat().st_size,
        "sha256": sha256(path),
    }


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout.rstrip()


def allowed_phreeqcrm_artifact(root: Path, relative: str) -> bool:
    path = root / relative
    if relative == "lib/libPhreeqcRM.so":
        return path.is_file()
    if re.fullmatch(
        r"src/Make/[^/]+/(?:.+\.(?:dep|o)|options|sourceFiles|variables)",
        relative,
    ):
        return path.is_file()
    return relative.startswith("src/lnInclude/") and path.is_symlink()


def runtime_state(root: Path) -> dict[str, object]:
    raw_status = git(
        root, "status", "--porcelain=v1", "--untracked-files=all"
    ).splitlines()
    source_status = [
        line
        for line in raw_status
        if not (
            len(line) > 3
            and line[0] == " "
            and line[1] in {"M", "?"}
            and line[3:] == "ThirdParty/PhreeqcRM"
        )
    ]
    if source_status:
        raise SystemExit(f"Runtime top-level source checkout is dirty: {source_status}")

    submodule = root / "ThirdParty" / "PhreeqcRM"
    expected_commit = git(root, "rev-parse", "HEAD:ThirdParty/PhreeqcRM")
    actual_commit = git(submodule, "rev-parse", "HEAD")
    if actual_commit != expected_commit:
        raise SystemExit(
            f"PhreeqcRM commit {actual_commit} does not match gitlink {expected_commit}"
        )
    tracked_status = git(
        submodule, "status", "--porcelain=v1", "--untracked-files=no"
    ).splitlines()
    if tracked_status:
        raise SystemExit(f"PhreeqcRM tracked source is dirty: {tracked_status}")

    build_status = git(
        submodule, "status", "--porcelain=v1", "--untracked-files=all"
    ).splitlines()
    unexpected = [
        line
        for line in build_status
        if not (line.startswith("?? ") and allowed_phreeqcrm_artifact(submodule, line[3:]))
    ]
    if unexpected:
        raise SystemExit(f"Unexpected PhreeqcRM worktree artifacts: {unexpected}")
    return {
        "root": str(root.resolve()),
        "commit": git(root, "rev-parse", "HEAD"),
        "tree": git(root, "show", "-s", "--format=%T", "HEAD"),
        "source_status": source_status,
        "raw_top_level_status": raw_status,
        "phreeqcrm": {
            "root": str(submodule.resolve()),
            "commit": actual_commit,
            "gitlink_commit": expected_commit,
            "tracked_source_status": tracked_status,
            "allowed_build_artifacts": [
                {"status": line[:2], "path": line[3:]} for line in build_status
            ],
        },
    }


def resolved_libraries(executable: Path) -> list[dict[str, object]]:
    output = subprocess.run(
        ["ldd", str(executable)],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
    ).stdout
    libraries = []
    for line in output.splitlines():
        fields = line.strip().split()
        if not fields or fields[0] == "linux-vdso.so.1":
            continue
        if "=>" in fields:
            if fields[2] == "not":
                raise SystemExit(f"Unresolved solver library: {line.strip()}")
            name, path_text = fields[0], fields[2]
        elif fields[0].startswith("/"):
            name, path_text = Path(fields[0]).name, fields[0]
        else:
            continue
        path = Path(path_text).resolve()
        if not path.is_file():
            raise SystemExit(f"Resolved solver library is not a file: {path}")
        libraries.append(
            {
                "name": name,
                "path": str(path),
                "bytes": path.stat().st_size,
                "sha256": sha256(path),
            }
        )
    return libraries


def read_env(path: Path) -> dict[str, str]:
    values = {}
    for line in path.read_text().splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            values[key] = value
    return values


def case_files(case_dir: Path, time_name: str) -> list[Path]:
    processors = sorted(
        case_dir.glob("processor*"),
        key=lambda path: int(path.name.removeprefix("processor")),
    )
    roots = processors or [case_dir]
    return [
        path
        for root in roots
        for path in sorted((root / time_name).glob("*"))
        if path.is_file()
    ]


def initial_payload(case_dir: Path, run_root: Path) -> dict[str, object]:
    matched = []
    surface = []
    processors = sorted(
        case_dir.glob("processor*"),
        key=lambda path: int(path.name.removeprefix("processor")),
    )
    roots = processors or [case_dir]
    for root in roots:
        for path in sorted((root / "0").glob("*")):
            if not path.is_file() or path.name.startswith("phreeqc"):
                continue
            (surface if path.name == "aSurf" else matched).append(record(path, run_root))
        mesh = root / "constant" / "polyMesh"
        matched.extend(record(path, run_root) for path in sorted(mesh.glob("*")) if path.is_file())

    for relative in (
        "constant/phreeqcReactions",
        "constant/thermoPhysicalProperties",
        "constant/transportProperties",
        "system/controlDict",
        "system/fvSchemes",
        "system/fvSolution",
    ):
        path = case_dir / relative
        if path.is_file():
            matched.append(record(path, run_root))
    for path in sorted((run_root / "shared").glob("**/*")):
        if path.is_file():
            matched.append(record(path, run_root))

    logs = sorted(case_dir.glob("createASurfReactive*.out"))
    log_records = [record(path, run_root) for path in logs]
    modes = set()
    integrated_area = 0.0
    area_records = 0
    for path in logs:
        text = path.read_text()
        if match := re.search(r"(?:\bmode=|\bexternal=)([^\s,]+)", text):
            modes.add(match.group(1))
        if match := re.search(r"\bsum\(aSurf\*V\)=([0-9.eE+-]+)", text):
            integrated_area += float(match.group(1))
            area_records += 1
    expected_mode = os.environ["ASURF_SURFACE_MODE"]
    if not logs or len(surface) != len(roots):
        raise SystemExit("Missing per-partition aSurf fields or construction logs")
    if modes != {expected_mode}:
        raise SystemExit(f"Surface logs report {sorted(modes)}, expected {expected_mode}")
    if area_records != len(logs):
        raise SystemExit("A surface construction log lacks sum(aSurf*V)")

    return {
        "matched_input_files": matched,
        "surface_field_files": surface,
        "surface_log_files": log_records,
        "surface_log_modes": sorted(modes),
        "logged_external_surface_area_m2": integrated_area,
    }


def complete_time(case_dir: Path) -> tuple[str, int]:
    processors = sorted(case_dir.glob("processor*"))
    roots = processors or [case_dir]
    candidates = []
    for path in roots[0].iterdir():
        if path.is_dir():
            try:
                candidates.append((float(path.name), path.name))
            except ValueError:
                pass
    for _, name in sorted(candidates, reverse=True):
        if all((root / name / "phreeqc.dmp").is_file() and (root / name / "phreeqc.complete").is_file() for root in roots):
            return name, len(roots)
    raise SystemExit(f"No complete PHREEQC checkpoint found in {case_dir}")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--phase", choices=("initial", "final"), required=True)
    parser.add_argument("--case-dir", type=Path, required=True)
    parser.add_argument("--run-config", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    label = os.environ["SURFACE_RECONSTRUCTION_LABEL"]
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*", label):
        raise SystemExit(f"Invalid SURFACE_RECONSTRUCTION_LABEL: {label}")
    run_root = args.case_dir.resolve().parent
    output = args.output.resolve()
    if args.phase == "initial":
        solver = shutil.which("reactiveTransportDBSFoam")
        if solver is None:
            raise SystemExit("reactiveTransportDBSFoam is not on PATH")
        runtime_root = Path(
            os.environ.get("GCFOAM_RUNTIME_ROOT", Path(solver).resolve().parent.parent)
        )
        runtime = runtime_state(runtime_root)
        expected_solver = runtime_root / "bin" / "reactiveTransportDBSFoam"
        if Path(solver).resolve() != expected_solver.resolve():
            raise SystemExit(f"Wrong solver selected: {solver}; expected {expected_solver}")
        runtime_validation = verify_runtime(
            runtime_root, expected_solver=Path(solver)
        )
        payload = {
            "schema_version": 1,
            "recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "reconstruction_label": label,
            "surface_mode": os.environ["ASURF_SURFACE_MODE"],
            "paper_source_commit": os.environ["PAPER_SOURCE_COMMIT"],
            "runtime": runtime,
            "runtime_validation": runtime_validation,
            "solver": record(Path(solver), runtime_root),
            "resolved_libraries": resolved_libraries(Path(solver)),
            "execution_stages": [{
                key: os.environ.get(key)
                for key in ("SLURM_JOB_ID", "SLURM_JOB_NAME", "SLURM_NNODES", "SLURM_NTASKS")
            }],
            "run_config": read_env(args.run_config),
            "initial": initial_payload(args.case_dir.resolve(), run_root),
        }
    else:
        if not output.is_file():
            raise SystemExit(f"Missing initial provenance: {output}")
        payload = json.loads(output.read_text())
        if payload["reconstruction_label"] != label:
            raise SystemExit("Restart label does not match initial provenance")
        if payload["surface_mode"] != os.environ["ASURF_SURFACE_MODE"]:
            raise SystemExit("Restart surface mode does not match initial provenance")
        solver = shutil.which("reactiveTransportDBSFoam")
        if solver is None:
            raise SystemExit("reactiveTransportDBSFoam is not on PATH")
        runtime_root = Path(
            os.environ.get("GCFOAM_RUNTIME_ROOT", Path(solver).resolve().parent.parent)
        )
        stage_runtime_validation = verify_runtime(
            runtime_root, expected_solver=Path(solver)
        )
        if (
            stage_runtime_validation["required_identity"]
            != payload["runtime_validation"]["required_identity"]
        ):
            raise SystemExit("Restart runtime identity differs from initial provenance")
        time_name, partitions = complete_time(args.case_dir.resolve())
        final_files = [
            record(path, run_root)
            for path in case_files(args.case_dir.resolve(), time_name)
            if path.name != "phreeqc.dmp"
        ]
        stage = {
            key: os.environ.get(key)
            for key in ("SLURM_JOB_ID", "SLURM_JOB_NAME", "SLURM_NNODES", "SLURM_NTASKS")
        }
        payload.setdefault("execution_stages", []).append(stage)
        payload.setdefault("stage_runtime_validations", []).append(
            stage_runtime_validation
        )
        payload["final"] = {
            "recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
            "time_s": float(time_name),
            "time_name": time_name,
            "partitions": partitions,
            "complete_dumps": partitions,
            "complete_markers": partitions,
            "field_files": final_files,
            "log_files": [
                record(path, run_root)
                for path in sorted(args.case_dir.resolve().glob("*.out"))
                if path.is_file()
            ],
        }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print(f"Wrote matched-run provenance: {output}")


if __name__ == "__main__":
    main()
