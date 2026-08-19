#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../.. && pwd)"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
    set +e
    set +u
    # shellcheck disable=SC1091
    source /usr/local/anaconda3/etc/profile.d/conda.sh
    conda activate gcfoam
    set -e
    set -u
fi

if [ -f "$repo_root/etc/bashrc" ]; then
    set +e
    set +u
    # shellcheck disable=SC1090
    source "$repo_root/etc/bashrc"
    set -e
    set -u
fi

# Pb2+ on Dzombak-Morel HFO two-site model.
# Pb-contaminated water (e.g. mine drainage) flowing through fractures with
# iron-oxyhydroxide coatings. Strong sites (Hfo_s) provide near-irreversible
# high-affinity Pb uptake; weak sites (Hfo_w) provide reversible bulk capacity.
pb_internal="0"
pb_inlet="1e-3"
cl_internal="0"
cl_inlet="2e-3"
h_internal="1.051e-7"
oh_internal="1.069e-7"

# Draft intrinsic surface area for the micropore phase [1/m].
# This adds unresolved in-phase reactive area inside label-1 micropore cells,
# instead of reacting only on the micropore/pore interface.
micropore_intrinsic_asurf="1e5"
export GCFOAM_ASURF_PROCS="${GCFOAM_ASURF_PROCS:-8}"

cp constant/thermoPhysicalProperties1 constant/thermoPhysicalProperties

NPX="$(tail -n 1 system/NPX)"
NPY="$(tail -n 1 system/NPY)"
NPZ="$(tail -n 1 system/NPZ)"

python "$repo_root/scripts/createASurfMarchingCubes.py" \
    500 500 1 \
    0 500 0 500 0 1 \
    250 250 1 \
    0.0001 \
    4StraightFractures \
    1 2 2D aSurf occupancyGaussian 0.75 "" \
    "1:${micropore_intrinsic_asurf}:micropore" true 0 > createASurfReactive.out

python "$repo_root/scripts/createASurfMarchingCubes.py" \
    500 500 1 \
    0 500 0 500 0 1 \
    250 250 1 \
    0.0001 \
    4StraightFractures \
    1 2 2D aSurfIntrinsic occupancyGaussian 0.75 none \
    "1:${micropore_intrinsic_asurf}:micropore" true 0 > createASurfIntrinsicReactive.out

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print | wc -l)"
    if [[ "${PLATFORM:-}" == "ARCHER2" ]]; then
        srun python "$GCFOAM_DIR/applications/utilities/pyTools/createT.py" 2D "$NPX" "$NPY" "$NPZ" 0 1 zeroGradient zeroGradient
    else
        mpirun -np "$NP" python "$GCFOAM_DIR/applications/utilities/pyTools/createT.py" 2D "$NPX" "$NPY" "$NPZ" 0 1 zeroGradient zeroGradient
    fi
else
    python "$GCFOAM_DIR/applications/utilities/pyTools/createT.py" 2D 1 1 1 0 1 zeroGradient zeroGradient
fi

export PB_INTERNAL="$pb_internal"
export PB_INLET="$pb_inlet"
export CL_INTERNAL="$cl_internal"
export CL_INLET="$cl_inlet"
export H_INTERNAL="$h_internal"
export OH_INTERNAL="$oh_internal"
export CASE_IS_PARALLEL="0"
if [ -d "processor0" ]; then
    export CASE_IS_PARALLEL="1"
fi

python - <<'PY'
import os
import re
from pathlib import Path


CASE_IS_PARALLEL = os.environ["CASE_IS_PARALLEL"] == "1"
ROOT = Path(".")


def read_scalar_list(path: Path) -> list[float]:
    text = path.read_text()
    m = re.search(
        r"internalField\s+nonuniform\s+List<scalar>\s*(\d+)\s*\((.*?)\)\s*;",
        text,
        re.S,
    )
    if not m:
        raise RuntimeError(f"Expected nonuniform scalar list in {path}")
    count = int(m.group(1))
    values = [float(x) for x in m.group(2).split()]
    if len(values) != count:
        raise RuntimeError(f"Value count mismatch in {path}")
    return values


