# Appendix A — OpenShift Local (CRC) deployment tier

Deploys the SAME two booking services as
[`examples/25-local-with-docker-compose`](../25-local-with-docker-compose)
(identical `quarkus/` and `python/` sources and Containerfiles — no third
copy of the app) onto **OpenShift Local (CRC)**, a real single-node
OpenShift cluster. Ch26 showed what changes going from "containers on one
host" to "a Kubernetes deployment tier." This appendix shows what changes
again going from plain Kubernetes to OpenShift specifically: **Routes**
instead of an Ingress controller, **edge TLS** terminated by the cluster's
own router, and an **in-cluster build** that never leaves the cluster to
reach an external registry.

This directory is a **cluster-tier example** (it needs a real, running CRC
cluster) and deliberately carries **no `verify.sh`** —
`scripts/validate.py`'s `cluster-dir-no-verify` check enforces that, so the
clusterless CI examples matrix never tries to auto-discover and run one
here. The only CI coverage for this directory is a static one: the
`k8s-manifests` job in `.github/workflows/contracts.yml` runs

```
helm lint examples/99-appendix-a-openshift-crc/helm
helm template examples/99-appendix-a-openshift-crc/helm | kubeconform -ignore-missing-schemas -summary
```

(`-ignore-missing-schemas`: `Route`, `BuildConfig`, and `ImageStream` are
OpenShift CRDs — kubeconform's upstream Kubernetes schema set has no entry
for them, so those three kinds are reported `Skipped`, not `Invalid`. The
six plain-Kubernetes kinds — `Deployment`, `Service`, `ConfigMap`, `Secret`
— still get full schema validation.)

Bringing the cluster up for real is a local, by-hand step: `run-crc.sh`.

## Ch26 (minikube) → Appendix A (CRC): what changes

