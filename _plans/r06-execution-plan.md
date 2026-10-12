---
title: "r06 Execution Plan (Phase 7)"
layout: plan
render_with_liquid: false
---

# r06 Execution Plan — Phase 7 content (Ch25–Ch27 + Appendix A)

Relay on branch `docs/r06-content`, mirroring `_plans/r05-execution-plan.md`.
Standing approval: run batches without gating once the plan is approved.
Part 11 is the "running it" tier (Compose → minikube → CRC); Part 12 is the
integrative complete project. Four [H] deliverables: Ch25, Ch26, Appendix A,
Ch27. The crux of this phase is **CI feasibility**: GitHub Actions gives us
Docker Compose only — no Kubernetes cluster, no GPU, bounded time — so the
cluster tiers (Ch26 minikube, Appendix A CRC) cannot sit in the examples
matrix, and the LGTM tier must be proven in CI without dragging the matrix
under. The contracts in `contracts/{openapi,asyncapi,schemas,cloudevents,arazzo}`
are already built; Ch27 ties them together end to end — it does NOT recreate
them.

## Approach
- Four [H] deliverables, each 2,000–2,500 words prose + >=1 paired
  SVG+`.excalidraw` figure (`scripts/generate_diagram.py`, amber `#e8870c`).
  Both-stack chapters (Ch25, Ch27) use `{% include codetabs.html langs="Quarkus|Python" %}`
  (exactly two fenced blocks); single-concern ops material (Ch26 manifests,
  Appendix A Routes/S2I) may use plain fenced blocks.
- The project **already standardizes on the single-container
  `grafana/otel-lgtm` image** (seen in every example's `compose.yaml` behind a
  `profiles: ["observability"]` block, OFF by default). That one container
  bundles Grafana + Tempo + Loki + Mimir + the OTel Collector and exposes OTLP
  (4317/4318) and Tempo's query API (3200). This is the lever for judgment call
  A: a real end-to-end trace assertion is CI-affordable because it is one
  image, not a five-service stack.
- **Judgment call A (Ch25 LGTM-in-CI): OPTION 1 — real trace, asserted via
  Tempo's query API.** CI brings up the app(s) + the single-container
  `otel-lgtm`, drives one request, and polls Tempo until the request's trace is
  queryable with spans from the service. Rejected option 2 (gate all LGTM out,
  assert only propagation headers) — it demotes the chapter's entire thesis
  ("one request traced end to end") to a doc check when the single-container
  image makes the real assertion bounded and deterministic.
- **Judgment call B (Ch26/Appendix A, clusterless CI): tier per chapter.** Ch26
  (minikube) earns "verified" by a **real local bring-up by the executor**
  (minikube, `MINIKUBE_DRIVER=docker`) capturing proof (pods Ready, a live
  request, a trace), PLUS static manifest validation in a **non-matrix** CI
  job. Appendix A (CRC) earns it by **static validation in that same non-matrix
  job + documented bring-up**, with real CRC bring-up **best-effort** (CRC is
  far heavier than minikube). Rejected: putting either in the examples matrix
  (there is no cluster on the runner — it would fail every push). Neither
  directory may contain a matrix-discoverable `examples/*/verify.sh`.
- **Judgment call C (Ch27 scope): integrative both-stack example assembled from
  existing chapter code, with a bounded CI-matrix `verify.sh`.** Ch27 wires the
  capabilities already built across Ch8–Ch21 into ONE service per stack and
  proves the full flow on the live REST+event path. Rejected: a from-scratch
  mega-build (scope balloon) and a prose-only "see the other chapters" with a
  token example (under-delivers on "complete project end to end").

## Judgment call A — Ch25 LGTM-in-CI shape (resolved)
**Chosen: Option 1 — bring up app(s) + the single-container `otel-lgtm`, trace
one request, and assert the trace was actually exported by querying Tempo.**

