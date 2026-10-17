# HANDOFF-M5：进入「处置建议与清单输出」

> 上一棒：M4 冲突与兼容性分析（2026-10-17 完成）。本文件是下一棒的**唯一入口**。
> 库内一律相对路径；用户侧启动命令用绝对路径指向本文件。
> **注意**：本轮未要求 commit，工作区保留全部变更（其中也包含 M2/M3 尚未提交的部分）。

## 一、当前进度与证据

### 已交付

| 交付物 | 位置 | 证据 |
| --- | --- | --- |
| SPDX 快照（3.29.0） | `references/spdx/` | 50 文件；`manifest.json` 记 sha256、`captured_on=2026-10-17` |
| curated 人工表 | `references/curated/` | `tiers.json` 48 条、`trove-map.json` 7 条、`scenario-triggers.json` 6 条、**`conflict-pairs.json` 4 条**、`trap-packages.json` 4 条 |
| 规则包 r0.1.0 | `references/ruleset/` | 6 份文件 + manifest；48/48 档位 + 6/6 触发 + **4/4 冲突对**过锚点门，`disabled=0` |
| 六个生成器 | `tools/` | `fetch_spdx.py` / `gen_ruleset.py` / `gen_synthetic.py` / `gen_profile_truth.py` / `gen_scenario_truth.py` / **`gen_conflict_truth.py`**，`--check` 各两层 |
| M1 解析器 + `scan` | `src/licaudit/inventory/`、`pipeline.py` | 六形态分派、四级可信度链、SPDX 表达式；产 `inventory.json` |
| M2 画像引擎 | `src/licaudit/assess/profile.py` | 原子拆分、档位查表、OSI/FSF、条款锚点、待确认原因码（新增共享 `inventory_records`） |
| M3 场景引擎 | `src/licaudit/assess/scenario.py` | 场景轴解析、`(delivery, link_mode)` 归一、触发查表、三态结论；**表达式依赖改为按求值结论判定（D32）** |
| **M4 冲突引擎** | `src/licaudit/assess/conflict.py` | 无向冲突对查表、依赖 × outbound 档位/义务比较、表达式递归求值（K16）、覆盖度登记 |
| **`assess` 全量模式** | `pipeline.py`、`cli.py` | 产 `profile.json` + `scenario.json` + **`conflicts.json`**；退出码聚合并打印三条摘要 |
| **冲突真值生成器** | `tools/gen_conflict_truth.py` | 由 curated 冲突对表 + curated 档位表直接推导；自带迷你文法，`--check` 两层 |
| **冲突真值** | `data/truth/conflicts.json` | 4 条冲突对 + 2 对未登记组合 + 6 条求值样例 + 1 条 `outbound = pending` |
| **`bench --only m4`** | `src/licaudit/verify.py` | `verify_conflicts`：**16/16 命中** |
| 测试 | `tests/` | 双解释器 **401 passed, 1 skipped** |
| 变异脚本 | `tools/_mutate_m4.py` | 12 组「弄坏 → 变红 → 恢复 → 变绿」（一次性，不入发布面） |

### 冲突对表（4 条，全部 `verified=true`、锚点可在 SPDX 全文逐字定位）

| pair_id | left × right | resolution | 依据锚点 |
| --- | --- | --- | --- |
| `CP-GPL2-APACHE2` | GPL-2.0-only × Apache-2.0 | incompatible | Apache-2.0 §3（专利诉讼终止） |
| `CP-GPL2-AGPL3` | GPL-2.0-only × AGPL-3.0-only | incompatible | AGPL-3.0-only §13 |
| `CP-GPL2-GPL3` | GPL-2.0-only × GPL-3.0-only | incompatible | GPL-2.0-only §6（禁止进一步限制） |
| `CP-GPL3-APACHE2` | GPL-3.0-only × Apache-2.0 | compatible | GPL-3.0-only §7（允许的附加条款） |

`cross_check` 登记 `osadl-mirror / advisory`，**判定不读该字段**（D3 / P4 关闭）。

### 实测记录（当轮真跑）

