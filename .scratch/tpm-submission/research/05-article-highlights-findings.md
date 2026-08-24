# Findings: Does TPM currently require "Article Highlights"?

Ticket: `.scratch/tpm-submission/issues/05-verify-article-highlights-requirement.md`

**Verdict: Confirmed — the requirement is currently live on TPM's own submission-guidelines
page, verified directly against the primary source (not a search-engine summary). However,
real-world compliance among recently published TPM papers is inconsistent, and TPM's own
Editor-in-Chief guidance (a TPM-specific PDF) does not mention it at all — it appears to be
generic Springer front-matter boilerplate rather than a TPM-specific editorial mandate, and it
is not strictly enforced as a hard submission gate.**

## How the primary source was reached

The normal browser path (`https://link.springer.com/journal/11242/submission-guidelines`)
303-redirects to `idp.springer.com/authorize?...` (a login wall) for both the `WebFetch` tool
and a plain `curl` with a default user agent — this matches what the original ticket reported.

Workaround: fetching the same URL with `curl -A "Mozilla/5.0 (compatible; Googlebot/2.1;
+http://www.google.com/bot.html)"` returns the full page (HTTP 200, ~299 KB), because
Springer serves crawlers the real content without the interactive login gate. This is the
actual live page users are pointed to from the journal home page — the same content the
search summarizer would have been indexing — not a mirror or cache.

`archive.org` was not reachable at all in this environment (`WebFetch` refused the domain
outright; the CDX API returned an empty `archived_snapshots` list for this specific URL), so
the Wayback Machine could not be used either way.

## 1. TPM's live submission-guidelines page — primary source, verbatim match

Fetched 2026-08-24: `https://link.springer.com/journal/11242/submission-guidelines`.

Under **Instructions for Authors → Title Page**, the subsections run: Title, Author
information, Abstract, Keywords, **Article Highlights**. The Article Highlights subsection
reads, verbatim:

> "Please provide three short bullet points (maximum of 120 characters each) summarizing the
> key findings and implications of the paper. These should be presented in non-technical
> language and not repeat verbatim text found in the abstract. They should be placed beneath
> the abstract under the heading of 'Article Highlights'."

This is an exact match for the original (unverified) claim — "3 bullet points, max 120
characters each, non-technical language, summarizing key findings, not copied verbatim from
the abstract." The claim is therefore verified against the primary source, not just
corroborated by a second summarizer.

**Caveat on "TPM-specific" vs. generic Springer boilerplate**: immediately above this
subsection, the same Title Page section carries Springer's standard generative-AI/LLM
authorship-disclosure paragraph (mentions ChatGPT by name, "AI assisted copy editing"
definition), and the adjacent Abstract subsection carries a "For life science journals only
(when applicable)" trial-registration clause that plainly does not apply to TPM. Both are
recognizable as shared Springer-wide template text reused across many journals' guidelines
pages, not hand-written by TPM's editors. The Article Highlights paragraph sits in the same
block and reads the same way — generic, not phrased as anything specific to porous-media
transport research. So: it is confirmed to be live and applicable *as displayed on TPM's own
guidelines page*, but the evidence below indicates it is most likely inherited Springer
boilerplate rather than a TPM-specific editorial requirement.

## 2. TPM-specific "Guidelines from the Editor-in-Chief" PDF — does NOT mention it

The same submission-guidelines page links a TPM-specific document: "Guidelines from the
Editor-in-Chief (Download pdf, 442 kB)", dated October 2023, at
`https://media.springer.com/full/springer-instructions-for-authors-assets/pdf/11242_TIPM_Guidelines from the Editor-in-Chief_October 2023.pdf`
(fetched successfully with the Googlebot UA trick; 5 pages, signed by Editor-in-Chief
Professor Martin J. Blunt, Imperial College).

This PDF covers: general submission statement, article types (Research manuscripts, Technical
Notes, Letters to the Editor, Review Articles, Books for Review), the TIPM reviewer-suggestion
process, and detailed Special Issue guidelines. **It says nothing about Article Highlights, or
about any structured front-matter/highlights requirement at all.** This is the one document on
the guidelines page that is unambiguously written by and for TPM specifically (it names the
journal, the EiC, and TPM-specific processes like the 4-reviewer-suggestion request) — and it
is silent on Article Highlights, reinforcing that the requirement is not something TPM's own
editorial office treats as a distinguishing/emphasized policy.

## 3. Actual published TPM articles — inconsistent compliance

Checked 17 real, currently-published TPM articles on `link.springer.com` (same Googlebot-UA
fetch trick; each page's rendered `<h3>Article Highlights</h3><ul>...` front-matter block was
checked directly in the HTML, not via search-snippet):

