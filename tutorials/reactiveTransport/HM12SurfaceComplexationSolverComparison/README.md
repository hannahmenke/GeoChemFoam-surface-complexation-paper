# HM12 Resolved-Wall/DBS Comparison

This benchmark compares two representations of the same HM12 crop using
`reactiveTransportDBSFoam` for both reactive-transport calculations.

Cases:

- `resolved-snappy`: body-fitted `snappyHexMesh`; wall-face area is mapped to
  adjacent chemistry cells as an explicit `aSurf` field.
- `../reactiveTransportDBSFoam/2DHM12SolidGrainsSurfaceComplexation`: Cartesian
  DBS mesh with an explicit smooth-interface `aSurf` field.

Frozen comparison settings:
- HM12 crop: `x=700:1300`, `y=700:1300`, `z=1:2`
- Connected pore mask: `HM12_2_4_thr120_conn`
- Resolved mesh: `600 x 600 x 1`
- DBS mesh: `300 x 300 x 1`
- Pressure-driven flow with pressure drops calibrated to the same inlet flux
- Reactive end time: `t = 200 s`
- Reactive timesteps: `0.1 s` (resolved) and `0.25 s` (DBS)
- Chemistry cutoff: `epsChemistryMin = 1e-3`

How to run:
```bash
cd tutorials/reactiveTransport/HM12SurfaceComplexationSolverComparison
./runAll.sh
```

What `runAll.sh` does:
- runs the resolved-wall and DBS cases in sequence
- renders the paper figure with the paper-facing plotting script

Figure output:
- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/png/fig10_hm12_surface_area_validation.png`

The plotting script is
`papers/scalarTransportDBSFoam-phreeqc-surface-complexation/figures/scripts/generate_micromodel_surface_area_validation.py`.