Why it is CI-safe and deterministic:
- **One container, not five.** `grafana/otel-lgtm` (the exact image already
  pinned behind the `observability` profile in every example compose) runs
  Grafana, Tempo, Loki, Mimir and the OTel Collector in a single process. Its
  healthcheck (`/api/health`, `start_period: 30s`) already exists in the repo's
  pattern, so boot is bounded and we gate on health before driving traffic.
- **Deterministic trace assertion.** The app is configured to export OTLP to
  the collector (`OTEL_EXPORTER_OTLP_ENDPOINT=http://lgtm:4317`,
  `OTEL_TRACES_SAMPLER=always_on`). `verify.sh` sends one request carrying a
  **known W3C `traceparent`** (fixed trace-id), then polls Tempo's query API
  (`GET http://localhost:3200/api/traces/<trace-id>`) with a bounded timeout
  until the trace resolves, and asserts it contains a span whose
  `service.name` is the app and whose span name covers the HTTP route. Using a
  caller-supplied trace-id removes the "which trace-id did the server pick"
  flakiness; always-on sampling removes sampling flakiness.
- **The rest of LGTM stays documented + locally runnable.** The full Grafana
  dashboards, the logs (Loki) and metrics (Mimir) correlation views, and the
  "follow the trace across services" walkthrough are written in the chapter and
  reproducible locally (Grafana at `:3000`), but CI asserts only the one
  deterministic thing: a span for the one request reached the backend.

**Rejected — Option 2** (tier-gate all of LGTM local-only; CI checks only
compose bring-up + propagation headers): the chapter's one job is to show a
request traced end to end. Asserting only that a `traceparent` header is
present proves propagation, not export/collection — the teaching core. Because
the single-container image is CI-affordable, there is no reason to settle for
the weaker check. The `observability` profile stays the local-dev pattern
everywhere else; Ch25 is the one place CI turns it on.

## Judgment call B — Ch26 (minikube) + Appendix A (CRC) verification tier (resolved)
GitHub Actions has no minikube/CRC cluster, so **neither can be in the
`examples/*/verify.sh` matrix** — a cluster-dependent `verify.sh` on a
clusterless runner fails every push. The footgun is concrete: the matrix
discovery glob is `examples/*/verify.sh` (one level deep). Resolution:

- **Directory + naming (the footgun fix).** Ch26 artifacts live at
  `examples/26-minikube/` and Appendix A at
  `examples/99-appendix-a-openshift-crc/`, but **neither directory contains a
  `verify.sh`**. The local runners are named `run-minikube.sh` and
  `run-crc.sh`; manifests live in `k8s/` (kustomize) and `helm/` subdirs. The
  glob cannot match `run-*.sh`, so the matrix never tries to run them. A
  one-line guard is added to `scripts/validate.py` (or asserted in the new
  static job): `examples/26-minikube` and `examples/99-appendix-a-openshift-crc`
  MUST NOT contain a `verify.sh`.
- **To avoid any app rebuild in these tiers**, both deploy the **same container
  images/app code as Ch25** (and/or Ch27); the Ch26/AppA directories hold only
  manifests + runner + README, no second copy of the service.
- **Ch26 (minikube) — tier (i): real local bring-up + static CI.** The executor
  actually brings the stack up locally with the `lgtm-minikube-stack` skill,
  **`MINIKUBE_DRIVER=docker`** (docker driver — docker is already installed here;
  minikube also supports containerd. CRC is separate: its own OpenShift-Local VM on crun.),
  and captures real proof into the chapter/README: `kubectl get pods` all
  Ready, a live request through the Ingress, and a trace visible in Grafana.
  CI adds a **non-matrix** `k8s-manifests` job that runs
  `kustomize build examples/26-minikube/k8s | kubeconform` and
  `kubectl apply --dry-run=client` (client-side, no cluster).
