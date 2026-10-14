# Source provenance

## Extraction

- source repository: `https://github.com/hannahmenke/GeoChemFoam-v-dev.git`
- source branch: `DBS_surface_complexation`
- source commit: `0d750971f84070be2cd669b713cc09d0adf48296`
- extraction date: `2026-08-19`
- paper history: preserved with `git subtree split`

The historical paper subtree was extracted from:

```text
.
```

The following case and metadata dependencies were copied at the same source
commit so the publication record does not depend on mutable tutorial files:

- metadata for 4StraightFractures, Kelvin1, Estaillades 3-phase, and HM12
- 1D linear-retardation validation case
- 2D four-straight-fracture surface-complexation case
- 3D Kelvin and Estaillades surface-complexation cases
- Estaillades micropore-as-solid case
- HM12 solid-grain and microporous-grain cases
- HM12 four-solver comparison cases
- sphere surface-area benchmark utilities and their mesh dictionary templates

## External raw images

Raw image archives that are already distributed in GeoChemFoam are deliberately
not duplicated here. `external_assets.json` records immutable source commits,
repository paths, download URLs, SHA-256 checksums, dimensions, voxel sizes,
labels, and all crop or threshold operations. Run `./prepare_external_assets.sh`
to link verified files from a local GeoChemFoam checkout or download them into
the original relative paths. Those materialised files are ignored by Git.

The small binary and phase crops in
`cases/3d_external_surface_flow_validation/shared`
remain tracked because they
are derived, paper-specific validation inputs. Their `metadata.json` records the
exact `[300:428, 340:468, 40:168]` crop from the linked Estaillades volume and
the micropore-to-solid remapping.

## Simulation provenance

The current two-scale production configuration is recorded at upstream commit
`913efcf59e75b9ccd93fcee42193a8a6a4c26b60`. Exact job chains and plotted
checkpoints are recorded in:

```text
./
  cases/two_scale_micromodel_sorption_validation/paper_validation_runs.json
```

Large run directories are deliberately excluded from Git. The ARCHER2 archive
created for this project is stored under the site-specific location selected by
the operator (represented below by `${ARCHER_ARCHIVE_ROOT}`):

```text
${ARCHER_ARCHIVE_ROOT}/
  two_scale_micromodel_sorption_20260818
```

That storage location is operational provenance, not a portable dependency;
published data should receive a DOI-backed deposit before manuscript release.

Historical run snapshots may mention local runtime files that are not part of
this public repository. Such references are represented by environment-variable
placeholders rather than exposing a workstation path.
