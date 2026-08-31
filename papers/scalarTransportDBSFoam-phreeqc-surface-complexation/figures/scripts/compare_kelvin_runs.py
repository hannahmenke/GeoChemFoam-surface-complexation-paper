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

from openfoam_field_io import read_internal_scalar


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
NEGATIVE_TOLERANCE = -1.0e-12
CONVERGENCE_RELATIVE_TOLERANCE = 0.01
RESTART_RELATIVE_TOLERANCE = 1.0e-10
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


def verify_absolute_record(record: object, label: str, expected: Path | None = None) -> Path:
    require(isinstance(record, dict), f"Malformed {label} record")
    path = Path(str(record.get("path", "")))
    require(path.is_absolute(), f"{label} path is not absolute: {path}")
    require(path.is_file() and not path.is_symlink(), f"Missing regular {label}: {path}")
    if expected is not None:
        require(path == expected.resolve(), f"Wrong {label} path: {path} != {expected.resolve()}")
    digest = str(record.get("sha256", ""))
    require(re.fullmatch(r"[0-9a-f]{64}", digest) is not None, f"Invalid {label} hash")
    require(sha256(path) == digest, f"{label} hash mismatch: {path}")
    return path


def list_payload(path: Path) -> tuple[int, bytes]:
    require(path.is_file() and not path.is_symlink(), f"Missing mesh list: {path}")
    data = path.read_bytes()
    require(re.search(rb"\bformat\s+ascii\s*;", data) is not None,
            f"Only ASCII mesh lists are supported: {path}")
    header = re.search(
        rb"\n[ \t]*(\d+)[ \t]*\r?\n[ \t]*\([ \t]*\r?\n", data
    )
    require(header is not None, f"Cannot locate list payload: {path}")
    stop = data.rfind(b"\n)")
    require(stop >= header.end(), f"Unterminated list payload: {path}")
    return int(header.group(1)), data[header.end():stop]


def read_label_list(path: Path) -> np.ndarray:
    count, payload = list_payload(path)
    values = np.fromstring(payload.decode("ascii"), dtype=np.int64, sep=" ")
    require(values.size == count, f"Label count mismatch in {path}: {values.size} != {count}")
    return values


def read_points(path: Path) -> np.ndarray:
    count, payload = list_payload(path)
    values = np.fromstring(
        payload.replace(b"(", b" ").replace(b")", b" ").decode("ascii"), sep=" "
    )
    require(values.size == 3 * count, f"Point count mismatch in {path}")
    result = values.reshape(count, 3)
    require(bool(np.all(np.isfinite(result))), f"Non-finite mesh point in {path}")
    return result


def read_quad_faces(path: Path) -> np.ndarray:
    count, payload = list_payload(path)
    values = np.fromstring(
        re.sub(rb"\s*4\s*\(", b" ", payload).replace(b")", b" ").decode("ascii"),
        dtype=np.int64,
        sep=" ",
    )
    require(values.size == 4 * count,
            f"Kelvin mesh must contain only quadrilateral faces: {path}")
    return values.reshape(count, 4)


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

    vertices = points[faces]
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
    centres = moments / volumes[:, None]
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
    return {"addressing": addressing, "volumes": volumes, "centres": centres, "x_index": i}


def scalar_values(path: Path, expected_size: int | None = None) -> np.ndarray:
    require(path.is_file() and not path.is_symlink(), f"Missing regular field: {path}")
    value = read_internal_scalar(path)
    if np.isscalar(value):
        require(expected_size is not None, f"Cannot expand uniform field without size: {path}")
        values = np.full(expected_size, float(value), dtype=np.float64)
    else:
        values = np.asarray(value, dtype=np.float64)
    if expected_size is not None:
        require(values.size == expected_size,
                f"Field count mismatch in {path}: {values.size} != {expected_size}")
    require(values.size > 0 and bool(np.all(np.isfinite(values))), f"Invalid field: {path}")
    return values


