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
  than one geometric scale in the reported volume render
- the binary pores-plus-solids variant is preserved separately in:
  - `cases/3d_estaillades_micropore_as_solid`

## Planned Outputs

- angled 3D geometry overview
- aqueous concentration volume render
- surface-loading volume render
- one summary performance/chemistry metric

## Current Draft Figure Convention

- the current staged PNG is only a temporary geometry placeholder
- the accepted final figure is a ParaView volume render of the real solver
  fields
- the final render should show the aqueous and adsorbed response in 3D rather
  than a sliced diagnostic plane

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
- `figures/png/fig08_estaillades_temporal.png`

Regenerate both figures after a completed run with:

```bash
../../figures/scripts/render_estaillades_figures.sh
```

## Current Runtime Status

- the solver case configuration has now been corrected to the true
  `Est_3phase500cubed4micron` image
- the corrected `8`-rank chemistry run to `t = 400` now exists and is valid
- any older reactive outputs generated before that correction must not be used
  as paper results because they were produced from the wrong image setup
- the draft manuscript now uses a true 3D volume-rendered field figure from the
  corrected run
