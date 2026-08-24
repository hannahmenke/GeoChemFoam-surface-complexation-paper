# Reviewer Candidates — Findings

Research for ticket 12. Feeds ticket 13 (final reviewer list), which requires
Hannah's sign-off before anything is submitted to the journal.

## Method

1. Read `references.bib` and the paper sections (abstract, introduction, model
   description, validation, test cases) to identify the paper's methodological
   and application anchors: DBS/micro-continuum formulation, PhreeqcRM cell-based
   coupling, `snappyHexMesh` resolved-wall validation, `porousMedia4Foam`-style
   micro-continuum benchmarking, image-based porous media, and the three
   application domains (heavy-metal/AMD remediation, critical-mineral/direct
   lithium extraction, radionuclide/DGR transport).
2. Built a candidate pool from the bib's author list plus adjacent subfields
   named in the ticket (classical Darcy-scale RTM codes, pore-scale DNS/LBM
   reactive transport, surface complexation modelling, pore-scale imaging).
3. Web-searched each serious candidate for (a) publication activity in
   roughly the last 3 years, (b) current institutional affiliation, and
   (c) direct co-authorship with Hannah Menke, Florian Doster, or Julien Maes
   in the last ~3-5 years (searched as `"<candidate name>" "Menke" OR "Maes"
   OR "Doster"`, plus manual cross-check of the bib itself, which surfaces
   several conflicts directly).

## Shortlist (10 candidates, ordered roughly by relevance)

1. **Sergi Molins** — Research Scientist, Earth & Environmental Sciences Area,
   Lawrence Berkeley National Laboratory (LBNL), USA.
   Relevance: leading figure in pore-scale DNS reactive transport and the
   community mineral-dissolution benchmark set (`molins2021simulation`, cited)
   that the paper's validation section measures itself against. No COI found.

2. **Christophe Tournassat** — Professor, Institut des Sciences de la Terre
   d'Orléans (ISTO), University of Orléans, France; Visiting Faculty, LBNL.
   Relevance: co-author of `porousMedia4Foam` and the OpenFOAM-PHREEQC
   platform paper (`pavuluri2022reactive`) that is the paper's closest direct
   methodological comparator; very active 2024-2025 (radionuclide/clay
   sorption, Environmental Science & Technology 2025). No COI found.

3. **Francis Claret** — Senior scientist / programme director, BRGM (French
   Geological Survey), Orléans, France.
   Relevance: co-author of both `porousMedia4Foam` papers cited in the paper;
   active 2024-2025 in nuclear-waste reactive transport (EURAD state-of-the-art
   report, ML-accelerated RTM) — strong fit for the DGR/radionuclide
   application case. No COI found.

4. **K. Ulrich Mayer** — Professor, Dept. of Earth, Ocean and Atmospheric
   Sciences, University of British Columbia, Canada.
   Relevance: developer of MIN3P, a classical multicomponent reactive
   transport code handling surface complexation and mining-contaminant
   transport (AMD, heavy-metal remediation — directly overlaps the paper's
   remediation application). Active 2025 (multi-domain RTM, Water Resources
   Research). No COI found.

5. **Hongkyu Yoon** — Distinguished Member of Technical Staff, Sandia
   National Laboratories, Albuquerque, USA.
   Relevance: pore-scale reactive transport and digital-rock-physics
   modelling in a DOE-lab context, adjacent to radionuclide/subsurface energy
   applications; active through 2024-2025 (though recent work has drifted
   toward ML/UQ surrogates rather than pore-scale RTM specifically — worth
   flagging as a minor fit caveat). No COI found.

6. **Tianfu Xu** — Professor, College of New Energy and Environment, Jilin
   University, China (formerly 16 years at LBNL).
   Relevance: chief developer of TOUGHREACT, used for nuclear-waste-disposal
   and CO2-storage reactive transport; co-author on an October 2024
   radioactive-waste-disposal RTM benchmark dataset — direct DGR/radionuclide
   relevance. Very active 2024-2025 (seminars, keynotes). No COI found.

7. **Frank Heberling** — Institute for Nuclear Waste Disposal (INE), Karlsruhe
   Institute of Technology (KIT), Germany.
   Relevance: calcite/carbonate surface complexation modelling and
   mineral-water interface geochemistry directly relevant to the paper's
   surface-complexation formulation and its radionuclide/DGR application;
   completed habilitation June 2024 and authored the 2026 "Surface
   Complexation Models for Carbonate Minerals" review chapter — clearly
   active. No COI found.

