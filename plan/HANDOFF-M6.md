# HANDOFF-M6：进入「发布」

> 上一棒：M5 处置建议与清单输出（2026-10-17 完成）。本文件是下一棒的**唯一入口**。
> 库内一律相对路径；用户侧启动命令用绝对路径指向本文件。
> **注意**：本轮未要求 commit，工作区保留全部变更（其中也包含 M1–M4 尚未提交的部分）。
>
> **M6 已执行完毕（2026-10-17）**：下方 §二 的六项待办全部完成，§五 的两项未勾选项已勾上并附证据。
> 发布事实（tag / Release 附件 / 校验和 / CI 四矩阵 / 干净 clone 复核 / 发布门自检）
> 一律以 **`plan/RELEASE-M6.md`** 为准；本文件只保留交接时的原始表述 + 完成状态。

## 一、当前进度与证据

### 已交付

| 交付物 | 位置 | 证据 |
| --- | --- | --- |
| SPDX 快照（3.29.0） | `references/spdx/` | 50 文件；`manifest.json` 记 sha256、`captured_on=2026-10-17` |
| curated 人工表 | `references/curated/` | `tiers.json` 48 条、`trove-map.json` 7 条、`scenario-triggers.json` 6 条、`conflict-pairs.json` 4 条、**`action-rules.json` 8 条 + 义务轴映射**、`trap-packages.json` 4 条 |
| 规则包 r0.1.0 | `references/ruleset/` | 6 份文件 + manifest；48/48 档位 + 6/6 触发 + 4/4 冲突对 + **8/8 处置规则**过锚点门，`disabled=0` |
| 七个生成器 | `tools/` | `fetch_spdx` / `gen_ruleset` / `gen_synthetic` / `gen_profile_truth` / `gen_scenario_truth` / `gen_conflict_truth` / **`gen_action_truth`**，`--check` 各两层 |
| M1 解析器 + `scan` | `src/licaudit/inventory/` | 六形态分派、四级可信度链、SPDX 表达式 |
| M2 画像引擎 | `src/licaudit/assess/profile.py` | 原子拆分、档位查表、OSI/FSF、条款锚点、待确认原因码 |
| M3 场景引擎 | `src/licaudit/assess/scenario.py` | 场景轴解析、`(delivery, link_mode)` 归一、触发查表、三态结论 |
| M4 冲突引擎 | `src/licaudit/assess/conflict.py` | 无向冲突对查表、依赖 × outbound 比较、表达式递归求值、覆盖度登记 |
| **M5 处置引擎** | `src/licaudit/assess/action.py` | **决策表查表分级（零条件分支）+ 五锚点门 + 确定性门 + 待确认投影** |
| **M5 报告层** | `src/licaudit/report/{sections,markdown,csv_render}.py` | **八章节结构（MD/CSV 同源）+ AST 三条零判定守门** |
| **`assess` 全量模式** | `pipeline.py`、`cli.py` | 产 `profile.json` + `scenario.json` + `conflicts.json` + **`actions.json`**；退出码四产物聚合 |
| **`report` 命令** | `pipeline.py`、`cli.py` | 读四份产物渲染 `license-report.md` / `.csv`；阻断级或待确认项 → exit 1 |
| **处置真值生成器** | `tools/gen_action_truth.py` | 由 curated 决策表 + 触发表直接推导；独立谓词匹配；`--check` 两层 |
| **处置真值** | `data/truth/actions.json` | 8 条决策规则 / 6 组可达义务轴 / **192 组确定输入 + 4 条四级样本** |
| **`bench --only m5`** | `src/licaudit/verify.py` | `verify_actions`：**196/196 命中** |
| **示例项目** | `data/synthetic/example-project/` | 六种清单形态、15 个依赖、全合成包名；进 `truth.json`（12 用例 / 59 记录） |
| **示例报告** | `examples/report/` | 两份运行 × (MD + CSV)；测试里重跑并**逐字节**比对 |
| 测试 | `tests/` | 双解释器 **467 passed, 0 skipped**（M5 新增 `test_action.py` 32 项、`test_report.py` 25 项） |
| 变异脚本 | `tools/_mutate_m5.py` | **13 组「弄坏 → 变红 → 恢复 → 变绿」**；`_mutate_m2/m3/m4` 复跑仍全绿 |

