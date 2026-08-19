import multiprocessing as mp
import os
import sys
import tarfile

import numpy as np
from scipy.ndimage import distance_transform_edt, gaussian_filter
from skimage.measure import find_contours, marching_cubes


SUPPORT_REDISTRIBUTED_2D_MODES = {"occupancyGaussian"}


_WORKER_VERTS = None
_WORKER_FACES = None
_WORKER_IMAGE = None
_WORKER_NX = None
_WORKER_NY = None
_WORKER_NZ = None
_WORKER_P = None
_WORKER_Q = None
_WORKER_R = None
_WORKER_RES = None
_WORKER_CELL_VOL = None
_WORKER_OWNER_LABEL = None


def load_raw_image(
    x_dim,
    y_dim,
    z_dim,
    x_min,
    x_max,
    y_min,
    y_max,
    z_min,
    z_max,
    image_name,
):
    raw_path = os.path.join("constant", "triSurface", image_name + ".raw")
    archive_path = os.path.join("constant", "triSurface", image_name + ".raw.tar.gz")
    if not os.path.exists(raw_path):
        gcfoam_img = os.environ.get("GCFOAM_IMG")
        if gcfoam_img:
            raw_candidates = (
                os.path.join(gcfoam_img, image_name + ".raw"),
                os.path.join(gcfoam_img, "raw", image_name + ".raw"),
            )
            archive_candidates = (
                os.path.join(gcfoam_img, image_name + ".raw.tar.gz"),
                os.path.join(gcfoam_img, "raw", image_name + ".raw.tar.gz"),
            )
            for fallback in raw_candidates:
                if os.path.exists(fallback):
                    raw_path = fallback
                    break
            for fallback in archive_candidates:
                if os.path.exists(fallback):
                    archive_path = fallback
                    break

    if os.path.exists(raw_path):
        image = np.fromfile(raw_path, dtype=np.uint8)
    elif os.path.exists(archive_path):
        with tarfile.open(archive_path, "r:gz") as archive:
            member = archive.getmember(image_name + ".raw")
            extracted = archive.extractfile(member)
            if extracted is None:
                raise ValueError(f"Unable to extract {image_name}.raw from {archive_path}")
            image = np.frombuffer(extracted.read(), dtype=np.uint8)
    else:
        raise FileNotFoundError(raw_path)

    expected = x_dim * y_dim * z_dim
    if image.size != expected:
        raise ValueError(f"Unexpected raw image size: {image.size} != {expected}")

    image = image.reshape((z_dim, y_dim, x_dim))
    return image[z_min:z_max, y_min:y_max, x_min:x_max]


def write_field(field, field_name, dimension, output_location="0"):
    nz1, ny1, nx1 = field.shape
    ncells = nx1 * ny1 * nz1

    os.makedirs(output_location, exist_ok=True)

    data = [
        "/*--------------------------------*- C++ -*----------------------------------*\\\n",
        "| =========                 |                                                 |\n",
        "| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |\n",
        "|  \\\\    /   O peration     | Version:  2212                                  |\n",
        "|   \\\\  /    A nd           | Website:  www.openfoam.com                      |\n",
        "|    \\\\/     M anipulation  |                                                 |\n",
        "\\*---------------------------------------------------------------------------*/\n",
        "FoamFile\n",
        "{\n",
        "    version     2.0;\n",
        "    format      ascii;\n",
        "    arch        \"LSB;label=32;scalar=64\";\n",
        "    class       volScalarField;\n",
        f"    location    \"{output_location}\";\n",
        f"    object      {field_name};\n",
        "}\n",
        "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n",
        "\n",
        "dimensions      [0 -1 0 0 0 0 0];\n",
        "\n",
        "internalField   nonuniform List<scalar> \n",
        f"{ncells}\n",
        "(\n",
    ]

    for k in range(nz1):
        for j in range(ny1):
            for i in range(nx1):
                value = format(field[k, j, i], ".12g")
                data.append(f"{value}\n")

    data.extend(
        [
            ")\n",
            ";\n",
            "\n",
            "boundaryField\n",
            "{\n",
            "    inlet\n",
            "    {\n",
            "        type            zeroGradient;\n",
            "    }\n",
            "    outlet\n",
            "    {\n",
            "        type            zeroGradient;\n",
            "    }\n",
            "    \"wall_.*\"\n",
            "    {\n",
            "        type            zeroGradient;\n",
            "    }\n",
        ]
    )

    if dimension == "2D":
        data.extend(
            [
                "    frontAndBack\n",
                "    {\n",
                "        type            empty;\n",
                "    }\n",
            ]
        )

    data.extend(["}\n", "\n", "// ************************************************************************* //\n"])

    with open(os.path.join(output_location, field_name), "w") as handle:
        handle.writelines(data)


