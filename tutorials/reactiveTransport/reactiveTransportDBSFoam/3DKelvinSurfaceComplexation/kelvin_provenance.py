#!/usr/bin/env python3
"""Fail-closed provenance for the canonical Kelvin paper case."""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import shutil
import subprocess
from pathlib import Path


REQUIRED_INITIAL_FIELDS = (
    "Cl-",
    "H+",
    "Kinv",
    "Mg+2",
    "Mn+2",
    "OH-",
    "Surf_s",
    "Surf_sO-",
    "Surf_sOH",
    "Surf_sOMn+",
    "Surf_w",
    "Surf_wO-",
    "Surf_wOH",
    "Surf_wOMg+",
    "Surf_wOMn+",
    "U",
    "aSurf",
    "aSurfIntrinsic",
    "eps",
    "p",
    "phi",
)
REQUIRED_POLYMESH_FILES = ("boundary", "faces", "neighbour", "owner", "points")


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def command(*args: str) -> str:
    return subprocess.run(
        args, check=True, text=True, stdout=subprocess.PIPE
    ).stdout.rstrip()


def git_state(root: Path) -> dict[str, object]:
    status = command("git", "-C", str(root), "status", "--porcelain").splitlines()
    diff = command("git", "-C", str(root), "diff", "--binary")
    return {
        "root": str(root.resolve()),
        "commit": command("git", "-C", str(root), "rev-parse", "HEAD"),
        "branch": command("git", "-C", str(root), "branch", "--show-current"),
        "status_porcelain": status,
        "tracked_diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
    }


def file_record(path: Path) -> dict[str, str]:
    resolved = path.resolve()
    if not resolved.is_file():
        raise SystemExit(f"Missing provenance input: {resolved}")
    return {"path": str(resolved), "sha256": sha256(resolved)}


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
        **file_record(path),
        "mode": mode,
        "sigma_vox": sigma,
        "integrated_area_m2": float(area_match.group(1)),
    }


def runtime_artifacts(root: Path, solver: Path) -> dict[str, object]:
    ldd = command("ldd", str(solver))
    libraries = []
    for line in ldd.splitlines():
        match = re.search(r"=>\s+(/\S+)\s+\(", line)
        if match:
            path = Path(match.group(1)).resolve()
            if path.is_relative_to(root):
                libraries.append(file_record(path))
    submodule = root / "ThirdParty" / "PhreeqcRM"
    return {
        "solver": file_record(solver),
        "resolved_libraries": libraries,
        "ldd_sha256": hashlib.sha256(ldd.encode()).hexdigest(),
        "phreeqcrm": git_state(submodule),
    }


def densities(path: Path) -> dict[str, float]:
    text = path.read_text()
    block = re.search(r"surfaceMasterDensities\s*\{(.*?)\}", text, re.S)
    if not block:
        raise SystemExit(f"No surfaceMasterDensities in {path}")
    result = {
        name: float(value)
        for name, value in re.findall(
            r"(Surf_[sw])\s+([0-9.eE+\-]+)\s*;", block.group(1)
        )
    }
    if result != {"Surf_s": 2e-7, "Surf_w": 6e-6}:
        raise SystemExit(f"Wrong surface densities: {result}")
    return result


def record(args: argparse.Namespace) -> None:
    runtime = args.runtime.resolve()
    solver_name = shutil.which("reactiveTransportDBSFoam")
    if solver_name is None:
        raise SystemExit("reactiveTransportDBSFoam is not on PATH")
    solver = Path(solver_name).resolve()
    expected = (runtime / "bin" / "reactiveTransportDBSFoam").resolve()
    if solver != expected:
        raise SystemExit(f"Wrong solver: {solver} != {expected}")
    runtime_state = git_state(runtime)
    if runtime_state["commit"] != args.runtime_commit:
        raise SystemExit(f"Wrong runtime commit: {runtime_state['commit']}")
    if runtime_state["status_porcelain"]:
        raise SystemExit(
            f"Runtime checkout is not clean: {runtime_state['status_porcelain']}"
        )
    payload = {
        "schema_version": 2,
        "case_id": "3d_kelvin",
        "recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "paper": git_state(args.paper.resolve()),
        "runtime": runtime_state,
        "runtime_artifacts": runtime_artifacts(runtime, solver),
        "surface": surface_record(args.surface_log, args.mode, args.sigma),
        "intrinsic_surface": surface_record(args.intrinsic_log, args.mode, args.sigma),
        "chemistry": {
            "surface_master_densities_kmol_m2": densities(args.thermo),
            "files": [file_record(path) for path in args.input],
        },
    }
    args.output.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Wrote {args.output}")


