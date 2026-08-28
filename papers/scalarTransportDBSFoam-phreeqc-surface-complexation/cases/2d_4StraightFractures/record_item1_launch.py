#!/usr/bin/env python3
"""Record portable, fail-closed launch provenance for the fresh Item 1 run."""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path


CASE = Path(__file__).resolve().parent
PAPER = CASE.parents[3]
RUNTIME = Path(os.environ["GCFOAM_RUNTIME_ROOT"]).resolve()
EXPECTED_RUNTIME = "3c4a34326b5573d76d48664093a1933a5a65b316"
EXPECTED_RUNTIME_PARENT = "10f7a66afbf745d25013f7eda45b090cff66b866"
EXPECTED_ADAPTER = "a43de2c1d1dd5c0f93489d560fa3cd3e94646471"
EXPECTED_ARTIFACTS = {
    "bin/reactiveTransportDBSFoam": "3b41fd0914b4407fa591ea403cc66c4fde1daa7d1608481edaac19533e11b124",
    "lib/libfiniteVolumeGCFOAM.so": "e13af080edca54982d9950378ab27d1c0df5cc1b26d384eb6bb64845348502ad",
    "lib/libreactionThermophysicalModelsGCFOAM.so": "447d857aa9679a1962f72d5df71f09c3faf0b84f4c5b74e279e092af1cdd425a",
    "ThirdParty/PhreeqcRM/lib/libPhreeqcRM.so": "90ffa2f6c554941c40535739fc9359af19528425e6dc61b2876d00b016affe29",
}
ALLOWED_ADAPTER_UNTRACKED = {
    "?? lib/",
    "?? src/Make/linux64GccDPInt32Opt/",
    "?? src/lnInclude/",
}


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def git(root: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, text=True,
        stdout=subprocess.PIPE,
    ).stdout.rstrip()


def portable(path: Path) -> str:
    path = path.resolve()
    for label, root in (("PAPER_REPO", PAPER), ("RUNTIME_REPO", RUNTIME)):
        if path == root:
            return f"${{{label}}}"
        if path.is_relative_to(root):
            return f"${{{label}}}/{path.relative_to(root).as_posix()}"
    raise RuntimeError(f"Path is outside recorded roots: {path}")


def record(path: Path) -> dict[str, str]:
    if not path.is_file():
        raise RuntimeError(f"Missing provenance input: {path}")
    return {"path": portable(path), "sha256": sha256(path)}


def tracked_state(root: Path) -> dict[str, object]:
    diff = git(root, "diff", "--binary")
    return {
        "root": portable(root),
        "commit": git(root, "rev-parse", "HEAD"),
        "tracked_diff_sha256": hashlib.sha256(diff.encode()).hexdigest(),
        "status_porcelain": git(root, "status", "--porcelain").splitlines(),
    }


