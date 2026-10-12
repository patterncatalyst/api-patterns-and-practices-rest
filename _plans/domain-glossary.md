---
title: "Domain Glossary — Shipping & Cargo"
layout: plan
render_with_liquid: false
---

# Domain Glossary — Shipping & Cargo

One canonical domain for the whole site. Every chapter, example, contract and
diagram uses these nouns. The source decks teach REST with a **coffee-shop**
domain; this site re-casts the same lessons in a **shipping/cargo booking**
domain so the examples carry a single consistent story end to end. The
coffee-shop → cargo column below is the translation key: when a deck concept is
ported, its coffee-shop noun maps to the cargo noun on the same row, and the
`lgtm-professional-voice` sweep greps for residual coffee-shop terms.

## Canonical nouns

| Term | Meaning | Resource / type |
|---|---|---|
| **Booking** | A customer's request to ship cargo from an origin to a destination. The aggregate root. | `Booking` · `/bookings` |
| **Cargo** | The goods carried under a booking: description, type, weight, volume, hazardous flag. A booking has one or more cargo items. | `Cargo` · `/bookings/{id}/cargo` |
| **Location** | A port or terminal, identified by UN/LOCODE. Origin and destination of a booking. | `Location` |
| **Route** | The planned sequence of legs that moves a booking's cargo from origin to destination. | `Route` (introduced with HATEOAS, Ch12) |
| **Leg** | One hop of a route (one carrier, one departure → arrival). | `Leg` |
| **Manifest** | The consolidated document/listing of all cargo on a voyage; the large binary / streamed resource. | `Manifest` (Ch15/16) |
| **Price / Quote** | The money amount to carry a booking's cargo. | `Money` |
| **Operation** | A server-owned record of long-running work (confirmation, reconcile). Returned by `202 Accepted`, polled for status. | `Operation` (Ch10) |
| **Reconcile job** | A rerunnable, server-scheduled job that re-checks manifests against bookings. | `Job` (Ch11) |

## Booking lifecycle (the finite-state machine behind HATEOAS)

```
PENDING ──confirm──▶ CONFIRMED ──load──▶ IN_TRANSIT ──deliver──▶ DELIVERED
   │                     │
   └──────cancel─────────┴──────────────▶ CANCELLED
```

The available state transitions are what HATEOAS links expose (Ch12): a
`PENDING` booking offers `confirm` and `cancel`; a `DELIVERED` booking offers
neither. The same FSM drives the async confirmation flow (Ch10: `202` →
poll `Operation` → `303` to the confirmed booking) and the event stream
(booking state changes emit CloudEvents, Ch21).

## Coffee-shop → cargo translation key

| Coffee-shop (deck source) | Shipping/cargo (this site) | Notes |
|---|---|---|
| Order | Booking | The aggregate root; the thing created, confirmed, cancelled. |
| Order item / coffee / product | Cargo item | The line items within the root. |
| Menu / product catalog | Locations / routes catalog | Reference data a booking draws from. |
| Kitchen / barista | Terminal / carrier | Where the work physically happens. |
| "Your order is being prepared" | Booking `IN_TRANSIT` | The in-progress state. |
| "Order ready / delivered" | Booking `DELIVERED` | Terminal success state. |
| Order cancelled | Booking `CANCELLED` | Terminal failure state. |
| Receipt / price | Quote / `Money` | The money amount. |
| Kitchen ticket queue | Manifest | The consolidated listing. |

## Identifiers & formats

- **Booking id** — opaque string, `bkg_` prefix (e.g. `bkg_01H...`), ULID-shaped.
- **Cargo id** — `crg_` prefix.
- **Operation id** — `op_` prefix.
- **Location** — UN/LOCODE (e.g. `USNYC`, `NLRTM`, `SGSIN`).
- **Money** — `{ "currency": "USD", "amount": "1250.00" }`; amount is a decimal **string** to avoid float drift.
- **Timestamps** — RFC 3339 / ISO 8601 UTC (`2026-10-11T14:30:00Z`).
- **Weight** — kilograms (`kg`); **Volume** — cubic metres (`m3`).

## Contract vocabulary

These names are fixed across `contracts/schemas/shipping.schema.json` (shared
JSON Schema components), `contracts/openapi/` (sync request/response),
`contracts/asyncapi/` (event channels), `contracts/cloudevents/` (event
envelope) and `contracts/arazzo/` (workflow). A type is defined **once** in the
shared schema and referenced everywhere else — see `contracts/README.md`.
