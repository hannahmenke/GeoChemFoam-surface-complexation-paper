#!/usr/bin/env bash

set -Eeuo pipefail
cd "$(dirname "$0")"

repo_root="$(cd ../../../.. && pwd)"
generated_root="$PWD/generated"
results_root="$PWD/results"

if ! command -v blockMesh >/dev/null 2>&1; then
    # shellcheck disable=SC1091
    source /usr/lib/openfoam/openfoam2512/etc/bashrc
fi

levels=("$@")
if [ "${#levels[@]}" -eq 0 ]; then
    levels=(8 16 32 64)
fi

for level in "${levels[@]}"; do
    name="$(printf 'sphere_r%02d' "$level")"
    asset_dir="$generated_root/$name"
    metadata="$asset_dir/$name.json"
    case_dir="$results_root/$name/snappy"

    if [ ! -f "$metadata" ]; then
        echo "Missing $metadata; run ./runAll.sh first" >&2
        exit 1
    fi

    rm -rf "$case_dir"
    mkdir -p "$case_dir/constant/triSurface" "$case_dir/system"
    cp "$asset_dir/${name}_analytic.stl" "$case_dir/constant/triSurface/"

    python - "$case_dir" "$metadata" "$name" <<'PY'
import json
import sys
from pathlib import Path

case = Path(sys.argv[1])
meta = json.loads(Path(sys.argv[2]).read_text())
name = sys.argv[3]
nx, ny, nz = (int(meta[key]) for key in ("nx", "ny", "nz"))
dx = float(meta["dx"])
radius = float(meta["radius"])
hx, hy, hz = (0.5 * n * dx for n in (nx, ny, nz))
keep_x = min(2.0 * radius, hx - 2.0 * dx)

(case / "system/controlDict").write_text("""FoamFile { version 2.0; format ascii; class dictionary; object controlDict; }
application foamRun; startFrom startTime; startTime 0; stopAt endTime; endTime 1;
deltaT 1; writeControl timeStep; writeInterval 1; runTimeModifiable false;
""")
(case / "system/blockMeshDict").write_text(f"""FoamFile {{ version 2.0; format ascii; class dictionary; object blockMeshDict; }}
convertToMeters 1;
vertices
(
({-hx} {-hy} {-hz}) ({hx} {-hy} {-hz}) ({hx} {hy} {-hz}) ({-hx} {hy} {-hz})
({-hx} {-hy} {hz}) ({hx} {-hy} {hz}) ({hx} {hy} {hz}) ({-hx} {hy} {hz})
);
blocks (hex (0 1 2 3 4 5 6 7) ({nx} {ny} {nz}) simpleGrading (1 1 1));
edges ();
boundary (outer {{ type patch; faces ((0 4 7 3) (1 2 6 5) (0 1 5 4) (3 7 6 2) (0 3 2 1) (4 5 6 7)); }});
mergePatchPairs ();
""")
(case / "system/snappyHexMeshDict").write_text(f"""FoamFile {{ version 2.0; format ascii; class dictionary; object snappyHexMeshDict; }}
castellatedMesh true; snap true; addLayers false;
geometry {{ {name}_analytic.stl {{ type triSurfaceMesh; name sphere; }} }}
castellatedMeshControls
{{
 maxLocalCells 500000000; maxGlobalCells 500000000; minRefinementCells 0;
 maxLoadUnbalance 0.1; nCellsBetweenLevels 1; features ();
 refinementSurfaces {{ sphere {{ level (0 0); }} }}
 resolveFeatureAngle 30; refinementRegions {{}};
 locationInMesh ({keep_x} 0 0); allowFreeStandingZoneFaces false;
}}
snapControls {{ nSmoothPatch 2; tolerance 2.0; nSolveIter 30; nRelaxIter 10; }}
addLayersControls
{{
 relativeSizes true; layers {{}}; expansionRatio 1; finalLayerThickness 1;
 minThickness 1e-13; nGrow 0; featureAngle 180; nRelaxIter 3;
 nSmoothSurfaceNormals 1; nSmoothNormals 3; nSmoothThickness 10;
 maxFaceThicknessRatio 0.5; maxThicknessToMedialRatio 0.3;
 minMedianAxisAngle 90; nBufferCellsNoExtrude 0; nLayerIter 50;
}}
meshQualityControls
{{
 maxNonOrtho 180; maxBoundarySkewness 20; maxInternalSkewness 20;
 maxConcave 80; minFlatness 0.5; minVol 1e-30; minTetQuality 1e-15;
 minArea -1; minTwist 0.02; minDeterminant 0.001; minFaceWeight 0.02;
 minVolRatio 0.01; minTriangleTwist -1; nSmoothScale 4; errorReduction 0.75;
}}
mergeTolerance 1e-6;
""")
PY

    (
        cd "$case_dir"
        blockMesh > blockMesh.out 2>&1
        snappyHexMesh -overwrite > snappyHexMesh.out 2>&1
    )
    python "$repo_root/scripts/measureSphereSurfaceArea.py" \
        --reference-json "$metadata" \
        --snappy-case "$case_dir" \
        --output-dir "$results_root/$name"
done
