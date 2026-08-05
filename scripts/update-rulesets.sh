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

for command_name in curl jq awk cmp sort; do
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

mihomo_version=$("$mihomo_bin" -v | head -n 1)
mkdir -p "$output_dir"
changed=true
changed=false
ruleset_count=0
ruleset_names_file="$tmp_dir/ruleset-names.txt"
: > "$ruleset_names_file"

jq -e '
  type == "object" and length > 0 and
  all(to_entries[];
    (.key | test("^[a-z0-9_]+$")) and
    (.value.source_url | type == "string" and length > 0) and
    (.value.behavior == "domain" or .value.behavior == "ipcidr") and
    (.value.input_format == "text") and
    (.value.output_format == "mrs") and
    (.value.source_license | type == "string" and length > 0) and
    (.value.minimum_entries | type == "number" and . > 0) and
    (.value.minimum_source_bytes | type == "number" and . > 0) and
    (.value.minimum_artifact_bytes | type == "number" and . > 0)
  )
' "$manifest" >/dev/null

while IFS=$'\t' read -r name source_url behavior input_format output_format \
  source_license minimum_entries minimum_source_bytes minimum_artifact_bytes; do
  ruleset_count=$((ruleset_count + 1))
  printf '%s\n' "$name" >> "$ruleset_names_file"

  source_file="$tmp_dir/$name.$input_format"
  artifact_file="$tmp_dir/$name.$output_format"
  artifact_check="$tmp_dir/$name.check.$output_format"

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
    echo "$name source is unexpectedly small: $source_bytes bytes" >&2
    exit 1
  fi
  if (( source_entries < minimum_entries )); then
    echo "$name source has too few entries: $source_entries" >&2
    exit 1
  fi

  "$mihomo_bin" convert-ruleset "$behavior" "$input_format" "$source_file" "$artifact_file"
  "$mihomo_bin" convert-ruleset "$behavior" "$input_format" "$source_file" "$artifact_check"

  if ! cmp -s "$artifact_file" "$artifact_check"; then
    echo "$name Mihomo conversion is not deterministic" >&2
    exit 1
  fi

  artifact_bytes=$(wc -c < "$artifact_file" | tr -d ' ')
  if (( artifact_bytes < minimum_artifact_bytes )); then
    echo "$name artifact is unexpectedly small: $artifact_bytes bytes" >&2
    exit 1
  fi

  validate_artifact="$tmp_dir/$name.validate.$output_format"
  validate_config="$tmp_dir/$name.validate.json"
  cp "$artifact_file" "$validate_artifact"
  jq -n \
    --arg name "$name" \
    --arg behavior "$behavior" \
    --arg path "./$(basename "$validate_artifact")" \
    '{
      "mixed-port": 7890,
      mode: "rule",
      "log-level": "silent",
      "rule-providers": {
        ($name): {
          type: "file",
          behavior: $behavior,
          format: "mrs",
          path: $path
        }
      },
      rules: [
        ("RULE-SET," + $name + ",REJECT"),
        "MATCH,DIRECT"
      ]
    }' > "$validate_config"
  "$mihomo_bin" -t -d "$tmp_dir" -f "$validate_config"

  source_sha256=$(sha256_file "$source_file")
  artifact_sha256=$(sha256_file "$artifact_file")
  recorded_source_sha256=''
  recorded_behavior=''
  recorded_input_format=''
  recorded_output_format=''
  recorded_source_license=''
  recorded_mihomo_version=''
  if [[ -f "$output_dir/$name.json" ]]; then
    recorded_source_sha256=$(jq -r '.source_sha256 // empty' "$output_dir/$name.json")
    recorded_behavior=$(jq -r '.behavior // empty' "$output_dir/$name.json")
    recorded_input_format=$(jq -r '.input_format // empty' "$output_dir/$name.json")
    recorded_output_format=$(jq -r '.output_format // empty' "$output_dir/$name.json")
    recorded_source_license=$(jq -r '.source_license // empty' "$output_dir/$name.json")
    recorded_mihomo_version=$(jq -r '.mihomo_version // empty' "$output_dir/$name.json")
  fi

  ruleset_changed=true
  if [[ -f "$output_dir/$name.$output_format" ]] \
    && cmp -s "$artifact_file" "$output_dir/$name.$output_format" \
    && [[ "$recorded_source_sha256" == "$source_sha256" ]] \
    && [[ "$recorded_behavior" == "$behavior" ]] \
    && [[ "$recorded_input_format" == "$input_format" ]] \
    && [[ "$recorded_output_format" == "$output_format" ]] \
    && [[ "$recorded_source_license" == "$source_license" ]] \
    && [[ "$recorded_mihomo_version" == "$mihomo_version" ]]; then
    ruleset_changed=false
  fi

  if [[ "$ruleset_changed" == true ]]; then
    generated_at=$(date -u +'%Y-%m-%dT%H:%M:%SZ')
    cp "$artifact_file" "$output_dir/$name.$output_format"
    jq -n \
      --arg source_url "$source_url" \
      --arg behavior "$behavior" \
      --arg input_format "$input_format" \
      --arg output_format "$output_format" \
      --arg source_license "$source_license" \
      --arg source_sha256 "$source_sha256" \
      --arg artifact_sha256 "$artifact_sha256" \
      --arg mihomo_version "$mihomo_version" \
      --arg generated_at "$generated_at" \
      --argjson source_entries "$source_entries" \
      --argjson source_bytes "$source_bytes" \
      --argjson artifact_bytes "$artifact_bytes" \
      '{
        source_url: $source_url,
        behavior: $behavior,
        input_format: $input_format,
        output_format: $output_format,
        source_license: $source_license,
        source_sha256: $source_sha256,
        source_entries: $source_entries,
        source_bytes: $source_bytes,
        artifact_sha256: $artifact_sha256,
        artifact_bytes: $artifact_bytes,
        mihomo_version: $mihomo_version,
        generated_at: $generated_at
      }' > "$output_dir/$name.json"
    changed=true
  fi

  printf '%s changed=%s entries=%s source_bytes=%s artifact_bytes=%s\n' \
    "$name" "$ruleset_changed" "$source_entries" "$source_bytes" "$artifact_bytes"
done < <(jq -r '
  to_entries[] |
  [
    .key,
    .value.source_url,
    .value.behavior,
    .value.input_format,
    .value.output_format,
    .value.source_license,
    .value.minimum_entries,
    .value.minimum_source_bytes,
    .value.minimum_artifact_bytes
  ] | @tsv
' "$manifest")

if (( ruleset_count == 0 )); then
  echo "No rulesets are declared in $manifest" >&2
  exit 1
fi

checksums_file="$tmp_dir/SHA256SUMS"
: > "$checksums_file"
while IFS= read -r name; do
  output_format=$(jq -er --arg name "$name" '.[$name].output_format' "$manifest")
  artifact_path="$output_dir/$name.$output_format"
  if [[ ! -f "$artifact_path" ]]; then
    echo "Expected artifact is missing: $artifact_path" >&2
    exit 1
  fi
  printf '%s  %s\n' "$(sha256_file "$artifact_path")" "$(basename "$artifact_path")" \
    >> "$checksums_file"
done < <(sort "$ruleset_names_file")

if [[ ! -f "$output_dir/SHA256SUMS" ]] || ! cmp -s "$checksums_file" "$output_dir/SHA256SUMS"; then
  cp "$checksums_file" "$output_dir/SHA256SUMS"
  changed=true
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'changed=%s\n' "$changed" >> "$GITHUB_OUTPUT"
fi

printf 'changed=%s rulesets=%s\n' "$changed" "$ruleset_count"
