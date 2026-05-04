#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


def read_internal_values(path: Path) -> list[float]:
    text = path.read_text()
    match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not match:
        raise RuntimeError(f"Expected nonuniform scalar field in {path}")
    count = int(match.group(1))
    values = [float(value) for value in match.group(2).split()]
    if len(values) != count:
        raise RuntimeError(f"Field length mismatch in {path}")
    return values


def as_field(template: str, values: list[float]) -> str:
    text = re.sub(r"object\s+\S+;", "object      aSurfIntrinsic;", template, count=1)
    text = re.sub(
        r"dimensions\s+\[[^\]]+\];",
        "dimensions      [0 -1 0 0 0 0 0];",
        text,
        count=1,
    )
    block = (
        "internalField   nonuniform List<scalar>\n"
        f"{len(values)}\n"
        "(\n"
        + "\n".join(f"{value:.8g}" for value in values)
        + "\n)\n;\n"
    )
    text, count = re.subn(
        r"internalField\s+nonuniform\s+List<scalar>\s*\d+\s*\((.*?)\)\s*;",
        block,
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("Could not replace internalField")
    return text


def write_for_zero_dir(zero_dir: Path, matrix_porosity: float, intrinsic_asurf: float) -> None:
    eps_path = zero_dir / "eps"
    eps_values = read_internal_values(eps_path)
    values = [
        intrinsic_asurf if abs(value - matrix_porosity) < 1e-6 else 0.0
        for value in eps_values
    ]
    (zero_dir / "aSurfIntrinsic").write_text(as_field(eps_path.read_text(), values))


def main() -> None:
    if len(sys.argv) != 3:
        raise SystemExit("Usage: write_intrinsic_asurf.py CASE_DIR METADATA_JSON")
    case_dir = Path(sys.argv[1])
    metadata = json.loads(Path(sys.argv[2]).read_text())
    dbs_metadata = metadata.get("dbs_full_upscaled", metadata.get("dbs_crop"))
    if dbs_metadata is None:
        raise RuntimeError("metadata must contain dbs_full_upscaled or dbs_crop")
    matrix_porosity = float(dbs_metadata["matrix_porosity_from_rev"])
    intrinsic_asurf = float(dbs_metadata["matrix_intrinsic_asurf_per_bulk_volume_m-1"])

    processor_zero_dirs = sorted(case_dir.glob("processor*/0"))
    if processor_zero_dirs:
        for zero_dir in processor_zero_dirs:
            write_for_zero_dir(zero_dir, matrix_porosity, intrinsic_asurf)
    else:
        write_for_zero_dir(case_dir / "0", matrix_porosity, intrinsic_asurf)

    print(
        "Wrote aSurfIntrinsic for matrix cells: "
        f"eps={matrix_porosity:.8g}, aSurf={intrinsic_asurf:.8g} m^-1"
    )


if __name__ == "__main__":
    main()
