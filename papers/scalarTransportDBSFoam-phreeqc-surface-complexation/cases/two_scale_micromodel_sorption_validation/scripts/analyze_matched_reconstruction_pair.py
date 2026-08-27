#!/usr/bin/env python3
"""Validate and plot a matched two-scale DBS reconstruction pair."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm

FIGURE_SCRIPTS = Path(__file__).resolve().parents[3] / "figures" / "scripts"
sys.path.insert(0, str(FIGURE_SCRIPTS))
from openfoam_field_io import read_internal_scalar  # noqa: E402


LABELS = ("supported", "legacy-reference")
DYNAMIC_FIELDS = ("Li+", "Surf_aLi")
STATIC_FIELDS = ("eps", "aSurf")
RESPONSE_LIMIT = 0.01
AREA_LIMIT = 0.001
COSINE_LIMIT = 0.995
EXPECTED_CELL_SIZE_M = 5e-6


class ValidationError(RuntimeError):
    """Raised when a pair cannot support the requested comparison."""


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def read_int(path: Path) -> int:
    return int(path.read_text().strip())


def read_field(path: Path, count: int) -> np.ndarray:
    values = read_internal_scalar(path)
    if np.isscalar(values):
        return np.full(count, float(values))
    array = np.asarray(values, dtype=float)
    if array.size != count:
        raise ValidationError(
            f"Field length mismatch in {path}: {array.size}, expected {count}"
        )
    return array


def partition_sizes(size: int, parts: int) -> list[int]:
    base, remainder = divmod(size, parts)
    return [base + (index < remainder) for index in range(parts)]


def geometry(case: Path) -> dict[str, object]:
    nx = read_int(case / "system" / "Nx1")
    ny = read_int(case / "system" / "Ny1")
    npx = read_int(case / "system" / "NPX")
    npy = read_int(case / "system" / "NPY")
    npz = read_int(case / "system" / "NPZ")
    dx = float((case / "system" / "cellSize").read_text().strip())
    if npz != 1:
        raise ValidationError(f"Expected a one-cell-thick 2D case, got NPZ={npz}")
    if not math.isclose(dx, EXPECTED_CELL_SIZE_M, rel_tol=0, abs_tol=1e-12):
        raise ValidationError(f"Expected 5 um cells, got {dx:.17g} m")
    processors = sorted(
        case.glob("processor*"),
        key=lambda path: int(path.name.removeprefix("processor")),
    )
    expected_names = [f"processor{rank}" for rank in range(npx * npy)]
    if [path.name for path in processors] != expected_names:
        raise ValidationError(
            f"Processor layout mismatch in {case}: expected {len(expected_names)} ranks"
        )
    return {
        "nx": nx,
        "ny": ny,
        "npx": npx,
        "npy": npy,
        "partitions": len(processors),
        "cell_size_m": dx,
    }


def assemble(
    case: Path, geom: dict[str, object], time_name: str, field: str
) -> np.ndarray:
    nx, ny = int(geom["nx"]), int(geom["ny"])
    npx, npy = int(geom["npx"]), int(geom["npy"])
    x_sizes, y_sizes = partition_sizes(nx, npx), partition_sizes(ny, npy)
    x_offsets = np.cumsum([0, *x_sizes[:-1]])
    y_offsets = np.cumsum([0, *y_sizes[:-1]])
    output = np.empty((ny, nx), dtype=float)
    for py, y_size in enumerate(y_sizes):
        for px, x_size in enumerate(x_sizes):
            rank = py * npx + px
            path = case / f"processor{rank}" / time_name / field
            if not path.is_file():
                raise ValidationError(f"Missing required field: {path}")
            block = read_field(path, x_size * y_size).reshape(y_size, x_size)
            output[
                y_offsets[py] : y_offsets[py] + y_size,
                x_offsets[px] : x_offsets[px] + x_size,
            ] = block
    if not np.all(np.isfinite(output)):
        raise ValidationError(f"Non-finite values in {case}/{time_name}/{field}")
    return output


def load_json(path: Path) -> dict[str, object]:
    try:
        return json.loads(path.read_text())
    except (OSError, json.JSONDecodeError) as error:
        raise ValidationError(f"Could not read provenance {path}: {error}") from error


def record_signature(records: list[dict[str, object]]) -> list[tuple[str, int, str]]:
    return sorted(
        (str(record["path"]), int(record["bytes"]), str(record["sha256"]))
        for record in records
    )


def library_signature(provenance: dict[str, object]) -> list[tuple[str, str]]:
    return sorted(
        (str(record["name"]), str(record["sha256"]))
        for record in provenance["resolved_libraries"]
    )


def runtime_signature(provenance: dict[str, object]) -> dict[str, object]:
    runtime = provenance["runtime"]
    return {
        "commit": runtime["commit"],
        "phreeqcrm_commit": runtime["phreeqcrm"]["commit"],
        "solver_sha256": provenance["solver"]["sha256"],
        "libraries": library_signature(provenance),
    }


def scientific_config(provenance: dict[str, object]) -> dict[str, str]:
    ignored = {"ASURF_SURFACE_MODE", "SURFACE_RECONSTRUCTION_LABEL"}
    return {
        key: value
        for key, value in provenance["run_config"].items()
        if key not in ignored
    }


def validate_provenance_pair(
    supported: dict[str, object], legacy: dict[str, object]
) -> None:
    for label, provenance in zip(LABELS, (supported, legacy), strict=True):
        if provenance.get("reconstruction_label") != label:
            raise ValidationError(f"Expected provenance label {label}")
        if "initial" not in provenance or "final" not in provenance:
            raise ValidationError(f"{label} provenance is not complete")
        initial = provenance["initial"]
        if initial.get("surface_log_modes") != [provenance.get("surface_mode")]:
            raise ValidationError(
                f"{label} surface logs do not prove the requested mode"
            )
    if supported["surface_mode"] == legacy["surface_mode"]:
        raise ValidationError("The two runs use the same reconstruction mode")
    if supported["paper_source_commit"] != legacy["paper_source_commit"]:
        raise ValidationError("Paper source commits differ")
    if runtime_signature(supported) != runtime_signature(legacy):
        raise ValidationError("Runtime, solver, or resolved-library provenance differs")
    if scientific_config(supported) != scientific_config(legacy):
        raise ValidationError("Scientific run configuration differs")

    supported_inputs = record_signature(supported["initial"]["matched_input_files"])
    legacy_inputs = record_signature(legacy["initial"]["matched_input_files"])
    if supported_inputs != legacy_inputs:
        raise ValidationError("Non-surface input manifests differ")
    supported_surface = record_signature(supported["initial"]["surface_field_files"])
    legacy_surface = record_signature(legacy["initial"]["surface_field_files"])
    if [item[0] for item in supported_surface] != [item[0] for item in legacy_surface]:
        raise ValidationError("Surface-field partition manifests differ")
    if not supported_surface or supported_surface == legacy_surface:
        raise ValidationError("The reconstructed surface fields do not differ")


def checkpoint_times(case: Path, geom: dict[str, object]) -> list[tuple[float, str]]:
    times = []
    for directory in (case / "processor0").iterdir():
        if not directory.is_dir():
            continue
        try:
            value = float(directory.name)
        except ValueError:
            continue
        if value <= 0:
            continue
        complete = True
        for rank in range(int(geom["partitions"])):
            root = case / f"processor{rank}" / directory.name
            if any(not (root / field).is_file() for field in DYNAMIC_FIELDS):
                complete = False
                break
        if complete:
            times.append((value, directory.name))
    return sorted(times)


def nearest_checkpoint(
    available: list[tuple[float, str]], target: float, tolerance: float
) -> tuple[float, str]:
    candidates = sorted(available, key=lambda item: abs(item[0] - target))
    if not candidates or abs(candidates[0][0] - target) > tolerance:
        raise ValidationError(
            f"No checkpoint within {tolerance:.4g} s of expected time {target:.17g}"
        )
    return candidates[0]


def select_checkpoints(
    supported_times: list[tuple[float, str]],
    legacy_times: list[tuple[float, str]],
    config: dict[str, str],
    expected_count: int,
    early_test: bool,
) -> list[dict[str, object]]:
    timestep = float(config["RT_TIMESTEP"])
    pair_tolerance = max(1e-10, timestep * 1e-6)
    if early_test:
        selected = []
        for supported_time, supported_name in supported_times:
            nearest = nearest_checkpoint(legacy_times, supported_time, pair_tolerance)
            if abs(nearest[0] - supported_time) <= pair_tolerance:
                selected.append(
                    {
                        "time_s": supported_time,
                        "supported_time": supported_name,
                        "legacy_reference_time": nearest[1],
                    }
                )
        if len(selected) < 2:
            raise ValidationError(
                "Early validation requires at least two common checkpoints"
            )
        return selected

    if int(config["RT_CHECKPOINT_COUNT"]) != expected_count:
        raise ValidationError(
            "Saved checkpoint count does not match the required count"
        )
    total_time = float(config["RT_TOTAL_TIME"])
    target_tolerance = 1.01 * timestep
    selected = []
    used_supported, used_legacy = set(), set()
    for index in range(1, expected_count + 1):
        target = total_time * index / expected_count
        supported = nearest_checkpoint(supported_times, target, target_tolerance)
        legacy = nearest_checkpoint(legacy_times, target, target_tolerance)
        if abs(supported[0] - legacy[0]) > pair_tolerance:
            raise ValidationError(
                f"Checkpoint times are not common: {supported[0]} vs {legacy[0]}"
            )
        if supported[1] in used_supported or legacy[1] in used_legacy:
            raise ValidationError(
                "One output was matched to multiple expected checkpoints"
            )
        used_supported.add(supported[1])
        used_legacy.add(legacy[1])
        selected.append(
            {
                "time_s": supported[0],
                "target_time_s": target,
                "supported_time": supported[1],
                "legacy_reference_time": legacy[1],
            }
        )
    return selected


def verify_clean_completion(
    case: Path,
    provenance: dict[str, object],
    geom: dict[str, object],
    final_time: str,
    early_test: bool,
) -> None:
    final = provenance["final"]
    partitions = int(geom["partitions"])
    if final.get("partitions") != partitions:
        raise ValidationError("Final provenance partition count differs from the case")
    if (
        final.get("complete_dumps") != partitions
        or final.get("complete_markers") != partitions
    ):
        raise ValidationError("Final PHREEQC checkpoint is incomplete")
    if not math.isclose(
        float(final["time_s"]), float(final_time), rel_tol=0, abs_tol=1e-10
    ):
        raise ValidationError(
            "Final provenance time differs from the selected checkpoint"
        )

    final_records = {str(record["path"]): record for record in final["field_files"]}
    initial_records = {
        str(record["path"]): record
        for key in ("matched_input_files", "surface_field_files")
        for record in provenance["initial"][key]
    }
    run_root = case.parent
    for rank in range(partitions):
        for field in (*DYNAMIC_FIELDS, *STATIC_FIELDS):
            path = case / f"processor{rank}" / final_time / field
            if not path.is_file() and field in STATIC_FIELDS:
                path = case / f"processor{rank}" / "0" / field
            if not path.is_file():
                raise ValidationError(f"Missing required final/static field: {path}")
            relative = str(path.relative_to(run_root))
            records = initial_records if path.parent.name == "0" else final_records
            record = records.get(relative)
            if record is None or int(record["bytes"]) != path.stat().st_size:
                raise ValidationError(f"Field is absent from provenance: {relative}")
            if record["sha256"] != sha256(path):
                raise ValidationError(f"Field hash mismatch: {relative}")

    if not early_test:
        exit_code = case.parent / "slurm_exit_code.txt"
        if not exit_code.is_file() or exit_code.read_text().strip() != "0":
            raise ValidationError(f"Missing clean Slurm completion record: {exit_code}")


def relative_difference(candidate: float, reference: float) -> float:
    if reference == 0:
        raise ValidationError("A required reference quantity is zero")
    return (candidate - reference) / reference


def normalized_l1(candidate: np.ndarray, reference: np.ndarray) -> float:
    candidate_sum, reference_sum = float(candidate.sum()), float(reference.sum())
    if candidate_sum <= 0 or reference_sum <= 0:
        raise ValidationError("Cannot normalize a non-positive inventory map")
    return float(np.abs(candidate / candidate_sum - reference / reference_sum).sum())


def cosine(candidate: np.ndarray, reference: np.ndarray) -> float:
    denominator = float(np.linalg.norm(candidate) * np.linalg.norm(reference))
    if denominator == 0:
        raise ValidationError("Cannot compute cosine for a zero inventory map")
    return float(np.dot(candidate.ravel(), reference.ravel()) / denominator)


def relative_l2(candidate: np.ndarray, reference: np.ndarray) -> float:
    denominator = float(np.linalg.norm(reference))
    if denominator == 0:
        raise ValidationError("Cannot compute relative L2 against a zero field")
    return float(np.linalg.norm(candidate - reference) / denominator)


def relative_norm(component: np.ndarray, reference: np.ndarray) -> float:
    denominator = float(np.linalg.norm(reference))
    if denominator == 0:
        raise ValidationError("Cannot normalize against a zero field")
    return float(np.linalg.norm(component) / denominator)


def acceptance_checks(
    comparison: dict[str, object], cell_size_m: float
) -> dict[str, bool]:
    """Evaluate the predeclared material-change thresholds."""
    return {
        "reactive_area_below_0p1_percent": abs(
            comparison["reactive_area_relative_difference"]
        )
        < AREA_LIMIT,
        "aqueous_inventory_below_1_percent": abs(
            comparison["aqueous_li_inventory_relative_difference"]
        )
        < RESPONSE_LIMIT,
        "sorbed_inventory_below_1_percent": abs(
            comparison["sorbed_li_inventory_relative_difference"]
        )
        < RESPONSE_LIMIT,
        "aqueous_normalized_l1_below_1_percent": comparison["aqueous_li_normalized_l1"]
        < RESPONSE_LIMIT,
        "sorbed_normalized_l1_below_1_percent": comparison["sorbed_li_normalized_l1"]
        < RESPONSE_LIMIT,
        "aqueous_cosine_at_least_0p995": comparison["aqueous_li_cosine"]
        >= COSINE_LIMIT,
        "sorbed_cosine_at_least_0p995": comparison["sorbed_li_cosine"] >= COSINE_LIMIT,
        "aqueous_x50_shift_within_one_cell": abs(
            comparison["aqueous_front_shift_m"]["x50"]
        )
        <= cell_size_m * (1 + 1e-12),
        "sorbed_x50_shift_within_one_cell": abs(
            comparison["sorbed_front_shift_m"]["x50"]
        )
        <= cell_size_m * (1 + 1e-12),
    }


def front_positions(density: np.ndarray, dx: float) -> dict[str, float]:
    profile = density.sum(axis=0)
    total = float(profile.sum())
    if total <= 0:
        raise ValidationError("Cannot locate a front in a non-positive inventory")
    cumulative = np.cumsum(profile) / total
    positions = {}
    for label, fraction in (("x10", 0.1), ("x50", 0.5), ("x90", 0.9)):
        index = min(int(np.searchsorted(cumulative, fraction)), profile.size - 1)
        positions[label] = (index + 0.5) * dx
    return positions


def static_case_data(
    case: Path, geom: dict[str, object]
) -> dict[str, np.ndarray | float]:
    eps = assemble(case, geom, "0", "eps")
    total_area_density = assemble(case, geom, "0", "aSurf")
    if np.any(eps < 0) or np.any(eps > 1) or np.any(total_area_density < 0):
        raise ValidationError(f"Invalid static field bounds in {case}")
    volume = float(geom["cell_size_m"]) ** 3
    return {
        "eps": eps,
        "area_density": total_area_density,
        "reactive_area_m2": float(total_area_density.sum() * volume),
        "cell_volume_m3": volume,
    }


def checkpoint_metrics(
    cases: dict[str, Path],
    geoms: dict[str, dict[str, object]],
    statics: dict[str, dict[str, np.ndarray | float]],
    checkpoint: dict[str, object],
) -> tuple[dict[str, object], dict[str, dict[str, np.ndarray]]]:
    data = {}
    maps = {}
    for label in LABELS:
        time_name = str(checkpoint[f"{label.replace('-', '_')}_time"])
        li = assemble(cases[label], geoms[label], time_name, "Li+")
        sorbed = assemble(cases[label], geoms[label], time_name, "Surf_aLi")
        eps = np.asarray(statics[label]["eps"])
        area_density = np.asarray(statics[label]["area_density"])
        volume = float(statics[label]["cell_volume_m3"])
        aqueous_density = li * eps
        sorbed_density = sorbed * area_density
        data[label] = {
            "reactive_area_m2": float(statics[label]["reactive_area_m2"]),
            "aqueous_li_inventory_mol": float(aqueous_density.sum() * volume),
            "sorbed_li_inventory_mol": float(sorbed_density.sum() * volume),
            "fronts_m": front_positions(
                aqueous_density, float(geoms[label]["cell_size_m"])
            ),
            "sorbed_fronts_m": front_positions(
                sorbed_density, float(geoms[label]["cell_size_m"])
            ),
        }
        maps[label] = {
            "aqueous_density": aqueous_density,
            "sorbed_density": sorbed_density,
            "surface_loading": sorbed,
        }

    supported, legacy = data["supported"], data["legacy-reference"]
    supported_maps, legacy_maps = maps["supported"], maps["legacy-reference"]
    comparison = {
        "reactive_area_relative_difference": relative_difference(
            supported["reactive_area_m2"], legacy["reactive_area_m2"]
        ),
        "aqueous_li_inventory_relative_difference": relative_difference(
            supported["aqueous_li_inventory_mol"], legacy["aqueous_li_inventory_mol"]
        ),
        "sorbed_li_inventory_relative_difference": relative_difference(
            supported["sorbed_li_inventory_mol"], legacy["sorbed_li_inventory_mol"]
        ),
        "aqueous_li_normalized_l1": normalized_l1(
            supported_maps["aqueous_density"], legacy_maps["aqueous_density"]
        ),
        "sorbed_li_normalized_l1": normalized_l1(
            supported_maps["sorbed_density"], legacy_maps["sorbed_density"]
        ),
        "aqueous_li_cosine": cosine(
            supported_maps["aqueous_density"], legacy_maps["aqueous_density"]
        ),
        "sorbed_li_cosine": cosine(
            supported_maps["sorbed_density"], legacy_maps["sorbed_density"]
        ),
        "aqueous_li_field_relative_l2": relative_l2(
            supported_maps["aqueous_density"], legacy_maps["aqueous_density"]
        ),
        "sorbed_li_field_relative_l2": relative_l2(
            supported_maps["sorbed_density"], legacy_maps["sorbed_density"]
        ),
        "sorbed_li_fixed_reference_area_relative_l2": relative_l2(
            np.asarray(statics["legacy-reference"]["area_density"])
            * supported_maps["surface_loading"],
            legacy_maps["sorbed_density"],
        ),
        "sorbed_li_area_relocation_component_relative_l2": relative_norm(
            supported_maps["surface_loading"]
            * (
                np.asarray(statics["supported"]["area_density"])
                - np.asarray(statics["legacy-reference"]["area_density"])
            ),
            legacy_maps["sorbed_density"],
        ),
        "surface_area_field_relative_l2": relative_l2(
            np.asarray(statics["supported"]["area_density"]),
            np.asarray(statics["legacy-reference"]["area_density"]),
        ),
        "aqueous_front_shift_m": {
            key: supported["fronts_m"][key] - legacy["fronts_m"][key]
            for key in ("x10", "x50", "x90")
        },
        "sorbed_front_shift_m": {
            key: supported["sorbed_fronts_m"][key] - legacy["sorbed_fronts_m"][key]
            for key in ("x10", "x50", "x90")
        },
    }
    checks = acceptance_checks(comparison, float(geoms["supported"]["cell_size_m"]))
    return {
        **checkpoint,
        "supported": data["supported"],
        "legacy-reference": data["legacy-reference"],
        "comparison": comparison,
        "acceptance": {"checks": checks, "passed": all(checks.values())},
    }, maps


def plot_report(
    report: dict[str, object],
    final_maps: dict[str, dict[str, np.ndarray]],
    output: Path,
) -> None:
    checkpoints = report["checkpoints"]
    times = np.array([item["time_s"] for item in checkpoints])
    comparisons = [item["comparison"] for item in checkpoints]
    blue, orange, grey = "#0072B2", "#D55E00", "#666666"

    figure = plt.figure(figsize=(14.5, 8.6))
    outer = figure.add_gridspec(
        3,
        1,
        height_ratios=(1.1, 1, 1),
        left=0.07,
        right=0.96,
        bottom=0.07,
        top=0.91,
        hspace=0.65,
    )
    top_grid = outer[0].subgridspec(1, 4, wspace=0.38)
    axes_top = [figure.add_subplot(top_grid[0, index]) for index in range(4)]

    def series(key: str) -> np.ndarray:
        return np.array([abs(float(item[key])) for item in comparisons])

    axes_top[0].plot(
        times,
        100 * series("reactive_area_relative_difference"),
        "o-",
        color=grey,
        label="area",
    )
    axes_top[0].plot(
        times,
        100 * series("aqueous_li_inventory_relative_difference"),
        "o-",
        color=blue,
        label="aqueous Li",
    )
    axes_top[0].plot(
        times,
        100 * series("sorbed_li_inventory_relative_difference"),
        "s-",
        color=orange,
        label="sorbed Li",
    )
    axes_top[0].axhline(
        1, color="black", linestyle=":", linewidth=1, label="1% response limit"
    )
    axes_top[0].axhline(
        0.1, color=grey, linestyle=":", linewidth=1, label="0.1% area limit"
    )
    axes_top[0].set_yscale("log")
    axes_top[0].set_ylabel("Absolute difference (%)")
    axes_top[0].set_title("Global response")
    axes_top[0].legend(frameon=False, fontsize=8)

    axes_top[1].plot(
        times,
        100 * series("aqueous_li_normalized_l1"),
        "o-",
        color=blue,
        label="aqueous L1 (gate)",
    )
    axes_top[1].plot(
        times,
        100 * series("aqueous_li_field_relative_l2"),
        "o--",
        color=blue,
        label="aqueous L2 (diagnostic)",
    )
    axes_top[1].plot(
        times,
        100 * series("sorbed_li_normalized_l1"),
        "s-",
        color=orange,
        label="sorbed L1 (gate)",
    )
    axes_top[1].plot(
        times,
        100 * series("sorbed_li_field_relative_l2"),
        "s--",
        color=orange,
        label="sorbed L2 (diagnostic)",
    )
    axes_top[1].plot(
        times,
        100 * series("sorbed_li_fixed_reference_area_relative_l2"),
        "^:",
        color=orange,
        label="sorbed fixed-area L2 (diagnostic)",
    )
    axes_top[1].axhline(1, color="black", linestyle=":", linewidth=1)
    axes_top[1].set_yscale("log")
    axes_top[1].set_title("Spatial metrics")
    axes_top[1].legend(
        frameon=False,
        fontsize=6.5,
        ncol=2,
        loc="upper center",
        bbox_to_anchor=(0.5, -0.28),
    )

    axes_top[2].plot(
        times,
        [item["aqueous_li_cosine"] for item in comparisons],
        "o-",
        color=blue,
        label="aqueous Li",
    )
    axes_top[2].plot(
        times,
        [item["sorbed_li_cosine"] for item in comparisons],
        "s-",
        color=orange,
        label="sorbed Li",
    )
    axes_top[2].axhline(COSINE_LIMIT, color="black", linestyle=":", linewidth=1)
    axes_top[2].set_ylim(min(0.9945, axes_top[2].get_ylim()[0]), 1.0002)
    axes_top[2].set_title("Map cosine")
    axes_top[2].legend(frameon=False, fontsize=8)

    for quantity, color, marker in (("aqueous", blue, "o"), ("sorbed", orange, "s")):
        x50_shifts = [
            abs(float(item[f"{quantity}_front_shift_m"]["x50"])) / EXPECTED_CELL_SIZE_M
            for item in comparisons
        ]
        outer_shifts = [
            max(
                abs(float(item[f"{quantity}_front_shift_m"][key]))
                for key in ("x10", "x90")
            )
            / EXPECTED_CELL_SIZE_M
            for item in comparisons
        ]
        axes_top[3].plot(
            times,
            x50_shifts,
            marker + "-",
            color=color,
            label=f"{quantity} x50 (gate)",
        )
        axes_top[3].plot(
            times,
            outer_shifts,
            marker + "--",
            color=color,
            label=f"{quantity} x10/x90 (diagnostic)",
        )
    axes_top[3].axhline(1, color="black", linestyle=":", linewidth=1)
    axes_top[3].set_title("Front shift")
    axes_top[3].set_ylabel("Absolute shift (cells)")
    axes_top[3].legend(frameon=False, fontsize=6.5)
    for axis in axes_top:
        axis.set_xlabel("Time (s)")
        axis.grid(alpha=0.2)

    geom = report["geometry"]
    extent = [
        0,
        float(geom["nx"]) * float(geom["cell_size_m"]) * 1e3,
        0,
        float(geom["ny"]) * float(geom["cell_size_m"]) * 1e3,
    ]
    map_axes, color_axes = [], []
    for row in (1, 2):
        map_grid = outer[row].subgridspec(
            1, 6, width_ratios=(1, 1, 1, 0.035, 0.22, 0.035), wspace=0.18
        )
        map_axes.append([figure.add_subplot(map_grid[0, col]) for col in range(3)])
        color_axes.append(
            (figure.add_subplot(map_grid[0, 3]), figure.add_subplot(map_grid[0, 5]))
        )
    titles = ("Legacy reference", "Supported", "Supported − legacy reference")
    quantities = (
        ("aqueous_density", "Aqueous Li inventory density", "mol m$^{-3}$ bulk"),
        ("sorbed_density", "Sorbed Li inventory density", "mol m$^{-3}$ bulk"),
    )
    for row, (key, label, units) in enumerate(quantities):
        legacy = final_maps["legacy-reference"][key]
        supported = final_maps["supported"][key]
        difference = supported - legacy
        vmin, vmax = min(float(legacy.min()), float(supported.min())), max(
            float(legacy.max()), float(supported.max())
        )
        images = []
        for col, values in enumerate((legacy, supported)):
            images.append(
                map_axes[row][col].imshow(
                    values,
                    origin="lower",
                    extent=extent,
                    vmin=vmin,
                    vmax=vmax,
                    cmap="viridis",
                    aspect="equal",
                    rasterized=True,
                )
            )
        limit = float(np.max(np.abs(difference)))
        if limit == 0:
            limit = np.finfo(float).eps
        diff_image = map_axes[row][2].imshow(
            difference,
            origin="lower",
            extent=extent,
            norm=TwoSlopeNorm(vmin=-limit, vcenter=0, vmax=limit),
            cmap="RdBu_r",
            aspect="equal",
            rasterized=True,
        )
        for col, axis in enumerate(map_axes[row]):
            axis.set_title(titles[col] if row == 0 else "")
            axis.set_xlabel("x (mm)")
            if col == 0:
                axis.set_ylabel(f"{label}\ny (mm)")
            else:
                axis.set_yticklabels([])
        colorbar = figure.colorbar(images[0], cax=color_axes[row][0])
        colorbar.set_label(units)
        difference_bar = figure.colorbar(diff_image, cax=color_axes[row][1])
        difference_bar.set_label(f"Difference ({units})")

    scope = report["scope"]
    suffix = " (early test; not full-horizon evidence)" if scope["early_test"] else ""
    map_time = float(checkpoints[-1]["time_s"])
    figure.suptitle(
        f"Matched Pe = 1 DBS reconstruction sensitivity{suffix}; "
        f"maps at t = {map_time:.6g} s"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(output, dpi=220)
    plt.close(figure)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--supported-case", type=Path, required=True)
    parser.add_argument("--legacy-reference-case", type=Path, required=True)
    parser.add_argument("--supported-provenance", type=Path, required=True)
    parser.add_argument("--legacy-reference-provenance", type=Path, required=True)
    parser.add_argument("--output-json", type=Path, required=True)
    parser.add_argument("--output-figure", type=Path, required=True)
    parser.add_argument("--expected-checkpoints", type=int, default=10)
    parser.add_argument("--early-test", action="store_true")
    args = parser.parse_args()

    cases = {
        "supported": args.supported_case.resolve(),
        "legacy-reference": args.legacy_reference_case.resolve(),
    }
    provenances = {
        "supported": load_json(args.supported_provenance),
        "legacy-reference": load_json(args.legacy_reference_provenance),
    }
    validate_provenance_pair(provenances["supported"], provenances["legacy-reference"])
    geoms = {label: geometry(case) for label, case in cases.items()}
    if geoms["supported"] != geoms["legacy-reference"]:
        raise ValidationError("Case geometries or decompositions differ")
    config = scientific_config(provenances["supported"])
    selected = select_checkpoints(
        checkpoint_times(cases["supported"], geoms["supported"]),
        checkpoint_times(cases["legacy-reference"], geoms["legacy-reference"]),
        config,
        args.expected_checkpoints,
        args.early_test,
    )
    for label in LABELS:
        time_key = f"{label.replace('-', '_')}_time"
        verify_clean_completion(
            cases[label],
            provenances[label],
            geoms[label],
            str(selected[-1][time_key]),
            args.early_test,
        )

    statics = {
        label: static_case_data(case, geoms[label]) for label, case in cases.items()
    }
    results, final_maps = [], None
    for checkpoint in selected:
        metrics, maps = checkpoint_metrics(cases, geoms, statics, checkpoint)
        results.append(metrics)
        final_maps = maps
    assert final_maps is not None
    overall_passed = all(item["acceptance"]["passed"] for item in results)
    report = {
        "schema_version": 2,
        "scope": {
            "early_test": args.early_test,
            "full_horizon_claim_valid": not args.early_test,
            "checkpoint_count": len(results),
            "expected_checkpoint_count": args.expected_checkpoints,
            "expected_end_time_s": float(config["RT_TOTAL_TIME"]),
        },
        "labels": list(LABELS),
        "provenance": {
            "documents": {
                "supported": {
                    "path": str(args.supported_provenance.resolve()),
                    "sha256": sha256(args.supported_provenance),
                },
                "legacy-reference": {
                    "path": str(args.legacy_reference_provenance.resolve()),
                    "sha256": sha256(args.legacy_reference_provenance),
                },
            },
            "paper_source_commit": provenances["supported"]["paper_source_commit"],
            "runtime": runtime_signature(provenances["supported"]),
            "matched_non_surface_input_count": len(
                provenances["supported"]["initial"]["matched_input_files"]
            ),
            "surface_partition_count": len(
                provenances["supported"]["initial"]["surface_field_files"]
            ),
            "sole_intended_difference_verified": True,
        },
        "geometry": geoms["supported"],
        "acceptance_thresholds": {
            "reactive_area_absolute_relative": AREA_LIMIT,
            "response_absolute_relative": RESPONSE_LIMIT,
            "normalized_l1": RESPONSE_LIMIT,
            "cosine_minimum": COSINE_LIMIT,
            "x50_shift_maximum_m": EXPECTED_CELL_SIZE_M,
        },
        "diagnostic_definitions": {
            "inventory_density_relative_l2": (
                "native-cell pointwise L2; non-gating because it includes deliberate "
                "reactive-area relocation"
            ),
            "sorbed_li_fixed_reference_area_relative_l2": (
                "surface-loading response compared after weighting both runs by the "
                "legacy-reference reactive-area field; non-gating"
            ),
            "sorbed_li_area_relocation_component_relative_l2": (
                "L2 norm of supported loading times the reactive-area-field change, "
                "normalized by legacy-reference sorbed inventory density; non-gating"
            ),
            "front_quantiles": (
                "x10/x50/x90 streamwise cumulative inventory quantiles; x10 and x90 "
                "are non-gating diagnostics"
            ),
        },
        "checkpoints": results,
        "overall_passed": overall_passed,
        "prospective_checkpoint_criteria_passed": overall_passed,
        "full_horizon_materially_unchanged": (not args.early_test) and overall_passed,
    }
    args.output_json.parent.mkdir(parents=True, exist_ok=True)
    args.output_json.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    plot_report(report, final_maps, args.output_figure)
    print(f"Wrote {args.output_json}")
    print(f"Wrote {args.output_figure}")
    print(f"Prospective checkpoint criteria passed: {overall_passed}")
    print(f"Full-horizon claim valid: {not args.early_test}")
    return 0 if overall_passed else 3


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except ValidationError as error:
        print(f"Validation failed: {error}", file=sys.stderr)
        raise SystemExit(2)
