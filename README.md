# GeoChemFoam surface-complexation paper

This private repository contains the manuscript, figures, plotting and analysis
scripts, validation cases, and frozen input assets for the GeoChemFoam
surface-complexation paper.

The material was extracted from
[`hannahmenke/GeoChemFoam-v-dev`](https://github.com/hannahmenke/GeoChemFoam-v-dev)
at commit `0d750971f84070be2cd669b713cc09d0adf48296`. The simulations require a
compatible GeoChemFoam build; solver source code is intentionally not copied
into this repository.

## Layout

- `papers/scalarTransportDBSFoam-phreeqc-surface-complexation`: manuscript,
  figures, paper-specific cases, and reproduction scripts
- `tutorials/reactiveTransport`: frozen snapshots of the GeoChemFoam cases
  used by the paper
- `images/raw`: compressed source images used by those cases and figures
- `scripts`: paper benchmark utilities
- `docs/phases`: paper-development and validation notes
- `SOURCE_PROVENANCE.md`: extraction boundary and upstream version record
- `RUN_ARCHIVE_MANIFEST.md`: verified production-output archive checksums

The original GeoChemFoam-relative paths are retained so the existing run and
figure scripts continue to resolve their inputs.

## Two-scale validation

The principal resolved-versus-upscaled benchmark is under:

```text
papers/scalarTransportDBSFoam-phreeqc-surface-complexation/
  cases/two_scale_micromodel_sorption_validation
```

Its README documents environment setup, ARCHER2 submission, acceptance
criteria, and figure reproduction. `paper_validation_runs.json` records the
solver template commit, Slurm job chains, checkpoint states, and exact plotted
times. Large ARCHER2 outputs are archived separately and are not committed to
Git.

## Build the manuscript

```bash
cd papers/scalarTransportDBSFoam-phreeqc-surface-complexation
./build.sh
```

## Relationship to GeoChemFoam

The case snapshots in this repository are publication records. Canonical
tutorials and shared image inputs remain in GeoChemFoam because they also serve
as solver examples and regression fixtures. Changes needed by the solver should
be made upstream and then deliberately imported here with a new provenance
record.
