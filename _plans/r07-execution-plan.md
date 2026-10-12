---
title: "r07 Execution Plan (Phase 8)"
layout: plan
render_with_liquid: false
---

# r07 Execution Plan — Phase 8 (polish + deck + launch)

Relay on branch `docs/r07-polish`, mirroring `_plans/r06-execution-plan.md`.
Standing approval: run batches without gating once the plan is approved.

**USER-CONFIRMED DECISIONS (gate):** (A) Deck = **separate follow-up iteration**, not
r07. (B) Bean-Validation = **harmonize ALL ~18 request-accepting Quarkus examples**, in
waves, each Docker-re-verified. (C-raw-JAX-RS) = **HARMONIZE** `@PathParam`/`@QueryParam`/
`@HeaderParam` → `@RestPath`/`@RestQuery`/`@RestHeader` across all Quarkus examples (user
overrode the "leave it" default). (E) rounding = **HALF_UP** both stacks.
**Execution split into two parallel branches (disjoint files):** `docs/r07-polish` =
PR1 site-polish + PR2 voice sweep (_docs prose + chrome); `docs/r07-examples` = PR3
idiom + Bean-Validation + raw-JAX-RS + rounding (examples/ code). Hub + deck separate. The site
is **content-complete** — all 27 chapters + the CRC appendix + 24 examples are
merged to main, CI is green (22 example matrix jobs + the `k8s-manifests` static
job + site + contracts), Pages is live. Phase 8 is **polish, the deck, and
launch — not new chapters.** Five workstreams: a static site-polish backlog, a
book-wide voice + em-dash sweep, a per-example idiomatic retro-sweep (the
Quarkus Bean-Validation harmonization is the heavy part), the conference deck,
and a small quote-rounding pin. Two deliverables sit outside this repo/branch:
the deck (its own follow-up iteration) and the hub entry (a different repo).

## Approach
- **Split by track, not by chapter.** Static polish, prose voice sweep, and the
  per-example idiom/validation sweep are independently verifiable and land as
  separate PRs so a slow or failing Docker `verify.sh` never blocks the static
  polish. Nothing flips any coverage row — every chapter is already `verified`;
  this phase must keep them that way.
- **Judgment call A (Deck): scope now, ship separately.** The Drive source is
  reachable (`gws drive files list/export`); the REST source deck is
  "API Patterns and Practices REST (Final)"
  (id `11L1JfgDMox-H9bt-2SM5VkvS1Xftks28-hcp3Ghs82I`) in the "API decks" folder
  (id `1hnMyhGM5LmCgDK8CTEXpTrt9s26gi-Ye`). The deck is a large artifact built
  with `lgtm-presentation` and belongs in its own `presentation/` dir (as in
  `datamesh-reference-arch-quarkus/presentation/` and
  `cpp-concurrency-and-parallelism/presentation/`). It is **a follow-up
  iteration**, not part of r07. Rejected: folding it into the polish merge
  (couples a big artifact to launch-ready polish and delays it).
- **Judgment call B (Bean-Validation scope): all request-accepting Quarkus
  examples, in waves, each re-verified.** 21 Quarkus example dirs, **none** use
  Bean Validation today, ~15–18 hand-roll request validation. Harmonize them all
  rather than a subset, because a half-migrated set reintroduces the very
  Python/Quarkus divergence the sweep removes — but sequence in waves with a
  Docker `verify.sh` re-run gating each, anchors first (Ch4, Ch5, Ch6, Ch7,
  Ch27). This is the heaviest workstream (~15–18 Docker build+run re-verifies per
  stack). Rejected: big-bang all-at-once (unreviewable, opaque Docker failures);
  leaving it deferred (perpetuates divergence).
- **Judgment call C (Examples nav): generated index page (a table).** Both EIP
  (`_example_pages/index.md` → `/examples/`) and cpp-concurrency (`examples.html`
  + an `_examples` collection) ship a real index page, not a bare GitHub link.
  The `example_pages` collection + `/examples/:name/` permalink are **already
  configured** in this repo's `_config.yml`; only `_example_pages/index.md` is
  missing. Use a table (per `[[feedback_prefer_tables]]`) listing each
  `examples/*`: what it shows, both/single stack, a chapter link, a GitHub source
  link. Rejected: a bare GitHub examples/ link (weaker than the house pattern).
- **Judgment call D (PR structure): separate coherent PRs.** PR1 site-polish,
  PR2 voice-sweep, PR3 idiom+validation+rounding (REST repo); deck and hub as
  separate tracks. Rejected: one monolithic commit (unreviewable, couples static
  polish to Docker re-verify risk).
- **Judgment call E (rounding): HALF_UP on both stacks.** HALF_UP is the common
  commercial default and matches Java's existing `%.2f` behavior (least churn).
  Rejected: HALF_EVEN (banker's rounding — less common in pricing; more code
  change).

