# Contracts — the single source of truth

Every payload type in the shipping/cargo domain is defined **once** and reused
across four contract languages. CI (`.github/workflows/contracts.yml`) lints and
validates all of them, and fails the build on drift. These files are excluded
from the Jekyll site (`_config.yml` → `exclude: contracts/`).

```
contracts/
├── schemas/
│   └── shipping.schema.json      # JSON Schema 2020-12 — ALL payload types ($defs)
├── openapi/
│   ├── shipping-api.yaml         # OpenAPI 3.1 — the current contract (v2), sync request/response
│   └── shipping-api-v1.yaml      # frozen v1 shape, for the versioning chapter (Ch14)
├── asyncapi/
│   └── shipping-events.yaml      # AsyncAPI 3.0 — booking lifecycle event channels
├── cloudevents/
│   └── booking-confirmed.example.json   # CloudEvents 1.0 envelope; data = BookingEvent
└── arazzo/
    └── booking-workflow.yaml     # Arazzo 1.0.1 — book → confirm → poll → track sequence
```

## The reuse rule (acceptance criterion #11)

- `schemas/shipping.schema.json` holds `Booking`, `Cargo`, `Money`, `Location`,
  `BookingEvent`, `Problem`, … under `$defs`.
- `openapi/shipping-api.yaml` references them via
  `$ref: '../schemas/shipping.schema.json#/$defs/Booking'`.
- `asyncapi/shipping-events.yaml` references the **same** `$defs/BookingEvent`.
- The CloudEvents `data` and the Arazzo inputs reference the same components.

No payload type is ever defined twice. Change it in the schema and every
contract — and both stacks generated from them — moves together.

## Which contract when? (the recurring Decision box)

| Need | Contract |
|---|---|
| Synchronous request/response | **OpenAPI 3.1** |
| Background / event channels | **AsyncAPI 3** |
| The event envelope + metadata | **CloudEvents** |
| A multi-step sequence across calls | **Arazzo** |

## Validating locally

```bash
# Lint + validate everything (what CI runs)
npx @stoplight/spectral-cli lint contracts/openapi/*.yaml contracts/asyncapi/*.yaml
npx @redocly/cli lint contracts/openapi/shipping-api.yaml
npx @asyncapi/cli validate contracts/asyncapi/shipping-events.yaml
python3 -I - <<'PY'
import json, jsonschema  # data payloads validate against the shared schema
PY
```

Artifacts are published to **Apicurio Registry** (the xRegistry touchpoint, Ch21)
when the registry service from the stack is running.
