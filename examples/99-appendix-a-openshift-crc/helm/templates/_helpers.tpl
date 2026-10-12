{{/*
Common labels applied to every object — the same k8s recommended-label idiom
~/Dev/modernizing-enterprise-applications/openshift/helm/mea's chart uses.
*/}}
{{- define "appendix-a.labels" -}}
app.kubernetes.io/part-of: appendix-a-booking
app.kubernetes.io/managed-by: {{ .Release.Service }}
helm.sh/chart: {{ .Chart.Name }}-{{ .Chart.Version }}
{{- end -}}

{{/*
Full image reference for a service built by this chart's BuildConfig:
<registry>/<release-namespace>/<name>:<tag> — the same path the
BuildConfig's ImageStreamTag output lands at, so a plain `helm upgrade
--install` always finds what run-crc.sh just built, in whatever namespace
the chart is installed into.
Usage: {{ include "appendix-a.image" (list $root $name) }}
*/}}
{{- define "appendix-a.image" -}}
{{- $root := index . 0 -}}
{{- $name := index . 1 -}}
{{ $root.Values.image.registry }}/{{ $root.Release.Namespace }}/{{ $name }}:{{ $root.Values.image.tag }}
{{- end -}}
