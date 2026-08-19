# Phase 10 Note: Simple 3D Kelvin Result Figure

## Scope

This note records the accepted 3D field figure for:

- `reactiveScalarTransportDBSFoam`

using:

- `tutorials/reactiveTransport/reactiveScalarTransportDBSFoam/3DKelvinSurfaceComplexation`

## What Was Added

The manuscript file:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig03_3d_kelvin.png`

is now a real volume-rendered 3D field figure.

An earlier slice-based draft was useful as an internal diagnostic, but it is no
longer the accepted paper method. The final draft figure is now produced by the
working `gcfoam` EGL volume-render path:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_3d_volume_render_pyvista.py`

The underlying data source remains the real `8`-rank solver output at:

- `t = 100`

## Figure Convention

The current Kelvin 3D figure uses:

- an initial geometry panel derived from the cell-centered `theta` field
- a true stitched-volume render of the full coarse simulation box
- the same angled 3D camera in both panels
- per-panel relative scaling for visual comparability

Panels:

- left: geometry
- middle: dissolved `Ca+2`
- right: adsorbed `Surf_aCa+`

The selected reported time (`t = 100`) is intentionally early enough that the
dissolved front remains close to the mid-domain position instead of appearing
nearly saturated at the outlet.

After the later paper review pass, this was tightened further to:

- `t = 50`

and the right-hand panel now shows incremental surface loading
(`Delta Surf_aCa+`) rather than absolute `Surf_aCa+`, so the figure reflects
only uptake caused by the inlet pulse.

## Current Interpretation

At `t = 100`, the Kelvin case is already close to aqueous saturation across the
domain, so the dissolved-calcium panel shows a modest but still visible global
gradient. The adsorbed-calcium panel is more structurally informative because
the uptake continues to follow the cell-scale `aSurf` distribution.