### M5 处置决策表（8 条，`references/curated/action-rules.json`）

表格**从上到下、先命中者生效**（顺序即优先级）；`obligation_axes` 把义务项映射成义务轴，
引擎不写任何义务项 / 档位 / 处置级别字面量。生成器另加两道门：**覆盖完备**（192 组确定输入零未覆盖）
与**无死规则**。

| 顺序 | rule_id | level | when | 依据锚点（可在 SPDX 全文逐字定位） |
| --- | --- | --- | --- | --- |
| 1 | `A-REPL-001` | replace_or_license | 轴含 `same-license` + 与 outbound 不相容 | GPL-2.0-only §6 |
| 2 | `A-REPL-002` | replace_or_license | 依赖间不兼容 + 链接方式 `none`/`static` | Apache-2.0 §3 |
| 3 | `A-DECL-001` | declare | 轴恰为 `{notice}` + 相容 + 无依赖间冲突 | MIT 条件段 |
| 4 | `A-ISOL-001` | isolate | 轴含 `source` + 无依赖间冲突 | LGPL-2.1-only §6(b) |
| 5 | `A-ISOL-002` | isolate | 轴含 `network-source` + 无依赖间冲突 | AGPL-3.0-only §13 |
| 6 | `A-ISOL-003` | isolate | 与 outbound 不相容 + 无依赖间冲突 | MPL-2.0 §3.3 |
| 7 | `A-ISOL-004` | isolate | 依赖间不兼容 + 链接方式 `dynamic`/`separate-process` | GPL-2.0-only §2 |
| 8 | `A-OK-001` | ok | 轴为空 + 相容 + 无依赖间冲突 | 0BSD 许可段 |

### 示例项目的两级实测（同一份清单、两种场景）

| 运行 | 参数 | 处置分布 | 提示 |
| --- | --- | --- | --- |
| 主示例 | `--scenario saas --network-interaction yes --outbound-license Elastic-2.0` | ok 8 / **declare 1** / isolate 0 / replace 4 / 待确认 2 | `examples/report/license-report.{md,csv}` |
| 分发示例 | `--scenario distribute-binary --outbound-license MIT` | ok 7 / declare 0 / **isolate 3** / replace 4 / 待确认 2 | `examples/report/license-report-distribute.{md,csv}` |

> **勘误（M6 实测）**：上表分发示例的 `ok 7` 测得为 **`ok 6`**（6 + 0 + 3 + 4 + 2 = 15 行）。
> 入仓示例报告（测试逐字节锁定）与 `plan/RELEASE-M6.md` §1.3 都是 `ok 6`，以实测为准。
> 另：示例项目 15 个依赖 = 13 个已归一化 + 2 个待确认（`scan` 摘要行只报 13 / 2 两项）。

**单场景下四级处置无法同时出现**（plan/06 §五有证明）：`declare` 需要「SaaS 场景 + 源可用档位 outbound」，
而那时档位级判定再也不会出现 `incompatible`；`replace_or_license` 只能靠依赖间不兼容对产生，
而那需要 `GPL-2.0-only` 在场，一旦 `AGPL-3.0-only` 也在场，`isolate` 的网络分支就轮不到。
两份运行合起来覆盖四级。

### 实测记录（当轮真跑）

