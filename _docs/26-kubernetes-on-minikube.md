---
title: "Kubernetes on minikube"
order: 26
part: "Running it: Docker → minikube → CRC"
description: "Moving the same two booking images from Chapter 25's Compose file onto a real cluster (Service and Ingress routing, three-tier health probes, ConfigMap/Secret injection, and a CPU-based HPA) via a kustomize base and minikube overlay."
duration: "25 min"
---

## Learning objectives

By the end of this chapter you can:

- Translate Compose primitives (published ports, a single healthcheck, a plaintext environment block, manual `--scale`) onto their Kubernetes equivalents (`Service`+`Ingress`, three-tier probes, `ConfigMap`/`Secret`, an `HPA`).
- Distinguish `startupProbe`, `readinessProbe`, and `livenessProbe`, and explain which lifecycle decision each one gates.
- Inject configuration via `ConfigMap`/`Secret` and `envFrom` without changing application code, using both an ordinal-override and a native-placeholder path.
- Configure a CPU-based `HorizontalPodAutoscaler` against the `metrics-server` addon.
- Structure manifests as a kustomize base plus a minikube overlay so a second target can reuse the same base.

## Why this matters

Chapter 25 proved one thing precisely: a traced `POST /bookings` reaches Tempo under a fixed trace id, on a single host, behind one `docker compose up`. Nothing about that proof depended on Compose specifically: it depended on two containers running somewhere and a collector somewhere they could reach. This chapter moves "somewhere" to a cluster. `examples/26-minikube/` takes the exact two images Chapter 25 built (same `quarkus/` and `python/` sources, same Containerfiles, no third copy of the application) and deploys them onto a local Kubernetes cluster with `kubectl apply -k`. The booking logic doesn't change. What changes is everything standing between a client and that logic: how a request finds a pod, how the cluster decides a pod may receive traffic, how configuration reaches a container without living in the image, and what happens when more than one replica is the right answer.

This chapter stays narrow by design. It documents manifests against a captured cluster run (minikube v1.38.1, Kubernetes v1.35.1, profile `ch26-booking`) rather than a generic survey of Kubernetes resource types. `examples/26-minikube/` carries no `verify.sh`; `scripts/validate.py`'s cluster-dir check expects that, because this is the first cluster-tier example in the book and a clusterless CI matrix has no cluster to run a verification script against. The only CI coverage this directory gets is static: `kubectl kustomize examples/26-minikube/k8s | kubeconform -strict` validates every manifest's shape against the Kubernetes API schema on every push, without starting minikube. Bringing the cluster up (building images, applying manifests, watching a rollout succeed) is a local, by-hand step, and `run-minikube.sh` is how a reader does it.

## Compose → Kubernetes: what changes

### Networking: published ports vs. Service + Ingress

In Chapter 25's `compose.yaml`, each service gets its own published host port (`8105:8080` for Quarkus, `8024:8000` for Python), and a client picks which service to talk to by picking which port to hit. There is no routing layer in front of either container; the port *is* the address. A service-to-service call inside the compose network (neither booking service makes one today) would resolve through Compose's embedded DNS, where a plain service name like `lgtm` is enough to find another container on the shared network.

Kubernetes drops both halves of that model. `k8s/base/quarkus-deployment.yaml` and `k8s/base/python-deployment.yaml` each pair a `Deployment` with a `Service` of `type: ClusterIP` (`quarkus-service` on port 8080, `python-service` on port 8000), reachable only from inside the cluster. Neither pod has a published host port. The only way outside traffic reaches either one is `k8s/base/ingress.yaml`'s single `Ingress`, and an Ingress routes by **host and path**, not port. `booking-ingress` puts both apps behind one host, `booking.ch26.local`, and tells them apart by URL prefix: `/quarkus(/|$)(.*)` backed by `quarkus-service:8080`, `/python(/|$)(.*)` backed by `python-service:8000`. Neither `BookingResource` nor `main.py` mounts its routes under `/quarkus` or `/python` (both still answer at `/bookings`), so the Ingress carries an `nginx.ingress.kubernetes.io/rewrite-target: /$2` annotation that strips the matched prefix before proxying; the regex's second capture group becomes `$2` in the rewrite target, so a request to `/quarkus/bookings` reaches the Quarkus pod as plain `/bookings`.

