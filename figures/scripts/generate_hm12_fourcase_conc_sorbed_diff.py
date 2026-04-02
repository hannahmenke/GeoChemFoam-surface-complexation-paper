#!/usr/bin/env python3

from __future__ import annotations

import argparse
import re
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
from matplotlib.colors import TwoSlopeNorm


def parse_scalar_field(path: Path) -> np.ndarray:
    text = path.read_text()
    uniform_match = re.search(r"internalField\s+uniform\s+([^\n;]+)\s*;", text)
    if uniform_match:
        return np.array([float(uniform_match.group(1))], dtype=float)

    nonuniform_match = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not nonuniform_match:
        raise RuntimeError(f"Unsupported scalar field format in {path}")

    count = int(nonuniform_match.group(1))
    values = np.array([float(item) for item in nonuniform_match.group(2).split()], dtype=float)
    if values.size != count:
        raise RuntimeError(f"Value count mismatch in {path}: expected {count}, got {values.size}")
    return values


def parse_vector_field(path: Path) -> np.ndarray:
    text = path.read_text()
    nonuniform_match = re.search(
        r"internalField\s+nonuniform\s+List<vector>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not nonuniform_match:
        raise RuntimeError(f"Unsupported vector field format in {path}")

    count = int(nonuniform_match.group(1))
    vectors = re.findall(r"\(([^()]+)\)", nonuniform_match.group(2))
    values = np.array([[float(x) for x in vec.split()] for vec in vectors], dtype=float)
    if values.shape != (count, 3):
        raise RuntimeError(f"Vector count mismatch in {path}: expected {count}, got {values.shape}")
    return values


def parse_list_body(text: str, kind: str) -> tuple[int, str]:
    match = re.search(
        rf"class\s+{re.escape(kind)}.*?\n\s*(\d+)\s*\(\s*(.*?)\s*\)\s*\n\s*//",
        text,
        re.S,
    )
    if not match:
        raise RuntimeError(f"Unsupported {kind} format")
    return int(match.group(1)), match.group(2)


def parse_label_list(path: Path) -> np.ndarray:
    count, body = parse_list_body(path.read_text(), "labelList")
    values = np.array([int(item) for item in body.split()], dtype=int)
    if values.size != count:
        raise RuntimeError(f"Value count mismatch in {path}: expected {count}, got {values.size}")
    return values


def parse_points(path: Path) -> np.ndarray:
    count, body = parse_list_body(path.read_text(), "vectorField")
    vectors = re.findall(r"\(([^()]+)\)", body)
    values = np.array([[float(x) for x in vec.split()] for vec in vectors], dtype=float)
    if values.shape != (count, 3):
        raise RuntimeError(f"Point count mismatch in {path}: expected {count}, got {values.shape}")
    return values


def parse_faces(path: Path) -> list[np.ndarray]:
    count, body = parse_list_body(path.read_text(), "faceList")
    faces: list[np.ndarray] = []
    for face_match in re.finditer(r"(\d+)\(([^()]*)\)", body):
        face_size = int(face_match.group(1))
        face_pts = np.array([int(item) for item in face_match.group(2).split()], dtype=int)
        if face_pts.size != face_size:
            raise RuntimeError(f"Face size mismatch in {path}: expected {face_size}, got {face_pts.size}")
        faces.append(face_pts)
    if len(faces) != count:
        raise RuntimeError(f"Face count mismatch in {path}: expected {count}, got {len(faces)}")
    return faces


def parse_boundary_metadata(path: Path) -> dict[str, dict[str, int]]:
    text = path.read_text()
    metadata: dict[str, dict[str, int]] = {}
    for match in re.finditer(r"^\s*([A-Za-z0-9_]+)\s*\n\s*\{(.*?)^\s*\}", text, re.M | re.S):
        name = match.group(1)
        block = match.group(2)
        nfaces_match = re.search(r"nFaces\s+(\d+)\s*;", block)
        start_face_match = re.search(r"startFace\s+(\d+)\s*;", block)
        if nfaces_match and start_face_match:
            metadata[name] = {
                "nFaces": int(nfaces_match.group(1)),
                "startFace": int(start_face_match.group(1)),
            }
    return metadata


def parse_boundary_patch_values(path: Path, patch_name: str) -> np.ndarray:
    text = path.read_text()
    match = re.search(rf"^\s*{re.escape(patch_name)}\s*\n\s*\{{(.*?)^\s*\}}", text, re.M | re.S)
    if not match:
        return np.array([], dtype=float)
    block = match.group(1)
    uniform_match = re.search(r"value\s+uniform\s+([^\n;]+)\s*;", block)
    if uniform_match:
        return np.array([float(uniform_match.group(1))], dtype=float)
    nonuniform_match = re.search(
        r"value\s+nonuniform\s+List<scalar>\s*(\d+)\s*\(\s*(.*?)\s*\)\s*;",
        block,
        re.S,
    )
    if not nonuniform_match:
        return np.array([], dtype=float)
    count = int(nonuniform_match.group(1))
    body = nonuniform_match.group(2).strip()
    if count == 0:
        return np.array([], dtype=float)
    values = np.array([float(item) for item in body.split()], dtype=float)
    if values.size != count:
        raise RuntimeError(f"Boundary value count mismatch in {path} patch {patch_name}")
    return values


def local_partition_sizes(n_total: int, n_proc: int) -> tuple[list[int], list[int]]:
    base = n_total // n_proc
    rem = n_total % n_proc
    sizes = []
    starts = []
    start = 0
    for idx in range(n_proc):
        size = base + (1 if idx < rem else 0)
        sizes.append(size)
        starts.append(start)
        start += size
    return sizes, starts


def assemble_parallel_structured(case_dir: Path, time_name: str, field_name: str) -> np.ndarray:
    coarse_nx = int((case_dir / "system" / "Nx1").read_text().strip())
    coarse_ny = int((case_dir / "system" / "Ny1").read_text().strip())
    npx = int((case_dir / "system" / "NPX").read_text().strip())
    npy = int((case_dir / "system" / "NPY").read_text().strip())

    grid = np.zeros((coarse_ny, coarse_nx), dtype=float)
    x_sizes, x_starts = local_partition_sizes(coarse_nx, npx)
    y_sizes, y_starts = local_partition_sizes(coarse_ny, npy)

    for rank in range(npx * npy):
        ipy = rank // npx
        ipx = rank % npx
        field_path = case_dir / f"processor{rank}" / time_name / field_name
        values = parse_scalar_field(field_path)
        local = values.reshape((y_sizes[ipy], x_sizes[ipx]))
        ys = y_starts[ipy]
        ye = ys + y_sizes[ipy]
        xs = x_starts[ipx]
        xe = xs + x_sizes[ipx]
        grid[ys:ye, xs:xe] = local

    return grid


def gather_parallel_unstructured(case_dir: Path, time_name: str, field_name: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    xs: list[np.ndarray] = []
    ys: list[np.ndarray] = []
    vals: list[np.ndarray] = []

    for proc_dir in sorted(case_dir.glob("processor*")):
        field_path = proc_dir / time_name / field_name
        centers_path = proc_dir / time_name / "cellCenters"
        if not field_path.exists() or not centers_path.exists():
            continue
        field = parse_scalar_field(field_path)
        centers = parse_vector_field(centers_path)
        if field.size == 1:
            field = np.full(centers.shape[0], float(field[0]), dtype=float)
        xs.append(centers[:, 0])
        ys.append(centers[:, 1])
        vals.append(field)

    if not vals:
        raise RuntimeError(f"No unstructured parallel field found for {case_dir} {time_name} {field_name}")

    return np.concatenate(xs), np.concatenate(ys), np.concatenate(vals)


def points_to_grid(
    x: np.ndarray,
    y: np.ndarray,
    values: np.ndarray,
    nx: int,
    ny: int,
    res: float,
) -> np.ndarray:
    grid = np.full((ny, nx), np.nan, dtype=float)
    if values.size == 1:
        values = np.full(x.shape[0], float(values[0]), dtype=float)
    ix = np.rint(x / res - 0.5).astype(int)
    iy = np.rint(y / res - 0.5).astype(int)
    valid = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
    grid[iy[valid], ix[valid]] = values[valid]
    return grid


def boundary_patch_to_grid(
    case_dir: Path,
    time_name: str,
    field_name: str,
    nx: int,
    ny: int,
    res: float,
    patch_names: tuple[str, ...] = ("fixedWalls", "walls"),
) -> np.ndarray:
    sums = np.zeros((ny, nx), dtype=float)
    counts = np.zeros((ny, nx), dtype=float)

    for proc_dir in sorted(case_dir.glob("processor*")):
        field_path = proc_dir / time_name / field_name
        centers_path = proc_dir / time_name / "cellCenters"
        owner_path = proc_dir / "constant" / "polyMesh" / "owner"
        boundary_path = proc_dir / "constant" / "polyMesh" / "boundary"
        if not (field_path.exists() and centers_path.exists() and owner_path.exists() and boundary_path.exists()):
            continue

        centers = parse_vector_field(centers_path)
        owners = parse_label_list(owner_path)
        boundary_meta = parse_boundary_metadata(boundary_path)

        for patch_name in patch_names:
            if patch_name not in boundary_meta:
                continue
            values = parse_boundary_patch_values(field_path, patch_name)
            n_faces = boundary_meta[patch_name]["nFaces"]
            if n_faces == 0:
                continue
            if values.size == 1:
                values = np.full(n_faces, float(values[0]), dtype=float)
            if values.size != n_faces:
                raise RuntimeError(
                    f"Patch face count mismatch for {field_path} patch {patch_name}: "
                    f"expected {n_faces}, got {values.size}"
                )

            start_face = boundary_meta[patch_name]["startFace"]
            patch_owners = owners[start_face:start_face + n_faces]
            patch_centers = centers[patch_owners]
            ix = np.rint(patch_centers[:, 0] / res - 0.5).astype(int)
            iy = np.rint(patch_centers[:, 1] / res - 0.5).astype(int)
            valid = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
            for i, j, value in zip(ix[valid], iy[valid], values[valid], strict=False):
                sums[j, i] += value
                counts[j, i] += 1.0

    grid = np.full((ny, nx), np.nan, dtype=float)
    mask = counts > 0.0
    grid[mask] = sums[mask] / counts[mask]
    return grid


def add_scale_bar(ax, x_extent: float, y_extent: float, length_mm: float = 2.0) -> None:
    x0 = x_extent * 0.06
    y0 = y_extent * 0.06
    ax.plot([x0, x0 + length_mm], [y0, y0], color="white", lw=3, solid_capstyle="butt")
    ax.text(
        x0 + 0.5 * length_mm,
        y0 + 0.18,
        f"{length_mm:g} mm",
        color="white",
        ha="center",
        va="bottom",
        fontsize=8,
        bbox=dict(facecolor="black", alpha=0.35, edgecolor="none", pad=1.5),
    )


def masked_structured(field: np.ndarray, pore_mask: np.ndarray) -> np.ma.MaskedArray:
    return np.ma.masked_where(~pore_mask, field)


def masked_unstructured(field: np.ndarray, pore_mask: np.ndarray) -> np.ma.MaskedArray:
    filled = np.where(np.isfinite(field), field, 0.0)
    return np.ma.masked_where(~pore_mask, filled)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--legacy-snappy-case", required=True)
    parser.add_argument("--legacy-subset-case", required=True)
    parser.add_argument("--dbs-file-case", required=True)
    parser.add_argument("--dbs-fallback-case", required=True)
    parser.add_argument("--time", default="200")
    parser.add_argument("--cin", type=float, default=1e-4)
    parser.add_argument("--nx", type=int, default=600)
    parser.add_argument("--ny", type=int, default=600)
    parser.add_argument("--res", type=float, default=3e-5)
    parser.add_argument("--output-png", required=True)
    args = parser.parse_args()

    time_name = args.time
    res_mm = args.res * 1e3
    x_extent = args.nx * res_mm
    y_extent = args.ny * res_mm

    legacy_snappy_case = Path(args.legacy_snappy_case)
    legacy_subset_case = Path(args.legacy_subset_case)
    dbs_file_case = Path(args.dbs_file_case)
    dbs_fallback_case = Path(args.dbs_fallback_case)

    theta = assemble_parallel_structured(dbs_file_case, "0", "theta")
    pore_mask = theta > 0.5

    dbs_file_sr = assemble_parallel_structured(dbs_file_case, time_name, "Sr+2") / args.cin
    dbs_fallback_sr = assemble_parallel_structured(dbs_fallback_case, time_name, "Sr+2") / args.cin
    dbs_file_sorbed = assemble_parallel_structured(dbs_file_case, time_name, "Surf_aSr+")
    dbs_fallback_sorbed = assemble_parallel_structured(dbs_fallback_case, time_name, "Surf_aSr+")

    snappy_x, snappy_y, snappy_sr_vals = gather_parallel_unstructured(legacy_snappy_case, time_name, "Sr+2")
    snappy_sr = points_to_grid(snappy_x, snappy_y, snappy_sr_vals / args.cin, args.nx, args.ny, args.res)
    snappy_pore_mask = np.isfinite(snappy_sr)
    snappy_sorbed = boundary_patch_to_grid(
        legacy_snappy_case,
        time_name,
        "Surf_aSr+",
        args.nx,
        args.ny,
        args.res,
    )

    subset_x, subset_y, subset_sr_vals = gather_parallel_unstructured(legacy_subset_case, time_name, "Sr+2")
    subset_sr = points_to_grid(subset_x, subset_y, subset_sr_vals / args.cin, args.nx, args.ny, args.res)
    subset_pore_mask = np.isfinite(subset_sr)
    subset_sorbed = boundary_patch_to_grid(
        legacy_subset_case,
        time_name,
        "Surf_aSr+",
        args.nx,
        args.ny,
        args.res,
    )

    sr_fields = [
        np.ma.masked_invalid(snappy_sr),
        np.ma.masked_invalid(subset_sr),
        masked_structured(dbs_file_sr, pore_mask),
        masked_structured(dbs_fallback_sr, pore_mask),
    ]
    sorbed_fields = [
        masked_unstructured(snappy_sorbed, snappy_pore_mask),
        masked_unstructured(subset_sorbed, subset_pore_mask),
        masked_structured(dbs_file_sorbed, pore_mask),
        masked_structured(dbs_fallback_sorbed, pore_mask),
    ]
    diff_fields = [
        np.ma.masked_invalid(snappy_sr - dbs_file_sr),
        np.ma.masked_invalid(subset_sr - dbs_file_sr),
        masked_structured(np.zeros_like(dbs_file_sr), pore_mask),
        masked_structured(dbs_fallback_sr - dbs_file_sr, pore_mask),
    ]
    sorbed_diff_fields = [
        masked_unstructured(snappy_sorbed - dbs_file_sorbed, snappy_pore_mask),
        masked_unstructured(subset_sorbed - dbs_file_sorbed, subset_pore_mask),
        masked_structured(np.zeros_like(dbs_file_sorbed), pore_mask),
        masked_structured(dbs_fallback_sorbed - dbs_file_sorbed, pore_mask),
    ]

    sr_titles = ["Legacy snappy", "Legacy subsetMesh", "DBS file", "DBS fallback"]
    row_titles = [
        "Aqueous Sr/C_in",
        "Sorbed Surf_aSr+",
        "Δ(Sr/C_in) vs DBS-file",
        "Δ(Surf_aSr+) vs DBS-file",
    ]

    sr_vmin = 0.0
    sr_vmax = max(float(np.nanmax(np.ma.filled(field, np.nan))) for field in sr_fields)
    sorbed_vmin = 0.0
    sorbed_vmax = max(float(np.nanmax(np.ma.filled(field, np.nan))) for field in sorbed_fields)
    diff_abs = max(float(np.nanmax(np.abs(np.ma.filled(field, np.nan)))) for field in diff_fields)
    diff_norm = TwoSlopeNorm(vmin=-diff_abs, vcenter=0.0, vmax=diff_abs)
    sorbed_diff_abs = max(float(np.nanmax(np.abs(np.ma.filled(field, np.nan)))) for field in sorbed_diff_fields)
    sorbed_diff_norm = TwoSlopeNorm(vmin=-sorbed_diff_abs, vcenter=0.0, vmax=sorbed_diff_abs)

    sr_cmap = plt.get_cmap("viridis").copy()
    sr_cmap.set_bad(color="#d9d9d9")
    sorbed_cmap = plt.get_cmap("magma").copy()
    sorbed_cmap.set_bad(color="black")
    diff_cmap = plt.get_cmap("RdBu_r").copy()
    diff_cmap.set_bad(color="#d9d9d9")

    fig, axes = plt.subplots(4, 4, figsize=(17.5, 16.0), constrained_layout=True)

    im_sr = None
    im_sorbed = None
    im_diff = None
    im_sorbed_diff = None
    for col, title in enumerate(sr_titles):
        for row in range(4):
            ax = axes[row, col]
            if row == 0:
                im_sr = ax.imshow(
                    sr_fields[col],
                    origin="lower",
                    extent=(0.0, x_extent, 0.0, y_extent),
                    cmap=sr_cmap,
                    vmin=sr_vmin,
                    vmax=sr_vmax,
                    interpolation="nearest",
                    aspect="equal",
                )
            elif row == 1:
                im_sorbed = ax.imshow(
                    sorbed_fields[col],
                    origin="lower",
                    extent=(0.0, x_extent, 0.0, y_extent),
                    cmap=sorbed_cmap,
                    vmin=sorbed_vmin,
                    vmax=sorbed_vmax,
                    interpolation="nearest",
                    aspect="equal",
                )
            elif row == 2:
                im_diff = ax.imshow(
                    diff_fields[col],
                    origin="lower",
                    extent=(0.0, x_extent, 0.0, y_extent),
                    cmap=diff_cmap,
                    norm=diff_norm,
                    interpolation="nearest",
                    aspect="equal",
                )
            else:
                im_sorbed_diff = ax.imshow(
                    sorbed_diff_fields[col],
                    origin="lower",
                    extent=(0.0, x_extent, 0.0, y_extent),
                    cmap=diff_cmap,
                    norm=sorbed_diff_norm,
                    interpolation="nearest",
                    aspect="equal",
                )

            ax.set_xlim(0.0, x_extent)
            ax.set_ylim(0.0, y_extent)
            ax.set_xlabel("x [mm]")
            ax.set_ylabel("y [mm]")
            add_scale_bar(ax, x_extent, y_extent)
            if row == 0:
                ax.set_title(title)
            if col == 0:
                ax.text(
                    -0.16,
                    0.5,
                    row_titles[row],
                    transform=ax.transAxes,
                    rotation=90,
                    ha="center",
                    va="center",
                    fontsize=11,
                )

    cbar_sr = fig.colorbar(im_sr, ax=axes[0, :], location="right", shrink=0.9, pad=0.02)
    cbar_sr.set_label("Sr/C_in")
    cbar_sorbed = fig.colorbar(im_sorbed, ax=axes[1, :], location="right", shrink=0.9, pad=0.02)
    cbar_sorbed.set_label("Surf_aSr+")
    cbar_diff = fig.colorbar(im_diff, ax=axes[2, :], location="right", shrink=0.9, pad=0.02)
    cbar_diff.set_label("Δ(Sr/C_in)")
    cbar_sorbed_diff = fig.colorbar(im_sorbed_diff, ax=axes[3, :], location="right", shrink=0.9, pad=0.02)
    cbar_sorbed_diff.set_label("Δ(Surf_aSr+)")

    output_png = Path(args.output_png)
    output_png.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(output_png, dpi=220)
    plt.close(fig)


if __name__ == "__main__":
    main()