def vector_values(path: Path, expected_size: int) -> np.ndarray:
    require(path.is_file() and not path.is_symlink(), f"Missing regular field: {path}")
    data = path.read_bytes()
    require(re.search(rb"\bformat\s+ascii\s*;", data) is not None,
            f"Only ASCII vector fields are supported: {path}")
    uniform = re.search(rb"internalField\s+uniform\s+\(([^)]*)\)\s*;", data)
    if uniform:
        vector = np.fromstring(uniform.group(1).decode("ascii"), sep=" ")
        require(vector.size == 3, f"Invalid uniform vector in {path}")
        values = np.tile(vector, (expected_size, 1))
    else:
        match = re.search(
            rb"internalField\s+nonuniform\s+List<vector>\s+(\d+)\s*\((.*?)\)\s*;",
            data,
            re.DOTALL,
        )
        require(match is not None, f"Unsupported vector field: {path}")
        count = int(match.group(1))
        payload = match.group(2).replace(b"(", b" ").replace(b")", b" ")
        flat = np.fromstring(payload.decode("ascii"), sep=" ")
        require(count == expected_size and flat.size == 3 * count,
                f"Vector count mismatch in {path}")
        values = flat.reshape(count, 3)
    require(bool(np.all(np.isfinite(values))), f"Non-finite vector field: {path}")
    return values


def update_statistics(target: dict[str, dict[str, object]], name: str, values: np.ndarray) -> None:
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
    record["minimum"] = min(float(record["minimum"]), minimum)
    record["maximum"] = max(float(record["maximum"]), maximum)
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


def verify_surface_record(record: object, label: str) -> None:
    path = verify_absolute_record(record, label)
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
    for index, record in enumerate(chemistry_files):
        verify_absolute_record(record, f"chemistry/input record {index}")
    call_provenance(provenance.verify_file_records, chemistry_files)
    verify_surface_record(payload.get("surface"), "surface-construction log")
    verify_surface_record(payload.get("intrinsic_surface"), "intrinsic-surface log")
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
        log = verify_absolute_record(stage.get("solver_log"), f"{stage_id} solver log")
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
    }


