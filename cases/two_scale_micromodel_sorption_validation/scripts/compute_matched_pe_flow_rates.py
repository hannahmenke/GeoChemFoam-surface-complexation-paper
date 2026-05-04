#!/usr/bin/env python3
from __future__ import annotations

import csv
import json
import sys
from pathlib import Path


def read_poro_perm(case_dir: Path) -> dict[str, float]:
    with (case_dir / "poroPerm.csv").open() as handle:
        row = next(csv.DictReader(handle, delimiter=" "))
    return {key: float(value) for key, value in row.items()}


def longitudinal_dispersion_multiplier(pe: float) -> float:
    if pe < 1.0:
        return 0.5995 * (1.0 + 0.228 * pe**1.1187)
    if pe < 10.0:
        return 0.5995 * (1.0 + 0.228 * pe**1.1187)
    return 0.5995 * (1.0 + 0.088 * pe**1.599)


def main() -> None:
    if len(sys.argv) != 5:
        raise SystemExit(
            "Usage: compute_matched_pe_flow_rates.py ROOT_DIR TARGET_PE DIFFUSION OUT_JSON"
        )

    root = Path(sys.argv[1])
    target_pe = float(sys.argv[2])
    diffusion = float(sys.argv[3])
    out_path = Path(sys.argv[4])

    specs = {
        "resolved-reference": {"height_m": 6.0e-3, "depth_m": 1.0e-6},
        "dbs-upscaled": {"height_m": 6.0e-3, "depth_m": 5.0e-6},
    }

    result = {
        "target_pe": target_pe,
        "pe_definition": {
            "formula": "Pe = U_D * L_pore / (D * phi)",
            "darcy_velocity_symbol": "U_D",
            "characteristic_length": "L_pore from processPoroPerm for each calibrated case",
            "diffusion": "aqueous molecular diffusion used for imposed-flow Pe",
            "porosity": "case porosity from processPoroPerm",
        },
        "diffusion_m2_per_s": diffusion,
        "domain_length_m": 18.0e-3,
        "target_front_fraction": 2.0 / 3.0,
        "runtime_safety_factor": 1.25,
        "matrix_longitudinal_effective_diffusion_m2_per_s": diffusion
        * longitudinal_dispersion_multiplier(target_pe),
        "matrix_longitudinal_effective_diffusion_model": {
            "quantity": "D_ex",
            "source": "Maes and Menke (2024), multiscale micromodel matrix REV, Eq. (51)",
            "selected_component": "longitudinal",
        },
        "cases": {},
    }

    lines = [
        "#!/usr/bin/env bash",
        f"export TARGET_PE={target_pe:.12g}",
        f"export DIFFUSION={diffusion:.12g}",
        f"export RESOLVED_REFERENCE_DIFFUSION={diffusion:.12g}",
        "export DBS_UPSCALED_DIFFUSION="
        f"{result['matrix_longitudinal_effective_diffusion_m2_per_s']:.12g}",
    ]

    for case_name, geometry in specs.items():
        metrics = read_poro_perm(root / case_name)
        porosity = metrics["poro"]
        lpore = metrics["Lpore"]
        darcy_velocity = target_pe * diffusion * porosity / lpore
        pore_velocity = darcy_velocity / porosity
        area = geometry["height_m"] * geometry["depth_m"]
        flow_rate = darcy_velocity * area
        achieved_pe = darcy_velocity * lpore / (diffusion * porosity)
        front_time = result["target_front_fraction"] * result["domain_length_m"] / pore_velocity

        result["cases"][case_name] = {
            "calibration": metrics,
            "height_m": geometry["height_m"],
            "depth_m": geometry["depth_m"],
            "inlet_area_m2": area,
            "target_darcy_velocity_m_per_s": darcy_velocity,
            "target_pore_velocity_m_per_s": pore_velocity,
            "target_flow_rate_m3_per_s": flow_rate,
            "target_pe_check": achieved_pe,
            "advective_time_to_target_front_s": front_time,
        }

        env_name = case_name.upper().replace("-", "_")
        lines.append(f"export {env_name}_FLOW_RATE={flow_rate:.12g}")

    max_front_time = max(
        case["advective_time_to_target_front_s"] for case in result["cases"].values()
    )
    recommended_total_time = result["runtime_safety_factor"] * max_front_time
    result["recommended_reactive_transport_time_s"] = recommended_total_time
    result["recommended_write_interval_s"] = recommended_total_time
    lines.append(f"export RECOMMENDED_RT_TOTAL_TIME={recommended_total_time:.12g}")
    lines.append(f"export RECOMMENDED_RT_WRITE_TIMESTEP={recommended_total_time:.12g}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(result, indent=2) + "\n")
    (out_path.with_suffix(".env")).write_text("\n".join(lines) + "\n")
    (out_path.parent / "pe_definition.json").write_text(
        json.dumps(result["pe_definition"], indent=2) + "\n"
    )

    for case_name, data in result["cases"].items():
        print(
            f"{case_name}: Pe={data['target_pe_check']:.6g}, "
            f"UD={data['target_darcy_velocity_m_per_s']:.6g} m/s, "
            f"Q={data['target_flow_rate_m3_per_s']:.6g} m3/s"
        )


if __name__ == "__main__":
    main()
