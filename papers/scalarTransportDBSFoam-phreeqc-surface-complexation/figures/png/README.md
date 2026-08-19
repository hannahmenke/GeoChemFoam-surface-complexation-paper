# Planned PNG Figures

This directory is the staging location for manuscript PNG outputs.

Geometry palette rule:

- pore: white / clear
- micropore or intermediate porous phase: blue
- solid: red

Planned figure targets:

- `fig01_1d_retardation.png`
- `fig02_2d_fractures.png`
- `fig03_3d_kelvin.png`
- `fig04_3d_estaillades.png`
- `fig08_estaillades_temporal.png`
- `fig09_two_scale_error_vs_peclet.png`
- `fig10_two_scale_pe1_fields.png`

Current staged figures:

- `fig01_1d_retardation.png`
  - two-panel 1D analytical validation figure
  - left: normalized aqueous profile vs cell-averaged analytical reference
  - right: normalized surface loading vs cell-averaged linear-limit reference
- `fig02_2d_fractures.png`
  - three-panel 2D results figure for Pb²⁺ / Dzombak–Morel HFO
  - left: fracture geometry
  - middle: log-scale Pb²⁺ / C_in at `t = 20000` (4 decades, fracture vs. micropore contrast)
  - right: log-scale Hfo_sOPb⁺/Hfo_s,total strong-site occupancy at `t = 20000`
  - uses the higher-load Pb case (`C_in = 10^-3 mol m^-3`), showing strong but incomplete retardation by HFO
- `fig03_3d_kelvin.png`
  - five-panel Kelvin competition figure, t = 12 s
  - top: segmented geometry
  - lower 2x2: dissolved Zn²⁺, dissolved Ca²⁺, ΔSurf_aZn⁺, and -ΔSurf_aCa⁺
- `fig04_3d_estaillades.png`
  - matplotlib 3D slice panels (generate_3d_field_panels.py), t = 40s
  - left: dissolved Sr²⁺ (DGR leachate front advancing through limestone pore structure)
  - right: adsorbed Sr (Surf_aSr⁺) in micropore phase
- `fig07_kelvin_temporal.png`
  - two-panel temporal evolution for Kelvin Zn²⁺/Ca²⁺ competitive sorption
  - left: domain-mean Ca²⁺ and Zn²⁺ / C_in vs time (31 time points)
  - right: normalised incremental Surf_aCa⁺ and Surf_aZn⁺ domain-mean vs time
- `fig08_estaillades_temporal.png`
  - two-panel temporal evolution for Estaillades Sr²⁺/Ca²⁺ chromatographic exchange
  - left: domain-mean Ca²⁺ / C_init and Sr²⁺ / C_in vs time (6 time points)
  - right: normalised incremental Surf_aCa⁺ and Surf_aSr⁺ domain-mean vs time
- `fig09_two_scale_error_vs_peclet.png`
  - fully resolved versus DBS-upscaled inventory, placement, and map errors at
    matched `x/L = 0.125` for Pe=0.1, 1, 3, and 10
- `fig10_two_scale_pe1_fields.png`
  - native 5 micrometre Pe=1 aqueous and sorbed Li fields at `x/L = 0.625`
  - resolved grains are masked and no display averaging is applied

The companion manifest records each staged PNG's source case and renderer.