```
py -3.8  -X utf8 -m pytest          → 401 passed, 1 skipped
py -3.12 -X utf8 -m pytest          → 401 passed, 1 skipped

PYTHONPATH=src py -3.12 -X utf8 -m licaudit --version → rc=0
PYTHONPATH=src py -3.12 -X utf8 -m licaudit status    → rc=0
  启用条目: tiers 48 / obligations 8 / scenario-triggers 6 / conflict-pairs 4 / action-rules 0 / trove-map 7；被拒绝 0
PYTHONPATH=src py -3.12 -X utf8 -m licaudit verify-data → rc=0（11 用例 / 44 记录 / F1 1.0）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m1 → rc=0（44/44，F1 1.0）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m2 → rc=0（条目 52 / 命中 52）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m3 → rc=0（条目 231 / 命中 231）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m4 → rc=0（条目 16 / 命中 16）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench          → rc=0（m1 + m2 + m3 + m4）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m5 → rc=2（尚未实现，不装通过）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit report          → rc=2（M5 未实现，不写占位产物）

# 端到端（scripts 已实跑，摘要末行见括号）
licaudit scan data/synthetic/npm-basic/package.json --out-dir out                  → rc=0
licaudit assess --inventory out/inventory.json --profile-only --out-dir out        → rc=0
licaudit assess --inventory out/inventory.json --scenario saas \
  --network-interaction yes --outbound-license MIT --scenario-note "SaaS 服务" \
  --out-dir out                                                                    → rc=1（一条依赖未识别 → 冲突待定）
licaudit assess ... --outbound-license pending                                      → rc=1（冲突全部待定）
licaudit assess ... --scenario static-link（未给 --delivery）                       → rc=1（待确认，不是默认交付形态）
licaudit assess ... --scenario saas（未答网络交互）                                 → rc=1（待确认）
licaudit assess ... --scenario static-link --linking dynamic                        → rc=2（场景与链接方式矛盾）
licaudit --rules-dir nope status                                                    → rc=3（显式目录无效不回退）

py -3.12 tools/fetch_spdx.py --check --out references/spdx → rc=0
py -3.12 tools/gen_ruleset.py --check                      → rc=0
py -3.12 tools/gen_synthetic.py --check                    → rc=0
py -3.12 tools/gen_profile_truth.py --check                → rc=0
py -3.12 tools/gen_scenario_truth.py --check               → rc=0
py -3.12 tools/gen_conflict_truth.py --check               → rc=0
```

`1 skipped` = `test_trap_case_is_absent_from_example_project`（`example-project` 属 M5）。

### 变异验证（实测，全部「弄坏 → 变红 → 恢复 → 变绿」）

`tools/_mutate_m4.py`（12 组）：

| # | 弄坏什么 | 变红的测试 |
| --- | --- | --- |
| 1 | 冲突对不再无向匹配（K15） | `test_undirected_matching_survives_record_order` |
| 2 | `OR` 取最严格（K16） | `test_or_takes_the_most_permissive_atom` |
| 3 | `AND` 取最宽松（K16） | `test_and_takes_the_strictest_atom` |
| 4 | outbound = pending 按 compatible 放过（K17） | `test_outbound_pending_makes_every_entry_pending` |
| 5 | 依赖强于 outbound 判 compatible | `test_stronger_dependency_than_outbound_is_incompatible` |
| 6 | 未覆盖档位按 permissive 猜（K31） | `test_uncovered_license_is_pending_not_guessed` |
| 7 | 求值时缺档位的原子按 permissive 猜 | `test_expression_with_uncovered_atom_is_not_evaluated` |
| 8 | 单原子记录也进 `expression_evaluations` | `test_single_atom_records_are_not_evaluated` |
| 9 | 冲突依据不再来自 curated 规则表 | `test_conflict_records_declare_the_curated_basis` |
| 10 | disabled 冲突对条目照用（K10） | `test_unverified_pair_is_rejected_by_the_loader_and_ignored_by_the_engine` |
| 11 | `bench m4` 恒判通过 | `test_bench_m4_turns_red_when_truth_drifts` |
| 12 | 表达式求值不再回填 scenario（D32） | `test_expression_is_evaluated_and_the_most_permissive_atom_wins` |

`tools/_mutate_m2.py`（9 组）、`tools/_mutate_m3.py`（9 组）复跑仍全绿。
**M3 脚本的 M9 变异点已修**：它原先按「m3 块的 `ok` 行 + `exit_code` 行」定位，
M4 追加分支后那段文本落到了 m4 块上（变异打偏 → 测试仍是绿）。现按 suite 名定位。

## 二、下一棒待办（M5）

按 `plan/03-模块详设.md` §M5 实现处置建议与中文清单输出：

