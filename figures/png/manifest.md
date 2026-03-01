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