def default_process_count(nfaces):
    requested = os.environ.get("GCFOAM_ASURF_MC_PROCS")
    if requested:
        nprocs = int(requested)
    else:
        nprocs = min(8, os.cpu_count() or 1)
    if nfaces < 10000:
        return 1
    return max(1, min(nprocs, nfaces))


def point_to_fine_index(point):
    k = int(np.clip(np.floor(point[0] / _WORKER_RES), 0, _WORKER_IMAGE.shape[0] - 1))
    j = int(np.clip(np.floor(point[1] / _WORKER_RES), 0, _WORKER_IMAGE.shape[1] - 1))
    i = int(np.clip(np.floor(point[2] / _WORKER_RES), 0, _WORKER_IMAGE.shape[2] - 1))
    return k, j, i


def is_owner_at(point):
    k, j, i = point_to_fine_index(point)
    return _WORKER_IMAGE[k, j, i] == _WORKER_OWNER_LABEL


def choose_owner_point(centroid, unit_normal):
    epsilon = 0.25 * _WORKER_RES
    plus = centroid + epsilon * unit_normal
    minus = centroid - epsilon * unit_normal
    plus_owner = is_owner_at(plus)
    minus_owner = is_owner_at(minus)

    if plus_owner and not minus_owner:
        return plus
    if minus_owner and not plus_owner:
        return minus
    if plus_owner:
        return plus
    if minus_owner:
        return minus
    return centroid


def point_to_coarse_index(point):
    k = int(np.clip(np.floor(point[0] / (_WORKER_R * _WORKER_RES)), 0, _WORKER_NZ - 1))
    j = int(np.clip(np.floor(point[1] / (_WORKER_Q * _WORKER_RES)), 0, _WORKER_NY - 1))
    i = int(np.clip(np.floor(point[2] / (_WORKER_P * _WORKER_RES)), 0, _WORKER_NX - 1))
    return k, j, i


def _init_worker(verts, faces, image, nx, ny, nz, p, q, r, res, cell_vol, owner_label):
    global _WORKER_VERTS
    global _WORKER_FACES
    global _WORKER_IMAGE
    global _WORKER_NX
    global _WORKER_NY
    global _WORKER_NZ
    global _WORKER_P
    global _WORKER_Q
    global _WORKER_R
    global _WORKER_RES
    global _WORKER_CELL_VOL
    global _WORKER_OWNER_LABEL

    _WORKER_VERTS = verts
    _WORKER_FACES = faces
    _WORKER_IMAGE = image
    _WORKER_NX = nx
    _WORKER_NY = ny
    _WORKER_NZ = nz
    _WORKER_P = p
    _WORKER_Q = q
    _WORKER_R = r
    _WORKER_RES = res
    _WORKER_CELL_VOL = cell_vol
    _WORKER_OWNER_LABEL = owner_label


def _accumulate_chunk(face_bounds):
    start, end = face_bounds
    field = np.zeros((_WORKER_NZ, _WORKER_NY, _WORKER_NX), dtype=np.float64)
    for face in _WORKER_FACES[start:end]:
        tri = _WORKER_VERTS[np.asarray(face, dtype=int)]
        edge1 = tri[1] - tri[0]
        edge2 = tri[2] - tri[0]
        normal = np.cross(edge1, edge2)
        norm = np.linalg.norm(normal)
        if norm == 0.0:
            continue
        area = 0.5 * norm
        centroid = tri.mean(axis=0)
        unit_normal = normal / norm
        owner_point = choose_owner_point(centroid, unit_normal)
        k, j, i = point_to_coarse_index(owner_point)
        field[k, j, i] += area / _WORKER_CELL_VOL
    return field


