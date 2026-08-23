from __future__ import annotations

import math
import os
import re
import sys
import tarfile
import time
from pathlib import Path

import numpy as np

from createASurfMarchingCubes import (
    build_reconstruction_field,
    contours_for_pair,
    marching_cubes_for_pair,
    parse_intrinsic_specs,
    parse_pair_specs,
    sanitize_component_name,
    SUPPORT_REDISTRIBUTED_2D_MODES,
)


def read_label_list(path: Path) -> list[int]:
    text = path.read_text()
    match = re.search(r"\n\s*(\d+)\s*\((.*?)\)\s*// \*", text, re.S)
    if not match:
        raise RuntimeError(f"Expected label list in {path}")
    count = int(match.group(1))
    values = [int(x) for x in match.group(2).split()]
    if len(values) != count:
        raise RuntimeError(f"Label count mismatch in {path}")
    return values


def replace_object(text: str, name: str) -> str:
    return re.sub(r"object\s+\S+;", f"object      {name};", text, count=1)


def replace_dimensions(text: str, dims: str) -> str:
    return re.sub(r"dimensions\s+\[[^\]]+\];", f"dimensions      {dims};", text, count=1)


def replace_internal_nonuniform(text: str, values: list[float]) -> str:
    block = (
        "internalField   nonuniform List<scalar>\n"
        f"{len(values)}\n"
        "(\n"
        + "\n".join(f"{value:.12g}" for value in values)
        + "\n)\n;\n"
    )
    updated, count = re.subn(
        r"internalField\s+nonuniform\s+List<scalar>\s*\d+\s*\((.*?)\)\s*;",
        block,
        text,
        count=1,
        flags=re.S,
    )
    if count != 1:
        raise RuntimeError("Failed to replace nonuniform internalField block")
    return updated


def write_local_field(template_path: Path, out_path: Path, field_name: str, values: np.ndarray) -> None:
    text = template_path.read_text()
    text = replace_object(text, field_name)
    text = replace_dimensions(text, "[0 -1 0 0 0 0 0]")
    text = replace_internal_nonuniform(text, values.reshape(-1).tolist())
    out_path.write_text(text)


