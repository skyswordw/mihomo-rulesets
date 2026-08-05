# Mihomo Rulesets

[![Update MRS rulesets](https://github.com/skyswordw/mihomo-rulesets/actions/workflows/update-rulesets.yml/badge.svg)](https://github.com/skyswordw/mihomo-rulesets/actions/workflows/update-rulesets.yml)

规则越来越多时，问题不只是配置文件变大。Mihomo 加载大型文本规则后，还要承担解析和内存开销。

在我们的 Sparkle / Mihomo 1.19.27 配置中，大型广告规则首次命中后，进程内存（RSS）曾超过 200 MiB。我们没有删减规则，而是把适合的规则转换成 Mihomo 原生的 MRS 二进制格式，并用自动化持续跟进上游。完成四份转换并刷新客户端后，短时 RSS 采样约为 68–73 MiB。

> 这是一次实际配置的优化结果，不是通用跑分。节点、策略组、流量、缓存和 Go GC 都会影响最终内存占用。

## 做了什么

- 保留上游规则覆盖，不过滤、不改写条目。
- 将广告域名、中国 IP、下载域名和 Apple CDN 四份规则统一转换为 MRS。
- 每 6 小时检查上游，有变化才提交并更新发布。
- 发布前检查源文件体积、条目数、转换确定性和 Mihomo 加载结果。
- 任一步失败都保留上一版 rolling release，不发布可疑产物。

2026-08-05 快照中，四份规则文件合计从约 3.07 MB 降至 1.20 MB，缩小约 **60.8%**。

| 规则 | 用途 | 文本源 | MRS | 缩小 |
| --- | --- | ---: | ---: | ---: |
| [`reject_domainset`](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/reject_domainset.mrs) | 广告与追踪域名 | 2,670,525 B | 1,163,736 B | 56.4% |
| [`china_ip`](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/china_ip.mrs) | 中国大陆 IPv4 | 346,387 B | 16,958 B | 95.1% |
| [`download_domainset`](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/download_domainset.mrs) | 下载与更新域名 | 46,243 B | 20,059 B | 56.6% |
| [`apple_cdn`](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/apple_cdn.mrs) | Apple CDN | 4,755 B | 1,587 B | 66.6% |

最新条目数、体积、来源和 SHA-256 见 rolling release 中的同名 JSON 元数据。

## 快速使用

在 Mihomo 配置中加入需要的 provider：

```yaml
rule-providers:
  reject_domainset:
    type: http
    behavior: domain
    format: mrs
    url: https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/reject_domainset.mrs
    path: ./ruleset/reject_domainset.mrs
    interval: 21600
```

再把规则放在通用兜底规则之前：

```yaml
rules:
  - RULE-SET,reject_domainset,REJECT
  - MATCH,PROXY # 请替换为已有策略组
```

<details>
<summary>展开四份完整 provider 配置</summary>

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

</details>

如果 GitHub 需要代理访问，可在 provider 中增加 `proxy: 已有策略组名`。切换格式时，`format` 和本地路径都要改成 `mrs`，不要继续复用旧 `.txt` 缓存路径。

## 兼容性

- 支持 Mihomo / Clash.Meta，以及使用兼容 Mihomo 内核的客户端。
- 不支持原版 Dreamacro Clash、sing-box 或 Surge，它们需要各自的规则格式。

## 更新与校验

rolling URL 适合自动更新：

```text
https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/<ruleset>.mrs
```

需要固定版本时，可锁定仓库提交：

```text
https://raw.githubusercontent.com/skyswordw/mihomo-rulesets/<commit>/rules/<ruleset>.mrs
```

下载四份 MRS 和 `SHA256SUMS` 后可验证：

```bash
# Linux
sha256sum --check SHA256SUMS

# macOS
shasum -a 256 --check SHA256SUMS
```

本地重新生成：

```bash
MIHOMO_BIN=/path/to/mihomo ./scripts/update-rulesets.sh
```

## 来源与许可证

源地址、转换类型和许可证状态记录在 [`sources.json`](sources.json)。

- Sukkaw 规则来自 [`SukkaW/Surge`](https://github.com/SukkaW/Surge)，许可证为 AGPL-3.0。
- `china_ip` 的直接来源仓库未声明许可证，因此元数据标记为 `NOASSERTION`，本仓库不额外授予其源数据权利。
- 本仓库的自动化代码采用 AGPL-3.0，详见 [`LICENSE`](LICENSE)。