## Judgment call A — Deck accessibility + scope (resolved)
**Drive is reachable.** `gws drive files list` returned the "API decks" folder's
7 Slides decks; the REST deck is the source. So the deck CAN mine the real deck
text (export via `gws drive files export`), map slides to `lgtm-presentation`
conventions, and live in a top-level `presentation/` dir. **Recommendation: ship
the deck as its own follow-up iteration** (e.g. `docs/r08-deck`), de-risked by
confirmed source access, kept out of the r07 polish/launch merge. r07 does not
block on it.

## Judgment call B — Bean-Validation harmonization (resolved)
**Survey:** 21 Quarkus example dirs; **0** currently depend on
`quarkus-hibernate-validator` or use `jakarta.validation`; 18 hand-roll request
validation. The fix per example: add `quarkus-hibernate-validator`; annotate
request DTOs with `@NotBlank`/`@Size`/`@Positive`/`@Valid` (matching the Python
Pydantic `Field` constraints); add one `ConstraintViolationException` →
`application/problem+json` `ExceptionMapper` **preserving the existing Problem
title/detail parity** so `verify.sh`'s payload assertions still hold. **Scope:
all request-accepting Quarkus examples (~15–18), in waves**, each re-built and
re-run through Docker `verify.sh` (both stacks) before the next. Anchor wave:
Ch4, Ch5, Ch6, Ch7, Ch27. Then the remainder (Ch8, Ch10–Ch16, Ch20, Ch21,
Ch22, Ch24, Ch25). Cost is dominated by the Docker re-verify, so this is its own
PR (PR3) and may stage across sub-waves; a failed verify isolates here.

## Judgment call C — Examples nav (resolved)
Add `_example_pages/index.md` (`permalink: /examples/`, `layout: tutorial`,
`sectionid: examples` — already the collection default) with a hero + a **table**
of every `examples/*`: Example (link to GitHub source dir), What it shows, Stacks
(both / single), Chapter (link to the chapter page). Header nav: **remove "Plan",
add "Examples"** pointing at `/examples/`. The Plan page stays reachable from the
footer (Build & iteration plan link already there), so removing it from the top
nav loses nothing.

## Judgment call D — Batch / PR structure (resolved)
- **PR1 — site-polish (this repo):** outline restructure, header nav, examples
  index page, bibliography page + nav/footer links. Static; `validate.py` +
  `jekyll build`.
- **PR2 — voice-sweep (this repo):** book-wide prose voice + em-dash pass. Voice
  scan + wordcount `GATE=1` + build.
- **PR3 — idiom+validation+rounding (this repo):** idiom triage, Bean-Validation
  harmonization, rounding pin; per-example Docker `verify.sh` re-runs; may stage
  in waves. Isolated so Docker risk never blocks PR1/PR2.
- **Deck — separate iteration/branch** (judgment call A).
- **Hub — separate repo** `patterncatalyst-workshops-tutorials-list`, own branch
  + PR: a hand entry in `_data/sites.yml` and the reference books into
  `_data/books.yml`. Note `books.yml` is **machine-generated** by
  `scripts/gen-books.py` (scans allowlisted repos for citations) — add this repo
  to the allowlist and regenerate, then human-review the heuristic output;
  `sites.yml` is hand-edited (pick a group, e.g. "Cloud-Native & Kubernetes").

## Judgment call E — Quote-rounding pin (resolved)
**HALF_UP on both stacks.** Java: replace quote `%.2f` formatting with
`BigDecimal.setScale(2, RoundingMode.HALF_UP)`; Python: replace `:.2f` with
`Decimal.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)`. Affects the ~15
examples that compute/format a booking quote (Ch4, Ch5, Ch6, Ch7, Ch8, Ch10,
Ch11, Ch12, Ch13, Ch14, Ch20, Ch21, Ch24, Ch25, Ch27 — confirm per grep at
execution). Update Ch4 prose (`_docs/04-contract-first-openapi.md`, the
"real gap left open" paragraphs) to state both stacks are now pinned to HALF_UP.
Re-verify each changed example.

## Scope per workstream

### 1 — Site-polish (PR1, static)
- **Outline** `_docs/00-outline.md` — restructure the Part/Chapters table into a
  cleaner per-part layout with **one bullet per chapter, each an active link to
  its `/docs/NN-slug/` page**, keeping the `[H]`/`[C]` distinction (tag per
  bullet). Preserve `order: 0`, `overview: true`, `part: "Prerequisites & the
  Lab"`, and the `description`. Verify: `validate.py` (front matter unchanged),
  `jekyll build`, links resolve.
- **Header** `_includes/header.html` — remove the "Plan"
  (`/plans/iteration-plan/`) nav item; add "Examples" (`/examples/`). Verify:
  build + manual nav check.
- **Examples index** new `_example_pages/index.md` (`permalink: /examples/`) —
  table of all `examples/*`. Verify: build, `/examples/` renders, source/chapter
  links resolve.