- **Appendix A (CRC) — tier (ii): static CI + documented bring-up, real
  bring-up best-effort.** CRC needs a full OpenShift VM and is far heavier than
  minikube, so "verified" is earned by `helm lint` + `helm template | kubeconform`
  in the same non-matrix job, plus a complete documented bring-up authored with
  the `lgtm-crc` skill (crc-admin kubeconfig context, pinned-CSV operators,
  edge-TLS Routes, binary S2I in-cluster build on ubi10/openjdk-25). The
  executor attempts a real CRC bring-up and captures proof **if the environment
  allows**; it is not a merge gate. Every container project ends with a CRC
  appendix (house standard), so the appendix ships regardless.

Both chapters flip to `verified` on: static job green + (Ch26) captured
real-cluster proof / (AppA) captured proof or a documented, reviewed bring-up.

## Judgment call C — Ch27 complete-project scope (resolved)
**Chosen: a NEW cohesive both-stack example, `examples/27-complete-project/`,
that assembles the capabilities already built across earlier chapters into ONE
service per stack and proves the full flow with a bounded CI-matrix
`verify.sh`.** It reuses existing example source (the Ch21 service is the
closest base: it already pairs REST with a background CloudEvents stream over
the shared schema) and layers in the remaining capabilities rather than
re-inventing them.

What the single service exposes (the end-to-end narrative):
- contract-first **booking + cargo** (`POST /bookings` -> 201 + `Location`,
  bodies vs `#/$defs/Booking`);
- **async confirmation** 202 -> poll -> 303 (Ch10 pattern);
- **keyset pagination** over bookings (Ch8);
- **HATEOAS** state-dependent links (Ch12);
- **media-type versioning** negotiation (Ch14);
- **soft delete + purge** with filtered reads (Ch13);
- **streamed manifest** (NDJSON, incremental) (Ch16);
- **background CloudEvents stream** over Kafka, AsyncAPI-described, sharing
  `contracts/schemas/shipping.schema.json` with the REST contract (Ch21);
- the **Arazzo workflow** (`contracts/arazzo/booking-workflow.yaml`) tying the
  sequence together.

What `verify.sh` asserts (bounded, matrix-safe, both stacks): the selftest gate;
POST booking -> 201 + Location, body vs `#/$defs/Booking`; async confirm
202 -> poll -> 303; one keyset page returns and the cursor advances; HATEOAS
links present for the resource's state; a versioned media type negotiates;
soft-delete then filtered GET hides it, purge removes it; the NDJSON manifest
arrives incrementally (`curl -N` + line counts); the background CloudEvents
`BookingEvent` is consumed from Kafka with a **bounded** timeout and validated
(envelope + `data` vs `#/$defs/BookingEvent`); the static "one schema, two
protocol contracts" grep holds; the Arazzo document validates structurally.

What is deliberately kept OUT of Ch27's CI gate to prevent balloon: **LGTM
tracing** rides the `observability` profile (local-only; Ch25 already proves
trace export in CI), and **load testing** reuses the Ch24 Newman harness as a
small, bounded, optional run documented in the README — CI asserts
pass/counts, never latency. This keeps Ch27's matrix job close to Ch21's
wall-clock (REST + Kafka + CloudEvents) rather than ballooning it.

**Rejected — from-scratch mega-build:** rebuilding every capability fresh in
one example is a huge, slow, flaky matrix job and duplicates code already
proven in Ch8–Ch21. **Rejected — prose-only orchestration with a token
example:** "see the other chapters" under-delivers on the "complete project end
to end" promise and leaves the integrative claims unverified.

## Scope / Examples (UNIQUE host ports; continue Quarkus 81xx / Python 80xx)
Survey of existing composes: Quarkus host ports used through 8104, Python
through 8023, Kafka external 19092, Apicurio 8104, OpenMetadata 8585, and the
shared `otel-lgtm` ports 3000/4317/4318/9090/3100/3200. Fresh picks below.

