# Phase 10 Note: ParaView Constraint And EGL Workaround

## Scope

This note records the current status of the 3D manuscript rendering pipeline.

## Accepted Rendering Policy

For the 3D chemistry figures, the accepted final method is:

- true 3D volume rendering

not:

- planar slices
- outer-skin geometry stand-ins

Available scripts:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_3d_volume_render_paraview.py`
- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_3d_volume_render_pyvista.py`

## What Was Verified

- system ParaView binaries are present:
  - `/usr/bin/pvpython`
  - `/usr/bin/pvbatch`
  - `/usr/bin/paraview`
- the ParaView Python module is installed under:
  - `/usr/lib/python3/dist-packages/paraview`
- on this machine, `pvpython` only imports that module correctly when:
  - `PYTHONPATH=/usr/lib/python3/dist-packages`

## System ParaView Constraint

The current system ParaView build is not rendering headlessly in this
environment.

Observed behavior:

- with the correct `PYTHONPATH`, scripts execute
- but any real render attempt crashes in:
  - `vtkXOpenGLRenderWindow`
- the runtime still attempts an X/GLX path
- software GL fallback is unavailable here (`swrast` missing)
- so the system ParaView route remains unsuitable on this machine

## Working Workaround

The rendering problem is now solved locally through the `gcfoam` environment.

Working path:

- install `mesalib` in `gcfoam`
- unset `DISPLAY`
- force:
  - `VTK_DEFAULT_OPENGL_WINDOW=vtkEGLRenderWindow`
- render with:
  - `generate_3d_volume_render_pyvista.py`

## Immediate Consequence

The system ParaView path is still broken here, but the final 3D chemistry
screenshots are no longer blocked because the `gcfoam` EGL volume-render path
works and is now the active manuscript rendering route.
