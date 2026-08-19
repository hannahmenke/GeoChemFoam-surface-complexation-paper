#!/usr/bin/env python3

from __future__ import annotations

import argparse
import math
import re
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ZERO_DIR = ROOT / "0"
ZERO_ORIG_DIR = ROOT / "0_orig"
CONST_DIR = ROOT / "constant"
SYSTEM_DIR = ROOT / "system"

BASE_H = 1.051e-7
BASE_OH = 1.069e-7
BASE_THETA = 0.5
BASE_ASURF = 1.0e5
BASE_U = 1.0e-6
BASE_D = 1.0e-11
DOMAIN_LENGTH = 4.0e-5


def read_text(path: Path) -> str:
    return path.read_text()


def write_text(path: Path, text: str) -> None:
    path.write_text(text)


def copy_zero_templates() -> None:
    ZERO_DIR.mkdir(exist_ok=True)
    for template in ZERO_ORIG_DIR.iterdir():
        if template.is_file():
            shutil.copy2(template, ZERO_DIR / template.name)


def replace_internal_scalar(text: str, value: float) -> str:
    replacement = f"internalField   uniform {value:.16e};"
    updated, count = re.subn(
        r"internalField\s+(uniform|nonuniform)\s+.*?;",
        replacement,
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("Failed to replace internalField")
    return updated


def replace_internal_vector(text: str, value: tuple[float, float, float]) -> str:
    replacement = (
        "internalField   uniform "
        f"({value[0]:.16e} {value[1]:.16e} {value[2]:.16e});"
    )
    updated, count = re.subn(
        r"internalField\s+(uniform|nonuniform)\s+.*?;",
        replacement,
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("Failed to replace internal vector field")
    return updated


def patch_block(text: str, patch_name: str, body: str) -> str:
    pattern = rf"(^\s*{re.escape(patch_name)}\s*\n\s*\{{\n)(.*?)(^\s*\}})"
    updated, count = re.subn(pattern, rf"\1{body}\3", text, flags=re.M | re.S)
    if count != 1:
        raise RuntimeError(f"Failed to patch block {patch_name}")
    return updated


def scalar_patch_body(patch_type: str, value: float | None = None) -> str:
    body = f"        type            {patch_type};\n"
    if value is not None:
        body += f"        value           uniform {value:.16e};\n"
    return body


def vector_patch_body(
    patch_type: str, value: tuple[float, float, float] | None = None
) -> str:
    body = f"        type            {patch_type};\n"
    if value is not None:
        body += (
            "        value           uniform "
            f"({value[0]:.16e} {value[1]:.16e} {value[2]:.16e});\n"
        )
    return body


def configure_scalar_field(
    name: str,
    internal: float,
    inlet_type: str = "zeroGradient",
    inlet_value: float | None = None,
    outlet_type: str = "zeroGradient",
    walls_type: str = "zeroGradient",
    fixed_walls_type: str = "zeroGradient",
) -> None:
    path = ZERO_DIR / name
    text = read_text(path).replace("//globalConcentrationMixed", "")
    text = replace_internal_scalar(text, internal)
    text = patch_block(text, "walls", scalar_patch_body(walls_type))
    text = patch_block(text, "fixedWalls", scalar_patch_body(fixed_walls_type))
    text = patch_block(text, "inlet", scalar_patch_body(inlet_type, inlet_value))
    text = patch_block(text, "outlet", scalar_patch_body(outlet_type))
    text = text.replace("type empty;", "type            empty;")
    write_text(path, text)


def configure_vector_field(name: str, internal: tuple[float, float, float]) -> None:
    path = ZERO_DIR / name
    text = read_text(path)
    text = replace_internal_vector(text, internal)
    text = patch_block(text, "walls", vector_patch_body("fixedValue", (0.0, 0.0, 0.0)))
    text = patch_block(
        text, "fixedWalls", vector_patch_body("fixedValue", (0.0, 0.0, 0.0))
    )
    text = patch_block(text, "inlet", vector_patch_body("fixedValue", internal))
    text = patch_block(text, "outlet", vector_patch_body("zeroGradient"))
    write_text(path, text)


def copy_thermo(surface: bool) -> None:
    source = (
        CONST_DIR / "thermoPhysicalPropertiesSurface"
        if surface
        else CONST_DIR / "thermoPhysicalPropertiesAqueous"
    )
    target = CONST_DIR / "thermoPhysicalProperties"
    if source.resolve() != target.resolve():
        shutil.copy2(source, target)


def set_diffusion(value: float) -> None:
    path = CONST_DIR / "thermoPhysicalProperties"
    text = read_text(path)
    replacement = f"D D [ 0 2 -1 0 0 0 0 ] {value:.16e};"
    updated, count = re.subn(
        r"D\s+D\s+\[\s*0\s+2\s+-1\s+0\s+0\s+0\s+0\s*\]\s+[^;]+;",
        replacement,
        text,
    )
    if count < 1:
        raise RuntimeError("Failed to set diffusion coefficients")
    write_text(path, updated)


OUTLET_PROBE_BLOCK = """\
functions
{
    outletCa
    {
        type            surfaceFieldValue;
        libs            (fieldFunctionObjects);
        log             false;
        writeControl    timeStep;
        writeInterval   1;
        regionType      patch;
        name            outlet;
        operation       areaAverage;
        fields          ( "Ca+2" );
        writeFields     false;
    }
}
"""


def write_control(
    end_time: float,
    delta_t: float,
    write_interval: float,
    outlet_probe: bool = False,
) -> None:
    functions_block = OUTLET_PROBE_BLOCK if outlet_probe else ""
    text = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    location    "system";
    object      controlDict;
}}

