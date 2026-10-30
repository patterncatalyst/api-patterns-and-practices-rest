---
title: "OpenShift Local (CRC)"
order: 99
part: "Running it: Docker → minikube → CRC"
appendix: true
appendix_label: "A"
description: "Redeploying the same two Chapter 25 booking images onto OpenShift Local: per-app Routes with edge TLS, an in-cluster BuildConfig/ImageStream build with no external registry, restricted-v2 SCCs, and an unvarnished account of where the Quarkus build hit a host limitation."
duration: "35 min"
---

## Learning objectives

By the end of this chapter you can:

- Replace a minikube `Ingress` with per-service OpenShift `Route`s terminating edge TLS at the cluster router.
- Build and push a container image entirely inside the cluster via a `BuildConfig`/`ImageStream` pair, with no external registry or host container engine.
- Explain why OpenShift's `restricted-v2` Security Context Constraint assigns a UID instead of honoring a Deployment's requested `runAsUser`, and build images that tolerate it.
- Diagnose a build failure down to a root cause (a non-root UID combined with a node's overlay storage mode) instead of treating it as an unexplained platform quirk.
- Decide when a project's target platform justifies standing up OpenShift Local (CRC) instead of staying on minikube.

## Why this matters

Chapter 26 moved the Chapter 25 booking images from "two containers on one host" to "a Kubernetes deployment tier": a `Deployment`/`Service` pair for each app, an Ingress routing by host and path, probes replacing a single healthcheck, a ConfigMap and Secret standing in for a plaintext environment block, an HPA replacing a manual scale command. Every one of those primitives is upstream Kubernetes, installed on minikube through a handful of `minikube addons enable` calls and an ingress-nginx controller a reader never has to think about by name. This appendix takes the same two images (still `examples/25-local-with-docker-compose/quarkus` and `examples/25-local-with-docker-compose/python`, still built from their own unmodified Containerfiles, no third copy of the application anywhere) and runs them on **OpenShift Local (CRC)**, a real single-node OpenShift cluster that installs and boots inside a local VM on a laptop. "Real" is doing work in that sentence: CRC is not a minikube profile with OpenShift-flavored labels painted on. It's the actual OpenShift control plane, the actual router, the actual integrated image registry, the actual admission chain a cluster administrator would recognize from a production OpenShift install, just sized down to fit one machine.

That distinction is the whole reason this appendix exists, and it exists for every container-based project in this catalog, not just this one. The house standard behind this book's sibling projects is that a container tutorial doesn't stop at "it runs on Kubernetes": it keeps going until it also runs on OpenShift, because a meaningful share of the audience this book is written for doesn't get to choose their target platform, and the platform they're handed enforces rules plain Kubernetes doesn't. Three of those rules carry this appendix: OpenShift ships its own **Route** resource instead of relying on an Ingress controller a cluster operator has to choose and install; it ships an **integrated image registry** inside the cluster, addressable the moment the cluster exists; and it admits every pod through a **Security Context Constraint**, a stricter, OpenShift-specific gate that has no equivalent in a stock kubeadm or minikube cluster. None of the three are optional add-ons on OpenShift the way ingress-nginx and metrics-server are optional addons on minikube: they're part of what "OpenShift" means as a platform, present on day one of any cluster a reader stands up, CRC included.

What doesn't change matters too, because this appendix keeps a narrow scope about what it re-proves. The ConfigMap/Secret → `envFrom` wiring, the per-app probe shape (Quarkus's three distinct `/q/health/started`, `/q/health/ready`, `/q/health/live` endpoints against the FastAPI app's single `/health` answering all three), and the `RollingUpdate` strategy with `maxUnavailable: 0` are copied forward from Chapter 26's manifests unchanged. `examples/99-appendix-a-openshift-crc/` carries no `verify.sh`; this is a cluster-tier example exactly like Chapter 26's minikube directory, `scripts/validate.py`'s `cluster-dir-no-verify` check enforces the absence, and the only CI coverage is static: `helm lint` plus `helm template | kubeconform -ignore-missing-schemas` against the chart under `helm/`. Bringing CRC up, building both images, and watching them run is a by-hand step a reader drives with `run-crc.sh`, the same division of labor Chapter 26 established for minikube.

## Routes and edge TLS

Chapter 26's `booking-ingress` puts both applications behind one `Ingress` object, one host (`booking.ch26.local`), and tells the two backends apart by URL prefix: `/quarkus` routed to `quarkus-service`, `/python` routed to `python-service`, with an `nginx.ingress.kubernetes.io/rewrite-target` annotation stripping the prefix before the request reaches either pod. That design exists because minikube has no router of its own; ingress-nginx is a `Deployment` a reader installs as an addon, and routing two backends behind one controller through one host keeps the addon's footprint small. OpenShift doesn't need that compromise, because the router isn't an addon: it's part of the cluster, running from the moment `crc start` finishes. `helm/templates/route.yaml` gives each booking service its **own** `Route`, its own real external hostname, with no path-prefix gymnastics standing between the client and either app:

{% raw %}
```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: {{ $name }}
spec:
  to:
    kind: Service
    name: {{ $name }}
    weight: 100
  port:
    targetPort: http
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```
{% endraw %}

`values.yaml` sets `route: true` for both `quarkus-booking` and `python-booking`, so the template ranging over `.Values.services` emits two Routes, not one shared object standing in front of both. Each resolves to a hostname of the form `<service>-<namespace>.apps-crc.testing` (`python-booking-appendix-a-booking.apps-crc.testing` for the Python side in the real run below) served by CRC's own ingress operator against a wildcard certificate for `*.apps-crc.testing`. `termination: edge` is the headline difference from Chapter 26's plain-HTTP Ingress: TLS ends at the cluster's router, not inside either booking process, and neither application needs a certificate, a keystore, or a single line of TLS-handling code to get it. `insecureEdgeTerminationPolicy: Redirect` closes the other half of the gap: a plain HTTP request doesn't get served unencrypted, it gets a redirect to the HTTPS form of the same URL. Both properties showed up exactly as specified against a live CRC instance:

```bash
$ curl -sS -D - -o /dev/null http://python-booking-appendix-a-booking.apps-crc.testing/health
HTTP/1.1 302 Found
location: https://python-booking-appendix-a-booking.apps-crc.testing/health

$ curl -skv https://python-booking-appendix-a-booking.apps-crc.testing/health 2>&1 \
    | grep -E "SSL connection|subject:|issuer:|HTTP/1.1"
* SSL connection using TLSv1.3 / TLS_AES_128_GCM_SHA256 / X25519MLKEM768 / RSASSA-PSS
* Server certificate:
*   subject: CN=*.apps-crc.testing
*   issuer: CN=ingress-operator@1789448506
< HTTP/1.1 200 OK
```

`CN=*.apps-crc.testing`, issued by `ingress-operator`, is the cluster router's own wildcard certificate: not anything the FastAPI app generated, mounted, or even knows exists. A `curl -k` is still needed on a local CRC instance because that certificate authority isn't in any client's trust store by default, which is exactly the self-signed situation any local developer cluster has; a production OpenShift Route would front the same mechanism with a certificate a real CA issued, with no change to the Route object's shape.

## In-cluster builds: BuildConfig, ImageStream, and no external registry

Chapter 26's build step is a single command run against the host's own container engine, redirected straight into minikube's image store: `minikube image build -p ch26-booking -t booking/quarkus:1.0 -f Containerfile examples/25-local-with-docker-compose/quarkus`. It's driver-agnostic and avoids a registry push entirely, but it still depends on a container engine running on the developer's own machine: Docker or Podman has to be present and working for that command to do anything. OpenShift replaces that dependency with a build that happens entirely inside the cluster, with no host engine involved at any point. `helm/templates/buildconfig.yaml` defines a `BuildConfig` per service, a Docker-strategy build reading a **binary source**: not a Git URL, not a prebuilt image, but a tarball of a local directory streamed straight into the cluster:

```yaml
apiVersion: build.openshift.io/v1
kind: BuildConfig
spec:
  source:
    type: Binary
  strategy:
    type: Docker
    dockerStrategy:
      dockerfilePath: Containerfile
  output:
    to:
      kind: ImageStreamTag
      name: "quarkus-booking:v1"
```

`run-crc.sh` drives that BuildConfig with `oc start-build quarkus-booking -n appendix-a-booking --from-dir=examples/25-local-with-docker-compose/quarkus --follow`: the `--from-dir` flag is what makes the source binary rather than Git-backed, packing the exact directory Chapter 25 and Chapter 26 already build from and shipping it to a build pod OpenShift schedules on the cluster's own node. That build pod runs the project's own, completely unmodified `Containerfile` through the Docker build strategy and pushes the finished image straight to an `ImageStream`: `helm/templates/imagestream.yaml`'s per-service object, a thin tracking record the integrated registry uses to resolve a short name like `quarkus-booking:v1` to a real image digest inside `image-registry.openshift-image-registry.svc:5000`. No `podman push`, no `docker login`, no registry credential of any kind touches this path; the only thing that leaves the developer's machine is the source tree itself, over `oc start-build`'s own streaming connection. `values.yaml`'s `image.registry` points every Deployment at that same in-cluster DNS name, so the Deployment's image reference and the BuildConfig's output land on the identical coordinate with nothing to reconcile by hand.

A production project with room to edit its own `pom.xml` would reach for `quarkus-openshift`'s true binary-S2I build path instead of a Docker-strategy BuildConfig: that extension adds an `openshift` Maven profile and gets a purpose-built S2I builder image rather than a generic Docker build. This appendix doesn't take that path because it would mean editing `examples/25-local-with-docker-compose/quarkus`, and the Chapter 25 apps are reused completely unmodified here exactly as Chapter 26 reused them unmodified on minikube. A Docker-strategy BuildConfig earns the identical property that actually matters for this appendix's point (the image is built inside the cluster and lands in the cluster's own registry, no external registry, no host engine) directly from the same Containerfile compose and minikube already proved out.

