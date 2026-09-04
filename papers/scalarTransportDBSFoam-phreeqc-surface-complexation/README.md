# Surface-complexation paper: reproduction guide

This directory is the entry point for the manuscript and its reproducibility
package. No current manuscript figure or case has to be inferred from a file
name: `reproducibility_manifest.json` maps Figures 1--14 to their case or source,
run command, renderer, evidence, and external image identifiers.

## Quick verification

From this directory:

```bash
./audit_reproducibility.sh
./validate_accepted_nonkelvin_artifacts.sh
./test_export_submission.sh
./build.sh
```

The audit checks that all 14 figures referenced by the manuscript are mapped,
all published and retained PNGs have renderers, every case directory is
classified, local dependencies are tracked, entry points parse, and external
images have immutable links, checksums, and crop metadata.

## External images

Raw archives already bundled with GeoChemFoam are not copied into this
repository. From the repository root, materialise them at the paths expected by
the unchanged case scripts:

```bash
./prepare_external_assets.sh --source-root /path/to/GeoChemFoam-v-dev
```

Without `--source-root`, the command downloads the commit-pinned files using
authenticated `gh` access (or `GITHUB_TOKEN`). See `../../external_assets.json`
for the full dimensions, voxel sizes, phase labels, thresholds, and crop
parameters. Use `--check` to verify an existing local set.

## Where things are

- `main.tex`, `sections/`: manuscript source
- `supplementary.tex`, `sections/supplementary_information.tex`: supporting
  information
- `cases/README.md`: complete case inventory, including the tutorial snapshots
  stored outside this directory
- `figures/README.md`: compact Figure 1--14 command matrix
- `figures/png/manifest.md`: detailed scientific content and provenance for
  every figure
- `reproducibility_manifest.json`: authoritative machine-readable relationship
  between figures, cases, scripts, and evidence
- `RUN_ARCHIVE_MANIFEST.md` at repository root and
  `cases/two_scale_micromodel_sorption_validation/paper_validation_runs.json`:
  checksum-bound external production outputs used for Figures 13 and 14

Published PNGs remain tracked so the manuscript builds without rerunning large
simulations. Regenerating a PNG is a separate, explicit operation using the
command in the figure matrix.
