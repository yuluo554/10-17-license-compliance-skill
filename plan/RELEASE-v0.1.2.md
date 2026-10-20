# plan/RELEASE-v0.1.2：licaudit `v0.1.2` 发布留档

> 命名口径：里程碑 M0–M6 已收口（M6 是发布里程碑），之后的发布留档按**版本**命名
> （`plan/RELEASE-v<version>.md`），`tools/check_release.py` 也据此按包版本发现留档。
>
> 本文件在 tag **之前**入库，只写 tag 时点**已经成立**的事实；tag 对象 / tag 提交 /
> Release 附件 / 远端 CI 结果这些只有 tag 之后才知道的，登记在 §二（追加栏）。

```release
version: 0.1.2
tag: v0.1.2
repository: https://github.com/yuluo554/10-17-license-compliance-skill
ruleset_version: r0.1.0
license_list_version: 3.29.0
```

## 一、tag 时点事实

### 1.1 版本与数据版本

| 项 | 值 | 来源（可当场复查） |
| --- | --- | --- |
| 包版本 | `0.1.2` | `pyproject.toml` 的 `version` |
| 包内 `__version__` | `0.1.2` | `src/licaudit/__init__.py` |
| Skill 版本 | `0.1.2` | `SKILL.md` 前言 `metadata.version` |
| 本次发布采用的 tag 名 | `v0.1.2` | 本节机读块（tag 对象与指向的提交在 §二 登记） |
| 规则包版本 | `r0.1.0` | `references/ruleset/manifest.json` 的 `ruleset_version` |
| SPDX 许可清单版本 | `3.29.0` | 同上 `license_list_version`；快照采集日 `2026-10-17` |
| 发布形态 | wheel + sdist（两者都自带 `references/` 与 `data/`） | `pyproject.toml` 的 `package-data`；`MANIFEST.in` |
| 仓库 | `https://github.com/yuluo554/10-17-license-compliance-skill` | 本次发布目标（公开，署名 D18） |

规则包启用条目（`licaudit status`，被拒绝 0）：`tiers` 48 / `obligations` 8 /
`scenario-triggers` 6 / `conflict-pairs` 4 / `action-rules` 8 / `trove-map` 7。

本轮相对 `v0.1.1` 的差异是**发布形态与元数据**，判定面为零（见 §1.5）。

### 1.2 本地实测（2026-10-20，tag 之前）

全量测试（本机双通道；`pyproject.toml` 的 `addopts = "-q"` 会让 `-q` 变 `-qq` 吞掉汇总行，
故显式写 `-o addopts=`）：

```bash
py -3.12 -X utf8 -m pytest -o addopts= -q   # 457 passed, 0 skipped
py -3.8  -X utf8 -m pytest -o addopts= -q   # 457 passed, 0 skipped（3.8 已非承诺面，仅作回归对照）
```

交付态入口与基准（`py -3.12 -X utf8 -m licaudit ...`）：

| 命令 | 退出码 | 摘要 |
| --- | --- | --- |
| `--version` | 0 | `licaudit 0.1.2` |
| `status` | 0 | 启用条目 48/8/6/4/8/7；被拒绝 0 |
| `selftest` | 0 | 7 项 check 全 `[OK]`（含 `ruleset_loadable — ruleset=r0.1.0 ids=3.29.0 disabled=0`） |
| `selftest --core` | 0 | 6 项纯内部不变量全 `[OK]` |
| `verify-data` | 0 | 用例 12 / 记录 59 / 命中 59；F1 1.0 |
| `bench --only m1` | 0 | 59/59；F1 1.0 |
| `bench --only m2` | 0 | 52/52 |
| `bench --only m3` | 0 | 231/231 |
| `bench --only m4` | 0 | 16/16 |
| `bench --only m5` | 0 | 196/196 |
| `bench`（无 `--only`） | 0 | m1+m2+m3+m4+m5 全绿 |
| `bench --only m6` | **2** | 「该基准套件尚未实现」——刻意不装通过 |
| `bench --only m9` | **2** | 「未知的基准套件」 |

七个生成器 `--check`（形态 + 重生成逐字节一致）全部 `rc=0`：
`fetch_spdx`（`--check --out references/spdx`）、`gen_ruleset`、`gen_synthetic`、
`gen_profile_truth`、`gen_scenario_truth`、`gen_conflict_truth`、`gen_action_truth`。

脱敏自查（`py -3.12 -X utf8 tools/_scan_desensitize.py`）：扫描面 209 文件，命中 27 条，
**全部是既有命中**——18 条来自上游 SPDX 许可证原文（`references/spdx/`）、8 条来自上游
原文邮箱（curated 锚点与合成陷阱清单里逐字引用的上游联系地址）、1 条是本仓工作树里
未跟踪的诊断目录 `update/README.md` 写的绝对路径（`update/` 本轮已加入 `.gitignore`，
不入库）。本轮改动的文件**零命中**。

### 1.3 端到端（示例项目，两份运行）