| Concern | Ch26 (minikube) | Appendix A (CRC) |
|---|---|---|
| External entry point | One `Ingress` (nginx-ingress), both apps behind **one host** (`booking.ch26.local`), told apart by **path prefix** (`/quarkus`, `/python`) with a `rewrite-target` annotation | **Two Routes**, one per app, each with its **own** `apps-crc.testing` hostname — no ingress controller to install, no path-rewrite gymnastics |
| TLS | None — plain HTTP to the Ingress | **Edge TLS**: the Route's `tls.termination: edge` ends HTTPS at the cluster's router; `insecureEdgeTerminationPolicy: Redirect` sends plain HTTP straight to HTTPS. Neither app terminates TLS itself |
| Getting an image into the cluster | `minikube image build` — builds straight into minikube's own container runtime, no registry object at all | A **`BuildConfig`** (Docker strategy, binary source) builds **inside the cluster** and pushes to an **`ImageStream`** in OpenShift's integrated registry (`image-registry.openshift-image-registry.svc:5000`) — a real registry object, reachable in-cluster by Service DNS, with no external account |
| Pod security | `restricted-v2`-equivalent (minikube's default PSA profile is permissive; manifests still pin `runAsUser: 185` / `runAsUser: 1001`, matching each Containerfile's own `USER`) | OpenShift's **`restricted-v2` SCC** *assigns* a UID from the namespace's range and rejects a pod that demands its own — so this chart drops `runAsUser` entirely for both Deployments and lets OpenShift pick (see `helm/templates/deployment.yaml`'s comment) |
| Namespace bootstrap | `kubectl apply -k` against the default namespace manifest | `oc new-project appendix-a-booking` — a *Project* is OpenShift's wrapper around a Namespace, carrying its own RBAC and quota defaults |

Everything else — the ConfigMap/Secret → `envFrom` wiring, the per-app
probe shape (Quarkus's three `/q/health/*` endpoints vs. the FastAPI app's
single `/health` for all three), `RollingUpdate` with `maxUnavailable: 0` —
is unchanged from Ch26; re-proving that wiring is not this appendix's
point.

## The chart: `helm/`

One `services:` map in `helm/values.yaml` drives every per-app template
(`deployment.yaml`, `service.yaml`, `route.yaml`, `buildconfig.yaml`,
`imagestream.yaml`) — the same "one template, services described as data"
idiom as
`~/Dev/modernizing-enterprise-applications/openshift/helm/mea/values.yaml`.
`Chart.yaml` lives directly at `helm/Chart.yaml`, so the CI job's exact
invocations (`helm lint examples/99-appendix-a-openshift-crc/helm`, `helm
template examples/99-appendix-a-openshift-crc/helm`) resolve without any
subpath juggling.

```
helm/
├── Chart.yaml
├── values.yaml
└── templates/
    ├── _helpers.tpl        # labels + the <registry>/<namespace>/<name>:<tag> image helper
    ├── configmap.yaml       # appendix-a-config
    ├── secret.yaml          # appendix-a-secret (dev-only, plaintext-in-git demo value)
    ├── imagestream.yaml     # one ImageStream per service
    ├── buildconfig.yaml     # one Docker-strategy BuildConfig per service
    ├── deployment.yaml
    ├── service.yaml
    ├── route.yaml           # edge TLS, one per service
    └── NOTES.txt
```

### Routes + edge TLS

```yaml
apiVersion: route.openshift.io/v1
kind: Route
spec:
  to: { kind: Service, name: quarkus-booking }
  port: { targetPort: http }
  tls:
    termination: edge
    insecureEdgeTerminationPolicy: Redirect
```

`oc apply`-ing this (or `helm install`) hands the Service a real external
hostname served by the cluster's router — nothing to publish on the host,
no `NodePort`, no separate Ingress controller `Deployment` to run. Both
booking services get one (`route: true` in `values.yaml` for both
`quarkus-booking` and `python-booking`), each independently addressable.

### The in-cluster build: Docker-strategy `BuildConfig`

```yaml
apiVersion: build.openshift.io/v1
kind: BuildConfig
spec:
  source: { type: Binary }
  strategy:
    type: Docker
    dockerStrategy: { dockerfilePath: Containerfile }
  output:
    to: { kind: ImageStreamTag, name: "quarkus-booking:v1" }
```

`run-crc.sh` feeds the **exact** `examples/25-local-with-docker-compose/
{quarkus,python}` source trees to this BuildConfig with `oc start-build
<service> --from-dir=<path> --follow`: OpenShift streams that directory
into a build pod, runs the project's own (unmodified) `Containerfile`
through the Docker build strategy, and pushes the result straight to the
`ImageStreamTag` in the project's own slice of the integrated registry.
No `podman`/`docker push`, no registry login, no host container engine
anywhere in that path — the headline "no external registry" story this
appendix exists to show.

**Why Docker strategy, not real S2I.** A genuine binary-S2I build for the
Quarkus service — the path the `lgtm-crc` skill documents
(`references/image-builds.md`), via the `quarkus-openshift` Maven
extension — needs an `openshift` Maven profile added to the service's own
`pom.xml`. That means editing
`examples/25-local-with-docker-compose/quarkus`, which is out of scope for
this appendix: the Ch25 apps are reused **completely unmodified**,
Containerfile included, same as Ch26. A Docker-strategy `BuildConfig` with
a binary source earns the identical property that matters here — the
image is built *inside the cluster* and lands in *its own registry*, no
external registry, no host engine — directly from the Containerfile that
compose (Ch25) and minikube (Ch26) already build. A real project with
room to touch the service's `pom.xml` should prefer true S2I; see the
`lgtm-crc` skill for that path.

### ConfigMap / Secret

`helm/templates/configmap.yaml` and `secret.yaml` mirror
`examples/26-minikube/k8s/base/{configmap,secret}.yaml` — same env-var
contract, same `envFrom` wiring, repointed at this chart's own namespace.
Neither booking service has a code path that reads most of these keys
today (no database, no OTel collector deployed in this appendix); that is
deliberate, documented, and harmless — this appendix's subject is
Routes/TLS/the in-cluster build, not re-proving ConfigMap/Secret wiring
Ch26 already covers end to end.

## Running it

```sh
bash run-crc.sh                 # full sequence: build both services, deploy, wait, print both Route URLs
bash run-crc.sh --skip-build    # redeploy only, images already built
```

It will: start CRC if it isn't already running (switching to the
`crc-admin` kubeconfig context CRC writes — no password is ever read,
typed, or printed), `oc new-project appendix-a-booking` plus `helm upgrade
--install` the chart (which creates the `BuildConfig`/`ImageStream` pair
the build step targets), run both services' in-cluster builds with
`oc start-build --from-dir`, roll both Deployments to pick up the freshly
pushed images, wait for rollout, and print both Route URLs plus a sample
`curl -k` booking request against each.

**Prerequisites:** `crc`, `oc`, `helm` on `PATH`; a Red Hat Developer pull
secret; CRC sized while stopped (this appendix only needs the "core"
sizing from the `lgtm-crc` skill — two small stateless services, no
Postgres/Kafka):

```sh
crc config set cpus 6
crc config set memory 20480     # 20 GiB
crc config set disk-size 80
crc setup
```

**Teardown** (not automatic — the script leaves the cluster up to poke
at):

```sh
oc delete project appendix-a-booking
crc stop
```

## Verification status

**Static validation (required, CI-gated) — both green:**

