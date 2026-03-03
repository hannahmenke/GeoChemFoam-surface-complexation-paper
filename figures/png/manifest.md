# Figure Manifest

## Figure 1

- target file:
  - `fig01_1d_retardation.png`
- section:
  - Validation
- content:
  - normalized 1D aqueous concentration profile
  - cell-averaged analytical retarded reference
  - normalized surface-loading profile
- source case:
  - `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/1DLinearRetardation`

## Figure 2

- target file:
  - `fig02_2d_fractures.png`
- section:
  - Test Cases / Simple 2D
- content:
  - geometry panel
  - normalized aqueous concentration panel at `t = 3000`
  - normalized surface-loading panel at `t = 3000`
- source asset:
  - `images/raw/4StraightFractures.raw.tar.gz`
- source case:
  - `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/4StraightFracturesSurfaceComplexation`

## Figure 3

- target file:
  - `fig03_3d_kelvin.png`
- section:
  - Test Cases / Simple 3D
- content:
  - geometry panel
  - true 3D volume render of dissolved calcium
  - true 3D volume render of adsorbed calcium
- source case:
  - `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DKelvinSurfaceComplexation`
- reported time:
  - `t = 100`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_3d_volume_render_pyvista.py`

## Figure 4

- target file:
  - `fig04_3d_estaillades.png`
- section:
  - Test Cases / Large 3D Porous Media
- content:
  - geometry panel
  - true 3D volume render of dissolved calcium
  - true 3D volume render of adsorbed calcium
- source asset:
  - `images/raw/Est_3phase500cubed4micron.raw.tar.gz`
- source case:
  - `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DEstailladesSurfaceComplexation`
- reported time:
  - `t = 100`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_3d_volume_render_pyvista.py`
- status:
  - corrected reactive run exists
  - current PNG is the active volume-rendered draft figure

## Figure 5

- target file:
  - `fig05_solver_workflow.png`
- section:
  - Numerical Implementation
- content:
  - schematic of the operator-splitting loop between transport and PHREEQC
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_solver_workflow.py`

## Figure 6

- target file:
  - `fig06_1d_breakthrough.png`
- section:
  - Validation / 1D Analytical Retardation Benchmark
- content:
  - outlet breakthrough curves C_out(t)/C_in vs time for aqueous-only and surface-enabled runs
  - Ogata-Banks analytical reference curves for both cases
  - breakthrough time markers
- source case:
  - `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/1DLinearRetardation`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_1d_breakthrough_plot.py`

## Figure 7

- target file:
  - `fig07_kelvin_temporal.png`
- section:
  - Test Cases / Simple 3D
- content:
  - domain-mean Ca2+/C_in vs time (left panel)
  - normalised incremental domain-mean Surf_aCa+ vs time (right panel)
  - 10 time points: t = 0, 4, 8, 10, 25, 50, 100, 200, 300, 400
- source case:
  - `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DKelvinSurfaceComplexation`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_kelvin_temporal_plot.py`