def scan_endpoint(
    case: Path, ranks: list[Path], endpoint: float
) -> dict[str, object]:
    statistics: dict[str, dict[str, object]] = {}
    local_counts: list[int] = []
    for rank in ranks:
        addressing = read_label_list(rank / "constant/polyMesh/cellProcAddressing")
        local_counts.append(int(addressing.size))
        directory = exact_time_directory(rank, endpoint)
        for name in CELL_SCALARS:
            values = scalar_values(directory / name, addressing.size)
            update_statistics(statistics, name, values)
        update_statistics(statistics, "U", vector_values(directory / "U", addressing.size))
        update_statistics(statistics, "phi", scalar_values(directory / "phi"))
    return {
        "endpoint_time_s": endpoint,
        "local_cell_counts": local_counts,
        "field_statistics": statistics,
        "negative_tolerance": NEGATIVE_TOLERANCE,
        "all_internal_field_values_finite": True,
        "all_analytically_nonnegative_internal_fields_within_tolerance": True,
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
    left_inputs = normalized_input_records(left, left_case)
    right_inputs = normalized_input_records(right, right_case)
    require(left_inputs == right_inputs, "Chemistry, geometry, or case inputs differ")
    left_initial = left["initial_case"]
    right_initial = right["initial_case"]
    require(left_initial == right_initial, "Initial decomposed fields or mesh differ")
    require(left["surface"] | {"path": None} == right["surface"] | {"path": None},
            "Surface-construction evidence differs")
    require(
        left["intrinsic_surface"] | {"path": None}
        == right["intrinsic_surface"] | {"path": None},
        "Intrinsic-surface evidence differs",
    )
    return {
        **identity,
        "initial_case_sha256": left_initial["sha256"],
        "chemistry_and_case_inputs": left_inputs,
        "same_exact_runtime": True,
        "same_initial_decomposed_mesh_and_fields": True,
        "same_chemistry_geometry_and_case_inputs": True,
    }


def inventory_arrays(fields: dict[str, np.ndarray], volumes: np.ndarray) -> dict[str, np.ndarray]:
    aqueous_weight = fields["eps"] * volumes
    surface_weight = fields["aSurf"] * volumes
    return {
        "Mn_aqueous": fields["Mn+2"] * aqueous_weight,
        "Mn_sorbed": (fields["Surf_sOMn+"] + fields["Surf_wOMn+"]) * surface_weight,
        "Mg_aqueous": fields["Mg+2"] * aqueous_weight,
        "Mg_sorbed": fields["Surf_wOMg+"] * surface_weight,
        "Cl_aqueous": fields["Cl-"] * aqueous_weight,
    }


def load_mass_fields(directory: Path, count: int) -> dict[str, np.ndarray]:
    return {name: scalar_values(directory / name, count) for name in MASS_FIELDS}


def empty_inventory() -> dict[str, list[float]]:
    return {name: [] for name in (
        "Mn_aqueous", "Mn_sorbed", "Mg_aqueous", "Mg_sorbed", "Cl_aqueous"
    )}


def inventory_totals(parts: dict[str, list[float]]) -> dict[str, float]:
    result = {name: math.fsum(values) for name, values in parts.items()}
    result["Mn_total"] = result["Mn_aqueous"] + result["Mn_sorbed"]
    result["Mg_total"] = result["Mg_aqueous"] + result["Mg_sorbed"]
    result["Cl_total"] = result["Cl_aqueous"]
    return result


def front_positions(profile: np.ndarray) -> dict[str, dict[str, object]]:
    total = float(np.sum(profile, dtype=np.float64))
    require(total > 0.0 and math.isfinite(total), "Cannot locate a front in an empty profile")
    cumulative = np.cumsum(profile, dtype=np.float64)
    require(bool(np.all(np.diff(cumulative) >= 0.0)),
            "Inventory profile is not monotone; front location would require clipping")
    result: dict[str, dict[str, object]] = {}
    for quantile in FRONT_QUANTILES:
        index = int(np.searchsorted(cumulative, quantile * total, side="left"))
        require(0 <= index < NX, "Front index is outside the Kelvin domain")
        result[f"x{int(100 * quantile)}"] = {
            "cell_index": index,
            "position_m": (index + 0.5) * CELL_SIZE_M,
        }
    return result


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
        left_label: {"Mn_aqueous": np.zeros(NX), "Mn_sorbed": np.zeros(NX)},
        right_label: {"Mn_aqueous": np.zeros(NX), "Mn_sorbed": np.zeros(NX)},
    }
    coverage = np.zeros(GLOBAL_CELL_COUNT, dtype=np.bool_)
    geometry_min = math.inf
    geometry_max = -math.inf
    max_volume_deviation = 0.0

    for rank_number in range(RANK_COUNT):
        left_rank = left_case / f"processor{rank_number}"
        right_rank = right_case / f"processor{rank_number}"
        left_geometry = mesh_geometry(left_rank)
        right_geometry = mesh_geometry(right_rank)
        for name in ("addressing", "volumes", "centres"):
            require(np.array_equal(left_geometry[name], right_geometry[name]),
                    f"Pair mesh geometry differs on processor{rank_number}: {name}")
        addressing = left_geometry["addressing"]
        require(not bool(np.any(coverage[addressing])),
                f"Duplicate global cells on processor{rank_number}")
        coverage[addressing] = True
        volumes = left_geometry["volumes"]
        geometry_min = min(geometry_min, float(np.min(volumes)))
        geometry_max = max(geometry_max, float(np.max(volumes)))
        max_volume_deviation = max(
            max_volume_deviation, float(np.max(np.abs(volumes - CELL_VOLUME_M3)))
        )
        count = addressing.size
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
            for name in ("Mn_aqueous", "Mn_sorbed"):
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

    require(bool(np.all(coverage)), "Decomposition does not cover every Kelvin cell exactly once")
    left_total = inventory_totals(left_parts)
    right_total = inventory_totals(right_parts)
    left_initial = inventory_totals(left_initial_parts)
    right_initial = inventory_totals(right_initial_parts)
    require(left_initial == right_initial, "Initial global inventories differ")

    relative_inventory: dict[str, float] = {}
    for name in left_total:
        denominator = abs(right_total[name])
        require(denominator > 0.0, f"Zero reference inventory for {name}")
        relative_inventory[name] = abs(left_total[name] - right_total[name]) / denominator
    relative_l1: dict[str, float] = {}
    for name in absolute_difference:
        denominator = abs(right_total[name])
        require(denominator > 0.0, f"Zero spatial-L1 denominator for {name}")
        relative_l1[name] = math.fsum(absolute_difference[name]) / denominator

    fronts = {
        label: {name: front_positions(profile) for name, profile in phase.items()}
        for label, phase in profiles.items()
    }
    front_deltas: dict[str, dict[str, object]] = {}
    for phase in ("Mn_aqueous", "Mn_sorbed"):
        front_deltas[phase] = {}
        for key in fronts[left_label][phase]:
            left_front = fronts[left_label][phase][key]
            right_front = fronts[right_label][phase][key]
            index_delta = int(left_front["cell_index"]) - int(right_front["cell_index"])
            front_deltas[phase][key] = {
                "cell_index_delta": index_delta,
                "position_delta_m": index_delta * CELL_SIZE_M,
            }

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
            "inventories_use_polyMesh_cell_volumes": True,
            "fronts_use_geometry_validated_x_cell_centres": True,
            "pair_mesh_geometry_identical": True,
        },
        "inventory_kmol": {
            left_label: {"initial": left_initial, "endpoint": left_total},
            right_label: {"initial": right_initial, "endpoint": right_total},
        },
        "inventory_change_kmol": changes,
        "relative_endpoint_inventory_difference": relative_inventory,
        "spatial_relative_L1": relative_l1,
        "front_definition": "x-locations of 10%, 50%, and 90% cumulative Mn inventory",
        "fronts": fronts,
        "front_differences": front_deltas,
        "mass_balance_scope": {
            "inventory_accounting": True,
            "boundary_flux_closure_evaluated": False,
            "reason": (
                "Schema-9 Kelvin runs do not record solver-consistent time-resolved "
                "advective and diffusive species boundary fluxes. Inventory agreement is "
                "reported, but is not mislabeled as a conservation residual."
            ),
        },
    }


