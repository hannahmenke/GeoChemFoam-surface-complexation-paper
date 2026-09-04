#!/usr/bin/env python3
"""Audit the paper's figure, case, renderer, and external-asset map."""

from __future__ import annotations

import ast
import json
import re
import stat
import subprocess
import sys
from pathlib import Path


PAPER_ROOT = Path(__file__).resolve().parent
REPO_ROOT = PAPER_ROOT.parents[1]
MANIFEST = PAPER_ROOT / "reproducibility_manifest.json"
HEX40 = re.compile(r"[0-9a-f]{40}")
HEX64 = re.compile(r"[0-9a-f]{64}")
GRAPHICS = re.compile(r"\\includegraphics(?:\[[^]]*\])?\{([^}]+)\}")


def fail(message: str, failures: list[str]) -> None:
    failures.append(message)


def repo_relative(path: Path) -> str:
    return path.resolve().relative_to(REPO_ROOT).as_posix()


def tracked_paths() -> set[str]:
    output = subprocess.check_output(
        ["git", "ls-files", "-z"], cwd=REPO_ROOT
    ).decode()
    return set(output.rstrip("\0").split("\0")) if output else set()


def local_path(relative: str) -> Path:
    path = (PAPER_ROOT / relative).resolve(strict=False)
    path.relative_to(REPO_ROOT)
    return path


def require_local(relative: str, label: str, tracked: set[str], failures: list[str]) -> Path:
    try:
        path = local_path(relative)
    except ValueError:
        fail(f"{label} escapes the repository: {relative}", failures)
        return PAPER_ROOT
    if not path.exists():
        fail(f"missing {label}: {relative}", failures)
    elif repo_relative(path) not in tracked and not path.is_dir():
        fail(f"untracked {label}: {relative}", failures)
    return path


def check_entrypoint(path: Path, label: str, failures: list[str]) -> None:
    if not path.is_file():
        return
    if path.suffix == ".sh":
        if not path.stat().st_mode & stat.S_IXUSR:
            fail(f"non-executable {label}: {repo_relative(path)}", failures)
        result = subprocess.run(["bash", "-n", path], capture_output=True, text=True)
        if result.returncode:
            fail(f"invalid shell syntax in {label}: {repo_relative(path)}", failures)
    elif path.suffix == ".py":
        try:
            ast.parse(path.read_text(), filename=str(path))
        except SyntaxError as error:
            fail(f"invalid Python syntax in {label}: {error}", failures)


def discovered_cases() -> set[str]:
    paths = {
        repo_relative(path)
        for path in (PAPER_ROOT / "cases").iterdir()
        if path.is_dir() and not path.name.startswith((".", "__"))
    }
    tutorial_root = REPO_ROOT / "tutorials/reactiveTransport"
    dbs_root = tutorial_root / "reactiveTransportDBSFoam"
    paths.update(
        repo_relative(path)
        for path in dbs_root.iterdir()
        if path.is_dir() and not path.name.startswith((".", "__"))
    )
    comparison = tutorial_root / "HM12SurfaceComplexationSolverComparison"
    paths.add(repo_relative(comparison))
    resolved = comparison / "resolved-snappy"
    if resolved.is_dir():
        paths.add(repo_relative(resolved))
    return paths


def check_tutorial_scope(failures: list[str]) -> None:
    tutorial_root = REPO_ROOT / "tutorials"
    unexpected = sorted(
        path.name
        for path in tutorial_root.iterdir()
        if path.is_dir() and path.name != "reactiveTransport"
    )
    if unexpected:
        fail(
            "tutorial trees outside the paper's reactive-transport scope: "
            f"{unexpected}",
            failures,
        )


