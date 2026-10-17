# plan/RELEASE-M6：licaudit `v0.1.0` 发布留档

> **口径**（`plan/00-README总览.md` §四、`plan/05-里程碑.md` §一 M6 行）：
> 本文件必须在 **打 tag 之前**入库；tag 之后只允许**追加类**提交。
> 全文分两栏，**禁止预填未发生的事实**：
>
> | 栏目 | 只写什么 | 何时可写 |
> | --- | --- | --- |
> | §一「tag 时点事实」 | 打 tag 之前**已经发生、可当场复查**的事实 | tag 之前 |
> | §二「tag 后追加事实」 | 只有 tag / Release 产生**之后**才存在的事实 | tag 之后（追加提交） |
>
> 机器可读契约（`tools/check_release.py` 按此核对，`--online` 会真下载附件重算 sha256）：
> 两栏各有一块 ```release 键值块（后者覆盖前者），`sums` 围栏块登记附件校验和。
> 发布终态要求本文件**不含任何占位标记**——标记词表就是 `tools/check_release.py` 里的
> `PLACEHOLDERS`，本节刻意不把它们逐字抄进来（抄进来会被自己的门判红）。

## 一、tag 时点事实

### 1.1 版本与数据版本

| 项 | 值 | 来源（可当场复查） |
| --- | --- | --- |
| 包版本 | `0.1.0` | `pyproject.toml` 的 `version` |
| Skill 版本 | `0.1.0` | `SKILL.md` 前言 `metadata.version` |
| 本次发布采用的 tag 名 | `v0.1.0` | 本节机读块（tag 对象与指向的提交在 §二 登记） |
| 规则包版本 | `r0.1.0` | `references/ruleset/manifest.json` 的 `ruleset_version` |
| SPDX 许可清单版本 | `3.29.0` | 同上 `license_list_version`；快照采集日 `2026-10-17` |
| 仓库 | `https://github.com/yuluo554/10-17-license-compliance-skill` | 本次发布目标（公开，署名 D18） |

规则包启用条目（`licaudit status`，被拒绝 0）：`tiers` 48 / `obligations` 8 /
`scenario-triggers` 6 / `conflict-pairs` 4 / `action-rules` 8 / `trove-map` 7。

### 1.2 本地实测（2026-10-17，tag 之前）

双解释器（`PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1`）：

```bash
py -3.8  -X utf8 -m pytest -o addopts= -q   # 467 passed, 0 skipped
py -3.12 -X utf8 -m pytest -o addopts= -q   # 467 passed, 0 skipped
```

> 注：`pyproject.toml` 的 `addopts = "-q"` 会让 `-q` 变成 `-qq`（吞掉汇总行），
> 因此上面显式写了 `-o addopts=`。

交付态入口与基准（`PYTHONPATH=src py -3.12 -X utf8 -m licaudit ...`）：

| 命令 | 退出码 | 摘要 |
| --- | --- | --- |
| `--version` | 0 | `licaudit 0.1.0` |
| `status` | 0 | 启用条目 48/8/6/4/8/7；被拒绝 0 |
| `selftest` | 0 | 7 项 check 全 OK（含 `ruleset_loadable`） |
| `selftest --core` | 0 | 6 项纯内部不变量全 OK |
| `verify-data` | 0 | 用例 12 / 记录 59 / 命中 59；F1 1.0 |
| `bench --only m1` | 0 | 59/59；F1 1.0 |
| `bench --only m2` | 0 | 52/52 |
| `bench --only m3` | 0 | 231/231 |
| `bench --only m4` | 0 | 16/16 |
| `bench --only m5` | 0 | 196/196 |
| `bench`（无 `--only`） | 0 | m1+m2+m3+m4+m5 全绿 |
| `bench --only m6` | **2** | 「该基准套件尚未实现」——刻意不装通过 |
| `bench --only m9` | **2** | 「未知的基准套件」 |
| `--rules-dir nope status` | **3** | 显式目录无效不回退（D21） |
| `--rules-dir nope report ...` | **3** | 报告命令同样先过规则包硬门 |

七个生成器 `--check`（形态 + 重生成逐字节一致）全部 `rc=0`：
`fetch_spdx`（`--out references/spdx`）、`gen_ruleset`、`gen_synthetic`、
`gen_profile_truth`、`gen_scenario_truth`、`gen_conflict_truth`、`gen_action_truth`。

### 1.3 端到端实测（示例项目，六种清单形态）

`data/synthetic/example-project/`：13 个依赖 + 2 条待人工确认 = **15 行明细**。

| 命令 | 退出码 | 摘要 |
| --- | --- | --- |
| `scan`（6 份清单） | 0 | 依赖 13 / 已归一化 13 / 待确认 2 |
| `assess --profile-only` | 0 | 原子 13 / 有档位 12 / 待确认 1（`GPL-unknown`） |
| `assess --scenario saas --network-interaction yes --outbound-license Elastic-2.0` | **1** | 处置 15 条：`ok` 8 / `declare` 1 / `isolate` 0 / `replace_or_license` 4 / 待确认 2 |
| `assess --scenario distribute-binary --outbound-license MIT` | **1** | 处置 15 条：`ok` 6 / `declare` 0 / `isolate` 3 / `replace_or_license` 4 / 待确认 2 |
| `report --format md` / `--format csv`（两次运行各一次） | **1** | 四份产物与入仓 `examples/report/` **逐字节一致**（`diff` 无输出） |