def evaluate_convergence(metrics: dict[str, Any]) -> dict[str, object]:
    inventory = metrics["relative_endpoint_inventory_difference"]
    l1 = metrics["spatial_relative_L1"]
    deltas = metrics["front_differences"]
    inventory_values = {name: inventory[name] for name in ("Mn_aqueous", "Mn_sorbed", "Mn_total")}
    l1_values = {name: l1[name] for name in ("Mn_aqueous", "Mn_sorbed")}
    front_cells = [
        abs(int(record["cell_index_delta"]))
        for phase in deltas.values() for record in phase.values()
    ]
    maximum_cells = max(front_cells)
    return {
        "tolerances": {
            "Mn_inventory_relative": {"operator": "<", "value": CONVERGENCE_RELATIVE_TOLERANCE},
            "Mn_spatial_relative_L1": {"operator": "<", "value": CONVERGENCE_RELATIVE_TOLERANCE},
            "front_absolute_cell_shift": {"operator": "<=", "value": 1},
            "front_relative_domain_shift": {"operator": "<", "value": 0.01},
        },
        "evaluated": {
            "Mn_inventory_relative": inventory_values,
            "Mn_spatial_relative_L1": l1_values,
            "maximum_front_cell_shift": maximum_cells,
            "maximum_front_relative_domain_shift": maximum_cells / NX,
        },
        "checks": {
            "Mn_inventories_below_1pct": all(
                value < CONVERGENCE_RELATIVE_TOLERANCE for value in inventory_values.values()
            ),
            "Mn_spatial_L1_below_1pct": all(
                value < CONVERGENCE_RELATIVE_TOLERANCE for value in l1_values.values()
            ),
            "fronts_within_one_cell": maximum_cells <= 1,
            "fronts_below_1pct_domain": maximum_cells / NX < 0.01,
        },
    }


def evaluate_restart(metrics: dict[str, Any]) -> dict[str, object]:
    inventory = metrics["relative_endpoint_inventory_difference"]
    l1 = metrics["spatial_relative_L1"]
    deltas = metrics["front_differences"]
    inventory_values = {
        name: inventory[name]
        for name in ("Mn_aqueous", "Mn_sorbed", "Mn_total", "Mg_aqueous",
                     "Mg_sorbed", "Mg_total", "Cl_total")
    }
    l1_values = {name: l1[name] for name in l1}
    front_cells = [
        abs(int(record["cell_index_delta"]))
        for phase in deltas.values() for record in phase.values()
    ]
    return {
        "tolerances": {
            "inventory_relative": {"operator": "<=", "value": RESTART_RELATIVE_TOLERANCE},
            "spatial_relative_L1": {"operator": "<=", "value": RESTART_RELATIVE_TOLERANCE},
            "front_cell_index_shift": {"operator": "==", "value": 0},
        },
        "evaluated": {
            "inventory_relative": inventory_values,
            "spatial_relative_L1": l1_values,
            "maximum_front_cell_shift": max(front_cells),
        },
        "checks": {
            "inventories_within_1e-10": all(
                value <= RESTART_RELATIVE_TOLERANCE for value in inventory_values.values()
            ),
            "spatial_L1_within_1e-10": all(
                value <= RESTART_RELATIVE_TOLERANCE for value in l1_values.values()
            ),
            "front_indices_identical": max(front_cells) == 0,
        },
    }