def main() -> None:
    if git(RUNTIME, "rev-parse", "HEAD") != EXPECTED_RUNTIME:
        raise RuntimeError("Reviewed runtime commit mismatch")
    if git(RUNTIME, "rev-parse", "HEAD^") != EXPECTED_RUNTIME_PARENT:
        raise RuntimeError("Reviewed runtime parent mismatch")
    adapter = RUNTIME / "ThirdParty" / "PhreeqcRM"
    gitlink = git(RUNTIME, "ls-tree", "HEAD", "ThirdParty/PhreeqcRM").split()[2]
    if gitlink != EXPECTED_ADAPTER:
        raise RuntimeError("Reviewed runtime gitlink mismatch")
    if git(adapter, "rev-parse", "HEAD") != EXPECTED_ADAPTER:
        raise RuntimeError("Reviewed PhreeqcRM adapter commit mismatch")
    for root, label in ((RUNTIME, "runtime"), (adapter, "PhreeqcRM adapter")):
        tracked = git(root, "status", "--porcelain", "--untracked-files=no").splitlines()
        if tracked:
            raise RuntimeError(f"{label} has tracked source changes: {tracked}")
    adapter_status = set(git(adapter, "status", "--porcelain").splitlines())
    unexpected = sorted(adapter_status - ALLOWED_ADAPTER_UNTRACKED)
    if unexpected:
        raise RuntimeError(f"Unexpected PhreeqcRM adapter files: {unexpected}")
    for relative, expected in EXPECTED_ARTIFACTS.items():
        actual = sha256(RUNTIME / relative)
        if actual != expected:
            raise RuntimeError(f"Runtime artifact hash mismatch: {relative}")
    forbidden = []
    for candidate in (CASE / "0", *(CASE.glob("processor*"))):
        if candidate.exists():
            forbidden.append(str(candidate))
    forbidden.extend(str(path) for path in CASE.rglob("phreeqc.dmp"))
    forbidden.extend(str(path) for path in CASE.rglob("phreeqc.complete"))
    if forbidden:
        raise RuntimeError(f"Fresh-run invariant failed: {forbidden}")

    source_paths = []
    for root in (CASE / "constant", CASE / "system"):
        source_paths.extend(path for path in root.rglob("*") if path.is_file())
    source_paths.extend(path for path in CASE.glob("*.sh") if path.is_file())
    source_paths.extend([
        CASE / "record_item1_launch.py",
        CASE.parent / "configure_runtime.sh",
        CASE.parent / "case_provenance.py",
        PAPER / "scripts" / "createASurfMarchingCubes.py",
        PAPER / "images" / "raw" / "4StraightFractures.raw.tar.gz",
        PAPER / "images" / "raw" / "4StraightFractures.txt",
    ])

    solver = RUNTIME / "bin" / "reactiveTransportDBSFoam"
    ldd = subprocess.run(
        ["ldd", str(solver)], check=True, text=True, stdout=subprocess.PIPE
    ).stdout
    libraries = []
    for line in ldd.splitlines():
        match = re.search(r"=>\s+(/\S+)\s+\(", line)
        if match:
            candidate = Path(match.group(1)).resolve()
            if candidate.is_relative_to(RUNTIME) and candidate.is_file():
                libraries.append(record(candidate))

    payload = {
        "schema_version": 1,
        "recorded_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "case_id": "2d_4StraightFractures_item1_final_fresh",
        "path_roots": {
            "PAPER_REPO": "isolated paper checkout used for this run",
            "RUNTIME_REPO": "reviewed combined GeoChemFoam runtime checkout",
        },
        "paper": tracked_state(PAPER),
        "runtime": tracked_state(RUNTIME),
        "runtime_pairing": {
            "parent_commit": EXPECTED_RUNTIME_PARENT,
            "phreeqcrm_gitlink": gitlink,
        },
        "runtime_artifacts": {
            "solver": record(solver),
            "resolved_libraries": libraries,
            "ldd_sha256": hashlib.sha256(ldd.encode()).hexdigest(),
            "phreeqcrm": tracked_state(RUNTIME / "ThirdParty" / "PhreeqcRM"),
        },
        "controls": {
            "mpi_ranks": 8,
            "decomposition": [4, 2, 1],
            "start_time_s": 0,
            "end_time_s": 20000,
            "delta_t_s": 0.25,
            "write_interval_s": 2000,
            "phreeqc_restore_checkpoint": False,
            "phreeqc_restart_checkpoints": True,
        },
        "chemistry": {
            "surface_master_densities_kmol_m2": {"Surf_s": 2e-7, "Surf_w": 6e-6}
        },
        "surface": {
            "mode": "occupancyGaussian",
            "sigma_vox": 0.75,
            "expected_integrated_area_m2": 0.021990199701030694,
            "expected_intrinsic_area_m2": 0.021960000000000004,
        },
        "cfl_preflight": {
            "matching_dt_s": 0.25,
            "prior_mean_courant": 0.004285756863393865,
            "prior_max_courant": 0.06024709546261201,
        },
        "fresh_state": {
            "copied_result_state": False,
            "copied_checkpoint_state": False,
            "initial_time_directories": [],
            "initial_processor_directories": [],
        },
        "source_inputs": [record(path) for path in sorted(set(source_paths))],
    }
    (CASE / "launch_provenance.json").write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n"
    )


if __name__ == "__main__":
    main()