- **Bibliography** new page (`permalink: /bibliography/`) — a **table** (not
  cards) of the five reference books: Amundsen, *RESTful Web API Patterns &
  Practices Cookbook*; Geewax, *API Design Patterns*; Gough et al., *Mastering API
  Architecture*; Dynowski, *Learning API Styles*; Lauret, *The Design of Web
  APIs, 2e*. Mirror `cpp-concurrency-and-parallelism/bibliography.html`. Add a
  "Bibliography" nav link and a footer link. Verify: build, `/bibliography/`
  renders.

### 2 — Voice + em-dash sweep (PR2, prose only)
- Sweep ALL `_docs/*.md` (Ch0–27 + appendix) with
  `~/.claude/skills/lgtm-professional-voice`. Baseline: **0 ban-tier**; watch:
  em-dash pileup (118 lines/23 files), "actually" (67/25). Target: keep 0
  ban-tier, **materially reduce em-dash pileup**, even out "actually", uniformly
  across the book. Prose only. Each chapter stays in the 2000–2500 word band.
  Verify: `scan.sh --tier ban` = 0; em-dash count down; `GATE=1 wordcount.sh`;
  build.

### 3 — Idiomatic retro-sweep of Ch0–24 examples (PR3)
- Run `~/.claude/skills/lgtm-idiomatic-review/scripts/scan.sh examples`.
  Baseline: 30 ban-tier (`print()` in 4 CLI check-scripts — triage, likely keep;
  `:latest` in 2 minikube manifests — pin or document) + 113 watch "raw JAX-RS
  param" across 27 files.
- **Bean-Validation harmonization** (judgment call B): per-example, waves,
  anchors first, Docker `verify.sh` re-run both stacks before the next.
- Verify: idiom `scan.sh` clean or every remaining hit triaged; every changed
  example `verify.sh` green locally then in the CI matrix.

### 5 — Quote-rounding pin (in PR3)
- Pin both stacks to HALF_UP across the ~15 quote-formatting examples; update Ch4
  prose; re-run `verify.sh` for each.

### Cross-repo (separate deliverables)
- **Deck** (own iteration): export the REST source deck, build via
  `lgtm-presentation` into `presentation/`, voice-pass the speaker notes.
- **Hub** (`patterncatalyst-workshops-tutorials-list`, own PR): `_data/sites.yml`
  hand entry + `_data/books.yml` via `scripts/gen-books.py` regeneration.

## Batches
1. **A (parallel static polish — PR1):** outline restructure; header nav; examples
   index; bibliography page + nav + footer links.
2. **B (sequential heavy work — PR3, each proven before next):** (a) idiom scan +
   triage ban-tier; (b) Bean-Validation harmonization per example in waves, Docker
   `verify.sh` re-green both stacks before moving on; (c) quote-rounding pin +
   Ch4 prose, re-verify each. (Voice sweep PR2 runs in parallel, prose-only.)
3. **D (validation — Opus + skills):** `lgtm-professional-voice` to 0 ban-tier
   book-wide + reduced em-dash; `lgtm-idiomatic-review` clean/triaged; Opus
   adversarial pass (Problem parity after Bean-Validation; rounding parity;
   wordcounts in band; outline links; nav correct).
4. **E (wrap):** full local gate; re-run voice + idiom scans; push each PR; watch
   CI; every changed example matrix job green; merge PR1, PR2, PR3. Deck + hub
   tracked as separate launch deliverables.

## Acceptance
- `validate.py` + wordcount `GATE=1` + `jekyll build --trace` green; chapters stay
  2000–2500 words.
- **0 voice ban-tier book-wide** + materially reduced em-dash pileup.
- Idiom scan clean or every remaining hit triaged with a reason.
- **Every changed example `verify.sh` re-green in CI**; Problem title/detail parity
  preserved after Bean-Validation; rounding pinned to HALF_UP, parity re-verified.
- Outline: every chapter an active link that resolves; `overview`/Part 0 preserved.
- Header nav has **Examples**, not **Plan**; `/examples/` index renders.
- Bibliography page renders as a table with all five books + a nav/footer link.
- Hub updated in the separate repo PR; deck per decision A (separate iteration).

## Risks (each with detection)
- **Voice sweep pushes a chapter out of band** → prose-only; re-run `GATE=1
  wordcount.sh` per chapter.
- **Bean-Validation breaks `verify.sh`** (Problem shape/status drift) → exception
  mapper preserves title/detail; per-example Docker re-verify both stacks in waves.
- **Idiom ban-tier mostly false-positive** (CLI `print()`, intentional minikube
  `:latest`) → triage with reasons; fix only substantive items.
- **Deck Drive access** → confirmed reachable; separate iteration so r07 never
  blocks; fall back to site content if access regresses.
- **Cross-repo hub** → separate branch/PR; `books.yml` machine-generated, so
  regenerate via `gen-books.py` + human review.
- **Scope/time** (idiom + Bean-Validation re-verify dominates) → three PRs, waves
  with per-example gating, deck + hub carved out.