def validate_case(case: Path, expected_endpoint: float) -> tuple[dict[str, Any], dict[str, Any]]:
    case = case.resolve()
    require(case.is_dir() and not case.is_symlink(), f"Missing regular case directory: {case}")
    manifest_path = case / "run_provenance.json"
    payload = load_json(manifest_path)
    verify_manifest_identity(payload, case)
    ranks = call_provenance(provenance.exact_ranks, case, RANK_COUNT)
    completed, attempts, chain = verify_stage_chain(payload, case, ranks, expected_endpoint)
    endpoint_scan = scan_endpoint(case, ranks, expected_endpoint)
    return payload, {
        "case": str(case),
        "run_manifest": file_record(manifest_path),
        "schema_version": payload["schema_version"],
        "delta_t_s": float(completed[0]["deltaT"]),
        "rank_count": RANK_COUNT,
        "decomposition": DECOMPOSITION,
        "stage_chain": chain,
        "superseded_attempts": attempts,
        "endpoint": endpoint_scan,
        "pass": True,
    }


def compare_convergence(coarse_case: Path, fine_case: Path) -> dict[str, object]:
    coarse_case = coarse_case.resolve()
    fine_case = fine_case.resolve()
    require(coarse_case != fine_case, "Coarse and fine cases must differ")
    coarse_manifest, coarse_integrity = validate_case(coarse_case, END_TIME_S)
    fine_manifest, fine_integrity = validate_case(fine_case, END_TIME_S)
    exact_number(coarse_integrity["delta_t_s"], COARSE_DT_S, "coarse deltaT")
    exact_number(fine_integrity["delta_t_s"], FINE_DT_S, "fine deltaT")
    exact_number(
        float(coarse_integrity["delta_t_s"]) / float(fine_integrity["delta_t_s"]),
        2.0,
        "timestep refinement ratio",
        1e-12,
    )
    require(
        [
            (record["start_time_s"], record["end_time_s"], record["restore"])
            for record in coarse_integrity["stage_chain"]["completed_schedule"]
        ]
        == [
            (record["start_time_s"], record["end_time_s"], record["restore"])
            for record in fine_integrity["stage_chain"]["completed_schedule"]
        ],
        "Temporal-convergence cases used different restart schedules",
    )
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


def compare_restart(
    uninterrupted_case: Path, restarted_case: Path, endpoint: float
) -> dict[str, object]:
    require(math.isfinite(endpoint) and endpoint > 0.0, "Restart endpoint must be positive")
    uninterrupted_case = uninterrupted_case.resolve()
    restarted_case = restarted_case.resolve()
    require(uninterrupted_case != restarted_case, "Restart comparison cases must differ")
    uninterrupted_manifest, uninterrupted_integrity = validate_case(
        uninterrupted_case, endpoint
    )
    restarted_manifest, restarted_integrity = validate_case(restarted_case, endpoint)
    exact_number(
        restarted_integrity["delta_t_s"], float(uninterrupted_integrity["delta_t_s"]),
        "restart pair deltaT",
    )
    uninterrupted_schedule = uninterrupted_integrity["stage_chain"]["completed_schedule"]
    restarted_schedule = restarted_integrity["stage_chain"]["completed_schedule"]
    require(len(uninterrupted_schedule) == 1
            and uninterrupted_schedule[0]["start_time_s"] == 0.0
            and math.isclose(float(uninterrupted_schedule[0]["end_time_s"]), endpoint,
                             rel_tol=0.0, abs_tol=1e-12),
            "Uninterrupted reference is not one completed 0-to-endpoint stage")
    require(len(restarted_schedule) >= 2 and restarted_schedule[1]["restore"] is True,
            "Restarted case does not contain a completed checkpoint continuation")
    identity = verify_pair_identity(
        uninterrupted_manifest, restarted_manifest, uninterrupted_case, restarted_case
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
            "restarted_minimum_stage_count": 2,
        },
        "sources": {
            "comparator": file_record(SCRIPT),
            "comparator_tests": file_record(TEST_SCRIPT),
            "uninterrupted_case": uninterrupted_integrity,
            "restarted_case": restarted_integrity,
        },
        "pair_identity": identity,
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
    restart.add_argument("--output", type=Path, required=True)
    return result


def main() -> None:
    args = parser().parse_args()
    try:
        if args.command == "convergence":
            result = compare_convergence(args.coarse_case, args.fine_case)
        else:
            result = compare_restart(
                args.uninterrupted_case, args.restarted_case, args.endpoint
            )
        write_result(args.output, result)
    except ComparisonError as error:
        raise SystemExit(f"Kelvin comparison refused: {error}") from error
    print(f"Wrote {args.output}; pass={result['pass']}")
    if result["pass"] is not True:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
