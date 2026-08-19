# Paper Test-Case Asset Map

The cases are stored and run from this paper repository. Build the main-branch
GeoChemFoam solver in a separate checkout and either place it beside this
repository as `GeoChemFoam-main-runtime` or set `GCFOAM_RUNTIME_DIR` to that
checkout. The case scripts source `etc/bashrc` from this repository and do not
write to the solver checkout.

The manuscript uses the following case ladder.

## 1D Analytical

- tracked case:
  - `tutorials/reactiveTransport/reactiveTransportDBSFoam/1DLinearRetardation`
- role:
  - analytical retardation benchmark
- manuscript note:
  - `cases/1d_linear_retardation/README.md`

## Simple 2D

- source asset:
  - `images/raw/4StraightFractures.raw.tar.gz`
- metadata:
  - `images/raw/4StraightFractures.txt`
- role:
  - transparent 2D image-based surface-complexation case
- manuscript note:
  - `cases/2d_4StraightFractures/README.md`

## Simple 3D

- source asset:
  - `images/raw/Kelvin1-200x200x200.raw.tar.gz`
- metadata:
  - `images/raw/Kelvin1-200x200x200.txt`
- role:
  - controlled 3D image-based case with simple topology
- manuscript note:
  - `cases/3d_kelvin/README.md`

## Large 3D Porous Media

- source asset:
  - `images/raw/Est_3phase500cubed4micron.raw.tar.gz`
- metadata:
  - `images/raw/Est_3phase500cubed4micron.txt`
- role:
  - larger Estaillades-style multi-scale demonstration case
- manuscript note:
  - `cases/3d_estaillades/README.md`

## Controlled Surface-Area Validation

- tracked 2D circular-post metrics:
  - `cases/2d_circular_post_surface_area_benchmark/results/area_metrics.csv`
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
  - compressed binary micromodel images under
    `cases/two_scale_micromodel_sorption_validation/shared/source`
- role:
  - matched fully resolved and DBS-upscaled lithium sorption benchmark at
    Pe=0.1, 1, 3, and 10
- publication figures:
  - `figures/png/fig09_two_scale_error_vs_peclet.png`
  - `figures/png/fig10_two_scale_pe1_fields.png`
- reproduction manifest:
  - `cases/two_scale_micromodel_sorption_validation/paper_validation_runs.json`
