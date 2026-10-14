#!/usr/bin/env python3
"""Materialise GeoChemFoam-owned raw images without duplicating them in Git."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import urllib.request
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
MANIFEST = REPO_ROOT / "external_assets.json"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def checked_target(relative: str) -> Path:
    relative_path = Path(relative)
    if relative_path.is_absolute():
        raise ValueError(f"External asset target must be repository-relative: {relative}")
    target = REPO_ROOT / relative_path
    target.parent.resolve().relative_to(REPO_ROOT)
    return target


def is_ready(path: Path, expected: str) -> bool:
    return path.is_file() and sha256(path) == expected


def materialise(asset: dict[str, object], source_root: Path | None) -> str:
    target = checked_target(str(asset["target"]))
    expected = str(asset["sha256"])
    if is_ready(target, expected):
        return f"ready     {target.relative_to(REPO_ROOT)}"
    if target.exists() or target.is_symlink():
        raise RuntimeError(f"Existing asset has the wrong SHA-256: {target}")

    target.parent.mkdir(parents=True, exist_ok=True)
    if source_root is not None:
        source = source_root / str(asset["source_path"])
        if source.is_file():
            actual = sha256(source)
            if actual != expected:
                raise RuntimeError(
                    f"Local source hash mismatch for {source}: {actual} != {expected}"
                )
            target.symlink_to(source.resolve())
            return f"linked    {target.relative_to(REPO_ROOT)} -> {source.resolve()}"

    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as handle:
        temporary = Path(handle.name)
    try:
        repository = str(asset["source_repository"]).removesuffix(".git")
        slug = repository.removeprefix("https://github.com/")
        endpoint = (
            f"repos/{slug}/contents/{asset['source_path']}"
            f"?ref={asset['source_commit']}"
        )
        if shutil.which("gh"):
            with temporary.open("wb") as output:
                subprocess.run(
                    ["gh", "api", "-H", "Accept: application/vnd.github.raw+json", endpoint],
                    stdout=output,
                    check=True,
                )
        else:
            raw_url = str(asset["url"]).replace(
                "https://github.com/", "https://raw.githubusercontent.com/"
            ).replace("/blob/", "/")
            headers = {}
            if os.environ.get("GITHUB_TOKEN"):
                headers["Authorization"] = f"Bearer {os.environ['GITHUB_TOKEN']}"
            request = urllib.request.Request(raw_url, headers=headers)
            with urllib.request.urlopen(request) as response, temporary.open("wb") as output:
                shutil.copyfileobj(response, output)
        actual = sha256(temporary)
        if actual != expected:
            raise RuntimeError(
                f"Downloaded hash mismatch for {asset['id']}: {actual} != {expected}"
            )
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)
    return f"downloaded {target.relative_to(REPO_ROOT)}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-root",
        type=Path,
        default=Path(os.environ["GCFOAM_SOURCE_ROOT"])
        if os.environ.get("GCFOAM_SOURCE_ROOT")
        else None,
        help="GeoChemFoam checkout to use before downloading (or GCFOAM_SOURCE_ROOT)",
    )
    parser.add_argument(
        "--include-legacy",
        action="store_true",
        help="also materialise linked historical assets that have no current consumer",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="verify already materialised assets without creating or downloading files",
    )
    args = parser.parse_args()

    manifest = json.loads(MANIFEST.read_text())
    assets = manifest["assets"]
    failures = 0
    for asset in assets:
        if not asset["used_by"] and not args.include_legacy:
            print(f"skipped   {asset['target']} (historical, unused by current figures)")
            continue
        target = checked_target(str(asset["target"]))
        if args.check:
            if is_ready(target, str(asset["sha256"])):
                print(f"ready     {target.relative_to(REPO_ROOT)}")
            else:
                print(f"missing   {target.relative_to(REPO_ROOT)}")
                failures += 1
            continue
        print(materialise(asset, args.source_root))
    return 1 if args.check and failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
