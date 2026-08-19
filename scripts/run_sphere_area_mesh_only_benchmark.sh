#!/usr/bin/env bash

set -Eeuo pipefail

repo_root="$(cd "$(dirname "$0")"/.. && pwd)"
benchmark_dir="$repo_root/papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_sphere_surface_area_benchmark"
generated_root="$benchmark_dir/generated"
results_root="$benchmark_dir/results"

levels=("$@")
if [ "${#levels[@]}" -eq 0 ]; then
    levels=(8 16)
fi

source_gcfoam_env() {
    if [ -f /usr/local/anaconda3/etc/profile.d/conda.sh ]; then
        set +e
        set +u
        # shellcheck disable=SC1091
        source /usr/local/anaconda3/etc/profile.d/conda.sh
        conda activate gcfoam >/dev/null 2>&1 || true
        set -e
        set -u
    fi
    if [ -f "$repo_root/etc/bashrc" ]; then
        set +e
        set +u
        # shellcheck disable=SC1090
        source "$repo_root/etc/bashrc" >/dev/null 2>&1
        set -e
        set -u
    fi
}

write_indicator_fields_from_raw() {
    local case_dir="$1"
    local raw_path="$2"
    local pore_value="${3:-255}"
    local solid_floor="${4:-0.0001}"
    python - <<'PY' "$case_dir" "$raw_path" "$pore_value" "$solid_floor"
from pathlib import Path
import json
import re
import sys

case_dir = Path(sys.argv[1])
raw_path = Path(sys.argv[2])
pore_value = int(sys.argv[3])
solid_floor = float(sys.argv[4])

raw_stem = raw_path.stem
parts = raw_stem.split("_r")
if len(parts) != 2:
    raise SystemExit(f"Cannot infer metadata name from raw path: {raw_path}")
meta_path = raw_path.with_name(f"{raw_stem}.json")
meta = json.loads(meta_path.read_text())
nx = int(meta["nx"])
ny = int(meta["ny"])
nz = int(meta["nz"])

raw = raw_path.read_bytes()
expected_size = nx * ny * nz
if len(raw) != expected_size:
    raise SystemExit(
        f"Raw size mismatch for {raw_path}: got {len(raw)}, expected {expected_size}"
    )

values = [1.0 if byte == pore_value else solid_floor for byte in raw]

template_path = case_dir / "0" / "eps"
template = template_path.read_text()
boundary_match = re.search(r"boundaryField\s*(\{.*\})\s*// \*+", template, re.S)
if not boundary_match:
    raise SystemExit(f"Failed to extract boundaryField from {template_path}")
boundary_block = boundary_match.group(1)

header = """FoamFile
{{
    version     2.0;
    format      ascii;
    class       volScalarField;
    location    "0";
    object      {object_name};
}}
"""

values_text = "\n".join(f"{value:.12g}" for value in values)

for object_name in ("eps", "theta", "epsNum"):
    out_path = case_dir / "0" / object_name
    out_text = (
        "/*--------------------------------*- C++ -*----------------------------------*\\\\n"
        "| =========                 |                                                 |\n"
        "| \\\\      /  F ield         | OpenFOAM: The Open Source CFD Toolbox           |\n"
        "|  \\\\    /   O peration     | Version:  2512                                  |\n"
        "|   \\\\  /    A nd           | Website:  www.openfoam.com                      |\n"
        "|    \\\\/     M anipulation  |                                                 |\n"
        "\\*---------------------------------------------------------------------------*/\n"
        + header.format(object_name=object_name)
        + "// * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * * //\n\n"
        + "dimensions      [0 0 0 0 0 0 0];\n\n"
        + f"internalField   nonuniform List<scalar>\n{len(values)}\n(\n{values_text}\n);\n\n"
        + "boundaryField\n"
        + boundary_block
        + "\n\n// ************************************************************************* //\n"
    )
    out_path.write_text(out_text)
PY
}

materialize_dbs_indicator_fields() {
    local case_dir="$1"
    python - <<'PY' "$case_dir"
from pathlib import Path
import re
import sys

case_dir = Path(sys.argv[1])
eps_path = case_dir / "0" / "eps"
theta_path = case_dir / "0" / "theta"
epsnum_path = case_dir / "0" / "epsNum"

text = eps_path.read_text()

def rewrite_object(src: str, obj_name: str) -> str:
    return re.sub(r"object\s+\S+;", f"object      {obj_name};", src, count=1)

theta_path.write_text(rewrite_object(text, "theta"))
epsnum_path.write_text(rewrite_object(text, "epsNum"))
PY
}

