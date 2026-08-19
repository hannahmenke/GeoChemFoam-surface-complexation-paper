#!/usr/bin/env bash

set -euo pipefail

repo_root="$(cd "$(dirname "$0")"/../../../../.. && pwd)"

if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
    set +e
    set +u
    # shellcheck disable=SC1091
    source /usr/local/anaconda3/etc/profile.d/conda.sh
    conda activate gcfoam
    set -e
    set -u
fi

if [ -z "${GCFOAM_DIR:-}" ] && [ -f "$repo_root/etc/bashrc" ]; then
    set +e
    set +u
    # shellcheck disable=SC1090
    source "$repo_root/etc/bashrc"
    set -e
    set -u
fi

# Li-selective sorption benchmark for direct-lithium-extraction-like brines.
li_internal="1e-12"
li_inlet="1e-3"
na_internal="0.10"
na_inlet="0.10"
k_internal="0.01"
k_inlet="0.01"
mg_internal="0.01"
mg_inlet="0.01"
cl_internal="0.13"
cl_inlet="0.131"
h_internal="1.051e-7"
oh_internal="1.069e-7"
rt_diffusion="${RT_DIFFUSION:-${DIFFUSION:-1e-9}}"

export GCFOAM_ASURF_PROCS="${GCFOAM_ASURF_PROCS:-1}"

cp constant/transportProperties2 constant/transportProperties
cp constant/thermoPhysicalProperties1 constant/thermoPhysicalProperties
sed -i "s/Diff/$rt_diffusion/g" constant/transportProperties
python - <<'PY' "$rt_diffusion"
import re
import sys
from pathlib import Path

diffusion = sys.argv[1]
path = Path("constant/thermoPhysicalProperties")
text = path.read_text()
text = re.sub(
    r"(D\s+D\s+\[\s*0\s+2\s+-1\s+0\s+0\s+0\s+0\s+\]\s+)[^;]+;",
    rf"\g<1>{diffusion};",
    text,
)
path.write_text(text)
PY

NPX="$(tail -n 1 system/NPX)"
NPY="$(tail -n 1 system/NPY)"
NPZ="$(tail -n 1 system/NPZ)"
COARSE_NX="$(tail -n 1 system/Nx1)"
COARSE_NY="$(tail -n 1 system/Ny1)"
COARSE_NZ="$(tail -n 1 system/Nz1)"

# The smoothInterface case reconstructs aSurf inside the solver at startup
# from constant/aSurfReconstructionDict, so no precomputed 0/aSurf field is
# generated here.

if [ -d "processor0" ]
then
    export NP="$(find processor* -maxdepth 0 -type d -print | wc -l)"
    if [[ "${PLATFORM:-}" == "ARCHER2" ]]; then
        srun --ntasks="$NP" python "$GCFOAM_DIR/applications/utilities/pyTools/createT.py" 2D "$NPX" "$NPY" "$NPZ" 0 1 zeroGradient zeroGradient
    else
        mpirun -np "$NP" python "$GCFOAM_DIR/applications/utilities/pyTools/createT.py" 2D "$NPX" "$NPY" "$NPZ" 0 1 zeroGradient zeroGradient
    fi
else
    python "$GCFOAM_DIR/applications/utilities/pyTools/createT.py" 2D 1 1 1 0 1 zeroGradient zeroGradient
fi

export LI_INTERNAL="$li_internal"
export LI_INLET="$li_inlet"
export NA_INTERNAL="$na_internal"
export NA_INLET="$na_inlet"
export K_INTERNAL="$k_internal"
export K_INLET="$k_inlet"
export MG_INTERNAL="$mg_internal"
export MG_INLET="$mg_inlet"
export CL_INTERNAL="$cl_internal"
export CL_INLET="$cl_inlet"
export H_INTERNAL="$h_internal"
export OH_INTERNAL="$oh_internal"
export NPX
export NPY
export NPZ
export COARSE_NX
export COARSE_NY
export COARSE_NZ
export GCFOAM_ASURF_REACTIVE_THETA_FLOOR="${GCFOAM_ASURF_REACTIVE_THETA_FLOOR:-0.0}"
export GCFOAM_REACTIVE_INLET_THETA_MIN="${GCFOAM_REACTIVE_INLET_THETA_MIN:-0.99}"
export CASE_IS_PARALLEL="0"
if [ -d "processor0" ]; then
    export CASE_IS_PARALLEL="1"
