---
title: "OpenShift Local (CRC)"
order: 99
part: "Running it: Docker → minikube → CRC"
appendix: true
appendix_label: "A"
description: "The same two booking images on OpenShift Local: per-app Routes with edge TLS, an in-cluster BuildConfig and ImageStream build, restricted-v2 admission, and a Quarkus build failure traced to its root cause."
duration: "35 min"
---

## Learning objectives

By the end of this chapter you can:

- Replace a minikube `Ingress` with per-service OpenShift `Route`s that terminate edge TLS at the cluster router.
- Build and push a container image entirely inside the cluster with a `BuildConfig` and `ImageStream`, with no external registry or host container engine.
- Explain why the `restricted-v2` Security Context Constraint assigns a UID instead of honoring a Deployment's `runAsUser`, and build images that tolerate it.
- Trace a build failure to its root cause: a non-root UID combined with a node's overlay storage mode.
- Decide when a target platform justifies OpenShift Local (CRC) over minikube.

## Why this matters

The minikube tier uses upstream Kubernetes: a `Deployment` and `Service` per app, an Ingress routing by host and path, probes, a ConfigMap and Secret, an HPA. This appendix runs the same two images, built from `examples/25-local-with-docker-compose/quarkus` and `examples/25-local-with-docker-compose/python` with their unmodified Containerfiles, on **OpenShift Local (CRC)**. CRC is a single-node OpenShift cluster in a local VM, with the real control plane, router, integrated image registry and admission chain.

Many teams don't choose their target platform, and OpenShift enforces rules plain Kubernetes doesn't. Three carry this appendix:

| OpenShift feature | Replaces on minikube |
|---|---|
| **Route**, served by the cluster router | An Ingress controller someone chooses and installs |
| **Integrated image registry**, addressable from day one | A host-engine build loaded into the node |
| **Security Context Constraint** admitting every pod | A permissive default pod security posture |

None is an add-on. They're present on any OpenShift cluster, CRC included.

Unchanged from the minikube tier: the ConfigMap and Secret wired through `envFrom`, the per-app probes (Quarkus's `/q/health/started`, `/q/health/ready` and `/q/health/live` against FastAPI's single `/health`), and `RollingUpdate` with `maxUnavailable: 0`. `examples/99-appendix-a-openshift-crc/` has no `verify.sh`, like the minikube directory. CI is static: `helm lint` and `helm template | kubeconform -ignore-missing-schemas` against the chart under `helm/`. `run-crc.sh` does the bring-up by hand.

## Routes and edge TLS

The minikube Ingress puts both apps behind one host and separates them by prefix (`/quarkus`, `/python`), with a rewrite annotation, because ingress-nginx is an addon and one controller keeps its footprint small. The OpenShift router runs from the moment `crc start` finishes, so `helm/templates/route.yaml` gives each service its own `Route` and hostname, with no path prefix:

{% raw %}
```yaml
apiVersion: route.openshift.io/v1
kind: Route
metadata:
  name: {{ $name }}
  labels:
    app.kubernetes.io/name: {{ $name }}
    {{- include "appendix-a.labels" $root | nindent 4 }}
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

`values.yaml` sets `route: true` for `quarkus-booking` and `python-booking`, and the template ranges over `.Values.services` to emit one Route each. Each gets a hostname of the form `<service>-<namespace>.apps-crc.testing`, served by CRC's ingress operator under a wildcard certificate for `*.apps-crc.testing`.

- `termination: edge` ends TLS at the router. Neither app needs a certificate, a keystore or TLS code.
- `insecureEdgeTerminationPolicy: Redirect` answers plain HTTP with a redirect to the HTTPS URL instead of serving it unencrypted.

Both held on a live CRC instance:

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

`CN=*.apps-crc.testing`, issued by `ingress-operator`, is the router's wildcard certificate, which the FastAPI app never generated or saw. `curl -k` is needed locally because that authority isn't in a client trust store, as on any local cluster. A production Route fronts the same mechanism with a certificate from a real CA and the same Route shape.

## In-cluster builds: BuildConfig and ImageStream

The minikube build, `minikube image build -p ch26-booking -t booking/quarkus:1.0 -f Containerfile examples/25-local-with-docker-compose/quarkus`, avoids a registry push but still needs Docker or Podman on the developer's machine. OpenShift builds inside the cluster. `helm/templates/buildconfig.yaml` defines a Docker-strategy `BuildConfig` per service reading a **binary source**, a tarball of a local directory streamed into the cluster:

{% raw %}
```yaml
apiVersion: build.openshift.io/v1
kind: BuildConfig
metadata:
  name: {{ $name }}
  labels:
    app.kubernetes.io/name: {{ $name }}
    {{- include "appendix-a.labels" $root | nindent 4 }}
