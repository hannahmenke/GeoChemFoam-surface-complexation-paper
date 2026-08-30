# 2D Manuscript Case: 4StraightFractures

## Source Asset

- image:
  - `images/raw/4StraightFractures.raw.tar.gz`
- metadata:
  - `images/raw/4StraightFractures.txt`

## Paper Role

- simplest image-based geometry
- visually transparent 2D retardation and uptake case

## Source Metadata

- image size:
  - `500 x 500 x 1`
- segmentation:
  - `phases`
- labels:
  - `1 = micropore`
  - `2 = pore`
- note:
  - the source metadata reserves `0 = solid`, but the raw image itself uses
    only labels `1` and `2`
  - the manuscript draft currently treats label `1` as the reactive
    micropore phase for `aSurf`
  - the source metadata does not currently report a resolved voxel size

## Runtime Case

- paper-local executable case:
  - `papers/scalarTransportDBSFoam-phreeqc-surface-complexation/cases/2d_4StraightFractures`
- reproducible entry point:
  - `runAll.sh`
- mesh:
  - `250 x 250 x 1`
- accepted production run:
  - `8` MPI ranks (`4 x 2 x 1`)

## Current Outputs

- geometry panel
- aqueous concentration panel
- surface-loading panel

## Accepted Record

- launch inputs and runtime identity:
  - `launch_provenance.json`
  - this is a point-in-time pre-launch record; the run scripts subsequently
    replace the working copies of `transportProperties`, `controlDict`, and
    `fvSolution` from their preserved `*1` templates
- realized transport inputs and source/output hashes:
  - `run_provenance.json`
- numerical validation summary:
  - `../../figures/png/fig02_item2_validation_metrics.json`
- figure provenance and verifier:
  - `../../figures/figure_provenance.json`
  - `../../figures/scripts/figure2_provenance.py`
- provenance scope:
  - the verifier and records are the bounded schema used for the accepted
    Figure 2 run; they predate the planned repository-wide common schema

## Figure

- `figures/png/fig02_2d_fractures.png`
  - populated from the `t = 20000` solver output
  - `1860 x 675` pixels
  - SHA-256 `72380206ac6e03d7d86f53a4c27f57fc319459d8b1b7ffb469c7b2e836ecaf38`

Regenerate the figure after a completed run with:

```bash
../../figures/scripts/render_2d_fractures_figure.sh
```
