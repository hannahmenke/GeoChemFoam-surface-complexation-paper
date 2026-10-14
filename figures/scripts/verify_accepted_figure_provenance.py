#!/usr/bin/env python3
"""Verify the hand-maintained accepted-figure provenance manifest.

The verifier is deliberately read-only.  It authenticates retained repository
files; it never discovers files or rewrites hashes into the manifest.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import stat
import subprocess
from pathlib import Path, PurePosixPath
from typing import Any


SCHEMA = "org.geochemfoam.paper.accepted-figure-provenance"
SCHEMA_VERSION = 1
SHA256_RE = re.compile(r"[0-9a-f]{64}\Z")
ID_RE = re.compile(r"[a-z0-9]+(?:[._-][a-z0-9]+)*\Z")
ALLOWED_BINDING_ROLES = {
    "figure",
    "material_data",
    "provenance_record",
    "renderer_source",
    "validation_evidence",
}
ALLOWED_ENVIRONMENT_AVAILABILITY = {
    "not_recorded",
    "partially_recorded",
    "recorded",
}
SCRIPT_RELATIVE_PATH = Path(
    "figures/scripts/verify_accepted_figure_provenance.py"
)
DEFAULT_MANIFEST_RELATIVE_PATH = Path(
    "figures/accepted_nonkelvin_provenance.json"
)


class VerificationError(ValueError):
    """A fail-closed manifest or binding error."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise VerificationError(message)


def exact_type(value: object, expected: type, label: str) -> None:
    require(
        type(value) is expected,
        f"{label} must be {expected.__name__}, got {type(value).__name__}",
    )


def exact_keys(value: object, expected: set[str], label: str) -> dict[str, Any]:
    exact_type(value, dict, label)
    mapping = value
    actual = set(mapping)
    require(actual == expected, f"{label} keys differ: expected {sorted(expected)}, got {sorted(actual)}")
    return mapping


def nonempty_string(value: object, label: str) -> str:
    exact_type(value, str, label)
    require(bool(value), f"{label} must not be empty")
    return value


def identifier(value: object, label: str) -> str:
    item = nonempty_string(value, label)
    require(ID_RE.fullmatch(item) is not None, f"{label} is not a normalized identifier: {item!r}")
    return item


def string_list(value: object, label: str, *, nonempty: bool = True) -> list[str]:
    exact_type(value, list, label)
    items = value
    if nonempty:
        require(bool(items), f"{label} must not be empty")
    for index, item in enumerate(items):
        nonempty_string(item, f"{label}[{index}]")
    require(len(items) == len(set(items)), f"{label} contains duplicates")
    return items


def identifier_list(value: object, label: str, *, nonempty: bool = True) -> list[str]:
    items = string_list(value, label, nonempty=nonempty)
    for index, item in enumerate(items):
        identifier(item, f"{label}[{index}]")
    return items


def canonical_json(payload: object) -> str:
    try:
        return json.dumps(
            payload,
            allow_nan=False,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ) + "\n"
    except (TypeError, ValueError) as error:
        raise VerificationError(f"Manifest cannot be encoded as canonical JSON: {error}") from error


