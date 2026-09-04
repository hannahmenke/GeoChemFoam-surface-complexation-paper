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
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/1d_linear_retardation`
- reproducible entry point:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/1d_linear_retardation/runPhase8AnalyticalBenchmark.sh`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_1d_retardation_plot.py`
- repeatable command:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_1d_validation_figures.sh`

## Figure 2

- target file:
  - `fig02_2d_fractures.png`
- section:
  - Test Cases / Simple 2D
- content:
  - geometry panel
  - log-scale Pb²⁺/C_in aqueous panel at `t = 20000`
  - log-scale Hfo_sOPb⁺/Hfo_s,total strong-site occupancy at `t = 20000`
- chemistry:
  - Pb²⁺ on Dzombak–Morel two-site HFO (Hfo_s + Hfo_w)
  - higher-load Pb injection (`C_in = 10^-3 mol L^-1`) with strong but incomplete retardation
  - fracture vs. micropore transport contrast visible
- source asset:
  - `images/raw/4StraightFractures.raw.tar.gz`
  - immutable source link, checksum, and full-image crop are recorded in
    `external_assets.json`; run `prepare_external_assets.sh` before regeneration
- source case:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/2d_4StraightFractures`
- reproducible entry point:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/2d_4StraightFractures/runAll.sh`
- accepted artifact:
  - `1860 x 675` pixels
  - SHA-256 `72380206ac6e03d7d86f53a4c27f57fc319459d8b1b7ffb469c7b2e836ecaf38`
- accepted run and validation records:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/2d_4StraightFractures/launch_provenance.json`
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/2d_4StraightFractures/run_provenance.json`
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig02_item2_validation_metrics.json`
- machine-readable figure record:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/figure_provenance.json`
- verifier:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/figure2_provenance.py`
  - this is the bounded Figure 2 schema used for the accepted run, not the final
    repository-wide common provenance schema
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_2d_raw_geometry.py`
- repeatable command:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_2d_fractures_figure.sh`

## Figure 3

- target file:
  - `fig03_3d_kelvin.png`
- section:
  - Test Cases / Simple 3D
- content:
  - top-centred geometry panel
  - lower 2x2 grid of true 3D volume renders for dissolved Mn²⁺, dissolved Mg²⁺,
    incremental HFO-Mn, and displaced HFO-Mg
- chemistry:
  - Mn²⁺ + Mg²⁺ competing for two-site Dzombak-Morel HFO sites
  - Mn²⁺ log_k values: Hfo_s −0.40, Hfo_w −3.50
  - Mg²⁺ log_k value: Hfo_w −4.60
  - Mg²⁺ uniform background (1×10⁻³ mol/L); Mn²⁺ inlet 1×10⁻⁵ mol/L
- source case:
  - `tutorials/reactiveTransport/reactiveTransportDBSFoam/3DKelvinSurfaceComplexation`
- reproducible entry point:
  - `tutorials/reactiveTransport/reactiveTransportDBSFoam/3DKelvinSurfaceComplexation/runAll.sh`
- reported time:
  - `t = 120`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_kelvin_competition_figure.py`
- repeatable command:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_kelvin_mnmg_figures.sh`

## Figure 4

- target file:
  - `fig04_3d_estaillades.png`
- section:
  - Test Cases / Large 3D Porous Media
- content:
  - opaque exterior view of the three-phase segmented geometry
  - 3D volume renders of dissolved Sr²⁺ and Ca²⁺ over the pore and micropore mobile-water domain
  - 3D volume render of incremental adsorbed Surf_aSr⁺, normalised by its maximum at `t = 40`
- chemistry:
  - Sr²⁺ leachate (0.1 mM inlet) invading Ca²⁺-bearing formation water (1 mM initial)
  - surface sites pre-loaded with Ca²⁺; Sr displaces Ca in chromatographic exchange
- source asset:
  - `images/raw/Est_3phase500cubed4micron.raw.tar.gz`
  - immutable source link, checksum, and full-image crop are recorded in
    `external_assets.json`; run `prepare_external_assets.sh` before regeneration
- source case:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_estaillades`
- reproducible entry point:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_estaillades/runAll.sh`
- reported time:
  - `t = 40`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_3d_volume_render_pyvista.py`