def build_field(verts, faces, image, nx, ny, nz, p, q, r, res, owner_label):
    cell_vol = p * q * r * (res ** 3)
    nfaces = faces.shape[0]
    nprocs = default_process_count(nfaces)

    _init_worker(verts, faces, image, nx, ny, nz, p, q, r, res, cell_vol, owner_label)

    if nprocs == 1:
        field = _accumulate_chunk((0, nfaces))
        return field, 1

    chunk_edges = np.linspace(0, nfaces, nprocs + 1, dtype=int)
    chunks = []
    for start, end in zip(chunk_edges[:-1], chunk_edges[1:]):
        if end > start:
            chunks.append((int(start), int(end)))

    ctx = mp.get_context("fork")
    with ctx.Pool(
        processes=len(chunks),
        initializer=_init_worker,
        initargs=(verts, faces, image, nx, ny, nz, p, q, r, res, cell_vol, owner_label),
    ) as pool:
        partials = pool.map(_accumulate_chunk, chunks)

    field = np.zeros((nz, ny, nx), dtype=np.float64)
    for part in partials:
        field += part
    return field, len(chunks)


def build_reconstruction_field(owner_mask, pair_mask, res, surface_mode, smooth_sigma_vox):
    owner_padded = np.pad(owner_mask.astype(np.uint8), 1, mode="constant", constant_values=0)
    pair_mask_padded = np.pad(pair_mask.astype(bool), 1, mode="constant", constant_values=False)

    if surface_mode == "binary":
        return owner_padded.astype(np.float32), 0.5, pair_mask_padded

    if surface_mode == "signedDistance":
        owner_bool = owner_padded.astype(bool)
        other_distance = distance_transform_edt(~owner_bool, sampling=(res, res, res))
        owner_distance = distance_transform_edt(owner_bool, sampling=(res, res, res))
        return other_distance - owner_distance, 0.0, pair_mask_padded

    if surface_mode == "signedDistanceGaussian":
        owner_bool = owner_padded.astype(bool)
        other_distance = distance_transform_edt(~owner_bool, sampling=(res, res, res))
        owner_distance = distance_transform_edt(owner_bool, sampling=(res, res, res))
        signed_distance = other_distance - owner_distance
        smoothed = gaussian_filter(
            signed_distance.astype(np.float32),
            sigma=float(smooth_sigma_vox),
            mode="nearest",
            truncate=4.0,
        )
        return smoothed, 0.0, pair_mask_padded

    if surface_mode == "occupancyGaussian":
        occupancy = owner_padded.astype(np.float32)
        mask_float = pair_mask_padded.astype(np.float32)
        weighted = gaussian_filter(
            occupancy * mask_float,
            sigma=float(smooth_sigma_vox),
            mode="constant",
            cval=0.0,
            truncate=4.0,
        )
        normalization = gaussian_filter(
            mask_float,
            sigma=float(smooth_sigma_vox),
            mode="constant",
            cval=0.0,
            truncate=4.0,
        )
        smoothed = np.zeros_like(weighted)
        valid = normalization > 1e-12
        smoothed[valid] = weighted[valid] / normalization[valid]
        return smoothed, 0.5, pair_mask_padded

    raise ValueError(f"Unsupported surface_mode: {surface_mode}")


def build_reconstruction_field_2d(owner_mask, pair_mask, res, surface_mode, smooth_sigma_vox):
    owner_2d = np.any(owner_mask, axis=0).astype(np.uint8)
    pair_mask_2d = np.any(pair_mask, axis=0).astype(bool)

    owner_padded = np.pad(owner_2d, 1, mode="constant", constant_values=0)
    pair_mask_padded = np.pad(pair_mask_2d, 1, mode="constant", constant_values=False)

    if surface_mode == "binary":
        return owner_padded.astype(np.float32), 0.5, pair_mask_padded

    if surface_mode == "signedDistance":
        owner_bool = owner_padded.astype(bool)
        other_distance = distance_transform_edt(~owner_bool, sampling=(res, res))
        owner_distance = distance_transform_edt(owner_bool, sampling=(res, res))
        return other_distance - owner_distance, 0.0, pair_mask_padded

    if surface_mode == "signedDistanceGaussian":
        owner_bool = owner_padded.astype(bool)
        other_distance = distance_transform_edt(~owner_bool, sampling=(res, res))
        owner_distance = distance_transform_edt(owner_bool, sampling=(res, res))
        signed_distance = other_distance - owner_distance
        smoothed = gaussian_filter(
            signed_distance.astype(np.float32),
            sigma=float(smooth_sigma_vox),
            mode="nearest",
            truncate=4.0,
        )
        return smoothed, 0.0, pair_mask_padded

    if surface_mode == "occupancyGaussian":
        occupancy = owner_padded.astype(np.float32)
        mask_float = pair_mask_padded.astype(np.float32)
        weighted = gaussian_filter(
            occupancy * mask_float,
            sigma=float(smooth_sigma_vox),
            mode="constant",
            cval=0.0,
            truncate=4.0,
        )
        normalization = gaussian_filter(
            mask_float,
            sigma=float(smooth_sigma_vox),
            mode="constant",
            cval=0.0,
            truncate=4.0,
        )
        smoothed = np.zeros_like(weighted)
        valid = normalization > 1e-12
        smoothed[valid] = weighted[valid] / normalization[valid]
        return smoothed, 0.5, pair_mask_padded

    raise ValueError(f"Unsupported surface_mode: {surface_mode}")


