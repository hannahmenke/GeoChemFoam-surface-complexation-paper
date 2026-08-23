import os
import sys
import tarfile
import multiprocessing as mp

import numpy as np


_WORKER_MISMATCH = None
_WORKER_PADDED = None
_WORKER_NX1 = None
_WORKER_NY1 = None
_WORKER_P = None
_WORKER_Q = None
_WORKER_R = None
_WORKER_COEFF = None
_WORKER_BLOCK_CELLS = None
_WORKER_INTRINSIC_ITEMS = None


def padded_bounds(x_min, x_max, y_min, y_max, z_min, z_max, pad_width, direction):
    if direction == 0:
        return (
            -pad_width,
            x_max - x_min + pad_width,
            0,
            y_max - y_min,
            0,
            z_max - z_min,
            0,
        )
    if direction == 1:
        return (
            0,
            x_max - x_min,
            -pad_width,
            y_max - y_min + pad_width,
            0,
            z_max - z_min,
            0,
        )
    if direction == 2:
        return (
            0,
            x_max - x_min,
            0,
            y_max - y_min,
            -pad_width,
            z_max - z_min + pad_width,
            pad_width,
        )
    if direction == -1:
        return (
            -pad_width,
            x_max - x_min + pad_width,
            -pad_width,
            y_max - y_min + pad_width,
            -pad_width,
            z_max - z_min + pad_width,
            pad_width,
        )
    raise ValueError(f"Unsupported direction: {direction}")