application     reactiveScalarTransportDBSFoam;

startFrom       startTime;

startTime       0;

stopAt          endTime;

endTime         {end_time:.16e};

deltaT          {delta_t:.16e};

writeControl    adjustableRunTime;

writeInterval   {write_interval:.16e};

purgeWrite      0;

writeFormat     ascii;

writePrecision  8;

writeCompression off;

timeFormat      general;

timePrecision   8;

runTimeModifiable yes;

{functions_block}"""
    write_text(SYSTEM_DIR / "controlDict", text)


def parse_scalar_field(path: Path) -> list[float]:
    text = read_text(path)
    uniform_match = re.search(r"internalField\s+uniform\s+([^\n;]+)\s*;", text)
    if uniform_match:
        return [float(uniform_match.group(1))]

    nonuniform_match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if nonuniform_match:
        count = int(nonuniform_match.group(1))
        values = [float(item) for item in nonuniform_match.group(2).split()]
        if len(values) != count:
            raise RuntimeError(f"Value count mismatch in {path}")
        return values

    raise RuntimeError(f"Unsupported field format in {path}")


def mean(values: list[float]) -> float:
    return sum(values) / len(values)


def ogata_banks(c_in: float, velocity: float, diffusion: float, time_value: float, x: float) -> float:
    if time_value <= 0.0:
        return c_in if x <= 0.0 else 0.0

    if diffusion <= 0.0:
        return c_in if x <= velocity * time_value else 0.0

    denom = 2.0 * math.sqrt(diffusion * time_value)
    term1 = 0.5 * math.erfc((x - velocity * time_value) / denom)
    term2 = 0.5 * math.exp(velocity * x / diffusion) * math.erfc((x + velocity * time_value) / denom)
    return c_in * (term1 + term2)


def profile_metrics(
    values: list[float], c_in: float, velocity: float, diffusion: float, time_value: float
) -> tuple[float, float]:
    count = len(values)
    dx = DOMAIN_LENGTH / max(count, 1)
    l1 = 0.0
    linf = 0.0

    for index, numeric in enumerate(values):
        x = (index + 0.5) * dx
        expected = ogata_banks(c_in, velocity, diffusion, time_value, x)
        diff = abs(numeric - expected)
        l1 += diff
        linf = max(linf, diff)

    scale = max(abs(c_in), 1.0e-30)
    return (l1 / count) / scale, linf / scale


def analytical_profile(
    count: int, c_in: float, velocity: float, diffusion: float, time_value: float
) -> list[float]:
    dx = DOMAIN_LENGTH / max(count, 1)
    return [
        ogata_banks(c_in, velocity, diffusion, time_value, (index + 0.5) * dx)
        for index in range(count)
    ]


def prepare(mode: str, surface: bool, ca_value: float) -> None:
    copy_zero_templates()
    copy_thermo(surface)
    set_diffusion(BASE_D if mode == "transport" else 0.0)

    configure_scalar_field("aSurf", BASE_ASURF if surface else 0.0)
    configure_scalar_field("theta", BASE_THETA, "zeroGradient", BASE_THETA)
    configure_scalar_field("epsNum", BASE_THETA, "zeroGradient", BASE_THETA)
    configure_scalar_field("Surf_a-", 0.0)
    configure_scalar_field("Surf_aCa+", 0.0)
    configure_scalar_field("Surf_aH", 0.0)

    if mode == "batch":
        write_control(1.0, 1.0, 1.0)
        configure_vector_field("U", (0.0, 0.0, 0.0))
        configure_scalar_field("Ca+2", ca_value)
        configure_scalar_field("Cl-", 2.0 * ca_value)
        configure_scalar_field("H+", BASE_H)
        configure_scalar_field("OH-", BASE_OH)
    elif mode == "transport":
        write_control(80.0, 0.25, 10.0, outlet_probe=True)
        configure_vector_field("U", (BASE_U, 0.0, 0.0))
        configure_scalar_field("Ca+2", 0.0, "fixedValue", ca_value)
        configure_scalar_field("Cl-", 0.0, "fixedValue", 2.0 * ca_value)
        configure_scalar_field("H+", BASE_H, "fixedValue", BASE_H)
        configure_scalar_field("OH-", BASE_OH, "fixedValue", BASE_OH)
    else:
        raise RuntimeError(f"Unsupported mode: {mode}")


def analyze_batch(c1_dir: Path, c2_dir: Path) -> None:
    c_eq1 = mean(parse_scalar_field(c1_dir / "Ca+2"))
    c_eq2 = mean(parse_scalar_field(c2_dir / "Ca+2"))
    gamma_eq1 = mean(parse_scalar_field(c1_dir / "Surf_aCa+"))
    gamma_eq2 = mean(parse_scalar_field(c2_dir / "Surf_aCa+"))
    delta_c = c_eq2 - c_eq1
    if abs(delta_c) < 1e-30:
        raise RuntimeError("Batch secant is singular")
    k_s = (gamma_eq2 - gamma_eq1) / delta_c
    print(f"C_eq1={c_eq1:.16e}")
    print(f"C_eq2={c_eq2:.16e}")
    print(f"Gamma_eq1={gamma_eq1:.16e}")
    print(f"Gamma_eq2={gamma_eq2:.16e}")
    print(f"K_s_field={k_s:.16e}")


def parse_phreeqc_time(log_path: Path) -> float:
    text = read_text(log_path)
    match = re.search(
        r"PhreeqcRM chemistry timing summary: calls=\d+, total_s=([0-9.eE+-]+)",
        text,
    )
    if not match:
        raise RuntimeError(f"Missing timing summary in {log_path}")
    return float(match.group(1))


def compare_transport(surface_dir: Path, aqueous_dir: Path, k_s: float, c_in: float) -> None:
    surface_ca_values = parse_scalar_field(surface_dir / "Ca+2")
    aqueous_ca_values = parse_scalar_field(aqueous_dir / "Ca+2")
    surface_ca = mean(surface_ca_values)
    aqueous_ca = mean(aqueous_ca_values)
    surface_gamma_values = parse_scalar_field(surface_dir / "Surf_aCa+")
    surface_gamma = mean(surface_gamma_values)
    max_surf = max(surface_gamma_values)

    # Current DBS Surf_* fields inherit the legacy PHREEQC surface scaling.
    # In field units, the conserved bulk inventory is:
    #   M_field = theta*C + (aSurf/theta)*Gamma_field
    # so the matching field-level retardation factor is:
    #   R_field = 1 + aSurf*K_s_field/theta^2
    r_factor = 1.0 + (BASE_ASURF * k_s) / (BASE_THETA * BASE_THETA)
    v_surface = BASE_U / (BASE_THETA * r_factor)
    v_aqueous = BASE_U / BASE_THETA
    d_surface = BASE_D / r_factor
    d_aqueous = BASE_D
    expected_surface_values = analytical_profile(
        len(surface_ca_values), c_in, v_surface, d_surface, 10.0
    )
    expected_aqueous_values = analytical_profile(
        len(aqueous_ca_values), c_in, v_aqueous, d_aqueous, 10.0
    )
    expected_surface_mean = mean(expected_surface_values)
    expected_aqueous_mean = mean(expected_aqueous_values)
    total_surface_equiv = BASE_THETA * surface_ca + (BASE_ASURF / BASE_THETA) * surface_gamma
    total_aqueous_equiv = BASE_THETA * aqueous_ca
    expected_total_surface_equiv = BASE_THETA * r_factor * expected_surface_mean
    expected_total_aqueous_equiv = BASE_THETA * expected_aqueous_mean
    l1_surface, linf_surface = profile_metrics(surface_ca_values, c_in, v_surface, d_surface, 10.0)
    l1_aqueous, linf_aqueous = profile_metrics(aqueous_ca_values, c_in, v_aqueous, d_aqueous, 10.0)

    rel_surface = abs(surface_ca - expected_surface_mean) / max(abs(expected_surface_mean), 1e-30)
    rel_aqueous = abs(aqueous_ca - expected_aqueous_mean) / max(abs(expected_aqueous_mean), 1e-30)
    rel_total_surface = abs(total_surface_equiv - expected_total_surface_equiv) / max(abs(expected_total_surface_equiv), 1e-30)
    rel_total_aqueous = abs(total_aqueous_equiv - expected_total_aqueous_equiv) / max(abs(expected_total_aqueous_equiv), 1e-30)
    time_surface = parse_phreeqc_time(surface_dir / "log.out")
    time_aqueous = parse_phreeqc_time(aqueous_dir / "log.out")

    print(f"K_s_field={k_s:.16e}")
    print(f"R_field={r_factor:.16e}")
    print(f"expected_mean_surface={expected_surface_mean:.16e}")
    print(f"numeric_mean_surface={surface_ca:.16e}")
    print(f"rel_err_surface={rel_surface:.16e}")
    print(f"l1_rel_surface={l1_surface:.16e}")
    print(f"linf_rel_surface={linf_surface:.16e}")
    print(f"expected_mean_aqueous={expected_aqueous_mean:.16e}")
    print(f"numeric_mean_aqueous={aqueous_ca:.16e}")
    print(f"rel_err_aqueous={rel_aqueous:.16e}")
    print(f"l1_rel_aqueous={l1_aqueous:.16e}")
    print(f"linf_rel_aqueous={linf_aqueous:.16e}")
    print(f"numeric_mean_surf_aCa={surface_gamma:.16e}")
    print(f"total_surface_equiv={total_surface_equiv:.16e}")
    print(f"expected_total_surface_equiv={expected_total_surface_equiv:.16e}")
    print(f"rel_err_total_surface={rel_total_surface:.16e}")
    print(f"total_aqueous_equiv={total_aqueous_equiv:.16e}")
    print(f"expected_total_aqueous_equiv={expected_total_aqueous_equiv:.16e}")
    print(f"rel_err_total_aqueous={rel_total_aqueous:.16e}")
    print(f"max_surf_aCa={max_surf:.16e}")
    print(f"phreeqc_time_surface={time_surface:.16e}")
    print(f"phreeqc_time_aqueous={time_aqueous:.16e}")

    if max_surf <= 0.0:
        raise RuntimeError("Analytical benchmark produced no adsorbed calcium")
    if surface_ca >= aqueous_ca:
        raise RuntimeError("Surface run did not retard the calcium front")
    if l1_surface > 0.08 or linf_surface > 0.18:
        raise RuntimeError("Surface run deviates too far from the analytical profile")
    if l1_aqueous > 0.05 or linf_aqueous > 0.12:
        raise RuntimeError("Aqueous run deviates too far from the analytical profile")
    if rel_total_surface > 0.05 or rel_total_aqueous > 0.05:
        raise RuntimeError("Analytical benchmark total inventory does not match the advection-diffusion limit")


def main() -> None:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)

    prepare_parser = subparsers.add_parser("prepare")
    prepare_parser.add_argument("--mode", choices=("batch", "transport"), required=True)
    prepare_parser.add_argument("--surface", choices=("on", "off"), required=True)
    prepare_parser.add_argument("--ca", type=float, required=True)

    analyze_parser = subparsers.add_parser("analyze-batch")
    analyze_parser.add_argument("--c1-dir", type=Path, required=True)
    analyze_parser.add_argument("--c2-dir", type=Path, required=True)

    compare_parser = subparsers.add_parser("compare-transport")
    compare_parser.add_argument("--surface-dir", type=Path, required=True)
    compare_parser.add_argument("--aqueous-dir", type=Path, required=True)
    compare_parser.add_argument("--k-s", type=float, required=True)
    compare_parser.add_argument("--ca-in", type=float, required=True)

    args = parser.parse_args()

    if args.command == "prepare":
        prepare(args.mode, args.surface == "on", args.ca)
    elif args.command == "analyze-batch":
        analyze_batch(args.c1_dir, args.c2_dir)
    elif args.command == "compare-transport":
        compare_transport(args.surface_dir, args.aqueous_dir, args.k_s, args.ca_in)


if __name__ == "__main__":
    main()
