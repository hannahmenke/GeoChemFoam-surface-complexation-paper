# Source provenance

## Extraction

- source repository: `https://github.com/hannahmenke/GeoChemFoam-v-dev.git`
- source branch: `DBS_surface_complexation`
- source commit: `0d750971f84070be2cd669b713cc09d0adf48296`
- extraction date: `2026-08-19`
- paper history: preserved with `git subtree split`

The historical paper subtree was extracted from:

```text
papers/scalarTransportDBSFoam-phreeqc-surface-complexation
```

The following tracked dependencies were copied at the same source commit so
the publication package does not depend on mutable tutorial files:

- raw inputs for 4StraightFractures, Kelvin1, Estaillades 3-phase, and HM12
- 1D linear-retardation validation case
- 2D four-straight-fracture surface-complexation case
- 3D Kelvin and Estaillades surface-complexation cases
- Estaillades micropore-as-solid case
- HM12 solid-grain and microporous-grain cases
- HM12 four-solver comparison cases
- sphere surface-area benchmark utilities and their mesh dictionary templates
- phase-10 manuscript and validation notes

## Simulation provenance

The current two-scale production configuration is recorded at upstream commit
`913efcf59e75b9ccd93fcee42193a8a6a4c26b60`. Exact job chains and plotted
checkpoints are recorded in:

```text
papers/scalarTransportDBSFoam-phreeqc-surface-complexation/
  cases/two_scale_micromodel_sorption_validation/paper_validation_runs.json
```

Large run directories are deliberately excluded from Git. The ARCHER2 archive
created for this project is stored under:

```text
/mnt/lustre/a2fs-work3/work/n03/shared/gcfoam/archives/
  two_scale_micromodel_sorption_20260818
```

That storage location is operational provenance, not a portable dependency;
published data should receive a DOI-backed deposit before manuscript release.
