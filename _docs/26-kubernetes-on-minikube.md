---
title: "Kubernetes on minikube"
order: 26
part: "Running it: Docker → minikube → CRC"
description: "The same two booking images moved from Compose onto a cluster: Service and Ingress routing, three-tier health probes, ConfigMap and Secret injection, and a CPU-based HPA, assembled with kustomize."
duration: "25 min"
---

## Learning objectives

By the end of this chapter you can:

- Translate Compose primitives (published ports, a single healthcheck, a plaintext environment block, manual `--scale`) onto Kubernetes equivalents (`Service` and `Ingress`, three-tier probes, `ConfigMap` and `Secret`, an `HPA`).
- Distinguish `startupProbe`, `readinessProbe` and `livenessProbe`, and say which lifecycle decision each gates.
- Inject configuration through `ConfigMap`, `Secret` and `envFrom` without changing application code, by an ordinal override and by a native placeholder.
- Configure a CPU-based `HorizontalPodAutoscaler` against the `metrics-server` addon.
- Structure manifests as a kustomize base plus a minikube overlay so a second target can reuse the base.

## Why this matters

The booking logic doesn't change when it moves to a cluster. What changes is everything between a client and that logic: how a request finds a pod, how the cluster decides a pod may receive traffic, how configuration reaches a container without living in the image, and what happens when one replica isn't enough.

Both Deployments run the two images built for the Compose tier, from the same `quarkus/` and `python/` sources and Containerfiles, with no third copy of the application, applied with `kubectl apply -k`. The manifests were captured against minikube v1.38.1, Kubernetes v1.35.1, profile `ch26-booking`. The directory has no `verify.sh`, and `scripts/validate.py` enforces that, because a clusterless CI matrix has no cluster to run it against. CI coverage is static: `kubectl kustomize examples/26-minikube/k8s | kubeconform -strict` checks every manifest against the Kubernetes API schema. Bringing the cluster up is a local step, and `run-minikube.sh` does it.

## Compose to Kubernetes

| Concern | Compose | Kubernetes |
|---|---|---|
| Addressing | A published host port per service | `ClusterIP` `Service` plus one `Ingress` routing by host and path |
| Replacement | A restart policy | `Deployment` with rolling updates |
| Health | One `healthcheck:` verdict | `startupProbe`, `readinessProbe`, `livenessProbe` |
| Configuration | A plaintext `environment:` block | `ConfigMap` and `Secret` through `envFrom` |
| Scaling | A manual `--scale` | `HorizontalPodAutoscaler` |

### Networking: Service and Ingress

Compose publishes `8105:8080` for Quarkus and `8024:8000` for Python, so the port is the address. Kubernetes drops that model. Each Deployment is paired with a `ClusterIP` `Service` (`quarkus-service` on 8080, `python-service` on 8000), reachable only inside the cluster. A single `Ingress`, `booking-ingress`, puts both apps behind the host `booking.ch26.local` and routes by URL prefix: `/quarkus(/|$)(.*)` to `quarkus-service:8080` and `/python(/|$)(.*)` to `python-service:8000`.

Neither application mounts its routes under those prefixes; both still answer at `/bookings`. The annotation `nginx.ingress.kubernetes.io/rewrite-target: /$2` strips the prefix, so `/quarkus/bookings` reaches the pod as `/bookings`.

In-cluster, the same idea as Compose's embedded DNS holds, with a real object in front. Compose resolves a bare service name such as `lgtm` straight to a container; Kubernetes resolves `quarkus-service.ch26-booking.svc.cluster.local` to a `Service` that load-balances across pods.

### Deployments and rollouts

Both Deployments use `strategy: RollingUpdate` with `maxUnavailable: 0, maxSurge: 1`. A new pod passes its readiness gate before the old one is removed, so a rollout never drops available replicas, even at `replicas: 1`. `run-minikube.sh` waits on that with `kubectl rollout status deployment/quarkus-booking --timeout=240s`.

Compose replaces a crashed container only through its restart policy and never swaps containers out from under a running stack. Pods are disposable: a crash, an eviction or a rolling update replaces one, and each replacement changes the pod IP. The `Service` selector (`app.kubernetes.io/name: quarkus-booking`) keeps the ClusterIP and DNS name fixed while pods come and go.

### Probes: three gates, not one

Compose polls one `CMD curl` and gets healthy or not. Kubernetes asks three questions:

| Probe | Failing means | Why it's separate |
|---|---|---|
| `startupProbe` | Not started yet; restart after the threshold | A JVM cold start is slow, and this allowance stays out of the tighter windows below |
| `readinessProbe` | Remove the pod from the Service; keep the process | The cause may be transient: a warming dependency, an exhausted pool |
| `livenessProbe` | Restart the container | The process is wedged and waiting won't fix it |

Readiness gates traffic and liveness gates the process's existence.

Quarkus has `quarkus-smallrye-health` on its classpath, which exposes `/q/health/started`, `/q/health/ready` and `/q/health/live`, and each probe targets its own endpoint. `failureThreshold: 30` at a 5-second period gives startup 150 seconds before the kubelet restarts the container, without that allowance leaking into the readiness and liveness windows that govern the running pod.