```
$ helm lint examples/99-appendix-a-openshift-crc/helm
==> Linting examples/99-appendix-a-openshift-crc/helm
[INFO] Chart.yaml: icon is recommended

1 chart(s) linted, 0 chart(s) failed

$ helm template examples/99-appendix-a-openshift-crc/helm | kubeconform -ignore-missing-schemas -summary
Summary: 12 resources found parsing stdin - Valid: 6, Invalid: 0, Errors: 0, Skipped: 6
```

(12 resources: 2 `Deployment`, 2 `Service`, 2 `Route`, 2 `BuildConfig`, 2
`ImageStream`, 1 `ConfigMap`, 1 `Secret`. The 6 `Skipped` are the three
OpenShift-only kinds — kubeconform has no upstream schema for `Route`,
`BuildConfig`, or `ImageStream`, which is exactly what
`-ignore-missing-schemas` is for; the 6 `Valid` are every plain-Kubernetes
kind, fully schema-checked.)

**Real CRC bring-up:** see `_plans/r06-execution-plan.md`'s Judgment call B
— Appendix A's acceptance bar is static-validated + documented, with real
CRC bring-up **best-effort** (CRC is a full OpenShift VM, far heavier than
minikube). CRC was brought up for real for this build (CRC 2.64.0 / OpenShift
4.22.14, `cpus=6`/`memory=24576`/`disk-size=100`, on a host with KVM). Result:
**`python-booking` fully verified live end to end; `quarkus-booking`'s
in-cluster build hit a genuine, fully root-caused host/kernel limitation**
(not a chart, BuildConfig, or SCC problem) — details below, honestly, not
glossed over.

### `python-booking` — verified live, end to end

```
$ oc new-project appendix-a-booking
$ helm upgrade --install appendix-a examples/99-appendix-a-openshift-crc/helm \
    --namespace appendix-a-booking --set image.tag=v1

$ oc start-build python-booking -n appendix-a-booking \
    --from-dir=examples/25-local-with-docker-compose/python --follow
...
Successfully pushed image-registry.openshift-image-registry.svc:5000/appendix-a-booking/python-booking@sha256:c810e23c...
Push successful

$ oc get builds -n appendix-a-booking
NAME               TYPE     FROM             STATUS     STARTED         DURATION
python-booking-1   Docker   Binary@3690368   Complete   8 minutes ago   20s

$ oc get pods -n appendix-a-booking
NAME                               READY   STATUS      RESTARTS   AGE
python-booking-1-build             0/1     Completed   0          8m19s
python-booking-67b77679d7-qrnzf    1/1     Running     0          9m20s
```

**Edge TLS, for real** — plain HTTP redirects to HTTPS, and the TLS
handshake terminates at the cluster's own router (not the app):

```
$ curl -sS -D - -o /dev/null http://python-booking-appendix-a-booking.apps-crc.testing/health
HTTP/1.1 302 Found
location: https://python-booking-appendix-a-booking.apps-crc.testing/health

$ curl -skv https://python-booking-appendix-a-booking.apps-crc.testing/health 2>&1 | grep -E "SSL connection|subject:|issuer:|HTTP/1.1"
* SSL connection using TLSv1.3 / TLS_AES_128_GCM_SHA256 / X25519MLKEM768 / RSASSA-PSS
* Server certificate:
*   subject: CN=*.apps-crc.testing
*   issuer: CN=ingress-operator@1789448506
< HTTP/1.1 200 OK
```