两次运行合起来覆盖四级处置；单场景下四级无法同时出现（`plan/06` §五 有证明）。
`report` 因含阻断级项返回 1，属既定语义（K22），不是故障。

> **勘误**：`plan/HANDOFF-M6.md` §一「示例项目的两级实测」表里分发运行写的是
> `ok 7`，实测为 **`ok 6`**（6+0+3+4+2 = 15 行）。以本节与入仓示例报告为准。

### 1.4 脱敏自查（public 之前的硬门）

`tools/_scan_desensitize.py`（一次性脚本，不入发布面）按下列模式全仓扫描
（`git ls-files -co --exclude-standard`，192 个文件）：

| 模式 | 命中 |
| --- | --- |
| Windows 盘符绝对路径（`X:\` / `X:/`） | 0 |
| 正斜杠家目录（`/home/...`、`/Users/...`） | 0 |
| Git Bash 盘符路径（`/d/ProgramData/...`） | 0 |
| UNC 路径 | 0 |
| token 形态（`ghp_*` / `github_pat_*` / `sk-*`） | 0 |
| 私钥头（`-----BEGIN ... PRIVATE KEY-----`） | 0 |
| 赋值式口令 / 密钥（`password = "..."` 等） | 0 |
| 邮箱 | 24（**全部**来自上游许可证原文与 curated 引用：Apache-1.1/2.0 与 OpenSSL、PHP 的
  NOTICE 条款、Beerware / WTFPL 作者地址、`data/synthetic/known-traps/` 与
  `references/curated/trap-packages.json` 里 pandas 的 `license` 原文字段，以及
  SPDX `licenses.json` 的一条 seeAlso 链接） |
| 模板占位标记（脚手架残留：示例仓库名 / 通用占位词 / 未替换的项目名变量） | 0 |
| 其他项目名 / 模板引用（跨项目 skill、其他仓库名、其他厂商名） | 0 |

结论：**无绝对路径、无凭证、无跨项目引用**；唯一含真实包名的目录是
`data/synthetic/known-traps/`（K28 白名单例外），且被
`test_synthetic_packages_are_whitelisted` 与示例报告（全合成包名）隔离。

### 1.5 CI 首推

M1–M5 的 `.github/workflows/ci.yml` 已就位（四矩阵 windows/ubuntu × 3.8/3.12；
`PYTHONUTF8=1`；三步烟测 + 七个生成器 `--check` + `bench --only m1..m5`），
仓库在本里程碑之前**没有远端**，配置从未运行。首推结果见 §二 2.2。

### 1.6 发布形态与产物构成

- 发布形态：**源码包 / git clone + editable 安装**（D12；不承诺 wheel 安装后规则可用）。
- `MANIFEST.in` 是本次新增的发布件：把 `references/`（规则包 + SPDX 快照）、`data/`、
  `examples/`、`plan/`、`tools/`、`tests/`、`scripts/` 一起打进 sdist，
  使「源码包」这一形态**自足**（解包 → `pip install -e .` → `licaudit status` 可用）。
  一次性变异脚本（`tools/_mutate_m*.py`）与临时产物目录不入包。
- 产物本体与校验和见 §二 2.3（tag 之后才知道）。

```release
version: 0.1.0
tag: v0.1.0
repository: https://github.com/yuluo554/10-17-license-compliance-skill
ruleset_version: r0.1.0
license_list_version: 3.29.0
```

## 二、tag 后追加事实

> 本节只允许在 tag / Release 产生**之后**追加。tag 之前的提交里，下面各表填「待追加」。

### 2.1 tag 与 Release

| 项 | 值 |
| --- | --- |
| tag | `v0.1.0` |
| tag 类型 | 待追加 |
| tag 指向的提交 | 待追加 |
| 指向提交的提交信息 | 待追加 |
| 推送方式 | 待追加 |
| Release 地址 | 待追加 |
| Release 状态 | 待追加（必须非 draft、非 prerelease 判定留痕） |

```release
tag_commit: 待追加
release_url: 待追加
```

### 2.2 CI 四矩阵结果（首推）

| 矩阵 | 结果 |
| --- | --- |
| 待追加 | 待追加 |

### 2.3 附件与校验和（发布物本体）

| 附件 | 内容 | 字节 |
| --- | --- | --- |
| 待追加 | 待追加 | 待追加 |

```sums
```

### 2.4 下载回验（发布物本体真下载）

| 项 | 值 |
| --- | --- |
| 下载方式 | 待追加 |
| 逐个重算 sha256 | 待追加 |
| 与 §2.3 登记值比对 | 待追加 |

### 2.5 干净 clone 复核（tag 本体）

tag 存在之后才能在全新目录里 clone 出**发布物本体**来复核，因此本节属追加事实。

| 步骤 | 命令 | 退出码 / 摘要 |
| --- | --- | --- |
| 待追加 | 待追加 | 待追加 |

### 2.6 发布终态自检

```bash
py -3.12 -X utf8 tools/check_release.py            # 离线
py -3.12 -X utf8 tools/check_release.py --online   # 核对远端 tag / CI / Release 附件 / sha256
```

| 命令 | 退出码 | 摘要 |
| --- | --- | --- |
| 待追加 | 待追加 | 待追加 |
