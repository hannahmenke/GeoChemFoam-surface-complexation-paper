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
  - populated with a two-panel 1D analytical validation figure
  - left: normalized aqueous profile vs cell-averaged analytical reference
  - right: normalized surface loading vs cell-averaged linear-limit reference
- `fig02_2d_fractures.png`
  - populated with a three-panel 2D results figure
  - left: geometry
  - middle: normalized dissolved calcium at `t = 3000`
  - right: normalized adsorbed calcium at `t = 3000`
  - uses the corrected intrinsic matrix surface term in the `eps = 0.4`
    microporous phase
- `fig03_3d_kelvin.png`
  - populated with a true 3D volume render from the real solver field
  - rendered through the `gcfoam` EGL VTK path
  - active script:
    - `figures/scripts/generate_3d_volume_render_pyvista.py`
- `fig04_3d_estaillades.png`
  - populated with a true 3D volume render from the corrected `8`-rank
    chemistry run
  - rendered through the `gcfoam` EGL VTK path
  - active script:
    - `figures/scripts/generate_3d_volume_render_pyvista.py`

The LaTeX draft already references these as the expected final PNG outputs.
