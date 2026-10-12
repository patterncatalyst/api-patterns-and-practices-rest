# Diagrams

Each diagram is a paired `name.svg` (committed, embedded via the `excalidraw.html`
include) + `name.excalidraw` (editable source). Generate both with
`scripts/generate_diagram.py` (see `references/diagram-engine.md`). Catalogue them
here as you add them:

| Diagram | Chapter | What it shows |
|---|---|---|
| `00-lab-topology` | Ch0 — Prerequisites & the lab | Quarkus and FastAPI services both implementing one OpenAPI 3.1 contract and reading/writing one Postgres instance; CI schema-validates live responses; LGTM observability shown as an optional, dashed lane. |
| `01-rest-constraints` | Ch1 — APIs & patterns | RPC/verb-oriented vs Web API/resource-oriented contrasted, then the five REST constraints (client–server, stateless, cacheable, uniform interface, layered system), with uniform interface emphasized in amber as the one most APIs violate. |
| `02-decision-framework` | Ch2 — The API decision framework | The six decision axes (interaction shape, payload size, latency/real-time need, cacheability, client diversity, evolution needs) feeding a central "pick the pattern, style & transport" node. Reused as the Decision box in later chapters. |
| `03-resource-model` | Ch3 — Designing around resources | The Booking→Cargo aggregate, and how it's exposed as a collection (`/bookings`), an item (`/bookings/{id}`) and a sub-resource (`/bookings/{id}/cargo`); notes that resources are nouns and must not mirror DB tables. |
| `04-contract-first-flow` | Ch4 — Contract-first with OpenAPI 3.1 | One contract scaffolds both stacks; CI schema-validates live responses; the flow branches to a passing merge or a drift-detected build failure. |
| `05-idempotency-matrix` | Ch5 — HTTP methods & idempotency | A method × {safe, idempotent} grid for GET/HEAD/PUT/DELETE/POST/PATCH, each row placed against a concrete booking operation (e.g. `PUT /bookings/{id}` idempotent, `POST /bookings` not idempotent). |
