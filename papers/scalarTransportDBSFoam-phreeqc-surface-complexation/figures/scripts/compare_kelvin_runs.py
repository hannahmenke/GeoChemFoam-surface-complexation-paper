#!/usr/bin/env python3
"""Fail-closed Kelvin convergence and restart comparison.

The comparator authenticates schema-9 run manifests before reading results.
It uses decomposed mesh geometry for all inventories and spatial norms; no
field is clipped by the validator.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import re
from pathlib import Path
from typing import Any

import numpy as np


SCRIPT = Path(__file__).resolve()
TEST_SCRIPT = SCRIPT.with_name("test_compare_kelvin_runs.py")
REPO_ROOT = SCRIPT.parents[4]
PROVENANCE_PATH = (
    REPO_ROOT
    / "tutorials/reactiveTransport/reactiveTransportDBSFoam/"
      "3DKelvinSurfaceComplexation/kelvin_provenance.py"
)
SPEC = importlib.util.spec_from_file_location("kelvin_schema9_provenance", PROVENANCE_PATH)
if SPEC is None or SPEC.loader is None:
    raise RuntimeError(f"Cannot import Kelvin provenance module: {PROVENANCE_PATH}")
provenance = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(provenance)


SCHEMA_VERSION = 2
MANIFEST_SCHEMA_VERSION = 9
RANK_COUNT = 32
DECOMPOSITION = {"NPX": 2, "NPY": 4, "NPZ": 4}
NX = NY = NZ = 200
GLOBAL_CELL_COUNT = NX * NY * NZ
CELL_SIZE_M = 1.0e-5
CELL_VOLUME_M3 = CELL_SIZE_M**3
DOMAIN_LENGTH_M = NX * CELL_SIZE_M
END_TIME_S = 0.5
COARSE_DT_S = 0.0001953125
FINE_DT_S = 0.00009765625
RESTART_ENDPOINT_S = 0.025
RESTART_SPLIT_S = 0.0125
ACCEPTED_DT_S = COARSE_DT_S
NEGATIVE_TOLERANCE = -1.0e-12
CONVERGENCE_RELATIVE_TOLERANCE = 0.01
RESTART_RELATIVE_TOLERANCE = 1.0e-10
RESTART_FIELD_ABSOLUTE_TOLERANCE = 1.0e-17
RESTART_AMOUNT_ABSOLUTE_TOLERANCE_KMOL = 1.0e-24
FRONT_QUANTILES = (0.1, 0.5, 0.9)
EMPTY_SHA256 = hashlib.sha256(b"").hexdigest()

CELL_SCALARS = tuple(
    name for name in provenance.REQUIRED_INITIAL_FIELDS if name not in {"U", "phi"}
)
NONNEGATIVE_CELL_SCALARS = frozenset(name for name in CELL_SCALARS if name != "p")
MASS_FIELDS = (
    "eps", "aSurf", "aSurfIntrinsic", "Kinv", "Mn+2", "Mg+2", "Cl-",
    "Surf_sOMn+", "Surf_wOMn+", "Surf_wOMg+",
)
MN_FREE = "Mn2plus_free_aqueous_species"
MN_SORBED = "Mn_selected_surface_complex_species"
MG_FREE = "Mg2plus_free_aqueous_species"
MG_SORBED = "Mg_selected_surface_complex_species"
CL_FREE = "Clminus_free_aqueous_species"
MN_REPORTED = "Mn_reported_species_sum"
MG_REPORTED = "Mg_reported_species_sum"
STATIC_FIELDS = frozenset(
    {"eps", "aSurf", "aSurfIntrinsic", "Kinv", "Surf_s", "Surf_w"}
)
AQUEOUS_DIMENSIONS = (0, -3, 0, 0, 1, 0, 0)
SURFACE_DIMENSIONS = (0, -2, 0, 0, 1, 0, 0)
FIELD_SPECS: dict[str, tuple[str, tuple[int, ...], str]] = {
    **{
        name: ("volScalarField", AQUEOUS_DIMENSIONS, "cell_scalar")
        for name in ("Cl-", "H+", "Mg+2", "Mn+2", "OH-")
    },
    **{
        name: ("volScalarField", SURFACE_DIMENSIONS, "cell_scalar")
        for name in (
            "Surf_s", "Surf_sO-", "Surf_sOH", "Surf_sOMn+", "Surf_w",
            "Surf_wO-", "Surf_wOH", "Surf_wOMg+", "Surf_wOMn+",
        )
    },
    "eps": ("volScalarField", (0, 0, 0, 0, 0, 0, 0), "cell_scalar"),
    "aSurf": ("volScalarField", (0, -1, 0, 0, 0, 0, 0), "cell_scalar"),
    "aSurfIntrinsic": ("volScalarField", (0, -1, 0, 0, 0, 0, 0), "cell_scalar"),
    "Kinv": ("volScalarField", (0, -2, 0, 0, 0, 0, 0), "cell_scalar"),
    "p": ("volScalarField", (0, 2, -2, 0, 0, 0, 0), "cell_scalar"),
    "U": ("volVectorField", (0, 1, -1, 0, 0, 0, 0), "cell_vector"),
    "phi": ("surfaceScalarField", (0, 3, -1, 0, 0, 0, 0), "face_scalar"),
    "R": ("volScalarField", (0, 0, -1, 0, 0, 0, 0), "cell_scalar"),
}
INITIAL_STATE_FIELDS = frozenset(provenance.REQUIRED_INITIAL_FIELDS)
ENDPOINT_RESTART_STATE_FIELDS = INITIAL_STATE_FIELDS | {"R"}
CHECKPOINT_ARTIFACTS = frozenset(
    {"phreeqc.dmp", "phreeqc.complete", "phreeqc.complete.tmp"}
)
if set(FIELD_SPECS) != ENDPOINT_RESTART_STATE_FIELDS:
    raise RuntimeError("Kelvin endpoint field contracts do not match the solver state")
FATAL_LOG_PATTERN = re.compile(
    r"FOAM FATAL|MPI_ABORT|PHREEQC error|Floating point exception|Segmentation fault",
    re.IGNORECASE,
)
TOP_LEVEL_KEYS = {
    "schema_version", "case_id", "recorded_utc", "paper",
    "transport_control_template", "tracked_transport_control_template",
    "runtime", "runtime_artifacts", "surface", "intrinsic_surface",
    "chemistry", "realized_initialization_dictionaries", "transport_stages",
    "initial_case",
}
CONTROL_KEYS = {
    "application", "startFrom", "startTime", "stopAt", "endTime", "deltaT",
    "writeControl", "writeInterval", "purgeWrite", "writeFormat",
    "writePrecision", "writeCompression", "timeFormat", "timePrecision",
    "runTimeModifiable", "phreeqcRestartCheckpoints", "phreeqcRestoreCheckpoint",
}
ATTEMPT_KEYS = CONTROL_KEYS | {
    "stage_id", "attempt", "status", "chain_relation", "recorded_utc",
    "rank_count", "decomposition", "initial_case_identity_sha256",
    "immutable_dictionary_sha256", "immutable_control_sha256", "dictionaries",
    "surface_master_fields", "selected_start_time_directories",
    "start_rank_inputs", "restart_checkpoints",
}
COMPLETION_KEYS = {
    "completed_utc", "solver_exit_status", "solver_log",
    "endpoint_time_directories", "endpoint_rank_outputs", "endpoint_checkpoints",
}


class ComparisonError(RuntimeError):
    """Input evidence cannot support the requested comparison."""


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ComparisonError(message)


def exact_number(actual: object, expected: float, label: str, tolerance: float = 1e-15) -> None:
    require(type(actual) in (int, float), f"{label} must be numeric")
    value = float(actual)
    require(math.isfinite(value), f"{label} must be finite")
    require(
        math.isclose(value, expected, rel_tol=0.0, abs_tol=tolerance),
        f"{label} mismatch: {value:.17g} != {expected:.17g}",
    )


def unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ComparisonError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def reject_json_constant(value: str) -> None:
    raise ComparisonError(f"Non-finite JSON number: {value}")


def load_json(path: Path) -> dict[str, Any]:
    require(path.is_file() and not path.is_symlink(), f"Missing regular JSON file: {path}")
    try:
        payload = json.loads(
            path.read_text(), object_pairs_hook=unique_object,
            parse_constant=reject_json_constant,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as error:
        raise ComparisonError(f"Invalid JSON in {path}: {error}") from error
    require(isinstance(payload, dict), f"JSON root is not an object: {path}")
    return payload


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def file_record(path: Path) -> dict[str, object]:
    path = path.resolve()
    require(path.is_file(), f"Missing file: {path}")
    return {"path": str(path), "size_bytes": path.stat().st_size, "sha256": sha256(path)}


def call_provenance(function: Any, *args: object) -> Any:
    try:
        return function(*args)
    except SystemExit as error:
        raise ComparisonError(str(error)) from error


def bounded_regular_file(path: Path, roots: tuple[Path, ...], label: str) -> Path:
    resolved = path.resolve()
    require(path == resolved, f"{label} path is noncanonical or contains a symlink: {path}")
    selected_root: Path | None = None
    for root in roots:
        candidate = root.resolve()
        try:
            resolved.relative_to(candidate)
        except ValueError:
            continue
        selected_root = candidate
        break
    require(selected_root is not None, f"{label} path escapes its allowed roots: {path}")
    cursor = selected_root
    for part in resolved.relative_to(selected_root).parts:
        cursor = cursor / part
        require(not cursor.is_symlink(), f"{label} path contains a symlink: {cursor}")
    require(resolved.is_file(), f"Missing regular {label}: {resolved}")
    return resolved


def verify_absolute_record(
    record: object, label: str, expected: Path | None = None,
    roots: tuple[Path, ...] | None = None,
) -> Path:
    require(isinstance(record, dict), f"Malformed {label} record")
    path = Path(str(record.get("path", "")))
    require(path.is_absolute(), f"{label} path is not absolute: {path}")
    require(path.is_file() and not path.is_symlink(), f"Missing regular {label}: {path}")
    resolved = bounded_regular_file(path, roots, label) if roots else path.resolve()
    if expected is not None:
        require(resolved == expected.resolve(), f"Wrong {label} path: {resolved} != {expected.resolve()}")
    digest = str(record.get("sha256", ""))
    require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, f"Invalid {label} hash")
    require(sha256(resolved) == digest, f"{label} hash mismatch: {resolved}")
    return resolved


def list_payload(path: Path, expected_class: str) -> tuple[int, str]:
    require(path.is_file() and not path.is_symlink(), f"Missing mesh list: {path}")
    try:
        text = strip_foam_comments(path.read_text(encoding="ascii"), path)
    except (OSError, UnicodeDecodeError) as error:
        raise ComparisonError(f"Cannot read ASCII mesh list {path}: {error}") from error
    header_match = re.search(r"(?<![A-Za-z0-9_])FoamFile\s*\{", text)
    require(header_match is not None, f"Missing FoamFile header in {path}")
    opening = text.find("{", header_match.start())
    header, header_stop = delimited_payload(
        text, opening, "{", "}", f"FoamFile block in {path}"
    )
    require(singleton_entry(header, "format", path) == "ascii",
            f"Only ASCII mesh lists are supported: {path}")
    require(singleton_entry(header, "class", path) == expected_class,
            f"Wrong mesh-list class in {path}")
    require(singleton_entry(header, "object", path) == path.name,
            f"Wrong mesh-list object in {path}")
    prefix = re.match(r"\s*(\d+)\s*", text[header_stop:])
    require(prefix is not None, f"Cannot locate list count in {path}")
    count = int(prefix.group(1))
    opening = header_stop + prefix.end()
    require(opening < len(text) and text[opening] == "(",
            f"Cannot locate list payload in {path}")
    payload, stop = delimited_payload(text, opening, "(", ")", f"list payload in {path}")
    require(not text[stop:].strip(), f"Unexpected active tokens after list payload in {path}")
    return count, payload


def read_label_list(path: Path) -> np.ndarray:
    count, payload = list_payload(path, "labelList")
    tokens = payload.split()
    require(all(re.fullmatch(r"[+\-]?\d+", token) is not None for token in tokens),
            f"Malformed label payload in {path}")
    values = np.asarray([int(token) for token in tokens], dtype=np.int64)
    require(values.size == count, f"Label count mismatch in {path}: {values.size} != {count}")
    return values


def read_points(path: Path) -> np.ndarray:
    count, payload = list_payload(path, "vectorField")
    values = numeric_tokens(payload, path)
    require(values.size == 3 * count, f"Point count mismatch in {path}")
    result = values.reshape(count, 3)
    require(bool(np.all(np.isfinite(result))), f"Non-finite mesh point in {path}")
    return result


def read_quad_faces(path: Path) -> np.ndarray:
    count, payload = list_payload(path, "faceList")
    pattern = re.compile(
        r"4\s*\(\s*([+\-]?\d+)\s+([+\-]?\d+)\s+"
        r"([+\-]?\d+)\s+([+\-]?\d+)\s*\)"
    )
    matches = list(pattern.finditer(payload))
    residue = pattern.sub("", payload)
    require(len(matches) == count and not residue.strip(),
            f"Kelvin mesh must contain exactly {count} quadrilateral faces: {path}")
    return np.asarray(
        [[int(value) for value in match.groups()] for match in matches], dtype=np.int64
    )


def mesh_geometry(rank: Path) -> dict[str, np.ndarray]:
    mesh = rank / "constant/polyMesh"
    addressing = read_label_list(mesh / "cellProcAddressing")
    points = read_points(mesh / "points")
    faces = read_quad_faces(mesh / "faces")
    owners = read_label_list(mesh / "owner")
    neighbours = read_label_list(mesh / "neighbour")
    require(owners.size == faces.shape[0], f"Owner/face count mismatch in {mesh}")
    require(neighbours.size <= owners.size, f"Neighbour/face count mismatch in {mesh}")
    require(
        bool(np.all((faces >= 0) & (faces < points.shape[0]))),
        f"Out-of-range face point in {mesh}",
    )
    cell_count = addressing.size
    require(cell_count > 0, f"Empty decomposition rank: {rank}")
    require(
        bool(np.all((owners >= 0) & (owners < cell_count)))
        and bool(np.all((neighbours >= 0) & (neighbours < cell_count))),
        f"Out-of-range cell label in {mesh}",
    )

    # Tetrahedral moments are translation invariant for a closed cell, but
    # evaluating them about the global origin loses precision on remote MPI
    # patches.  A rank-local origin keeps all operands near the cell scale.
    reference = np.min(points, axis=0)
    vertices = (points - reference)[faces]
    p0, p1, p2, p3 = (vertices[:, index, :] for index in range(4))
    v1 = np.einsum("ij,ij->i", p0, np.cross(p1, p2)) / 6.0
    v2 = np.einsum("ij,ij->i", p0, np.cross(p2, p3)) / 6.0
    face_volume = v1 + v2
    face_moment = (
        v1[:, None] * (p0 + p1 + p2) / 4.0
        + v2[:, None] * (p0 + p2 + p3) / 4.0
    )
    volumes = np.zeros(cell_count, dtype=np.float64)
    moments = np.zeros((cell_count, 3), dtype=np.float64)
    np.add.at(volumes, owners, face_volume)
    np.add.at(moments, owners, face_moment)
    np.add.at(volumes, neighbours, -face_volume[:neighbours.size])
    np.add.at(moments, neighbours, -face_moment[:neighbours.size])
    require(bool(np.all(np.isfinite(volumes))) and bool(np.all(volumes > 0.0)),
            f"Invalid cell volume in {mesh}")
    centres = moments / volumes[:, None] + reference
    require(bool(np.all(np.isfinite(centres))), f"Invalid cell centre in {mesh}")

    require(
        bool(np.all((addressing >= 0) & (addressing < GLOBAL_CELL_COUNT))),
        f"Out-of-range global addressing in {mesh}",
    )
    i = addressing % NX
    j = (addressing // NX) % NY
    k = addressing // (NX * NY)
    expected_centres = (np.column_stack((i, j, k)) + 0.5) * CELL_SIZE_M
    require(
        bool(np.allclose(centres, expected_centres, rtol=0.0, atol=1.0e-12)),
        f"Mesh geometry/global addressing mismatch in {mesh}",
    )
    require(
        bool(np.allclose(volumes, CELL_VOLUME_M3, rtol=1.0e-10, atol=1.0e-27)),
        f"Kelvin cell-volume contract changed in {mesh}",
    )
    return {
        "addressing": addressing,
        "volumes": volumes,
        "centres": centres,
        "x_index": i,
        "internal_face_count": int(neighbours.size),
    }


FOAM_NUMBER = r"[+\-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+\-]?\d+)?"


def strip_foam_comments(text: str, path: Path) -> str:
    """Remove OpenFOAM comments while preserving token boundaries and newlines."""
    block_starts = [match.start() for match in re.finditer(r"/\*", text)]
    block_ends = [match.start() for match in re.finditer(r"\*/", text)]
    require(len(block_starts) == len(block_ends), f"Unterminated block comment in {path}")
    require(
        all(start < end for start, end in zip(block_starts, block_ends)),
        f"Malformed block-comment delimiters in {path}",
    )

    def blank(match: re.Match[str]) -> str:
        return "".join("\n" if character == "\n" else " " for character in match.group())

    blanked = re.sub(r"/\*.*?\*/|//[^\n]*", blank, text, flags=re.S)
    require("/*" not in blanked and "*/" not in blanked,
            f"Malformed block-comment delimiters in {path}")
    return blanked


def delimited_payload(
    text: str, start: int, opening: str, closing: str, label: str
) -> tuple[str, int]:
    require(start < len(text) and text[start] == opening, f"Missing {opening} for {label}")
    depth = 0
    for index in range(start, len(text)):
        if text[index] == opening:
            depth += 1
        elif text[index] == closing:
            depth -= 1
            if depth == 0:
                return text[start + 1:index], index + 1
    raise ComparisonError(f"Unterminated {label}")


def named_block(text: str, keyword: str, path: Path) -> str:
    matches = list(re.finditer(rf"(?<![A-Za-z0-9_]){re.escape(keyword)}\s*\{{", text))
    require(len(matches) == 1, f"Expected one {keyword} block in {path}, found {len(matches)}")
    opening = text.find("{", matches[0].start())
    payload, _ = delimited_payload(text, opening, "{", "}", f"{keyword} block in {path}")
    return payload


def singleton_entry(block: str, key: str, path: Path) -> str:
    matches = re.findall(rf"(?m)^\s*{re.escape(key)}\s+([^;]+)\s*;", block)
    require(len(matches) == 1, f"Expected one {key} entry in {path}, found {len(matches)}")
    return matches[0].strip()


def numeric_tokens(payload: str, path: Path) -> np.ndarray:
    tokens = payload.replace("(", " ").replace(")", " ").split()
    require(
        all(re.fullmatch(FOAM_NUMBER, token) is not None for token in tokens),
        f"Malformed numeric payload in {path}",
    )
    values = np.asarray([float(token) for token in tokens], dtype=np.float64)
    require(bool(np.all(np.isfinite(values))), f"Non-finite numeric payload in {path}")
    return values


def boundary_numeric_contract(
    boundary: str, path: Path
) -> tuple[np.ndarray, str]:
    """Validate boundary lists and separate physical values from list counts."""
    count_spans: set[tuple[int, int]] = set()
    list_pattern = re.compile(r"nonuniform\s+List<(scalar|vector)>\s+(\d+)\s*")
    cursor = 0
    while True:
        match = list_pattern.search(boundary, cursor)
        if match is None:
            break
        opening = match.end()
        require(opening < len(boundary) and boundary[opening] == "(",
                f"Malformed boundary nonuniform list in {path}")
        payload, stop = delimited_payload(
            boundary, opening, "(", ")", f"boundary nonuniform list in {path}"
        )
        count = int(match.group(2))
        width = 3 if match.group(1) == "vector" else 1
        require(
            numeric_tokens(payload, path).size == count * width,
            f"Boundary list count mismatch in {path}",
        )
        count_spans.add(match.span(2))
        cursor = stop

    pattern = re.compile(rf"(?<![A-Za-z0-9_]){FOAM_NUMBER}(?![A-Za-z0-9_])")
    values: list[float] = []
    structure: list[str] = []
    cursor = 0
    for match in pattern.finditer(boundary):
        structure.append(boundary[cursor:match.start()])
        if match.span() in count_spans:
            structure.append(match.group())
        else:
            values.append(float(match.group()))
            structure.append("<number>")
        cursor = match.end()
    structure.append(boundary[cursor:])
    result = np.asarray(values, dtype=np.float64)
    require(bool(np.all(np.isfinite(result))), f"Non-finite boundary field: {path}")
    return result, "".join(structure)


def read_foam_field(path: Path, expected_size: int) -> dict[str, object]:
    """Read one strict ASCII OpenFOAM field and validate its semantic metadata."""
    require(path.is_file() and not path.is_symlink(), f"Missing regular field: {path}")
    try:
        text = strip_foam_comments(path.read_text(encoding="ascii"), path)
    except (OSError, UnicodeDecodeError) as error:
        raise ComparisonError(f"Cannot read ASCII field {path}: {error}") from error
    require(
        re.search(r"(?<![A-Za-z])(?:nan|[+\-]?inf(?:inity)?)(?![A-Za-z])", text, re.I)
        is None,
        f"Non-finite token in field or boundary values: {path}",
    )
    name = path.name
    require(name in FIELD_SPECS, f"No Kelvin field contract for {name}")
    expected_class, expected_dimensions, kind = FIELD_SPECS[name]
    header = named_block(text, "FoamFile", path)
    require(singleton_entry(header, "format", path) == "ascii", f"Field is not ASCII: {path}")
    require(
        singleton_entry(header, "class", path) == expected_class,
        f"Wrong OpenFOAM class for {path}",
    )
    require(singleton_entry(header, "object", path) == name, f"Wrong object name in {path}")
    dimension_matches = re.findall(r"(?m)^\s*dimensions\s+\[([^]]+)\]\s*;", text)
    require(len(dimension_matches) == 1, f"Expected one dimensions entry in {path}")
    dimensions = numeric_tokens(dimension_matches[0], path)
    require(
        dimensions.size == 7 and tuple(dimensions.tolist()) == expected_dimensions,
        f"Wrong dimensions in {path}: {dimensions.tolist()} != {expected_dimensions}",
    )
    internal = list(re.finditer(r"(?m)^\s*internalField\s+", text))
    require(len(internal) == 1, f"Expected one active internalField in {path}")
    body = text[internal[0].end():]
    uniform = re.match(rf"uniform\s+({FOAM_NUMBER}|\([^;]*\))\s*;", body)
    if uniform:
        raw = numeric_tokens(uniform.group(1), path)
        expected_width = 3 if kind == "cell_vector" else 1
        require(raw.size == expected_width, f"Wrong uniform value width in {path}")
        values = (
            np.tile(raw, (expected_size, 1))
            if expected_width == 3
            else np.full(expected_size, raw[0], dtype=np.float64)
        )
    else:
        list_type = "vector" if kind == "cell_vector" else "scalar"
        prefix = re.match(rf"nonuniform\s+List<{list_type}>\s+(\d+)\s*", body)
        require(prefix is not None, f"Unsupported internalField in {path}")
        count = int(prefix.group(1))
        opening = internal[0].end() + prefix.end()
        while opening < len(text) and text[opening].isspace():
            opening += 1
        payload, stop = delimited_payload(text, opening, "(", ")", f"internalField in {path}")
        require(text[stop:].lstrip().startswith(";"), f"Missing internalField terminator in {path}")
        raw = numeric_tokens(payload, path)
        width = 3 if kind == "cell_vector" else 1
        require(count == expected_size, f"Field count mismatch in {path}: {count} != {expected_size}")
        require(raw.size == width * count, f"Value count mismatch in {path}")
        values = raw.reshape(count, width) if width == 3 else raw
    require(values.shape[0] == expected_size, f"Field count mismatch in {path}")
    require(bool(np.all(np.isfinite(values))), f"Non-finite internal field: {path}")
    boundary = " ".join(named_block(text, "boundaryField", path).split())
    boundary_values, boundary_structure = boundary_numeric_contract(boundary, path)
    return {
        "values": values,
        "boundary": boundary,
        "boundary_values": boundary_values,
        "boundary_structure": boundary_structure,
        "class": expected_class,
        "dimensions": list(expected_dimensions),
    }


def endpoint_state_field_names(directory: Path) -> frozenset[str]:
    """Discover the exact solver-written restart state at one endpoint."""
    require(directory.is_dir() and not directory.is_symlink(),
            f"Missing regular endpoint directory: {directory}")
    names: set[str] = set()
    for path in directory.iterdir():
        if path.name in CHECKPOINT_ARTIFACTS:
            require(not path.is_symlink(), f"Symlinked checkpoint artifact: {path}")
            continue
        if path.name == "uniform" and path.is_dir() and not path.is_symlink():
            # OpenFOAM stores time metadata and function-object data here.
            continue
        require(path.is_file() and not path.is_symlink(),
                f"Unexpected endpoint artifact: {path}")
        try:
            text = strip_foam_comments(path.read_text(encoding="ascii"), path)
        except (OSError, UnicodeDecodeError) as error:
            raise ComparisonError(f"Cannot inspect endpoint field {path}: {error}") from error
        header = named_block(text, "FoamFile", path)
        field_class = singleton_entry(header, "class", path)
        require(
            field_class in {"volScalarField", "volVectorField", "surfaceScalarField"},
            f"Unexpected endpoint non-field artifact: {path} (class {field_class})",
        )
        require(singleton_entry(header, "object", path) == path.name,
                f"Wrong object name in endpoint field: {path}")
        require(path.name not in names, f"Duplicate endpoint state field: {path.name}")
        names.add(path.name)
    require(
        names == ENDPOINT_RESTART_STATE_FIELDS,
        "Endpoint restart-state field set differs: "
        f"missing={sorted(ENDPOINT_RESTART_STATE_FIELDS - names)}, "
        f"unexpected={sorted(names - ENDPOINT_RESTART_STATE_FIELDS)}",
    )
    return frozenset(names)


def scalar_values(path: Path, expected_size: int) -> np.ndarray:
    values = np.asarray(read_foam_field(path, expected_size)["values"], dtype=np.float64)
    require(values.ndim == 1, f"Expected scalar field: {path}")
    return values


def vector_values(path: Path, expected_size: int) -> np.ndarray:
    values = np.asarray(read_foam_field(path, expected_size)["values"], dtype=np.float64)
    require(values.shape == (expected_size, 3), f"Expected vector field: {path}")
    return values


def update_statistics(target: dict[str, dict[str, object]], name: str, values: np.ndarray) -> None:
    if values.size == 0:
        target.setdefault(
            name,
            {"minimum": None, "maximum": None, "negative_count": 0,
             "below_negative_tolerance_count": 0, "value_count": 0},
        )
        return
    minimum = float(np.min(values))
    maximum = float(np.max(values))
    negative_count = int(np.count_nonzero(values < 0.0))
    below_tolerance = int(np.count_nonzero(values < NEGATIVE_TOLERANCE))
    if name in NONNEGATIVE_CELL_SCALARS:
        require(below_tolerance == 0,
                f"{name} contains {below_tolerance} values below {NEGATIVE_TOLERANCE:g}")
    record = target.setdefault(
        name,
        {"minimum": minimum, "maximum": maximum, "negative_count": 0,
         "below_negative_tolerance_count": 0, "value_count": 0},
    )
    record["minimum"] = (
        minimum if record["minimum"] is None else min(float(record["minimum"]), minimum)
    )
    record["maximum"] = (
        maximum if record["maximum"] is None else max(float(record["maximum"]), maximum)
    )
    record["negative_count"] = int(record["negative_count"]) + negative_count
    record["below_negative_tolerance_count"] = (
        int(record["below_negative_tolerance_count"]) + below_tolerance
    )
    record["value_count"] = int(record["value_count"]) + int(values.size)


def exact_time_directory(rank: Path, value: float) -> Path:
    return call_provenance(provenance.numeric_time_directory, rank, value)


def expected_time_record(case: Path, rank: Path, value: float) -> dict[str, str]:
    directory = exact_time_directory(rank, value)
    return {"rank": rank.name, "path": str(directory.resolve()), "time_name": directory.name}


def checkpoint_record(case: Path, rank: Path, value: float) -> dict[str, object]:
    directory = exact_time_directory(rank, value)
    return {
        "rank": rank.name,
        "time_name": directory.name,
        **call_provenance(provenance.checkpoint_record, directory, value, case, rank.name),
    }


def stage_snapshot_map(stage: dict[str, Any]) -> dict[Path, dict[str, Any]]:
    records = stage.get("dictionaries")
    require(isinstance(records, list), "Stage has no dictionary snapshots")
    result: dict[Path, dict[str, Any]] = {}
    for record in records:
        require(isinstance(record, dict) and isinstance(record.get("snapshot"), dict),
                "Malformed stage dictionary snapshot")
        source = Path(str(record.get("source", "")))
        require(source not in result, f"Duplicate stage dictionary snapshot: {source}")
        result[source] = record["snapshot"]
    return result


def snapshot_identity(records: object) -> list[dict[str, str]]:
    require(isinstance(records, list), "Missing dictionary snapshot records")
    result: list[dict[str, str]] = []
    for record in records:
        require(isinstance(record, dict) and isinstance(record.get("snapshot"), dict),
                "Malformed dictionary snapshot record")
        source = Path(str(record.get("source", "")))
        snapshot = record["snapshot"]
        result.append({"source": source.as_posix(), "sha256": str(snapshot.get("sha256", ""))})
    return sorted(result, key=lambda item: item["source"])


def stage_dictionary_contract(stage: dict[str, Any], case: Path) -> dict[str, object]:
    snapshots = stage_snapshot_map(stage)
    require(
        set(snapshots) == set(provenance.REQUIRED_REALIZED_DICTIONARIES),
        f"Incomplete realized dictionary set in {stage.get('stage_id')}",
    )
    control_source = Path("system/controlDict")
    control_record = snapshots[control_source]
    control_path = verify_absolute_record(
        control_record, f"{stage.get('stage_id')} control snapshot", roots=(case,)
    )
    controls = call_provenance(provenance.control_values, control_path)
    require(
        controls == {key: stage[key] for key in CONTROL_KEYS},
        f"Recorded controls differ from realized snapshot in {stage.get('stage_id')}",
    )
    require(
        call_provenance(provenance.immutable_control_digest, control_path)
        == stage.get("immutable_control_sha256"),
        f"Immutable control digest mismatch in {stage.get('stage_id')}",
    )
    dictionary_records = []
    for source in sorted(snapshots):
        if source == control_source:
            continue
        path = verify_absolute_record(
            snapshots[source], f"{stage.get('stage_id')} {source} snapshot", roots=(case,)
        )
        dictionary_records.append({"path": str(source), "sha256": sha256(path)})
    digest = call_provenance(provenance.records_digest, dictionary_records)
    require(
        digest == stage.get("immutable_dictionary_sha256"),
        f"Immutable dictionary digest mismatch in {stage.get('stage_id')}",
    )
    return {
        "noncontrol_snapshots": [
            record for record in snapshot_identity(stage["dictionaries"])
            if record["source"] != control_source.as_posix()
        ],
        "canonical_control_contract": call_provenance(
            provenance.canonical_control_contract, control_path
        ),
    }


def verify_surface_record(record: object, label: str, case: Path, filename: str) -> None:
    path = verify_absolute_record(record, label, case / filename, (case,))
    assert isinstance(record, dict)
    rebuilt = call_provenance(
        provenance.surface_record, path, str(record.get("mode", "")),
        float(record.get("sigma_vox")),
    )
    require(rebuilt == record, f"{label} record no longer matches its source")


def verify_manifest_identity(payload: dict[str, Any], case: Path) -> None:
    require(set(payload) == TOP_LEVEL_KEYS,
            f"Schema-9 manifest keys differ: {sorted(set(payload) ^ TOP_LEVEL_KEYS)}")
    require(payload.get("case_id") == "3d_kelvin", "Wrong case_id in run manifest")
    require(payload.get("schema_version") == MANIFEST_SCHEMA_VERSION,
            "Run manifest is not schema version 9")
    call_provenance(provenance.validate_recorded_runtime, payload)
    call_provenance(provenance.validate_recorded_paper, payload)
    call_provenance(
        provenance.validate_control_template_record, payload, case / "system/controlDict1"
    )
    runtime = payload["runtime"]
    require(runtime.get("tracked_diff_sha256") == EMPTY_SHA256,
            "GeoChemFoam runtime was not clean")
    require(isinstance(runtime.get("phreeqcrm"), dict)
            and runtime["phreeqcrm"].get("tracked_diff_sha256") == EMPTY_SHA256,
            "PHREEQCRM runtime was not clean")
    chemistry = payload.get("chemistry")
    require(isinstance(chemistry, dict), "Missing chemistry identity")
    chemistry_files = chemistry.get("files")
    require(isinstance(chemistry_files, list) and chemistry_files,
            "Missing chemistry/input records")
    paper = payload.get("paper")
    require(isinstance(paper, dict), "Missing paper identity")
    paper_root = Path(str(paper.get("root", ""))).resolve()
    for index, record in enumerate(chemistry_files):
        verify_absolute_record(
            record, f"chemistry/input record {index}", roots=(case, paper_root)
        )
    call_provenance(provenance.verify_file_records, chemistry_files)
    verify_surface_record(
        payload.get("surface"), "surface-construction log", case,
        "createASurfReactive.out",
    )
    verify_surface_record(
        payload.get("intrinsic_surface"), "intrinsic-surface log", case,
        "createASurfIntrinsicReactive.out",
    )
    call_provenance(
        provenance.verify_dictionary_snapshots,
        payload.get("realized_initialization_dictionaries"), case,
        case / "provenance/initialization",
    )


def verify_stage_chain(
    payload: dict[str, Any], case: Path, ranks: list[Path], expected_endpoint: float
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, object]]:
    initial = payload.get("initial_case")
    require(isinstance(initial, dict) and set(initial) == {"sha256", "records"},
            "Missing exact initial-case record")
    current_initial: list[dict[str, object]] = []
    for rank in ranks:
        current_initial.extend(call_provenance(provenance.tree_records, rank / "0", case))
        current_initial.extend(
            call_provenance(provenance.tree_records, rank / "constant/polyMesh", case)
        )
    require(current_initial == initial["records"], "Initial decomposed fields or mesh changed")
    require(call_provenance(provenance.records_digest, current_initial) == initial["sha256"],
            "Initial-case identity digest is inconsistent")

    stages = payload.get("transport_stages")
    require(isinstance(stages, list) and stages, "Manifest has no transport stages")
    completed: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    pending_attempts: list[dict[str, Any]] = []
    authoritative_end = 0.0
    pending_interval: tuple[float, float] | None = None
    pending_attempt = 0
    invariant: tuple[object, ...] | None = None
    dictionary_contract: dict[str, object] | None = None
    seen_stage_ids: set[str] = set()

    for index, stage in enumerate(stages):
        require(isinstance(stage, dict), f"Malformed stage {index}")
        status = stage.get("status")
        expected_keys = ATTEMPT_KEYS | (COMPLETION_KEYS if status == "completed" else set())
        require(set(stage) == expected_keys,
                f"Stage {index} keys differ: {sorted(set(stage) ^ expected_keys)}")
        require(status in {"attempted", "completed"}, f"Invalid stage status: {status}")
        stage_id = str(stage.get("stage_id", ""))
        require(stage_id not in seen_stage_ids, f"Duplicate stage id: {stage_id}")
        seen_stage_ids.add(stage_id)
        start = float(stage["startTime"])
        end = float(stage["endTime"])
        delta_t = float(stage["deltaT"])
        require(all(math.isfinite(value) for value in (start, end, delta_t)),
                f"Non-finite time in {stage_id}")
        require(end > start and delta_t > 0.0, f"Invalid stage interval in {stage_id}")
        exact_number(stage["writeInterval"], end - start, f"{stage_id} write interval", 1e-12)
        require(stage.get("phreeqcRestartCheckpoints") is True,
                f"Checkpoint writing disabled in {stage_id}")
        require(stage.get("phreeqcRestoreCheckpoint") is (start != 0.0),
                f"Wrong restore mode in {stage_id}")
        require(stage.get("rank_count") == RANK_COUNT, f"Wrong rank count in {stage_id}")
        require(stage.get("decomposition") == DECOMPOSITION,
                f"Wrong decomposition in {stage_id}")

        this_invariant = (
            stage["deltaT"], stage["rank_count"], stage["decomposition"],
            stage["initial_case_identity_sha256"], stage["immutable_dictionary_sha256"],
            stage["immutable_control_sha256"],
        )
        if invariant is None:
            invariant = this_invariant
            require(math.isclose(start, 0.0, rel_tol=0.0, abs_tol=1e-12),
                    "First Kelvin stage does not start at zero")
        else:
            require(this_invariant == invariant, f"Stage invariants changed in {stage_id}")
        require(stage["initial_case_identity_sha256"] == initial["sha256"],
                f"Initial-case identity mismatch in {stage_id}")

        if pending_interval is None:
            require(math.isclose(start, authoritative_end, rel_tol=0.0, abs_tol=1e-12),
                    f"Stage chain skips or backtracks at {stage_id}")
            pending_interval = (start, end)
            pending_attempt = 1
            expected_relation = "initial" if not completed else "continuation"
        else:
            require((start, end) == pending_interval,
                    f"Only an exact retry may follow an attempted stage: {stage_id}")
            pending_attempt += 1
            expected_relation = "retry"
        require(stage.get("attempt") == pending_attempt,
                f"Non-sequential attempt number in {stage_id}")
        require(stage.get("chain_relation") == expected_relation,
                f"Wrong chain relation in {stage_id}")

        call_provenance(
            provenance.verify_dictionary_snapshots, stage.get("dictionaries"), case,
            case / "provenance/stages" / stage_id,
        )
        current_dictionary_contract = stage_dictionary_contract(stage, case)
        if dictionary_contract is None:
            dictionary_contract = current_dictionary_contract
        else:
            require(
                current_dictionary_contract == dictionary_contract,
                f"Realized non-stage dictionary contract changed in {stage_id}",
            )
        selected = [expected_time_record(case, rank, start) for rank in ranks]
        require(stage.get("selected_start_time_directories") == selected,
                f"Selected start directories changed in {stage_id}")
        current_start: list[dict[str, object]] = []
        for rank in ranks:
            current_start.extend(
                call_provenance(
                    provenance.tree_records, exact_time_directory(rank, start), case,
                    {"phreeqc.dmp", "phreeqc.complete", "phreeqc.complete.tmp"},
                )
            )
        require(stage.get("start_rank_inputs") == current_start,
                f"Start fields changed in {stage_id}")
        restart_checkpoints = (
            [] if start == 0.0 else [checkpoint_record(case, rank, start) for rank in ranks]
        )
        require(stage.get("restart_checkpoints") == restart_checkpoints,
                f"Start checkpoints changed in {stage_id}")

        master_records = []
        for rank in ranks:
            start_dir = exact_time_directory(rank, start)
            for name, expected in (("Surf_s", 2e-7), ("Surf_w", 6e-6)):
                path = start_dir / name
                exact_number(call_provenance(provenance.uniform, path), expected,
                             f"{stage_id} {rank.name} {name}")
                master_records.append(
                    {"path": str(path.resolve()), "sha256": sha256(path),
                     "value_kmol_m2": expected}
                )
        require(stage.get("surface_master_fields") == master_records,
                f"Surface-master fields changed in {stage_id}")

        if status == "attempted":
            pending_attempts.append(
                {"stage_id": stage_id, "status": status, "superseded": True}
            )
            continue

        require(stage.get("solver_exit_status") == 0,
                f"Nonzero solver status in {stage_id}")
        log = verify_absolute_record(
            stage.get("solver_log"), f"{stage_id} solver log", roots=(case,)
        )
        text = log.read_text(errors="replace")
        require(FATAL_LOG_PATTERN.search(text) is None, f"Fatal solver log: {log}")
        times = re.findall(r"^\s*Time\s*=\s*([0-9.eE+\-]+)\s*$", text, re.M)
        require(times and math.isclose(float(times[-1]), end, rel_tol=0.0, abs_tol=1e-12),
                f"Solver log does not reach {end:g}: {log}")
        end_positions = [match.start() for match in re.finditer(r"^\s*End\s*$", text, re.M)]
        last_time = list(re.finditer(r"^\s*Time\s*=", text, re.M))[-1].start()
        require(end_positions and end_positions[-1] > last_time,
                f"Solver log has no clean End after endpoint: {log}")

        endpoint_dirs = [expected_time_record(case, rank, end) for rank in ranks]
        require(stage.get("endpoint_time_directories") == endpoint_dirs,
                f"Endpoint directories changed in {stage_id}")
        current_outputs: list[dict[str, object]] = []
        for rank in ranks:
            endpoint_state_field_names(exact_time_directory(rank, end))
            current_outputs.extend(
                call_provenance(
                    provenance.tree_records, exact_time_directory(rank, end), case,
                    {"phreeqc.dmp", "phreeqc.complete", "phreeqc.complete.tmp"},
                )
            )
        require(stage.get("endpoint_rank_outputs") == current_outputs,
                f"Endpoint outputs changed in {stage_id}")
        checkpoints = [checkpoint_record(case, rank, end) for rank in ranks]
        require(stage.get("endpoint_checkpoints") == checkpoints,
                f"Endpoint checkpoints changed in {stage_id}")

        for attempt in pending_attempts:
            attempt["superseded_by"] = stage_id
        attempts.extend(pending_attempts)
        pending_attempts = []
        completed.append(stage)
        authoritative_end = end
        pending_interval = None
        pending_attempt = 0

    require(pending_interval is None, "Latest Kelvin stage is incomplete")
    exact_number(authoritative_end, expected_endpoint, "final Kelvin endpoint", 1e-12)
    require(completed, "No completed Kelvin stage")

    expected_times = {0.0}
    for stage in stages:
        expected_times.add(float(stage["startTime"]))
        if stage["status"] == "completed":
            expected_times.add(float(stage["endTime"]))
    for rank in ranks:
        numeric: dict[float, str] = {}
        for path in rank.iterdir():
            if not path.is_dir():
                continue
            try:
                value = float(path.name)
            except ValueError:
                continue
            require(not path.is_symlink(), f"Symlinked time directory: {path}")
            require(value not in numeric, f"Duplicate numeric time {value:g} in {rank}")
            numeric[value] = path.name
        require(set(numeric) == expected_times,
                f"Unrecorded, stale, or missing numeric time in {rank}: "
                f"actual={sorted(numeric)}, expected={sorted(expected_times)}")
    temporary = list(case.glob("processor*/**/phreeqc*.tmp*"))
    require(not temporary, f"Checkpoint temporary files remain: {temporary[:3]}")

    latest_snapshots = stage_snapshot_map(completed[-1])
    for source, snapshot in latest_snapshots.items():
        verify_absolute_record(snapshot, f"latest {source} snapshot")
        require(sha256(case / source) == snapshot["sha256"],
                f"Current realized dictionary differs from final completed stage: {source}")

    schedule = [
        {
            "stage_id": stage["stage_id"], "start_time_s": stage["startTime"],
            "end_time_s": stage["endTime"], "restore": stage["phreeqcRestoreCheckpoint"],
        }
        for stage in completed
    ]
    return completed, attempts, {
        "initial_case_sha256": initial["sha256"],
        "completed_stage_count": len(completed),
        "superseded_attempt_count": len(attempts),
        "completed_schedule": schedule,
        "all_stage_records_recomputed": True,
        "all_checkpoint_pairs_valid": True,
        "unrecorded_numeric_time_count": 0,
        "dictionary_contract": dictionary_contract,
    }


def scan_timepoint(
    case: Path, ranks: list[Path], time_value: float
) -> dict[str, object]:
    statistics: dict[str, dict[str, object]] = {}
    boundary_statistics: dict[str, dict[str, object]] = {}
    local_counts: list[int] = []
    boundary_records: list[dict[str, str]] = []
    for rank in ranks:
        addressing = read_label_list(rank / "constant/polyMesh/cellProcAddressing")
        internal_faces = read_label_list(rank / "constant/polyMesh/neighbour").size
        local_counts.append(int(addressing.size))
        directory = exact_time_directory(rank, time_value)
        scalar_names = CELL_SCALARS + (() if time_value == 0.0 else ("R",))
        for name in scalar_names:
            parsed = read_foam_field(directory / name, addressing.size)
            values = np.asarray(parsed["values"], dtype=np.float64)
            update_statistics(statistics, name, values)
            update_statistics(
                boundary_statistics, name,
                np.asarray(parsed["boundary_values"], dtype=np.float64),
            )
            boundary_records.append(
                {
                    "rank": rank.name, "field": name,
                    "sha256": hashlib.sha256(str(parsed["boundary"]).encode()).hexdigest(),
                }
            )
        for name, size in (("U", addressing.size), ("phi", int(internal_faces))):
            parsed = read_foam_field(directory / name, size)
            update_statistics(statistics, name, np.asarray(parsed["values"], dtype=np.float64))
            update_statistics(
                boundary_statistics, name,
                np.asarray(parsed["boundary_values"], dtype=np.float64),
            )
            boundary_records.append(
                {
                    "rank": rank.name, "field": name,
                    "sha256": hashlib.sha256(str(parsed["boundary"]).encode()).hexdigest(),
                }
            )
    return {
        "time_s": time_value,
        "local_cell_counts": local_counts,
        "field_statistics": statistics,
        "boundary_value_statistics": boundary_statistics,
        "boundary_field_records": boundary_records,
        "negative_tolerance": NEGATIVE_TOLERANCE,
        "all_internal_field_values_finite": True,
        "all_boundary_field_values_finite": True,
        "all_field_classes_objects_and_dimensions_valid": True,
        "all_analytically_nonnegative_internal_and_boundary_fields_within_tolerance": True,
    }


def verify_static_timepoints(
    ranks: list[Path], time_values: list[float]
) -> dict[str, object]:
    checked = sorted(set(time_values))
    for rank in ranks:
        cell_count = read_label_list(rank / "constant/polyMesh/cellProcAddressing").size
        baseline = {
            name: read_foam_field(exact_time_directory(rank, 0.0) / name, cell_count)
            for name in STATIC_FIELDS
        }
        for value in checked:
            current_dir = exact_time_directory(rank, value)
            for name in STATIC_FIELDS:
                current = read_foam_field(current_dir / name, cell_count)
                require(
                    np.array_equal(current["values"], baseline[name]["values"]),
                    f"Static internal field changed at {value:g}: {rank.name}/{name}",
                )
                require(
                    current["boundary"] == baseline[name]["boundary"],
                    f"Static boundary field changed at {value:g}: {rank.name}/{name}",
                )
    return {
        "fields": sorted(STATIC_FIELDS),
        "times_s": checked,
        "all_internal_and_boundary_values_equal_to_time_zero": True,
    }


def normalized_input_records(payload: dict[str, Any], case: Path) -> list[dict[str, str]]:
    paper = payload.get("paper")
    chemistry = payload.get("chemistry")
    require(isinstance(paper, dict) and isinstance(chemistry, dict), "Missing pair identity")
    paper_root = Path(str(paper.get("root", ""))).resolve()
    result = []
    for record in chemistry.get("files", []):
        require(isinstance(record, dict), "Malformed chemistry input record")
        path = Path(str(record.get("path", ""))).resolve()
        try:
            role = "case/" + path.relative_to(case).as_posix()
        except ValueError:
            try:
                role = "paper/" + path.relative_to(paper_root).as_posix()
            except ValueError as error:
                raise ComparisonError(f"Chemistry/input path has no bounded role: {path}") from error
        result.append({"role": role, "sha256": str(record.get("sha256", ""))})
    roles = [record["role"] for record in result]
    require(len(roles) == len(set(roles)), "Duplicate chemistry/input role")
    return result


def code_identity(payload: dict[str, Any]) -> dict[str, object]:
    runtime = payload["runtime"]
    phreeqcrm = runtime["phreeqcrm"]
    paper = payload["paper"]
    artifacts = payload["runtime_artifacts"]
    return {
        "geochemfoam": {
            "commit": runtime["commit"], "tree": runtime["tree"],
            "tracked_diff_sha256": runtime["tracked_diff_sha256"],
            "phreeqcrm_gitlink": runtime["phreeqcrm_gitlink"],
        },
        "phreeqcrm": {
            "commit": phreeqcrm["commit"], "tree": phreeqcrm["tree"],
            "tracked_diff_sha256": phreeqcrm["tracked_diff_sha256"],
        },
        "runtime_artifact_identity_sha256": artifacts["identity_sha256"],
        "paper": {
            "commit": paper["commit"], "tree": paper["tree"],
            "tracked_diff_sha256": paper["tracked_diff_sha256"],
        },
    }


def verify_pair_identity(
    left: dict[str, Any], right: dict[str, Any], left_case: Path, right_case: Path
) -> dict[str, object]:
    identity = code_identity(left)
    require(code_identity(right) == identity, "Code/runtime/paper identities differ")
    require(left["runtime"] == right["runtime"],
            "Pair did not use the same exact runtime root and source identity")
    require(left["runtime_artifacts"] == right["runtime_artifacts"],
            "Runtime binaries, libraries, compiler, MPI, or environment differ")
    initialization_identity = snapshot_identity(
        left["realized_initialization_dictionaries"]
    )
    require(
        initialization_identity
        == snapshot_identity(right["realized_initialization_dictionaries"]),
        "Realized initialization dictionaries differ",
    )
    left_inputs = normalized_input_records(left, left_case)
    right_inputs = normalized_input_records(right, right_case)
    require(left_inputs == right_inputs, "Chemistry, geometry, or case inputs differ")
    left_initial = left["initial_case"]
    right_initial = right["initial_case"]
    require(left_initial == right_initial, "Initial decomposed fields or mesh differ")
    surface_identity = left["surface"] | {"path": None}
    intrinsic_surface_identity = left["intrinsic_surface"] | {"path": None}
    require(surface_identity == right["surface"] | {"path": None},
            "Surface-construction evidence differs")
    require(
        intrinsic_surface_identity == right["intrinsic_surface"] | {"path": None},
        "Intrinsic-surface evidence differs",
    )
    left_stages = left.get("transport_stages")
    right_stages = right.get("transport_stages")
    require(isinstance(left_stages, list) and isinstance(right_stages, list),
            "Missing stage dictionaries in pair identity")
    left_contracts = [stage_dictionary_contract(stage, left_case) for stage in left_stages]
    right_contracts = [stage_dictionary_contract(stage, right_case) for stage in right_stages]
    require(left_contracts and right_contracts, "Pair has no realized stage dictionaries")
    require(
        left_contracts[0] == right_contracts[0],
        "Realized stage dictionaries or immutable control contract differ",
    )
    return {
        **identity,
        "initial_case_sha256": left_initial["sha256"],
        "chemistry_and_case_inputs": left_inputs,
        "surface_construction": surface_identity,
        "intrinsic_surface_construction": intrinsic_surface_identity,
        "realized_initialization_dictionaries": initialization_identity,
        "realized_stage_dictionary_contract": left_contracts[0],
        "same_exact_runtime": True,
        "same_initial_decomposed_mesh_and_fields": True,
        "same_chemistry_geometry_and_case_inputs": True,
        "same_realized_initialization_and_stage_dictionaries": True,
    }


def inventory_arrays(fields: dict[str, np.ndarray], volumes: np.ndarray) -> dict[str, np.ndarray]:
    aqueous_weight = fields["eps"] * volumes
    surface_weight = fields["aSurf"] * volumes
    return {
        MN_FREE: fields["Mn+2"] * aqueous_weight,
        MN_SORBED: (fields["Surf_sOMn+"] + fields["Surf_wOMn+"]) * surface_weight,
        MG_FREE: fields["Mg+2"] * aqueous_weight,
        MG_SORBED: fields["Surf_wOMg+"] * surface_weight,
        CL_FREE: fields["Cl-"] * aqueous_weight,
    }


def load_mass_fields(directory: Path, count: int) -> dict[str, np.ndarray]:
    return {name: scalar_values(directory / name, count) for name in MASS_FIELDS}


def add_global_addressing(
    coverage: np.ndarray, addressing: np.ndarray, rank_label: str
) -> None:
    require(
        np.unique(addressing).size == addressing.size,
        f"Duplicate global cells within {rank_label}",
    )
    require(
        bool(np.all((addressing >= 0) & (addressing < coverage.size))),
        f"Out-of-range global cells within {rank_label}",
    )
    np.add.at(coverage, addressing, 1)


def empty_inventory() -> dict[str, list[float]]:
    return {name: [] for name in (MN_FREE, MN_SORBED, MG_FREE, MG_SORBED, CL_FREE)}


def inventory_totals(parts: dict[str, list[float]]) -> dict[str, float]:
    result = {name: math.fsum(values) for name, values in parts.items()}
    result[MN_REPORTED] = result[MN_FREE] + result[MN_SORBED]
    result[MG_REPORTED] = result[MG_FREE] + result[MG_SORBED]
    return result


def front_positions(profile: np.ndarray) -> dict[str, Any]:
    require(bool(np.all(np.isfinite(profile))), "Inventory profile is non-finite")
    require(bool(np.all(profile >= 0.0)),
            "Inventory profile contains negative bins; front location would require clipping")
    total = float(np.sum(profile, dtype=np.float64))
    require(math.isfinite(total), "Inventory profile total is non-finite")
    if total == 0.0:
        return {"defined": False, "quantiles": {}}
    cumulative = np.cumsum(profile, dtype=np.float64)
    require(bool(np.all(np.diff(cumulative) >= 0.0)),
            "Inventory profile is not monotone after nonnegative validation")
    quantiles: dict[str, dict[str, object]] = {}
    for quantile in FRONT_QUANTILES:
        index = int(np.searchsorted(cumulative, quantile * total, side="left"))
        require(0 <= index < NX, "Front index is outside the Kelvin domain")
        quantiles[f"x{int(100 * quantile)}"] = {
            "cell_index": index,
            "position_m": (index + 0.5) * CELL_SIZE_M,
        }
    return {"defined": True, "quantiles": quantiles}


def front_cell_shifts(deltas: dict[str, dict[str, Any]]) -> list[int]:
    return [
        abs(int(record["cell_index_delta"]))
        for phase in deltas.values()
        if phase["defined"]
        for record in phase["quantiles"].values()
    ]


def scientific_metrics(
    left_case: Path, right_case: Path, left_endpoint: float, right_endpoint: float,
    left_label: str, right_label: str,
) -> dict[str, object]:
    left_parts = empty_inventory()
    right_parts = empty_inventory()
    left_initial_parts = empty_inventory()
    right_initial_parts = empty_inventory()
    absolute_difference = {name: [] for name in left_parts}
    profiles = {
        left_label: {MN_FREE: np.zeros(NX), MN_SORBED: np.zeros(NX)},
        right_label: {MN_FREE: np.zeros(NX), MN_SORBED: np.zeros(NX)},
    }
    coverage = np.zeros(GLOBAL_CELL_COUNT, dtype=np.uint8)
    total_local_cells = 0
    geometry_min = math.inf
    geometry_max = -math.inf
    max_volume_deviation = 0.0
    field_abs_difference = {name: [] for name in ENDPOINT_RESTART_STATE_FIELDS}
    field_left_norm = {name: [] for name in ENDPOINT_RESTART_STATE_FIELDS}
    field_right_norm = {name: [] for name in ENDPOINT_RESTART_STATE_FIELDS}
    boundary_abs_difference = {name: [] for name in ENDPOINT_RESTART_STATE_FIELDS}
    boundary_left_norm = {name: [] for name in ENDPOINT_RESTART_STATE_FIELDS}
    boundary_right_norm = {name: [] for name in ENDPOINT_RESTART_STATE_FIELDS}
    boundary_structure_equal = {name: True for name in ENDPOINT_RESTART_STATE_FIELDS}
    field_maximum_absolute_difference = {
        name: 0.0 for name in ENDPOINT_RESTART_STATE_FIELDS
    }
    field_maximum_absolute_magnitude = {
        name: 0.0 for name in ENDPOINT_RESTART_STATE_FIELDS
    }
    boundary_maximum_absolute_difference = {
        name: 0.0 for name in ENDPOINT_RESTART_STATE_FIELDS
    }
    boundary_maximum_absolute_magnitude = {
        name: 0.0 for name in ENDPOINT_RESTART_STATE_FIELDS
    }

    for rank_number in range(RANK_COUNT):
        left_rank = left_case / f"processor{rank_number}"
        right_rank = right_case / f"processor{rank_number}"
        left_geometry = mesh_geometry(left_rank)
        right_geometry = mesh_geometry(right_rank)
        for name in ("addressing", "volumes", "centres"):
            require(np.array_equal(left_geometry[name], right_geometry[name]),
                    f"Pair mesh geometry differs on processor{rank_number}: {name}")
        addressing = left_geometry["addressing"]
        require(
            left_geometry["internal_face_count"] == right_geometry["internal_face_count"],
            f"Pair internal-face count differs on processor{rank_number}",
        )
        add_global_addressing(coverage, addressing, f"processor{rank_number}")
        total_local_cells += int(addressing.size)
        volumes = left_geometry["volumes"]
        geometry_min = min(geometry_min, float(np.min(volumes)))
        geometry_max = max(geometry_max, float(np.max(volumes)))
        max_volume_deviation = max(
            max_volume_deviation, float(np.max(np.abs(volumes - CELL_VOLUME_M3)))
        )
        count = addressing.size
        for name in sorted(ENDPOINT_RESTART_STATE_FIELDS):
            _, _, kind = FIELD_SPECS[name]
            field_count = (
                int(left_geometry["internal_face_count"])
                if kind == "face_scalar" else int(count)
            )
            left_parsed = read_foam_field(
                exact_time_directory(left_rank, left_endpoint) / name, field_count
            )
            right_parsed = read_foam_field(
                exact_time_directory(right_rank, right_endpoint) / name, field_count
            )
            left_values = np.asarray(left_parsed["values"], dtype=np.float64).reshape(-1)
            right_values = np.asarray(right_parsed["values"], dtype=np.float64).reshape(-1)
            require(left_values.shape == right_values.shape,
                    f"Restart-state field shape differs: processor{rank_number}/{name}")
            field_abs_difference[name].append(float(np.sum(np.abs(left_values - right_values))))
            field_left_norm[name].append(float(np.sum(np.abs(left_values))))
            field_right_norm[name].append(float(np.sum(np.abs(right_values))))
            if left_values.size:
                field_maximum_absolute_difference[name] = max(
                    field_maximum_absolute_difference[name],
                    float(np.max(np.abs(left_values - right_values))),
                )
                field_maximum_absolute_magnitude[name] = max(
                    field_maximum_absolute_magnitude[name],
                    float(np.max(np.maximum(np.abs(left_values), np.abs(right_values)))),
                )
            left_boundary = np.asarray(left_parsed["boundary_values"], dtype=np.float64)
            right_boundary = np.asarray(right_parsed["boundary_values"], dtype=np.float64)
            require(left_boundary.shape == right_boundary.shape,
                    f"Boundary field shape differs: processor{rank_number}/{name}")
            boundary_structure_equal[name] = bool(
                boundary_structure_equal[name]
                and left_parsed["boundary_structure"] == right_parsed["boundary_structure"]
            )
            boundary_abs_difference[name].append(
                float(np.sum(np.abs(left_boundary - right_boundary)))
            )
            boundary_left_norm[name].append(float(np.sum(np.abs(left_boundary))))
            boundary_right_norm[name].append(float(np.sum(np.abs(right_boundary))))
            if left_boundary.size:
                boundary_maximum_absolute_difference[name] = max(
                    boundary_maximum_absolute_difference[name],
                    float(np.max(np.abs(left_boundary - right_boundary))),
                )
                boundary_maximum_absolute_magnitude[name] = max(
                    boundary_maximum_absolute_magnitude[name],
                    float(np.max(np.maximum(np.abs(left_boundary), np.abs(right_boundary)))),
                )
        left_fields = load_mass_fields(exact_time_directory(left_rank, left_endpoint), count)
        right_fields = load_mass_fields(exact_time_directory(right_rank, right_endpoint), count)
        for name in ("eps", "aSurf", "aSurfIntrinsic", "Kinv"):
            require(np.array_equal(left_fields[name], right_fields[name]),
                    f"{name} differs on processor{rank_number}")
        left_mass = inventory_arrays(left_fields, volumes)
        right_mass = inventory_arrays(right_fields, volumes)
        for name in left_parts:
            left_parts[name].append(float(np.sum(left_mass[name], dtype=np.float64)))
            right_parts[name].append(float(np.sum(right_mass[name], dtype=np.float64)))
            absolute_difference[name].append(
                float(np.sum(np.abs(left_mass[name] - right_mass[name]), dtype=np.float64))
            )
        for label, mass in ((left_label, left_mass), (right_label, right_mass)):
            for name in (MN_FREE, MN_SORBED):
                profiles[label][name] += np.bincount(
                    left_geometry["x_index"], weights=mass[name], minlength=NX
                )

        left_initial_fields = load_mass_fields(exact_time_directory(left_rank, 0.0), count)
        right_initial_fields = load_mass_fields(exact_time_directory(right_rank, 0.0), count)
        for name in MASS_FIELDS:
            require(np.array_equal(left_initial_fields[name], right_initial_fields[name]),
                    f"Initial mass field differs on processor{rank_number}: {name}")
        left_initial_mass = inventory_arrays(left_initial_fields, volumes)
        right_initial_mass = inventory_arrays(right_initial_fields, volumes)
        for name in left_initial_parts:
            left_initial_parts[name].append(float(np.sum(left_initial_mass[name])))
            right_initial_parts[name].append(float(np.sum(right_initial_mass[name])))

    require(total_local_cells == GLOBAL_CELL_COUNT,
            f"Wrong total decomposed cell count: {total_local_cells} != {GLOBAL_CELL_COUNT}")
    require(bool(np.all(coverage == 1)),
            "Decomposition does not cover every Kelvin cell exactly once")
    left_total = inventory_totals(left_parts)
    right_total = inventory_totals(right_parts)
    left_initial = inventory_totals(left_initial_parts)
    right_initial = inventory_totals(right_initial_parts)
    require(left_initial == right_initial, "Initial global inventories differ")

    relative_inventory: dict[str, float] = {}
    absolute_inventory: dict[str, float] = {}
    for name in left_total:
        absolute_inventory[name] = abs(left_total[name] - right_total[name])
        denominator = abs(right_total[name])
        if denominator == 0.0:
            denominator = abs(left_total[name])
        relative_inventory[name] = (
            0.0 if denominator == 0.0 else absolute_inventory[name] / denominator
        )
    relative_l1: dict[str, float] = {}
    absolute_l1: dict[str, float] = {}
    for name in absolute_difference:
        absolute_l1[name] = math.fsum(absolute_difference[name])
        denominator = abs(right_total[name])
        if denominator == 0.0:
            denominator = abs(left_total[name])
        relative_l1[name] = 0.0 if denominator == 0.0 else absolute_l1[name] / denominator

    def relative_field_norm(
        differences: list[float], left_norms: list[float], right_norms: list[float]
    ) -> float:
        numerator = math.fsum(differences)
        denominator = max(math.fsum(left_norms), math.fsum(right_norms))
        return 0.0 if denominator == 0.0 else numerator / denominator

    fieldwise_l1 = {
        name: relative_field_norm(
            field_abs_difference[name], field_left_norm[name], field_right_norm[name]
        )
        for name in ENDPOINT_RESTART_STATE_FIELDS
    }
    boundary_l1 = {
        name: relative_field_norm(
            boundary_abs_difference[name], boundary_left_norm[name], boundary_right_norm[name]
        )
        for name in ENDPOINT_RESTART_STATE_FIELDS
    }

    fronts = {
        label: {name: front_positions(profile) for name, profile in phase.items()}
        for label, phase in profiles.items()
    }
    front_deltas: dict[str, dict[str, object]] = {}
    for phase in (MN_FREE, MN_SORBED):
        left_phase = fronts[left_label][phase]
        right_phase = fronts[right_label][phase]
        require(
            left_phase["defined"] == right_phase["defined"],
            f"{phase} front is defined in only one comparison case",
        )
        phase_deltas: dict[str, object] = {
            "defined": left_phase["defined"], "quantiles": {},
        }
        if not left_phase["defined"]:
            front_deltas[phase] = phase_deltas
            continue
        left_quantiles = left_phase["quantiles"]
        right_quantiles = right_phase["quantiles"]
        require(left_quantiles.keys() == right_quantiles.keys(),
                f"{phase} front quantiles differ between comparison cases")
        quantile_deltas: dict[str, dict[str, object]] = {}
        for key in left_quantiles:
            left_front = left_quantiles[key]
            right_front = right_quantiles[key]
            index_delta = int(left_front["cell_index"]) - int(right_front["cell_index"])
            quantile_deltas[key] = {
                "cell_index_delta": index_delta,
                "position_delta_m": index_delta * CELL_SIZE_M,
            }
        phase_deltas["quantiles"] = quantile_deltas
        front_deltas[phase] = phase_deltas

    changes = {
        left_label: {name: left_total[name] - left_initial[name] for name in left_total},
        right_label: {name: right_total[name] - right_initial[name] for name in right_total},
    }
    return {
        "geometry": {
            "global_cell_count": GLOBAL_CELL_COUNT,
            "domain_dimensions_m": [DOMAIN_LENGTH_M] * 3,
            "minimum_cell_volume_m3": geometry_min,
            "maximum_cell_volume_m3": geometry_max,
            "maximum_absolute_volume_deviation_from_1e-15_m3": max_volume_deviation,
            "reported_species_amounts_use_polyMesh_cell_volumes": True,
            "fronts_use_geometry_validated_x_cell_centres": True,
            "pair_mesh_geometry_identical": True,
        },
        "reported_species_amount_kmol": {
            left_label: {"initial": left_initial, "endpoint": left_total},
            right_label: {"initial": right_initial, "endpoint": right_total},
        },
        "reported_species_amount_change_kmol": changes,
        "relative_endpoint_reported_species_amount_difference": relative_inventory,
        "absolute_endpoint_reported_species_amount_difference_kmol": absolute_inventory,
        "spatial_relative_L1": relative_l1,
        "spatial_absolute_L1_kmol": absolute_l1,
        "complete_state_fieldwise_symmetric_relative_L1": fieldwise_l1,
        "complete_state_fieldwise_maximum_absolute_difference": (
            field_maximum_absolute_difference
        ),
        "complete_state_fieldwise_maximum_absolute_magnitude": (
            field_maximum_absolute_magnitude
        ),
        "complete_state_boundary_symmetric_relative_L1": boundary_l1,
        "complete_state_boundary_maximum_absolute_difference": (
            boundary_maximum_absolute_difference
        ),
        "complete_state_boundary_maximum_absolute_magnitude": (
            boundary_maximum_absolute_magnitude
        ),
        "complete_state_boundary_structure_equal": boundary_structure_equal,
        "front_definition": (
            "x-locations of 10%, 50%, and 90% cumulative free Mn+2 aqueous-species "
            "amount or selected Mn-bearing surface-complex-species amount; a front is "
            "undefined, with no quantiles compared, when the phase amount is exactly zero"
        ),
        "fronts": fronts,
        "front_differences": front_deltas,
        "mass_balance_scope": {
            "reported_species_amount_accounting": True,
            "elemental_inventory_evaluated": False,
            "boundary_flux_closure_evaluated": False,
            "reason": (
                "GeoChemFoam records individual aqueous species, not PHREEQC elemental "
                "components. Mn chloride/hydroxide complexes and chloride bound in those "
                "complexes are not persisted Kelvin fields. Reported amounts therefore "
                "cover free Mn+2, free Mg+2, free Cl-, and the named Mn/Mg surface "
                "complexes only. Schema-9 also lacks solver-consistent time-resolved "
                "species boundary fluxes, so these are neither complete elemental "
                "inventories nor conservation residuals."
            ),
        },
    }


def evaluate_convergence(metrics: dict[str, Any]) -> dict[str, object]:
    inventory = metrics["relative_endpoint_reported_species_amount_difference"]
    l1 = metrics["spatial_relative_L1"]
    deltas = metrics["front_differences"]
    inventory_values = {name: inventory[name] for name in (MN_FREE, MN_SORBED, MN_REPORTED)}
    l1_values = {name: l1[name] for name in (MN_FREE, MN_SORBED)}
    front_cells = front_cell_shifts(deltas)
    maximum_cells = max(front_cells) if front_cells else None
    return {
        "tolerances": {
            "Mn_reported_species_amount_relative": {
                "operator": "<", "value": CONVERGENCE_RELATIVE_TOLERANCE
            },
            "Mn_spatial_relative_L1": {"operator": "<", "value": CONVERGENCE_RELATIVE_TOLERANCE},
            "front_absolute_cell_shift": {"operator": "<=", "value": 1},
            "front_relative_domain_shift": {"operator": "<", "value": 0.01},
        },
        "evaluated": {
            "Mn_reported_species_amount_relative": inventory_values,
            "Mn_spatial_relative_L1": l1_values,
            "maximum_front_cell_shift": maximum_cells,
            "maximum_front_relative_domain_shift": (
                None if maximum_cells is None else maximum_cells / NX
            ),
        },
        "checks": {
            "Mn_reported_species_amounts_below_1pct": all(
                value < CONVERGENCE_RELATIVE_TOLERANCE for value in inventory_values.values()
            ),
            "Mn_spatial_L1_below_1pct": all(
                value < CONVERGENCE_RELATIVE_TOLERANCE for value in l1_values.values()
            ),
            "fronts_within_one_cell": maximum_cells is None or maximum_cells <= 1,
            "fronts_below_1pct_domain": (
                maximum_cells is None or maximum_cells / NX < 0.01
            ),
        },
    }


def evaluate_restart(metrics: dict[str, Any]) -> dict[str, object]:
    inventory = metrics["relative_endpoint_reported_species_amount_difference"]
    l1 = metrics["spatial_relative_L1"]
    deltas = metrics["front_differences"]
    inventory_values = {
        name: inventory[name]
        for name in (MN_FREE, MN_SORBED, MN_REPORTED, MG_FREE,
                     MG_SORBED, MG_REPORTED, CL_FREE)
    }
    l1_values = {name: l1[name] for name in l1}
    state_l1 = metrics["complete_state_fieldwise_symmetric_relative_L1"]
    boundary_l1 = metrics["complete_state_boundary_symmetric_relative_L1"]
    boundary_structure = metrics["complete_state_boundary_structure_equal"]
    absolute_inventory = metrics["absolute_endpoint_reported_species_amount_difference_kmol"]
    absolute_spatial = metrics["spatial_absolute_L1_kmol"]
    field_absolute = metrics["complete_state_fieldwise_maximum_absolute_difference"]
    field_scale = metrics["complete_state_fieldwise_maximum_absolute_magnitude"]
    boundary_absolute = metrics["complete_state_boundary_maximum_absolute_difference"]
    boundary_scale = metrics["complete_state_boundary_maximum_absolute_magnitude"]
    front_cells = front_cell_shifts(deltas)
    return {
        "tolerances": {
            "reported_species_amount_combined": {
                "operator": "<= absolute + relative*scale",
                "absolute": RESTART_AMOUNT_ABSOLUTE_TOLERANCE_KMOL,
                "relative": RESTART_RELATIVE_TOLERANCE,
            },
            "spatial_L1_combined": {
                "operator": "<= absolute + relative*scale",
                "absolute": RESTART_AMOUNT_ABSOLUTE_TOLERANCE_KMOL,
                "relative": RESTART_RELATIVE_TOLERANCE,
            },
            "complete_state_fieldwise_combined": {
                "operator": "maximum_abs_difference <= absolute + relative*maximum_abs_magnitude",
                "absolute": RESTART_FIELD_ABSOLUTE_TOLERANCE,
                "relative": RESTART_RELATIVE_TOLERANCE,
            },
            "complete_state_boundary_combined": {
                "operator": "maximum_abs_difference <= absolute + relative*maximum_abs_magnitude",
                "absolute": RESTART_FIELD_ABSOLUTE_TOLERANCE,
                "relative": RESTART_RELATIVE_TOLERANCE,
            },
            "boundary_structure_equal": {"operator": "==", "value": True},
            "front_cell_index_shift": {"operator": "==", "value": 0},
        },
        "evaluated": {
            "reported_species_amount_relative": inventory_values,
            "spatial_relative_L1": l1_values,
            "complete_state_fieldwise_relative_L1": state_l1,
            "complete_state_boundary_relative_L1": boundary_l1,
            "boundary_structure_equal": boundary_structure,
            "reported_species_amount_absolute_kmol": absolute_inventory,
            "spatial_absolute_L1_kmol": absolute_spatial,
            "complete_state_fieldwise_maximum_absolute_difference": field_absolute,
            "complete_state_fieldwise_maximum_absolute_magnitude": field_scale,
            "complete_state_boundary_maximum_absolute_difference": boundary_absolute,
            "complete_state_boundary_maximum_absolute_magnitude": boundary_scale,
            "maximum_front_cell_shift": max(front_cells) if front_cells else None,
        },
        "checks": {
            "reported_species_amounts_within_combined_tolerance": all(
                absolute_inventory[name]
                <= RESTART_AMOUNT_ABSOLUTE_TOLERANCE_KMOL
                + RESTART_RELATIVE_TOLERANCE * max(
                    abs(metrics["reported_species_amount_kmol"][label]["endpoint"][name])
                    for label in ("uninterrupted", "restarted")
                )
                for name in inventory_values
            ),
            "spatial_L1_within_combined_tolerance": all(
                absolute_spatial[name]
                <= RESTART_AMOUNT_ABSOLUTE_TOLERANCE_KMOL
                + RESTART_RELATIVE_TOLERANCE
                * max(
                    abs(metrics["reported_species_amount_kmol"][label]["endpoint"][name])
                    for label in ("uninterrupted", "restarted")
                )
                for name in l1_values
            ),
            "complete_state_fields_within_combined_tolerance": all(
                field_absolute[name]
                <= RESTART_FIELD_ABSOLUTE_TOLERANCE
                + RESTART_RELATIVE_TOLERANCE * field_scale[name]
                for name in state_l1
            ),
            "complete_state_boundaries_within_combined_tolerance": all(
                boundary_absolute[name]
                <= RESTART_FIELD_ABSOLUTE_TOLERANCE
                + RESTART_RELATIVE_TOLERANCE * boundary_scale[name]
                for name in boundary_l1
            ),
            "boundary_structures_identical": all(boundary_structure.values()),
            "front_indices_identical": not front_cells or max(front_cells) == 0,
        },
    }


def validate_case(case: Path, expected_endpoint: float) -> tuple[dict[str, Any], dict[str, Any]]:
    require(case.is_dir() and not case.is_symlink(), f"Missing regular case directory: {case}")
    case = case.resolve()
    manifest_path = case / "run_provenance.json"
    payload = load_json(manifest_path)
    verify_manifest_identity(payload, case)
    ranks = call_provenance(provenance.exact_ranks, case, RANK_COUNT)
    completed, attempts, chain = verify_stage_chain(payload, case, ranks, expected_endpoint)
    retained_times = sorted(
        {0.0}
        | {float(stage["startTime"]) for stage in completed}
        | {float(stage["endTime"]) for stage in completed}
    )
    scans = [scan_timepoint(case, ranks, value) for value in retained_times]
    static = verify_static_timepoints(ranks, retained_times)
    endpoint_scan = next(scan for scan in scans if scan["time_s"] == expected_endpoint)
    return payload, {
        "case": str(case),
        "run_manifest": file_record(manifest_path),
        "schema_version": payload["schema_version"],
        "delta_t_s": float(completed[0]["deltaT"]),
        "rank_count": RANK_COUNT,
        "decomposition": DECOMPOSITION,
        "stage_chain": chain,
        "superseded_attempts": attempts,
        "retained_time_scans": scans,
        "static_field_contract": static,
        "endpoint": endpoint_scan,
        "pass": True,
    }


def compare_convergence(coarse_case: Path, fine_case: Path) -> dict[str, object]:
    require(coarse_case.resolve() != fine_case.resolve(), "Coarse and fine cases must differ")
    coarse_manifest, coarse_integrity = validate_case(coarse_case, END_TIME_S)
    fine_manifest, fine_integrity = validate_case(fine_case, END_TIME_S)
    coarse_case = coarse_case.resolve()
    fine_case = fine_case.resolve()
    exact_number(coarse_integrity["delta_t_s"], COARSE_DT_S, "coarse deltaT")
    exact_number(fine_integrity["delta_t_s"], FINE_DT_S, "fine deltaT")
    exact_number(
        float(coarse_integrity["delta_t_s"]) / float(fine_integrity["delta_t_s"]),
        2.0,
        "timestep refinement ratio",
        1e-12,
    )
    required_schedule = [(0.0, END_TIME_S, False)]
    for label, integrity in (("coarse", coarse_integrity), ("fine", fine_integrity)):
        schedule = [
            (record["start_time_s"], record["end_time_s"], record["restore"])
            for record in integrity["stage_chain"]["completed_schedule"]
        ]
        require(schedule == required_schedule,
                f"{label} convergence case is not one uninterrupted 0-to-0.5 stage")
    identity = verify_pair_identity(coarse_manifest, fine_manifest, coarse_case, fine_case)
    metrics = scientific_metrics(
        coarse_case, fine_case, END_TIME_S, END_TIME_S, "coarse", "fine"
    )
    gate = evaluate_convergence(metrics)
    gate["pass"] = all(gate["checks"].values())
    return {
        "schema_version": SCHEMA_VERSION,
        "comparison": "3d_kelvin_temporal_convergence",
        "required_pair": {
            "coarse_delta_t_s": COARSE_DT_S, "fine_delta_t_s": FINE_DT_S,
            "refinement_ratio": 2.0, "endpoint_s": END_TIME_S,
        },
        "sources": {
            "comparator": file_record(SCRIPT),
            "comparator_tests": file_record(TEST_SCRIPT),
            "coarse_case": coarse_integrity,
            "fine_case": fine_integrity,
        },
        "pair_identity": identity,
        "metrics": metrics,
        "acceptance": gate,
        "pass": gate["pass"],
    }


def validate_convergence_acceptance(path: Path) -> tuple[dict[str, Any], dict[str, object]]:
    artifact = load_json(path)
    require(artifact.get("schema_version") == SCHEMA_VERSION,
            "Accepted convergence artifact has the wrong schema")
    require(artifact.get("comparison") == "3d_kelvin_temporal_convergence",
            "Accepted convergence artifact has the wrong comparison type")
    require(artifact.get("pass") is True, "Temporal convergence was not accepted")
    sources = artifact.get("sources")
    require(isinstance(sources, dict), "Accepted convergence artifact has no sources")
    for key, expected in (("comparator", SCRIPT), ("comparator_tests", TEST_SCRIPT)):
        record = sources.get(key)
        require(isinstance(record, dict), f"Accepted convergence artifact lacks {key}")
        require(record.get("sha256") == sha256(expected),
                f"Accepted convergence artifact used a different {key}")
    case_paths: list[Path] = []
    for key in ("coarse_case", "fine_case"):
        case_source = sources.get(key)
        require(isinstance(case_source, dict),
                f"Accepted convergence artifact lacks {key}")
        case_path = Path(str(case_source.get("case", "")))
        require(case_path.is_absolute(), f"Accepted convergence {key} path is not absolute")
        case_paths.append(case_path)
    rehydrated = compare_convergence(case_paths[0], case_paths[1])
    require(
        rehydrated == artifact,
        "Accepted convergence artifact differs from a fresh authenticated recomputation",
    )
    require(rehydrated.get("pass") is True, "Temporal convergence was not accepted")
    return artifact, file_record(path)


def compare_restart(
    uninterrupted_case: Path, restarted_case: Path, endpoint: float,
    convergence_result: Path,
) -> dict[str, object]:
    exact_number(endpoint, RESTART_ENDPOINT_S, "required restart endpoint", 1e-15)
    convergence_artifact, convergence_record = validate_convergence_acceptance(
        convergence_result
    )
    require(
        uninterrupted_case.resolve() != restarted_case.resolve(),
        "Restart comparison cases must differ",
    )
    uninterrupted_manifest, uninterrupted_integrity = validate_case(
        uninterrupted_case, endpoint
    )
    restarted_manifest, restarted_integrity = validate_case(restarted_case, endpoint)
    uninterrupted_case = uninterrupted_case.resolve()
    restarted_case = restarted_case.resolve()
    exact_number(
        restarted_integrity["delta_t_s"], float(uninterrupted_integrity["delta_t_s"]),
        "restart pair deltaT",
    )
    exact_number(uninterrupted_integrity["delta_t_s"], ACCEPTED_DT_S,
                 "accepted restart deltaT")
    uninterrupted_schedule = uninterrupted_integrity["stage_chain"]["completed_schedule"]
    restarted_schedule = restarted_integrity["stage_chain"]["completed_schedule"]
    uninterrupted_tuple = [
        (record["start_time_s"], record["end_time_s"], record["restore"])
        for record in uninterrupted_schedule
    ]
    restarted_tuple = [
        (record["start_time_s"], record["end_time_s"], record["restore"])
        for record in restarted_schedule
    ]
    require(
        uninterrupted_tuple == [(0.0, RESTART_ENDPOINT_S, False)],
        "Uninterrupted reference is not the required 0-to-0.025 stage",
    )
    require(
        restarted_tuple == [
            (0.0, RESTART_SPLIT_S, False),
            (RESTART_SPLIT_S, RESTART_ENDPOINT_S, True),
        ],
        "Restarted case is not the required 0-to-0.0125-to-0.025 chain",
    )
    identity = verify_pair_identity(
        uninterrupted_manifest, restarted_manifest, uninterrupted_case, restarted_case
    )
    require(
        identity == convergence_artifact.get("pair_identity"),
        "Restart pair identity differs from the accepted convergence pair identity",
    )
    metrics = scientific_metrics(
        uninterrupted_case, restarted_case, endpoint, endpoint,
        "uninterrupted", "restarted",
    )
    gate = evaluate_restart(metrics)
    gate["pass"] = all(gate["checks"].values())
    return {
        "schema_version": SCHEMA_VERSION,
        "comparison": "3d_kelvin_restart_equivalence",
        "required_pair": {
            "delta_t_s": uninterrupted_integrity["delta_t_s"],
            "endpoint_s": endpoint,
            "uninterrupted_stage_count": 1,
            "restart_split_s": RESTART_SPLIT_S,
            "restarted_stage_count": 2,
        },
        "sources": {
            "comparator": file_record(SCRIPT),
            "comparator_tests": file_record(TEST_SCRIPT),
            "accepted_convergence_result": convergence_record,
            "uninterrupted_case": uninterrupted_integrity,
            "restarted_case": restarted_integrity,
        },
        "pair_identity": identity,
        "checkpoint_authentication": {
            "uninterrupted_case_all_recorded_pairs_authenticated": (
                uninterrupted_integrity["stage_chain"]["all_checkpoint_pairs_valid"]
            ),
            "restarted_case_all_recorded_pairs_authenticated": (
                restarted_integrity["stage_chain"]["all_checkpoint_pairs_valid"]
            ),
            "cross_run_dump_or_marker_byte_identity_required": False,
            "cross_run_acceptance_basis": "numerical field and reported-species equivalence",
        },
        "metrics": metrics,
        "acceptance": gate,
        "pass": gate["pass"],
    }


def write_result(path: Path, result: dict[str, object]) -> None:
    require(not path.exists(), f"Refusing to overwrite comparison artifact: {path}")
    require(path.parent.is_dir(), f"Output parent does not exist: {path.parent}")
    temporary = path.with_name(path.name + f".tmp.{os.getpid()}")
    require(not temporary.exists(), f"Temporary output already exists: {temporary}")
    try:
        temporary.write_text(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description=__doc__)
    subparsers = result.add_subparsers(dest="command", required=True)
    convergence = subparsers.add_parser("convergence")
    convergence.add_argument("--coarse-case", type=Path, required=True)
    convergence.add_argument("--fine-case", type=Path, required=True)
    convergence.add_argument("--output", type=Path, required=True)
    restart = subparsers.add_parser("restart")
    restart.add_argument("--uninterrupted-case", type=Path, required=True)
    restart.add_argument("--restarted-case", type=Path, required=True)
    restart.add_argument("--endpoint", type=float, required=True)
    restart.add_argument("--convergence-result", type=Path, required=True)
    restart.add_argument("--output", type=Path, required=True)
    return result


def main(argv: list[str] | None = None) -> None:
    args = parser().parse_args(argv)
    try:
        if args.command == "convergence":
            result = compare_convergence(args.coarse_case, args.fine_case)
        else:
            result = compare_restart(
                args.uninterrupted_case, args.restarted_case, args.endpoint,
                args.convergence_result,
            )
        write_result(args.output, result)
    except ComparisonError as error:
        raise SystemExit(f"Kelvin comparison refused: {error}") from error
    print(f"Wrote {args.output}; pass={result['pass']}")
    if result["pass"] is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
