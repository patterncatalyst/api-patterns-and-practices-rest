# Ch21 — Multi-protocol contracts: REST + events, one schema

Most services don't pick one protocol for life. A booking service answers
synchronous REST calls (`POST /bookings`, `GET /bookings/{id}`) AND tells the
rest of the system what happened, asynchronously, over a broker. This
chapter builds that as ONE service, on both stacks: a synchronous REST path
backed by `contracts/openapi/shipping-api.yaml`, paired with a background
event-streaming path backed by `contracts/asyncapi/shipping-events.yaml` and
`contracts/cloudevents/*` — and both paths are generated from the **same**
shared schema, `contracts/schemas/shipping.schema.json`. One `Booking`
type, one `BookingEvent` type, two protocol contracts, zero drift.

It also shows — real, runnable, but deliberately **not** in CI — the
governance tier that keeps multi-protocol contracts honest at scale: a
schema/artifact **registry** (Apicurio) and a **data catalog** (OpenMetadata).
They answer different questions and are not interchangeable; see
"Governance tier" below.

## What happens on `POST /bookings`

1. The request is validated and a `Booking` (`#/$defs/Booking`) is created
   in status `PENDING` — same shape/quote formula as
   `examples/04-contract-first`.
2. The synchronous REST response returns immediately: `201 Created`,
   `Location: /bookings/{id}`, body = the `PENDING` booking.
3. **In the background** (off the request thread — `CompletableFuture.runAsync`
   on Quarkus, FastAPI's `BackgroundTasks` on Python) the service flips the
   booking to `CONFIRMED` and publishes a **CloudEvents-enveloped
   `BookingEvent`** to the Kafka topic `shipping.bookings.lifecycle`:

   ```json
   {
     "specversion": "1.0",
     "id": "evt_...",
     "source": "/shipping/bookings",
     "type": "dev.patterncatalyst.shipping.booking.confirmed",
     "subject": "bkg_...",
     "time": "2026-...",
     "datacontenttype": "application/json",
     "data": { "bookingId": "bkg_...", "status": "CONFIRMED", "previousStatus": "PENDING", "origin": {...}, "destination": {...}, "occurredAt": "2026-..." }
   }
   ```

   This is the exact envelope shape committed at
   `contracts/cloudevents/booking-confirmed.example.json`, and `data`
   conforms to `#/$defs/BookingEvent` — the same `$defs` the REST side's
   `Booking.origin`/`Booking.destination` already use.

The caller of `POST /bookings` never waits on Kafka; a failed publish is
logged, not surfaced as a 5xx on the already-returned response — the two
paths are coupled by shared data, not by a shared failure domain.

## Run it

```bash
cd examples/21-multi-protocol-contracts
./verify.sh
```

This brings up **kafka + quarkus + python only** (the governance profiles are
never started by a plain `compose up` or by `verify.sh`) and, for each stack:

1. runs `validate_response.py --selftest` (the schema-validation gate has
   teeth before anything else is trusted);
2. statically confirms `contracts/schemas/shipping.schema.json` is `$ref`'d
   by BOTH `contracts/openapi/shipping-api.yaml` and
   `contracts/asyncapi/shipping-events.yaml` — "one schema, two protocol
   contracts" isn't just a claim in this README, it's grepped;
3. structurally validates `contracts/arazzo/booking-workflow.yaml` (the
   `arazzo`/`workflows` keys and a `bookAndConfirm` workflow with `steps`) —
   see `check_arazzo.py`;
4. `POST`s a booking → `201` + `Location`, body vs `#/$defs/Booking`; `GET`s
   the `Location` → `200`, body vs `#/$defs/Booking`;
5. consumes the booking's `BookingEvent` from `shipping.bookings.lifecycle`
   with a **bounded** (20s) `kafka-console-consumer.sh --from-beginning
   --max-messages N --timeout-ms 20000` run inside the broker container, and
   validates the CloudEvents envelope attributes (`specversion`, `id`,
   `source`, `type`) plus the `data` payload against `#/$defs/BookingEvent`.

A missing event fails fast (bounded timeout), not by hanging the gate.

To poke at it by hand:

```bash
docker compose up --build

curl -isS -X POST -H 'Content-Type: application/json' \
  -d '{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}]}' \
  http://localhost:8101/bookings   # Quarkus
# ... or http://localhost:8021/bookings for FastAPI

# Watch the event land:
docker compose exec kafka /opt/kafka/bin/kafka-console-consumer.sh \
  --bootstrap-server localhost:9092 --topic shipping.bookings.lifecycle \
  --from-beginning --max-messages 1 --timeout-ms 20000

docker compose down -v
```

Ports are **unique** across the repo's examples: Quarkus `8101`, FastAPI
`8021`, Kafka's external listener `19092`, Apicurio `8104` (registry
profile), OpenMetadata `8585` (catalog profile).

