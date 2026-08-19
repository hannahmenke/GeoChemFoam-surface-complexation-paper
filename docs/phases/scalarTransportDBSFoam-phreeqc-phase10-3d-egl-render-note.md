# Phase 10 Note: Working EGL Volume Rendering Path

## Scope

This note records the first successful local 3D off-screen volume-render
workflow for the manuscript figures.

## Problem

The system ParaView runtime remained unusable for headless rendering on this
machine because it kept falling back to a broken X/GLX path over the forwarded
display.

## Working Fix

The local `gcfoam` environment now has a working off-screen rendering path
using VTK EGL.

Working setup:

- conda environment:
  - `gcfoam`
- added package:
  - `mesalib`
- required environment:
  - `DISPLAY=` (unset)
  - `VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow`

## Renderer Used

The final 3D manuscript PNGs are now generated with:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_3d_volume_render_pyvista.py`

This script:

- stitches the decomposed regular-grid OpenFOAM scalar fields,
- classifies the initial geometry from the cell-centered `theta` field,
- reconstructs them as a VTK image volume,
- applies per-panel relative scaling for visibility,
- can subtract the `t = 0` surface-loading baseline so the plotted surface
  panel represents only inlet-driven uptake,
- renders true 3D volumes for:
  - geometry
  - dissolved `Ca+2`
  - incremental adsorbed `Surf_aCa+`
- uses the same chemistry color logic as Figure 2:
  - `cividis` for dissolved concentration
  - `magma` for surface loading

## Generated Figures

Successful outputs:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig03_3d_kelvin.png`
  - generated from:
    - `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DKelvinSurfaceComplexation`
  - reported time:
    - `t = 50`
  - reason for chosen time:
    - the dissolved front is still near the mid-domain position
- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig04_3d_estaillades.png`
  - generated from:
    - `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DEstailladesSurfaceComplexation`
  - reported time:
    - `t = 100`
  - reason for chosen time:
    - the dissolved front is still close to the half-domain position

## Initialization Caveat

The current PHREEQC backend does not keep a solution component active if that
component is completely absent from the startup solutions. For that reason, the
3D paper cases still retain a tiny startup calcium trace (`1e-12`) rather than
literal zero. The manuscript figures avoid showing this negligible background
surface loading by plotting:

- `Delta Surf_aCa+ = Surf_aCa+(t) - Surf_aCa+(0)`

## Consequence

The remaining Phase 10 blocker is removed within the current no-reference draft
scope. The paper now has real 1D, 2D, and 3D figure outputs generated from the
tracked runtime cases.
