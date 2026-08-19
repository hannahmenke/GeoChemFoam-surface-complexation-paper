#!/usr/bin/env python3

from __future__ import annotations

import argparse
import csv
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np

REPO_ROOT = Path(__file__).resolve().parents[4]
import sys
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.measureSphereSurfaceArea import patch_area


def write_cylinder_stl(path: Path, radius: float, zmin: float, zmax: float, nseg: int = 720) -> None:
    lines = ["solid post\n"]
    for i in range(nseg):
        a0 = 2.0 * math.pi * i / nseg
        a1 = 2.0 * math.pi * (i + 1) / nseg
        p0 = np.array([radius * math.cos(a0), radius * math.sin(a0), zmin])
        p1 = np.array([radius * math.cos(a1), radius * math.sin(a1), zmin])
        p2 = np.array([radius * math.cos(a1), radius * math.sin(a1), zmax])
        p3 = np.array([radius * math.cos(a0), radius * math.sin(a0), zmax])
        normal = np.array([math.cos(0.5 * (a0 + a1)), math.sin(0.5 * (a0 + a1)), 0.0])
        for tri in ((p0, p1, p2), (p0, p2, p3)):
            lines.append(f"  facet normal {normal[0]:.12e} {normal[1]:.12e} {normal[2]:.12e}\n")
            lines.append("    outer loop\n")
            for point in tri:
                lines.append(f"      vertex {point[0]:.12e} {point[1]:.12e} {point[2]:.12e}\n")
            lines.append("    endloop\n")
            lines.append("  endfacet\n")
    lines.append("endsolid post\n")
    path.write_text("".join(lines))


def write_block_mesh_dict(path: Path, nxy: int, radius: float, pad: float, thickness: float) -> None:
    half_xy = radius + pad
    half_z = 0.5 * thickness
    path.write_text(
        f"""FoamFile
{{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      blockMeshDict;
}}
convertToMeters 1;
vertices
(
    ({-half_xy:.12e} {-half_xy:.12e} {-half_z:.12e})
    ({half_xy:.12e} {-half_xy:.12e} {-half_z:.12e})
    ({half_xy:.12e} {half_xy:.12e} {-half_z:.12e})
    ({-half_xy:.12e} {half_xy:.12e} {-half_z:.12e})
    ({-half_xy:.12e} {-half_xy:.12e} {half_z:.12e})
    ({half_xy:.12e} {-half_xy:.12e} {half_z:.12e})
    ({half_xy:.12e} {half_xy:.12e} {half_z:.12e})
    ({-half_xy:.12e} {half_xy:.12e} {half_z:.12e})
);
blocks
(
    hex (0 1 2 3 4 5 6 7) ({nxy} {nxy} 1) simpleGrading (1 1 1)
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
    )


def write_snappy_dict(path: Path, radius: float, pad: float) -> None:
    keep_x = radius + 0.5 * pad
    path.write_text(
        f"""FoamFile
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
    post.stl
    {{
        type triSurfaceMesh;
        name post;
    }}
}}
castellatedMeshControls
{{
    maxLocalCells 50000000;
    maxGlobalCells 50000000;
    minRefinementCells 0;
    maxLoadUnbalance 0.1;
    nCellsBetweenLevels 1;
    features ();
    refinementSurfaces
    {{
        post
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
    )


def prepare_case(case_dir: Path, radius: int, thickness: float) -> None:
    pad = max(8, int(math.ceil(0.5 * radius)))
    nxy = 2 * radius + 2 * pad
    if case_dir.exists():
        subprocess.run(["rm", "-rf", str(case_dir)], check=True)
    (case_dir / "system").mkdir(parents=True)
    (case_dir / "constant" / "triSurface").mkdir(parents=True)
    write_cylinder_stl(case_dir / "constant" / "triSurface" / "post.stl", radius, -2.0 * thickness, 2.0 * thickness)
    write_block_mesh_dict(case_dir / "system" / "blockMeshDict", nxy, radius, pad, thickness)
    write_snappy_dict(case_dir / "system" / "snappyHexMeshDict", radius, pad)
    (case_dir / "system" / "controlDict").write_text(
        """FoamFile
{
    version     2.0;
    format      ascii;
    class       dictionary;
    object      controlDict;
}
application     snappyHexMesh;
startFrom       startTime;
startTime       0;
stopAt          endTime;
endTime         1;
deltaT          1;
writeControl    timeStep;
writeInterval   1;
purgeWrite      0;
writeFormat     ascii;
writePrecision  8;
writeCompression off;
timeFormat      general;
timePrecision   6;
runTimeModifiable true;
"""
    )
    template_system = REPO_ROOT / "tutorials" / "stressAnalysis" / "solidDisplacementElasticVOSFoam" / "spheresVOS" / "system"
    for name in ("fvSchemes", "fvSolution"):
        shutil.copy(template_system / name, case_dir / "system" / name)


def run_case(case_dir: Path) -> None:
    with (case_dir / "blockMesh.out").open("w") as handle:
        subprocess.run(["blockMesh"], cwd=case_dir, stdout=handle, stderr=subprocess.STDOUT, check=True)
    with (case_dir / "snappyHexMesh.out").open("w") as handle:
        subprocess.run(["snappyHexMesh", "-overwrite"], cwd=case_dir, stdout=handle, stderr=subprocess.STDOUT, check=True)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--radii", nargs="*", type=int, default=[8, 16, 32, 64])
    parser.add_argument("--thickness", type=float, default=1.0)
    args = parser.parse_args()

    rows = []
    for radius in args.radii:
        case_dir = args.output_dir / f"post_r{radius:02d}" / "snappy"
        prepare_case(case_dir, radius, args.thickness)
        run_case(case_dir)
        area = patch_area(case_dir / "constant" / "polyMesh", "post")
        reference = 2.0 * math.pi * radius * args.thickness
        rows.append(
            {
                "method": "snappy",
                "radius_over_dx": radius,
                "area": area,
                "analytic_area": reference,
                "rel_err_vs_analytic": (area - reference) / reference,
            }
        )

    output_csv = args.output_dir / "area_metrics.csv"
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    with output_csv.open("w", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["method", "radius_over_dx", "area", "analytic_area", "rel_err_vs_analytic"],
        )
        writer.writeheader()
        writer.writerows(rows)

    for row in rows:
        print(
            f"R/dx={row['radius_over_dx']:g} "
            f"area={row['area']:.12e} "
            f"rel={row['rel_err_vs_analytic']:+.6%}"
        )


if __name__ == "__main__":
    main()
