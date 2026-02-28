# 3D Manuscript Case: Estaillades-Style Multiscale Image

## Source Asset

- image:
  - `images/raw/Est_3phase500cubed4micron.raw.tar.gz`
- metadata:
  - `images/raw/Est_3phase500cubed4micron.txt`

## Paper Role

- larger porous-media demonstration
- Estaillades-style multi-scale image benchmark
- application-scale performance and surface-complexation showcase
- distinct from the simple 3D case because the structure must visibly span more
  than one geometric scale in the reported slices

## Planned Outputs

- angled 3D geometry overview
- angled 3D zoom view that exposes the multi-scale hierarchy
- aqueous concentration slices
- surface-loading slices
- one summary performance/chemistry metric

## Current Draft Figure Convention

- the staged draft geometry figure is an outer-skin render of the cropped
  full volume
- all phases on the external surface are colored
- no internal geometry is shown in this draft figure
- when a second panel is shown, it is a second exterior viewing angle rather
  than a cropped cutaway

## Required Reported Metadata

- voxel size from the source metadata
- cropped domain size actually simulated
- total `aSurf` used in the reported run
- MPI rank count
- representative runtime on the reporting machine

## Source Metadata

- image size:
  - `500 x 500 x 500`
- voxel size:
  - `4 mum`
- labels:
  - `1 = pore`
  - `2 = micropores`
  - `3 = solid`

## Planned Figure

- `figures/png/fig04_3d_estaillades.png`