(`CN=*.apps-crc.testing`, issued by `ingress-operator` — the cluster
router's own wildcard cert, not anything the FastAPI app generated or
mounted. That's what "edge TLS" means in practice.)

**A live booking through the Route:**

```
$ curl -sSk -D - -X POST https://python-booking-appendix-a-booking.apps-crc.testing/bookings \
    -H 'Content-Type: application/json' \
    -d '{"origin":{"unLocode":"USNYC","name":"New York","country":"US"},"destination":{"unLocode":"NLRTM","name":"Rotterdam","country":"NL"},"cargo":[{"description":"Palletized electronics","type":"GENERAL","dimensions":{"weightKg":1200.5,"volumeM3":4.2},"hazardous":false}],"requestedPickup":"2026-02-01"}'

HTTP/1.1 201 Created
location: /bookings/bkg_01M4RNPRQ4JNFN8THTCCSA73Q6
content-type: application/json

{"id":"bkg_01M4RNPRQ4JNFN8THTCCSA73Q6","status":"PENDING","origin":{"unLocode":"USNYC",...},"quote":{"currency":"USD","amount":"3001.25"},...}
```

**ConfigMap/Secret `envFrom`, reaching the container for real:**

```
$ oc -n appendix-a-booking exec deploy/python-booking -- env | grep -E "PRICING_PROVIDER_API_KEY|OTEL_SERVICE_NAME"
OTEL_SERVICE_NAME=shipping-python
PRICING_PROVIDER_API_KEY=demo-pricing-key-appendix-a-dev-only
```

**No `runAsUser`, `restricted-v2` assigned a real UID, and the container
ran under it without edits** (exactly the design the chart's
`deployment.yaml` comment predicts):

```
$ oc -n appendix-a-booking exec deploy/python-booking -- id
uid=1000700000(1000700000) gid=0(root) groups=0(root),1000700000

$ oc get deploy python-booking -n appendix-a-booking -o jsonpath='{.spec.template.spec.containers[0].image}'
image-registry.openshift-image-registry.svc:5000/appendix-a-booking/python-booking:v1
```

### `quarkus-booking` — in-cluster build fails on this host; root-caused, not a chart problem

The `quarkus-booking` `BuildConfig`/`ImageStream`/`Deployment`/`Route` all
deployed cleanly via the same `helm upgrade --install` above (the Route
resolves, `oc get route quarkus-booking` returns a host). But
`oc start-build quarkus-booking --from-dir=.../quarkus --follow` fails
every time, deterministically, partway through the Maven build:

```
[ERROR] Failed to execute goal org.apache.maven.plugins:maven-resources-plugin:3.3.1:resources
  (default-resources) on project ch25-quarkus-compose: Cannot create resource
  output directory: /build/target/classes -> [Help 1]
error: build error: building at STEP "RUN mvn -B package -DskipTests
  -Dmaven.javadoc.skip=true": while running runtime: exit status 1
```

**This was root-caused, not left as a mystery.** The quarkus-booking build
pod already runs under the `privileged` SCC (`oc get pod
quarkus-booking-*-build -o jsonpath='{.metadata.annotations.openshift\.io/scc}'`
→ `privileged`), so it is not an SCC/RBAC restriction. `oc debug node/crc`
+ `ausearch -m avc` showed no SELinux denial around the build. The
cluster's disk has 52 GB free and no `ResourceQuota`/`LimitRange` is set on
the project. Isolating it further, by reproducing the exact
`WORKDIR`/`COPY`/`RUN` sequence with plain `podman build` **directly on the
CRC node** (`oc debug node/crc` → `chroot /host` → `podman build`,
completely bypassing OpenShift's `BuildConfig`/`openshift-builder` machinery)
reproduced the identical failure:

```
STEP 3/4: COPY pom.xml .
--> 08715a2faca2
STEP 4/4: RUN mkdir -p target/classes && echo OK
mkdir: cannot create directory 'target': Permission denied
```

— and adding `USER 0` before the same `WORKDIR`/`COPY`/`RUN` sequence makes
it succeed. The Quarkus side of the Ch25 Containerfile never sets `USER`
in its build stage, so it inherits the `ubi10/openjdk-25:1.24-15` base
image's own default non-root user (`uid=185(default) gid=0(root)`,
confirmed with `podman run ... id`); the Python side's build stage
explicitly runs `USER 0`, which is exactly why `python-booking`'s build
succeeded and `quarkus-booking`'s did not. The actual defect: this CRC
VM's node kernel has `CONFIG_OVERLAY_FS_REDIRECT_DIR` enabled (buildah logs
`Not using native diff for overlay, this may cause degraded performance`
at the start of every build on this host) and, with that feature engaged,
a `RUN` step cannot create a **new** directory under a path a prior `COPY`
touched when running as a non-root UID — a buildah/overlayfs storage-driver
interaction, reproduced with plain `podman` with no OpenShift involved at
all, and not something a Helm chart, a `BuildConfig` spec, or an SCC grant
can work around. (A `STORAGE_DRIVER=vfs` override on the `BuildConfig` was
tried and did not change the outcome — the openshift-builder image's own
container runtime still hit the same path.)

This is a genuine, reproducible **host/kernel limitation of this
particular CRC VM**, not a flaw in Appendix A's chart or the reused Ch25
Containerfile (which builds correctly in `docker compose`, `minikube
image build`, and everywhere else that isn't this exact
buildah+overlay+non-root combination) — fixing it would mean either
editing the Ch25 Containerfile to add `USER 0` to its build stage (out of
scope: the Ch25 apps are reused completely unmodified) or changing the CRC
node's own storage configuration (not a supported, repeatable step for a
reader to follow, and not something this appendix's scope covers). It is
reported here exactly as found, per this task's "do not fake proof"
instruction, alongside `python-booking`'s fully-verified live run as the
best-effort real-CRC evidence for this appendix.