## Security Context Constraints

Minikube's default pod security posture is permissive enough that Chapter 26's manifests can pin a specific `runAsUser` (`185` for the Quarkus image, `1001` for the Python image, both matching each Containerfile's own declared `USER`) and have that request simply honored. OpenShift doesn't honor it. Every pod OpenShift admits passes through a **Security Context Constraint**, and the cluster's default, `restricted-v2`, actively rejects a pod that demands a specific UID of its own; instead, it *assigns* one from a high range reserved for the namespace the pod lands in. `helm/templates/deployment.yaml` drops `runAsUser` entirely for both booking Deployments rather than fighting that default: no `runAsUser` key appears anywhere in either container's `securityContext`, only `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, an all-capabilities drop, and `seccompProfile: RuntimeDefault`. Both Chapter 25 images were already built to tolerate an arbitrary assigned UID (the Quarkus side's UBI base image and the Python side's `COPY --chown=1001:0` both put the application's files in group `0` rather than owned by one specific uid), so whichever UID `restricted-v2` hands out, the container runs under it without a single line of either Containerfile changing.

That assignment held exactly as designed on a live CRC instance. `oc -n appendix-a-booking exec deploy/python-booking -- id` returned `uid=1000700000(1000700000) gid=0(root) groups=0(root),1000700000`: a UID nowhere near the `1001` the Containerfile's own `USER` line names, picked entirely by the cluster, with the container running normally under it regardless. The gap between what minikube lets a manifest ask for and what OpenShift actually grants is the practical shape of "OpenShift is stricter than vanilla Kubernetes by default": a plain Kubernetes Deployment that pins `runAsUser` to a fixed value works unmodified on minikube and is rejected outright on OpenShift's default SCC, and the fix isn't a chart change or an SCC exception: a stateless image built to run under group `0` with no UID assumptions, which both Chapter 25 images already are, needs neither.

## The live bring-up: one service runs end to end, one hits a documented wall

Both Deployments, both Routes, and both BuildConfig/ImageStream pairs deployed cleanly through one `helm upgrade --install` against a real CRC instance: CRC 2.64.0, OpenShift 4.22.14, sized to `cpus=6`/`memory=24576`/`disk-size=100` on a host with KVM. `python-booking` went the rest of the way live, end to end: its in-cluster build completed in twenty seconds and pushed to the integrated registry, its Deployment rolled out, its Route served the edge-TLS handshake captured above, and a real booking request through that Route came back exactly as Chapter 25 and Chapter 26 both proved it would:

```bash
$ curl -sSk -D - -X POST https://python-booking-appendix-a-booking.apps-crc.testing/bookings \
    -H 'Content-Type: application/json' \
    -d '{"origin":{"unLocode":"USNYC","name":"New York","country":"US"}, ...}'

HTTP/1.1 201 Created
location: /bookings/bkg_01M4RNPRQ4JNFN8THTCCSA73Q6
content-type: application/json
```

`quarkus-booking`'s in-cluster build did not reach that point, and this appendix reports exactly why rather than quietly dropping the Quarkus side from its evidence. The build fails deterministically, partway through Maven, with `Cannot create resource output directory: /build/target/classes`. It is not an SCC or RBAC problem: the build pod runs under the `privileged` SCC OpenShift grants `openshift-builder` pods by design, confirmed by reading the pod's own `openshift.io/scc` annotation. It is not a disk or quota problem: the node had 52 GB free and no `ResourceQuota` or `LimitRange` on the project. Reproducing the exact `WORKDIR`/`COPY`/`RUN` sequence directly on the CRC node with plain `podman build`, completely bypassing OpenShift's build machinery (`oc debug node/crc` → `chroot /host` → `podman build`), reproduced the identical failure: `mkdir: cannot create directory 'target': Permission denied`. Adding `USER 0` before that same sequence made it succeed.

The root cause traces to one asymmetry between the two Containerfiles: the Python build stage explicitly runs `USER 0`, while the Quarkus build stage never sets a `USER` at all and inherits its UBI base image's own non-root default (`uid=185`). Combined with this particular CRC VM's node storage configuration (buildah logs `Not using native diff for overlay, this may cause degraded performance` on every build on this host, a signal that its overlay filesystem is running in a mode where a `RUN` step can't create a new directory under a path a prior `COPY` touched while running as a non-root UID), that asymmetry is enough to make the Python build succeed and the Quarkus build fail on the identical cluster, identical chart, identical SCC. A `STORAGE_DRIVER=vfs` override on the BuildConfig was tried and made no difference; the `openshift-builder` image's own runtime hit the same path regardless. A durable fix means adding `USER 0` to the Quarkus Containerfile's build stage, which would mean editing `examples/25-local-with-docker-compose/quarkus` (out of scope for an appendix whose entire premise is reusing the Chapter 25 apps unmodified), or changing the CRC node's own storage driver, which isn't a repeatable step a reader following this appendix could reasonably take.

This is the kind of thing an in-cluster build tier is supposed to surface, and surfacing it here, with the root cause nailed down rather than hand-waved, is the point of running this appendix against a real cluster instead of only validating the chart statically. An in-cluster build removes a host container engine from the picture, but it trades that dependency for a new one: the build now runs on *the cluster's own* storage configuration, not the developer's, and a Containerfile that never needed to think about its build stage's UID on `docker compose` or `minikube image build` can hit a wall the moment the thing running `docker build` underneath it is a different host with different overlay semantics. `minikube image build` and `docker compose build` both ran this exact Containerfile without incident; only the in-cluster build, on this exact VM, didn't.

{% include excalidraw.html file="appendix-a-openshift-crc" alt="OpenShift Local topology: a client reaching an edge-TLS Route served by the cluster's router, routing to a Service in front of app pods assigned a UID by the restricted-v2 SCC, with a BuildConfig streaming binary source into the cluster and pushing the built image to an ImageStream in the integrated registry that the Deployment pulls from." caption="Figure A.1: Edge-TLS Routes, an in-cluster BuildConfig/ImageStream build, and restricted-v2 SCC admission, replacing minikube's Ingress, host-engine image build, and permissive default pod security." %}

## Decision

<div class="callout callout--safe"><p class="callout__title">Decision</p><p>Reach for OpenShift Local once the actual target is OpenShift, not Kubernetes in general: the moment a reader needs to validate how a manifest behaves against a Route instead of an Ingress, how a Security Context Constraint admits or rejects a pod before it ever reaches a kubelet, or how an in-cluster BuildConfig builds and pushes an image with no external registry and no host engine in the loop. None of those three things can be faithfully exercised on minikube, no matter how many addons are enabled: an Ingress controller is not a Route, a permissive default pod security profile is not an SCC, and `minikube image build` proves a host-engine build works, not an in-cluster one. What CRC costs in return is real: a heavier VM than minikube needs (`cpus=6`/`memory=20480` minimum for this appendix's two small services, far more for anything with a database or a message broker alongside them), a slower first boot, and, as this appendix's own Quarkus build shows, a build environment with its own storage and kernel quirks that a developer's local Docker Engine doesn't have and can't be assumed away. For a feature under active development, or a CI job that just needs both services reachable for a contract check, minikube or Compose stay the right default: nothing about routing, security admission, or image provenance was in question there. Reach for CRC once the open question is specifically "does this run, admit, and build the way OpenShift runs, admits, and builds things", and treat a result like this appendix's, one service fully proven and the other's failure fully root-caused rather than hidden, as what that question is actually supposed to produce.</p></div>

## Build, run, observe

```bash
cd examples/99-appendix-a-openshift-crc && ./run-crc.sh
```

`run-crc.sh` starts OpenShift Local, builds the Quarkus and FastAPI booking images in-cluster from Chapter 25's sources through the chart's BuildConfig and ImageStream pair, rolls out both deployments, and prints each service's edge-TLS Route URL along with a sample booking request. The full command output is in `examples/99-appendix-a-openshift-crc/README.md`.

## For deeper coverage

- Cloud Native Design Patterns, "Appendix S: OpenShift Local": the same CRC bring-up conventions (`crc start`, Routes, SCCs) this chapter's `run-crc.sh` follows.
- [OpenShift Local (CRC) documentation](https://crc.dev/crc/): the official reference for sizing, starting, and administering a CRC instance.
- [Quarkus: Deploying to OpenShift guide](https://quarkus.io/guides/deploying-to-openshift): the `quarkus-openshift` binary-S2I path this chapter's Docker-strategy BuildConfig stands in for.
- Bilgin Ibryam & Roland Huß, *Kubernetes Patterns* (O'Reilly, 2023): the Service/config patterns this appendix carries over from Chapter 26 onto OpenShift's Route and SCC model.
