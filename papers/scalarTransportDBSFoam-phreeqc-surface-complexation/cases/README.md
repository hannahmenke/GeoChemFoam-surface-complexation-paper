# Paper Test-Case Asset Map

The cases are stored and run from this paper repository. Build the main-branch
GeoChemFoam solver in a separate checkout and either place it beside this
repository as `GeoChemFoam-main-runtime` or set `GCFOAM_RUNTIME_ROOT` to that
checkout. The case scripts use that checkout only as the solver runtime and do
not write to it.

The manuscript uses the following case ladder.

## 1D Analytical

- tracked case:
  - `tutorials/reactiveTransport/reactiveTransportDBSFoam/1DLinearRetardation`
- role:
  - analytical retardation benchmark
- manuscript note:
  - `cases/1d_linear_retardation/README.md`

## Simple 2D

- tracked case:
  - `tutorials/reactiveTransport/reactiveTransportDBSFoam/4StraightFracturesSurfaceComplexation`
- source asset:
  - `images/raw/4StraightFractures.raw.tar.gz`
- metadata:
  - `images/raw/4StraightFractures.txt`
- role:
  - transparent 2D image-based surface-complexation case
- manuscript note:
  - `cases/2d_4StraightFractures/README.md`

## Simple 3D

- tracked case:
  - `tutorials/reactiveTransport/reactiveTransportDBSFoam/3DKelvinSurfaceComplexation`
- source asset:
  - `images/raw/Kelvin1-200x200x200.raw.tar.gz`
- metadata:
  - `images/raw/Kelvin1-200x200x200.txt`
- role:
  - controlled 3D image-based case with simple topology
- manuscript note:
  - `cases/3d_kelvin/README.md`

## Large 3D Porous Media

- tracked case:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_estaillades`
- source asset:
  - `images/raw/Est_3phase500cubed4micron.raw.tar.gz`
- metadata:
  - `images/raw/Est_3phase500cubed4micron.txt`
- role:
  - larger Estaillades-style multi-scale demonstration case
- manuscript note:
  - `cases/3d_estaillades/README.md`

## Controlled Surface-Area Validation

- generated 2D circular-post metrics:
  - run `cases/2d_circular_post_surface_area_benchmark/runAll.sh`
- tracked 3D sphere case:
  - `cases/3d_sphere_surface_area_benchmark`
- role:
  - verifies the quasi-2D contour and 3D isosurface branches against controlled
    geometries

## 3D External-Surface Validation

- resolved-wall/DBS flow and sorption comparison:
  - `cases/3d_external_surface_flow_validation`
- role:
  - compares resolved-wall `snappyHexMesh` with DBS `smoothSurface`
    for an image-derived three-dimensional porous geometry

## Two-Scale Upscaling Validation

- tracked case:
  - `cases/two_scale_micromodel_sorption_validation`
- source assets:
  - compressed binary micromodel images materialised under
    `cases/two_scale_micromodel_sorption_validation/shared/source`
- role:
  - matched fully resolved and DBS-upscaled lithium sorption benchmark at
    Pe=0.1, 1, 3, and 10
- publication figures:
  - `figures/png/fig09_two_scale_error_vs_peclet.png`
  - `figures/png/fig10_two_scale_pe1_fields.png`
- reproduction manifest:
  - `cases/two_scale_micromodel_sorption_validation/paper_validation_runs.json`

## Complete inventory and current use

The paths above describe the scientific case ladder. The following table
disambiguates paper-specific cases from frozen tutorial snapshots and accounts
for every retained case directory. “Supporting” means retained but not used to
produce a current manuscript figure.

| ID | Repository-relative path | Classification | Figures |
|---|---|---|---:|
| `paper-1d-linear` | `papers/.../cases/1d_linear_retardation` | paper figure case; results generated locally | 1, 6 |
| `paper-2d-fractures` | `papers/.../cases/2d_4StraightFractures` | paper figure case | 2 |
| `paper-circular-post` | `papers/.../cases/2d_circular_post_surface_area_benchmark` | paper figure case; metrics generated locally | 9 |
| `paper-estaillades` | `papers/.../cases/3d_estaillades` | paper figure case | 4, 8 |
| `paper-external-3d` | `papers/.../cases/3d_external_surface_flow_validation` | paired paper figure case | 11 |
| `paper-kelvin-pointer` | `papers/.../cases/3d_kelvin` | documentation pointer | 3, 7 |
| `paper-sphere` | `papers/.../cases/3d_sphere_surface_area_benchmark` | paper figure case | 9 |
| `paper-two-scale` | `papers/.../cases/two_scale_micromodel_sorption_validation` | paper figure case | 12--14 |
| `tutorial-kelvin` | `tutorials/.../3DKelvinSurfaceComplexation` | paper figure case | 3, 7 |
| `hm12-comparison` | `tutorials/reactiveTransport/HM12SurfaceComplexationSolverComparison` | paired paper driver | 10 |
| `hm12-resolved` | `tutorials/.../HM12SurfaceComplexationSolverComparison/resolved-snappy` | paper subcase | 10 |
| `tutorial-hm12-solid-dbs` | `tutorials/.../2DHM12SolidGrainsSurfaceComplexation` | paper subcase | 10 |
| `tutorial-1d` | `tutorials/.../1DLinearRetardation` | retained upstream snapshot | -- |
| `tutorial-4straight` | `tutorials/.../4StraightFracturesSurfaceComplexation` | retained upstream snapshot | -- |
| `tutorial-estaillades` | `tutorials/.../3DEstailladesSurfaceComplexation` | retained upstream snapshot | -- |
| `tutorial-hm12-microporous` | `tutorials/.../2DHM12MicroporousGrainsSurfaceComplexation` | retained supporting comparator | -- |
| `tutorial-estaillades-micropore-solid` | `tutorials/.../3DEstailladesMicroporeAsSolidSurfaceComplexation` | retained supporting comparator | -- |

Here, `papers/...` abbreviates
`papers/scalarTransportDBSFoam-phreeqc-surface-complexation`, and
`tutorials/...` abbreviates
`tutorials/reactiveTransport/reactiveTransportDBSFoam` unless the longer HM12
path is shown. Exact paths, run commands, and renderer relationships are checked
in `../reproducibility_manifest.json`. No supporting case has been removed.

## Image links and crops

Run `./prepare_external_assets.sh` from the repository root before an
image-based simulation. `external_assets.json` records the immutable links,
SHA-256 checksums, full dimensions, voxel sizes, labels, and these operations:

- 4StraightFractures: full `500 x 500 x 1` image; no crop.
- Kelvin: full `200 x 200 x 200` image; no crop.
- Estaillades main case: full `500 x 500 x 500` image. External-surface case:
  `x=300:428, y=340:468, z=40:168`, with micropore remapped to solid.
- HM12: source `2000 x 2000 x 10`; `x=700:1300, y=700:1300, z=1:2`,
  threshold `>120`, then retain the inlet-connected pore component.
- two-scale: full resolved `6000 x 6000` and DBS `1200 x 1200` inputs; matrix
  REV `x=0:300, y=2200:2500`; threshold `>127`; `base, mirror-x, base`
  extension; four-voxel resolved and one-voxel DBS inlet pore pads.

Large solver outputs are not stored in Git. The accepted two-scale run paths,
checkpoints, and checksums are recorded in `paper_validation_runs.json` and the
repository-level `RUN_ARCHIVE_MANIFEST.md`; the published PNGs remain tracked.