```
py -3.8  -X utf8 -m pytest          → 467 passed（0 skipped）
py -3.12 -X utf8 -m pytest          → 467 passed（0 skipped）

PYTHONPATH=src py -3.12 -X utf8 -m licaudit --version → rc=0（licaudit 0.1.0）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit status    → rc=0
  启用条目: tiers 48 / obligations 8 / scenario-triggers 6 / conflict-pairs 4 / action-rules 8 / trove-map 7；被拒绝 0
PYTHONPATH=src py -3.12 -X utf8 -m licaudit selftest        → rc=0
PYTHONPATH=src py -3.12 -X utf8 -m licaudit selftest --core → rc=0
PYTHONPATH=src py -3.12 -X utf8 -m licaudit verify-data → rc=0（12 用例 / 59 记录 / F1 1.0）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m1 → rc=0（记录 59 / 命中 59 / F1 1.0）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m2 → rc=0（条目 52 / 命中 52）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m3 → rc=0（条目 231 / 命中 231）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m4 → rc=0（条目 16 / 命中 16）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m5 → rc=0（条目 196 / 命中 196）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench          → rc=0（m1 + m2 + m3 + m4 + m5）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m6 → rc=2（尚未实现，不装通过）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m9 → rc=2（未知套件）

# 端到端（示例项目六份清单一次扫描，摘要见括号）
licaudit scan <6 份清单> --out-dir out/e2e                              → rc=0（依赖 15 / 已归一化 15 / 待确认 2）
licaudit assess --inventory out/e2e/inventory.json --profile-only       → rc=0（原子 13 / 有档位 12 / 待确认 1）
licaudit assess ... --scenario saas --network-interaction yes \
  --outbound-license Elastic-2.0                                       → rc=1（ok 8 / declare 1 / replace 4 / 待确认 2）
licaudit assess ... --scenario saas ... --outbound-license pending     → rc=1（15 条全部待定）
licaudit assess ... --scenario static-link（未给 --delivery）           → rc=1（待确认，不是默认交付形态）
licaudit assess ... --scenario static-link --linking dynamic           → rc=2（场景与链接方式矛盾）
licaudit report --out-dir out/ex-saas --format md                      → rc=1（8 章节 / 15 行 / 待确认 7 条）
licaudit report --out-dir out/ex-saas --format csv                     → rc=1（同上）
licaudit report --out-dir out/empty --format md                        → rc=2（产物不存在，不写占位报告）
licaudit --rules-dir nope status                                       → rc=3（显式目录无效不回退）
licaudit --rules-dir nope report --out-dir out/ex-saas --format md     → rc=3（报告也先过规则包硬门）

py -3.12 -X utf8 tools/fetch_spdx.py --check --out references/spdx → rc=0
py -3.12 -X utf8 tools/gen_ruleset.py --check                      → rc=0
py -3.12 -X utf8 tools/gen_synthetic.py --check                    → rc=0
py -3.12 -X utf8 tools/gen_profile_truth.py --check                → rc=0
py -3.12 -X utf8 tools/gen_scenario_truth.py --check               → rc=0
py -3.12 -X utf8 tools/gen_conflict_truth.py --check               → rc=0
py -3.12 -X utf8 tools/gen_action_truth.py --check                 → rc=0
```

### 变异验证（实测，全部「弄坏 → 变红 → 恢复 → 变绿」）

`tools/_mutate_m5.py`（13 组）：

| # | 弄坏什么 | 变红的测试 |
| --- | --- | --- |
| 1 | 义务轴任一命中即算命中（义务轴形同虚设） | `test_permissive_dependency_without_obligations_is_ok` |
| 2 | 五锚点门不再要求声明位置（K20） | `test_pending_action_declares_which_anchor_is_missing`、`test_action_layer_alone_can_force_exit_one` |
| 3 | 版本未知不再降级 | `test_unknown_version_degrades_the_action` |
| 4 | 输入不确定时照给级别（K7/K14） | `test_unresolved_inputs_go_to_pending_not_to_ok` |
| 5 | 义务轴映射不可用时不禁用整张表（K4） | `test_unusable_obligation_axes_never_yield_ok`、`test_usable_rules_rejects_entries_with_undefined_axis` |
| 6 | 不校验 `when` 里的义务轴是否已定义 | `test_usable_rules_rejects_entries_with_undefined_axis` |
| 7 | 决策表改成「最后命中者生效」（顺序语义） | `test_first_matching_rule_wins` |
| 8 | 待确认项不再算阻断（§5.5） | `test_has_blocking_action_covers_levels_and_pending` |
| 9 | 退出码聚合漏掉处置层 | `test_action_layer_alone_can_force_exit_one` |
| 10 | `bench m5` 恒判通过 | `test_bench_m5_turns_red_when_truth_drifts` |
| 11 | 报告层内联档位名（AST 内联判定表守门） | `test_report_layer_has_no_inline_license_or_level_table` |
| 12 | 报告层 import 判定模块（AST import 守门） | `test_report_layer_does_not_import_judgement_modules` |
| 13 | 报告层非常量字符串拼接（AST BinOp 守门） | `test_report_layer_has_no_arithmetic_or_concatenation_binop` |

