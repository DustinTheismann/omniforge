# Paper — submission plan

Target for `paper/proofforge-omega.md` (decision of 2026-06-06, recorded here so
it doesn't live only in chat).

## Venue

1. **arXiv — now (primary, immediate).** Citable + establishes priority, no
   gatekeeping. The article-class build is already arXiv-ready: arXiv compiles
   LaTeX source, and `paper.yml` emits a CI-verified `proofforge-omega.tex` +
   PDF. Nothing structural is needed to post.
2. **CICM — Conference on Intelligent Computer Mathematics, Systems & Projects
   track (peer-reviewed home).** Springer LNAI/LNCS, ≤ 15 pp + bibliography.

### Why CICM
It is this paper's exact community — CAS + proof-assistant integration,
mathematical knowledge management, OpenMath (which the paper cites) — and the
Systems & Projects track is designed for implementations / integrations / case
studies at proof-of-concept maturity, where the honest "small-scale PoC" framing
fits rather than counts against. **ITP was the runner-up and rejected**: this is
a systems/integration paper, not a new proof technique or a Lean library, so ITP
would undervalue the unification thesis and ignore the CAS lane.

### Timing (important)
- **CICM 2026** (Ljubljana, 21–25 Sep 2026): submission **closed** — deadlines
  were abstract 25 Mar / paper 1 Apr 2026. Not an option.
- **CICM 2027**: target the S&P track when its CFP opens (~early 2027).
- **arXiv**: open now; post the current draft immediately.

## State

- Content: complete draft; every empirical claim cross-referenced to a repo file
  or CI workflow; bibliography source-verified (14 refs).
- Build: `paper.yml` typesets MD → PDF + `.tex` via pandoc → pdflatex, **fails
  closed on a missing glyph**, green on `main`. PDF/`.tex` are CI artifacts.

## Remaining work (owner-action)

Outward / editorial — not automatable here:
- [ ] Author + **affiliation** line (not invented in the draft).
- [ ] **Post to arXiv** (the irreversible step; cannot be done from CI).

Before CICM 2027 (mechanical, can be done on request):
- [ ] Port to LNCS class (`llncs`) + a pandoc-LNCS template; CI must still build.
- [ ] Add the VIPR (IPCO 2017) chapter DOI — flagged unconfirmed in the bib.
- [ ] Trim to ≤ 15 pp if needed; polish to the template.

Deliberately deferred: the LNCS port is premature for an ~April-2027 deadline and
unnecessary for arXiv, so it is not done yet.