The in-cluster DNS story is the same idea as Compose's, with a real object standing in front of it. Compose's embedded DNS resolves a bare service name to whichever container answers on the shared network; Kubernetes gives that name resolution a concrete, inspectable object, a `Service`, sitting between the DNS name (`quarkus-service.ch26-booking.svc.cluster.local`) and the pods it load-balances across, rather than an alias resolving straight to a container's own IP. That Service is also the layer the ConfigMap's `QUARKUS_OTEL_EXPORTER_OTLP_ENDPOINT` points at later in this chapter: the DNS name of a Service that this tier never deploys, which turns out to be harmless rather than broken.

### Deployments, Services, and rollouts

A `Deployment` does more than Compose's container definition ever had to. `compose.yaml` names an image, a port, an environment block, and a healthcheck; a one-shot `docker compose up --scale` is the only lever Compose offers for running more than one instance, and nothing in Compose reconciles a crashed container back to a known-good state beyond a restart policy. Both Deployments here declare `strategy: RollingUpdate` with `maxUnavailable: 0, maxSurge: 1`: a new pod comes up and passes its readiness gate before the old one is torn down, so a rollout never drops available replicas, even at `replicas: 1`. `run-minikube.sh` waits on exactly that guarantee: `kubectl rollout status deployment/quarkus-booking --timeout=240s` doesn't return until the controller reports the new pod set healthy, not just created.

The Service in front of each Deployment handles load-balancing and the stable-address problem in one object. Pods are disposable (a crash, an eviction, or a rolling update constantly swaps one pod's IP for another's), and the Service's `selector` (matching on `app.kubernetes.io/name: quarkus-booking`) is what lets `quarkus-service`'s ClusterIP and DNS name stay fixed while the pods behind it come and go. Compose's container names are comparatively stable because Compose doesn't replace containers out from under a running stack the way a rollout routinely does.

### Probes: three gates, not one

Compose's `healthcheck:` block is a single `CMD curl` entry, polled on a timer by the Docker engine, with one outcome: healthy or not. Kubernetes splits that question into three, each controlling a different lifecycle decision, and the real contrast between the two app images here is that Quarkus has enough health surface to make all three distinct, while Python doesn't.

Quarkus ships `quarkus-smallrye-health` on its classpath (see `examples/25-local-with-docker-compose/quarkus/pom.xml`), which exposes three separate endpoints (`/q/health/started`, `/q/health/ready`, `/q/health/live`) and `quarkus-deployment.yaml` points a different probe at each:

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

The `startupProbe` exists because a JVM's cold start is slow and bursty: `failureThreshold: 30` at a 5-second period gives the application 150 seconds to report started before Kubernetes gives up and restarts the container, without that generous allowance ever leaking into the faster, tighter `readinessProbe`/`livenessProbe` windows that govern the pod once it's running. The readiness and liveness checks answer two different questions even though they look structurally identical: a failing `readinessProbe` pulls the pod out of its Service's load-balancing rotation: traffic stops arriving, but the container keeps running, because the problem might be transient (a downstream dependency warming up, a connection pool temporarily exhausted) and killing the process wouldn't fix it. A failing `livenessProbe` does the opposite: Kubernetes assumes the process itself is wedged and restarts the container, because no amount of waiting fixes a deadlock. Readiness gates traffic; liveness gates the process's existence.

Python's FastAPI app has exactly one health surface (`/health`, with no started/ready/live split), so `python-deployment.yaml`'s three probes all target the same path:

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