1. **`references/curated/action-rules.json`**：补齐四级处置决策表
   （`ok` / `declare` / `isolate` / `replace_or_license`），每条带 `anchor`（原文可定位 quote）+
   `checked_on` + `verified`；重跑 `tools/gen_ruleset.py`（哈希变更属预期）。
   **同时要改 `tools/gen_ruleset.py` 的 `build_action_rules`**：现在只校验 `level`，
   没有锚点门、没校验输入字段枚举——按 tiers / 触发表 / 冲突对的同口径补上（D20）。
2. **`src/licaudit/assess/action.py`**（或 `report/sections.py` 的判定侧）：
   分级**只查 `action-rules.json` 决策表**，代码零条件分支（K18/K4）；
   需要拍板 `actions.json` 由谁产出（建议 `assess` 全量模式追加第四份产物，与前三份同源），
   并登记为新决策 D35。
3. **五锚点门**（K20）：`package` + `version`（未知 `*` 且降级）+ `declaration_location`
   （文件 + 字段/行号）+ `spdx_id` + `basis_clause`（规则包锚点或触发表 `rule_id` + 条款）；
   缺任一 → 该条不进处置建议，进「待人工确认项」并写明缺哪一项。
4. **`src/licaudit/report/`**：`sections.py` 返回结构化章节数据；MD 与 CSV 渲染器**共用**它
   （八章节顺序固定：概述 / 口径声明 / 证据锚点 / 逐包明细 / 风险分级 / 处置建议 /
   待人工确认项 / 免责声明）。CSV 列序 = `contract.REPORT_CSV_COLUMNS`、
   `lineterminator="\n"`、UTF-8 无 BOM（P2 已倾向无 BOM，落地前拍板）。
5. **零判定守门（K23）**：AST 三条——`report/` 不 import `licaudit.inventory` / `licaudit.assess`、
   无 `BinOp`（字符串拼接豁免）、无内联「许可证 ID → 档位/处置」字面量表。
6. **退出码联动**：存在 `replace_or_license` / `isolate` → exit 1；只有 `declare` / `ok` → exit 0；
   有 `pending_confirmation` 但无阻断级 → exit 1。
7. **示例项目与示例报告**：`data/synthetic/example-project/`（12–15 个依赖，覆盖六种清单形态与四级处置，
   全合成包名）+ `examples/report/license-report.md` + `.csv` 入仓；
   去掉 `test_trap_case_is_absent_from_example_project` 的 skip。
8. **`data/truth/actions.json` + `tools/gen_action_truth.py`**：每级处置至少一个植入真值；
   由 curated 决策表直接推导，生成器不 import 生产处置引擎；`--check` 两层。
9. **`bench --only m5`**：`verify.IMPLEMENTED_SUITES` 加 `m5`；
   把 `tests/test_verify_data.py::test_bench_unimplemented_suite_is_usage_error` 的靶子
   从 `m5` 改到 `BENCH_SUITES` 之外的套件（如 `m6`），否则该测试会自相矛盾。
10. **`tests/test_action.py` / `tests/test_report.py`**：决策表查表、五锚点缺项降级、
    章节顺序、MD/CSV 同源一致、免责声明逐字、CSV 列序与无 BOM、双跑逐字节一致、
    AST 守门、`bench m5` 阳性/阴性对照。
11. **M4 遗留的口径细化（D34）**：决定是否引入 `linkage-boundary.json` 做传染范围聚合
    （`scope_aggregation`），顺带收窄档位级粗判的两类已知偏差：
    ① 弱传染档位高于宽松档即判不兼容（`MPL-2.0` 依赖 + `MIT` outbound 现在输出 `incompatible`）；
    ② 判据不看场景是否真的分发（`internal` 场景同样报）。无论做不做都要写进 `plan/06` 并加测试。
12. 回写 `plan/00`、`plan/03`（§5 落地补充）、`plan/04`、`plan/05`、`plan/06`；写 `plan/HANDOFF-M6.md`。

### M5 开工前必须知道的既有约束

- **全量模式退出码从 M4 起是三个产物的聚合**：`--outbound-license pending` 一律 exit 1；
  M5 加处置分级时不要把这条冲掉（有测试锁：`test_outbound_pending_makes_every_entry_pending`、
  `test_all_compatible_exits_zero`）。
- **表达式求值只有一份实现**：`conflict.evaluate_expression`，`scenario.py` 直接 import 它；
  新增处置分级时同样不要在别处写第二套 `OR`/`AND` 规则。
- **`conflicts.json` 的两类条目共用 `contract.CONFLICT_FIELDS`**；`actions.json` 用
  `contract.ACTION_FIELDS`（已锁）。报告层只消费字段，遇到未知字段忽略、不推导。