def contour_total_length(contours: list[np.ndarray]) -> float:
    total = 0.0
    for contour in contours:
        if contour.shape[0] < 2:
            continue
        diffs = np.diff(contour, axis=0)
        total += float(np.sum(np.linalg.norm(diffs, axis=1)))
    return total


def first_shell_support_mask_2d(owner_mask: np.ndarray, pair_mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    owner_2d = np.any(owner_mask, axis=0)
    pair_2d = np.any(pair_mask, axis=0)
    other_2d = pair_2d & ~owner_2d

    support = np.zeros_like(owner_2d, dtype=bool)
    support[:-1, :] |= owner_2d[:-1, :] & other_2d[1:, :]
    support[1:, :] |= owner_2d[1:, :] & other_2d[:-1, :]
    support[:, :-1] |= owner_2d[:, :-1] & other_2d[:, 1:]
    support[:, 1:] |= owner_2d[:, 1:] & other_2d[:, :-1]
    return owner_2d, support


def target_interface_length_2d(owner_mask: np.ndarray, pair_mask: np.ndarray, res: float) -> float:
    owner_2d, support = first_shell_support_mask_2d(owner_mask, pair_mask)
    pair_2d = np.any(pair_mask, axis=0)
    other_2d = pair_2d & ~owner_2d

    vertical = owner_2d[:, :-1] & other_2d[:, 1:]
    vertical |= other_2d[:, :-1] & owner_2d[:, 1:]
    horizontal = owner_2d[:-1, :] & other_2d[1:, :]
    horizontal |= other_2d[:-1, :] & owner_2d[1:, :]

    return float((np.count_nonzero(vertical) + np.count_nonzero(horizontal)) * res)


def contour_support_fraction_2d(
    contours: list[np.ndarray],
    owner_mask_2d: np.ndarray,
    support_mask_2d: np.ndarray,
    res: float,
) -> float:
    total_length = 0.0
    supported_length = 0.0

    for contour in contours:
        if contour.shape[0] < 2:
            continue
        for start, end in zip(contour[:-1], contour[1:]):
            segment = end - start
            seg_len = np.linalg.norm(segment)
            if seg_len == 0.0:
                continue

            tangent = segment / seg_len
            unit_normal = np.array([-tangent[1], tangent[0]], dtype=np.float64)
            midpoint = 0.5 * (start + end)
            owner_point = choose_owner_point_2d(midpoint, unit_normal, owner_mask_2d, res)
            j, i = point_to_fine_index_2d(owner_point, support_mask_2d.shape, res)

            total_length += seg_len
            if support_mask_2d[j, i]:
                supported_length += seg_len

    if total_length <= 0.0:
        return 0.0
    return supported_length / total_length


def marching_cubes_for_pair(owner_mask, pair_mask, res, surface_mode, smooth_sigma_vox):
    modes_to_try = [surface_mode]
    if surface_mode != "binary":
        modes_to_try.append("binary")

    last_exc = None
    for mode in modes_to_try:
        reconstruction_field, level, mc_mask = build_reconstruction_field(
            owner_mask, pair_mask, res, mode, smooth_sigma_vox
        )
        try:
            verts, faces, _, _ = marching_cubes(
                reconstruction_field,
                level=level,
                spacing=(res, res, res),
                step_size=1,
                allow_degenerate=False,
                mask=mc_mask,
            )
            verts -= res
            return verts, faces, mode
        except (RuntimeError, ValueError) as exc:
            last_exc = exc
            if "No surface found" in str(exc) or "Surface level" in str(exc):
                continue
            raise

    if last_exc is None:
        raise RuntimeError("marching_cubes_for_pair failed without an exception")
    raise last_exc


def contours_for_pair(owner_mask, pair_mask, res, surface_mode, smooth_sigma_vox):
    modes_to_try = [surface_mode]
    if surface_mode != "binary":
        modes_to_try.append("binary")

    target_length = target_interface_length_2d(owner_mask, pair_mask, res)
    owner_mask_2d, support_mask_2d = first_shell_support_mask_2d(owner_mask, pair_mask)

    for mode in modes_to_try:
        reconstruction_field, level, contour_mask = build_reconstruction_field_2d(
            owner_mask, pair_mask, res, mode, smooth_sigma_vox
        )

        if mode == "signedDistanceGaussian" and target_length > 0.0:
            level_span = max(1.5 * res, 1.5 * smooth_sigma_vox * res)
            candidate_levels = np.linspace(-level_span, level_span, 41)
        else:
            level_span = max(abs(float(level)), 1.0)
            candidate_levels = np.array([level], dtype=np.float64)

        best = None
        best_score = None
        for candidate_level in candidate_levels:
            contours = find_contours(
                reconstruction_field,
                level=float(candidate_level),
                fully_connected="low",
                positive_orientation="low",
                mask=contour_mask,
            )
            if not contours:
                continue
            shifted = [(np.asarray(contour, dtype=np.float64) - 1.0) * res for contour in contours]
            length = contour_total_length(shifted)
            perimeter_rel_error = (
                abs(length - target_length) / target_length if target_length > 0.0 else 0.0
            )
            support_fraction = contour_support_fraction_2d(
                shifted,
                owner_mask_2d,
                support_mask_2d,
                res,
            )
            level_penalty = abs(float(candidate_level)) / max(level_span, 1e-12)
            score = perimeter_rel_error + 0.75 * (1.0 - support_fraction) + 0.05 * level_penalty
            if best_score is None or score < best_score:
                best_score = score
                best = shifted

        if best:
            return best, mode

    raise RuntimeError("contours_for_pair found no interface contours")


def point_to_fine_index_2d(point, image_shape, res):
    j = int(np.clip(np.floor(point[0] / res), 0, image_shape[0] - 1))
    i = int(np.clip(np.floor(point[1] / res), 0, image_shape[1] - 1))
    return j, i


def is_owner_at_2d(point, owner_mask_2d, res):
    j, i = point_to_fine_index_2d(point, owner_mask_2d.shape, res)
    return owner_mask_2d[j, i]


def choose_owner_point_2d(midpoint, unit_normal, owner_mask_2d, res):
    # Smoothed 2-D contours can sit inside the non-reactive side of the binary
    # image. Search far enough along the local normal to assign the contour
    # length to the pore-side owner cell used by DBS chemistry.
    for epsilon_vox in (0.2, 0.4, 0.6, 0.8, 1.0, 1.25, 1.5):
        epsilon = epsilon_vox * res
        plus = midpoint + epsilon * unit_normal
        minus = midpoint - epsilon * unit_normal
        plus_owner = is_owner_at_2d(plus, owner_mask_2d, res)
        minus_owner = is_owner_at_2d(minus, owner_mask_2d, res)

        if plus_owner and not minus_owner:
            return plus
        if minus_owner and not plus_owner:
            return minus
        if plus_owner:
            return plus
        if minus_owner:
            return minus
    return midpoint


def segment_split_t_values_2d(start, end, cell_height, cell_width):
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


def segment_contributions_2d(start, end, cell_height, cell_width, ny, nx):
    segment = end - start
    seg_len = np.linalg.norm(segment)
    if seg_len == 0.0:
        return []

    ts = segment_split_t_values_2d(start, end, cell_height, cell_width)
    contributions = []
    for t0, t1 in zip(ts[:-1], ts[1:]):
        if t1 <= t0:
            continue
        midpoint = start + 0.5 * (t0 + t1) * segment
        j = int(np.clip(np.floor(midpoint[0] / cell_height), 0, ny - 1))
        i = int(np.clip(np.floor(midpoint[1] / cell_width), 0, nx - 1))
        contributions.append((j, i, seg_len * (t1 - t0)))
    return contributions


def owner_segment_contributions_2d(
    start,
    end,
    unit_normal,
    owner_mask_2d,
    res,
    cell_height,
    cell_width,
    ny,
    nx,
    origin=None,
):
    if origin is None:
        origin = np.zeros(2, dtype=np.float64)

    segment = end - start
    seg_len = np.linalg.norm(segment)
    if seg_len == 0.0:
        return []

    start_global = start + origin
    end_global = end + origin
    ts = segment_split_t_values_2d(start_global, end_global, cell_height, cell_width)
    contributions = []
    for t0, t1 in zip(ts[:-1], ts[1:]):
        if t1 <= t0:
            continue

        midpoint = start + 0.5 * (t0 + t1) * segment
        owner_point = choose_owner_point_2d(midpoint, unit_normal, owner_mask_2d, res)
        owner_point_global = owner_point + origin
        j = int(np.clip(np.floor(owner_point_global[0] / cell_height), 0, ny - 1))
        i = int(np.clip(np.floor(owner_point_global[1] / cell_width), 0, nx - 1))
        contributions.append((j, i, seg_len * (t1 - t0)))
    return contributions


def build_field_2d(contours, image, nx, ny, nz, p, q, r, res, owner_label):
    cell_vol = p * q * r * (res ** 3)
    field = np.zeros((nz, ny, nx), dtype=np.float64)
    owner_mask_2d = np.any(image == owner_label, axis=0)
    thickness = image.shape[0] * res

    for contour in contours:
        if contour.shape[0] < 2:
            continue

        shifted = np.asarray(contour, dtype=np.float64)
        for start, end in zip(shifted[:-1], shifted[1:]):
            segment = end - start
            seg_len = np.linalg.norm(segment)
            if seg_len == 0.0:
                continue

            tangent = segment / seg_len
            unit_normal = np.array([-tangent[1], tangent[0]], dtype=np.float64)

            for j, i, piece_len in owner_segment_contributions_2d(
                start,
                end,
                unit_normal,
                owner_mask_2d,
                res,
                q * res,
                p * res,
                ny,
                nx,
            ):
                field[0, j, i] += (piece_len * thickness) / cell_vol

    return field


def point_segment_distance_2d(point, start, end):
    segment = end - start
    denom = float(np.dot(segment, segment))
    if denom <= 0.0:
        return float(np.linalg.norm(point - start))
    t = float(np.clip(np.dot(point - start, segment) / denom, 0.0, 1.0))
    projection = start + t * segment
    return float(np.linalg.norm(point - projection))


def build_field_2d_local_deposition(
    contours,
    image,
    nx,
    ny,
    nz,
    p,
    q,
    r,
    res,
    owner_label,
    other_label,
    search_radius=2,
    sigma_cells=1.0,
    contact_power=1.0,
):
    cell_vol = p * q * r * (res ** 3)
    field = np.zeros((nz, ny, nx), dtype=np.float64)
    owner_mask_2d = np.any(image == owner_label, axis=0)
    other_mask_2d = np.any(image == other_label, axis=0)
    fine_support_weights = first_shell_support_weights_2d(owner_mask_2d, other_mask_2d)
    expected_shape = (ny * q, nx * p)
    if fine_support_weights.shape != expected_shape:
        raise ValueError(
            f"Fine support shape mismatch: {fine_support_weights.shape} != {expected_shape}"
        )
    support_weights = fine_support_weights.reshape(ny, q, nx, p).sum(axis=(1, 3))
    support = support_weights > 0.0
    thickness = image.shape[0] * res
    sigma = max(float(sigma_cells) * res, 1e-30)

    for contour in contours:
        if contour.shape[0] < 2:
            continue

        shifted = np.asarray(contour, dtype=np.float64)
        for start, end in zip(shifted[:-1], shifted[1:]):
            segment = end - start
            seg_len = np.linalg.norm(segment)
            if seg_len == 0.0:
                continue

            tangent = segment / seg_len
            unit_normal = np.array([-tangent[1], tangent[0]], dtype=np.float64)
            ts = segment_split_t_values_2d(start, end, q * res, p * res)

            for t0, t1 in zip(ts[:-1], ts[1:]):
                if t1 <= t0:
                    continue

                piece_start = start + t0 * segment
                piece_end = start + t1 * segment
                midpoint = 0.5 * (piece_start + piece_end)
                owner_point = choose_owner_point_2d(midpoint, unit_normal, owner_mask_2d, res)
                cj = int(np.clip(np.floor(owner_point[0] / (q * res)), 0, ny - 1))
                ci = int(np.clip(np.floor(owner_point[1] / (p * res)), 0, nx - 1))

                candidates = []
                weights = []
                for jj in range(max(0, cj - search_radius), min(ny, cj + search_radius + 1)):
                    for ii in range(max(0, ci - search_radius), min(nx, ci + search_radius + 1)):
                        if not support[jj, ii]:
                            continue
                        center = np.array([(jj + 0.5) * q * res, (ii + 0.5) * p * res], dtype=np.float64)
                        distance = point_segment_distance_2d(center, piece_start, piece_end)
                        weight = np.exp(-0.5 * (distance / sigma) ** 2)
                        weight *= support_weights[jj, ii] ** contact_power
                        if weight > 0.0:
                            candidates.append((jj, ii))
                            weights.append(weight)

                if not candidates:
                    continue

                weights = np.asarray(weights, dtype=np.float64)
                weights /= np.sum(weights)
                piece_area = seg_len * (t1 - t0) * thickness
                for (jj, ii), weight in zip(candidates, weights):
                    field[0, jj, ii] += piece_area * weight / cell_vol

    return field


def first_shell_support_weights_2d(owner_mask_2d, other_mask_2d):
    weights = np.zeros_like(owner_mask_2d, dtype=np.float64)
    weights[:-1, :] += owner_mask_2d[:-1, :] & other_mask_2d[1:, :]
    weights[1:, :] += owner_mask_2d[1:, :] & other_mask_2d[:-1, :]
    weights[:, :-1] += owner_mask_2d[:, :-1] & other_mask_2d[:, 1:]
    weights[:, 1:] += owner_mask_2d[:, 1:] & other_mask_2d[:, :-1]
    return weights


def redistribute_2d_field_to_support(field, image, nx, ny, nz, p, q, r, owner_label, other_label):
    owner_mask_2d = np.any(image == owner_label, axis=0)
    other_mask_2d = np.any(image == other_label, axis=0)
    fine_weights = first_shell_support_weights_2d(owner_mask_2d, other_mask_2d)
    weights = np.zeros((ny, nx), dtype=np.float64)

    for j in range(ny):
        y0 = j * q
        y1 = y0 + q
        for i in range(nx):
            x0 = i * p
            x1 = x0 + p
            weights[j, i] = float(np.sum(fine_weights[y0:y1, x0:x1]))

    redistributed = np.zeros_like(field)
    for i in range(nx):
        total = float(np.sum(field[:, :, i]))
        column_weights = weights[:, i]
        weight_sum = float(np.sum(column_weights))
        if total > 0.0 and weight_sum > 0.0:
            redistributed[0, :, i] = column_weights * total / weight_sum
        else:
            redistributed[:, :, i] = field[:, :, i]

    return redistributed


def parse_pair_specs(text, default_owner_label, default_other_label):
    if text.strip().lower() == "none":
        return []

    if not text:
        return [
            {
                "owner": int(default_owner_label),
                "other": int(default_other_label),
                "name": "external",
            }
        ]

    specs = []
    for raw_spec in text.split(";"):
        raw_spec = raw_spec.strip()
        if not raw_spec:
            continue
        parts = raw_spec.split(":")
        if len(parts) not in {3, 4}:
            raise ValueError(
                "Pair specs must use 'owner:labelA:labelB[:name]' and be separated by ';'"
            )
        owner = int(float(parts[0]))
        label_a = int(float(parts[1]))
        label_b = int(float(parts[2]))
        if owner not in {label_a, label_b}:
            raise ValueError(f"Owner label {owner} must match one of pair labels {label_a}, {label_b}")
        other = label_b if owner == label_a else label_a
        name = parts[3] if len(parts) == 4 else f"{owner}_{other}"
        specs.append({"owner": owner, "other": other, "name": name})

    if not specs:
        raise ValueError("At least one non-empty pair spec is required")
    return specs


def parse_intrinsic_specs(text):
    if not text:
        return []

    specs = []
    for raw_spec in text.split(";"):
        raw_spec = raw_spec.strip()
        if not raw_spec:
            continue
        parts = raw_spec.split(":")
        if len(parts) not in {2, 3}:
            raise ValueError(
                "Intrinsic specs must use 'label:density[:name]' and be separated by ';'"
            )
        label = int(float(parts[0]))
        density = float(parts[1])
        if density < 0.0:
            raise ValueError("Intrinsic densities must be non-negative")
        name = parts[2] if len(parts) == 3 else str(label)
        specs.append({"label": label, "density": density, "name": name})
    return specs


def sanitize_component_name(base_name, component_name):
    clean = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in component_name)
    return f"{base_name}_{clean}"