spec:
  runPolicy: Serial
  source:
    type: Binary
  strategy:
    type: Docker
    dockerStrategy:
      dockerfilePath: {{ $root.Values.build.dockerfilePath }}
  output:
    to:
      kind: ImageStreamTag
      name: "{{ $name }}:{{ $root.Values.image.tag }}"
```
{% endraw %}

With `build.dockerfilePath: "Containerfile"` and `image.tag: "v1"` in `values.yaml`, the Quarkus build writes to `quarkus-booking:v1`.

`run-crc.sh` drives it with `oc start-build quarkus-booking -n appendix-a-booking --from-dir=examples/25-local-with-docker-compose/quarkus --follow`. `--from-dir` makes the source binary instead of Git-backed. A build pod on the cluster's node runs the unmodified `Containerfile` and pushes the result to an `ImageStream`, the integrated registry's tracking record that resolves `quarkus-booking:v1` to a digest inside `image-registry.openshift-image-registry.svc:5000`. No `podman push`, no `docker login` and no registry credential is involved; only the source tree leaves the machine. `values.yaml`'s `image.registry` points each Deployment at the same in-cluster name, so the BuildConfig output and the Deployment image are the same coordinate.

A project that can edit its `pom.xml` would use the `quarkus-openshift` extension's binary S2I build with a purpose-built builder image. That would mean editing the shared Quarkus app, so the Docker-strategy BuildConfig is used instead. It gives the property that matters here: the image is built in the cluster and lands in the cluster's registry.

## Security Context Constraints

Minikube honors a pinned `runAsUser` (`185` for Quarkus, `1001` for Python, each matching its Containerfile's `USER`). OpenShift doesn't. Every pod passes a Security Context Constraint, and the default `restricted-v2` rejects a pod that demands its own UID and **assigns** one from a high range reserved for the namespace.

`helm/templates/deployment.yaml` therefore has no `runAsUser`. Each container's `securityContext` keeps `runAsNonRoot: true`, `allowPrivilegeEscalation: false`, a drop-all capability set and `seccompProfile: RuntimeDefault`. Both images tolerate an arbitrary UID because their files are group `0`: the Quarkus UBI base image and the Python `COPY --chown=1001:0` both put the application in group `0`, not under one UID.

On a live CRC instance, `oc -n appendix-a-booking exec deploy/python-booking -- id` returned `uid=1000700000(1000700000) gid=0(root) groups=0(root),1000700000`, nowhere near the `1001` the Containerfile names, and the container ran normally. A Deployment that pins `runAsUser` works on minikube and is rejected under the default SCC. The fix is not an SCC exception but a stateless image built to run under group `0` with no UID assumptions.

## The live bring-up

Both Deployments, Routes and BuildConfig and ImageStream pairs deployed with one `helm upgrade --install` on CRC 2.64.0 (OpenShift 4.22.14), sized to `cpus=6`, `memory=24576` and `disk-size=100` on a KVM host. `python-booking` ran end to end: the in-cluster build finished in twenty seconds and pushed to the registry, the Deployment rolled out, the Route served the edge-TLS handshake above, and a booking request returned as it did on the earlier tiers:

```bash
$ curl -sSk -D - -X POST https://python-booking-appendix-a-booking.apps-crc.testing/bookings \
    -H 'Content-Type: application/json' \
    -d '{"origin":{"unLocode":"USNYC","name":"New York","country":"US"}, ...}'