- `examples/25-local-with-docker-compose` — **both** stacks + `otel-lgtm`
  (the LGTM tier is ON in this example's CI, unlike the repo default),
  Quarkus `8105` / Python `8024`, project `ch25-local`. `otel-lgtm` keeps the
  standard ports (3000/4317/4318/9090/3100/3200). **In the CI matrix.**
  `verify.sh` asserts (judgment call A): compose up + LGTM healthy; one request
  with a fixed `traceparent` per stack -> poll Tempo
  `GET :3200/api/traces/<id>` (bounded) -> a span with the service's
  `service.name` and HTTP route exists; the response body validates vs
  `#/$defs/Booking`. Full Grafana/logs/metrics correlation documented + locally
  runnable.
- `examples/26-minikube` — **not in the matrix** (no cluster on the runner).
  Holds `k8s/` (kustomize: Deployment(s), Service, Ingress, probes,
  ConfigMap/Secret, HPA), `run-minikube.sh` (local bring-up via
  `lgtm-minikube-stack`, `MINIKUBE_DRIVER=docker`), and README. **No
  `verify.sh`.** Deploys the Ch25 images. CI: static `kustomize build |
  kubeconform` + `--dry-run=client` in the non-matrix `k8s-manifests` job.
  "Verified" also requires captured real-cluster proof (pods Ready, live
  request, trace).
- `examples/99-appendix-a-openshift-crc` — **not in the matrix**. Holds
  `helm/` (restricted-v2 chart, edge-TLS Routes), optional `k8s/` for S2I build
  config, `run-crc.sh` (bring-up via `lgtm-crc`), and README. **No
  `verify.sh`.** CI: static `helm lint` + `helm template | kubeconform` in the
  `k8s-manifests` job. "Verified" on static-green + documented/captured
  bring-up (real CRC best-effort).
- `examples/27-complete-project` — **both** stacks + Kafka (KRaft) + `otel-lgtm`
  behind the `observability` profile (local-only), Quarkus `8106` / Python
  `8025`, Kafka external `19093`, project `ch27-complete`. **In the CI matrix.**
  `verify.sh` asserts the full end-to-end flow listed in judgment call C;
  tracing and load ride local-only profiles, out of the gate.

## Figures (paired svg+excalidraw; specs in `scripts/diagrams/`)
`25-local-with-docker-compose` — a request's path from client -> app -> OTel
Collector -> Tempo -> Grafana, one trace highlighted end to end.
`26-kubernetes-on-minikube` — Compose vs minikube side by side: compose DNS vs
Service/Ingress, liveness/readiness probes, ConfigMap/Secret, HPA scaling.
`appendix-a-openshift-crc` — CRC topology: edge-TLS Route -> Service -> Pod,
with the in-cluster binary S2I build feeding the image.
`27-complete-project` — the booking/cargo lifecycle across the REST surface +
the background CloudEvents stream + the Arazzo workflow, traced through LGTM.
(spec files `fig_25_local_with_docker_compose.py`,
`fig_26_kubernetes_on_minikube.py`, `fig_appendix_a_openshift_crc.py`,
`fig_27_complete_project.py`, amber `#e8870c`, via `scripts/generate_diagram.py`.)

## Parts (existing `_parts/` run 00–10; add 11 and 12)
- `_parts/11-running-it.md` (order 11) — `part_name: "Running it: Docker → minikube → CRC"`,
  `title` + `blurb` to match. Ch25, Ch26 and Appendix A set `part:` to that
  exact string.
- `_parts/12-complete-project.md` (order 12) — `part_name: "Complete project"`;
  Ch27 sets `part:` to that string.

## Appendix ordering (resolve in Batch A — it is an acceptance item)
The nav derives order from front-matter `order`: `part_index.html` sorts a
part's docs by `order` and labels each "Chapter {{ doc.order }}" (unless
`order == 0` -> "Overview"); `tutorial.html` sorts all non-overview docs by
`order` for the big numeric marker and the prev/next pager. No appendix
convention exists yet.

