# Mihomo Rulesets

[![Update MRS rulesets](https://github.com/skyswordw/mihomo-rulesets/actions/workflows/update-rulesets.yml/badge.svg)](https://github.com/skyswordw/mihomo-rulesets/actions/workflows/update-rulesets.yml)

最开始，我们只是想解决一个很具体的问题：Sparkle 里的 Mihomo 进程偶尔会从几十 MiB 涨到 200 多 MiB，而且很难降下来。

## 这事怎么来的

排查后发现，这次内存突增的主因是一份 2.67 MB 的广告文本规则。Mihomo 第一次用到它时，需要解析十多万条域名。删掉这份规则当然最省内存，但这部分广告拦截也跟着没了，不是我们想要的结果。

于是先拿 `reject_domainset` 做了个试验：规则一条不删，只把文本转换成 Mihomo 原生的 MRS 二进制格式。这个改法奏效了。接着我们又检查了其他规则，把能等价转换的 `china_ip`、`download_domainset` 和 `apple_cdn` 也放进来。

没有把所有规则硬转成 MRS。混合了多种语法的 `classical` 规则仍然保留文本格式，强行拆分会改变规则结构和顺序，省下的那点内存不值得冒这个险。

四份规则都换完、客户端刷新后，我们这套配置的短时 RSS 在 68–73 MiB 左右。换台机器、换份配置肯定不是同一个数字，但至少说明这次找对了方向。

## 现在有四份

| 规则 | 用来做什么 | 文本源 | MRS | 缩小 |
| --- | --- | ---: | ---: | ---: |
| [`reject_domainset`](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/reject_domainset.mrs) | 拦广告和追踪域名 | 2,670,525 B | 1,163,736 B | 56.4% |
| [`china_ip`](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/china_ip.mrs) | 匹配中国大陆 IPv4 | 346,387 B | 16,958 B | 95.1% |
| [`download_domainset`](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/download_domainset.mrs) | 匹配下载和更新域名 | 46,243 B | 20,059 B | 56.6% |
| [`apple_cdn`](https://github.com/skyswordw/mihomo-rulesets/releases/download/rolling/apple_cdn.mrs) | 匹配 Apple CDN | 4,755 B | 1,587 B | 66.6% |

上表是 2026-08-05 的快照。四份文件合计从约 3.07 MB 降到 1.20 MB，少了 60.8%。最新体积、条目数、来源和 SHA-256 都在 rolling release 的同名 JSON 里。

## 怎么用

把需要的 provider 放进 Mihomo 配置：

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

再把规则放到通用兜底规则前面：

```yaml
rules:
  - RULE-SET,reject_domainset,REJECT
  - MATCH,PROXY # 换成你已有的策略组
```

<details>
<summary>四份完整 provider 配置</summary>

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

从文本切换过来时，记得同时修改 `format` 和本地路径，不要让 MRS 继续复用旧的 `.txt` 缓存。如果 GitHub 需要走代理，可以在 provider 里加上 `proxy: 你的策略组名`。

MRS 只能给 Mihomo / Clash.Meta 使用。原版 Dreamacro Clash、sing-box 和 Surge 认不出这个格式；使用图形客户端时，是否支持取决于它内置的 Mihomo 版本。

## 更新不用手动盯

手工转换一次没什么意义，上游第二天更新，本地文件就落后了。

这个仓库每 6 小时检查一次源文件。每次更新都会确认文件没有异常缩水、两次转换结果一致，而且 Mihomo 能正常加载。全部通过后才更新 rolling release；中间任何一步出错，旧版本继续保留。源文件没变，也不会多提交一次。

想固定版本，不跟随 rolling 更新，可以锁定某次提交：

```text
https://raw.githubusercontent.com/skyswordw/mihomo-rulesets/<commit>/rules/<ruleset>.mrs
```

下载四份 MRS 和 `SHA256SUMS` 后，可以自己核对文件：

```bash
# Linux
sha256sum --check SHA256SUMS

# macOS
shasum -a 256 --check SHA256SUMS
```

本地重新生成只需要指定 Mihomo：

```bash
MIHOMO_BIN=/path/to/mihomo ./scripts/update-rulesets.sh
```

## 规则从哪来

具体源地址和转换方式写在 [`sources.json`](sources.json)。

Sukkaw 规则来自 [`SukkaW/Surge`](https://github.com/SukkaW/Surge)，许可证是 AGPL-3.0。`china_ip` 的直接来源仓库没有声明许可证，所以元数据标记为 `NOASSERTION`，本仓库也不替它授予额外权利。

自动化代码采用 AGPL-3.0，见 [`LICENSE`](LICENSE)。