- **报告层不得 import 判定模块**（K23）；处置分级要在判定侧完成后再交给渲染层。
- 场景真值 / 画像真值 / 冲突真值都是 curated 表的投影；**改 curated 必须同时重跑
  `gen_ruleset.py` 与对应的 `gen_*_truth.py`**，否则 `--check` 会红。

## 三、既定口径清单（动了会打挂测试）

完整 K 清单见 `plan/05-里程碑.md` §三。M5 直接相关的既有口径：

| 编号 | 口径 | 影响面 |
| --- | --- | --- |
| K4 | 五档 / 义务项 / 场景触发 / 冲突对 / 处置级别只在规则包定义一次 | 引擎零枚举复制 |
| K7 | 未知即 `pending` / 待人工确认，不按最宽松默认 | M5 的 pending 同口径 |
| K15 | 冲突对无向匹配；`pair_id` 唯一；无向组合不得重复登记 | `curated/conflict-pairs.json` |
| K16 | `OR` 取最宽松、`AND` 取最严格（按 K7 档位序），递归求值 | `assess/conflict.evaluate_expression` |
| K17 | outbound 未提供 → exit 2；outbound = `pending` → 全部条目 `pending` | `assess/conflict.py` |
| K18 | 处置四级：`ok` < `declare` < `isolate` < `replace_or_license`；分级只查 `action-rules.json` | M5 |
| K19 | 报告八章节顺序固定；MD 与 CSV 共用同一章节结构函数 | M5 |
| K20 | 五锚点缺一 → 该条不进处置建议，进待确认项 | M5 |
| K21 | 免责声明逐字输出，不得改写 | `contract.DISCLAIMER` |
| K22 | 退出码四语义：0 完成 / 1 检出阻断 / 2 用法或未知 ID / 3 规则包问题 | `exit_codes.py` |
| K23 | 报告层零判定：不 import 判定模块、无 `BinOp`、无内联判定表 | M5 |
| K26 | 真值只存输入与期望；`observed_*` 即红 | `verify.py` + 测试 |
| K27 | 生成物 `--check` 两层 | 六个生成器 |
| K31 | 画像按原子 ID 出；未覆盖不猜档位 | M5 直接消费 |
| K32 | 条款三态：无规则 = `null`，不是 `false` | `assess/profile.py` |

### M4 新增/收紧的口径（已登记 plan/06）

| 编号 | 内容 |
| --- | --- |
| D32 | 表达式求值**回填 scenario 判定**：按求值选中的原子给结论；但任一原子本身待确认 → 整体仍待确认；`expression_unresolved` 收窄为「求值不出」 |
| D33 | `same-license` 判据加档位护栏：GPL-3.0-only 依赖 + AGPL-3.0-only outbound 判 `compatible`（AGPL §13 允许合并） |
| D34 | M4 不做传染范围聚合，只做档位级比较并在 `notes` 显式登记；聚合挪到 M5 |
| P4 | 冲突对来源交叉验证**已关闭**：curated 为主 + `cross_check` 留痕，判定不读 |
| P7 | 聚合表与档位级粗判的关系**已关闭**：见 D34 |

## 四、本机环境坑（M1–M4 实测）

- **`py` 不是 `python`**（`python` 是商店占位符）。跑脚本一律 `py -3.12 -X utf8`。
- **本仓库未安装时用 `PYTHONPATH=src`**：`py -3.12 -m licaudit` 直接跑会 `No module named licaudit`。
- **多行 heredoc 写文件会被吞**：本机 Git Bash 对 `cat > file <<'PY'` 的收尾不稳，
  写脚本请用文件写入工具，或先写到临时文件再执行。
- **往 `python - <<'PY'` 里嵌含反斜杠的文本会被转义吃掉**：`\\` 到 Python 只剩一个，
  行尾反斜杠还会被当成续行（本轮就因此让一次 `replace` 匹配失败）。需要匹配含反斜杠的文本时，
  用文件编辑工具而不是 heredoc。
- **改 curated 必须重跑生成器**：`gen_ruleset.py` 重写 manifest 哈希；
  场景触发条目还要重跑 `gen_scenario_truth.py`，冲突对条目还要重跑 `gen_conflict_truth.py`。
  只改一处会让 `--check` 变红。
- **变异脚本按文本片段定位，会随文件结构漂移**：`_mutate_m2/m3.py` 里针对 `verify.py` 的变异点
  原先靠「m3 块 + `exit_code` 行」定位，M4 插入分支后打到了 m4 上（变异未被发现）。
  现已改为按 suite 名定位；**新增里程碑后务必复跑三份变异脚本**。
