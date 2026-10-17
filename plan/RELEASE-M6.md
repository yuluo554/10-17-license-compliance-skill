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
（`git ls-files -co --exclude-standard`，197 个文件）。表里的模式**不逐字抄写**
（抄进来会被扫描器命中，也算一种自证污染），要看字面量直接读脚本的 `PATTERNS`：

| 模式 | 命中 |
| --- | --- |
| 盘符绝对路径（单个盘符字母 + 冒号 + 反斜杠或正斜杠） | 0 |
| 类 Unix 家目录前缀路径 | 0 |
| Git Bash 的盘符路径写法 | 0 |
| UNC 路径 | 0 |
| token 形态（GitHub 的几种 token 前缀、`sk-` 打头的密钥串） | 0 |
| PEM 私钥头 | 0 |
| 赋值式口令 / 密钥字段 | 0 |
| 模板脚手架残留（全大写花括号占位 / 占位人名变量 / 脚手架提示词 / 尖括号全大写项目名） | 0 |
| 邮箱 | 本仓 8 / 上游 18（**全部**来自许可证原文与版权声明：`references/curated/tiers.json` 与
  `references/ruleset/tiers.json` 里 Apache-2.0 / OpenSSL / PHP 的 NOTICE 条款引用各 3 处，
  `data/synthetic/known-traps/pandas/package.json` 与 `references/curated/trap-packages.json`
  里 pandas 的 `license` 原文字段各 1 处；上游 18 处是 SPDX `texts/` 与 `licenses.json` 的原文内容） |
| 跨项目引用（其他仓库名 / 其他 skill 名 / 其他厂商名） | 0（另行 grep 复核，未固化进脚本以避免把别的项目名写进本仓） |

扫描面分两档：**本仓命中**须为 0（脚本退出码即此判定）；**上游冻结数据
（`references/spdx/`）**单独计数（18 处），全部是许可证原文里的反斜杠、人名与邮箱，
不是本仓引入的内容。

结论：**无绝对路径、无凭证、无跨项目引用**；唯一含真实包名的目录是
`data/synthetic/known-traps/`（K28 白名单例外），且被
`test_synthetic_packages_are_whitelisted` 与示例报告（全合成包名）隔离。

### 1.5 CI 首推（首推提交 = `5e7ad6f`）

`plan/HANDOFF-M6.md` 交接时仓库**没有远端**，CI 配置从未运行。本次首推后实测：

| 矩阵 | 结论 | 耗时（job 起止，UTC） |
| --- | --- | --- |
| `ubuntu-latest / py3.12` | success | 12:46:18 → 12:46:40 |
| `ubuntu-latest / py3.8` | success | 12:46:19 → 12:46:48 |
| `windows-latest / py3.12` | success | 12:46:18 → 12:46:58 |
| `windows-latest / py3.8` | success | 12:46:18 → 12:47:40 |

运行整体 `conclusion = success`（run `39033849070`，提交 `5e7ad6f`，2026-10-17）。

**四个 job 都真跑了断言，不是空壳绿**：日志里能看到每个矩阵各自的
`selftest` 6 项 `[OK]`、七个生成器 `--check` 的 8 行 `[OK]`（含逐字节一致）、
`verify-data` 的「命中 59 条」、以及 `bench` m1–m5 的
`59/59`、`52/52`、`231/231`、`16/16`、`196/196`。

两点如实记录：

- `actions/checkout@v4` 与 `actions/setup-python@v5` 在 runner 上触发
  「Node.js 20 已弃用」notice（actions 自身告警，非本仓库问题，不影响结论）；
  `ubuntu-latest` 另有一条「标签将于 2026-10-19 迁移到 Ubuntu 26」notice。
- CI 的 pytest 步骤写的是 `python -m pytest -q`，而 `pyproject.toml` 有
  `addopts = "-q"`，两者叠加成 `-qq` 会吞掉「467 passed」汇总行。
  本地已用 `-o addopts=` 复核（见 §1.2）；发布提交起 CI 步骤改为 `python -m pytest`
  （只保留 `addopts` 里的那一层 `-q`），让汇总行出现在日志里。

> `check_release.py` **刻意不进 CI**：它是**发布终态**门，发布之前必然因
> 「留档仍有未填项」而红（这是设计，见 §二 2.6 与 `tools/README.md`）。
> 把它挂进 CI 会让「tag 之前的正常提交」永远红，反而掩盖真问题。

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

> 本节只允许在 tag / Release 产生**之后**追加；本次追加发生在 tag `v0.1.0` 建成之后，
> 属「tag 之后只允许追加类提交」的允许范围（只加事实，不改 §一 的任何结论）。