def block_reduce_label_density(image, label, density, nx, ny, nz, p, q, r):
    coarse = np.zeros((nz, ny, nx), dtype=np.float64)
    block_cells = p * q * r
    for k in range(nz):
        z0 = k * r
        z1 = z0 + r
        for j in range(ny):
            y0 = j * q
            y1 = y0 + q
            for i in range(nx):
                x0 = i * p
                x1 = x0 + p
                count = np.count_nonzero(image[z0:z1, y0:y1, x0:x1] == label)
                coarse[k, j, i] = density * count / block_cells
    return coarse


def main():
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
    field_name = sys.argv[18] if len(sys.argv) > 18 else "aSurf"
    surface_mode = sys.argv[19] if len(sys.argv) > 19 else "signedDistance"
    smooth_sigma_vox = float(sys.argv[20]) if len(sys.argv) > 20 else 0.75
    pair_specs_text = sys.argv[21] if len(sys.argv) > 21 else ""
    intrinsic_specs_text = sys.argv[22] if len(sys.argv) > 22 else ""
    write_components = (
        sys.argv[23].lower() in {"1", "true", "yes", "on"}
        if len(sys.argv) > 23
        else False
    )
    output_location = sys.argv[24] if len(sys.argv) > 24 else "0"

    if (x_max - x_min) % n_x or (y_max - y_min) % n_y or (z_max - z_min) % n_z:
        raise ValueError("Coarse mesh dimensions must divide the cropped image exactly")

    p = int((x_max - x_min) / n_x)
    q = int((y_max - y_min) / n_y)
    r = int((z_max - z_min) / n_z)

    image = load_raw_image(
        x_dim,
        y_dim,
        z_dim,
        x_min,
        x_max,
        y_min,
        y_max,
        z_min,
        z_max,
        image_name,
    )

    pair_specs = parse_pair_specs(pair_specs_text, pore_value, solid_value)
    intrinsic_specs = parse_intrinsic_specs(intrinsic_specs_text)

    total_field = np.zeros((n_z, n_y, n_x), dtype=np.float64)
    total_triangles = 0
    max_procs = 1
    used_modes = []

    for spec in pair_specs:
        owner_mask = image == spec["owner"]
        other_mask = image == spec["other"]
        pair_mask = owner_mask | other_mask
        if not np.any(owner_mask) or not np.any(other_mask):
            component = np.zeros_like(total_field)
            ntris = 0
            nprocs = 1
        else:
            try:
                if dimension == "2D":
                    contours, used_mode = contours_for_pair(
                        owner_mask, pair_mask, res, surface_mode, smooth_sigma_vox
                    )
                    if surface_mode in SUPPORT_REDISTRIBUTED_2D_MODES:
                        component = build_field_2d_local_deposition(
                            contours,
                            image,
                            n_x,
                            n_y,
                            n_z,
                            p,
                            q,
                            r,
                            res,
                            spec["owner"],
                            spec["other"],
                        )
                    else:
                        component = build_field_2d(
                            contours, image, n_x, n_y, n_z, p, q, r, res, spec["owner"]
                        )
                    nprocs = 1
                    ntris = sum(max(0, contour.shape[0] - 1) for contour in contours)
                else:
                    verts, faces, used_mode = marching_cubes_for_pair(
                        owner_mask, pair_mask, res, surface_mode, smooth_sigma_vox
                    )
                    component, nprocs = build_field(
                        verts, faces, image, n_x, n_y, n_z, p, q, r, res, spec["owner"]
                    )
                    ntris = faces.shape[0]
                used_modes.append(f"{spec['name']}={used_mode}")
            except (RuntimeError, ValueError) as exc:
                if "No surface found" in str(exc) or "Surface level" in str(exc):
                    component = np.zeros_like(total_field)
                    ntris = 0
                    nprocs = 1
                    used_modes.append(f"{spec['name']}=none")
                else:
                    raise
        total_field += component
        total_triangles += ntris
        max_procs = max(max_procs, nprocs)
        if write_components:
            write_field(
                component,
                sanitize_component_name(field_name, spec["name"]),
                dimension,
                output_location,
            )

    for spec in intrinsic_specs:
        component = block_reduce_label_density(image, spec["label"], spec["density"], n_x, n_y, n_z, p, q, r)
        total_field += component
        if write_components:
            write_field(
                component,
                sanitize_component_name(field_name, f"intrinsic_{spec['name']}"),
                dimension,
                output_location,
            )

    write_field(total_field, field_name, dimension, output_location)
    print(
        f"Created {field_name} with smooth reconstruction: "
        f"mode={surface_mode} "
        f"sigma_vox={smooth_sigma_vox:.6g} "
        f"pairs={len(pair_specs)} intrinsic={len(intrinsic_specs)} "
        f"used_modes={','.join(used_modes) if used_modes else 'none'} "
        f"triangles={total_triangles} procs={max_procs} "
        f"sum(aSurf*V)={total_field.sum() * p * q * r * (res ** 3):.16e}"
    )


if __name__ == "__main__":
    main()
