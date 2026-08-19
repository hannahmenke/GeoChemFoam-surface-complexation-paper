# Phase 10 Paper Plan: Manuscript Draft And Test-Case Package

## Scope

This phase adds the manuscript drafting track for the DBS PHREEQC surface
complexation work.

The goal is not final submission formatting yet. The goal is to produce a
scientifically complete internal draft with:

- the mathematical model written clearly
- the implementation path explained accurately
- the benchmark/test-case ladder written in publishable order
- figure and case placeholders wired to reproducible repo assets

## Target Structure

The manuscript should follow the same broad structure as the 2021 GeoChemFoam
reactive transport paper:

1. Abstract
2. Introduction
3. Model Description
4. Validation
5. Test Cases / Results
6. Conclusions

Within that structure, the DBS paper should be organized as:

1. Abstract
2. Introduction
3. Model Description
4. Numerical Implementation
5. Validation
6. Test Cases
7. Conclusions

This keeps the same logic as the reference paper while separating the DBS
implementation details cleanly from the mathematical statement.

## Test-Case Ladder

The paper should present results in this order:

1. 1D analytical benchmark
2. simple 2D image-based benchmark
3. simple 3D image-based benchmark
4. large 3D porous-media benchmark

Accepted source assets in this repo:

- 2D:
  - `images/raw/4StraightFractures.raw.tar.gz`
  - metadata: `images/raw/4StraightFractures.txt`
- simple 3D:
  - `images/raw/Kelvin1-200x200x200.raw.tar.gz`
  - metadata: `images/raw/Kelvin1-200x200x200.txt`
- large 3D porous media:
  - `images/raw/Est_3phase500cubed4micron.raw.tar.gz`
  - metadata: `images/raw/Est_3phase500cubed4micron.txt`

The 1D analytical benchmark remains the tracked:

- `tutorials/reactiveTransport/reactiveTransportDBSFoam/1DLinearRetardation`

## Detailed Step-By-Step Task List

### A. Manuscript Skeleton

1. Create a dedicated paper directory in the repo.
2. Create a top-level LaTeX entry file.
3. Split the manuscript into section files.
4. Add a figure staging directory for PNG outputs.
5. Add a case/asset manifest that maps each paper section to a repo test case.

### B. Mathematical Write-Up

1. Write the conservative DBS transport equation using the exact field
   definitions used in the solver.
2. Write the cell-based surface inventory and explain the current written
   `Surf_*` field convention.
3. Write the local PHREEQC coupling step and the Lie-splitting algorithm.
4. State the field locations explicitly:
   - cell-centered `Yi`, `theta`, `epsNum`, `aSurf`, `Surf_*`
   - face-centered `phi`
5. State the current known limits explicitly:
   - local decomposition sensitivity on tiny meshes
   - small timestep sensitivity in front shape
   - current field-scaling convention for `Surf_*`

### C. Implementation Write-Up

1. Document the solver lineage:
   - `reactiveScalarTransportFoam`
   - `multiScalarTransportDBSFoam`
   - `phreeqcDBSMixture`
   - `reactiveTransportDBSFoam`
2. Document which validation solvers remain in-tree and why.
3. Document the benchmark harnesses used for verification.
4. Document the meaning of:
   - `epsNum`
   - `theta`
   - `aSurf`
   - solution species fields
   - surface species fields

### D. Validation Section

1. Write the 1D analytical benchmark subsection first.
2. Include:
   - the dilute linear-equilibrium reduction
   - the field-level retardation factor
   - measured versus expected mean transport
3. Add a figure placeholder for the 1D profile/retardation result.
4. Add a short performance note tied to the same benchmark.

### E. 2D Section

1. Use `4StraightFractures` as the geometry source.
2. Define the 2D case setup and what physics it is meant to isolate.
3. Produce PNGs for:
   - geometry
   - aqueous concentration
   - surface loading
4. Write the interpretation in terms of:
   - front retardation
   - wall interaction
   - conservation

### F. Simple 3D Section

1. Use `Kelvin1-200x200x200` as the geometry source.
2. Define a simple, controlled 3D run that is still interpretable.
3. Produce PNGs for:
   - geometry slices / render
   - aqueous concentration slices
   - surface loading slices
4. Explain what the 3D case adds beyond 2D:
   - topology
   - surface-area distribution
   - 3D transport pathways

### G. Large 3D Porous-Media Section

1. Use `Est_3phase500cubed4micron` as the large porous-media source.
2. Treat it explicitly as a multi-scale benchmark, not just a larger voxel set.
3. Define the production-scale demonstration case.
4. Record the scale-separation quantities that make the case scientifically
   distinct:
   - voxel size
   - image size
   - representative pore-throat / grain-scale contrast visible in slices
   - total reactive surface-area density used by the DBS model
5. State how the manuscript subvolume or cropped domain is chosen so the case
   remains reproducible and not tuned by eye.
6. Produce PNGs for:
   - geometry overview
   - coarse and fine slice views that show the multi-scale structure
   - aqueous concentration slices
   - surface loading slices
   - any summary metric plot
7. Explain:
   - why this is the realistic porous-media stress test
   - what the multi-scale image adds beyond the Kelvin case
   - computational cost
   - what remains controlled vs what becomes application-like

### H. Internal Review Preparation

1. Ensure every equation points to a matching implementation concept.
2. Ensure every result section points to a reproducible case path or asset path.
3. Ensure every figure has a planned PNG target filename.
4. Ensure the draft is readable even before references are added.
5. Only then mark Phase 10 ready for internal scientific review.

## Deliverables For This First Phase 10 Checkpoint

This first checkpoint should produce:

- a LaTeX manuscript skeleton
- section placeholders with real mathematical and implementation content
- a mapped set of planned test cases
- figure placeholders and PNG target locations

References can remain deferred until after the technical narrative is stable.
