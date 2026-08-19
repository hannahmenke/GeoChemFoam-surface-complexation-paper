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

# Sr2+/Ca2+ DGR scenario: Sr-90 leachate invades Ca2+-bearing limestone porewater.
# The domain starts at 1 mM Ca2+ (realistic formation water); the inlet carries
# 0.1 mM Sr2+ with no Ca. Ca2+ pre-loads surface sites (via SOLUTION 1 in
# phreeqcReactions); incoming Sr displaces Ca in a nonlinear chromatographic exchange.
ca_internal="1e-3"
ca_inlet="0"
sr_internal="0"
sr_inlet="1e-4"
cl_internal="2e-3"
cl_inlet="2e-4"
h_internal="1.051e-7"
oh_internal="1.069e-7"

# Binary quasi-2D micromodel comparison case:
# grain voxels are treated as solids; reactive area comes only from the
# pore/grain interface of the HM12 image.
export GCFOAM_ASURF_PROCS="${GCFOAM_ASURF_PROCS:-8}"

cp constant/transportProperties2 constant/transportProperties
cp constant/thermoPhysicalProperties1 constant/thermoPhysicalProperties

mkdir -p constant/triSurface
if [ ! -f constant/triSurface/HM12_2_4_thr120.raw ]; then
    if [ ! -f constant/triSurface/HM12_2_4.raw ]; then
        cp "$GCFOAM_IMG/raw/HM12_2_4.raw.tar.gz" constant/triSurface/.
        (
            cd constant/triSurface
            tar -xf HM12_2_4.raw.tar.gz
        )
    fi
    python - <<'PY'
import numpy as np
from pathlib import Path

src = Path("constant/triSurface/HM12_2_4.raw")
dst = Path("constant/triSurface/HM12_2_4_thr120.raw")
raw = np.fromfile(src, dtype=np.uint8)
binary = np.where(raw > 120, 255, 0).astype(np.uint8)
binary.tofile(dst)
print(f"Created {dst} from {src} with threshold 120")
PY
fi

NPX="$(tail -n 1 system/NPX)"
NPY="$(tail -n 1 system/NPY)"
NPZ="$(tail -n 1 system/NPZ)"
COARSE_NX="$(tail -n 1 system/Nx1)"
COARSE_NY="$(tail -n 1 system/Ny1)"
COARSE_NZ="$(tail -n 1 system/Nz1)"

python "$GCFOAM_DIR/applications/utilities/pyTools/createASurfPhases.py" \
    2000 2000 10 \
    700 1300 700 1300 1 2 \
    300 300 1 \
    3e-5 \
    HM12_2_4_thr120 \
    0 255 0 2D 0 aSurf fluid > createASurfReactive.out

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

export CA_INTERNAL="$ca_internal"
export CA_INLET="$ca_inlet"
export SR_INTERNAL="$sr_internal"
export SR_INLET="$sr_inlet"
export CL_INTERNAL="$cl_internal"
export CL_INLET="$cl_inlet"
export H_INTERNAL="$h_internal"
export OH_INTERNAL="$oh_internal"
export COARSE_NX
export COARSE_NY
export COARSE_NZ
export GCFOAM_ASURF_REACTIVE_THETA_FLOOR="${GCFOAM_ASURF_REACTIVE_THETA_FLOOR:-0.0}"
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


def zero_gradient_body() -> str:
    return "        type            zeroGradient;\n"


def write_species(template_path: Path, out_path: Path, name: str, dims: str, internal: str, inlet_mode: str, inlet_value: str | None) -> None:
    text = template_path.read_text()
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
reactive_theta_floor = float(os.environ["GCFOAM_ASURF_REACTIVE_THETA_FLOOR"])

asurf_global = read_scalar_list(ROOT / "0" / "aSurf")
coarse_nx = int(os.environ["COARSE_NX"])
coarse_ny = int(os.environ["COARSE_NY"])
coarse_nz = int(os.environ["COARSE_NZ"])

expected_asurf = coarse_nx * coarse_ny * coarse_nz
if len(asurf_global) != expected_asurf:
    raise RuntimeError(
        f"aSurf length mismatch: expected {expected_asurf}, got {len(asurf_global)}"
    )