- **链接方式轴场景必须给交付形态**：`--scenario static-link` 不带 `--delivery` → 全部待确认（exit 1），
  这是 K14 的行为，不是 bug。
- **`saas` 必须回答网络交互**：不答 → 整批待确认（exit 1）；答 `no` 是矛盾 → 同样待确认。
- **`--outbound-license pending` → 全量模式 exit 1**：M4 起冲突全部待定，有测试锁。
- **显式 `--rules-dir` 指向空目录会 exit 3**，不会静默回退（D21）。
- **`references/spdx/` 是 2.8 MB 冻结数据**：`.gitattributes` 已标 `-text`，别让编辑器改行尾。
- **Windows 路径**：`os.path.relpath` 跨盘符会抛 `ValueError`；展示路径要兜底。
- **编码**：`encoding.ensure_utf8_stdio` 已按 `stream.encoding` 探针处理；CI 另设 `PYTHONUTF8=1`。
- **变异脚本是一次性的**：跑完务必复跑一次全量测试确认恢复无损。

## 五、DoD 逐项 checklist（M4）

- [x] 已知冲突对全命中（含 `GPL-2.0-only × Apache-2.0`）：`bench --only m4` 16/16
- [x] 冲突对无向匹配：`(left,right)` ≡ `(right,left)`，倒序清单结论逐字相同（K15）
- [x] `OR` 最宽松 / `AND` 最严格：含嵌套、`WITH`、未覆盖档位；求值过程写进 `expression_evaluations`（K16）
- [x] outbound 未知 → 全部待定：文案固定「项目自身许可证待定」，条目全进 `pending_confirmation`（K17）
- [x] 依赖强于 outbound → `incompatible`；全相容 → 退出码 0
- [x] 未覆盖档位不猜：`tier: null` → `pending`；求值 `resolved = false`
- [x] 每条冲突自带 `basis` + 可定位 `anchor` + `checked_on`，且与规则表逐字一致
- [x] 冲突对表 4/4 条锚点可在 SPDX 全文逐字定位；`disabled=0`；left/right 全在快照内
- [x] `data/truth/conflicts.json` 由 curated 冲突对表直接推导，`--check` 位级一致
- [x] `conflicts.json` 字段序 == `contract.CONFLICT_FIELDS`（两类条目逐条断言）
- [x] 纯函数：双跑逐字节一致
- [x] 双解释器 401 passed
- [x] 12 组变异验证（`tools/_mutate_m4.py`）+ 复跑 M2/M3 各 9 组
- [x] D32–D34 与 P4/P7 已登记 `plan/06`；`plan/00/03/04/05` 与 SKILL/README/references/tools/CI 已回写
- [ ] **CI 首推**：配置已更新（含 `gen_conflict_truth.py --check` 与 `bench --only m4`），
      但仍**未推送、未运行**；M6 首推时据实补记

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

# 生成物自检
py -3.12 -X utf8 tools/fetch_spdx.py --check --out references/spdx
py -3.12 -X utf8 tools/gen_ruleset.py --check
py -3.12 -X utf8 tools/gen_synthetic.py --check
py -3.12 -X utf8 tools/gen_profile_truth.py --check
py -3.12 -X utf8 tools/gen_scenario_truth.py --check
py -3.12 -X utf8 tools/gen_conflict_truth.py --check

# 变异验证（一次性；会临时改源码再恢复）
py -3.12 -X utf8 tools/_mutate_m2.py
py -3.12 -X utf8 tools/_mutate_m3.py
py -3.12 -X utf8 tools/_mutate_m4.py

# 交付态入口
licaudit status
licaudit scan data/synthetic/npm-basic/package.json --out-dir out
licaudit assess --inventory out/inventory.json --profile-only --out-dir out
licaudit assess --inventory out/inventory.json --scenario saas \
  --network-interaction yes --outbound-license MIT --scenario-note "用户原话" --out-dir out
licaudit assess --inventory out/inventory.json --scenario static-link \
  --delivery binary --outbound-license pending --scenario-note "分发 + 静态链接" --out-dir out
licaudit verify-data
licaudit bench --only m1
licaudit bench --only m2
licaudit bench --only m3
licaudit bench --only m4

# 未安装时（Skill 场景）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit assess --inventory out/inventory.json \
  --scenario saas --network-interaction yes --outbound-license MIT \
  --scenario-note "用户原话" --out-dir out
```

## 七、启动提示词（新对话用）

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M5.md" 继续完成任务
```
