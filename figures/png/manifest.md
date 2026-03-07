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
  - log-scale Pb²⁺/C_in aqueous panel at `t = 2000`
  - log-scale Hfo_sOPb⁺ strong-site surface loading at `t = 2000`
- chemistry:
  - Pb²⁺ on Dzombak–Morel two-site HFO (Hfo_s + Hfo_w)
  - near-complete retardation shown via log colorscale (4 decades)
  - fracture vs. matrix transport contrast visible
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
  - true 3D volume render of dissolved Zn²⁺ (competitive sorption)
  - true 3D volume render of adsorbed Surf_aZn⁺
- chemistry:
  - Zn²⁺ + Ca²⁺ competing for Surf_a sites; Zn²⁺ log_k −4.0 vs Ca²⁺ log_k −5.85
  - Ca²⁺ uniform background (1×10⁻⁴ mol/L); Zn²⁺ inlet 1×10⁻⁵ mol/L
- source case:
  - `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DKelvinSurfaceComplexation`
- reported time:
  - `t = 20`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_3d_field_panels.py`

## Figure 4

- target file:
  - `fig04_3d_estaillades.png`
- section:
  - Test Cases / Large 3D Porous Media
- content:
  - geometry panel
  - true 3D volume render of dissolved Sr²⁺ or Ca²⁺ (DGR scenario)
  - true 3D volume render of adsorbed Surf_aSr⁺
- chemistry:
  - Sr²⁺ leachate (0.1 mM inlet) invading Ca²⁺-bearing formation water (1 mM initial)
  - surface sites pre-loaded with Ca²⁺; Sr displaces Ca in chromatographic exchange
- source asset:
  - `images/raw/Est_3phase500cubed4micron.raw.tar.gz`
- source case:
  - `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DEstailladesSurfaceComplexation`
- reported time:
  - `t = 40`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_3d_field_panels.py`

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
  - left panel: domain-mean Ca²⁺/C_in and Zn²⁺/C_in vs time (competitive sorption)
  - right panel: normalised incremental domain-mean Surf_aCa⁺ and Surf_aZn⁺ vs time
  - 31 time points: t = 0, 4, 8, ..., 120 (writeInterval=4, endTime=120)
- chemistry:
  - Ca²⁺ background at inlet and initial; Zn²⁺ inlet only; competing for Surf_a sites
- source case:
  - `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DKelvinSurfaceComplexation`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_kelvin_temporal_plot.py`
