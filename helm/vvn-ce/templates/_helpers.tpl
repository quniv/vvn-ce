{{/*
Expand the name of the chart.
*/}}
{{- define "vvn-ce.name" -}}
{{- default .Chart.Name .Values.nameOverride | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Create a default fully qualified app name.
*/}}
{{- define "vvn-ce.fullname" -}}
{{- if .Values.fullnameOverride }}
{{- .Values.fullnameOverride | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- $name := default .Chart.Name .Values.nameOverride }}
{{- if contains $name .Release.Name }}
{{- .Release.Name | trunc 63 | trimSuffix "-" }}
{{- else }}
{{- printf "%s-%s" .Release.Name $name | trunc 63 | trimSuffix "-" }}
{{- end }}
{{- end }}
{{- end }}

{{/*
Chart label: name-version
*/}}
{{- define "vvn-ce.chart" -}}
{{- printf "%s-%s" .Chart.Name .Chart.Version | replace "+" "_" | trunc 63 | trimSuffix "-" }}
{{- end }}

{{/*
Common labels applied to every resource.
*/}}
{{- define "vvn-ce.labels" -}}
helm.sh/chart: {{ include "vvn-ce.chart" . }}
{{ include "vvn-ce.selectorLabels" . }}
{{- if .Chart.AppVersion }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end }}
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Selector labels (stable — used in matchLabels, must not change after first deploy).
*/}}
{{- define "vvn-ce.selectorLabels" -}}
app.kubernetes.io/name: {{ include "vvn-ce.name" . }}
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end }}

{{/*
Name of the Secret that holds DATABASE_URL and OPENROUTER_API_KEY.
*/}}
{{- define "vvn-ce.secretName" -}}
{{- if .Values.secret.existingSecret }}
{{- .Values.secret.existingSecret }}
{{- else }}
{{- include "vvn-ce.fullname" . }}
{{- end }}
{{- end }}

{{/*
Resolved image tag: explicit value → Chart.AppVersion.
*/}}
{{- define "vvn-ce.imageTag" -}}
{{- . | default $.Chart.AppVersion }}
{{- end }}