`tools/_mutate_m2.py`（9 组）、`_mutate_m3.py`（9 组）、`_mutate_m4.py`（12 组）复跑仍全绿。
**M5 新增了 `bench` 的 m5 分支**，因此按 suite 名定位的四份脚本都复跑过一遍（无锚点漂移）。

## 二、下一棒待办（M6 发布动作）

> **全部完成（2026-10-17）**。下面保留交接时的原始表述（作为任务口径的留档），
> 每项后面加一行实测结果；完整事实与命令见 `plan/RELEASE-M6.md`。

按 `plan/05-里程碑.md` §一 M6 行与 `plan/00` 的发布口径执行。M6 **不新增判定能力**，
只做「让交付物真的到得了用户手里」：

1. **脱敏自查**：全仓无绝对路径（除 `plan/HANDOFF-*.md` 里的用户侧启动命令）、无凭证、
   无其他项目名/模板引用；`data/synthetic/known-traps/` 是唯一含真实包名的目录，
   且已被 `test_synthetic_packages_are_whitelisted` / 示例报告断言隔离。
   → 实测（`tools/_scan_desensitize.py`，197 文件）：本仓路径/凭证/模板命中 **0**；
   邮箱本仓 8 / 上游 18，全部来自许可证原文与版权声明。见 `plan/RELEASE-M6.md` §1.4。
2. **`plan/RELEASE-M6.md` 必须在打 tag 之前入库**，内容为「tag 时点事实 / tag 后追加事实」两栏，
   禁止预填未发生的事实。
   → 已入库（提交 `5e7ad6f` 建档、`4f4951c` 补全 tag 时点事实；tag `v0.1.0` 指向后者），
   两栏齐备，tag 后只做追加提交。见 §1 / §2.7。
3. **CI 首推**：M1–M5 的配置已就绪（含七个生成器 `--check` 与 `bench --only m1..m5`），
   但**从未推送、从未运行**。首推后据实记录四矩阵结果；失败就是失败，照实写。
   → 首推成功：windows/ubuntu × 3.8/3.12 **四个 job 全 success**（run `39033849070`，
   提交 `5e7ad6f`），日志含 `selftest` / 七个 `--check` / `verify-data` / `bench m1–m5` 的实测输出。
   发布提交（`4f4951c`）另跑一次同样全绿，日志含 `467 passed`（run `39034225029`）。见 §1.5 / §2.2。
4. **干净 clone 复核**：在全新目录 `git clone` → `python -m venv` → `pip install -e ".[dev]"` →
   `pytest -q` → `licaudit verify-data` → `licaudit bench` → 端到端 `scan → assess → report`，
   记录命令与退出码（本机双解释器不算「干净环境」）。
   → 已按 tag `v0.1.0` 本体做完（不用 `PYTHONPATH`）：`467 passed`、`verify-data` rc=0、
   `bench` m1–m5 全绿、七个生成器 `--check` 7×rc=0、端到端四份报告与 tag 内
   `examples/report/` **逐字节相同**。逐条命令与退出码见 §2.5。
5. **tag + Release**：tag 与 `ruleset_version`/`licenseListVersion` 一起写进留档；
   Release 附件按 `plan/00` 的口径挂**真实产物**（不是「源码 zipball 即产物」）；
   下载回来核对 sha256。
   → tag `v0.1.0`（附注 tag）→ 提交 `4f4951c`；Release 挂 7 个附件（sdist 源码包、规则包与快照
   数据留档、示例报告 MD/CSV 各两份、`SHA256SUMS`）；**全部下载回来重算 sha256 与留档一致**。
   见 §2.1 / §2.3 / §2.4。
6. **口径复核**：`SKILL.md` / `README.md` 的「当前状态」与限制段必须与 tag 时点一致；
   `plan/00` 的状态表与承诺-证据台账同步翻转（M5 行已 ✅，M6 行待填）。
   → 已翻转：README / SKILL → 「M0–M6 已完成，本版为 `v0.1.0` 发布版」；
   `plan/00` 里程碑表 M6 行 ✅ + 台账新增发布三件套 / CI 四矩阵 / 源码包自足三行；
   `plan/05` 新增 §二之六 M6 DoD 明细（14 项）；`plan/06` §1.4 状态翻转 + 新增 D37。
   发布门 `tools/check_release.py`（离线 + `--online`）两条都是 rc=0，见 §2.6。