if CASE_IS_PARALLEL:
    proc_dirs = sorted(ROOT.glob("processor*/0"))
    for proc_dir in proc_dirs:
        template_path = proc_dir / "T"
        eps_path = proc_dir / "eps"
        cell_addressing = read_label_list(proc_dir.parent / "constant" / "polyMesh" / "cellProcAddressing")

        write_species(template_path, proc_dir / "Ca+2", "Ca+2", aqueous_dims, os.environ["CA_INTERNAL"], "fixedValue", os.environ["CA_INLET"])
        write_species(template_path, proc_dir / "Sr+2", "Sr+2", aqueous_dims, os.environ["SR_INTERNAL"], "fixedValue", os.environ["SR_INLET"])
        write_species(template_path, proc_dir / "Cl-", "Cl-", aqueous_dims, os.environ["CL_INTERNAL"], "fixedValue", os.environ["CL_INLET"])
        write_species(template_path, proc_dir / "H+", "H+", aqueous_dims, os.environ["H_INTERNAL"], "fixedValue", os.environ["H_INTERNAL"])
        write_species(template_path, proc_dir / "OH-", "OH-", aqueous_dims, os.environ["OH_INTERNAL"], "fixedValue", os.environ["OH_INTERNAL"])
        write_species(template_path, proc_dir / "Surf_a-", "Surf_a-", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Surf_aCa+", "Surf_aCa+", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Surf_aSr+", "Surf_aSr+", surface_dims, "0", "zeroGradient", None)
        write_species(template_path, proc_dir / "Surf_aH", "Surf_aH", surface_dims, "0", "zeroGradient", None)

        make_eps_copy(eps_path, proc_dir / "epsNum", "epsNum")
        make_eps_copy(eps_path, proc_dir / "theta", "theta")

        local_values = [
            asurf_global[celli] if celli >= 0 else 0.0
            for celli in cell_addressing
        ]
        eps_values = read_scalar_list(eps_path)
        if len(eps_values) != len(local_values):
            raise RuntimeError("eps/aSurf local length mismatch")
        local_values = [
            value if theta_value > reactive_theta_floor else 0.0
            for value, theta_value in zip(local_values, eps_values)
        ]
        write_asurf_from_template(eps_path, proc_dir / "aSurf", local_values)

        template_path.unlink(missing_ok=True)
else:
    zero_dir = ROOT / "0"
    template_path = zero_dir / "T"
    eps_path = zero_dir / "eps"

    write_species(template_path, zero_dir / "Ca+2", "Ca+2", aqueous_dims, os.environ["CA_INTERNAL"], "fixedValue", os.environ["CA_INLET"])
    write_species(template_path, zero_dir / "Sr+2", "Sr+2", aqueous_dims, os.environ["SR_INTERNAL"], "fixedValue", os.environ["SR_INLET"])
    write_species(template_path, zero_dir / "Cl-", "Cl-", aqueous_dims, os.environ["CL_INTERNAL"], "fixedValue", os.environ["CL_INLET"])
    write_species(template_path, zero_dir / "H+", "H+", aqueous_dims, os.environ["H_INTERNAL"], "fixedValue", os.environ["H_INTERNAL"])
    write_species(template_path, zero_dir / "OH-", "OH-", aqueous_dims, os.environ["OH_INTERNAL"], "fixedValue", os.environ["OH_INTERNAL"])
    write_species(template_path, zero_dir / "Surf_a-", "Surf_a-", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Surf_aCa+", "Surf_aCa+", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Surf_aSr+", "Surf_aSr+", surface_dims, "0", "zeroGradient", None)
    write_species(template_path, zero_dir / "Surf_aH", "Surf_aH", surface_dims, "0", "zeroGradient", None)

    make_eps_copy(eps_path, zero_dir / "epsNum", "epsNum")
    make_eps_copy(eps_path, zero_dir / "theta", "theta")
    eps_values = read_scalar_list(eps_path)
    if len(eps_values) != len(asurf_global):
        raise RuntimeError("eps/aSurf serial length mismatch")
    masked_values = [
        value if theta_value > reactive_theta_floor else 0.0
        for value, theta_value in zip(asurf_global, eps_values)
    ]
    write_asurf_from_template(eps_path, zero_dir / "aSurf", masked_values)
    template_path.unlink(missing_ok=True)
PY

echo "Reactive transport case initialised for reactiveScalarTransportDBSFoam."
