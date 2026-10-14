# GeoChemFoam surface-complexation paper

This repository contains the manuscript, figures, plotting and analysis
scripts, validation cases, and pinned input-asset references for the GeoChemFoam
surface-complexation paper.

Generated case results are not tracked. They must be produced locally from the
case entry points or recovered from the checksum-bound external run archives.

The material was extracted from
[`hannahmenke/GeoChemFoam-v-dev`](https://github.com/hannahmenke/GeoChemFoam-v-dev)
at commit `0d750971f84070be2cd669b713cc09d0adf48296`. The simulations require a
compatible GeoChemFoam build; solver source code is intentionally not copied
into this repository.

## Layout

- repository root: manuscript,
  figures, paper-specific cases, and reproduction scripts
- `tutorials/reactiveTransport`: frozen snapshots of GeoChemFoam cases used
  directly by the paper
- `external_assets.json`: immutable GeoChemFoam image links, checksums, and crop
  parameters
- `images/raw`: small tracked image metadata; raw archives are materialised here
  locally and are not duplicated in Git
- `scripts`: paper benchmark utilities
- `SOURCE_PROVENANCE.md`: extraction boundary and upstream version record

The tracked paths are repository-relative so the existing run and figure
scripts continue to resolve their inputs after cloning. Site-specific runtime
locations are supplied through environment variables documented by the ARCHER2
launcher scripts.

## Start here

The authoritative navigation and reproduction guide is
[`MANUSCRIPT_README.md`](MANUSCRIPT_README.md).
It maps every manuscript figure to its case, run command, renderer, and evidence.
The same mapping is machine-readable in `reproducibility_manifest.json` and is
checked by `audit_reproducibility.sh`.

Prepare the GeoChemFoam-owned image archives without committing copies:

```bash
./prepare_external_assets.sh --source-root /path/to/GeoChemFoam-v-dev
```

If `--source-root` is omitted, the script downloads the immutable links recorded
in `external_assets.json` using authenticated `gh` access (or `GITHUB_TOKEN`).
In both modes it verifies every SHA-256 checksum.

## Two-scale validation

The principal resolved-versus-upscaled benchmark is under:

```text
./
  cases/two_scale_micromodel_sorption_validation
```

Its README documents environment setup, ARCHER2 submission, acceptance
criteria, and figure reproduction. `paper_validation_runs.json` records the
solver template commit, Slurm job chains, checkpoint states, and exact plotted
times. Large ARCHER2 outputs are archived separately and are not committed to
Git. The eight external archive basenames and SHA-256 values are listed in
`external_archive_checksums.sha256`.

## Build the manuscript

```bash
cd /path/to/GeoChemFoam-surface-complexation-paper
./build.sh
```

Before release, audit the complete case/figure map:

```bash
./audit_reproducibility.sh
./validate_accepted_nonkelvin_artifacts.sh
./test_export_submission.sh
```

The audit fails if numerical case outputs, result directories, processor
directories, solver logs, or generated validation summaries are Git-tracked.

## Relationship to GeoChemFoam

The case snapshots in this repository are publication records. Canonical
tutorials and shared image inputs remain in GeoChemFoam because they also serve
as solver examples and regression fixtures. Changes needed by the solver should
be made upstream and then deliberately imported here with a new provenance
record.