```yaml
startupProbe:
  httpGet:
    path: /q/health/started
    port: http
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 30
readinessProbe:
  httpGet:
    path: /q/health/ready
    port: http
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3
livenessProbe:
  httpGet:
    path: /q/health/live
    port: http
  initialDelaySeconds: 10
  periodSeconds: 10
  failureThreshold: 3
```

The FastAPI app has one health route, `/health`, with no started, ready or live split, so all three probes target it:

```yaml
startupProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 3
  periodSeconds: 5
  failureThreshold: 20
readinessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 3
  periodSeconds: 10
  failureThreshold: 3
livenessProbe:
  httpGet:
    path: /health
    port: http
  initialDelaySeconds: 5
  periodSeconds: 10
  failureThreshold: 3
```

The probe kinds still differ to the kubelet: a liveness failure restarts the pod and a readiness failure pulls it from the Service. But one check can't tell "started but not ready" from "ready but no longer live"; it expresses only "the process answers HTTP". A framework that ships dedicated health endpoints buys a deployment finer control.

### Config and secrets

Compose's `environment:` is one flat, plaintext bag, visible to `docker inspect`, with no line between a log level and a credential. Kubernetes splits it into `k8s/base/configmap.yaml` and `k8s/base/secret.yaml`, injected into each Deployment the same way:

```yaml
envFrom:
  - configMapRef:
      name: booking-config
  - secretRef:
      name: booking-secret
```

The ConfigMap exercises two override paths that reach unchanged application code:

| Key | Path | How it works |
|---|---|---|
| `QUARKUS_OTEL_EXPORTER_OTLP_ENDPOINT` | Ordinal override | `application.properties` hardcodes `quarkus.otel.exporter.otlp.endpoint=http://lgtm:4317` with no `${...}` placeholder. MicroProfile Config's environment source (ordinal 300) outranks the properties file (ordinal 250), so the mapped variable wins with no code change. |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | Native placeholder | `app/telemetry.py` already reads this variable, defaulting to `http://lgtm:4318`. |

Both endpoints point at `otel-collector.ch26-booking.svc.cluster.local`, which resolves to nothing because this tier deploys no collector. That's harmless: each `BatchSpanProcessor` logs a dropped export and the HTTP path is untouched. The subject is the override mechanism, not the tracing pipeline.

`booking-secret` holds one key, `PRICING_PROVIDER_API_KEY`, injected through the same `envFrom` as the ConfigMap. Neither service reads it, because both use an in-memory store with no upstream credential, so it carries a representative value to show the mechanism. Both kinds reach the container:

```bash
$ kubectl -n ch26-booking exec deploy/quarkus-booking -- env | grep -E "PRICING_PROVIDER_API_KEY|QUARKUS_OTEL_EXPORTER_OTLP_ENDPOINT"
QUARKUS_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.ch26-booking.svc.cluster.local:4317
PRICING_PROVIDER_API_KEY=demo-pricing-key-ch26-dev-only
```

A `Secret` is its own API kind: base64-encoded at rest (an encoding, not encryption) and RBAC-restrictable separately from ConfigMaps. Production uses a SealedSecret or an ExternalSecret synced from a vault, not a plaintext value in Git.

### Autoscaling: a CPU-based HPA

Compose has `docker compose up --scale app=3`, a one-shot command with no feedback loop. `k8s/base/hpa.yaml` adds the loop for the Quarkus Deployment:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: quarkus-booking-hpa
  namespace: ch26-booking
  labels:
    app.kubernetes.io/part-of: ch26-booking
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: quarkus-booking
  minReplicas: 1
  maxReplicas: 3
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: 70
```

The controller reads CPU from the `metrics-server` addon, which `run-minikube.sh` enables alongside `ingress`, and scales `quarkus-booking` between 1 and 3 replicas. Only Quarkus gets one: JVM warm-up under load is the more CPU-bound case, and leaving `python-booking` unscaled shows that not every workload needs an HPA. A new HPA reports `cpu: <unknown>/70%` until `metrics-server` collects its first sample, then settles, for example at `cpu: 2%/70%`.

## kustomize: base and minikube overlay

The base under `k8s/base/` references placeholder image names, `booking/quarkus:latest` and `booking/python:latest`, that are never deployed as written. The overlay `k8s/overlays/minikube/kustomization.yaml` lists `../../base` as its resource and names the pinned tag:

```yaml
images:
  - name: booking/quarkus
    newName: booking/quarkus
    newTag: "1.0"
  - name: booking/python
    newName: booking/python
    newTag: "1.0"

replicas:
  - name: quarkus-booking
    count: 1
  - name: python-booking
    count: 1