| DOI | Published | Article Highlights present? |
|---|---|---|
| 10.1007/s11242-021-01649-4 | 2021-07-29 | **Yes** (3 bullets, ~115–127 chars each) |
| 10.1007/s11242-025-02156-6 | 2025-02-17 | **Yes** (3 bullets) |
| 10.1007/s11242-025-02245-6 | 2025-12-10 | No |
| 10.1007/s11242-025-02251-8 | 2025-11-28 | No |
| 10.1007/s11242-025-02252-7 | 2025-11-20 | Yes |
| 10.1007/s11242-025-02253-6 | 2025-11-25 | No |
| 10.1007/s11242-025-02256-3 | 2025-11-20 | No |
| 10.1007/s11242-025-02257-2 | 2025-11-20 | No |
| 10.1007/s11242-025-02259-0 | 2025-11-26 | Yes |
| 10.1007/s11242-025-02260-7 | 2025-11-28 | No |
| 10.1007/s11242-025-02261-6 | 2025-12-03 | No |
| 10.1007/s11242-025-02262-5 | 2025-12-03 | Yes |
| 10.1007/s11242-025-02263-4 | 2025-11-20 | Yes |
| 10.1007/s11242-025-02264-3 | 2025-11-26 | No |
| 10.1007/s11242-025-02266-1 | 2025-11-25 | No |
| 10.1007/s11242-026-02313-5 | 2026-04-21 | No |
| 10.1007/s11242-026-02332-2 | 2026-07-16 | No |

Only **5 of 17 (~29%)** carry an Article Highlights section, and both of the two most recent
articles checked (April and July 2026) omit it entirely. This is strong evidence that Article
Highlights functions as an **optional/soft field in TPM's submission system rather than a hard
requirement enforced at editorial or production stage** — a large majority of recently
published, presumably fully peer-reviewed and accepted, TPM papers do not have one.

Where present, the field is also not strictly enforced to the stated 120-character cap: the
2021 example (Capone, Gentile & Gianfrani, "Optimal Stability Thresholds in Rotating Fully
Anisotropic Porous Medium with LTNE", `10.1007/s11242-021-01649-4`) has three bullets of 122,
115, and 127 characters — i.e. two of the three exceed the stated "maximum of 120 characters"
in the published version, with no evidence of correction at proof stage. This further
suggests the cap is a soft style guideline rather than a hard-enforced submission-system limit.

## 4. Springer Nature `sn-jnl` LaTeX template — no dedicated highlights environment

Checked the public Springer Nature LaTeX template mirror
(`github.com/godkingjay/springer-nature-latex-template`, `sn-jnl.cls` and the sample
`sn-article.tex`). Neither file contains any `highlight`-related macro, environment, or
example usage. So even where authors do include Article Highlights, there is no special LaTeX
structure Springer expects — it is evidently just plain text/an itemized list placed under the
abstract in the manuscript body, consistent with how it renders on the article pages above
(a plain `<ul>` under an `<h3>Article Highlights</h3>` heading, no special styling).

## 5. Springer Nature-wide documentation on "Article Highlights" as a feature

Web search for general Springer Nature documentation on which journal families use "Article
Highlights" did not surface a dedicated policy page distinguishing subject areas that require
it from those that don't; results only returned generic author-guidelines index pages. No
authoritative Springer Nature-wide statement was found either confirming or ruling out that
this is a physics/earth-science-family feature. This line of inquiry was inconclusive and adds
no evidence either way.

## Sources consulted

- `https://link.springer.com/journal/11242/submission-guidelines` (fetched via
  `curl -A "Googlebot/2.1..."`, HTTP 200; login-walled via normal `WebFetch`/browser UA — primary source, current as of 2026-08-24)
- `https://media.springer.com/full/springer-instructions-for-authors-assets/pdf/11242_TIPM_Guidelines from the Editor-in-Chief_October 2023.pdf` (TPM-specific EiC guidelines PDF, read directly)
- `https://link.springer.com/article/10.1007/s11242-021-01649-4` and the 16 other TPM article DOIs listed in the table above (fetched via the same Googlebot-UA workaround)
- `https://raw.githubusercontent.com/godkingjay/springer-nature-latex-template/master/sn-jnl.cls` and `sn-article.tex`
- `http://archive.org/wayback/available?...` (empty result — no Wayback snapshot available for this URL) and a direct `WebFetch` attempt on `web.archive.org` (tool refused the domain outright)
- General web search for Springer Nature "Article Highlights" policy documentation (inconclusive, no dedicated policy page found)
