# 3D Manuscript Case: HFO-Coated Kelvin Cell

## Source Asset

- image: `images/raw/Kelvin1-200x200x200.raw.tar.gz`
- metadata: `images/raw/Kelvin1-200x200x200.txt`

## Paper Role

- controlled 3D image-based reactive transport example
- critical-metal recovery analogue in an open-cell sorbent medium
- coupled flow, transport, and surface-complexation response in a 3D DBS case

## Geometry

- image size: `200 x 200 x 200`
- voxel size: `10 mum`
- labels:
  - `1 = pore`
  - `2 = microporous/reactive sorbent phase`

## Surface Model

- two-site Dzombak-Morel hydrous ferric oxide (HFO) surface complexation
- strong sites: `Hfo_s = 2e-7 mol/m2`
- weak sites: `Hfo_w = 6e-6 mol/m2`
- target species: Mn2+
- competing background species: Mg2+
- initial and inlet Mg2+: `1e-3 mol/L`
- inlet Mn2+: `1e-5 mol/L`

Mn2+ has stronger HFO affinity than Mg2+ in the Dzombak-Morel reaction set, so
the injected Mn-bearing front is preferentially captured from Mg-rich water.

## Surface Area

- interface-count `aSurf`
- intrinsic micropore contribution inside label `2`
- intrinsic micropore density: `1e5 1/m`

## Reproducibility

Run the full case from this directory:

```bash
./runAll.sh
```

The script creates the mesh, runs flow, runs reactive transport, and performs
the configured post-processing.

## Figures

- `figures/png/fig03_3d_kelvin.png`
- `figures/png/fig07_kelvin_temporal.png`

Regenerate both figures after a completed run with:

```bash
../../figures/scripts/render_kelvin_mnmg_figures.sh
```