8. **Ilenia Battiato** — Assistant Professor, Dept. of Energy Resources
   Engineering, Stanford University, USA.
   Relevance: upscaling of pore-scale reactive transport to Darcy/continuum
   scale, including deep-learning upscaling frameworks — directly relevant to
   the paper's DBS micro-continuum upscaling argument. Active through 2024
   (Stanford technical report on multiscale reactive fronts). No COI found
   (co-appears with Maes/Doster/Menke only as fellow attendees at CMWR 2024 —
   no shared authorship).

9. **Catherine Noiriel** — Associate Professor, Géosciences Environnement
   Toulouse (GET), Université Paul Sabatier / CNRS, France.
   Relevance: pore-scale X-ray imaging and reactive-surface-area evolution
   during dissolution (cited: `noiriel2009changes`) — relevant to the paper's
   image-based porous-media validation approach. Active, hosted the 2025
   Reactive Transport Workshop in Cologne. No COI found.

10. **Ralf Haese** — Professor of Environmental Geochemistry, School of
    Geography, Earth and Atmospheric Sciences, University of Melbourne,
    Australia.
    Relevance: closest direct methodological analogue outside the cited
    porousMedia4Foam lineage — developed a COMSOL-PhreeqC pore-scale coupling
    (`jyoti2021validation`, cited) structurally similar to this paper's
    OpenFOAM-PhreeqcRM coupling; recent work also covers copper mobilisation
    from low-grade ore (critical-mineral relevance). No COI found.

## Considered but deprioritized (not COI — weaker fit or uncertain current status)

- **Saideep Pavuluri** (`porousMedia4Foam` co-author) — ResearchGate profile
  lists him as "PostDoc Position" with no confirmed publication activity found
  past 2022; early-career and current institution/status unclear from search.
  Worth a second look if the shortlist needs padding, but Tournassat and
  Claret cover the same methodological ground with clearer current seniority
  and activity.
- **David Dzombak** (Carnegie Mellon) — co-author of the foundational
  `dzombak1990surface` (Dzombak & Morel) hydrous-ferric-oxide surface
  complexation reference. Still an active CMU professor, but search turned up
  no clearly recent (2023-2025) publication specifically on surface
  complexation methods — likely more valuable as a very senior "elder
  statesman" check than an actively-current technical reviewer.
- **Vitaliy/Vitalii Starchenko** (Oak Ridge National Laboratory) — wormhole/
  dissolution pore-scale modelling, co-author on the `molins2021simulation`
  benchmark review; no clear 2023-2025 publication activity surfaced in
  search (most recent confirmed work is 2018).
- **David L. Parkhurst / Scott R. Charlton** (USGS) — authors of PHREEQC and
  PhreeqcRM itself (`parkhurst2013phreeqc`, `parkhurst2015phreeqcrm`,
  `charlton2011modules`). Technically the most authoritative reviewers of the
  paper's core coupling tool, but USGS scientists of this seniority are
  atypical picks for journal peer review and would effectively be reviewing
  an application of their own software — flagging as a backup option rather
  than a primary recommendation.

## Excluded for conflict of interest

These authors appear directly in the paper's own `references.bib` as
co-authors with Menke and/or Maes within the last ~3-5 years — a clear,
easily-documented conflict:

- **Cyprien Soulaine** — co-author with *both* Julien Maes and Hannah Menke on
  `maes2022vos` (Maes, Soulaine, Menke, *Frontiers in Earth Science*, 2022).
  He is otherwise the single most obvious reviewer choice (lead author of
  `porousMedia4Foam` and the DBS/micro-continuum foundational papers
  `soulaine2016micro`, `soulaine2017mineral`, `soulaine2024microcontinuum`,
  all cited), but the direct 2022 co-authorship with both paper authors is
  disqualifying.
- **Sebastian Geiger** — co-author with Julien Maes on `maes2018direct`
  (2018) and with Hannah Menke on `menke2021upscaling` (2021).
- **Martin J. Blunt** and **Branko Bijeljic** — both co-authors with Hannah
  Menke on `menke2015dynamic` (2015) and `menke2018fourd` (2018); Blunt was
  Menke's PhD advisor at Imperial College.

## Note on Florian Doster's own recent co-authors

Searched Doster's recent (2022-2026) publication record directly to check for
additional conflicts not visible from the paper's own bib. His recent
co-authors (Ahmed ElSheikh, Shahin Kord, S. Moslehi, H. Fazeli, S. Achuo Dze,
T. Phillips, and internal Heriot-Watt collaborators) do not overlap with
anyone on the shortlist above.
