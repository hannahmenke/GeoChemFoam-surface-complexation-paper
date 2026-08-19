# 3D external surface flow validation

This benchmark compares a resolved-wall `snappyHexMesh` case with a Cartesian
DBS case on the same three-dimensional Estaillades crop. Each case runs
pressure-driven flow first and then reactive Sr/Ca transport with surface
complexation:

- `snappy`: resolved pore-space mesh, run with `simpleFoam` and
  `reactiveTransportDBSFoam`; resolved wall area is mapped to adjacent chemistry
  cells.
- `dbs-smoothsurface`: Cartesian DBS mesh, run with `simpleDBSFoam` and
  `reactiveTransportDBSFoam`, with an explicit smooth-interface `aSurf` field.

The shared crop is generated from `Est_3phase500cubed4micron`. The micropore label is remapped to solid and only the inlet-connected pore space is retained, so all three cases solve flow through the same external pore network.

Run the full benchmark with:

```bash
cd papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/3d_external_surface_flow_validation
./runAll.sh
```

To run the two methods concurrently after preparing the shared crop, use:

```bash
./runAllParallel.sh
```

The run writes:

- `shared/estaillades_external_crop_phase.raw`
- `shared/estaillades_external_crop_binary.raw`
- `snappy/poroPerm.csv`
- `dbs-smoothsurface/poroPerm.csv`
- `results/summary.csv`
- `results/summary.json`
- `results/parallel-logs/*.log` when run with `runAllParallel.sh`

The default reactive transport comparison time is `t = 2.5`, with `dt = 0.01`.
Both cases use `epsChemistryMin = 1e-3`. The summary reports surface area,
permeability/Darcy velocity, and sorbed Sr inventory relative to the resolved
reference at that comparison time.