### 2.1 tag 与 Release

| 项 | 值 |
| --- | --- |
| tag | `v0.1.0` |
| tag 类型 | 附注 tag（annotated）；tag 对象 `32a11be17ec38079ab5f7bf16192cc0f3083606d` |
| tag 指向的提交 | `4f4951c3dfe038a5c2b11e3cf95e2390d950e2cd` |
| 指向提交的提交信息 | `M6 发布提交：发布留档 + 状态翻转 + CI 首推实测` |
| 推送方式 | SSH（`git@github.com:yuluo554/10-17-license-compliance-skill.git`） |
| Release 地址 | <https://github.com/yuluo554/10-17-license-compliance-skill/releases/tag/v0.1.0> |
| Release 状态 | 已发布：`isDraft = false`、`isPrerelease = false`、`publishedAt = 2026-10-17T12:54:41Z` |
| 附件数 | 7（全部 `state = uploaded`） |

> **推送方式为何是 SSH**：本机到 `github.com:443` 的 HTTPS 连接不通（`gh api` 与
> `ssh -T git@github.com` 都正常，唯独 `git push` 走 HTTPS 时连不上），因此
> `origin` 改用 SSH。这是本机网络环境的事实，不影响仓库内容与公开性。

```release
tag_commit: 4f4951c3dfe038a5c2b11e3cf95e2390d950e2cd
release_url: https://github.com/yuluo554/10-17-license-compliance-skill/releases/tag/v0.1.0
```

### 2.2 发布提交（tag 指向的提交）的 CI 四矩阵结果

tag 指向哪个提交只有在 tag 之后才知道，因此本节属追加事实。

| 矩阵 | 结论 | 摘要（日志实测） |
| --- | --- | --- |
| `ubuntu-latest / py3.8` | success | `467 passed in 5.33s` |
| `ubuntu-latest / py3.12` | success | `467 passed in 2.96s` |
| `windows-latest / py3.8` | success | `467 passed in 5.90s` |
| `windows-latest / py3.12` | success | `467 passed in 6.83s` |

run `39034225029`（提交 `4f4951c`，2026-10-17），整体 `conclusion = success`，
四个 job 全 success。这一步同时验证了 §1.5 记的 CI 改动：pytest 汇总行现在出现在日志里。

### 2.3 附件与校验和（发布物本体）

| 附件 | 内容 | 字节 |
| --- | --- | --- |
| `licaudit-0.1.0.tar.gz` | sdist 源码包（自带 `references/` 规则包与 SPDX 快照） | 870853 |
| `licaudit-r0.1.0-data.tar.gz` | 规则包 `r0.1.0` + SPDX 3.29.0 快照 + curated 表 + 四份真值（129 条目） | 598201 |
| `license-report.md` | 示例中文清单（SaaS 运行） | 20240 |
| `license-report.csv` | 同上，机读版 | 5465 |
| `license-report-distribute.md` | 示例中文清单（分发二进制运行） | 21656 |
| `license-report-distribute.csv` | 同上，机读版 | 5901 |
| `SHA256SUMS` | 以上 6 项的 sha256 | 542 |

产物由 **tag 本体**生成：sdist 在 `git clone -b v0.1.0` 的干净检出上
`python -m build --sdist --no-isolation`；数据留档用 `git archive v0.1.0 references data`；
示例报告直接取自 tag 内的 `examples/report/`（测试逐字节守着）。
两份 tar 包内的冻结数据都与仓库字节一致（抽查 `references/spdx/manifest.json`、
`references/spdx/texts/GPL-3.0-only.json`、`references/spdx/licenses.json`、
`references/ruleset/manifest.json`、`references/curated/tiers.json`、`data/truth/actions.json`，
逐个 sha256 相等）。

```sums
aab14a19b749568f2523995d24cbabc3aeea764b4299412fbf4dd651ba9812ac  licaudit-0.1.0.tar.gz
47328cc42a493883d9977315c36593ae8fed692c65f38385c12220625121ff08  licaudit-r0.1.0-data.tar.gz
5a8a47da65d3a3329d8f136fdaf3867803091bde4a7b69b6bafb711b8a267bcf  license-report-distribute.csv
5815fe7e3b40bb08eab2677a04194d638808e6b2ae07d63be0000b015827a3c4  license-report-distribute.md
0c9f31b83f244e49bc2d7610d18bf129b4e9ae7c0f9a9ae398339c872e70080a  license-report.csv
6b652c2f6c74485d9a81bc722211d1efc222d478f5a10f9bdf10cb9eb81cb264  license-report.md
```

### 2.4 下载回验（发布物本体真下载）

