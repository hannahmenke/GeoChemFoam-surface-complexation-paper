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

Current staged figures:

- `fig01_1d_retardation.png`
  - two-panel 1D analytical validation figure
  - left: normalized aqueous profile vs cell-averaged analytical reference
  - right: normalized surface loading vs cell-averaged linear-limit reference
- `fig02_2d_fractures.png`
  - three-panel 2D results figure for Pb²⁺ / Dzombak–Morel HFO
  - left: fracture geometry
  - middle: log-scale Pb²⁺ / C_in at `t = 2000` (4 decades, fracture vs. matrix contrast)
  - right: log-scale Hfo_sOPb⁺ strong-site surface loading at `t = 2000`
  - shows near-complete Pb retardation by HFO; fracture channels visible as faster transport paths
- `fig03_3d_kelvin.png`
  - matplotlib 3D slice panels (generate_3d_field_panels.py), t = 20s
  - left: dissolved Zn²⁺ (competitive sorption front traversing domain)
  - right: adsorbed Zn (Surf_aZn⁺) in micropore phase (diamond pattern)
- `fig04_3d_estaillades.png`
  - matplotlib 3D slice panels (generate_3d_field_panels.py), t = 40s
  - left: dissolved Sr²⁺ (DGR leachate front advancing through limestone pore structure)
  - right: adsorbed Sr (Surf_aSr⁺) in micropore phase
- `fig07_kelvin_temporal.png`
  - two-panel temporal evolution for Kelvin Zn²⁺/Ca²⁺ competitive sorption
  - left: domain-mean Ca²⁺ and Zn²⁺ / C_in vs time (31 time points)
  - right: normalised incremental Surf_aCa⁺ and Surf_aZn⁺ domain-mean vs time

The LaTeX draft already references these as the expected final PNG outputs.
