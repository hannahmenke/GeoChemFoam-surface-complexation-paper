# Phase 10 Note: Field Rendering Strategy

## Scope

This note records the rendering strategy for paper-quality concentration and
surface-loading figures.

## 2D Cases

For 2D cases, the preferred paper rendering is:

- geometry shown as a light background mask
- the reported scalar field (`Ca+2` or `Surf_aCa+`) shown as a filled image on
  the same grid
- a fixed colormap and fixed normalization across all 2D comparisons
- percentile clipping to avoid one-cell outliers dominating the color range

## 3D Cases

For 3D cases, the paper should not use planar slices as the main figure.
Instead, the preferred rendering is:

- an angled 3D voxel render so the reader can immediately see the domain is
  volumetric
- the same camera angle across related figures so geometry and chemistry are
  visually comparable
- geometry-only renders for the draft scaffold
- concentration and surface-loading renders that color the visible voxels by
  cell-centered field values

## Practical Rendering Rule

The render pipeline should:

- downsample the voxel field for plotting only
- preserve the simulation data on the original mesh
- color each plotted block by a robust representative value from the underlying
  cells:
  - mean for smooth aqueous fields
  - max or upper-quantile can be considered for sparse surface-loading fields
- use fixed scaling within a given comparison set

## Aesthetic Rule For The Paper

- use clean white backgrounds
- avoid rainbow colormaps
- keep one consistent camera orientation per case family
- keep colorbar labels in physical field names
- do not mix a geometry-only camera angle with a different chemistry camera
  angle for the same case
- keep the geometry palette fixed across all cases:
  - pore = white / clear
  - micropore or intermediate porous phase = blue
  - solid = red

## Status

The current draft has geometry-only staged renders. The next implementation
step is to add scriptable field-based renders that apply the same camera and
downsampling rules to `Ca+2` and `Surf_aCa+`.