```

The base describes the application's shape for any target, and the overlay supplies what is specific to one: here the image tag the script builds. Without the split, the Deployment either hardcodes `booking/quarkus:1.0`, which breaks once a second target such as OpenShift Local needs a different tag or host, or each target keeps a hand-edited copy with no single source of truth. `k8s/kustomization.yaml`, the CI entrypoint, points at the minikube overlay, so `kubectl kustomize examples/26-minikube/k8s` and the overlay path build the same manifests.

`run-minikube.sh` brings the stack up in order:

1. `minikube start -p ch26-booking --driver=docker` starts the cluster.
2. `minikube addons enable ingress` and `minikube addons enable metrics-server` turn on the two capabilities the manifests need.
3. `minikube image build -p ch26-booking -t booking/quarkus:1.0 -f Containerfile examples/25-local-with-docker-compose/quarkus` builds straight into the cluster's image store, with no registry push, no `minikube image load` and no `eval $(minikube docker-env)`. The command is driver-agnostic, and `imagePullPolicy: IfNotPresent` finds the image. The Python image builds the same way.
4. `kubectl apply -k k8s` applies the manifests and `kubectl rollout status` waits on both Deployments.
5. The script prints the pods, the Ingress host, the minikube IP, sample `curl` commands and the HPA. It leaves the cluster running.

`MINIKUBE_DRIVER` and `MINIKUBE_PROFILE` override the driver and profile. If `~/.minikube/config/config.json` pins `rootless: true` globally and your Docker Engine isn't rootless, `minikube start` with the `docker` driver fails fast with `MK_USAGE`. The script passes `--rootless=${MINIKUBE_ROOTLESS:-false}`; run `MINIKUBE_ROOTLESS=true bash run-minikube.sh` if your Docker context is rootless.

This tier deploys no collector, Tempo, Loki, Mimir or Postgres, and stops at an upstream ingress-nginx cluster with no operators, mesh, registry or cluster-wide security policy beyond each Deployment's `securityContext` (`runAsNonRoot`, drop-all capabilities, `seccompProfile: RuntimeDefault`). The OpenShift Local appendix moves the same service onto Routes, Security Context Constraints and an operator-managed platform.

{% include excalidraw.html file="26-kubernetes-on-minikube" alt="The Compose topology on the left (published host ports, Docker embedded DNS, a single healthcheck, plaintext environment variables, manual scale commands) mapped against the Kubernetes topology on the right (a ClusterIP Service and host/path-routed Ingress, three-tier startup/readiness/liveness probes, a ConfigMap and Secret injected via envFrom, and a CPU-based HorizontalPodAutoscaler), with a kustomize base and minikube overlay pinning the real image tag in between." caption="Figure 26.1: The same two booking images, with Compose primitives on the left mapped to Kubernetes equivalents on the right, assembled by a kustomize base and minikube overlay." %}

## When to move from Compose

Move when a deployment needs something Compose can't provide:

- host and path routing in front of more than one service;
- a rolling update that never drops available replicas;
- separate readiness and liveness semantics;
- a config and secret split with its own access control;
- scaling decided by the platform.

The cost is a base and overlay to maintain instead of one `compose.yaml`, a cluster to create and delete (`minikube delete -p ch26-booking`), and more moving parts between client and response: an Ingress controller, a label selector, three probes. For a single-host dev loop or a CI job that only needs both services reachable, Compose stays the default. Reach for Kubernetes when the question changes from "can I reach both containers" to "can this system route, heal, configure and scale itself unwatched." Reach for the OpenShift Local tier when it adds "under a platform's own security and operator model."

## Build, run, observe

```bash
cd examples/26-minikube && ./run-minikube.sh
```

The script starts minikube, builds both images into the cluster, applies the kustomized manifests, waits for both rollouts and prints the Ingress host with sample booking requests. Both pods report `1/1 Running`. The host `booking.ch26.local` has no DNS entry: send the request to the minikube IP with a `Host: booking.ch26.local` header, or add an `/etc/hosts` line. The captured run is in `examples/26-minikube/README.md`.

- `POST /quarkus/bookings` and `POST /python/bookings` through the Ingress: both return `201 Created` with `Location: /bookings/bkg_...`, one host routed by path.
- `kubectl -n ch26-booking exec deploy/quarkus-booking -- env`: the ConfigMap and Secret values, including `QUARKUS_LOG_LEVEL=INFO`, are in the container's environment.
- `kubectl -n ch26-booking get hpa` right after rollout: `cpu: <unknown>/70%` for the first 60 to 90 seconds, with `FailedGetResourceMetric` events in `kubectl describe hpa`, then a reading such as `cpu: 2%/70%`.
- `kubectl kustomize examples/26-minikube/k8s | kubeconform -strict -summary`: 9 resources, all valid, with no cluster running.

Tear down with `minikube delete -p ch26-booking`.

## For deeper coverage

- Cloud Native Design Patterns, "Appendix R: minikube": the minikube conventions (`addons enable`, `image build`) the script follows.
- Bilgin Ibryam & Roland Huß, *Kubernetes Patterns* (O'Reilly, 2023): the probe, config and autoscaling patterns used here.
- Brendan Burns, Joe Beda, Kelsey Hightower & Lachlan Evenson, *Kubernetes: Up and Running* (O'Reilly, 2022): Deployments, Services and rollout mechanics in depth.
- [Kubernetes docs: Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): the official reference behind the three-probe split.
