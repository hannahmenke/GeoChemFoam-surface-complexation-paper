#!/usr/bin/env python3
"""Conservative storage estimate for two-scale ARCHER production jobs."""

from __future__ import annotations

import argparse
import os


GIB = 1024**3
CHECKPOINT_BYTES_PER_CELL = 5000
FIXED_OVERHEAD_BYTES = 5 * GIB
BYTES_PER_SCALAR_ASCII = 22
ARCHIVED_FIELDS = 11
SELECTED_ARCHIVE_SAFETY_NUMERATOR = 5
SELECTED_ARCHIVE_SAFETY_DENOMINATOR = 2


def case_cells(case_name: str, environment: dict[str, str]) -> int:
    mirror_copies = int(environment.get("X_MIRROR_COPIES", "2"))
    if mirror_copies < 0:
        raise ValueError("X_MIRROR_COPIES must be non-negative")
    if case_name == "resolved-reference":
        prefix, default_max = "RESOLVED", "6000"
    elif case_name == "dbs-upscaled":
        prefix, default_max = "DBS", "1200"
    else:
        raise ValueError(f"unknown TARGET_CASE: {case_name}")

    x_min = int(environment.get(f"{prefix}_CROP_X_MIN", "0"))
    x_max = int(environment.get(f"{prefix}_CROP_X_MAX", default_max))
    y_min = int(environment.get(f"{prefix}_CROP_Y_MIN", "0"))
    y_max = int(environment.get(f"{prefix}_CROP_Y_MAX", default_max))
    coarsen_factor = int(environment.get(f"{prefix}_COARSEN_FACTOR", "1"))
    if coarsen_factor <= 0:
        raise ValueError("coarsen factor must be positive")
    if x_max <= x_min or y_max <= y_min:
        raise ValueError("crop bounds must define a positive area")
    if (x_max - x_min) % coarsen_factor or (y_max - y_min) % coarsen_factor:
        raise ValueError("crop dimensions must be divisible by coarsen factor")
    return (
        ((x_max - x_min) // coarsen_factor)
        * (1 + mirror_copies)
        * ((y_max - y_min) // coarsen_factor)
    )


def estimate_bytes(
    case_name: str,
    checkpoint_count: int,
    scope: str,
    archive_mode: str,
    environment: dict[str, str] | None = None,
) -> int:
    if checkpoint_count < 1:
        raise ValueError("checkpoint count must be positive")
    if archive_mode not in {"metadata", "selected", "full"}:
        raise ValueError(f"unknown archive mode: {archive_mode}")
    if scope not in {"scratch", "archive"}:
        raise ValueError(f"unknown estimate scope: {scope}")

    cells = case_cells(
        case_name,
        environment if environment is not None else dict(os.environ),
    )
    # Every completed checkpoint retains its PHREEQCRM dump and OpenFOAM fields.
    # The 4.32-million-cell DBS runs measured 19.17 GiB/checkpoint, or about
    # 4.77 kB/cell. Budget 5.0 kB/cell plus fixed mesh/log/time-zero overhead.
    retained_checkpoint_storage = (
        cells * CHECKPOINT_BYTES_PER_CELL * checkpoint_count
        + FIXED_OVERHEAD_BYTES
    )
    if scope == "scratch" or archive_mode == "full":
        return retained_checkpoint_storage
    if archive_mode == "selected":
        write_count = checkpoint_count + 1  # includes time zero
        selected = cells * BYTES_PER_SCALAR_ASCII * ARCHIVED_FIELDS * write_count
        selected *= SELECTED_ARCHIVE_SAFETY_NUMERATOR
        selected //= SELECTED_ARCHIVE_SAFETY_DENOMINATOR
        return selected + FIXED_OVERHEAD_BYTES
    return FIXED_OVERHEAD_BYTES


def required_bytes(modeled: int, override: str) -> int:
    if not override:
        return modeled
    if not override.isdecimal():
        raise ValueError("storage override must be a non-negative integer")
    requested = int(override)
    if requested < modeled:
        raise ValueError(
            f"storage override {requested} is below modeled requirement {modeled}"
        )
    return requested


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True)
    parser.add_argument("--checkpoint-count", required=True, type=int)
    parser.add_argument("--scope", choices=("scratch", "archive"), required=True)
    parser.add_argument(
        "--archive-mode", choices=("metadata", "selected", "full"), required=True
    )
    parser.add_argument("--override", default="")
    args = parser.parse_args()
    try:
        modeled = estimate_bytes(
            args.case,
            args.checkpoint_count,
            args.scope,
            args.archive_mode,
        )
        result = required_bytes(modeled, args.override)
    except ValueError as error:
        parser.error(str(error))
    print(result)


if __name__ == "__main__":
    main()