## The broker

A single-node **Kafka in KRaft mode** (`apache/kafka:3.9.1`, no ZooKeeper) —
the exact broker `contracts/asyncapi/shipping-events.yaml` already names
(`servers.kafka`, `protocol: kafka`, "Local Kafka (KRaft)"). Two listeners:
`PLAINTEXT` (advertised as `kafka:9092`, used by the compose-network apps)
and `EXTERNAL` (advertised as `localhost:19092`, published `19092->9094`,
for host tooling). The healthcheck runs
`kafka-topics.sh --bootstrap-server localhost:9092 --list` so the broker is
only reported healthy once it actually accepts client connections — both
app containers wait on that before starting, so there's no Kafka-not-ready
race at app boot.

## Endpoints

| Method | Path | Behavior |
|---|---|---|
| POST | `/bookings` | Create a `Booking`; `201` + `Location` + `#/$defs/Booking` body (status `PENDING`); triggers the background confirm-and-publish. |
| GET | `/bookings/{id}` | `200` + `#/$defs/Booking`, or `404` + `#/$defs/Problem`. |
| GET | `/health` (Python) / `/q/health` (Quarkus) | Liveness, used by `docker compose` healthchecks. |

## Governance tier (local-only, OUT of CI)

CI proves the live REST + Kafka + CloudEvents path only — that's the
integrative core this chapter teaches. The governance tier is real and
runnable, but kept behind opt-in compose profiles, exactly like HTTP/3 in
Ch19: shown, reproducible, never load-bearing for the gate.

```bash
docker compose -p ch21-contracts config --profiles
# catalog
# registry
```

### Apicurio Registry — the schema/artifact registry (xRegistry touchpoint)

```bash
docker compose --profile registry up -d apicurio-registry
```

Apicurio Registry ships its own embedded H2 storage, so no extra datastore
is needed — it answers health checks within ~15s. Publish the three
artifacts this chapter's contracts are made of, into a `shipping` group,
and resolve one back:

```bash
BASE=http://localhost:8104/apis/registry/v3

curl -s -X POST "$BASE/groups" -H 'Content-Type: application/json' \
  -d '{"groupId":"shipping"}'

# Shared schema
curl -s -X POST "$BASE/groups/shipping/artifacts" -H 'Content-Type: application/json' -d '{
  "artifactId": "shipping-schema", "artifactType": "JSON",
  "firstVersion": { "content": {
    "content": "'"$(python3 -c "import json;print(json.dumps(open('../../contracts/schemas/shipping.schema.json').read())[1:-1])")"'",
    "contentType": "application/json" } }
}'

# OpenAPI + AsyncAPI contracts (artifactType OPENAPI / ASYNCAPI)
# — same POST shape, contentType application/yaml, pointed at
#   contracts/openapi/shipping-api.yaml and contracts/asyncapi/shipping-events.yaml.

# Resolve the shared schema back out:
curl -s "$BASE/groups/shipping/artifacts/shipping-schema/versions/1/content" | jq '.["$defs"] | keys'
```

**Verified in this environment:** all three artifacts (`shipping-schema`,
`shipping-openapi`, `shipping-asyncapi`) published successfully (`200`),
`GET /groups/shipping/artifacts` lists all three, and resolving
`shipping-schema` back returned all 17 `$defs` intact. Apicurio's
`/apis/registry/v3/system/info` reports `"Apicurio Registry (In Memory)"` —
this is the xRegistry-model touchpoint: artifacts, groups, versions, content
resolution by coordinate, all the things a schema/API **registry** does.

### OpenMetadata — a data catalog (NOT an xRegistry implementation)

**This distinction matters:** Apicurio Registry answers "what are my
artifacts and how do I resolve one by coordinate, right now?" OpenMetadata
answers a different question: "what changed, when, and what's the blast
radius?" — it's a **data catalog**: it ingests metadata about datasets,
services, and (via its API-service entities) APIs, then tracks **version
history and lineage** across changes. A registry alone doesn't tell you
"this table/schema used to look like X and now looks like Y, as of this
timestamp, with this diff." That's the governance story a catalog adds.

