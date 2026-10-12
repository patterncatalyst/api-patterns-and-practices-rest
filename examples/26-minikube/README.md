# Ch26 — minikube deployment tier

Deploys the SAME two booking services as
[`examples/25-local-with-docker-compose`](../25-local-with-docker-compose)
(identical `quarkus/` and `python/` sources and Containerfiles — no third
copy of the app) onto a local Kubernetes cluster, to make concrete what
changes between "containers on one host" and "a Kubernetes deployment
tier": networking, health checking, config/secrets injection, and scaling.

This directory is a **cluster-tier example** (it needs a real, running
minikube cluster) and deliberately carries **no `verify.sh`** —
`scripts/validate.py`'s `cluster-dir-no-verify` check enforces that, so the
clusterless CI examples matrix never tries to auto-discover and run one
here. The only CI coverage for this directory is a static one: the
`k8s-manifests` job in `.github/workflows/contracts.yml` runs

```
kubectl kustomize examples/26-minikube/k8s | kubeconform -strict
```

Bringing the cluster up for real is a local, by-hand step: `run-minikube.sh`.

## Compose → Kubernetes mapping

| Compose concept (Ch25) | Kubernetes equivalent (Ch26) | What changes |
|---|---|---|
| Published host port per service (`8105:8080`, `8024:8000`) | `Service` (ClusterIP) + one `Ingress` | Nothing is reachable from outside the cluster except through the Ingress; it **routes by host + path**, not by picking a different port per service. Both apps sit behind one host (`booking.ch26.local`), told apart by path prefix (`/quarkus`, `/python`) via `nginx.ingress.kubernetes.io/rewrite-target`. |
| `depends_on` + Docker Compose's embedded DNS (plain service name, e.g. `lgtm`) | Kubernetes Service DNS (`<svc>.<ns>.svc.cluster.local`) | Same idea (name-based discovery), different resolver and a real object (`Service`) in front of it instead of an implicit network alias. |
| `healthcheck:` (one `CMD curl` entry per container, polled by the Docker engine) | `startupProbe` / `readinessProbe` / `livenessProbe` (three distinct lifecycle gates) | Quarkus has three real, distinct endpoints — `/q/health/started`, `/q/health/ready`, `/q/health/live` (quarkus-smallrye-health is on the classpath) — so each probe targets a different check. Python's FastAPI app has only one `/health` endpoint, so all three probes hit the same path — a visible, concrete contrast in what "probing" buys you per app, not just a copy-pasted block. |
| `environment:` (plaintext key/value pairs, visible in `docker inspect`, committed in `compose.yaml`) | `ConfigMap` (`booking-config`) + `Secret` (`booking-secret`), both via `envFrom` | Same env-var injection mechanism the app code already expects — Quarkus's `QUARKUS_OTEL_EXPORTER_OTLP_ENDPOINT` env-var mapping overrides the hardcoded `quarkus.otel.exporter.otlp.endpoint` property (ordinal-override trick, zero code change), and the Python side already reads `OTEL_EXPORTER_OTLP_ENDPOINT`/`OTEL_SERVICE_NAME` natively — but the *Secret* object is a distinct Kubernetes kind from a ConfigMap (base64-at-rest, RBAC-able separately), not just another key in the same bag the way compose's flat `environment:` list is. |
| No scaling primitive at all (`docker compose up --scale` is a manual, one-shot command) | `HorizontalPodAutoscaler` (CPU-based, on `quarkus-booking`) | The cluster watches CPU utilization (via the `metrics-server` addon) and adjusts replica count on its own — compose has nothing resembling this. Scoped to one app deliberately (the acceptance bar is "at least one", and Quarkus's JVM warm-up cost is the more illustrative CPU-bound case); `python-booking` is left unscaled on purpose, to keep the "not every Deployment needs this" contrast visible. |

## Layout

```
examples/26-minikube/
├── k8s/
│   ├── kustomization.yaml        # CI entrypoint: `kubectl kustomize examples/26-minikube/k8s`
│   ├── base/                     # Deployments, Services, ConfigMap, Secret, Ingress, HPA
│   │   ├── kustomization.yaml
│   │   ├── namespace.yaml        # ch26-booking
│   │   ├── configmap.yaml        # booking-config
│   │   ├── secret.yaml           # booking-secret (dev-only, plaintext-in-git demo value)
│   │   ├── quarkus-deployment.yaml
│   │   ├── python-deployment.yaml
│   │   ├── ingress.yaml          # booking-ingress — host+path routing
│   │   └── hpa.yaml              # quarkus-booking-hpa — CPU-based
│   └── overlays/
│       └── minikube/
│           └── kustomization.yaml   # pins the real image tags (booking/{quarkus,python}:1.0)
├── run-minikube.sh                # the local runner (NOT verify.sh)
└── README.md
```

`k8s/base` uses generic placeholder image names (`booking/quarkus:latest`,
`booking/python:latest`); `k8s/overlays/minikube` is the one place the real,
pinned tag (`1.0`, built by `run-minikube.sh`) is named — the same
base/overlay split as
`~/Dev/modernizing-enterprise-applications/deploy/k8s/overlays/minikube`'s
own `images:` transformer, which this build was modeled on.

## Running it

```
bash run-minikube.sh                       # driver=docker (default)
MINIKUBE_DRIVER=podman bash run-minikube.sh
MINIKUBE_PROFILE=my-profile bash run-minikube.sh
```

It will: start minikube (`--driver=docker` by default), enable the
`ingress` and `metrics-server` addons, build both Ch25 app images straight
into the cluster's image store with `minikube image build` (no registry,
no separate `image load` step), `kubectl apply -k` the manifests, wait for
both Deployments to roll out, and print the Ingress host/IP plus sample
`curl` commands for both backends.