copy_case_tree() {
    local src="$1"
    local dst="$2"
    rm -rf "$dst"
    mkdir -p "$dst"
    cp -a "$src"/system "$dst"/
    cp -a "$src"/*.sh "$dst"/ 2>/dev/null || true
}

prepare_snappy_case() {
    local case_dir="$1"
    local asset_dir="$2"
    local name="$3"
    local meta_json="$4"

    rm -rf "$case_dir"
    mkdir -p "$case_dir/system" "$case_dir/constant/triSurface"
    cp "$asset_dir/${name}_analytic.stl" "$case_dir/constant/triSurface/"
    cp "$repo_root/tutorials/stressAnalysis/solidDisplacementElasticVOSFoam/spheresVOS/system/fvSchemes" "$case_dir/system/"
    cp "$repo_root/tutorials/stressAnalysis/solidDisplacementElasticVOSFoam/spheresVOS/system/fvSolution" "$case_dir/system/"
    cp "$repo_root/tutorials/stressAnalysis/solidDisplacementElasticVOSFoam/spheresVOS/system/controlDict" "$case_dir/system/"

    python - <<'PY' "$case_dir" "$name" "$meta_json"
import json
from pathlib import Path
import sys

case_dir = Path(sys.argv[1])
name = sys.argv[2]
meta = json.loads(Path(sys.argv[3]).read_text())

nx = int(meta["nx"])
ny = int(meta["ny"])
nz = int(meta["nz"])
dx = float(meta["dx"])
radius = float(meta["radius"])

half_x = 0.5 * nx * dx
half_y = 0.5 * ny * dx
half_z = 0.5 * nz * dx
keep_x = min(2.0 * radius, half_x - 2.0 * dx)

block_mesh = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}}
convertToMeters 1;
vertices
(
    ({-half_x:.12e} {-half_y:.12e} {-half_z:.12e})
    ({half_x:.12e} {-half_y:.12e} {-half_z:.12e})
    ({half_x:.12e} {half_y:.12e} {-half_z:.12e})
    ({-half_x:.12e} {half_y:.12e} {-half_z:.12e})
    ({-half_x:.12e} {-half_y:.12e} {half_z:.12e})
    ({half_x:.12e} {-half_y:.12e} {half_z:.12e})
    ({half_x:.12e} {half_y:.12e} {half_z:.12e})
    ({-half_x:.12e} {half_y:.12e} {half_z:.12e})
);
blocks
(
    hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1)
);
edges
(
);
boundary
(
    outer
    {{
        type patch;
        faces
        (
            (0 4 7 3)
            (1 2 6 5)
            (0 1 5 4)
            (3 7 6 2)
            (0 3 2 1)
            (4 5 6 7)
        );
    }}
);
mergePatchPairs
(
);
"""

snappy = f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      snappyHexMeshDict;
}}
castellatedMesh true;
snap true;
addLayers false;
geometry
{{
    {name}_analytic.stl
    {{
        type triSurfaceMesh;
        name sphere;
    }}
}}
castellatedMeshControls
{{
    maxLocalCells 500000000;
    maxGlobalCells 500000000;
    minRefinementCells 0;
    maxLoadUnbalance 0.1;
    nCellsBetweenLevels 1;
    features ();
    refinementSurfaces
    {{
        sphere
        {{
            level (0 0);
        }}
    }}
    resolveFeatureAngle 30;
    refinementRegions {{}}
    locationInMesh ({keep_x:.12e} 0 0);
    allowFreeStandingZoneFaces false;
}}
snapControls
{{
    nSmoothPatch 2;
    tolerance 2.0;
    nSolveIter 30;
    nRelaxIter 10;
}}
addLayersControls
{{
    relativeSizes true;
    layers {{}}
    expansionRatio 1;
    finalLayerThickness 1.0;
    minThickness 1e-13;
    nGrow 0;
    featureAngle 180;
    slipFeatureAngle 30;
    nRelaxIter 3;
    nSmoothSurfaceNormals 1;
    nSmoothNormals 3;
    nSmoothThickness 10;
    maxFaceThicknessRatio 0.5;
    maxThicknessToMedialRatio 0.3;
    minMedianAxisAngle 90;
    nBufferCellsNoExtrude 0;
    nLayerIter 50;
}}
meshQualityControls
{{
    maxNonOrtho 180;
    maxBoundarySkewness 20;
    maxInternalSkewness 20;
    maxConcave 80;
    minFlatness 0.5;
    minVol 1e-30;
    minTetQuality 1e-15;
    minArea -1;
    minTwist 0.02;
    minDeterminant 0.001;
    minFaceWeight 0.02;
    minVolRatio 0.01;
    minTriangleTwist -1;
    nSmoothScale 4;
    errorReduction 0.75;
}}
mergeTolerance 1e-6;
"""

(case_dir / "system" / "blockMeshDict").write_text(block_mesh)
(case_dir / "system" / "snappyHexMeshDict").write_text(snappy)
PY
}

prepare_subset_case() {
    local case_dir="$1"
    local asset_dir="$2"
    local name="$3"
    local meta_json="$4"

    prepare_dbs_case "$case_dir" "$asset_dir" "$name" "$meta_json"

    cat > "$case_dir/system/topoSetDict" <<'EOF'
FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      topoSetDict;
}

actions
(
    {
        name    solidCells;
        type    cellSet;
        action  new;
        source  fieldToCell;

        sourceInfo
        {
            field   epsNum;
            min     0;
            max     0.5;
        }
    }
);
EOF

}

prepare_dbs_case() {
    local case_dir="$1"
    local asset_dir="$2"
    local name="$3"
    local meta_json="$4"

    copy_case_tree \
        "$repo_root/tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/2DHM12SolidGrainsSurfaceComplexation" \
        "$case_dir"

    python - <<'PY' "$case_dir/createMesh.sh" "$name" "$asset_dir" "$meta_json"
from pathlib import Path
import json
import re
import sys

path = Path(sys.argv[1])
name = sys.argv[2]
asset_dir = sys.argv[3]
meta = json.loads(Path(sys.argv[4]).read_text())

nx = int(meta["nx"]); ny = int(meta["ny"]); nz = int(meta["nz"])
dx = float(meta["dx"])

text = path.read_text()
replacements = {
    r'Source_image_name="[^"]+"': f'Source_image_name="{name}"',
    r'Image_name="[^"]+"': f'Image_name="{name}_thr120"',
    r'dir="[^"]+"': f'dir="{asset_dir}"',
    r"compressed='[^']+'": "compressed='yes'",
    r'x_dim=\d+': f'x_dim={nx}',
    r'y_dim=\d+': f'y_dim={ny}',
    r'z_dim=\d+': f'z_dim={nz}',
    r'pores_value=\d+': 'pores_value=255',
    r'solid_value=\d+': 'solid_value=0',
    r'phases=\([^)]+\)': 'phases=(0,255)',
    r'micro_por=\([^)]+\)': 'micro_por=(0.0001,1)',
    r'x_min=\d+': 'x_min=0',
    r'x_max=\d+': f'x_max={nx}',
    r'y_min=\d+': 'y_min=0',
    r'y_max=\d+': f'y_max={ny}',
    r'z_min=\d+': 'z_min=0',
    r'z_max=\d+': f'z_max={nz}',
    r'padWidth=\d+': 'padWidth=0',
    r'res=[0-9.eE+-]+': f'res={dx:.12e}',
    r'n_x=\d+': f'n_x={nx}',
    r'n_y=\d+': f'n_y={ny}',
    r'n_z=\d+': f'n_z={nz}',
    r'NPX=\d+': 'NPX=1',
    r'NPY=\d+': 'NPY=1',
    r'NPZ=\d+': 'NPZ=1',
}
for pattern, repl in replacements.items():
    text = re.sub(pattern, repl, text, count=1)
text = text.replace('dimension="2D"', 'dimension="3D"')
text = text.replace('src = Path("HM12_2_4.raw")', f'src = Path("{name}.raw")')
text = text.replace('dst = Path("HM12_2_4_thr120.raw")', f'dst = Path("{name}_thr120.raw")')
path.write_text(text)
PY
}

prepare_dbs_fallback_control_dict() {
    local control_dict="$1"
    python - <<'PY' "$control_dict"
from pathlib import Path
import re
import sys

path = Path(sys.argv[1])
text = path.read_text()
entries = {
    "surfaceAreaSource": "fvIndicator",
    "surfaceAreaIndicatorField": "epsNum",
    "surfaceAreaIntrinsicAssembly": "none",
    "surfaceAreaWriteComputedField": "true",
}
for key, value in entries.items():
    pattern = rf"^\s*{re.escape(key)}\s+.*?;\s*$"
    replacement = f"{key:<28}{value};"
    if re.search(pattern, text, flags=re.M):
        text = re.sub(pattern, replacement, text, count=1, flags=re.M)
    else:
        marker = "runTimeModifiable yes;"
        if marker in text:
            text = text.replace(marker, marker + "\n\n" + replacement)
        else:
            text += "\n" + replacement + "\n"
path.write_text(text)
PY
}

run_level() {
    local level="$1"
    local name
    name="$(printf 'sphere_r%02d' "$level")"
    local asset_dir="$generated_root/$name"
    local meta_json="$asset_dir/$name.json"
    local level_root="$results_root/$name"
    local snappy_case="$level_root/snappy"
    local subset_case="$level_root/subset"
    local dbs_file_case="$level_root/dbs-file"
    local dbs_fallback_case="$level_root/dbs-fallback"
    local dbs_smoothed_case="$level_root/dbs-smoothed-mc"

    if [ ! -f "$meta_json" ]; then
        echo "Missing generated assets for $name under $asset_dir" >&2
        exit 1
    fi

    read -r nx ny nz dx image_name <<EOF
$(python - <<'PY' "$meta_json"
import json,sys
meta=json.load(open(sys.argv[1]))
print(meta["nx"], meta["ny"], meta["nz"], f"{meta['dx']:.12e}", f"{meta['name']}_thr120")
PY
)
EOF

    echo "=== Sphere area benchmark: $name ==="
    rm -rf "$level_root"
    mkdir -p "$level_root"

    echo "--- Preparing snappy case ---"
    prepare_snappy_case "$snappy_case" "$asset_dir" "$name" "$meta_json"
    (
        source_gcfoam_env
        cd "$snappy_case"
        blockMesh > blockMesh.out 2>&1
        snappyHexMesh -overwrite > snappyHexMesh.out 2>&1
    )

    echo "--- Preparing subsetMesh case ---"
    prepare_subset_case "$subset_case" "$asset_dir" "$name" "$meta_json"
    (
        source_gcfoam_env
        cd "$subset_case"
        ./createMesh.sh > createMesh.out 2>&1
        write_indicator_fields_from_raw "$PWD" "$asset_dir/${name}.raw" 255 0.0001
        topoSet > topoSet.out 2>&1
        subsetMesh solidCells -patch sphere -overwrite > subsetMesh.out 2>&1
    )

    echo "--- Preparing DBS file case ---"
    prepare_dbs_case "$dbs_file_case" "$asset_dir" "$name" "$meta_json"
    (
        source_gcfoam_env
        cd "$dbs_file_case"
        ./createMesh.sh > createMesh.out 2>&1
        materialize_dbs_indicator_fields "$PWD"
        mkdir -p constant/triSurface
        cp "$asset_dir/${name}.raw" "constant/triSurface/${name}.raw"
        cp "$asset_dir/${name}.raw" "constant/triSurface/${image_name}.raw"
        python "$GCFOAM_DIR/applications/utilities/pyTools/createASurfPhases.py" \
            "$nx" "$ny" "$nz" \
            0 "$nx" 0 "$ny" 0 "$nz" \
            "$nx" "$ny" "$nz" \
            "$dx" \
            "$image_name" \
            0 255 0 3D 0 aSurf > createASurf.out 2>&1
    )

    echo "--- Preparing DBS fallback case ---"
    cp -a "$dbs_file_case" "$dbs_fallback_case"
    rm -f "$dbs_fallback_case/0/aSurf"
    prepare_dbs_fallback_control_dict "$dbs_fallback_case/system/controlDict"
    materialize_dbs_indicator_fields "$dbs_fallback_case"
    (
        source_gcfoam_env
        cd "$repo_root/applications/solvers/reactiveTransport/aSurfFieldProbeFoam"
        wmake > "$level_root/aSurfFieldProbeFoam.wmake.out" 2>&1
    )
    (
        source_gcfoam_env
        cd "$dbs_fallback_case"
        aSurfFieldProbeFoam > aSurfFieldProbeFoam.out 2>&1
    )

    echo "--- Preparing DBS smoothed marching-cubes case ---"
    cp -a "$dbs_file_case" "$dbs_smoothed_case"
    (
        source_gcfoam_env
        cd "$dbs_smoothed_case"
        python "$GCFOAM_DIR/applications/utilities/pyTools/createASurfMarchingCubes.py" \
            "$nx" "$ny" "$nz" \
            0 "$nx" 0 "$ny" 0 "$nz" \
            "$nx" "$ny" "$nz" \
            "$dx" \
            "$name" \
            255 0 3D aSurfSmooth occupancyGaussian 0.75 > createASurfSmooth.out 2>&1
    )

    local dbs_fallback_time="0"
    if [ ! -f "$dbs_fallback_case/0/aSurf" ] && [ -f "$dbs_fallback_case/1/aSurf" ]; then
        dbs_fallback_time="1"
    fi

    echo "--- Analyzing $name ---"
    python "$repo_root/scripts/analyze_sphere_area_benchmark.py" \
        --reference-json "$meta_json" \
        --snappy-case "$snappy_case" \
        --subset-case "$subset_case" \
        --dbs-file-case "$dbs_file_case" \
        --dbs-fallback-case "$dbs_fallback_case" \
        --dbs-smoothed-case "$dbs_smoothed_case" \
        --snappy-patch "sphere" \
        --subset-patch "sphere" \
        --dbs-file-time "0" \
        --dbs-fallback-time "$dbs_fallback_time" \
        --dbs-smoothed-time "0" \
        --dbs-smoothed-field "aSurfSmooth" \
        --output-json "$level_root/area_metrics.json" \
        --output-csv "$level_root/area_metrics.csv" \
        --output-report "$level_root/area_report.md"

    echo "Report: $level_root/area_report.md"
}

mkdir -p "$results_root"

for level in "${levels[@]}"; do
    run_level "$level"
done