fi

python - <<'PY'
import os
import re
from pathlib import Path
from typing import Optional

import numpy as np


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


def read_label_list(path: Path) -> list[int]:
    text = path.read_text()
    m = re.search(
        r"\n\s*(\d+)\s*\((.*?)\)\s*// \*",
        text,
        re.S,
    )
    if not m:
        raise RuntimeError(f"Expected label list in {path}")
    count = int(m.group(1))
    values = [int(x) for x in m.group(2).split()]
    if len(values) != count:
        raise RuntimeError(f"Label count mismatch in {path}")
    return values


def read_n_faces(boundary_path: Path, patch_name: str) -> int:
    text = boundary_path.read_text()
    m = re.search(rf"\n\s*{re.escape(patch_name)}\s*\n\s*\{{(.*?)\n\s*\}}", text, re.S)
    if not m:
        raise RuntimeError(f"Could not find patch {patch_name} in {boundary_path}")
    fm = re.search(r"nFaces\s+(\d+);", m.group(1))
    if not fm:
        raise RuntimeError(f"Could not find nFaces for patch {patch_name} in {boundary_path}")
    return int(fm.group(1))


def partition_sizes(n_cells: int, n_parts: int) -> list[int]:
    base, rem = divmod(n_cells, n_parts)
    return [base + (1 if i < rem else 0) for i in range(n_parts)]


def replace_object(text: str, name: str) -> str:
    return re.sub(r"object\s+\S+;", f"object      {name};", text, count=1)


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


def fixed_value_nonuniform_body(values: list[float]) -> str:
    body = (
        "        type            fixedValue;\n"
        "        value           nonuniform List<scalar>\n"
        f"        {len(values)}\n"
        "        (\n"
    )
    body += "\n".join(f"        {value:.8g}" for value in values)
    body += "\n        )\n        ;\n"
    return body


def zero_gradient_body() -> str:
    return "        type            zeroGradient;\n"


def write_species(
    template_path: Path,
    out_path: Path,
    name: str,
    dims: str,
    internal: str,
    inlet_mode: str,
    inlet_value: Optional[str],
    inlet_values: Optional[list[float]] = None,
) -> None:
    text = template_path.read_text()
    text = replace_object(text, name)
    text = replace_dimensions(text, dims)
    text = replace_internal_uniform(text, internal)
    if inlet_mode == "fixedValue":
        if inlet_values is not None:
            text = patch_block(text, "inlet", fixed_value_nonuniform_body(inlet_values))
        else:
            text = patch_block(text, "inlet", fixed_value_body(inlet_value if inlet_value is not None else internal))
    else:
        text = patch_block(text, "inlet", zero_gradient_body())
    text = patch_block(text, "outlet", zero_gradient_body())
    wall_patch = '"wall_.*"' if '"wall_.*"' in text else "walls"
    text = patch_block(text, wall_patch, zero_gradient_body())
    out_path.write_text(text)


def make_eps_copy(template_path: Path, out_path: Path, name: str) -> None:
    text = template_path.read_text()
    text = replace_object(text, name)
    out_path.write_text(text)


def write_asurf_from_template(template_path: Path, out_path: Path, values: list[float]) -> None:
    text = template_path.read_text()
    text = replace_object(text, "aSurf")
    text = replace_dimensions(text, "[0 -1 0 0 0 0 0]")
    text = replace_internal_nonuniform(text, values)
    out_path.write_text(text)


