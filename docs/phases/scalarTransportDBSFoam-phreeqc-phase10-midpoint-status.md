# Phase 10 Midpoint Status

## Scope

This note records the current midpoint state of the manuscript draft for the
DBS PHREEQC surface-complexation paper.

## What Is Now In Place

- The manuscript skeleton exists in:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/main.tex`
- The core math and implementation sections are populated:
  - `sections/03_model_description.tex`
  - `sections/04_numerical_implementation.tex`
- The 1D validation figure is no longer a placeholder:
  - `figures/png/fig01_1d_retardation.png`
- The 2D fracture result figure is now based on the corrected intrinsic matrix
  surface term and the accepted clean run:
  - `figures/png/fig02_2d_fractures.png`
- The large 3D Estaillades case is configured against the correct
  `Est_3phase500cubed4micron` image and the corrected `8`-rank draft chemistry
  run exists to `t = 400`.

## Current Quantitative Draft Results

- 1D analytical benchmark:
  - retained as the primary analytical validation figure
  - current manuscript metrics are taken from the tracked Phase 9 benchmark
- 2D fracture case:
  - accepted reporting time: `t = 3000`
  - run on `8` MPI ranks
  - matrix phase uses an intrinsic unresolved surface term
- 3D Estaillades draft case:
  - coarse grid: `50 x 50 x 50`
  - ranks: `8`
  - final reported time: `t = 400`
  - chemistry calls: `80`
  - PHREEQC total time: about `58.1 s`
  - wall-clock to final write: about `82 s`

## 3D Rendering Status

The final 3D manuscript figures are now available from a working local
off-screen path.

- The active rendering route is:
  - `gcfoam` VTK EGL volume rendering
- The working renderer is:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_3d_volume_render_pyvista.py`
- The system ParaView path remains unsuitable on this machine, but it is no
  longer the draft blocker.

## Current Draft Rule

- 1D and 2D figures are accepted as draft manuscript figures.
- The 3D Kelvin and Estaillades figures are now real volume-rendered field
  figures generated from the tracked runtime cases.

## Decision Status

- Phase 10 is complete within the current no-reference draft scope.
- No modeling decision is currently blocking the paper.