def replace_object(text: str, name: str) -> str:
    return re.sub(r"object\s+\S+;", f"object      {name};", text, count=1)


def normalize_header(text: str) -> str:
    return text.replace("*\\\\\\\\n|", "*\\\n|", 1)


def replace_dimensions(text: str, dims: str) -> str:
    return re.sub(r"dimensions\s+\[[^\]]+\];", f"dimensions      {dims};", text, count=1)


def replace_internal_uniform(text: str, value: str) -> str:
    return re.sub(
        r"internalField\s+uniform\s+[^;]+;",
        f"internalField   uniform {value};",
        text,
        count=1,
    )


def replace_internal_nonuniform(text: str, values: list[float]) -> str:
    block = (
        "internalField   nonuniform List<scalar>\n"
        f"{len(values)}\n"
        "(\n"
        + "\n".join(f"{value:.8g}" for value in values)
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


def patch_block(text: str, patch_name: str, body: str) -> str:
    pattern = rf"(^\s*{re.escape(patch_name)}\s*\n\s*\{{\n)(.*?)(^\s*\}})"
    updated, count = re.subn(pattern, rf"\1{body}\3", text, flags=re.M | re.S)
    if count != 1:
        raise RuntimeError(f"Could not patch block {patch_name}")
    return updated


def fixed_value_body(value: str) -> str:
    return (
        "        type            fixedValue;\n"
        f"        value           uniform {value};\n"
    )


def zero_gradient_body() -> str:
    return "        type            zeroGradient;\n"


def write_species(template_path: Path, out_path: Path, name: str, dims: str, internal: str, inlet_mode: str, inlet_value: str | None) -> None:
    text = normalize_header(template_path.read_text())
    text = replace_object(text, name)
    text = replace_dimensions(text, dims)
    text = replace_internal_uniform(text, internal)
    if inlet_mode == "fixedValue":
        text = patch_block(text, "inlet", fixed_value_body(inlet_value if inlet_value is not None else internal))
    else:
        text = patch_block(text, "inlet", zero_gradient_body())
    text = patch_block(text, "outlet", zero_gradient_body())
    wall_patch = '"wall_.*"' if '"wall_.*"' in text else "walls"
    text = patch_block(text, wall_patch, zero_gradient_body())
    out_path.write_text(text)


def make_eps_copy(template_path: Path, out_path: Path, name: str) -> None:
    text = normalize_header(template_path.read_text())
    text = replace_object(text, name)
    out_path.write_text(text)


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


def write_asurf_from_template(template_path: Path, out_path: Path, field_name: str, values: list[float]) -> None:
    text = normalize_header(template_path.read_text())
    text = replace_object(text, field_name)
    text = replace_dimensions(text, "[0 -1 0 0 0 0 0]")
    text = replace_internal_nonuniform(text, values)
    out_path.write_text(text)


aqueous_dims = "[0 -3 0 0 1 0 0]"
surface_dims = "[0 -2 0 0 1 0 0]"

asurf_global = read_scalar_list(ROOT / "0" / "aSurf")
asurf_intrinsic_path = ROOT / "0" / "aSurfIntrinsic"
asurf_intrinsic_global = (
    read_scalar_list(asurf_intrinsic_path)
    if asurf_intrinsic_path.exists()
    else None
)
coarse_nx = 250
coarse_ny = 250
asurf_grid = [asurf_global[row * coarse_nx:(row + 1) * coarse_nx] for row in range(coarse_ny)]
asurf_intrinsic_grid = (
    [asurf_intrinsic_global[row * coarse_nx:(row + 1) * coarse_nx] for row in range(coarse_ny)]
    if asurf_intrinsic_global is not None
    else None
)

if CASE_IS_PARALLEL:
    npx = int((ROOT / "system" / "NPX").read_text().strip())
    npy = int((ROOT / "system" / "NPY").read_text().strip())
    x_sizes, x_starts = local_partition_sizes(coarse_nx, npx)
    y_sizes, y_starts = local_partition_sizes(coarse_ny, npy)

    proc_dirs = sorted(ROOT.glob("processor*/0"))
    for proc_dir in proc_dirs:
        rank = int(proc_dir.parent.name.replace("processor", ""))
        ipy = rank // npx
        ipx = rank % npx
        template_path = proc_dir / "T"
        eps_path = proc_dir / "eps"

        write_species(template_path, proc_dir / "Pb+2", "Pb+2", aqueous_dims, os.environ["PB_INTERNAL"], "fixedValue", os.environ["PB_INLET"])
        write_species(template_path, proc_dir / "Cl-", "Cl-", aqueous_dims, os.environ["CL_INTERNAL"], "fixedValue", os.environ["CL_INLET"])
        write_species(template_path, proc_dir / "H+", "H+", aqueous_dims, os.environ["H_INTERNAL"], "fixedValue", os.environ["H_INTERNAL"])
        write_species(template_path, proc_dir / "OH-", "OH-", aqueous_dims, os.environ["OH_INTERNAL"], "fixedValue", os.environ["OH_INTERNAL"])
        write_species(template_path, proc_dir / "Hfo_sOH", "Hfo_sOH", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Hfo_sO-", "Hfo_sO-", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Hfo_sOPb+", "Hfo_sOPb+", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Hfo_wOH", "Hfo_wOH", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Hfo_wO-", "Hfo_wO-", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Hfo_wOPb+", "Hfo_wOPb+", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Hfo_s", "Hfo_s", surface_dims, "2e-7", "zeroGradient", None)
        write_species(template_path, proc_dir / "Hfo_w", "Hfo_w", surface_dims, "6e-6", "zeroGradient", None)


        xs = x_starts[ipx]
        xe = xs + x_sizes[ipx]
        ys = y_starts[ipy]
        ye = ys + y_sizes[ipy]
        local_values = []
        local_intrinsic_values = [] if asurf_intrinsic_grid is not None else None
        for row in range(ys, ye):
            local_values.extend(asurf_grid[row][xs:xe])
            if local_intrinsic_values is not None:
                local_intrinsic_values.extend(asurf_intrinsic_grid[row][xs:xe])
        write_asurf_from_template(eps_path, proc_dir / "aSurf", "aSurf", local_values)
        if local_intrinsic_values is not None:
            write_asurf_from_template(eps_path, proc_dir / "aSurfIntrinsic", "aSurfIntrinsic", local_intrinsic_values)

        template_path.unlink(missing_ok=True)
else:
    zero_dir = ROOT / "0"
    template_path = zero_dir / "T"
    eps_path = zero_dir / "eps"

    write_species(template_path, zero_dir / "Pb+2", "Pb+2", aqueous_dims, os.environ["PB_INTERNAL"], "fixedValue", os.environ["PB_INLET"])
    write_species(template_path, zero_dir / "Cl-", "Cl-", aqueous_dims, os.environ["CL_INTERNAL"], "fixedValue", os.environ["CL_INLET"])
    write_species(template_path, zero_dir / "H+", "H+", aqueous_dims, os.environ["H_INTERNAL"], "fixedValue", os.environ["H_INTERNAL"])
    write_species(template_path, zero_dir / "OH-", "OH-", aqueous_dims, os.environ["OH_INTERNAL"], "fixedValue", os.environ["OH_INTERNAL"])
    write_species(template_path, zero_dir / "Hfo_sOH", "Hfo_sOH", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Hfo_sO-", "Hfo_sO-", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Hfo_sOPb+", "Hfo_sOPb+", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Hfo_wOH", "Hfo_wOH", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Hfo_wO-", "Hfo_wO-", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Hfo_wOPb+", "Hfo_wOPb+", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Hfo_s", "Hfo_s", surface_dims, "2e-7", "zeroGradient", None)
    write_species(template_path, zero_dir / "Hfo_w", "Hfo_w", surface_dims, "6e-6", "zeroGradient", None)

    if asurf_intrinsic_global is not None:
        write_asurf_from_template(eps_path, zero_dir / "aSurfIntrinsic", "aSurfIntrinsic", asurf_intrinsic_global)
    template_path.unlink(missing_ok=True)
PY

python "$repo_root/scripts/initialiseSurfaceSpecies.py" . --time 0
echo "Reactive transport case initialised for reactiveTransportDBSFoam."