aqueous_dims = "[0 -3 0 0 1 0 0]"
surface_dims = "[0 -2 0 0 1 0 0]"
theta_min = float(os.environ["GCFOAM_REACTIVE_INLET_THETA_MIN"])


def inlet_patch_values(
    eps_values: list[float],
    rank: int,
    fixed_value: str,
    background_value: str,
    n_faces: int,
) -> list[float]:
    if n_faces == 0:
        return []
    npx = int(os.environ["COARSE_NX"])
    npy = int(os.environ["COARSE_NY"])
    nproc_x = int(os.environ.get("NPX", "1"))
    nproc_y = int(os.environ.get("NPY", "1"))
    ipy = (rank % (nproc_x * nproc_y)) // nproc_x
    ipx = rank % nproc_x
    x_size = partition_sizes(npx, nproc_x)[ipx]
    y_size = partition_sizes(npy, nproc_y)[ipy]
    if len(eps_values) != x_size * y_size:
        raise RuntimeError(
            f"Unexpected eps length on processor{rank}: {len(eps_values)} != {x_size * y_size}"
        )
    eps = np.array(eps_values, dtype=float).reshape((y_size, x_size))
    values = [
        float(fixed_value) if theta > theta_min else float(background_value)
        for theta in eps[:, 0]
    ]
    if len(values) != n_faces:
        raise RuntimeError(f"Inlet face/value mismatch on processor{rank}: {len(values)} != {n_faces}")
    return values