def main() -> int:
    failures: list[str] = []
    data = json.loads(MANIFEST.read_text())
    external_path = local_path(data["external_assets"])
    external = json.loads(external_path.read_text())
    tracked = tracked_paths()
    check_tutorial_scope(failures)

    if repo_relative(MANIFEST) not in tracked:
        fail("reproducibility_manifest.json is not Git-tracked", failures)
    if repo_relative(external_path) not in tracked:
        fail("external_assets.json is not Git-tracked", failures)
    for name in ("fvSchemes", "fvSolution"):
        require_local(
            f"../../scripts/snappyHexMeshSystem/{name}",
            f"snappyHexMesh benchmark template {name}",
            tracked,
            failures,
        )

    asset_ids: set[str] = set()
    for asset in external.get("assets", []):
        asset_id = asset.get("id")
        if not isinstance(asset_id, str) or asset_id in asset_ids:
            fail(f"invalid or duplicate external asset id: {asset_id!r}", failures)
            continue
        asset_ids.add(asset_id)
        commit = asset.get("source_commit", "")
        digest = asset.get("sha256", "")
        url = asset.get("url", "")
        if not HEX40.fullmatch(str(commit)) or str(commit) not in str(url):
            fail(f"external asset {asset_id} is not pinned to its immutable commit", failures)
        if not HEX64.fullmatch(str(digest)):
            fail(f"external asset {asset_id} has an invalid SHA-256", failures)
        if not asset.get("crop_xyz") or not asset.get("source_shape_xyz"):
            fail(f"external asset {asset_id} lacks shape/crop metadata", failures)
        target = (REPO_ROOT / str(asset.get("target", ""))).absolute()
        try:
            relative_target = target.relative_to(REPO_ROOT).as_posix()
        except ValueError:
            fail(f"external asset target escapes repository: {asset_id}", failures)
        else:
            if relative_target in tracked:
                fail(f"external asset is duplicated in Git: {relative_target}", failures)

    figure_numbers: set[int] = set()
    outputs: set[str] = set()
    case_ids = {case["id"] for case in data.get("cases", [])}
    for figure in data.get("figures", []):
        number = figure.get("number")
        if not isinstance(number, int) or number in figure_numbers:
            fail(f"invalid or duplicate manuscript figure number: {number!r}", failures)
        else:
            figure_numbers.add(number)
        output = str(figure.get("output", ""))
        outputs.add(output)
        require_local(output, f"Figure {number} output", tracked, failures)
        for key in ("run", "render"):
            if key in figure:
                entrypoint = require_local(str(figure[key]), f"Figure {number} {key}", tracked, failures)
                check_entrypoint(entrypoint, f"Figure {number} {key}", failures)
        for run_path in figure.get("runs", []):
            entrypoint = require_local(str(run_path), f"Figure {number} run", tracked, failures)
            check_entrypoint(entrypoint, f"Figure {number} run", failures)
        for evidence in figure.get("evidence", []):
            require_local(str(evidence), f"Figure {number} evidence", tracked, failures)
        for case_id in figure.get("case_ids", []):
            if case_id not in case_ids:
                fail(f"Figure {number} refers to unknown case id {case_id}", failures)
        for asset_id in figure.get("external_asset_ids", []):
            if asset_id not in asset_ids:
                fail(f"Figure {number} refers to unknown external asset {asset_id}", failures)

    if figure_numbers != set(range(1, 15)):
        fail(f"figure manifest numbers are {sorted(figure_numbers)}, expected 1--14", failures)

    manuscript_outputs: set[str] = set()
    for tex in [PAPER_ROOT / "main.tex", *(PAPER_ROOT / "sections").glob("*.tex")]:
        for match in GRAPHICS.finditer(tex.read_text()):
            manuscript_outputs.add(match.group(1))
    if outputs != manuscript_outputs:
        fail(
            "manuscript/manifest figure mismatch: "
            f"manifest-only={sorted(outputs - manuscript_outputs)}, "
            f"manuscript-only={sorted(manuscript_outputs - outputs)}",
            failures,
        )

    retained_outputs: set[str] = set()
    for figure in data.get("retained_figure_assets", []):
        output = str(figure["output"])
        retained_outputs.add(output)
        require_local(output, "retained figure output", tracked, failures)
        renderer = require_local(str(figure["render"]), "retained figure renderer", tracked, failures)
        check_entrypoint(renderer, "retained figure renderer", failures)
    png_outputs = {
        path.relative_to(PAPER_ROOT).as_posix()
        for path in (PAPER_ROOT / "figures/png").glob("*.png")
    }
    documented_outputs = outputs | retained_outputs
    if png_outputs != documented_outputs:
        fail(
            "undocumented/orphan PNG mismatch: "
            f"undocumented={sorted(png_outputs - documented_outputs)}, "
            f"missing={sorted(documented_outputs - png_outputs)}",
            failures,
        )

    declared_case_paths: set[str] = set()
    for case in data.get("cases", []):
        path = require_local(str(case["path"]), f"case {case['id']}", tracked, failures)
        declared_case_paths.add(repo_relative(path))
        if not case.get("classification"):
            fail(f"case {case['id']} has no classification", failures)
    found_cases = discovered_cases()
    if found_cases != declared_case_paths:
        fail(
            "case inventory mismatch: "
            f"unclassified={sorted(found_cases - declared_case_paths)}, "
            f"missing={sorted(declared_case_paths - found_cases)}",
            failures,
        )

    if failures:
        print("Reproducibility audit FAILED:", file=sys.stderr)
        for message in failures:
            print(f"- {message}", file=sys.stderr)
        return 1
    print(
        f"Reproducibility audit passed: {len(outputs)} manuscript figures, "
        f"{len(retained_outputs)} retained figure assets, {len(declared_case_paths)} cases, "
        f"and {len(asset_ids)} external assets are fully classified."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
