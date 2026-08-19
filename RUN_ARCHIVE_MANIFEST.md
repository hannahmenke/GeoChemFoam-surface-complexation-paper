# Production run archive manifest

The eight production cases used by the two-scale validation were independently
archived as SquashFS images on the shared `n03` ARCHER2 project filesystem.
Final verification completed at `2026-08-19T05:10:49+00:00` in Slurm job
`14800626`.

Archive directory:

```text
/mnt/lustre/a2fs-work3/work/n03/shared/gcfoam/archives/
  two_scale_micromodel_sorption_20260818
```

| Archive | Size (bytes) | SHA-256 |
|---|---:|---|
| `pe0p1_dbs.sqfs` | 7,802,650,624 | `0aad2e885f8f73c79688337cab4f556c1438fd322e71198ed8e671b92dd2030f` |
| `pe0p1_resolved.sqfs` | 5,286,920,192 | `e5db3adceac2e8e74f4a818b2a38d8237dfbaff0671cb4f0aa8eca2bfcec5ec1` |
| `pe1_dbs.sqfs` | 8,193,703,936 | `e2297c3695749be8dfa9c62aff20defefb6220866680c84c18810db2173b1bf1` |
| `pe1_resolved.sqfs` | 5,298,978,816 | `254a290f23527dd6e0b0114a1452ecc7c56f2831e3fbfe088d0f3fc50257a5c6` |
| `pe3_dbs.sqfs` | 7,578,124,288 | `4f7cc75a117dcff200a2b468cbbb8b3f3128f4b66f3b54af697cbb218db23429` |
| `pe3_resolved.sqfs` | 5,252,710,400 | `5015744617a9ca88c38d7b8efe514713b863689e0497bb6860e73952221714ab` |
| `pe10_dbs.sqfs` | 7,574,978,560 | `0bee6b3909e03e995cb0f31927259420819ff77caaefe904fc9beed4d1cc97af` |
| `pe10_resolved.sqfs` | 5,238,816,768 | `e8522823b10f4fe6c12582fd435e4ae93343844e20e9df67a39fefc42fd34fa4` |

Verify an archive from that directory with, for example:

```bash
sha256sum -c pe3_resolved.sqfs.sha256
```

Inspect or restore it with:

```bash
unsquashfs -ll pe3_resolved.sqfs
unsquashfs -d /path/to/restored/pe3_resolved pe3_resolved.sqfs
```

The Git repository contains the case templates, compressed geometry inputs,
analysis scripts, plotted figures, and exact job/checkpoint provenance. It does
not contain these approximately 52 GB of compressed solver output.
