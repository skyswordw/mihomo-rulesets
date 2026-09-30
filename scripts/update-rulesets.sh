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

for command_name in curl jq awk cmp sort python3; do
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
staged_dir="$tmp_dir/staged"
mkdir -p "$staged_dir"
# Keep last-known-good files untouched until every source and artifact passes.
cp -a "$output_dir/." "$staged_dir/"
changed=false
ruleset_count=0
ruleset_names_file="$tmp_dir/ruleset-names.txt"
: > "$ruleset_names_file"

jq -e '
  type == "object" and length > 0 and
  all(to_entries[];
    (.key | test("^[a-z0-9_]+$")) and
    (
      (.value | has("source_url") and (has("sources") | not)) and
      (.value.source_url | type == "string" and startswith("https://"))
      or
      (.value | has("sources") and (has("source_url") | not)) and
      (.value.behavior == "ipcidr") and
      (.value.sources | type == "array" and length > 0 and
        all(.[];
          (.url | type == "string" and startswith("https://")) and
          (.minimum_entries | type == "number" and . > 0 and . <= 2147483647 and . == floor) and
          (.minimum_source_bytes | type == "number" and . > 0 and . <= 2147483647 and . == floor) and
          (.source_license | type == "string" and length > 0))) and
      (.value.max_address_change_fraction | type == "number" and . >= 0 and . <= 1)
    ) and
    (.value.behavior == "domain" or .value.behavior == "ipcidr") and
    (.value.input_format == "text") and
    (.value.output_format == "mrs") and
    (.value.source_license | type == "string" and length > 0) and
    (.value.minimum_entries | type == "number" and . > 0 and . <= 2147483647 and . == floor) and
    (.value.minimum_source_bytes | type == "number" and . > 0 and . <= 2147483647 and . == floor) and
    (.value.minimum_artifact_bytes | type == "number" and . > 0 and . <= 2147483647 and . == floor)
  )
' "$manifest" >/dev/null

while IFS=$'\t' read -r name source_urls behavior input_format output_format \
  source_license minimum_entries minimum_source_bytes minimum_artifact_bytes; do
  ruleset_count=$((ruleset_count + 1))
  printf '%s\n' "$name" >> "$ruleset_names_file"

  source_file="$tmp_dir/$name.$input_format"
  artifact_file="$tmp_dir/$name.$output_format"
  artifact_check="$tmp_dir/$name.check.$output_format"

  source_details="$tmp_dir/$name.sources.json"
  coverage_details="$tmp_dir/$name.coverage.json"
  printf 'null\n' > "$source_details"
  printf 'null\n' > "$coverage_details"
  source_files=()
  while IFS= read -r source_url; do
    download_file="$tmp_dir/$name.source.${#source_files[@]}"
    echo "Fetching $name: $source_url"
    if ! curl \
      --fail \
      --location \
      --silent \
      --show-error \
      --retry 3 \
      --retry-all-errors \
      --connect-timeout 15 \
      --max-time 120 \
      "$source_url" \
      --output "$download_file"; then
      echo "$name source download failed: $source_url" >&2
      exit 1
    fi
    source_files+=("$download_file")
  done < <(jq -r '.[]' <<< "$source_urls")

  if jq -e --arg name "$name" '.[$name] | has("sources")' "$manifest" >/dev/null; then
    python3 "$repo_root/scripts/merge-ipv4.py" merge \
      --sources-json "$(jq -c --arg name "$name" '.[$name].sources' "$manifest")" \
      --metadata "$source_details" "${source_files[@]}" > "$source_file"
    # Decode the checked-in previous successful artifact: no remote fallback or
    # bootstrapping to an unreviewed baseline if this evidence is missing.
    baseline_artifact="$output_dir/$name.$output_format"
    expected_baseline_sha=$(jq -er '.artifact_sha256' "$output_dir/$name.json")
    if [[ "$(sha256_file "$baseline_artifact")" != "$expected_baseline_sha" ]]; then
      echo "$name previous artifact checksum mismatch" >&2
      exit 1
    fi
    baseline_text="$tmp_dir/$name.previous.txt"
    "$mihomo_bin" convert-ruleset ipcidr mrs "$baseline_artifact" "$baseline_text"
    python3 "$repo_root/scripts/merge-ipv4.py" coverage \
      --previous "$baseline_text" --current "$source_file" \
      --max-change-fraction "$(jq -r --arg name "$name" '.[$name].max_address_change_fraction' "$manifest")" \
      > "$coverage_details"
    echo "$name coverage: $(cat "$coverage_details")"
  else
    cp "${source_files[0]}" "$source_file"
  fi

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

  if [[ "$(cat "$source_details")" != null ]]; then
    roundtrip_text="$tmp_dir/$name.roundtrip.txt"
    "$mihomo_bin" convert-ruleset ipcidr mrs "$artifact_file" "$roundtrip_text"
    python3 "$repo_root/scripts/merge-ipv4.py" coverage \
      --previous "$source_file" --current "$roundtrip_text" --max-change-fraction 0 >/dev/null
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
  recorded_source_details='null'
  recorded_source_urls=''
  recorded_source_sha256=''
  recorded_behavior=''
  recorded_input_format=''
  recorded_output_format=''
  recorded_source_license=''
  recorded_mihomo_version=''
  if [[ -f "$output_dir/$name.json" ]]; then
    recorded_source_details=$(jq -c '.sources // null' "$output_dir/$name.json")
    recorded_source_urls=$(jq -c '.source_urls // [.source_url]' "$output_dir/$name.json")
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
    && [[ "$recorded_source_details" == "$(jq -c . "$source_details")" ]] \
    && [[ "$recorded_source_urls" == "$source_urls" ]] \
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
    cp "$artifact_file" "$staged_dir/$name.$output_format"
    jq -n \
      --argjson source_urls "$source_urls" \
      --slurpfile sources "$source_details" \
      --slurpfile coverage "$coverage_details" \
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
      } + (if $sources[0] == null then
        {source_url: $source_urls[0]}
      else
        {source_urls: $source_urls, sources: $sources[0], coverage: $coverage[0]}
      end)' > "$staged_dir/$name.json"
    changed=true
  fi

  printf '%s changed=%s entries=%s source_bytes=%s artifact_bytes=%s\n' \
    "$name" "$ruleset_changed" "$source_entries" "$source_bytes" "$artifact_bytes"
done < <(jq -r '
  to_entries[] |
  [
    .key,
    ((if .value.sources then [.value.sources[].url] else [.value.source_url] end) | tojson),
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
  artifact_path="$staged_dir/$name.$output_format"
  if [[ ! -f "$artifact_path" ]]; then
    echo "Expected artifact is missing: $artifact_path" >&2
    exit 1
  fi
  printf '%s  %s\n' "$(sha256_file "$artifact_path")" "$(basename "$artifact_path")" \
    >> "$checksums_file"
done < <(sort "$ruleset_names_file")

if [[ ! -f "$output_dir/SHA256SUMS" ]] || ! cmp -s "$checksums_file" "$output_dir/SHA256SUMS"; then
  cp "$checksums_file" "$staged_dir/SHA256SUMS"
  changed=true
fi

if [[ "$changed" == true ]]; then
  cp "$staged_dir/"* "$output_dir/"
fi

if [[ -n "${GITHUB_OUTPUT:-}" ]]; then
  printf 'changed=%s\n' "$changed" >> "$GITHUB_OUTPUT"
fi

printf 'changed=%s rulesets=%s\n' "$changed" "$ruleset_count"
