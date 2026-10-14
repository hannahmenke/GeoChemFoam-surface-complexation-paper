#!/usr/bin/env python3
from __future__ import annotations

import json
import math
import os
import re
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np


CASES = [
    {
        "label": "Pe 1",
        "job": "13528073",
        "case_dir": Path(os.environ.get("RESOLVED_CASES_ROOT", "results/archer"))
        / "two_scale_resolved-reference_pe_1_13528073/resolved-reference",
    },
    {
        "label": "Pe 0.3",
        "job": "13528075",
        "case_dir": Path(os.environ.get("RESOLVED_CASES_ROOT", "results/archer"))
        / "two_scale_resolved-reference_pe_0.3_13528075/resolved-reference",
    },
    {
        "label": "Pe 0.1",
        "job": "13528074",
        "case_dir": Path(os.environ.get("RESOLVED_CASES_ROOT", "results/archer"))
        / "two_scale_resolved-reference_pe_0.1_13528074/resolved-reference",
    },
]

FIELDS = ["Li+", "Na+", "Cl-", "Sor_aLi"]
NX = 18000
NY = 6000
LENGTH_MM = 18.0


def read_int(path: Path) -> int:
    return int(path.read_text().strip())


def latest_time(case_dir: Path) -> str:
    proc0 = case_dir / "processor0"
    candidates: list[tuple[float, str]] = []
    for child in proc0.iterdir():
        if not child.is_dir():
            continue
        try:
            value = float(child.name)
        except ValueError:
            continue
        if value > 0 and any((child / field).exists() for field in FIELDS):
            candidates.append((value, child.name))
    if not candidates:
        raise FileNotFoundError(f"No saved field timestep found under {proc0}")
    return max(candidates)[1]


def local_extent(global_n: int, parts: int, index: int) -> tuple[int, int]:
    base = global_n // parts
    rem = global_n % parts
    if index < rem:
        size = base + 1
        start = index * size
    else:
        size = base
        start = rem * (base + 1) + (index - rem) * base
    return start, size


def read_internal_scalar(path: Path, expected_count: int) -> np.ndarray:
    text = path.read_text()
    match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s+(\d+)\s*\(\s*(.*?)\s*\)\s*;",
        text,
        flags=re.S,
    )
    if not match:
        uniform = re.search(r"internalField\s+uniform\s+([0-9.eE+-]+)", text)
        if uniform:
            return np.full(expected_count, float(uniform.group(1)))
        raise ValueError(f"Could not parse nonuniform scalar field: {path}")
    count = int(match.group(1))
    data = np.fromstring(match.group(2), sep=" ", dtype=float)
    if data.size != count:
        raise ValueError(f"{path}: expected {count} values, got {data.size}")
    return data


def profile(case_dir: Path, time_name: str, field: str) -> tuple[np.ndarray, np.ndarray]:
    npx = read_int(case_dir / "system" / "NPX")
    npy = read_int(case_dir / "system" / "NPY")
    global_y = NY // 2
    ipy = None
    y_start = nyp = None
    for candidate in range(npy):
        candidate_start, candidate_size = local_extent(NY, npy, candidate)
        if candidate_start <= global_y < candidate_start + candidate_size:
            ipy = candidate
            y_start = candidate_start
            nyp = candidate_size
            break
    if ipy is None or y_start is None or nyp is None:
        raise RuntimeError(f"could not locate global middle row {global_y} in {npy} y partitions")
    local_y = global_y - y_start
    if local_y < 0 or local_y >= nyp:
        raise RuntimeError(f"middle row mapping failed for {case_dir}: ipy={ipy}, local_y={local_y}")

    xs: list[np.ndarray] = []
    vals: list[np.ndarray] = []
    for ipx in range(npx):
        x_start, nxp = local_extent(NX, npx, ipx)
        rank = ipy * npx + ipx
        values = read_internal_scalar(
            case_dir / f"processor{rank}" / time_name / field,
            expected_count=nxp * nyp,
        )
        if values.size != nxp * nyp:
            raise ValueError(
                f"processor{rank} {field}: expected {nxp*nyp} values, got {values.size}"
            )
        row = values.reshape((nyp, nxp))[local_y, :]
        xs.append((np.arange(x_start, x_start + nxp) + 0.5) * LENGTH_MM / NX)
        vals.append(row)
    return np.concatenate(xs), np.concatenate(vals)


def main() -> None:
    out_dir = Path("results/quick_plots")
    out_dir.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(len(FIELDS), 1, figsize=(11, 10), sharex=True)
    summary = []

    colors = ["#1b6ca8", "#d95f02", "#1b9e77"]
    for case_index, case in enumerate(CASES):
        case_dir = case["case_dir"]
        time_name = latest_time(case_dir)
        item = {
            "label": case["label"],
            "job": case["job"],
            "case_dir": str(case_dir),
            "latest_time": time_name,
            "fields": {},
        }
        for ax, field in zip(axes, FIELDS):
            x, y = profile(case_dir, time_name, field)
            ax.plot(x, y, lw=1.2, color=colors[case_index], label=f"{case['label']} t={time_name}")
            item["fields"][field] = {
                "min": float(np.nanmin(y)),
                "max": float(np.nanmax(y)),
                "mean": float(np.nanmean(y)),
            }
        summary.append(item)

    for ax, field in zip(axes, FIELDS):
        ax.set_ylabel(field)
        ax.grid(True, alpha=0.25)
        if field in {"Li+", "Sor_aLi"}:
            ax.ticklabel_format(axis="y", style="sci", scilimits=(-2, 2))
    axes[0].legend(loc="best", fontsize=8)
    axes[-1].set_xlabel("x position along resolved domain (mm), middle row")
    fig.suptitle("Resolved-reference latest saved middle-row profiles")
    fig.tight_layout(rect=(0, 0, 1, 0.97))

    png = out_dir / "resolved_latest_middle_row_profiles.png"
    json_path = out_dir / "resolved_latest_middle_row_profiles_summary.json"
    fig.savefig(png, dpi=180)
    json_path.write_text(json.dumps(summary, indent=2) + "\n")
    print(png)
    print(json_path)


if __name__ == "__main__":
    main()
