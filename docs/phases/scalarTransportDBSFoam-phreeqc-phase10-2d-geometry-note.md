# Phase 10 Note: 2D Geometry Draft Figure

## Scope

This note records the first concrete 2D figure asset for the manuscript test
case based on the existing `4StraightFractures` image.

## What Was Added

The staged manuscript figure:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig02_2d_fractures.png`

is now generated directly from:

- `images/raw/4StraightFractures.raw.tar.gz`
- `images/raw/4StraightFractures.txt`

using:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_2d_raw_geometry.py`

## Current Figure Content

The current figure is a geometry-only draft panel:

- segmented voxel map
- `500 x 500 x 1` image dimensions
- phase labels:
  - `0 = solid`
  - `1 = matrix`
  - `2 = pore`

## Status

This is a paper-draft geometry figure, not the final 2D results panel. The
2D section still needs:

- aqueous concentration output from the solver
- surface-loading output from the solver
- a final multi-panel figure layout
