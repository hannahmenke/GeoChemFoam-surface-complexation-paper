# Findings: ORCID iDs for the three authors

Ticket: `.scratch/tpm-submission/issues/09-find-orcid-ids.md`

All three authors are confirmed, high confidence.

## Hannah P. Menke

- **ORCID: 0000-0002-1445-6354**
- **Confidence: high**
- Sources:
  - Heriot-Watt Research Portal profile, which surfaces the ORCID directly:
    https://researchportal.hw.ac.uk/en/persons/hannah-menke — lists ORCID iD
    `https://orcid.org/0000-0002-1445-6354`, affiliation "Associate Professor,
    School of Energy, Geoscience, Infrastructure and Society" / Institute of
    GeoEnergy Engineering, email `H.Menke@hw.ac.uk` (matches the paper's
    corresponding-author email `h.menke@hw.ac.uk`).
  - ORCID public API record (`https://pub.orcid.org/v3.0/0000-0002-1445-6354/person`)
    confirms name "Hannah Menke".
  - ORCID public works list for this iD includes papers co-authored with
    Julien Maes and Florian Doster (e.g. "A Deep-Learning Iterative Stacked
    Approach for Prediction of Reactive Dissolution in Porous Media",
    "Enhanced permeability estimation in microporous rocks using a hybrid
    macropore-Darcy approach", "A Benchmark Dataset for Machine Learning
    Surrogates of Pore-Scale CO2-Water Interaction"), consistent with the
    same research group / co-author network as the other two authors.
  - Note: the ORCID record's `employments` section is empty/private, so
    institutional affiliation confirmation for this ORCID rests on the HW
    Research Portal page (which explicitly links this ORCID to Hannah Menke)
    plus the matching email and shared co-authored works, rather than on the
    ORCID employment history itself.

## Julien Maes

- **ORCID: 0000-0002-3248-9758**
- **Confidence: high**
- Sources:
  - ORCID public API record
    (`https://pub.orcid.org/v3.0/0000-0002-3248-9758/employments`) lists
    employment history at "Institute of GeoEnergy Engineering" with roles
    Assistant Professor, Research Fellow, Post-Doctoral Research Associate,
    all at the organization disambiguated via ROR `04mghma93`, which
    resolves (via the ROR API) to **Heriot-Watt University**.
  - Crossref publisher metadata for `10.1007/s11242-021-01661-8`
    (= `maes2021geochemfoam` in this manuscript's own `references.bib`,
    "GeoChemFoam: Direct Modelling of Multiphase Reactive Transport in Real
    Pore Geometries with Equilibrium Reactions", *Transport in Porous
    Media*, 2021 — the same target journal as this submission) lists the
    author "Julien Maes" with ORCID
    `https://orcid.org/0000-0002-3248-9758` explicitly attached, and
    co-author "Hannah P. Menke" (ORCID not populated by publisher, but same
    person as above).
  - ORCID public works list includes GeoChemFoam / pore-scale / reactive
    transport / micro-CT papers co-authored with Hannah Menke and Florian
    Doster, matching the exact research area of this paper.
  - Web search corroboration: Heriot-Watt Research Portal
    (https://researchportal.hw.ac.uk/en/persons/julien-maes/), personal
    site https://www.julienmaes.com/, Google Scholar
    (https://scholar.google.co.uk/citations?user=xDC7VjkAAAAJ) — all
    describe the same "Assistant Professor, Institute for GeoEnergy
    Engineering, Heriot-Watt University, leads the GeoChemFoam group"
    person. (Note: the HW Research Portal person page itself did not
    render an ORCID link in a page-text fetch, likely a client-rendered
    widget not captured by simple HTML→text conversion — the ORCID API and
    Crossref confirmations above are the authoritative sources actually
    used here.)

## Florian Doster

- **ORCID: 0000-0001-7460-573X**
- **Confidence: high**
- Sources:
  - Heriot-Watt Research Portal profile
    (https://researchportal.hw.ac.uk/en/persons/florian-doster/) directly
    lists ORCID iD `https://orcid.org/0000-0001-7460-573X`, affiliation
    "Professor, School of Energy, Geoscience, Infrastructure and Society" /
    Institute for GeoEnergy Engineering, Heriot-Watt University.
  - ORCID public API record
    (`https://pub.orcid.org/v3.0/0000-0001-7460-573X/employments`) shows an
    employment entry at organization disambiguated via ROR `04mghma93`
    (= Heriot-Watt University, confirmed via ROR API), department
    "SET-IT" (School of Energy, Geoscience, Infrastructure and Society),
    role "Academic Member".
  - ORCID public works list includes papers co-authored with Hannah Menke
    and Julien Maes (e.g. "A Deep-Learning Iterative Stacked Approach for
    Prediction of Reactive Dissolution in Porous Media", "A Benchmark
    Dataset for Machine Learning Surrogates of Pore-Scale CO2-Water
    Interaction"), matching the same reactive-transport/porous-media
    co-author network as the other two authors.
  - Web search corroboration: Google Scholar
    (https://scholar.google.com/citations?user=YOh8aUgAAAAJ), Heriot-Watt
    news item on his inaugural lecture as Professor at IGE.

## Cross-checks performed

- Verified the ROR id `04mghma93` (attached to both Maes's and Doster's
  ORCID employment records) resolves to "Heriot-Watt University" via the
  ROR API (`https://api.ror.org/v2/organizations/04mghma93`).
- Compared the ORCID "works" lists of all three iDs and found multiple
  shared co-authored publications across all three (Maes+Menke+Doster
  jointly on "A Deep-Learning Iterative Stacked Approach for Prediction of
  Reactive Dissolution in Porous Media" and "A Benchmark Dataset for
  Machine Learning Surrogates of Pore-Scale CO2-Water Interaction"), which
  is strong evidence that these three ORCID iDs genuinely belong to the
  same research group / co-author trio as the paper's author list, not
  merely a name-string match.
- Checked Crossref metadata for the manuscript's own cited GeoChemFoam
  papers (`maes2021geochemfoam`, `maes2022vos`, `maes2024dispersivity`);
  only `maes2021geochemfoam`'s Crossref record carries a populated ORCID
  field, but it matches Julien Maes's ORCID found above.

## Summary table

| Author | ORCID | Confidence |
|---|---|---|
| Hannah P. Menke | 0000-0002-1445-6354 | high |
| Julien Maes | 0000-0002-3248-9758 | high |
| Florian Doster | 0000-0001-7460-573X | high |
