# Paper Test-Case Asset Map

The manuscript uses the following case ladder.

Paper-local executable cases and copied tutorial overrides are stored alongside these notes so the paper workflow does not depend on modified files under `tutorials/`.
Each manuscript case should preserve its runnable inputs under this directory, expose a `runAll.sh` entry point where the case is executable, and list the corresponding figure-render command in the case README.

## 1D Analytical

- paper-local executable case:
  - `cases/1d_linear_retardation/runAll.sh`
- role:
  - analytical retardation benchmark
- manuscript note and figure command:
  - `cases/1d_linear_retardation/README.md`

## Simple 2D

- source asset:
  - `images/raw/4StraightFractures.raw.tar.gz`
- metadata:
  - `images/raw/4StraightFractures.txt`
- role:
  - transparent 2D image-based surface-complexation case
- paper-local executable case:
  - `cases/2d_4StraightFractures/runAll.sh`
- manuscript note and figure command:
  - `cases/2d_4StraightFractures/README.md`

## Simple 3D

- source asset:
  - `images/raw/Kelvin1-200x200x200.raw.tar.gz`
- metadata:
  - `images/raw/Kelvin1-200x200x200.txt`
- role:
  - controlled 3D image-based Cu/Zn HFO surface-complexation case with simple topology
- paper-local executable case:
  - `cases/3d_kelvin/runAll.sh`
- manuscript note and exact case parameters:
  - `cases/3d_kelvin/README.md`
- figure regeneration script:
  - `figures/scripts/render_kelvin_cuzn_figures.sh`

## Large 3D Porous Media

- source asset:
  - `images/raw/Est_3phase500cubed4micron.raw.tar.gz`
- metadata:
  - `images/raw/Est_3phase500cubed4micron.txt`
- role:
  - larger Estaillades-style multi-scale demonstration case
- paper-local executable case:
  - `cases/3d_estaillades/runAll.sh`
- manuscript note and figure command:
  - `cases/3d_estaillades/README.md`

## 3D Binary Estaillades Variant

- paper-local runnable case:
  - `cases/3d_estaillades_micropore_as_solid`
- role:
  - two-phase pores-plus-solids Estaillades benchmark where the micropore label is remapped to solid
- manuscript note:
  - `cases/3d_estaillades_micropore_as_solid/README.md`

## HM12 Three-Case Solver Comparison

- paper-local benchmark:
  - `cases/hm12_fourcase_solver_comparison`
- role:
  - paper comparison between resolved-wall snappy, DBS `|\nabla epsilon|`, and DBS `smoothSurface`
- manuscript output:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig10_hm12_surface_area_validation.png`
- benchmark note:
  - `cases/hm12_fourcase_solver_comparison/README.md`

## HM12 2D Legacy Diagnostics

- paper-local diagnostic cases:
  - `cases/hm12_2d_legacy/runAll.sh`
- role:
  - preserves older solid-grain and microporous-grain HM12 render inputs used by diagnostic figure scripts
- benchmark note:
  - `cases/hm12_2d_legacy/README.md`

## 3D Sphere Surface-Area Benchmark

- paper-local benchmark scaffold:
  - `cases/3d_sphere_surface_area_benchmark`
- role:
  - separates analytic-sphere error from voxelization error for `snappy`, `subsetMesh`, `DBS file`, and `DBS fallback`
- benchmark note:
  - `cases/3d_sphere_surface_area_benchmark/README.md`

## Copied Tutorial Overrides

- paper-local mirror:
  - `cases/tutorial_overrides`
- role:
  - preserves paper-specific tutorial edits before resetting `tutorials/` back to the upstream baseline
- note:
  - `cases/tutorial_overrides/README.md`
