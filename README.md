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

`china_ip` 直接合并原 `Seameee/override-hub` 合并脚本使用的三个 IPv4 来源：

- `teishahbc/bgp-cn-ip` 的 `cn_as4134_as56040_ipv4.txt`
- `teishahbc/bgp-cn-ip` 的 `cn_other_asns_ipv4.txt`
- Sukka 的 `Clash/ip/china_ip.txt`

上游通过 [PR #5](https://github.com/Seameee/override-hub/pull/5) 在 2026-09-26 合并了删除旧合并文件及任务的改动。本仓库延续其逐行去空白、去注释、精确去重和排序的合并方式，不折叠网段、不替换为范围不同的单一来源。三个来源必须全部下载成功、非空且只含有效 IPv4 条目；任一失败都中止更新。元数据中的 `source_urls` 记录所有输入，`sources` 逐项记录来源、条目数、体积、许可证说明和 SHA-256，`source_sha256` 对应合并后的文本。多源合并需要 Python 3（仅使用标准库）。

Sukka 的这份 IPv4 数据文件声明 `CC BY-SA 2.0`；其余来源的许可证未能确定，因此合并产物元数据仍标记为 `NOASSERTION`，不代表替代各上游许可证。本仓库的自动化代码采用 AGPL-3.0，见 [`LICENSE`](LICENSE)。


## 更新保护与测试

`china_ip` 的三个输入分别至少包含 1,000 / 15,000 / 3,000 条和 15,000 / 250,000 / 40,000 字节；合并后仍须达到原有的 15,000 条、250,000 字节和 10,000 字节 MRS 门槛。这些是基于已有规模设定的安全下限，并非上游承诺。

更新还会验证上一版 MRS 的 SHA-256，解码其 IPv4 地址集合，并检查新集合的新增和移除地址数：任一超过上一版地址总数的 1% 都会中止，要求人工复核。按覆盖地址数计算，重叠网段不重复计数；不以原始行数替代覆盖检查。新 MRS 解码后的覆盖必须与合并文本完全相同。没有旧基准时也会中止，不会自行接受新基准。

所有来源和四份产物通过检查后才替换本地生成文件；失败时 GitHub Actions 不提交产物、不更新 rolling release，继续保留上一成功版。PR 的只读检查运行回归测试和真实下载/转换，不发布规则。若覆盖检查阻止了合理的大调整，请先检查各源变化和路由影响，再通过单独审阅的改动更新基准或阈值，不要设置自动备用源绕过检查。

离线回归测试：

```bash
python3 -m unittest discover -s tests -v
```