def global_id_to_ijk(global_cell: int, nx: int, ny: int) -> tuple[int, int, int]:
    i = global_cell % nx
    j = (global_cell // nx) % ny
    k = global_cell // (nx * ny)
    return i, j, k


def load_raw_subvolume(
    x_dim: int,
    y_dim: int,
    z_dim: int,
    abs_x0: int,
    abs_x1: int,
    abs_y0: int,
    abs_y1: int,
    abs_z0: int,
    abs_z1: int,
    image_name: str,
) -> np.ndarray:
    raw_path = Path("constant") / "triSurface" / f"{image_name}.raw"
    archive_path = Path("constant") / "triSurface" / f"{image_name}.raw.tar.gz"

    if raw_path.exists():
        data = np.memmap(raw_path, dtype=np.uint8, mode="r", shape=(z_dim, y_dim, x_dim))
        return np.asarray(data[abs_z0:abs_z1, abs_y0:abs_y1, abs_x0:abs_x1])

    if archive_path.exists():
        with tarfile.open(archive_path, "r:gz") as archive:
            member = archive.getmember(f"{image_name}.raw")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise RuntimeError(f"Unable to extract {image_name}.raw from {archive_path}")
            image = np.frombuffer(extracted.read(), dtype=np.uint8)
        image = image.reshape((z_dim, y_dim, x_dim))
        return image[abs_z0:abs_z1, abs_y0:abs_y1, abs_x0:abs_x1]

    gcfoam_img = os.environ.get("GCFOAM_IMG")
    if gcfoam_img:
        fallback = Path(gcfoam_img) / f"{image_name}.raw"
        if fallback.exists():
            data = np.memmap(fallback, dtype=np.uint8, mode="r", shape=(z_dim, y_dim, x_dim))
            return np.asarray(data[abs_z0:abs_z1, abs_y0:abs_y1, abs_x0:abs_x1])

    raise FileNotFoundError(raw_path)


def local_default_process_count(nfaces: int) -> int:
    requested = os.environ.get("GCFOAM_ASURF_MC_PROCS")
    if requested:
        return max(1, int(requested))
    return 1


def point_to_fine_index(point: np.ndarray, image_shape: tuple[int, int, int], res: float) -> tuple[int, int, int]:
    k = int(np.clip(np.floor(point[0] / res), 0, image_shape[0] - 1))
    j = int(np.clip(np.floor(point[1] / res), 0, image_shape[1] - 1))
    i = int(np.clip(np.floor(point[2] / res), 0, image_shape[2] - 1))
    return k, j, i


def is_owner_at(point: np.ndarray, image: np.ndarray, owner_label: int, res: float) -> bool:
    k, j, i = point_to_fine_index(point, image.shape, res)
    return image[k, j, i] == owner_label


def choose_owner_point(centroid: np.ndarray, unit_normal: np.ndarray, image: np.ndarray, owner_label: int, res: float) -> np.ndarray:
    # Gaussian smoothing can move the reconstructed interface well inside the
    # non-owner phase. Search far enough to recover the pore-side owner cell.
    for epsilon_vox in (0.2, 0.4, 0.6, 0.8, 1.0, 1.25, 1.5, 2.0, 2.5, 3.0):
        epsilon = epsilon_vox * res
        plus = centroid + epsilon * unit_normal
        minus = centroid - epsilon * unit_normal
        plus_owner = is_owner_at(plus, image, owner_label, res)
        minus_owner = is_owner_at(minus, image, owner_label, res)

        if plus_owner and not minus_owner:
            return plus
        if minus_owner and not plus_owner:
            return minus
        if plus_owner:
            return plus
        if minus_owner:
            return minus

    k0, j0, i0 = point_to_fine_index(centroid, image.shape, res)
    for radius in range(1, 5):
        k1, k2 = max(0, k0 - radius), min(image.shape[0], k0 + radius + 1)
        j1, j2 = max(0, j0 - radius), min(image.shape[1], j0 + radius + 1)
        i1, i2 = max(0, i0 - radius), min(image.shape[2], i0 + radius + 1)
        owners = np.argwhere(image[k1:k2, j1:j2, i1:i2] == owner_label)
        if owners.size:
            owners += np.array([k1, j1, i1])
            centres = (owners.astype(np.float64) + 0.5) * res
            return centres[np.argmin(np.sum((centres - centroid) ** 2, axis=1))]
    return centroid


def block_reduce_intrinsic(
    image: np.ndarray,
    label: int,
    density: float,
    owned_bounds: tuple[int, int, int, int, int, int],
    block_shape: tuple[int, int, int],
) -> np.ndarray:
    min_i, max_i, min_j, max_j, min_k, max_k = owned_bounds
    p, q, r = block_shape
    field = np.zeros((max_k - min_k + 1, max_j - min_j + 1, max_i - min_i + 1), dtype=np.float64)
    block_cells = p * q * r
    for lk, gk in enumerate(range(min_k, max_k + 1)):
        z0 = gk * r
        z1 = z0 + r
        for lj, gj in enumerate(range(min_j, max_j + 1)):
            y0 = gj * q
            y1 = y0 + q
            for li, gi in enumerate(range(min_i, max_i + 1)):
                x0 = gi * p
                x1 = x0 + p
                count = np.count_nonzero(image[z0:z1, y0:y1, x0:x1] == label)
                field[lk, lj, li] = density * count / block_cells
    return field


def accumulate_pair_local(
    verts: np.ndarray,
    faces: np.ndarray,
    image: np.ndarray,
    owner_label: int,
    res: float,
    block_shape: tuple[int, int, int],
    local_origin_vox: tuple[int, int, int],
    owned_bounds: tuple[int, int, int, int, int, int],
    global_mesh_dims: tuple[int, int, int],
) -> np.ndarray:
    min_i, max_i, min_j, max_j, min_k, max_k = owned_bounds
    n_x, n_y, n_z = global_mesh_dims
    p, q, r = block_shape
    field = np.zeros((max_k - min_k + 1, max_j - min_j + 1, max_i - min_i + 1), dtype=np.float64)
    cell_vol = p * q * r * (res ** 3)

    origin_phys = np.array(
        [local_origin_vox[2] * res, local_origin_vox[1] * res, local_origin_vox[0] * res],
        dtype=np.float64,
    )

    for face in faces:
        tri = verts[np.asarray(face, dtype=int)]
        edge1 = tri[1] - tri[0]
        edge2 = tri[2] - tri[0]
        normal = np.cross(edge1, edge2)
        norm = np.linalg.norm(normal)
        if norm == 0.0:
            continue

        centroid = tri.mean(axis=0)
        owner_point_local = choose_owner_point(centroid, normal / norm, image, owner_label, res)
        owner_point_global = owner_point_local + origin_phys

        gk = int(np.clip(np.floor(owner_point_global[0] / (r * res)), 0, n_z - 1))
        gj = int(np.clip(np.floor(owner_point_global[1] / (q * res)), 0, n_y - 1))
        gi = int(np.clip(np.floor(owner_point_global[2] / (p * res)), 0, n_x - 1))

        if not (min_i <= gi <= max_i and min_j <= gj <= max_j and min_k <= gk <= max_k):
            continue

        field[gk - min_k, gj - min_j, gi - min_i] += 0.5 * norm / cell_vol

    return field


def first_shell_support_mask_2d(owner_mask: np.ndarray, other_mask: np.ndarray) -> np.ndarray:
    owner_2d = np.any(owner_mask, axis=0)
    other_2d = np.any(other_mask, axis=0)

    support = np.zeros_like(owner_2d, dtype=bool)
    support[:-1, :] |= owner_2d[:-1, :] & other_2d[1:, :]
    support[1:, :] |= owner_2d[1:, :] & other_2d[:-1, :]
    support[:, :-1] |= owner_2d[:, :-1] & other_2d[:, 1:]
    support[:, 1:] |= owner_2d[:, 1:] & other_2d[:, :-1]
    return support


def first_shell_support_weights_2d(owner_mask: np.ndarray, other_mask: np.ndarray) -> np.ndarray:
    owner_2d = np.any(owner_mask, axis=0)
    other_2d = np.any(other_mask, axis=0)

    weights = np.zeros_like(owner_2d, dtype=np.float64)
    weights[:-1, :] += owner_2d[:-1, :] & other_2d[1:, :]
    weights[1:, :] += owner_2d[1:, :] & other_2d[:-1, :]
    weights[:, :-1] += owner_2d[:, :-1] & other_2d[:, 1:]
    weights[:, 1:] += owner_2d[:, 1:] & other_2d[:, :-1]
    return weights


def coarse_support_mask_2d(
    support_mask_2d: np.ndarray,
    local_origin_vox: tuple[int, int, int],
    block_shape: tuple[int, int, int],
    global_mesh_dims: tuple[int, int, int],
) -> np.ndarray:
    p, q, _ = block_shape
    n_x, n_y, _ = global_mesh_dims
    coarse = np.zeros((n_y, n_x), dtype=bool)
    local_x0, local_y0, _ = local_origin_vox
    ys, xs = np.nonzero(support_mask_2d)
    for y, x in zip(ys, xs):
        gj = int((local_y0 + y) // q)
        gi = int((local_x0 + x) // p)
        if 0 <= gj < n_y and 0 <= gi < n_x:
            coarse[gj, gi] = True
    return coarse


def coarse_support_weights_2d(
    support_weights_2d: np.ndarray,
    local_origin_vox: tuple[int, int, int],
    block_shape: tuple[int, int, int],
    global_mesh_dims: tuple[int, int, int],
) -> np.ndarray:
    p, q, _ = block_shape
    n_x, n_y, _ = global_mesh_dims
    coarse = np.zeros((n_y, n_x), dtype=np.float64)
    local_x0, local_y0, _ = local_origin_vox
    ys, xs = np.nonzero(support_weights_2d > 0.0)
    for y, x in zip(ys, xs):
        gj = int((local_y0 + y) // q)
        gi = int((local_x0 + x) // p)
        if 0 <= gj < n_y and 0 <= gi < n_x:
            coarse[gj, gi] += support_weights_2d[y, x]
    return coarse


def segment_split_t_values_2d(start: np.ndarray, end: np.ndarray, cell_height: float, cell_width: float) -> np.ndarray:
    segment = end - start
    seg_len = np.linalg.norm(segment)
    if seg_len == 0.0:
        return np.array([], dtype=np.float64)

    ts = [0.0, 1.0]
    dy = float(segment[0])
    dx = float(segment[1])
    tol = 1e-12

    if abs(dy) > tol:
        y_min = min(start[0], end[0])
        y_max = max(start[0], end[0])
        first_k = int(np.floor(y_min / cell_height)) + 1
        last_k = int(np.floor(y_max / cell_height))
        for k in range(first_k, last_k + 1):
            y_line = k * cell_height
            t = (y_line - start[0]) / dy
            if tol < t < 1.0 - tol:
                ts.append(float(t))

    if abs(dx) > tol:
        x_min = min(start[1], end[1])
        x_max = max(start[1], end[1])
        first_k = int(np.floor(x_min / cell_width)) + 1
        last_k = int(np.floor(x_max / cell_width))
        for k in range(first_k, last_k + 1):
            x_line = k * cell_width
            t = (x_line - start[1]) / dx
            if tol < t < 1.0 - tol:
                ts.append(float(t))

    return np.array(sorted(set(ts)), dtype=np.float64)


def nearest_supported_cell_2d(
    midpoint_global: np.ndarray,
    gj: int,
    gi: int,
    coarse_support: np.ndarray,
    cell_height: float,
    cell_width: float,
    search_radius: int = 2,
) -> tuple[int, int] | None:
    ny, nx = coarse_support.shape
    if 0 <= gj < ny and 0 <= gi < nx and coarse_support[gj, gi]:
        return gj, gi

    best = None
    best_dist2 = None
    for dj in range(-search_radius, search_radius + 1):
        for di in range(-search_radius, search_radius + 1):
            jj = gj + dj
            ii = gi + di
            if jj < 0 or jj >= ny or ii < 0 or ii >= nx or not coarse_support[jj, ii]:
                continue
            center = np.array([(jj + 0.5) * cell_height, (ii + 0.5) * cell_width], dtype=np.float64)
            dist2 = float(np.sum((center - midpoint_global) ** 2))
            if best_dist2 is None or dist2 < best_dist2:
                best_dist2 = dist2
                best = (jj, ii)
    return best


def point_segment_distance_2d(point: np.ndarray, start: np.ndarray, end: np.ndarray) -> float:
    segment = end - start
    denom = float(np.dot(segment, segment))
    if denom <= 0.0:
        return float(np.linalg.norm(point - start))
    t = float(np.clip(np.dot(point - start, segment) / denom, 0.0, 1.0))
    projection = start + t * segment
    return float(np.linalg.norm(point - projection))


def accumulate_pair_local_2d(
    contours: list[np.ndarray],
    owner_mask: np.ndarray,
    other_mask: np.ndarray,
    res: float,
    block_shape: tuple[int, int, int],
    local_origin_vox: tuple[int, int, int],
    owned_bounds: tuple[int, int, int, int, int, int],
    global_mesh_dims: tuple[int, int, int],
) -> np.ndarray:
    min_i, max_i, min_j, max_j, min_k, max_k = owned_bounds
    n_x, n_y, _ = global_mesh_dims
    p, q, r = block_shape
    field = np.zeros((max_k - min_k + 1, max_j - min_j + 1, max_i - min_i + 1), dtype=np.float64)
    cell_vol = p * q * r * (res ** 3)

    support_2d = first_shell_support_mask_2d(owner_mask, other_mask)
    coarse_support = coarse_support_mask_2d(
        support_2d,
        local_origin_vox,
        block_shape,
        global_mesh_dims,
    )
    thickness = owner_mask.shape[0] * res
    cell_height = q * res
    cell_width = p * res
    origin_global = np.array([local_origin_vox[1] * res, local_origin_vox[0] * res], dtype=np.float64)

    assigned_area = 0.0
    for contour in contours:
        if contour.shape[0] < 2:
            continue

        contour_phys = np.asarray(contour, dtype=np.float64)
        for start, end in zip(contour_phys[:-1], contour_phys[1:]):
            segment = end - start
            seg_len = np.linalg.norm(segment)
            if seg_len == 0.0:
                continue

            start_global = start + origin_global
            end_global = end + origin_global
            ts = segment_split_t_values_2d(start_global, end_global, cell_height, cell_width)
            for t0, t1 in zip(ts[:-1], ts[1:]):
                if t1 <= t0:
                    continue

                midpoint_global = start_global + 0.5 * (t0 + t1) * (end_global - start_global)
                piece_len = seg_len * (t1 - t0)
                gj = int(np.clip(np.floor(midpoint_global[0] / cell_height), 0, n_y - 1))
                gi = int(np.clip(np.floor(midpoint_global[1] / cell_width), 0, n_x - 1))
                target = nearest_supported_cell_2d(
                    midpoint_global,
                    gj,
                    gi,
                    coarse_support,
                    cell_height,
                    cell_width,
                )
                if target is None:
                    continue

                gj_t, gi_t = target
                if not (min_i <= gi_t <= max_i and min_j <= gj_t <= max_j and min_k <= 0 <= max_k):
                    continue

                field[0 - min_k, gj_t - min_j, gi_t - min_i] += (piece_len * thickness) / cell_vol
                assigned_area += piece_len * thickness

    deposited_area = float(field.sum() * cell_vol)
    if deposited_area > 0.0 and assigned_area > 0.0:
        field *= assigned_area / deposited_area

    return field


def accumulate_pair_local_2d_deposited(
    contours: list[np.ndarray],
    owner_mask: np.ndarray,
    other_mask: np.ndarray,
    res: float,
    block_shape: tuple[int, int, int],
    local_origin_vox: tuple[int, int, int],
    owned_bounds: tuple[int, int, int, int, int, int],
    global_mesh_dims: tuple[int, int, int],
    search_radius: int = 2,
    sigma_cells: float = 1.0,
    contact_power: float = 1.0,
) -> np.ndarray:
    min_i, max_i, min_j, max_j, min_k, max_k = owned_bounds
    n_x, n_y, _ = global_mesh_dims
    p, q, r = block_shape
    field = np.zeros((max_k - min_k + 1, max_j - min_j + 1, max_i - min_i + 1), dtype=np.float64)
    cell_vol = p * q * r * (res ** 3)

    support_weights = coarse_support_weights_2d(
        first_shell_support_weights_2d(owner_mask, other_mask),
        local_origin_vox,
        block_shape,
        global_mesh_dims,
    )
    support = support_weights > 0.0
    thickness = owner_mask.shape[0] * res
    cell_height = q * res
    cell_width = p * res
    sigma = max(float(sigma_cells) * res, 1e-30)
    origin_global = np.array([local_origin_vox[1] * res, local_origin_vox[0] * res], dtype=np.float64)

    for contour in contours:
        if contour.shape[0] < 2:
            continue

        contour_phys = np.asarray(contour, dtype=np.float64)
        for start, end in zip(contour_phys[:-1], contour_phys[1:]):
            segment = end - start
            seg_len = np.linalg.norm(segment)
            if seg_len == 0.0:
                continue

            start_global = start + origin_global
            end_global = end + origin_global
            ts = segment_split_t_values_2d(start_global, end_global, cell_height, cell_width)
            for t0, t1 in zip(ts[:-1], ts[1:]):
                if t1 <= t0:
                    continue

                piece_start = start_global + t0 * (end_global - start_global)
                piece_end = start_global + t1 * (end_global - start_global)
                midpoint = 0.5 * (piece_start + piece_end)
                piece_len = seg_len * (t1 - t0)
                gj = int(np.clip(np.floor(midpoint[0] / cell_height), 0, n_y - 1))
                gi = int(np.clip(np.floor(midpoint[1] / cell_width), 0, n_x - 1))

                candidates: list[tuple[int, int]] = []
                weights: list[float] = []
                for jj in range(max(0, gj - search_radius), min(n_y, gj + search_radius + 1)):
                    for ii in range(max(0, gi - search_radius), min(n_x, gi + search_radius + 1)):
                        if not support[jj, ii]:
                            continue
                        center = np.array([(jj + 0.5) * cell_height, (ii + 0.5) * cell_width], dtype=np.float64)
                        distance = point_segment_distance_2d(center, piece_start, piece_end)
                        weight = np.exp(-0.5 * (distance / sigma) ** 2)
                        weight *= support_weights[jj, ii] ** contact_power
                        if weight > 0.0:
                            candidates.append((jj, ii))
                            weights.append(float(weight))

                if not candidates:
                    continue

                weights_array = np.asarray(weights, dtype=np.float64)
                weights_array /= np.sum(weights_array)
                piece_area = piece_len * thickness
                for (gj_t, gi_t), weight in zip(candidates, weights_array):
                    if not (min_i <= gi_t <= max_i and min_j <= gj_t <= max_j and min_k <= 0 <= max_k):
                        continue
                    field[0 - min_k, gj_t - min_j, gi_t - min_i] += piece_area * weight / cell_vol

    return field


def redistribute_local_2d_field_to_support(
    field: np.ndarray,
    owner_mask: np.ndarray,
    other_mask: np.ndarray,
    block_shape: tuple[int, int, int],
    local_origin_vox: tuple[int, int, int],
    owned_bounds: tuple[int, int, int, int, int, int],
    global_mesh_dims: tuple[int, int, int],
) -> np.ndarray:
    min_i, max_i, min_j, max_j, min_k, max_k = owned_bounds
    support_weights = coarse_support_weights_2d(
        first_shell_support_weights_2d(owner_mask, other_mask),
        local_origin_vox,
        block_shape,
        global_mesh_dims,
    )

    redistributed = np.zeros_like(field)
    for gi in range(min_i, max_i + 1):
        local_i = gi - min_i
        total = float(np.sum(field[:, :, local_i]))
        weights = support_weights[min_j : max_j + 1, gi]
        weight_sum = float(np.sum(weights))
        if total > 0.0 and weight_sum > 0.0 and min_k <= 0 <= max_k:
            redistributed[0 - min_k, :, local_i] = weights * total / weight_sum
        else:
            redistributed[:, :, local_i] = field[:, :, local_i]

    return redistributed


def main() -> None:
    t0 = time.perf_counter()
    x_dim = int(sys.argv[1])
    y_dim = int(sys.argv[2])
    z_dim = int(sys.argv[3])
    x_min = int(sys.argv[4])
    x_max = int(sys.argv[5])
    y_min = int(sys.argv[6])
    y_max = int(sys.argv[7])
    z_min = int(sys.argv[8])
    z_max = int(sys.argv[9])
    n_x = int(sys.argv[10])
    n_y = int(sys.argv[11])
    n_z = int(sys.argv[12])
    res = float(sys.argv[13])
    image_name = sys.argv[14]
    pore_value = int(float(sys.argv[15]))
    solid_value = int(float(sys.argv[16]))
    dimension = sys.argv[17]
    field_name = sys.argv[18]
    surface_mode = sys.argv[19]
    smooth_sigma_vox = float(sys.argv[20])
    pair_specs_text = sys.argv[21]
    intrinsic_specs_text = sys.argv[22]
    write_components = sys.argv[23].lower() in {"1", "true", "yes", "on"}
    time_name = sys.argv[24]
    proc_index = int(sys.argv[25])
    template_field = sys.argv[26] if len(sys.argv) > 26 else "eps"
    check_only = sys.argv[27].lower() in {"1", "true", "yes", "on"} if len(sys.argv) > 27 else False

    p = int((x_max - x_min) / n_x)
    q = int((y_max - y_min) / n_y)
    r = int((z_max - z_min) / n_z)

    proc_root = Path(f"processor{proc_index}")
    cell_addressing = read_label_list(proc_root / "constant" / "polyMesh" / "cellProcAddressing")
    if not cell_addressing:
        raise RuntimeError(f"No cellProcAddressing entries for processor {proc_index}")

    coords = [global_id_to_ijk(global_cell, n_x, n_y) for global_cell in cell_addressing]
    is_ = [c[0] for c in coords]
    js_ = [c[1] for c in coords]
    ks_ = [c[2] for c in coords]
    min_i, max_i = min(is_), max(is_)
    min_j, max_j = min(js_), max(js_)
    min_k, max_k = min(ks_), max(ks_)

    expected = (max_i - min_i + 1) * (max_j - min_j + 1) * (max_k - min_k + 1)
    if expected != len(cell_addressing):
        raise RuntimeError(
            f"Processor {proc_index} is not a contiguous block-mapped subdomain: "
            f"bbox volume={expected}, cells={len(cell_addressing)}"
        )

    expected_ids = {
        i + n_x * (j + n_y * k)
        for k in range(min_k, max_k + 1)
        for j in range(min_j, max_j + 1)
        for i in range(min_i, max_i + 1)
    }
    if set(cell_addressing) != expected_ids:
        raise RuntimeError(
            f"Processor {proc_index} does not own a full rectangular block of coarse cells"
        )

    if surface_mode == "occupancyGaussian":
        halo = int(math.ceil(4.0 * smooth_sigma_vox)) + 1
    else:
        halo = 1

    local_x0 = max(0, min_i * p - halo)
    local_x1 = min(x_max - x_min, (max_i + 1) * p + halo)
    local_y0 = max(0, min_j * q - halo)
    local_y1 = min(y_max - y_min, (max_j + 1) * q + halo)
    local_z0 = max(0, min_k * r - halo)
    local_z1 = min(z_max - z_min, (max_k + 1) * r + halo)

    if check_only:
        tile_shape = (local_z1 - local_z0, local_y1 - local_y0, local_x1 - local_x0)
        print(
            f"Support check passed for processor{proc_index}: "
            f"owned_block=({min_i}:{max_i},{min_j}:{max_j},{min_k}:{max_k}) "
            f"block_shape=({p},{q},{r}) "
            f"tile_shape_vox={tile_shape} "
            f"halo_vox={halo}"
        )
        return

    image = load_raw_subvolume(
        x_dim,
        y_dim,
        z_dim,
        x_min + local_x0,
        x_min + local_x1,
        y_min + local_y0,
        y_min + local_y1,
        z_min + local_z0,
        z_min + local_z1,
        image_name,
    )

    pair_specs = parse_pair_specs(pair_specs_text, pore_value, solid_value)
    intrinsic_specs = parse_intrinsic_specs(intrinsic_specs_text)
    owned_bounds = (min_i, max_i, min_j, max_j, min_k, max_k)
    block_shape = (p, q, r)
    total_field = np.zeros((max_k - min_k + 1, max_j - min_j + 1, max_i - min_i + 1), dtype=np.float64)
    total_triangles = 0
    used_modes: list[str] = []

    for spec in pair_specs:
        owner_mask = image == spec["owner"]
        other_mask = image == spec["other"]
        pair_mask = owner_mask | other_mask
        if not np.any(owner_mask) or not np.any(other_mask):
            component = np.zeros_like(total_field)
            used_modes.append(f"{spec['name']}=none")
            ntris = 0
        else:
            if dimension == "2D":
                contours, used_mode = contours_for_pair(
                    owner_mask, pair_mask, res, surface_mode, smooth_sigma_vox
                )
                if surface_mode in SUPPORT_REDISTRIBUTED_2D_MODES:
                    component = accumulate_pair_local_2d_deposited(
                        contours,
                        owner_mask,
                        other_mask,
                        res,
                        block_shape,
                        (local_x0, local_y0, local_z0),
                        owned_bounds,
                        (n_x, n_y, n_z),
                    )
                else:
                    component = accumulate_pair_local_2d(
                        contours,
                        owner_mask,
                        other_mask,
                        res,
                        block_shape,
                        (local_x0, local_y0, local_z0),
                        owned_bounds,
                        (n_x, n_y, n_z),
                    )
                ntris = sum(max(0, contour.shape[0] - 1) for contour in contours)
            else:
                verts, faces, used_mode = marching_cubes_for_pair(
                    owner_mask, pair_mask, res, surface_mode, smooth_sigma_vox
                )
                component = accumulate_pair_local(
                    verts,
                    faces,
                    image,
                    spec["owner"],
                    res,
                    block_shape,
                    (local_x0, local_y0, local_z0),
                    owned_bounds,
                    (n_x, n_y, n_z),
                )
                ntris = faces.shape[0]
            used_modes.append(f"{spec['name']}={used_mode}")
        total_field += component
        total_triangles += ntris
        if write_components:
            write_local_field(
                proc_root / time_name / template_field,
                proc_root / time_name / sanitize_component_name(field_name, spec["name"]),
                sanitize_component_name(field_name, spec["name"]),
                component,
            )

    for spec in intrinsic_specs:
        component = block_reduce_intrinsic(
            image,
            spec["label"],
            spec["density"],
            owned_bounds,
            block_shape,
        )
        total_field += component
        if write_components:
            write_local_field(
                proc_root / time_name / template_field,
                proc_root / time_name / sanitize_component_name(field_name, f"intrinsic_{spec['name']}"),
                sanitize_component_name(field_name, f"intrinsic_{spec['name']}"),
                component,
            )

    write_local_field(
        proc_root / time_name / template_field,
        proc_root / time_name / field_name,
        field_name,
        total_field,
    )

    elapsed = time.perf_counter() - t0
    active_cells = int(np.count_nonzero(total_field > 0.0))
    tile_shape = (local_z1 - local_z0, local_y1 - local_y0, local_x1 - local_x0)

    print(
        f"Created local {field_name} for processor{proc_index}: "
        f"owned_block=({min_i}:{max_i},{min_j}:{max_j},{min_k}:{max_k}) "
        f"block_shape=({p},{q},{r}) "
        f"tile_shape_vox={tile_shape} "
        f"halo_vox={halo} "
        f"used_modes={','.join(used_modes) if used_modes else 'none'} "
        f"triangles={total_triangles} "
        f"active_cells={active_cells} "
        f"sum(aSurf*V)={total_field.sum() * p * q * r * (res ** 3):.16e} "
        f"procs={local_default_process_count(total_triangles)} "
        f"elapsed_s={elapsed:.6f}"
    )


if __name__ == "__main__":
    main()