- repeatable command:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_estaillades_figures.sh`

## Figure 5

- target file:
  - `fig05_solver_workflow.png`
- section:
  - Numerical Implementation
- content:
  - source-traced operator-splitting loop between aqueous transport and PHREEQCRM
  - initialization, `speciesMixture.correct()` push/run/pull sequence, and OpenFOAM field-write ordering
- source implementation:
  - GeoChemFoam commit `c51d4e34`
  - `applications/solvers/reactiveTransport/reactiveTransportDBSFoam/{reactiveTransportDBSFoam.C,createFields.H,YiEqn.H}`
  - `src/thermophysicalModels/reactionThermo/mixtures/phreeqcMixture/phreeqcMixture.C`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_solver_workflow.py`
- repeatable command:
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
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/1d_linear_retardation`
- reproducible entry point:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/1d_linear_retardation/runPhase8AnalyticalBenchmark.sh`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_1d_breakthrough_plot.py`
- repeatable command:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_1d_validation_figures.sh`

## Figure 7

- target file:
  - `fig07_kelvin_temporal.png`
- section:
  - Test Cases / Simple 3D
- content:
  - left panel: pore-volume weighted Mn²⁺/C_in and pore-volume weighted Mg²⁺ excess above background vs time
  - right panel: normalised signed surface-area-weighted changes in HFO-Mn and HFO-Mg vs time
  - 11 plotted time points: t = 0, 12, 24, ..., 120 (sampled from writeInterval=4 output)
- chemistry:
  - Mg²⁺ background at inlet and initial; Mn²⁺ inlet only; competing for HFO sites
- source case:
  - `tutorials/reactiveTransport/reactiveTransportDBSFoam/3DKelvinSurfaceComplexation`
- reproducible entry point:
  - `tutorials/reactiveTransport/reactiveTransportDBSFoam/3DKelvinSurfaceComplexation/runAll.sh`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_kelvin_temporal_plot.py`
- repeatable command:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_kelvin_mnmg_figures.sh`

## Figure 8

- target file:
  - `fig08_estaillades_temporal.png`
- section:
  - Test Cases / Large 3D Porous Media
- content:
  - left panel: pore-volume-weighted Ca²⁺/C_init and Sr²⁺/C_in vs time
  - right panel: incremental surface-area-weighted Surf_aCa⁺ and Surf_aSr⁺ vs time, normalised by the largest absolute change over the plotted sequence
  - 7 time points: t = 0, 20, 40, 60, 80, 100, 120
- chemistry:
  - Sr²⁺ leachate displacing Ca²⁺ from pre-loaded Surf_a sites in Estaillades micropores
- source case:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_estaillades`
- reproducible entry point:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_estaillades/runAll.sh`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_estaillades_temporal_plot.py`
- numerical acceptance check:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/validate_estaillades_checkpoint.py`
  - finite Cl⁻ and Sr²⁺ fields with at most 0.1% overshoot in chemistry-active cells ($\theta>10^{-3}$) at each saved transport checkpoint
- repeatable command:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_estaillades_figures.sh`

## Figure 9

- target file:
  - `fig09_sphere_surface_area_validation.png`
- section:
  - Validation / Controlled Surface-Area Validation
- content:
  - relative error in integrated surface area versus the analytic 3D sphere
  - relative error in integrated surface area versus the analytic 2D circular post
  - comparison of `snappyHexMesh` and smooth-interface DBS where applicable
- source assets:
  - generated `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_sphere_surface_area_benchmark/results`
  - generated `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/2d_circular_post_surface_area_benchmark/results/area_metrics.csv`
  - DBS circular-post metrics generated analytically by the renderer
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_sphere_surface_area_validation.py`
- repeatable command:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_surface_area_validation_figures.sh`
  - run both benchmark case entry points first; generated metrics are not tracked

## Figure 10

- target file:
  - `fig10_hm12_surface_area_validation.png`
- section:
  - Validation / Micromodel Image-Based Surface-Area Validation
- content:
  - micromodel two-case panel at `t = 200`
  - resolved-wall `snappyHexMesh` and DBS `smoothSurface`
  - aqueous Sr/C_in fields, cell-wise reactive area, and sorbed inventory fields
- source asset:
  - generated directly from the two micromodel case outputs
- note:
  - the paper-facing figure is only rendered when the `snappyHexMesh` and
    `DBS smoothSurface` outputs both exist
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_surface_area_validation_figures.sh`