**Recommendation:** `_docs/99-appendix-a-openshift-crc.md` with
`order: 99` (matches the filename and the existing coverage row, keeps an
integer so the marker padding never sees a float), `part: "Running it: Docker → minikube → CRC"`,
plus two new flags `appendix: true` and `appendix_label: "A"`. Add **minimal**
display handling (Batch A, touches `_layouts/`): in `part_index.html` render
"Appendix {{ doc.appendix_label }}" instead of "Chapter {{ doc.order }}" when
`doc.appendix`; in `tutorial.html` render the label ("A") in place of the
padded number when `page.appendix`. With `order: 99` the appendix reads last in
the linear pager (the conventional place for an appendix) while still appearing
as a card under Part 11's part page. (Alternative considered — a float `order:
26.5` to seat it inside Part 11's read-flow — rejected: it breaks the
integer-marker padding and the "Chapter 26.5" label.) `validate.py` requires
`title/order/part/description` on the appendix and does not enforce a
contiguous order sequence, so `99` is safe.

## Batches
1. **A (parallel):** two Part pages (`_parts/11-running-it.md`,
   `_parts/12-complete-project.md`); four figure specs + generated pairs
   (25, 26, appendix-a, 27); the minimal appendix display handling in
   `_layouts/{part_index,tutorial}.html` + the `appendix`/`appendix_label`
   front-matter convention; the `k8s-manifests` non-matrix CI job added to
   `.github/workflows/contracts.yml` (kustomize/helm/kubeconform/dry-run); the
   `validate.py` guard that `examples/26-minikube` and
   `examples/99-appendix-a-openshift-crc` contain no `verify.sh`. Coverage rows
   stay `planned` until prose lands.
2. **B (sequential example/infra builds — each proven before the next; prose
   after its example):**
   a. **Ch25** `examples/25-local-with-docker-compose` — both apps + `otel-lgtm`;
      get the Tempo trace-query assertion deterministic (fixed `traceparent`,
      `always_on` sampler, bounded poll) and `verify.sh` green locally before
      moving on. This is the LGTM-in-CI risk gate. Then draft the prose
      (`lgtm-docker-stack` conventions go IN the executor prompt).
   b. **Ch26** `examples/26-minikube` — kustomize manifests deploying the Ch25
      images; `run-minikube.sh` real local bring-up (`MINIKUBE_DRIVER=docker`,
      `lgtm-minikube-stack`); capture proof (pods Ready, live request, trace);
      confirm static `k8s-manifests` job passes; NO `verify.sh`. Then prose.
   c. **Appendix A** `examples/99-appendix-a-openshift-crc` — restricted-v2 Helm
      chart + edge-TLS Routes + S2I build config (`lgtm-crc`); static validation
      green; documented bring-up (+ real CRC best-effort); NO `verify.sh`. Then
      prose (set `appendix: true`, `appendix_label: "A"`).
   d. **Ch27** `examples/27-complete-project` — assemble the integrative both-stack
      service from existing chapter code (Ch21 base + Ch8/10/12/13/14/16
      capabilities); get the bounded `verify.sh` (full flow, REST + Kafka +
      CloudEvents + Arazzo) green locally. Then prose.
3. **D (validation):** Opus adversarial pass on all four deliverables — voice,
   technical accuracy, contract-reuse claims, that Ch27's capability claims are
   actually exercised by its `verify.sh`, that the CI footgun fix holds (no
   stray `verify.sh` in the cluster dirs), and that the appendix convention
   renders. **Fold the `lgtm-professional-voice` sweep in here so 0 ban-tier is
   reached BEFORE anything flips to `verified`** (r05 lesson: do not let
   ban-tier reach merge).
4. **E (wrap):** flip coverage rows to `draft` as prose lands; full local gate
   (`python3 -I scripts/validate.py`, `GATE=1 bash scripts/wordcount.sh`,
   `bundle exec jekyll build --trace`); re-run the voice scan (0 ban-tier);
   push; watch CI (contracts + site + examples matrix + the new `k8s-manifests`
   job); flip Ch25/Ch27 to `verified` only after their matrix jobs are green,
   and Ch26/Appendix A to `verified` per their tier (static green + captured/
   documented bring-up); open PR + merge.

## Acceptance (same bar as r01–r05)
- 2,000–2,500 words each for Ch25, Ch26, Appendix A, Ch27 (`GATE=1 bash
  scripts/wordcount.sh` green); >=1 paired SVG+`.excalidraw` per deliverable
  (figures 25, 26, appendix-a, 27 present under `assets/diagrams/`).
- Both-stack chapters (Ch25, Ch27) use `codetabs` with exactly two fenced
  blocks; `validate.py` codetabs check passes.
- 0 voice ban-tier (lgtm-professional-voice scan clean) BEFORE any `verified`
  flip.
- `python3 -I scripts/validate.py` + wordcount `GATE=1` + `bundle exec jekyll
  build --trace` all green.
- **Ch25 CI-matrix `verify.sh` green**, asserting a real exported trace via
  Tempo query (judgment call A); **Ch27 CI-matrix `verify.sh` green**,
  asserting the full end-to-end flow (judgment call C).
- **Ch26 and Appendix A are NOT in the examples matrix** (no `verify.sh` in
  either dir; validate.py guard passes); the non-matrix `k8s-manifests` job is
  green (kustomize/helm + kubeconform + dry-run). Ch26 has captured
  real-cluster proof (minikube/docker); Appendix A has static-green + a
  documented bring-up (real CRC best-effort).
- Coverage rows truthful: T1/Ch25, T2/Ch26, T3/Appendix A and Ch27 flip
  planned -> draft -> verified only as each bar is met.
- The appendix renders as "Appendix A" (not "Chapter 99") in both the part page
  and the chapter header, sorts into Part 11's part page, and reads at the end
  of the linear pager.

## Risks (each with how it's detected)
- **LGTM weight/boot flakiness in Ch25 CI** → single-container `otel-lgtm`
  (one image, already repo-standard), health-gated boot, `always_on` sampler,
  fixed `traceparent`, bounded Tempo poll. Detected by the Ch25 matrix job
  wall-clock and any trace-poll timeout.
- **Clusterless-CI matrix footgun (judgment call B)** → Ch26/AppA dirs carry NO
  `verify.sh` (runners named `run-minikube.sh`/`run-crc.sh`); a `validate.py`
  guard fails the build if a `verify.sh` ever appears there. Detected by the
  discover-examples matrix list (must stay at its current count + Ch25 + Ch27
  only) and the guard.
- **minikube/CRC local bring-up time** → Ch26 reuses Ch25 images (no rebuild),
  `MINIKUBE_DRIVER=docker`; CRC bring-up is best-effort, not a gate. Detected by
  executor bring-up logs; CI relies on static validation, so a slow cluster
  never blocks the pipeline.
- **Ch27 scope balloon** → assemble from existing chapter code; tracing and
  load ride local-only profiles, out of the CI gate; bounded consume timeout on
  the event path. Detected by the Ch27 matrix job wall-clock approaching Ch21's
  and by example dependency/build size.
- **Appendix ordering / nav** → integer `order: 99` + `appendix`/`appendix_label`
  flags + minimal layout handling; `validate.py` requires the four front-matter
  keys. Detected by the jekyll build, the part-page/pager render, and
  `validate.py`.
- **Over-softening in the voice sweep** → sweep prose only; leave code,
  commands, identifiers and recorded output untouched. Detected by the Opus
  validation pass and a grep diff review.
- **Push branch with `-u`** (branch already pushed); keep CI green on every
  push.