**Teardown** (not automatic — the script leaves the cluster up to poke at):

```
minikube delete -p ch26-booking
```

### A note on this machine's `--rootless` default

This host's `~/.minikube/config/config.json` pins `rootless: true` (set for
a separate podman-driver profile) — the `docker` driver needs a rootless
Docker *context* to honor that, which this host's Docker Engine isn't
running under, and `minikube start` fails fast with `MK_USAGE` if you don't
override it. `run-minikube.sh` passes `--rootless=${MINIKUBE_ROOTLESS:-false}`
for that reason; override with `MINIKUBE_ROOTLESS=true` if your Docker
context actually is rootless.

## Captured proof (real cluster, driver=docker)

Brought up for real on 2026-10-12 with `minikube v1.38.1`, Kubernetes
v1.35.1, profile `ch26-booking`, driver `docker --rootless=false`.

**1. Static validation — `kubectl kustomize | kubeconform -strict -summary`:**

```
$ kubectl kustomize examples/26-minikube/k8s | kubeconform -strict -summary
Summary: 9 resources found parsing stdin - Valid: 9, Invalid: 0, Errors: 0, Skipped: 0
```

**2. `minikube image build` — both Ch25 images, no registry:**

```
$ minikube image build -p ch26-booking -t booking/quarkus:1.0 -f Containerfile examples/25-local-with-docker-compose/quarkus
...
[INFO] BUILD SUCCESS
...
#16 naming to docker.io/booking/quarkus:1.0 done

$ minikube image build -p ch26-booking -t booking/python:1.0 -f Containerfile examples/25-local-with-docker-compose/python
...
 + shipping-python-ch25==1.0.0 (from file:///app)
...
#14 naming to docker.io/booking/python:1.0 done
```

**3. Rollout — both Deployments Ready:**

```
$ kubectl apply -k examples/26-minikube/k8s
namespace/ch26-booking created
configmap/booking-config created
secret/booking-secret created
service/python-service created
service/quarkus-service created
deployment.apps/python-booking created
deployment.apps/quarkus-booking created
horizontalpodautoscaler.autoscaling/quarkus-booking-hpa created
ingress.networking.k8s.io/booking-ingress created

$ kubectl rollout status deployment/quarkus-booking --timeout=240s
deployment "quarkus-booking" successfully rolled out
$ kubectl rollout status deployment/python-booking --timeout=180s
deployment "python-booking" successfully rolled out

$ kubectl -n ch26-booking get pods
NAME                               READY   STATUS    RESTARTS   AGE
python-booking-8d9d4b655-msrg5     1/1     Running   0          2m11s
quarkus-booking-5c64fbf797-7w7cv   1/1     Running   0          2m11s
```

**4. A live booking through the Ingress — both backends, path-routed off
one host:**

```
$ curl -sS -D - -X POST "http://192.168.49.2/quarkus/bookings" \
    -H "Host: booking.ch26.local" -H 'Content-Type: application/json' \
    -d '{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'

HTTP/1.1 201 Created
Content-Type: application/json;charset=UTF-8
Location: /bookings/bkg_01M4RMD792K0ZB4WT6JZEW3T2A

{"id":"bkg_01M4RMD792K0ZB4WT6JZEW3T2A","status":"PENDING","origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"id":"crg_01M4RMD791J3GXX7M2H3000KHS","description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"quote":{"currency":"USD","amount":"3001.25"},"requestedPickup":"2026-02-01","createdAt":"2026-10-12T18:01:13Z"}
```

```
$ curl -sS -D - -X POST "http://192.168.49.2/python/bookings" \
    -H "Host: booking.ch26.local" -H 'Content-Type: application/json' \
    -d '{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'

HTTP/1.1 201 Created
Content-Type: application/json
location: /bookings/bkg_01M4RMDBHERAPV7B8KKH6CSKWH

{"id":"bkg_01M4RMDBHERAPV7B8KKH6CSKWH","status":"PENDING","origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false,"id":"crg_01M4RMDBHE91BWCGTPNMWTAPYN"}],"quote":{"currency":"USD","amount":"3001.25"},"requestedPickup":"2026-02-01","createdAt":"2026-10-12T18:01:18Z"}
```

**5. ConfigMap + Secret actually reached both containers** (`envFrom`,
verified with `kubectl exec ... env`):

```
$ kubectl -n ch26-booking exec deploy/quarkus-booking -- env | grep -E "PRICING_PROVIDER_API_KEY|QUARKUS_OTEL_EXPORTER_OTLP_ENDPOINT|QUARKUS_LOG_LEVEL"
QUARKUS_LOG_LEVEL=INFO
QUARKUS_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.ch26-booking.svc.cluster.local:4317
PRICING_PROVIDER_API_KEY=demo-pricing-key-ch26-dev-only
```

**6. HPA — CPU-based, backed by a real `metrics-server` reading:**

```
$ kubectl -n ch26-booking get hpa
NAME                  REFERENCE                    TARGETS       MINPODS   MAXPODS   REPLICAS   AGE
quarkus-booking-hpa   Deployment/quarkus-booking   cpu: 2%/70%   1         3         1          2m11s
```

(`cpu: <unknown>/70%` for the first ~60-90s after rollout while
`metrics-server` collects its first sample is expected and resolved on its
own — the `describe hpa` events show `FailedGetResourceMetric` during that
window, then `ValidMetricFound` once a reading lands.)

**Teardown:** `minikube delete -p ch26-booking` (run after capturing the
above; not left running).
