# Phase 10 Note: 3D Geometry Draft Figures

## Scope

This note records the first staged 3D geometry figures for the manuscript.

## What Was Added

The staged manuscript figures:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig03_3d_kelvin.png`
- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig04_3d_estaillades.png`

are now generated directly from:

- `images/raw/Kelvin1-200x200x200.raw.tar.gz`
- `images/raw/Kelvin1-200x200x200.txt`
- `images/raw/Est_3phase500cubed4micron.raw.tar.gz`
- `images/raw/Est_3phase500cubed4micron.txt`

using:

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_3d_raw_slice.py`

## Current Figure Content

- `fig03_3d_kelvin.png`
  - central 2D slice through the Kelvin segmented image
  - geometry-only draft panel
- `fig04_3d_estaillades.png`
  - central overview slice plus a zoomed subregion
  - geometry-only draft panel intended to expose the multi-scale structure

## Status

These are geometry-only draft figures. The 3D manuscript sections still need:

- aqueous concentration outputs from the solver
- surface-loading outputs from the solver
- final result-focused multi-panel layouts