| 项 | 值 |
| --- | --- |
| 下载方式 | `gh release download v0.1.0 --dir <临时目录>`（7 个附件全部取回） |
| 逐个重算 sha256 | 6 个登记附件的 sha256 **全部**与 §2.3 一致 |
| 与 §2.3 登记值比对 | 一致；额外只有一个 `SHA256SUMS` 本身（它不自哈希），下载回来的 `SHA256SUMS` 与本地生成的那份**逐字节相同** |

### 2.5 干净 clone 复核（tag 本体）

tag 存在之后才能在全新目录里 clone 出**发布物本体**来复核，因此本节属追加事实。
在仓库外全新目录 `git clone -b v0.1.0`（走公开远端）后，**不使用 `PYTHONPATH`**
（证明安装面而非源码面可用）：

| 步骤 | 命令 | 退出码 / 摘要 |
| --- | --- | --- |
| 建虚拟环境 | `py -3.12 -m venv .venv` | rc=0（Python 3.12.10） |
| 安装 | `.venv/Scripts/python.exe -m pip install -e ".[dev]"` | rc=0（`licaudit 0.1.0` + `pytest 8.4.2`） |
| 全量测试 | `.venv/Scripts/python.exe -m pytest -o addopts= -q` | rc=0，**467 passed** |
| 版本 | `.venv/Scripts/licaudit.exe --version` | rc=0，`licaudit 0.1.0` |
| 自检 | `.venv/Scripts/licaudit.exe selftest --core` | rc=0 |
| 真值对账 | `.venv/Scripts/licaudit.exe verify-data` | rc=0（12 用例 / 59 记录 / F1 1.0；规则包与真值均从 clone 内解析） |
| 基准 | `.venv/Scripts/licaudit.exe bench` | rc=0（m1 59/59、m2 52/52、m3 231/231、m4 16/16、m5 196/196） |
| 七个生成器 `--check` | `tools/{fetch_spdx,gen_ruleset,gen_synthetic,gen_profile_truth,gen_scenario_truth,gen_conflict_truth,gen_action_truth}.* --check` | 7 × rc=0（位级一致） |
| 端到端 `scan` | `.venv/Scripts/licaudit.exe scan <6 份清单> --out-dir out/saas` | rc=0（依赖 13 / 已归一化 13 / 待确认 2） |
| 端到端 `assess`（SaaS） | `--scenario saas --network-interaction yes --outbound-license Elastic-2.0` | rc=1（`ok` 8 / `declare` 1 / `isolate` 0 / `replace_or_license` 4 / 待确认 2） |
| 端到端 `assess`（分发） | `--scenario distribute-binary --outbound-license MIT` | rc=1（`ok` 6 / `declare` 0 / `isolate` 3 / `replace_or_license` 4 / 待确认 2） |
| 端到端 `report` × 4 | `--format md` / `--format csv`（两次运行各一次） | 4 × rc=1（含阻断级项，既定语义）；四份产物与 tag 内 `examples/report/` **逐字节相同** |
| sdist 自足性 | 解包 Release 附件 → `pip install -e .` → 从**解包目录之外**的 CWD 跑 `licaudit status` | rc=0，规则包从包内推导命中（`ruleset r0.1.0`，被拒绝 0）——D37 成立 |
| sdist 内自检 | 解包目录为 CWD：`verify-data` / `bench --only m5` / `scan` | 3 × rc=0 |

### 2.6 发布终态自检

```bash
py -3.12 -X utf8 tools/check_release.py            # 离线
py -3.12 -X utf8 tools/check_release.py --online   # 核对远端 tag / CI / Release 附件 / sha256
```

| 命令 | 退出码 | 摘要 |
| --- | --- | --- |
| `tools/check_release.py` | 0 | 留档两栏标题齐备且无未填标记；版本三方一致（`pyproject` / `SKILL` / tag）；规则包版本与留档一致；sdist 自足；README・SKILL・`plan/00` 状态已翻转；附件校验和可机读 |
| `tools/check_release.py --online` | 0 | 追加核对：仓库公开、tag 指向 `4f4951c`、该提交 CI 四 job 全 success、Release 非 draft、附件集合 == 登记的 6 个载荷 + `SHA256SUMS`、逐个附件**下载回来重算 sha256** 相符，且下载回来的 `SHA256SUMS` 恰好登记同一批载荷 |

### 2.7 发布后追加的修复（tag 之后发现，属追加事实）

**tag 内的 `tools/check_release.py` 有一处缺陷，已在本追加提交里修好，`v0.1.0` 的 tag 与 Release 未改动。**
如实记录，避免读者以为 tag 内那份工具与下面这版行为一致：

