# Accepted short two-scale surface-reconstruction comparison

This record preserves the accepted short sensitivity test for the two-scale
DBS case. It compares the `occupancyGaussian` reconstruction with the
historical baseline reconstructed `aSurf` field. It is not a DBS-versus-resolved
comparison.

## Decision and scope

The matched Pe = 1 cases used a 3600 x 1200 x 1 grid at 5 micrometre spacing
and 16 MPI ranks. Three common checkpoints were compared through
`t = 0.99564208 s`. Every prospective material-response check passed. The
largest absolute differences were 0.000647% in integrated reactive area,
0.000703% in aqueous Li inventory, 0.2110% in sorbed Li inventory, 0.00172% in
aqueous normalized L1, 0.5147% in sorbed normalized L1, and 0.03993% in the
fixed-reference-area sorbed-response L2. Aqueous and sorbed x50 shifts were
zero. These results support the project decision that the short comparison
shows no appreciable material response difference and that no longer rerun is
required for this decision.

The accepted checkpoint spans only 0.489% of the originally configured
203.5305 s horizon. It must not be represented as a full-horizon invariance
test. Native-cell sorbed inventory-density L2 was 3.61--4.49%; this non-gating
diagnostic is dominated by deliberate reactive-area relocation and rules out a
claim of pointwise identity.

## Provenance

The preserved source directories are listed in
`short_surface_reconstruction_comparison.json`. The scratch case copies do not
contain Git metadata, and their recorded absolute paths are machine-local.
Within each deterministic collection-hash recipe, every relative path is
resolved from that source's recorded `case_path`. Their reconstructed
provenance records paper source
commit `103685cb`, verifies 495 matched non-surface input files, and identifies
the surface field as the sole intended input difference. The runtime was
GeoChemFoam `92145f07` with PHREEQCRM `8aa2a904`; the solver SHA-256 was
`d7a55047...435b10`.

The first long-horizon wrapper attempts later failed after producing the early
checkpoints and therefore are not evidence of complete production runs. The
accepted pair was restarted from the matched `0.11703513 s` checkpoints and
both restarts completed with exit status 0 at `0.99564208 s`, including 16
rank-local dump/marker pairs per case.

The validated analyzer at commit `b21b5d1` (SHA-256
`335f1e6a...970a76`) was rerun read-only on 2026-08-30. All ten focused tests
passed, and the recomputed report SHA-256 was `fa6fe288...5eb787`. The compact
JSON records the exact metrics, thresholds, source paths, provenance/log
hashes, and deterministic collection hashes for all 256 analysis input files.
Raw outputs, logs, PID/status debris, and runtime binaries are intentionally
excluded from this branch.
