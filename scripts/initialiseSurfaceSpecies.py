#!/usr/bin/env python3
"""Initialise surface-species fields for upstream phreeqcMixture cases."""

from __future__ import annotations

import argparse
import ctypes
import os
import re
from pathlib import Path


def dictionary_block(text: str, name: str) -> str:
    match = re.search(rf"\b{re.escape(name)}\s*\{{(.*?)\n\}}", text, re.S)
    if not match:
        raise RuntimeError(f"Missing {name} block")
    return match.group(1)


def names_from_block(text: str, name: str) -> list[str]:
    return re.findall(r"([A-Za-z][A-Za-z0-9_+\-]*)\s*;", dictionary_block(text, name))


def densities_from_block(text: str) -> dict[str, float]:
    block = dictionary_block(text, "surfaceMasterDensities")
    return {
        name: float(value)
        for name, value in re.findall(
            r"([A-Za-z][A-Za-z0-9_+\-]*)\s+([0-9.eE+\-]+)\s*;", block
        )
    }


def phreeqc_library() -> Path:
    if value := os.environ.get("PHREEQCRM_LIBBIN"):
        return Path(value) / "libPhreeqcRM.so"
    if value := os.environ.get("GCFOAM_DIR"):
        return Path(value) / "ThirdParty/PhreeqcRM/lib/libPhreeqcRM.so"
    raise RuntimeError("Set PHREEQCRM_LIBBIN or GCFOAM_DIR")


def equilibrium_species(
    database: Path,
    reactions: Path,
    species: list[str],
    masters: list[str],
    densities: dict[str, float],
    solution_id: int,
) -> dict[str, float]:
    lib = ctypes.CDLL(str(phreeqc_library()))
    lib.CreateIPhreeqc.restype = ctypes.c_int
    lib.GetSelectedOutputString.restype = ctypes.c_char_p
    lib.GetSelectedOutputString.argtypes = [ctypes.c_int]
    for function, arguments in (
        ("LoadDatabase", [ctypes.c_int, ctypes.c_char_p]),
        ("RunString", [ctypes.c_int, ctypes.c_char_p]),
        ("SetCurrentSelectedOutputUserNumber", [ctypes.c_int, ctypes.c_int]),
        ("SetSelectedOutputStringOn", [ctypes.c_int, ctypes.c_int]),
        ("DestroyIPhreeqc", [ctypes.c_int]),
    ):
        getattr(lib, function).argtypes = arguments

    instance = lib.CreateIPhreeqc()
    if instance < 0:
        raise RuntimeError("CreateIPhreeqc failed")
    try:
        if lib.LoadDatabase(instance, str(database).encode()) != 0:
            raise RuntimeError(f"Could not load {database}")
        lib.SetSelectedOutputStringOn(instance, 1)
        surface_lines = [
            f"{master} {densities[master] * 1000:.17g} 1 1" for master in masters
        ]
        punch = ", ".join(f'MOL("{name}")' for name in species)
        extra = "\n".join(
            [
                "SURFACE 999",
                f"-equilibrate with solution {solution_id}",
                *surface_lines,
                "SELECTED_OUTPUT 999",
                "-reset false",
                "USER_PUNCH 999",
                "-headings " + " ".join(species),
                "-start",
                "10 PUNCH " + punch,
                "-end",
                "END",
            ]
        )
        source = reactions.read_text() + "\n" + extra + "\n"
        if lib.RunString(instance, source.encode()) != 0:
            raise RuntimeError(f"PHREEQC surface initialisation failed for {reactions}")
        lib.SetCurrentSelectedOutputUserNumber(instance, 999)
        lib.SetSelectedOutputStringOn(instance, 1)
        output = lib.GetSelectedOutputString(instance)
        if not output:
            raise RuntimeError("PHREEQC returned no surface initialisation output")
        lines = [line.split() for line in output.decode().splitlines() if line.strip()]
        headings, values = lines[-2], lines[-1]
        if headings != species or len(values) != len(species):
            raise RuntimeError(f"Unexpected PHREEQC surface output: {output.decode()}")
        # One square metre of surface was used, so mol divided by 1000 gives
        # the OpenFOAM field convention of kmol per square metre.
        return {name: float(value) / 1000 for name, value in zip(headings, values)}
    finally:
        lib.DestroyIPhreeqc(instance)


def update_field(path: Path, value: float) -> None:
    text = path.read_text()
    updated, count = re.subn(
        r"internalField\s+uniform\s+[^;]+;",
        f"internalField   uniform {value:.16e};",
        text,
        count=1,
    )
    if count != 1:
        raise RuntimeError(f"Expected a uniform internalField in {path}")
    path.write_text(updated)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("case", type=Path, nargs="?", default=Path("."))
    parser.add_argument("--time", default="0")
    args = parser.parse_args()

    case = args.case.resolve()
    thermo = (case / "constant/thermoPhysicalProperties").read_text()
    species = names_from_block(thermo, "surfaceSpecies")
    masters = names_from_block(thermo, "surfaceMasters")
    densities = densities_from_block(thermo)
    solution_match = re.search(r"\bsurfaceInitialSolutionId\s+(\d+)\s*;", thermo)
    solution_id = int(solution_match.group(1)) if solution_match else 0
    missing = [name for name in masters if name not in densities]
    if missing:
        raise RuntimeError(f"Missing surface master densities: {', '.join(missing)}")

    values = equilibrium_species(
        case / "constant/GeoChem.dat",
        case / "constant/phreeqcReactions",
        species,
        masters,
        densities,
        solution_id,
    )
    time_dirs = [case / args.time]
    time_dirs.extend(sorted(case.glob(f"processor*/{args.time}")))
    updated = 0
    for time_dir in time_dirs:
        if not time_dir.is_dir():
            continue
        for name, value in values.items():
            field = time_dir / name
            if field.is_file():
                update_field(field, value)
                updated += 1
    if updated == 0:
        raise RuntimeError(f"No surface-species fields found at time {args.time}")
    print("Initial surface state: " + ", ".join(f"{k}={v:.6e}" for k, v in values.items()))


if __name__ == "__main__":
    main()