| 项 | 内容 |
| --- | --- |
| 现象 | tag 内那版 `check_release.py --online` 把远端附件集合（7 个）与 `sums` 块登记的载荷（6 个）直接比较，于是对**一次完全正常的发布**报 `[FAIL] Release 附件与留档登记不一致` |
| 根因 | 定契约时漏了 `SHA256SUMS` 这个「自身不进 `sums` 块」的伴随清单文件；且没有校验下载回来的 `SHA256SUMS` 是否恰好登记同一批载荷 |
| 影响面 | 只影响 `--online` 这一个模式；tag 内那版的**离线模式**结论正确。交付物本体（判定链、规则包、真值、示例报告、CLI）与 §2.1–§2.5 的全部事实不受影响 |
| 处置 | 在本追加提交里修正：远端附件集合判定改为「登记的载荷 + `SHA256SUMS`」，并追加「下载回来的 `SHA256SUMS` 必须恰好登记同一批载荷」这条检查。**未重打 tag、未重传附件**——已发布的 tag 与附件不重写，修正只出现在 `main` 上 |
| 读者须知 | 想用修好的发布门：用 `main`（或 `main` 之后的版本）里的 `tools/check_release.py`；`v0.1.0` 的 tag 内那份在 `--online` 下会误报 |

同一轮里还把两条**过松**的检查收紧了（它们不会误报，但会漏报，由 §2.8 的变异验证据暴露）：

- 栏目标题原先只查「全文里出现过这两个词」，正文提过一行就能满足 → 改为必须存在**标题行**；
- sdist 自足原先只查「`MANIFEST.in` 里有 `recursive-include references`」，把 `references` 的
  pattern 改成只剩 `*.md` 也能过 → 改为要求 `references` 与 `data` 的 pattern 都真的覆盖 `*.json`。

脱敏自查脚本也在这一轮改了（**结论不变**：无绝对路径、无凭证、无跨项目引用；改动是口径与噪声，
不是发现了新问题）：

| 改动 | 原因 |
| --- | --- |
| 邮箱模式排除 VCS 远端写法（`git@<主机>` 一类） | 记录推送方式时合法地写了一次 SSH 远端，被当成邮箱命中；那是 URL 不是地址 |
| 扫描面分「本仓」与「上游冻结数据（`references/spdx/`）」两档，退出码只看本仓 | 许可证原文里本来就有反斜杠、人名、邮箱；混在一起会掩盖真命中 |
| 模板类模式收窄为「不可能是正文」的形态 | 原先的宽口径会把 `${{ ... }}`（Actions 表达式）、Python 的 `{{` 转义、许可证原文里的措辞、XML 的 `<project>` 标签全判成占位 |
| §1.4 的模式清单不再逐字抄写字面量 | 抄进文档会被扫描器命中自己的说明；要看字面量直接读脚本 `PATTERNS` |

首版脚本还有一个更硬的毛病：写它时用了 shell heredoc，`UNC` 那条正则里的反斜杠被 shell 吞掉，
模式实际是坏的。已改用文件写入工具重写并复跑。**这也是 `plan/HANDOFF-M6.md` §四
「往 heredoc 里嵌含反斜杠的文本会被转义吃掉」那条坑的又一次现场复现。**

### 2.8 发布门变异验证（11 组）

`tools/_mutate_m6.py`（一次性脚本，不入发布面）对**发布态本身**做
「弄坏 → 变红 → 恢复 → 变绿」：8 组离线 + 3 组联网，全部通过。

| # | 弄坏什么 | 变红的检查 |
| --- | --- | --- |
| M1 | 留档少了「tag 后追加事实」标题行 | 栏目标题 |
| M2 | 留档里插入一个占位标记 | 无占位标记 |
| M3 | 校验和行截断成 40 位 | `sums` 行文法 |
| M4 | 留档登记的规则包版本与 manifest 不符 | 规则包版本一致 |
| M5 | `plan/00` 的 M6 行回退成 ⬜ | 状态已翻转 |
| M6 | `MANIFEST.in` 的 `references` 不再覆盖 `*.json` | sdist 自足 |
| M7 | 包版本与 `SKILL.md` 版本不一致 | 版本三方一致 |
| M8 | 留档 tag 与包版本不匹配 | tag ↔ 版本 |
| M9 | `tag_commit` 与远端 tag 指向不符 | 远端 tag 指向 |
| M10 | 登记的附件名远端不存在 | 远端附件集合 |
| M11 | 校验和是合法 sha256 但值不对 | 附件下载回验 |

> M1 与 M6 是第一次跑时**真的红了**的两组——门当时确实没在看那两个点。修完再跑才 11/11。
> 「发布门自己也要被证伪」这条要求，正因为会红才有意义。