def uniform(path: Path) -> float:
    match = re.search(
        r"internalField\s+uniform\s+([0-9.eE+\-]+)\s*;", path.read_text()
    )
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


def run_config(args: argparse.Namespace) -> None:
    payload = json.loads(args.manifest.read_text())
    if payload.get("case_id") != "3d_kelvin":
        raise SystemExit("Manifest is not for the Kelvin case")
    controls = control_values(args.control)
    expected_ranks = 1
    decomposition = {}
    for key in ("NPX", "NPY", "NPZ"):
        value = scalar_file(args.case / "system" / key)
        decomposition[key] = value
        expected_ranks *= value
    ranks = sorted(args.case.glob("processor*"))
    if len(ranks) != expected_ranks:
        raise SystemExit(
            f"Expected {expected_ranks} ranks from decomposition, found {len(ranks)}"
        )
    masters = []
    initial = []
    for rank in ranks:
        missing_fields = [
            name for name in REQUIRED_INITIAL_FIELDS if not (rank / "0" / name).is_file()
        ]
        missing_mesh = [
            name
            for name in REQUIRED_POLYMESH_FILES
            if not (rank / "constant" / "polyMesh" / name).is_file()
        ]
        if missing_fields or missing_mesh:
            raise SystemExit(
                f"Incomplete initial rank inputs in {rank}: "
                f"fields={missing_fields}, polyMesh={missing_mesh}"
            )
        for name, expected in (("Surf_s", 2e-7), ("Surf_w", 6e-6)):
            path = rank / "0" / name
            if uniform(path) != expected:
                raise SystemExit(f"Wrong master field: {path}")
            masters.append({**file_record(path), "value_kmol_m2": expected})
        for root in (rank / "0", rank / "constant" / "polyMesh"):
            initial.extend(
                file_record(path)
                for path in sorted(root.rglob("*"))
                if path.is_file()
            )
    payload["realized_transport"] = {
        **controls,
        "rank_count": expected_ranks,
        "decomposition": decomposition,
        "control_dict": file_record(args.control),
        "thermo_file": file_record(args.thermo),
        "surface_master_fields": masters,
        "initial_rank_inputs": initial,
    }
    args.manifest.write_text(json.dumps(payload, indent=2) + "\n")
    print(f"Updated {args.manifest}")


def parser() -> argparse.ArgumentParser:
    main = argparse.ArgumentParser()
    sub = main.add_subparsers(dest="command", required=True)
    rec = sub.add_parser("record")
    rec.add_argument("--paper", type=Path, required=True)
    rec.add_argument("--runtime", type=Path, required=True)
    rec.add_argument("--runtime-commit", required=True)
    rec.add_argument("--surface-log", type=Path, required=True)
    rec.add_argument("--intrinsic-log", type=Path, required=True)
    rec.add_argument("--mode", required=True)
    rec.add_argument("--sigma", type=float, required=True)
    rec.add_argument("--thermo", type=Path, required=True)
    rec.add_argument("--input", action="append", type=Path, default=[])
    rec.add_argument("--output", type=Path, required=True)
    rec.set_defaults(func=record)
    run = sub.add_parser("record-run")
    run.add_argument("--manifest", type=Path, required=True)
    run.add_argument("--case", type=Path, required=True)
    run.add_argument("--control", type=Path, required=True)
    run.add_argument("--thermo", type=Path, required=True)
    run.set_defaults(func=run_config)
    return main


if __name__ == "__main__":
    arguments = parser().parse_args()
    arguments.func(arguments)