if CASE_IS_PARALLEL:
    proc_dirs = sorted(ROOT.glob("processor*/0"))
    for proc_dir in proc_dirs:
        template_path = proc_dir / "T"
        eps_path = proc_dir / "eps"
        rank = int(proc_dir.parent.name.replace("processor", ""))
        eps_values = read_scalar_list(eps_path)
        n_inlet_faces = read_n_faces(proc_dir.parent / "constant" / "polyMesh" / "boundary", "inlet")
        cell_addressing = read_label_list(proc_dir.parent / "constant" / "polyMesh" / "cellProcAddressing")

        write_species(template_path, proc_dir / "Li+", "Li+", aqueous_dims, os.environ["LI_INTERNAL"], "fixedValue", os.environ["LI_INLET"], inlet_patch_values(eps_values, rank, os.environ["LI_INLET"], os.environ["LI_INTERNAL"], n_inlet_faces))
        write_species(template_path, proc_dir / "Na+", "Na+", aqueous_dims, os.environ["NA_INTERNAL"], "fixedValue", os.environ["NA_INLET"], inlet_patch_values(eps_values, rank, os.environ["NA_INLET"], os.environ["NA_INTERNAL"], n_inlet_faces))
        write_species(template_path, proc_dir / "K+", "K+", aqueous_dims, os.environ["K_INTERNAL"], "fixedValue", os.environ["K_INLET"], inlet_patch_values(eps_values, rank, os.environ["K_INLET"], os.environ["K_INTERNAL"], n_inlet_faces))
        write_species(template_path, proc_dir / "Mg+2", "Mg+2", aqueous_dims, os.environ["MG_INTERNAL"], "fixedValue", os.environ["MG_INLET"], inlet_patch_values(eps_values, rank, os.environ["MG_INLET"], os.environ["MG_INTERNAL"], n_inlet_faces))
        write_species(template_path, proc_dir / "Cl-", "Cl-", aqueous_dims, os.environ["CL_INTERNAL"], "fixedValue", os.environ["CL_INLET"], inlet_patch_values(eps_values, rank, os.environ["CL_INLET"], os.environ["CL_INTERNAL"], n_inlet_faces))
        write_species(template_path, proc_dir / "H+", "H+", aqueous_dims, os.environ["H_INTERNAL"], "fixedValue", os.environ["H_INTERNAL"], inlet_patch_values(eps_values, rank, os.environ["H_INTERNAL"], os.environ["H_INTERNAL"], n_inlet_faces))
        write_species(template_path, proc_dir / "OH-", "OH-", aqueous_dims, os.environ["OH_INTERNAL"], "fixedValue", os.environ["OH_INTERNAL"], inlet_patch_values(eps_values, rank, os.environ["OH_INTERNAL"], os.environ["OH_INTERNAL"], n_inlet_faces))
        write_species(template_path, proc_dir / "Sor_a-", "Sor_a-", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Sor_aLi", "Sor_aLi", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Sor_aNa", "Sor_aNa", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Sor_aK", "Sor_aK", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Sor_aMg+", "Sor_aMg+", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Sor_aH", "Sor_aH", surface_dims, "0", "zeroGradient", None)

        make_eps_copy(eps_path, proc_dir / "epsNum", "epsNum")
        make_eps_copy(eps_path, proc_dir / "theta", "theta")

        template_path.unlink(missing_ok=True)
else:
    zero_dir = ROOT / "0"
    template_path = zero_dir / "T"
    eps_path = zero_dir / "eps"

    eps_values = read_scalar_list(eps_path)
    n_inlet_faces = read_n_faces(ROOT / "constant" / "polyMesh" / "boundary", "inlet")
    write_species(template_path, zero_dir / "Li+", "Li+", aqueous_dims, os.environ["LI_INTERNAL"], "fixedValue", os.environ["LI_INLET"], inlet_patch_values(eps_values, 0, os.environ["LI_INLET"], os.environ["LI_INTERNAL"], n_inlet_faces))
    write_species(template_path, zero_dir / "Na+", "Na+", aqueous_dims, os.environ["NA_INTERNAL"], "fixedValue", os.environ["NA_INLET"], inlet_patch_values(eps_values, 0, os.environ["NA_INLET"], os.environ["NA_INTERNAL"], n_inlet_faces))
    write_species(template_path, zero_dir / "K+", "K+", aqueous_dims, os.environ["K_INTERNAL"], "fixedValue", os.environ["K_INLET"], inlet_patch_values(eps_values, 0, os.environ["K_INLET"], os.environ["K_INTERNAL"], n_inlet_faces))
    write_species(template_path, zero_dir / "Mg+2", "Mg+2", aqueous_dims, os.environ["MG_INTERNAL"], "fixedValue", os.environ["MG_INLET"], inlet_patch_values(eps_values, 0, os.environ["MG_INLET"], os.environ["MG_INTERNAL"], n_inlet_faces))
    write_species(template_path, zero_dir / "Cl-", "Cl-", aqueous_dims, os.environ["CL_INTERNAL"], "fixedValue", os.environ["CL_INLET"], inlet_patch_values(eps_values, 0, os.environ["CL_INLET"], os.environ["CL_INTERNAL"], n_inlet_faces))
    write_species(template_path, zero_dir / "H+", "H+", aqueous_dims, os.environ["H_INTERNAL"], "fixedValue", os.environ["H_INTERNAL"], inlet_patch_values(eps_values, 0, os.environ["H_INTERNAL"], os.environ["H_INTERNAL"], n_inlet_faces))
    write_species(template_path, zero_dir / "OH-", "OH-", aqueous_dims, os.environ["OH_INTERNAL"], "fixedValue", os.environ["OH_INTERNAL"], inlet_patch_values(eps_values, 0, os.environ["OH_INTERNAL"], os.environ["OH_INTERNAL"], n_inlet_faces))
    write_species(template_path, zero_dir / "Sor_a-", "Sor_a-", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Sor_aLi", "Sor_aLi", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Sor_aNa", "Sor_aNa", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Sor_aK", "Sor_aK", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Sor_aMg+", "Sor_aMg+", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Sor_aH", "Sor_aH", surface_dims, "0", "zeroGradient", None)

    make_eps_copy(eps_path, zero_dir / "epsNum", "epsNum")
    make_eps_copy(eps_path, zero_dir / "theta", "theta")
    template_path.unlink(missing_ok=True)
PY

python ../scripts/write_intrinsic_asurf.py . ../shared/metadata.json

echo "Reactive transport case initialised for reactiveScalarTransportDBSFoam."