### M6 开工前必须知道的既有约束

- **四份产物 + 报告都是纯函数**：同输入双跑逐字节一致（测试锁）；发布附产物时用同一套命令重跑，
  不要手工编辑报告。
- **示例报告是「入仓即校验」**：`tests/test_report.py::test_example_reports_are_reproducible`
  会重跑 `scan → assess → report` 并与 `examples/report/` 逐字节比对；
  改了报告层或示例数据，必须重新生成这 4 个文件，否则测试红。
- **改 curated 必须重跑生成器**：`gen_ruleset.py` + 对应的 `gen_*_truth.py`
  （档位→画像真值；触发表→场景真值 + **处置真值**；冲突对→冲突真值；决策表→处置真值）。
  只改一处 `--check` 会红。
- **`bench m6` 是有意的「未实现」**：`BENCH_SUITES` 含 m6（发布里程碑无判定套件），
  `IMPLEMENTED_SUITES` 到 m5 为止；`--only m6` 必须继续报「尚未实现」exit 2，不要为了好看把它变成空套件通过。
- **报告层 AST 守门会拦住「顺手加个 `+`」**：`report/` 下只能用 `str.join` / `str.format`；
  字符串常量与 f-string 的拼接才豁免。
- **`report` 有阻断级时返回 1**：脚本里别用 `&&` 串联（本机实测踩过一次，链在第二步就断了）。

## 三、既定口径清单（动了会打挂测试）

完整 K 清单见 `plan/05-里程碑.md` §三。M6 直接相关的既有口径：

| 编号 | 口径 | 影响面 |
| --- | --- | --- |
| K18 | 处置四级：`ok` < `declare` < `isolate` < `replace_or_license`；分级只查 `action-rules.json`（表的书写顺序即优先级） | `assess/action.py` |
| K19 | 报告八章节顺序固定；MD 与 CSV 共用同一章节结构函数 | `report/sections.py` |
| K20 | 五锚点（包名/版本/声明位置/SPDX ID/依据条款）缺一 → 该条不进处置建议，进待确认项 | `assess/action.py` |
| K21 | 免责声明逐字输出，不得改写 | `contract.DISCLAIMER` |
| K22 | 退出码四语义：0 完成 / 1 检出阻断 / 2 用法或未知 ID / 3 规则包问题 | `exit_codes.py` |
| K23 | 报告层零判定：不 import 判定模块、无 `BinOp`、无内联判定表（另加：不读盘、不读时钟） | `tests/test_report.py` |
| K26 | 真值只存输入与期望；`observed_*` 即红 | 四份真值 + 测试 |
| K27 | 生成物 `--check` 两层 | 七个生成器 |
| K28 | 合成包名白名单 `example-pkg-*`（坑位用例除外） | 数据 + 测试 |
| K31 | 画像按原子 ID 出；未覆盖不猜档位 | M5 直接消费 |

### M5 新增/收紧的口径（已登记 plan/06）

| 编号 | 内容 |
| --- | --- |
| D35 | `actions.json` 由 `assess` 全量模式产出（第四份产物），`report` 只读产物不重算判定 |
| D36 | 处置分级查有序决策表（义务轴 + 冲突结论 + 依赖间冲突 + 链接方式）；「边界可分离」由 `link_mode` 维度承担，**传染范围聚合仍不实现** |
| P2 | CSV **无 BOM**（字节确定优先）；LF 行尾；列序 == `contract.REPORT_CSV_COLUMNS` |
| P5 | 示例项目 15 个依赖、六种清单形态（单场景四级无法同时出现 → 两份运行） |
| P6 | 不提供 `--json` 扁平输出（四份产物文件已可机读，避免第二套契约） |
| P7 | 传染范围聚合与档位级粗判的关系：M5 用决策表 `link_mode` 维度落地，聚合仍不做 |

## 四、本机环境坑（M1–M5 实测）

