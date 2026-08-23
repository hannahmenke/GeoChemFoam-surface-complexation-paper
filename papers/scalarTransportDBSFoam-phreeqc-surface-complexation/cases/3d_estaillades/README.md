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

## Production Outputs

- angled 3D geometry overview
- aqueous concentration volume render
- surface-loading volume render
- one summary performance/chemistry metric

## Figure Convention

- the accepted figure is generated from the native-resolution solver fields
- the render shows the aqueous and adsorbed response in 3D rather than a
  sliced diagnostic plane

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

## Figures

- `figures/png/fig04_3d_estaillades.png`
- `figures/png/fig08_estaillades_temporal.png`

Regenerate both figures after a completed run with:

```bash
../../figures/scripts/render_estaillades_figures.sh
```

## Full-Resolution Production Configuration

- computational grid: `500 x 500 x 500` (125,000,000 cells)
- chemistry-active cells: 94,031,005 (`eps > 1e-3`)
- decomposition: `4 x 4 x 4` (64 MPI ranks)
- reactive solver: `reactiveTransportDBSFoam`
- surface-site density: `2.4e-9 kmol/m2` in the OpenFOAM dictionary,
  equivalent to `2.4e-6 mol/m2`
- reactive timestep: `2 s`; the implicit Euler/upwind transport discretisation
  gives a face-flux Courant number of `63.400` maximum (`5.424` mean) on the
  converged full-resolution flow field
- transported-species linear solve: `tolerance 5e-7`, `relTol 0.001`; this
  tighter relative criterion avoids the conservative-species overshoot seen
  with the generic main-branch production setting at this case's larger Co
- final time: `120 s`
- write interval: `20 s`
- OpenFOAM field output: binary

The standalone paper repository must be pointed to the read-only GeoChemFoam
runtime checkout before launch:

```bash
export GCFOAM_RUNTIME_ROOT=/path/to/GeoChemFoam
./runAll.sh
```

Generated mesh, fields, and logs remain untracked. Older
coarse-grid outputs must not be used for the full-resolution paper result.

Launch the flow stage first, then evaluate its maximum velocity and Courant
number before starting chemistry:

```bash
RUN_STAGE=flow ./runAll.sh
RUN_STAGE=reactive RUN_TIMESTEP=2 ./runAll.sh
```
