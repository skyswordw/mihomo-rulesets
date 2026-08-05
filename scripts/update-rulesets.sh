#!/usr/bin/env bash
set -euo pipefail

repo_root=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
manifest="$repo_root/sources.json"
output_dir="$repo_root/rules"
mihomo_bin=${MIHOMO_BIN:-}

if [[ -z "$mihomo_bin" || ! -x "$mihomo_bin" ]]; then
  echo "MIHOMO_BIN must point to an executable Mihomo binary" >&2
  exit 1
fi

for command_name in curl jq awk cmp; do
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Required command is missing: $command_name" >&2
    exit 1
  fi
done

sha256_file() {
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$1" | awk '{print $1}'
  else
    shasum -a 256 "$1" | awk '{print $1}'
  fi
}

tmp_dir=$(mktemp -d "${TMPDIR:-/tmp}/mihomo-rulesets.XXXXXX")
trap 'rm -r -- "$tmp_dir"' EXIT

source_url=$(jq -er '.reject_domainset.source_url' "$manifest")
minimum_entries=$(jq -er '.reject_domainset.minimum_entries' "$manifest")
minimum_source_bytes=$(jq -er '.reject_domainset.minimum_source_bytes' "$manifest")
minimum_artifact_bytes=$(jq -er '.reject_domainset.minimum_artifact_bytes' "$manifest")

source_file="$tmp_dir/reject_domainset.txt"
artifact_file="$tmp_dir/reject_domainset.mrs"
artifact_check="$tmp_dir/reject_domainset.check.mrs"

curl \
  --fail \
  --location \
  --silent \
  --show-error \
  --retry 3 \
  --retry-all-errors \
  --connect-timeout 15 \
  --max-time 120 \
  "$source_url" \
  --output "$source_file"

source_bytes=$(wc -c < "$source_file" | tr -d ' ')
source_entries=$(awk '!/^[[:space:]]*($|#)/ { count++ } END { print count + 0 }' "$source_file")

if (( source_bytes < minimum_source_bytes )); then
  echo "Source is unexpectedly small: $source_bytes bytes" >&2
  exit 1
fi
if (( source_entries < minimum_entries )); then
  echo "Source has too few entries: $source_entries" >&2
  exit 1
fi

"$mihomo_bin" convert-ruleset domain text "$source_file" "$artifact_file"
"$mihomo_bin" convert-ruleset domain text "$source_file" "$artifact_check"

if ! cmp -s "$artifact_file" "$artifact_check"; then
  echo "Mihomo conversion is not deterministic" >&2
  exit 1
fi

artifact_bytes=$(wc -c < "$artifact_file" | tr -d ' ')
if (( artifact_bytes < minimum_artifact_bytes )); then
  echo "Generated artifact is unexpectedly small: $artifact_bytes bytes" >&2
  exit 1
fi

cp "$artifact_file" "$tmp_dir/reject_domainset.validate.mrs"
cat > "$tmp_dir/validate.yaml" <<'YAML'
mixed-port: 7890
mode: rule
log-level: silent
rule-providers:
  reject_domainset:
    type: file
    behavior: domain
    format: mrs
    path: ./reject_domainset.validate.mrs
rules:
  - RULE-SET,reject_domainset,REJECT
  - MATCH,DIRECT
YAML
"$mihomo_bin" -t -d "$tmp_dir" -f "$tmp_dir/validate.yaml"

source_sha256=$(sha256_file "$source_file")
artifact_sha256=$(sha256_file "$artifact_file")
mihomo_version=$("$mihomo_bin" -v | head -n 1)
generated_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')

mkdir -p "$output_dir"
changed=true
recorded_source_sha256=''
if [[ -f "$output_dir/reject_domainset.json" ]]; then
  recorded_source_sha256=$(jq -r '.source_sha256 // empty' "$output_dir/reject_domainset.json")
fi
if [[ -f "$output_dir/reject_domainset.mrs" ]] \
  && cmp -s "$artifact_file" "$output_dir/reject_domainset.mrs" \
  && [[ "$recorded_source_sha256" == "$source_sha256" ]]; then
  changed=false
fi

if [[ "$changed" == true ]]; then
  cp "$artifact_file" "$output_dir/reject_domainset.mrs"
  jq -n \
    --arg source_url "$source_url" \
    --arg source_sha256 "$source_sha256" \
    --arg artifact_sha256 "$artifact_sha256" \
    --arg mihomo_version "$mihomo_version" \
    --arg generated_at "$generated_at" \
    --argjson source_entries "$source_entries" \
    --argjson source_bytes "$source_bytes" \
    --argjson artifact_bytes "$artifact_bytes" \
    '{
      source_url: $source_url,
      source_sha256: $source_sha256,
      source_entries: $source_entries,
      source_bytes: $source_bytes,
      artifact_sha256: $artifact_sha256,
      artifact_bytes: $artifact_bytes,
      mihomo_version: $mihomo_version,
      generated_at: $generated_at
    }' > "$output_dir/reject_domainset.json"
  printf '%s  %s\n' "$artifact_sha256" 'reject_domainset.mrs' > "$output_dir/SHA256SUMS"
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'changed=%s\n' "$changed" >> "$GITHUB_OUTPUT"
fi

printf 'changed=%s entries=%s source_bytes=%s artifact_bytes=%s\n' \
  "$changed" "$source_entries" "$source_bytes" "$artifact_bytes"