That's not a shortcut in writing the manifest; it's the visible, structural fact that an ASGI app with one `/health` route cannot distinguish "started but not ready" from "ready but no longer live" the way a framework shipping three dedicated endpoints can. The three probe *kinds* still mean different things to the kubelet (a liveness failure here still restarts the pod; a readiness failure still pulls it from the Service), but the single underlying check can't express more than "the process answers HTTP" either way. A reader comparing the two manifests side by side sees how much a framework's own health-check surface buys a deployment.

### Config and secrets: out of the image, into two Kubernetes objects

Compose's `environment:` block is plaintext, committed in `compose.yaml`, and visible to anyone who runs `docker inspect` against the running container: one flat bag of key-value pairs with no distinction between a log level and a credential. Kubernetes splits that bag into two kinds, `k8s/base/configmap.yaml` and `k8s/base/secret.yaml`, both injected into each Deployment the same mechanical way:

```yaml
envFrom:
  - configMapRef:
      name: booking-config
  - secretRef:
      name: booking-secret
```

The ConfigMap carries two kinds of keys, because they exercise two different override paths that land on the same unchanged application code. `QUARKUS_OTEL_EXPORTER_OTLP_ENDPOINT` is an **ordinal-override** key: `application.properties` hardcodes `quarkus.otel.exporter.otlp.endpoint=http://lgtm:4317` with no `${...}` placeholder, but MicroProfile Config's environment-variable source carries a higher config ordinal than the properties file, so the mapped env var wins automatically, no code change needed. `OTEL_EXPORTER_OTLP_ENDPOINT` is a **native placeholder**: the Python side already reads that exact variable name in `app/telemetry.py`, defaulting to `http://lgtm:4318`, so the ConfigMap just supplies the documented knob. Both paths move a wire address out of application code by two different mechanisms, the same split Chapter 25 drew between Quarkus's declarative OTel properties and Python's hand-built SDK pipeline.

What this ConfigMap does not do: it does not stand the Chapter 25 LGTM stack back up on this cluster. Both OTel endpoints point at `otel-collector.ch26-booking.svc.cluster.local`, an in-cluster DNS name that resolves to nothing, because this tier never deploys a collector. That's a harmless no-op: exporting to an endpoint with nothing listening just logs a dropped export in each `BatchSpanProcessor` and leaves the HTTP response path untouched. The point here is the override *mechanism*, a ConfigMap value beating a hardcoded property and a native env placeholder reaching the app unchanged, not a rerun of Chapter 25's tracing pipeline.

The Secret is where the kind-level distinction from a ConfigMap matters. `booking-secret` carries one key, `PRICING_PROVIDER_API_KEY`, wired into both Deployments via `secretKeyRef` exactly like the ConfigMap keys. Neither booking service reads that key today (both run an in-memory store with no upstream credential to protect), so this Secret shows the mechanism with a representative value, standing in for a credential neither app needs yet. A `Secret` is a distinct Kubernetes API kind from a `ConfigMap`, not just another key in the same bag: it's base64-encoded at rest (not encrypted by that encoding alone, a frequently misunderstood point), and it's a kind the API server lets a cluster operator RBAC-restrict separately from ConfigMaps, so a pod's access to secrets can be scoped tighter than its access to ordinary config. Reaching the container works identically to the ConfigMap path, confirmed with `kubectl exec`:

```bash
$ kubectl -n ch26-booking exec deploy/quarkus-booking -- env | grep -E "PRICING_PROVIDER_API_KEY|QUARKUS_OTEL_EXPORTER_OTLP_ENDPOINT"
QUARKUS_OTEL_EXPORTER_OTLP_ENDPOINT=http://otel-collector.ch26-booking.svc.cluster.local:4317
PRICING_PROVIDER_API_KEY=demo-pricing-key-ch26-dev-only
```

`k8s/base/secret.yaml`'s own comment names what production would do instead: a SealedSecret or an ExternalSecret synced from a vault, not a plaintext value committed to Git. That's out of scope for a manifests-only chapter whose job is showing the injection mechanism, not standing up a secrets backend.

### Autoscaling: a CPU-based HPA