## Figure 11

- target file:
  - `fig11_3d_external_surface_area_validation.png`
- section:
  - Validation / 3D External Surface-Area Validation
- content:
  - translucent 3D render of the connected Estaillades external pore-grain surface with micropore label remapped to solid
  - external pore-solid surface area only, excluding intrinsic micropore area
  - `snappyHexMesh` wall area binned to the image grid, DBS `smoothSurface` area, projected differences, and axial area profiles at `t = 2.5`
- source case:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_external_surface_flow_validation`
- note:
  - snappy wall faces are binned to the Cartesian crop for the projected-area panels; global area and sorbed inventory are computed on each method's native support
- reproducible entry point:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_external_surface_flow_validation/runAllParallel.sh`
- availability:
  - the clean repository archive retains the published PNG and renderer; the
    flat submission source retains only the published PNG. Neither retains raw
    mesh or field outputs; regenerate only after `runAll.sh` or
    `runAllParallel.sh` has completed, or from an external completed case tree
- case analyzer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_external_surface_flow_validation/scripts/analyze_external_flow_validation.py`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_3d_external_surface_area_validation.sh`

## Figure 12

- target file:
  - `fig12_two_scale_lithium_nested_geometries.png`
- section:
  - Validation / Two-Scale Micromodel Sorption Benchmark
- content:
  - nested geometry hierarchy following the dispersivity-paper benchmark structure
  - full long two-scale micromodel
  - full-model resolved REV
  - resolved matrix REV used to parameterise the upscaled matrix
- source assets:
  - `longTSmicromodelDBS.raw.tar.gz`
  - `TSmicromodel6000.raw.tar.gz`
  - the current renderer uses the resolved and DBS source images identified in
    `external_assets.json`; the long DBS archive is retained there as an unused
    historical link rather than duplicated in Git
- source case:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/two_scale_micromodel_sorption_validation`
- reproducible entry point:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/two_scale_micromodel_sorption_validation/runPeSweep.sh`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_two_scale_lithium_sorption_validation.sh`

## Retained analysis asset

- target file:
  - `fig13_two_scale_lithium_sorption_validation.png`
- section:
  - Validation / Two-Scale Micromodel Sorption Benchmark
- content:
  - axial aqueous Li inventory distribution
  - global DBS mismatch versus Peclet number
  - axial sorbed Li inventory distribution
- source case:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/two_scale_micromodel_sorption_validation`
- reproducible entry point:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/two_scale_micromodel_sorption_validation/runPeSweep.sh`
- analyzer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/two_scale_micromodel_sorption_validation/scripts/analyze_results.py`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/render_two_scale_lithium_sorption_validation.sh`
- note:
  - retained for provenance and not referenced by the manuscript
  - superseded by the production Pe-sweep Figures 13 and 14 below

## Figure 13

- target file:
  - `fig09_two_scale_error_vs_peclet.png`
- section:
  - Validation / Resolved-to-DBS Two-Scale Sorption Benchmark
- content:
  - DBS-minus-resolved aqueous and sorbed Li inventory differences
  - normalized streamwise-profile L1 errors
  - native-domain map dissimilarity at matched `x/L = 0.625`
  - production cases at Pe = 0.1, 1, 3, and 10
- source case:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/two_scale_micromodel_sorption_validation`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/two_scale_micromodel_sorption_validation/scripts/reproduce_paper_validation.py`

## Figure 14

- target file:
  - `fig10_two_scale_pe1_fields.png`
- section:
  - Validation / Resolved-to-DBS Two-Scale Sorption Benchmark
- content:
  - fully resolved and DBS-upscaled aqueous Li fields at Pe = 1 and `x/L = 0.625`
  - corresponding sorbed Li fields on a shared logarithmic scale
  - native-grid zooms with resolved grains masked and no spatial averaging
- source case:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/two_scale_micromodel_sorption_validation`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/two_scale_micromodel_sorption_validation/scripts/reproduce_paper_validation.py`