def reject_duplicate_object_keys(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise VerificationError(f"Duplicate JSON object key: {key}")
        result[key] = value
    return result


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as error:
        raise VerificationError(f"Cannot read manifest {path}: {error}") from error
    try:
        payload = json.loads(
            text,
            object_pairs_hook=reject_duplicate_object_keys,
            parse_constant=lambda value: (_ for _ in ()).throw(
                VerificationError(f"Non-finite JSON value: {value}")
            ),
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        raise VerificationError(f"Invalid JSON in {path}: {error}") from error
    exact_type(payload, dict, "manifest")
    require(text == canonical_json(payload), "Manifest is not canonical JSON (UTF-8, sorted keys, two-space indent, final newline)")
    return payload


def verify_schema(payload: object) -> dict[str, dict[str, Any]]:
    root = exact_keys(payload, {"bindings", "figures", "schema", "schema_version", "scope"}, "manifest")
    nonempty_string(root["schema"], "manifest.schema")
    require(root["schema"] == SCHEMA, f"Unsupported schema: {root['schema']!r}")
    exact_type(root["schema_version"], int, "manifest.schema_version")
    require(root["schema_version"] == SCHEMA_VERSION, f"Unsupported schema_version: {root['schema_version']!r}")

    scope = exact_keys(root["scope"], {"description", "expected_figure_ids", "id"}, "manifest.scope")
    identifier(scope["id"], "manifest.scope.id")
    nonempty_string(scope["description"], "manifest.scope.description")
    expected_figure_ids = identifier_list(scope["expected_figure_ids"], "manifest.scope.expected_figure_ids")

    exact_type(root["bindings"], list, "manifest.bindings")
    require(bool(root["bindings"]), "manifest.bindings must not be empty")
    bindings: dict[str, dict[str, Any]] = {}
    paths: set[str] = set()
    binding_order: list[str] = []
    for index, raw_binding in enumerate(root["bindings"]):
        label = f"manifest.bindings[{index}]"
        binding = exact_keys(raw_binding, {"id", "media_type", "path", "role", "sha256", "size_bytes"}, label)
        binding_id = identifier(binding["id"], f"{label}.id")
        require(binding_id not in bindings, f"Duplicate binding id: {binding_id}")
        path = validate_repo_relative_path(binding["path"], f"{label}.path")
        require(path not in paths, f"Duplicate binding path: {path}")
        role = nonempty_string(binding["role"], f"{label}.role")
        require(role in ALLOWED_BINDING_ROLES, f"Unknown binding role {role!r} for {binding_id}")
        nonempty_string(binding["media_type"], f"{label}.media_type")
        digest = nonempty_string(binding["sha256"], f"{label}.sha256")
        require(SHA256_RE.fullmatch(digest) is not None, f"Invalid SHA-256 for {binding_id}")
        exact_type(binding["size_bytes"], int, f"{label}.size_bytes")
        require(binding["size_bytes"] >= 0, f"Negative size for {binding_id}")
        bindings[binding_id] = binding
        paths.add(path)
        binding_order.append(binding_id)
    require(binding_order == sorted(binding_order), "manifest.bindings must be sorted by id")

    exact_type(root["figures"], list, "manifest.figures")
    require(bool(root["figures"]), "manifest.figures must not be empty")
    seen_figures: set[str] = set()
    seen_numbers: set[int] = set()
    artifact_ids: set[str] = set()
    referenced_ids: set[str] = set()
    figure_order: list[int] = []
    for index, raw_figure in enumerate(root["figures"]):
        label = f"manifest.figures[{index}]"
        figure = exact_keys(
            raw_figure,
            {
                "artifact_binding_id",
                "case",
                "claim_role",
                "comparison",
                "figure_id",
                "manuscript_number",
                "material_binding_ids",
                "provenance",
                "renderer",
            },
            label,
        )
        figure_id = identifier(figure["figure_id"], f"{label}.figure_id")
        require(figure_id not in seen_figures, f"Duplicate figure_id: {figure_id}")
        seen_figures.add(figure_id)
        exact_type(figure["manuscript_number"], int, f"{label}.manuscript_number")
        number = figure["manuscript_number"]
        require(number > 0, f"Invalid manuscript number for {figure_id}")
        require(number not in seen_numbers, f"Duplicate manuscript number: {number}")
        seen_numbers.add(number)
        figure_order.append(number)
        nonempty_string(figure["claim_role"], f"{label}.claim_role")

        case = exact_keys(figure["case"], {"id", "label", "provenance_semantics"}, f"{label}.case")
        identifier(case["id"], f"{label}.case.id")
        nonempty_string(case["label"], f"{label}.case.label")
        nonempty_string(case["provenance_semantics"], f"{label}.case.provenance_semantics")

        comparison = exact_keys(
            figure["comparison"],
            {"method_roles", "quantity_roles", "reference_basis"},
            f"{label}.comparison",
        )
        exact_type(comparison["method_roles"], list, f"{label}.comparison.method_roles")
        require(bool(comparison["method_roles"]), f"{label}.comparison.method_roles must not be empty")
        method_ids: set[str] = set()
        for method_index, raw_method in enumerate(comparison["method_roles"]):
            method_label = f"{label}.comparison.method_roles[{method_index}]"
            method = exact_keys(raw_method, {"id", "label", "role"}, method_label)
            method_id = identifier(method["id"], f"{method_label}.id")
            require(method_id not in method_ids, f"Duplicate method id {method_id} in {figure_id}")
            method_ids.add(method_id)
            nonempty_string(method["label"], f"{method_label}.label")
            nonempty_string(method["role"], f"{method_label}.role")
        string_list(comparison["quantity_roles"], f"{label}.comparison.quantity_roles")
        nonempty_string(comparison["reference_basis"], f"{label}.comparison.reference_basis")

        artifact_id = identifier(figure["artifact_binding_id"], f"{label}.artifact_binding_id")
        require(artifact_id not in artifact_ids, f"Figure artifact reused: {artifact_id}")
        artifact_ids.add(artifact_id)
        require_binding_role(bindings, artifact_id, "figure", f"{label}.artifact_binding_id")
        referenced_ids.add(artifact_id)

        material_ids = identifier_list(
            figure["material_binding_ids"],
            f"{label}.material_binding_ids",
            nonempty=False,
        )
        for binding_id in material_ids:
            require_binding_role(
                bindings,
                binding_id,
                {"material_data", "validation_evidence"},
                f"{label}.material_binding_ids",
            )
            referenced_ids.add(binding_id)

        exact_type(figure["provenance"], list, f"{label}.provenance")
        require(bool(figure["provenance"]), f"{label}.provenance must not be empty")
        provenance_ids: set[str] = set()
        for provenance_index, raw_record in enumerate(figure["provenance"]):
            record_label = f"{label}.provenance[{provenance_index}]"
            record = exact_keys(raw_record, {"binding_id", "record_kind", "semantics"}, record_label)
            binding_id = identifier(record["binding_id"], f"{record_label}.binding_id")
            require(binding_id not in provenance_ids, f"Duplicate provenance binding {binding_id} in {figure_id}")
            provenance_ids.add(binding_id)
            require_binding_role(bindings, binding_id, "provenance_record", f"{record_label}.binding_id")
            identifier(record["record_kind"], f"{record_label}.record_kind")
            nonempty_string(record["semantics"], f"{record_label}.semantics")
            referenced_ids.add(binding_id)

        renderer = exact_keys(figure["renderer"], {"command", "environment", "source_binding_ids"}, f"{label}.renderer")
        nonempty_string(renderer["command"], f"{label}.renderer.command")
        source_ids = identifier_list(renderer["source_binding_ids"], f"{label}.renderer.source_binding_ids")
        for binding_id in source_ids:
            require_binding_role(bindings, binding_id, "renderer_source", f"{label}.renderer.source_binding_ids")
            referenced_ids.add(binding_id)
        environment = exact_keys(
            renderer["environment"],
            {"availability", "description", "reference_binding_ids"},
            f"{label}.renderer.environment",
        )
        availability = nonempty_string(environment["availability"], f"{label}.renderer.environment.availability")
        require(
            availability in ALLOWED_ENVIRONMENT_AVAILABILITY,
            f"Unknown renderer environment availability: {availability!r}",
        )
        nonempty_string(environment["description"], f"{label}.renderer.environment.description")
        environment_ids = identifier_list(
            environment["reference_binding_ids"],
            f"{label}.renderer.environment.reference_binding_ids",
            nonempty=False,
        )
        require(
            availability == "not_recorded" or bool(environment_ids),
            f"{figure_id} records renderer environment availability without a reference",
        )
        for binding_id in environment_ids:
            require_binding_role(bindings, binding_id, "provenance_record", f"{label}.renderer.environment.reference_binding_ids")
            referenced_ids.add(binding_id)

    require(figure_order == sorted(figure_order), "manifest.figures must be sorted by manuscript_number")
    require(expected_figure_ids == [item["figure_id"] for item in root["figures"]], "scope.expected_figure_ids must exactly match figure order")
    require(seen_figures == set(expected_figure_ids), "Missing or unexpected figure records")
    unreferenced = set(bindings) - referenced_ids
    require(not unreferenced, f"Unexpected/unreferenced bindings: {sorted(unreferenced)}")
    return bindings


def require_binding_role(
    bindings: dict[str, dict[str, Any]],
    binding_id: str,
    expected: str | set[str],
    label: str,
) -> None:
    require(binding_id in bindings, f"Missing binding referenced by {label}: {binding_id}")
    allowed = {expected} if isinstance(expected, str) else expected
    role = bindings[binding_id]["role"]
    require(role in allowed, f"Wrong role for {binding_id}: expected {sorted(allowed)}, got {role!r}")


def validate_repo_relative_path(value: object, label: str) -> str:
    path = nonempty_string(value, label)
    require("\\" not in path, f"{label} must use POSIX separators")
    pure = PurePosixPath(path)
    require(not pure.is_absolute(), f"{label} must be repository-relative")
    require(path == pure.as_posix(), f"{label} is not normalized: {path!r}")
    require(path != ".", f"{label} must identify a file")
    require(all(part not in {"", ".", ".."} for part in pure.parts), f"{label} contains traversal")
    return path


def has_checkout_metadata(repo_root: Path) -> bool:
    metadata = repo_root / ".git"
    try:
        mode = metadata.lstat().st_mode
    except FileNotFoundError:
        return False
    except OSError as error:
        raise VerificationError(f"Cannot inspect checkout metadata {metadata}: {error}") from error
    require(not stat.S_ISLNK(mode), f"Checkout metadata must not be a symlink: {metadata}")
    if stat.S_ISDIR(mode):
        return True
    require(stat.S_ISREG(mode), f"Checkout metadata is neither a directory nor a worktree file: {metadata}")
    try:
        pointer_text = metadata.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise VerificationError(f"Cannot read linked-worktree metadata {metadata}: {error}") from error
    pointer_match = re.fullmatch(r"gitdir: ([^\r\n]+)\n", pointer_text)
    require(pointer_match is not None, f"Malformed linked-worktree metadata: {metadata}")
    administrative_path = Path(pointer_match.group(1))
    require(administrative_path.is_absolute(), f"Linked-worktree gitdir must be absolute: {administrative_path}")
    try:
        administrative_mode = administrative_path.lstat().st_mode
        administrative_directory = administrative_path.resolve(strict=True)
    except OSError as error:
        raise VerificationError(f"Cannot resolve linked-worktree gitdir {administrative_path}: {error}") from error
    require(
        not stat.S_ISLNK(administrative_mode) and stat.S_ISDIR(administrative_mode),
        f"Linked-worktree gitdir is not a non-symlink directory: {administrative_path}",
    )
    backlink = administrative_directory / "gitdir"
    try:
        backlink_mode = backlink.lstat().st_mode
        backlink_text = backlink.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as error:
        raise VerificationError(f"Cannot read linked-worktree backlink {backlink}: {error}") from error
    require(
        not stat.S_ISLNK(backlink_mode) and stat.S_ISREG(backlink_mode),
        f"Linked-worktree backlink is not a non-symlink regular file: {backlink}",
    )
    backlink_match = re.fullmatch(r"([^\r\n]+)\n", backlink_text)
    require(backlink_match is not None, f"Malformed linked-worktree backlink: {backlink}")
    backlink_path = Path(backlink_match.group(1))
    require(backlink_path.is_absolute(), f"Linked-worktree backlink must be absolute: {backlink_path}")
    try:
        authenticated_metadata = backlink_path.resolve(strict=True)
        expected_metadata = metadata.resolve(strict=True)
    except OSError as error:
        raise VerificationError(f"Cannot resolve linked-worktree backlink {backlink_path}: {error}") from error
    require(
        authenticated_metadata == expected_metadata,
        f"Linked-worktree backlink does not authenticate this root: {authenticated_metadata} != {expected_metadata}",
    )
    return True


def git_tracked_paths(repo_root: Path) -> set[str]:
    try:
        top_level = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--show-toplevel"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        ).stdout.strip()
        require(
            Path(top_level).resolve(strict=True) == repo_root,
            f"Git metadata at {repo_root / '.git'} resolves to a different worktree: {top_level}",
        )
        result = subprocess.run(
            ["git", "-C", str(repo_root), "ls-files", "-z"],
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise VerificationError(f"Cannot enumerate tracked files in {repo_root}: {error}") from error
    return {item.decode("utf-8") for item in result.stdout.split(b"\0") if item}


def verify_bound_files(repo_root: Path, bindings: dict[str, dict[str, Any]]) -> bool:
    root = repo_root.resolve(strict=True)
    tracking_enforced = has_checkout_metadata(root)
    tracked = git_tracked_paths(root) if tracking_enforced else None
    for binding_id, binding in bindings.items():
        relative = binding["path"]
        if tracked is not None:
            require(relative in tracked, f"Binding is not Git-tracked: {binding_id}: {relative}")
        candidate = root / relative
        current = root
        for part in PurePosixPath(relative).parts:
            current = current / part
            try:
                mode = current.lstat().st_mode
            except OSError as error:
                raise VerificationError(f"Missing/unreadable binding {binding_id}: {relative}: {error}") from error
            require(not stat.S_ISLNK(mode), f"Symlink is forbidden in binding path {binding_id}: {relative}")
        try:
            resolved = candidate.resolve(strict=True)
        except OSError as error:
            raise VerificationError(f"Cannot resolve binding {binding_id}: {relative}: {error}") from error
        require(resolved.is_relative_to(root), f"Binding escapes repository: {binding_id}: {relative}")
        require(candidate.is_file(), f"Binding is not a regular file: {binding_id}: {relative}")
        actual_size = candidate.stat().st_size
        require(actual_size == binding["size_bytes"], f"Size mismatch for {binding_id}: expected {binding['size_bytes']}, got {actual_size}")
        digest = hashlib.sha256()
        with candidate.open("rb") as stream:
            for block in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(block)
        actual_digest = digest.hexdigest()
        require(actual_digest == binding["sha256"], f"SHA-256 mismatch for {binding_id}: expected {binding['sha256']}, got {actual_digest}")
    return tracking_enforced


def default_repo_root(script_path: Path) -> Path:
    try:
        script = script_path.resolve(strict=True)
    except OSError as error:
        raise VerificationError(f"Cannot resolve installed verifier {script_path}: {error}") from error
    root = script
    for _ in SCRIPT_RELATIVE_PATH.parts:
        root = root.parent
    expected_script = root / SCRIPT_RELATIVE_PATH
    try:
        installed_script = expected_script.resolve(strict=True)
    except OSError as error:
        raise VerificationError(f"Cannot resolve expected verifier path {expected_script}: {error}") from error
    require(
        installed_script == script and expected_script.is_file(),
        f"Verifier is not installed at expected repository-relative path {SCRIPT_RELATIVE_PATH}",
    )
    try:
        expected_manifest = (root / DEFAULT_MANIFEST_RELATIVE_PATH).resolve(strict=True)
    except OSError as error:
        raise VerificationError(
            f"Cannot resolve expected manifest {root / DEFAULT_MANIFEST_RELATIVE_PATH}: {error}"
        ) from error
    require(expected_manifest.is_relative_to(root), f"Expected manifest escapes repository: {expected_manifest}")
    require(expected_manifest.is_file(), f"Expected manifest is not a regular file: {expected_manifest}")
    return root


def verify(manifest_path: Path, repo_root: Path) -> tuple[int, bool]:
    payload = load_manifest(manifest_path)
    bindings = verify_schema(payload)
    tracking_enforced = verify_bound_files(repo_root, bindings)
    return len(payload["figures"]), tracking_enforced


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest", type=Path)
    parser.add_argument("--repo-root", type=Path)
    args = parser.parse_args()
    script = Path(__file__).resolve()
    try:
        repo_root = (args.repo_root or default_repo_root(script)).resolve(strict=True)
        manifest = args.manifest or (
            repo_root
            / DEFAULT_MANIFEST_RELATIVE_PATH
        )
        manifest = manifest.resolve(strict=True)
        require(manifest.is_relative_to(repo_root), f"Manifest is outside repository: {manifest}")
        count, tracking_enforced = verify(manifest, repo_root)
    except (OSError, VerificationError) as error:
        raise SystemExit(f"FAIL: {error}") from error
    tracking_note = (
        "Git tracking membership enforced"
        if tracking_enforced
        else "archive mode: Git tracking membership unavailable; all path and byte checks enforced"
    )
    print(f"PASS: verified {count} accepted figure records and all bound files ({tracking_note})")


if __name__ == "__main__":
    main()
