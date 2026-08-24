Type: research
Status: resolved

## Question

Compile a candidate list of suggested reviewers by mining `references.bib` and broader field knowledge for active researchers in reactive transport modeling, PHREEQC-coupled simulation, DBS/micro-continuum methods, or the paper's specific application areas (contaminant sorption, critical-mineral recovery, radionuclide transport). Exclude Menke, Doster, Maes, and their very recent close collaborators/co-authors to avoid conflicts of interest. For each candidate, note affiliation and why they're relevant.

## Answer

Full findings, deprioritized candidates, and COI exclusions with rationale:
`.scratch/tpm-submission/research/12-reviewer-candidates-findings.md`.

**This is a candidate list only — final reviewer selection still requires
Hannah's approval (feeds ticket 13, a separate follow-up).**

Shortlist of 10, checked for recent (~3 year) activity and no co-authorship
with Menke/Doster/Maes in the last ~3-5 years:

1. **Sergi Molins** (LBNL) — pore-scale DNS reactive transport; co-developed
   the mineral-dissolution benchmark set the paper's validation measures
   against.
2. **Christophe Tournassat** (Univ. Orléans / LBNL) — co-author of
   `porousMedia4Foam` and the OpenFOAM-PHREEQC platform paper, the paper's
   closest methodological comparator.
3. **Francis Claret** (BRGM) — `porousMedia4Foam` co-author; active in
   nuclear-waste reactive transport, strong fit for the DGR application case.
4. **K. Ulrich Mayer** (UBC) — developer of MIN3P, classical multicomponent
   RTM with surface complexation and mining-contaminant transport.
5. **Hongkyu Yoon** (Sandia) — pore-scale reactive transport / digital rock
   physics in a DOE-lab, radionuclide-adjacent context.
6. **Tianfu Xu** (Jilin Univ., ex-LBNL) — TOUGHREACT developer; recent work
   directly on radioactive-waste-disposal RTM benchmarking.
7. **Frank Heberling** (KIT-INE) — calcite/carbonate surface complexation and
   mineral-water interface chemistry; radionuclide/DGR relevance.
8. **Ilenia Battiato** (Stanford) — upscaling of pore-scale reactive
   transport to Darcy/continuum scale, directly relevant to the DBS
   micro-continuum argument.
9. **Catherine Noiriel** (Univ. Toulouse / CNRS) — pore-scale X-ray imaging
   and reactive surface area evolution during dissolution.
10. **Ralf Haese** (Univ. Melbourne) — built a COMSOL-PhreeqC pore-scale
    coupling structurally similar to this paper's OpenFOAM-PhreeqcRM
    coupling; also works on critical-mineral (copper ore) applications.

**Excluded for conflict of interest** (co-authored directly with Menke and/or
Maes within the last ~3-5 years, per the paper's own `references.bib`):
Cyprien Soulaine (co-author with both Maes and Menke on `maes2022vos`, 2022 —
otherwise the single most obvious pick as `porousMedia4Foam`/DBS lead
author), Sebastian Geiger, Martin J. Blunt, Branko Bijeljic.

Also considered but deprioritized for weaker/uncertain current fit (not
COI): Saideep Pavuluri, David Dzombak, Vitaliy Starchenko, and
Parkhurst/Charlton (PHREEQC/PhreeqcRM authors themselves — authoritative but
an atypical choice for independent peer review). Details in the findings
file.