- **`py` 不是 `python`**（`python` 是商店占位符）。跑脚本一律 `py -3.12 -X utf8`。
- **本仓库未安装时用 `PYTHONPATH=src`**：`py -3.12 -m licaudit` 直接跑会 `No module named licaudit`。
- **多行 heredoc 写文件会被吞**：本机 Git Bash 对 `cat > file <<'PY'` 的收尾不稳，
  写脚本请用文件写入工具，或先写到临时文件再执行。
- **往 `python - <<'PY'` 里嵌含反斜杠的文本会被转义吃掉**：`\\` 到 Python 只剩一个，
  行尾反斜杠还会被当成续行。需要匹配含反斜杠的文本时，用文件编辑工具而不是 heredoc。
- **Git Bash 的 `/tmp/x` 与 Windows Python 的 `/tmp/x` 不是同一个路径**：
  shell 里 `rm -rf /tmp/out1` 有效，但 `py -3.12 -c "open('/tmp/out1/...')"` 会 `FileNotFoundError`。
  跨命令传产物路径时统一用仓库内相对路径（`out/...`）。
- **`report` 检出阻断级时返回 1**：`cmd1 && cmd2` 会在第二步断链，批量跑用 `for` 循环或分开执行。
- **改 curated 必须重跑生成器**：`gen_ruleset.py` 重写 manifest 哈希；触发表变更还要重跑
  `gen_scenario_truth.py` **与 `gen_action_truth.py`**（处置真值依赖触发表的可达义务轴），
  冲突对变更重跑 `gen_conflict_truth.py`，档位变更重跑 `gen_profile_truth.py`。
- **报告层 AST 守门会红**：`report/` 下出现 `+` 拼接、`.format()` 之外的计算、档位/级别名字面量都会失败
  —— 这是设计，不是误报；要用 `str.join` / `str.format`，标签从 `contract` 取。
- **`tests/test_conflict.py` 的合成清单必须带 `evidence.file`**：M5 起五锚点门要求声明位置可定位，
  缺 `file`/`locator` 会让全量模式 exit 1，从而掩盖 M4 要验的「全相容 → 0」。
- **变异脚本按文本片段定位，会随文件结构漂移**：新增里程碑后务必复跑四份脚本。
- **示例报告改了要重生成**：4 个文件由测试逐字节守门，不同步就红。
- **`references/spdx/` 是 2.8 MB 冻结数据**：`.gitattributes` 已标 `-text`，别让编辑器改行尾。
- **Windows 路径**：`os.path.relpath` 跨盘符会抛 `ValueError`；展示路径要兜底。
- **编码**：`encoding.ensure_utf8_stdio` 已按 `stream.encoding` 探针处理；CI 另设 `PYTHONUTF8=1`。

## 五、DoD 逐项 checklist（M5）

- [x] 分级只查决策表：假规则表 → 引擎跟着表走；表顺序即优先级；引擎无「义务项 → 处置」分支（K18）
- [x] 决策表覆盖完备 + 无死规则：192 组确定输入零未覆盖、零死规则（生成器门 + 真值断言）
- [x] 五锚点门：进处置建议的条目逐条五锚点非空；缺项进待确认并写明缺哪一项（K20）
- [x] 未知即待确认：场景/兼容性待定、义务轴映射不可用 → 绝不落 `ok`（K7）
- [x] 八章节顺序固定，MD 位置单调递增（K19）
- [x] MD 与 CSV 同源：CSV 行 == 逐包明细章节数据；列序 == `contract.REPORT_CSV_COLUMNS`
- [x] 免责声明逐字输出（K21）
- [x] 「证据锚点」章节固定引用中国司法参照（（2021）最高法知民终2063号）
- [x] CSV 无 BOM、LF 行尾（P2 关闭，逐字节断言）
- [x] 报告层三条 AST 守门 + 不读盘不读时钟；三条都能被变异弄红（K23）
- [x] 退出码：阻断级或待确认 → 1；仅 declare/ok → 0；处置层**单独**也能让全量模式 → 1（K22）
- [x] `outbound = pending` 的口径没被冲掉：全部待定 + exit 1
- [x] 真值是 curated 决策表的投影，生成器不 import 生产引擎，`--check` 位级一致
- [x] `bench --only m5` 196/196；未实现套件（`m6`）仍明确报错不装通过
- [x] 示例项目（15 依赖 / 六种清单形态）与两份示例报告入仓，测试里逐字节复现；四级处置全覆盖
- [x] 纯函数：报告双跑逐字节一致
- [x] 双解释器 **467 passed, 0 skipped**
- [x] 13 组变异验证（`tools/_mutate_m5.py`）+ 复跑 M2/M3/M4 各 9/9/12 组
- [x] D35/D36/P2/P5/P6/P7 已登记 `plan/06`；`plan/00/02/03/04/05` 与 SKILL/README/references/tools/data/examples/CI 已回写
- [x] **CI 首推**：配置已更新到 M5（七个生成器 `--check` + `bench --only m1..m5`），
      首推后四矩阵（windows/ubuntu × 3.8/3.12）**全绿**；据实补记在 `plan/RELEASE-M6.md` §1.5 / §2.2
