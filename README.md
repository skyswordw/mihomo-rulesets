# Mihomo Rulesets

[![Update MRS rulesets](https://github.com/skyswordw/mihomo-rulesets/actions/workflows/update-rulesets.yml/badge.svg)](https://github.com/skyswordw/mihomo-rulesets/actions/workflows/update-rulesets.yml)

Ready-to-use, reproducibly built `.mrs` rule providers for Mihomo. Keep the
upstream rule coverage, download smaller artifacts, and follow stable rolling
URLs that are checked every six hours.

为 Mihomo 提供可直接引用的 MRS 规则集：不删减上游规则，自动跟踪更新，并发布来源、体积与 SHA-256 元数据。

## Why use this repository?

- **Drop-in MRS providers:** use the published URLs directly in Mihomo or a
  Mihomo-based client.
- **No intentional rule reduction:** each artifact is converted from its
  declared text source without filtering or rewriting entries.
- **Guarded rolling updates:** a bad or unexpectedly truncated source does not
  replace the last working release.
- **Auditable output:** every artifact includes source provenance, entry and
  byte counts, converter version, and SHA-256 metadata.
- **Reproducible builds:** the workflow pins both the Mihomo version and its
  archive checksum, then verifies deterministic conversion.

In the **2026-08-05** metadata snapshot, source files total **3,067,910 bytes**;
the corresponding MRS artifacts total **1,202,340 bytes**, a **60.8%**
reduction in downloaded and stored rule data.

| Ruleset | Typical use | Behavior | Entries | Text source | MRS | Reduction |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| `reject_domainset` | Advertising and tracking rejection | `domain` | 115,929 | 2,670,525 B | 1,163,736 B | 56.4% |
| `china_ip` | Mainland China IPv4 routing | `ipcidr` | 21,818 | 346,387 B | 16,958 B | 95.1% |
| `download_domainset` | Download and update traffic | `domain` | 1,968 | 46,243 B | 20,059 B | 56.6% |
| `apple_cdn` | Apple CDN traffic | `domain` | 159 | 4,755 B | 1,587 B | 66.6% |

Check the rolling JSON metadata for current measurements after upstream
updates. Runtime memory savings vary with the Mihomo version, the rest of the
profile, rule hits, caches, and Go garbage collection; artifact size is not a
direct RSS estimate.

## Quick start

Copy the providers you need into a Mihomo profile:

```yaml
rule-providers:
  reject_domainset:
    type: http
    behavior: domain
    format: mrs
    url: https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/reject_domainset.mrs
    path: ./ruleset/reject_domainset.mrs
    interval: 21600

  china_ip:
    type: http
    behavior: ipcidr
    format: mrs
    url: https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/china_ip.mrs
    path: ./ruleset/china_ip.mrs
    interval: 21600

  download_domainset:
    type: http
    behavior: domain
    format: mrs
    url: https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/download_domainset.mrs
    path: ./ruleset/download_domainset.mrs
    interval: 21600

  apple_cdn:
    type: http
    behavior: domain
    format: mrs
    url: https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/apple_cdn.mrs
    path: ./ruleset/apple_cdn.mrs
    interval: 21600
```

Then reference them before broader fallback rules. Adapt the policies to your
own groups:

```yaml
rules:
  - RULE-SET,reject_domainset,REJECT
  - RULE-SET,apple_cdn,DIRECT
  - RULE-SET,download_domainset,DIRECT
  - RULE-SET,china_ip,DIRECT,no-resolve
  - MATCH,PROXY # Replace PROXY with an existing policy group.
```

If GitHub downloads must use a proxy, add `proxy: YOUR_PROXY_GROUP` to each
provider. The named group must already exist in your profile.

## Download links

| Artifact | Rolling MRS | Metadata |
| --- | --- | --- |
| `reject_domainset` | [Download](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/reject_domainset.mrs) | [JSON](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/reject_domainset.json) |
| `china_ip` | [Download](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/china_ip.mrs) | [JSON](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/china_ip.json) |
| `download_domainset` | [Download](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/download_domainset.mrs) | [JSON](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/download_domainset.json) |
| `apple_cdn` | [Download](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/apple_cdn.mrs) | [JSON](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/apple_cdn.json) |

Use the rolling URLs for automatic updates. For a deployment that must never
change without review, pin a repository commit instead:

```text
https://raw.githubusercontent.com/skyswordw/mihomo-rulesets/<commit>/rules/<ruleset>.mrs
```

## Compatibility

| Client or format | Support |
| --- | --- |
| Mihomo / Clash.Meta | Yes |
| Mihomo-based GUI clients | Yes, when their bundled core supports MRS |
| Original Dreamacro Clash | No |
| sing-box | No; use a native sing-box ruleset |
| Surge | No; use a native Surge ruleset |

MRS is a Mihomo-specific binary ruleset format. This repository does not try
to make the same artifact serve incompatible rule engines.

## Common issues

- **The provider does not load:** confirm that `format: mrs`, the declared
  `behavior`, and the local `.mrs` path all match the example. Do not reuse an
  old `.txt` cache path after switching formats.
- **GitHub is unreachable during startup:** route the provider download through
  an existing policy group with `proxy: YOUR_PROXY_GROUP`.
- **The client reports an unknown format:** update its Mihomo core. Original
  Clash, sing-box, and Surge cannot read MRS files.
- **RSS does not immediately fall:** verify that the active profile and local
  cache actually use MRS, then compare multiple samples after similar rule
  traffic. Go garbage collection can make one-time readings misleading.

## Verify a release

Download the four MRS files and `SHA256SUMS` into one directory, then run:

```bash
sha256sum --check SHA256SUMS
```

On macOS:

```bash
shasum -a 256 --check SHA256SUMS
```

The rolling release also publishes one JSON file per ruleset with the source
URL and SHA-256, entry count, source and artifact sizes, source-license status,
Mihomo version, and generation time.

## Update safety

GitHub Actions checks every source declared in `sources.json` every six hours.
Before publishing, the workflow requires all of the following:

1. The source exceeds its minimum entry and byte thresholds.
2. The downloaded Mihomo archive matches the pinned checksum.
3. Two conversions of the same source produce identical MRS files.
4. The artifact exceeds its expected minimum size.
5. Mihomo successfully loads the generated provider in a test configuration.

If any check fails, the existing rolling release remains available. If nothing
changed, the workflow creates no commit.

## Build locally

Use Mihomo 1.19.27 or another version you explicitly want to test:

```bash
MIHOMO_BIN=/path/to/mihomo ./scripts/update-rulesets.sh
```

The script reads `sources.json`, validates every source, writes artifacts and
metadata under `rules/`, and updates `rules/SHA256SUMS` only when needed.

To propose another ruleset, add a manifest entry with its behavior, source and
artifact formats, license status, and conservative size thresholds, then run
the same command locally before opening a pull request.

Compatibility reports and well-sourced ruleset proposals are welcome through
GitHub Issues and pull requests. Include the client name, Mihomo version, and a
minimal provider configuration when reporting a loading problem.

## Sources and licenses

Canonical source URLs, conversion behaviors, and declared licenses are tracked
in [`sources.json`](sources.json).

- The Sukkaw sources are generated by
  [`SukkaW/Surge`](https://github.com/SukkaW/Surge) under AGPL-3.0.
- `china_ip` follows the source used by the original Sub-Store profile. That
  source currently declares no license, so its metadata uses `NOASSERTION` and
  this repository grants no additional rights over that source data.
- The automation code in this repository is distributed under AGPL-3.0. See
  [`LICENSE`](LICENSE) and each metadata file for source-specific provenance.