Compose has nothing resembling an autoscaling primitive: `docker compose up --scale app=3` is a one-shot manual command a human runs, with no feedback loop deciding whether three is the right number. `k8s/base/hpa.yaml` gives the Quarkus Deployment exactly that feedback loop:

```yaml
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: quarkus-booking-hpa
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

The `HorizontalPodAutoscaler` controller reads CPU utilization from the `metrics-server` addon (`run-minikube.sh` enables it alongside `ingress` before anything is deployed) and adjusts `quarkus-booking`'s replica count between 1 and 3 on its own, with no human issuing a scale command. It's scoped to the Quarkus Deployment only, not both: Quarkus's JVM warm-up cost under load is the more illustrative CPU-bound case, and leaving `python-booking` unscaled keeps a real contrast visible rather than pasting the same HPA onto both Deployments by reflex; not every workload needs one. A freshly rolled-out HPA briefly reports `cpu: <unknown>/70%` while `metrics-server` collects its first sample (expected, not a misconfiguration), and this chapter's captured proof shows that reading settle to `cpu: 2%/70%` once a sample lands.

## kustomize: base + minikube overlay

Every manifest above lives under `k8s/base/`, and `k8s/base/quarkus-deployment.yaml` and `k8s/base/python-deployment.yaml` both reference generic placeholder image names (`booking/quarkus:latest`, `booking/python:latest`) that are never meant to be deployed as written. `k8s/overlays/minikube/kustomization.yaml` is the one place the pinned tag gets named:

```yaml
resources:
  - ../../base

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