```bash
docker compose --profile catalog up -d om-mysql om-elasticsearch
# wait for both healthy, then:
docker compose --profile catalog up -d om-migrate   # one-shot DB migration
# wait for it to exit 0, then:
docker compose --profile catalog up -d om-server
# wait ~60-90s for http://localhost:8585 to answer
```

**Verified in this environment** — a full local bring-up, not just a compose
file:

- `om-mysql` and `om-elasticsearch` reported `healthy` within ~45s.
- `om-migrate` ran OpenMetadata's real schema migration chain
  (1.9.x → 2.0.5) against the fresh database and exited `0`.
- `om-server` became healthy (`wget --spider http://localhost:8586/healthcheck`
  → `200`) and served its UI (`http://localhost:8585/` → `200`) and API
  (`/api/v1/system/version` → `{"version":"2.0.5",...}`).
- Logged in via `POST /api/v1/users/login` with the default admin
  credentials, then over the REST API (no ingestion pipeline needed for
  this minimal walkthrough) created a `DatabaseService` → `Database` →
  `DatabaseSchema` → `Table` named `bookings`, with columns mirroring
  `#/$defs/Booking` (`id`, `status`, `origin_un_locode`,
  `destination_un_locode`, `quote_amount`, `created_at`). The table came
  back at **version `0.1`**.
- Simulated a schema evolution — the same kind of change a real connector
  run would detect — by `PATCH`ing the table to add a `requested_pickup`
  column (mirroring `Booking.requestedPickup`). The response came back at
  **version `0.2`**, with:

  ```json
  "changeDescription": {
    "fieldsAdded": [{ "name": "columns", "newValue": "[{\"name\":\"requested_pickup\", ...}]" }],
    "previousVersion": 0.1
  }
  ```

- `GET /api/v1/tables/{id}/versions` returned BOTH `0.1` and `0.2`, the
  latter carrying the exact diff above — this is the "tracks schema changes
  over time" story made concrete: a version timeline with a structured
  change description, not just "current state."

**Not run in this environment:** the `om-ingestion` service (Airflow-based
connector runtime). Its image (`docker.getcollate.io/openmetadata/ingestion:2.0.5`)
was confirmed to pull cleanly, and the compose service definition mirrors
OpenMetadata's own vetted quickstart compose, but a live connector-driven
ingestion run (pointing a real Database/API connector at this chapter's
contracts and watching a DAG execute) was not exercised — the REST-driven
walkthrough above already demonstrates the version-tracking/lineage claim
without needing Airflow up. A reader extending this chapter's walkthrough
with a real connector run should bring up `om-ingestion` too
(`docker compose --profile catalog up -d om-ingestion`) and follow
OpenMetadata's connector docs to register a pipeline against the
`shipping-contracts` service created above.

Default admin login for a fresh `catalog` profile instance:
`admin@open-metadata.org` / `admin`.

Tear down the catalog profile same as any other: `docker compose --profile
catalog down -v --remove-orphans` (removes the `om-db-data`/`om-es-data`
volumes too — this is a throwaway local demo, not a persisted catalog).

## The drift probe

Corrupt the CloudEvents `data` payload so it no longer conforms to
`#/$defs/BookingEvent` — for example, in `quarkus/.../BookingEventPublisher.java`,
change:

```java
data.put("status", confirmed.status().name());
```

to:

```java
data.put("status", "TELEPORTING");
```

Re-run `./verify.sh`. REST still passes (nothing about `POST /bookings`
changed), but the event-path assertion fails loudly:

```
lib.sh: ok — quarkus CloudEvents envelope has specversion/id/source/type
INVALID: body does not conform to #/$defs/BookingEvent
  - status: 'TELEPORTING' is not one of ['PENDING', 'CONFIRMED', 'IN_TRANSIT', 'DELIVERED', 'CANCELLED']
lib.sh: FAIL — body does not conform to #/$defs/BookingEvent
```

That's the point: the envelope attributes (`specversion`/`id`/`source`/`type`)
can be perfectly well-formed CloudEvents while the `data` payload inside
drifts from the schema — only validating `data` against `#/$defs/BookingEvent`
catches it. Revert the change and `./verify.sh` goes back to `PASS`.

## Repeatability

`verify.sh` is safe to run back-to-back: `compose_down -v --remove-orphans`
tears down the broker, both app containers, and the compose network every
time (via `lib.sh`'s `EXIT` trap plus an explicit call at the end), so a
second run starts from an empty topic and a fresh KRaft cluster — no leaked
offsets, no stale consumer groups, no port conflicts.
