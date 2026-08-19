# Phase 10 Summary

## Scope

This note closes the current no-reference paper-drafting phase for the DBS
PHREEQC surface-complexation manuscript.

## Completed Outputs

- manuscript workspace:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/`
- compiling LaTeX draft:
  - `main.tex`
- completed draft result figures:
  - `figures/png/fig01_1d_retardation.png`
  - `figures/png/fig02_2d_fractures.png`
  - `figures/png/fig03_3d_kelvin.png`
  - `figures/png/fig04_3d_estaillades.png`

## Technical State Captured In The Draft

- the 1D analytical benchmark is reported with quantitative error metrics
- the 2D fracture case is reported from the corrected matrix-reactive run with
  intrinsic unresolved matrix surface area
- the simple 3D Kelvin case is reported as a true 3D volume-rendered field
  figure from the stitched `8`-rank runtime output at `t = 100`
- the large 3D Estaillades-style case is reported from the corrected `8`-rank
  runtime output at `t = 400`, with timing and field metrics plus a true 3D
  volume-rendered field figure

## Rendering Path Used

The final 3D draft figures are rendered through the working local `gcfoam` EGL
path:

- `mesalib` installed in `gcfoam`
- `DISPLAY=` unset
- `VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow`
- renderer:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_3d_volume_render_pyvista.py`

## Remaining Work Outside Phase 10

- tighten prose where draft wording still refers to placeholders or temporary
  status
- add literature references
- decide whether to keep the current relative-scale 3D rendering convention or
  switch to physically scaled color bars for the final submission build

## Decision

- Phase 10 is complete within the current no-reference draft scope.
