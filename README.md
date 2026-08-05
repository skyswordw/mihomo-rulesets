# Mihomo Rulesets

[![Update MRS rulesets](https://github.com/skyswordw/mihomo-rulesets/actions/workflows/update-rulesets.yml/badge.svg)](https://github.com/skyswordw/mihomo-rulesets/actions/workflows/update-rulesets.yml)

这里提供 4 份可直接用于 Mihomo 的 MRS 规则。转换时不删规则，每 6 小时自动检查上游更新。

## 规则

| 规则 | 用途 | 文本体积 | MRS 体积 |
| --- | --- | ---: | ---: |
| [`reject_domainset`](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/reject_domainset.mrs) | 广告和追踪域名 | 2,670,525 B | 1,163,736 B |
| [`china_ip`](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/china_ip.mrs) | 中国大陆 IPv4 | 346,387 B | 16,958 B |
| [`download_domainset`](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/download_domainset.mrs) | 下载和更新域名 | 46,243 B | 20,059 B |
| [`apple_cdn`](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/apple_cdn.mrs) | Apple CDN | 4,755 B | 1,587 B |

体积为 2026-08-05 的快照，四份文件合计约从 3.07 MB 降至 1.20 MB。最新体积、条目数、来源和 SHA-256 可在 [rolling release](https://github.com/skyswordw/mihomo-rulesets/releases/tag/rolling) 中查看。

## 使用

在 Mihomo 配置中加入 rule provider：

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

再把规则放到 `MATCH` 等兜底规则前：

```yaml
rules:
  - RULE-SET,reject_domainset,REJECT
  - MATCH,PROXY # 换成你已有的策略组
```

<details>
<summary>四份规则的 provider 配置</summary>

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

从文本规则切换时，需要同时修改 `format` 和本地文件后缀，避免继续读取旧缓存。GitHub 下载需要走代理时，可在 provider 中加入 `proxy: 策略组名`。

MRS 适用于 Mihomo / Clash.Meta。原版 Dreamacro Clash、sing-box 和 Surge 不支持此格式；图形客户端能否使用，取决于其内置内核。

## 更新

GitHub Actions 每 6 小时检查一次源文件。新文件通过条目数、体积、重复转换和 Mihomo 加载检查后才会发布；检查失败时继续保留上一版。

需要固定版本时，可将 URL 换成某次提交：

```text
https://raw.githubusercontent.com/skyswordw/mihomo-rulesets/<commit>/rules/<ruleset>.mrs
```

本地转换：

```bash
MIHOMO_BIN=/path/to/mihomo ./scripts/update-rulesets.sh
```

## 来源与许可证

源地址和转换方式见 [`sources.json`](sources.json)。Sukkaw 规则来自 [`SukkaW/Surge`](https://github.com/SukkaW/Surge)，许可证为 AGPL-3.0。

`china_ip` 的直接来源仓库未声明许可证，因此元数据标记为 `NOASSERTION`。本仓库的自动化代码采用 AGPL-3.0，见 [`LICENSE`](LICENSE)。