- [x] **发布留档**：`plan/RELEASE-M6.md`（tag 前入库，两栏）、tag `v0.1.0`、
      Release 附 7 个真实产物且逐个下载回验 sha256、干净 clone 复核（tag 本体）—— 全部属 M6

## 六、关键命令速查

```bash
# 安装（干净环境）
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"

# 双解释器全量测试
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 py -3.8  -X utf8 -m pytest -q
PYTHONPATH=src PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest -q

# 生成器（数据刷新是人工步骤）
py -3.12 -X utf8 tools/fetch_spdx.py --out references/spdx
py -3.12 -X utf8 tools/gen_ruleset.py
py -3.12 -X utf8 tools/gen_synthetic.py
py -3.12 -X utf8 tools/gen_profile_truth.py
py -3.12 -X utf8 tools/gen_scenario_truth.py
py -3.12 -X utf8 tools/gen_conflict_truth.py
py -3.12 -X utf8 tools/gen_action_truth.py

# 生成物自检
py -3.12 -X utf8 tools/fetch_spdx.py --check --out references/spdx
py -3.12 -X utf8 tools/gen_ruleset.py --check
py -3.12 -X utf8 tools/gen_synthetic.py --check
py -3.12 -X utf8 tools/gen_profile_truth.py --check
py -3.12 -X utf8 tools/gen_scenario_truth.py --check
py -3.12 -X utf8 tools/gen_conflict_truth.py --check
py -3.12 -X utf8 tools/gen_action_truth.py --check

# 变异验证（一次性；会临时改源码再恢复）
py -3.12 -X utf8 tools/_mutate_m2.py
py -3.12 -X utf8 tools/_mutate_m3.py
py -3.12 -X utf8 tools/_mutate_m4.py
py -3.12 -X utf8 tools/_mutate_m5.py

# 交付态入口
licaudit status
licaudit selftest --core
licaudit scan data/synthetic/npm-basic/package.json --out-dir out
licaudit assess --inventory out/inventory.json --profile-only --out-dir out
licaudit assess --inventory out/inventory.json --scenario saas \
  --network-interaction yes --outbound-license MIT --scenario-note "用户原话" --out-dir out
licaudit assess --inventory out/inventory.json --scenario static-link \
  --delivery binary --outbound-license pending --scenario-note "分发 + 静态链接" --out-dir out
licaudit report --out-dir out --format md
licaudit report --out-dir out --format csv
licaudit verify-data
licaudit bench --only m1
licaudit bench --only m2
licaudit bench --only m3
licaudit bench --only m4
licaudit bench --only m5
licaudit bench

# 示例报告复现（两份运行；`report` 有阻断级 → rc=1，别用 && 串联）
EX=data/synthetic/example-project
licaudit scan $EX/package.json $EX/package-lock.json $EX/requirements.txt \
  $EX/pyproject.toml $EX/go.mod $EX/pom.xml --out-dir out/ex-saas
licaudit assess --inventory out/ex-saas/inventory.json --scenario saas \
  --network-interaction yes --outbound-license Elastic-2.0 \
  --scenario-note "示例项目以 SaaS 形式对外提供服务" --out-dir out/ex-saas
licaudit report --out-dir out/ex-saas --format md
licaudit report --out-dir out/ex-saas --format csv

# 未安装时（Skill 场景）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit report --out-dir out --format md
```

## 七、启动提示词（新对话用）

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M6.md" 继续完成任务
```