That split exists for the same reason any base/overlay pair exists: the base describes the application's shape in a way that's reusable across targets, and the overlay supplies the handful of things specific to one target, here just the image tag `run-minikube.sh` builds. A raw, un-kustomized manifest set would either hardcode `booking/quarkus:1.0` into the Deployment (fine for one target, awkward once a second target, say, Appendix A's CRC tier, needs a different tag or host) or leave every target's manifest a hand-edited copy of the last, with no single source of truth for what's shared. `k8s/kustomization.yaml`, the entrypoint CI invokes, does nothing but point at the minikube overlay: `kubectl kustomize examples/26-minikube/k8s` and `kubectl kustomize examples/26-minikube/k8s/overlays/minikube` build the identical manifest set, so there's exactly one path a reader or a CI job needs to know about.

`run-minikube.sh` walks the bring-up in order: `minikube start -p ch26-booking --driver=docker` brings the cluster up, then `minikube addons enable ingress` and `minikube addons enable metrics-server` turn on the two cluster capabilities this chapter's manifests depend on. `minikube image build -p ch26-booking -t booking/quarkus:1.0 -f Containerfile examples/25-local-with-docker-compose/quarkus` builds the same Ch25 image straight into the cluster's image store: no registry push, no separate `minikube image load` round-trip, no `eval $(minikube docker-env)` dance, because `minikube image build` is driver-agnostic and lands the image wherever the kubelet already looks with `imagePullPolicy: IfNotPresent`. The same command runs for the Python image. Then `kubectl apply -k k8s` applies the kustomized manifest set, `kubectl rollout status` waits on both Deployments, and the script prints the Ingress host, the minikube IP, and sample `curl` commands through the Ingress, the same Chapter 25 images, same source, under a different set of platform primitives.

On this book's own dev machine, `minikube start --driver=docker` needed one extra flag: `~/.minikube/config/config.json` pins `rootless: true` globally (set for an unrelated podman-driver profile), and the `docker` driver only honors that under a rootless Docker context, which this host's Docker Engine isn't running under. `run-minikube.sh` passes `--rootless=${MINIKUBE_ROOTLESS:-false}` to override the on-disk default per invocation instead of failing against a host-wide setting it didn't set. `MINIKUBE_ROOTLESS=true bash run-minikube.sh` is the override if a reader's own Docker context is in fact rootless.

What this chapter doesn't do: deploy a collector, Tempo, Loki, or Mimir, or re-prove Chapter 25's trace-id assertion: the OTel endpoints in `booking-config` point at a Service that was never created, which is fine, because the subject here is the injection mechanism, not the pipeline. It also leaves Postgres untouched: neither service persists anything in this tier any more than it did in Chapter 25. And it stops at minikube: an upstream, ingress-nginx-based cluster with no platform operators, no mesh, no registry, and no cluster-wide security policy beyond each Deployment's own `securityContext` (`runAsNonRoot`, a drop-all capability set, `seccompProfile: RuntimeDefault`). Appendix A moves this same service onto OpenShift Local: Routes instead of raw Ingress, Security Context Constraints instead of a self-declared `securityContext`, an operator-managed platform instead of a handful of enabled addons.

{% include excalidraw.html file="26-kubernetes-on-minikube" alt="The Chapter 25 Compose topology on the left (published host ports, Docker embedded DNS, a single healthcheck, plaintext environment variables, manual scale commands) mapped against the Chapter 26 Kubernetes topology on the right (a ClusterIP Service and host/path-routed Ingress, three-tier startup/readiness/liveness probes, a ConfigMap and Secret injected via envFrom, and a CPU-based HorizontalPodAutoscaler), with a kustomize base and minikube overlay pinning the real image tag in between." caption="Figure 26.1: The same two booking images, Compose primitives on the left mapped to their Kubernetes equivalents on the right, assembled by a kustomize base + minikube overlay." %}

## Decision

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Move from Compose to Kubernetes the moment a deployment needs a capability Compose structurally cannot provide: host/path-based routing in front of more than one service, a rolling update that never drops available replicas, independent readiness and liveness semantics instead of one healthcheck verdict, a config/secret split with its own access controls, or a scaling decision made by the platform instead of a human running a command. None of those needs are hypothetical dressing in this example: Chapter 25's booking services didn't change to get them, only the manifests wrapping them did. What a cluster buys costs something in return: a `kustomize` base and overlay to maintain instead of one `compose.yaml`, a cluster to provision and tear down (`minikube delete -p ch26-booking`, not run automatically here) instead of `docker compose down`, and more moving parts between a client and a response: an Ingress controller, a Service's label selector, a kubelet polling three separate probes instead of one. For a single-host dev loop or a small CI job that just needs both services reachable for a contract check, Compose remains the right default: Chapter 25 didn't need an Ingress or an HPA to prove its trace-id assertion, and reaching for one anyway would add a cluster to provision for no capability the claim depended on. Reach for Kubernetes once the question stops being "can I reach both containers" and becomes "can this system route, heal, configure, and scale itself unwatched," and reach for the Appendix A tier once it becomes "can this system do all of that under a platform's own security and operator model, not a developer's own best-effort manifests."</p></div>

## Build, run, observe

```bash
cd examples/26-minikube && ./run-minikube.sh
```

`run-minikube.sh` starts a minikube cluster, builds the Quarkus and FastAPI booking images from Chapter 25's sources straight into the cluster's image store, applies the kustomized manifests, and waits for both deployments to roll out before printing the Ingress host and sample booking requests. The full command output, including pod status and the HPA, is in `examples/26-minikube/README.md`.

## For deeper coverage

- Cloud Native Design Patterns, "Appendix R: minikube": the same minikube bring-up conventions (`addons enable`, `image build`) this chapter's `run-minikube.sh` follows.
- Bilgin Ibryam & Roland Huß, *Kubernetes Patterns* (O'Reilly, 2023): the probe, config, and autoscaling patterns this chapter builds from.
- Brendan Burns, Joe Beda, Kelsey Hightower & Lachlan Evenson, *Kubernetes: Up and Running* (O'Reilly, 2022): Deployments, Services, and rollout mechanics in full depth.
- [Kubernetes docs: Configure Liveness, Readiness and Startup Probes](https://kubernetes.io/docs/tasks/configure-pod-container/configure-liveness-readiness-startup-probes/): the official reference behind this chapter's three-probe split.