HTTP/1.1 201 Created
location: /bookings/bkg_01M4RNPRQ4JNFN8THTCCSA73Q6
content-type: application/json
```

### A Quarkus build failure and its cause

`quarkus-booking`'s in-cluster build fails every time, partway through Maven, with `Cannot create resource output directory: /build/target/classes`. It isn't SCC, RBAC, disk or quota:

- The build pod runs under the `privileged` SCC that OpenShift grants `openshift-builder` pods, per its `openshift.io/scc` annotation.
- The node had 52 GB free and the project had no `ResourceQuota` or `LimitRange`.
- The same `WORKDIR`, `COPY` and `RUN` sequence under plain `podman build` on the CRC node (`oc debug node/crc`, then `chroot /host`) fails the same way with `mkdir: cannot create directory 'target': Permission denied`. Adding `USER 0` before it makes the build succeed.

The Python build stage runs `USER 0`. The Quarkus build stage sets no `USER` and inherits its UBI base image's non-root default, `uid=185`. On this VM, buildah logs `Not using native diff for overlay, this may cause degraded performance` on every build, which means a `RUN` step as a non-root UID can't create a directory under a path a prior `COPY` touched. That asymmetry makes the Python build pass and the Quarkus build fail on the same cluster, chart and SCC. A `STORAGE_DRIVER=vfs` override on the BuildConfig made no difference.

A durable fix is `USER 0` in the Quarkus Containerfile's build stage, which edits the shared app, or a different storage driver on the CRC node, which no reader can repeat reliably.

An in-cluster build removes the host engine and adds a dependency on the cluster's own storage configuration. A Containerfile that never needed to think about its build stage's UID under `docker compose` or `minikube image build` can fail when the builder underneath is a different host with different overlay semantics. Both of those ran this exact Containerfile without incident.

{% include excalidraw.html file="appendix-a-openshift-crc" alt="OpenShift Local topology: a client reaching an edge-TLS Route served by the cluster's router, routing to a Service in front of app pods assigned a UID by the restricted-v2 SCC, with a BuildConfig streaming binary source into the cluster and pushing the built image to an ImageStream in the integrated registry that the Deployment pulls from." caption="Figure A.1: Edge-TLS Routes, an in-cluster BuildConfig and ImageStream build, and restricted-v2 SCC admission, replacing minikube's Ingress, host-engine image build and permissive default pod security." %}

## When to use CRC

Use OpenShift Local when the target is OpenShift, not Kubernetes in general, and you need to validate:

- how a manifest behaves against a Route instead of an Ingress;
- how a Security Context Constraint admits or rejects a pod before it reaches a kubelet;
- how an in-cluster BuildConfig builds and pushes with no external registry and no host engine.

Minikube can't exercise any of these: an Ingress controller isn't a Route, a permissive default isn't an SCC, and `minikube image build` proves a host-engine build, not an in-cluster one.

The costs are a heavier VM (`cpus=6` and `memory=20480` at minimum for these two small services, more with a database or broker), a slower first boot, and a build environment with its own storage and kernel behavior, as the Quarkus failure shows. For feature work or a CI job that needs both services reachable, minikube or Compose stays the default.

## Build, run, observe

```bash
cd examples/99-appendix-a-openshift-crc && ./run-crc.sh
```

The script starts OpenShift Local, builds both images in-cluster through the chart's BuildConfig and ImageStream pair, rolls out both Deployments and prints each service's edge-TLS Route URL with a sample booking request. Expect the Python build and rollout to complete and the Quarkus build to fail as described above. The full output is in `examples/99-appendix-a-openshift-crc/README.md`.

- Request the Python Route over plain HTTP: you get `302 Found` to the HTTPS URL.
- Add `runAsUser: 1001` to the Python container's `securityContext`: the default SCC rejects the pod.
- Run `oc exec deploy/python-booking -- id`: the UID is in the namespace's assigned range, not `1001`.
- In `oc debug node/crc` with `chroot /host`, run the Quarkus build stage's `WORKDIR`, `COPY` and `RUN` sequence under `podman build`: it fails with `Permission denied` on `target`, and succeeds once `USER 0` precedes it.

## For deeper coverage

- Cloud Native Design Patterns, "Appendix S: OpenShift Local": the CRC conventions (`crc start`, Routes, SCCs) that `run-crc.sh` follows.
- [OpenShift Local (CRC) documentation](https://crc.dev/crc/): the official reference for sizing, starting and administering a CRC instance.
- [Quarkus: Deploying to OpenShift guide](https://quarkus.io/guides/deploying-to-openshift): the `quarkus-openshift` binary S2I path that the Docker-strategy BuildConfig stands in for.
- Bilgin Ibryam & Roland Huß, *Kubernetes Patterns* (O'Reilly, 2023): the Service and config patterns carried over onto OpenShift's Route and SCC model.