def load_padded_image(
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
    pad_width,
    pad_value,
    direction,
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
    image = image[z_min:z_max, y_min:y_max, x_min:x_max]

    if direction == 0:
        return np.pad(
            image,
            ((0, 0), (0, 0), (pad_width, pad_width)),
            mode="constant",
            constant_values=pad_value,
        )
    if direction == 1:
        return np.pad(
            image,
            ((0, 0), (pad_width, pad_width), (0, 0)),
            mode="constant",
            constant_values=pad_value,
        )
    if direction == 2:
        return np.pad(
            image,
            ((pad_width, pad_width), (0, 0), (0, 0)),
            mode="constant",
            constant_values=pad_value,
        )
    if direction == -1:
        return np.pad(
            image,
            ((pad_width, pad_width), (pad_width, pad_width), (pad_width, pad_width)),
            mode="constant",
            constant_values=pad_value,
        )

    raise ValueError(f"Unsupported direction: {direction}")


def write_field(field, field_name, dimension):
    nz1, ny1, nx1 = field.shape
    ncells = nx1 * ny1 * nz1

    os.makedirs("0", exist_ok=True)

    header = [
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
        "    location    \"0\";\n",
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

    footer = [
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

    if dimension == "2D":
        footer.extend(
            [
                "    frontAndBack\n",
                "    {\n",
                "        type            empty;\n",
                "    }\n",
            ]
        )

    footer.extend(["}\n", "\n", "// ************************************************************************* //\n"])

    with open(os.path.join("0", field_name), "w") as handle:
        handle.writelines(header)
        # Stream values directly: a 500^3 field must not become 125 million
        # simultaneously live Python strings.
        np.savetxt(handle, field.reshape(-1, 1), fmt="%.8g")
        handle.writelines(footer)


def mismatch_counts(is_solid, support_mode):
    counts = np.zeros(is_solid.shape, dtype=np.uint8)

    if support_mode == "none":
        return counts

    diff_x = is_solid[:, :, 1:] != is_solid[:, :, :-1]
    if support_mode == "both":
        counts[:, :, 1:] += diff_x
        counts[:, :, :-1] += diff_x
    elif support_mode == "fluid":
        counts[:, :, 1:] += diff_x & (~is_solid[:, :, 1:])
        counts[:, :, :-1] += diff_x & (~is_solid[:, :, :-1])
    elif support_mode == "solid":
        counts[:, :, 1:] += diff_x & is_solid[:, :, 1:]
        counts[:, :, :-1] += diff_x & is_solid[:, :, :-1]
    else:
        raise ValueError(f"Unsupported support mode: {support_mode}")

    diff_y = is_solid[:, 1:, :] != is_solid[:, :-1, :]
    if support_mode == "both":
        counts[:, 1:, :] += diff_y
        counts[:, :-1, :] += diff_y
    elif support_mode == "fluid":
        counts[:, 1:, :] += diff_y & (~is_solid[:, 1:, :])
        counts[:, :-1, :] += diff_y & (~is_solid[:, :-1, :])
    elif support_mode == "solid":
        counts[:, 1:, :] += diff_y & is_solid[:, 1:, :]
        counts[:, :-1, :] += diff_y & is_solid[:, :-1, :]

    diff_z = is_solid[1:, :, :] != is_solid[:-1, :, :]
    if support_mode == "both":
        counts[1:, :, :] += diff_z
        counts[:-1, :, :] += diff_z
    elif support_mode == "fluid":
        counts[1:, :, :] += diff_z & (~is_solid[1:, :, :])
        counts[:-1, :, :] += diff_z & (~is_solid[:-1, :, :])
    elif support_mode == "solid":
        counts[1:, :, :] += diff_z & is_solid[1:, :, :]
        counts[:-1, :, :] += diff_z & is_solid[:-1, :, :]

    return counts


def default_process_count(nz1):
    requested = os.environ.get("GCFOAM_ASURF_PROCS")
    if requested:
        nprocs = int(requested)
    else:
        nprocs = min(8, os.cpu_count() or 1)

    return max(1, min(nprocs, nz1))


def block_reduce(local_values, k_start, k_end, ny1, nx1, r, q, p):
    k_count = k_end - k_start
    reshaped = local_values.reshape((k_count, r, ny1, q, nx1, p))
    return reshaped.sum(axis=(1, 3, 5), dtype=np.float64)


def _init_worker(mismatch, padded, nx1, ny1, p, q, r, coeff, block_cells, intrinsic_items):
    global _WORKER_MISMATCH
    global _WORKER_PADDED
    global _WORKER_NX1
    global _WORKER_NY1
    global _WORKER_P
    global _WORKER_Q
    global _WORKER_R
    global _WORKER_COEFF
    global _WORKER_BLOCK_CELLS
    global _WORKER_INTRINSIC_ITEMS

    _WORKER_MISMATCH = mismatch
    _WORKER_PADDED = padded
    _WORKER_NX1 = nx1
    _WORKER_NY1 = ny1
    _WORKER_P = p
    _WORKER_Q = q
    _WORKER_R = r
    _WORKER_COEFF = coeff
    _WORKER_BLOCK_CELLS = block_cells
    _WORKER_INTRINSIC_ITEMS = intrinsic_items


def _compute_chunk(k_bounds):
    k_start, k_end = k_bounds
    z0 = k_start * _WORKER_R
    z1 = k_end * _WORKER_R

    reduced = (
        block_reduce(
            _WORKER_MISMATCH[z0:z1],
            k_start,
            k_end,
            _WORKER_NY1,
            _WORKER_NX1,
            _WORKER_R,
            _WORKER_Q,
            _WORKER_P,
        )
        * _WORKER_COEFF
    )

    for label, density in _WORKER_INTRINSIC_ITEMS:
        local_mask = (_WORKER_PADDED[z0:z1] == label).astype(np.uint8)
        reduced += (
            block_reduce(
                local_mask,
                k_start,
                k_end,
                _WORKER_NY1,
                _WORKER_NX1,
                _WORKER_R,
                _WORKER_Q,
                _WORKER_P,
            )
            / _WORKER_BLOCK_CELLS
        ) * density

    return k_start, reduced


def build_field_parallel(mismatch, padded, nx1, ny1, nz1, p, q, r, coeff, block_cells, intrinsic_density_by_label):
    field = np.zeros((nz1, ny1, nx1), dtype=np.float64)
    nprocs = default_process_count(nz1)

    _init_worker(
        mismatch,
        padded,
        nx1,
        ny1,
        p,
        q,
        r,
        coeff,
        block_cells,
        tuple(sorted(intrinsic_density_by_label.items())),
    )

    if nprocs == 1:
        _, reduced = _compute_chunk((0, nz1))
        field[:, :, :] = reduced
        return field, 1

    chunk_edges = np.linspace(0, nz1, nprocs + 1, dtype=int)
    chunks = []
    for start, end in zip(chunk_edges[:-1], chunk_edges[1:]):
        if end > start:
            chunks.append((int(start), int(end)))

    ctx = mp.get_context("fork")
    with ctx.Pool(processes=len(chunks)) as pool:
        # Assign completed slabs immediately instead of retaining every worker
        # result (another full float64 field) in the parent process.
        for k_start, reduced in pool.imap_unordered(_compute_chunk, chunks):
            k_end = k_start + reduced.shape[0]
            field[k_start:k_end, :, :] = reduced

    return field, len(chunks)


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
    pad_width = int(sys.argv[15])
    pad_value = int(float(sys.argv[16]))
    solid_value = int(float(sys.argv[17]))
    dimension = sys.argv[18]
    direction = int(sys.argv[19])
    field_name = sys.argv[20] if len(sys.argv) > 20 else "aSurf"
    support_mode = "both"

    optional_index = 21
    if len(sys.argv) > optional_index and sys.argv[optional_index] in {"both", "fluid", "solid", "none"}:
        support_mode = sys.argv[optional_index]
        optional_index += 1

    intrinsic_density_by_label: dict[int, float] = {}
    if len(sys.argv) > optional_index:
        if len(sys.argv) <= optional_index + 1:
            raise ValueError(
                "Intrinsic aSurf requires both phase labels and densities: "
                "createASurfPhases.py ... fieldName phaseLabels phaseDensities"
            )

        intrinsic_labels = [item for item in sys.argv[optional_index].split(",") if item]
        intrinsic_densities = [item for item in sys.argv[optional_index + 1].split(",") if item]

        if len(intrinsic_labels) != len(intrinsic_densities):
            raise ValueError("Intrinsic phase label and density lists must have the same length")

        for label_text, density_text in zip(intrinsic_labels, intrinsic_densities):
            label = int(float(label_text))
            density = float(density_text)
            if density < 0.0:
                raise ValueError("Intrinsic surface densities must be non-negative")
            intrinsic_density_by_label[label] = density

    if (x_max - x_min) % n_x or (y_max - y_min) % n_y or (z_max - z_min) % n_z:
        raise ValueError("Coarse mesh dimensions must divide the cropped image exactly")

    xmin, xmax, ymin, ymax, zmin, zmax, _ = padded_bounds(
        x_min, x_max, y_min, y_max, z_min, z_max, pad_width, direction
    )

    p = int((x_max - x_min) / n_x)
    q = int((y_max - y_min) / n_y)
    r = int((z_max - z_min) / n_z)

    nx1 = int((xmax - xmin) / p)
    ny1 = int((ymax - ymin) / q)
    nz1 = int((zmax - zmin) / r)

    padded = load_padded_image(
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
        pad_width,
        pad_value,
        direction,
    )

    is_solid = padded == solid_value
    if support_mode == "both":
        coeff = 0.5 / (p * q * r * res)
    else:
        coeff = 1.0 / (p * q * r * res)
    block_cells = p * q * r
    mismatch = mismatch_counts(is_solid, support_mode)
    field, nprocs = build_field_parallel(
        mismatch,
        padded,
        nx1,
        ny1,
        nz1,
        p,
        q,
        r,
        coeff,
        block_cells,
        intrinsic_density_by_label,
    )

    write_field(field, field_name, dimension)
    print(
        f"Created {field_name}: ncells={nx1 * ny1 * nz1} "
        f"procs={nprocs} "
        f"support={support_mode} "
        f"sum(aSurf*V)={field.sum() * (p * q * r) * (res ** 3):.16e}"
    )


if __name__ == "__main__":
    main()