`data/synthetic/example-project/`（六种清单形态 / 15 个依赖）跑 `scan → assess → report`：

| 运行 | 场景参数 | `scan` | `assess` | `report`（md / csv） |
| --- | --- | --- | --- | --- |
| `license-report` | `saas` + `--network-interaction yes` + outbound `Elastic-2.0` | 0 | 1（检出阻断级，既定语义） | 1 / 1（含阻断级，既定语义） |
| `license-report-distribute` | `distribute-binary` + outbound `MIT` | 0 | 1（同上） | 1 / 1（同上） |

与入仓示例报告的关系（`examples/report/`，测试逐字节比对）：

- 两份 `.csv`：**逐字节不变**（CSV 不含版本列）。
- 两份 `.md`：只差**一行**——报告概述区的「工具版本」由 `0.1.1` 变 `0.1.2`
  （把两份报告按 `s/0\.1\.[0-9]*/X/g` 归一化后逐字节相同，字节数也一致：20303 / 21719）。
  因此按 `plan/04` 的定义重新生成并入仓，**判定内容一行没变**。

### 1.4 构建与打包实测

| 检查 | 命令 | 结果 |
| --- | --- | --- |
| 构建无弃用警告 | `py -3.12 -m build --outdir <tmp>` | rc=0；输出里 `DeprecationWarning` **0 条**（只剩 setuptools 的 `no previously-included files` 提示） |
| wheel 构成 | 解 `licaudit-0.1.2-py3-none-any.whl` | 140 个文件条目：`licaudit/` 30 / `references/` 65 / `data/` 39 |
| wheel 元数据 | `*.dist-info/METADATA` | `Metadata-Version: 2.4`、`License-Expression: MIT`、`License-File: LICENSE`、`Requires-Python: >=3.12` |
| sdist 自足 | 解 `licaudit-0.1.2.tar.gz` | 含 `references/*.json` 64 条、`data/*.json` 16 条、`LICENSE`、`MANIFEST.in`、`plan/*.md` |
| 干净 venv 装 wheel | `py -3.12 -m venv` + `pip install <wheel>` | `licaudit status` rc=0（规则包从 `site-packages/references/ruleset` 解析）；`licaudit selftest` rc=0；`--version` 输出 `licaudit 0.1.2` |

### 1.5 本轮改变了什么（判定面为零）

- `src/licaudit/` 只改了 `__init__.py` 的 `__version__` 字符串；判定链（`inventory` /
  `assess` / `report` / `ruleset`）一行未改。
- 规则包 `references/ruleset/`、SPDX 快照 `references/spdx/`、curated 表与 `data/truth/`
  的字节未动（七个生成器 `--check` 全绿即逐字节证明）。
- `pyproject.toml`：`license` 改 PEP 639 形式 + `license-files`、`build-system` 抬到
  `setuptools>=77`、`requires-python` 3.8 → **3.12**、classifiers 同步（口径见 `plan/06` D39）。
- `.github/workflows/ci.yml`：`actions/checkout@v7` / `actions/setup-python@v7`；
  矩阵由 `windows/ubuntu × 3.8/3.12`（4 job）收为 `windows/ubuntu × 3.12`（**2 job**）。
- `tools/check_release.py`：发布留档不再写死 `plan/RELEASE-M6.md`，改为按包版本匹配
  `plan/RELEASE-*.md` 的 `tag` 字段。
- 文档事实修正：`SKILL.md`（版本号 / 限制段 / 当前实现状态）、`README.md`（徽章 / 安装要求 /
  当前版本段）、`DEVELOPMENT.md`（CI 矩阵）、`plan/00`·`plan/02`·`plan/05`·`plan/06`。
- **明确不改**：`plan/05` §二之一–六、`plan/RELEASE-M6.md`、`plan/HANDOFF-M1..M6` 里的历史
  数字（467 / 四矩阵 / 3.8 通道）按「里程碑时点实测」保留。

### 1.6 发布形态与产物构成

- 两种形态都自足：`pip install licaudit`（wheel）与解 sdist + `pip install -e .` 都能直接
  `licaudit status`（D38 起规则包与真值随包）。
- 附件按 `plan/00` 的口径挂**真实产物**：`licaudit-0.1.2-py3-none-any.whl`、
  `licaudit-0.1.2.tar.gz`，外加伴随清单 **`SHA256SUMS`**（无扩展名）。
- 伴随清单命名的口径：`tools/check_release.py` 的 `SUMS_FILE = "SHA256SUMS"`，`--online`
  要求「远端附件集合 == 登记的载荷 + `SHA256SUMS`」。`v0.1.1` 的 Release 用的是
  `SHA256SUMS.txt`，与该契约不符（本轮改名对齐，不改动已发布的 `v0.1.1` 附件）。
- 校验和的权威登记处是 §二 与 Release 附件 `SHA256SUMS`：本留档与 `CHANGELOG.md` 都随 sdist
  一起分发，产物里不可能写下自身的 sha256（自指）。