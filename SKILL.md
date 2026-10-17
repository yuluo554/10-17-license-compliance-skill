---
name: license-compliance-audit
description: >-
  读依赖清单（package.json / package-lock.json / requirements.txt / pyproject.toml /
  go.mod / pom.xml），把许可证归一化为 SPDX 标识，结合分发方式、链接方式与网络交互
  判定传染范围与冲突，输出中文《第三方开源清单》+ 风险分级 + 四级处置建议。
  当用户问「我这样用 GPL/AGPL/LGPL/MPL 会不会被传染」「能不能商用/闭源/SaaS」
  「依赖之间或与我要用的许可证是否冲突」「生成一份第三方开源清单/合规审查报告」时使用。
license: MIT
metadata:
  version: 0.1.0
  author: yuluo554
  language: zh-CN
---

# 开源许可证合规审查

把「我用了什么许可证」推进到「**我的用法触发什么义务**」。

本 Skill 是**判定层**工具：不做源码扫描、不生成 SBOM、不做 CVE 评分。取证层已有成熟工具，本 Skill 只回答场景判定。

<!-- contract-fields: package version raw_license spdx_id confidence evidence -->
<!-- contract-profile: spdx_id tier obligations is_osi_approved is_fsf_libre patent_clause trademark_clause evidence -->
<!-- contract-scenario: package scenario link_mode triggers verdict evidence -->
<!-- contract-conflict: pair_id left right basis resolution evidence -->
<!-- contract-action: package version spdx_id level reasons evidence -->
<!-- report-sections: 概述 口径声明 证据锚点 逐包明细 风险分级 处置建议 待人工确认项 免责声明 -->
<!-- exit-codes: 0=分析完成且无阻断项 1=检出阻断或隔离级项 2=用法错误或未知许可证ID 3=规则包缺失或校验失败 -->

## 何时使用

- 用户给出依赖清单，问「这些依赖的许可证有什么风险」。
- 用户问 GPL / AGPL / LGPL / MPL / BUSL 等在**自己的交付方式**下是否传染。
- 用户准备商用、闭源分发、SaaS 上线或融资尽调，需要第三方开源清单。
- 用户问依赖之间、或依赖与自己计划的 outbound 许可证是否冲突。

## 何时不要用

- 需要扫源码里的许可头、生成 SBOM、查 CVE —— 用 syft / scancode / ORT / reuse 等工具。
- 需要法律意见 —— 本 Skill 只做工程判断，输出固定免责声明。

## 工作流

### 第 1 步：收集事实

向用户确认三件事，**不要替用户回答**：

1. 依赖清单文件路径（可多个）。
2. 交付形态与链接方式（八场景之一：内部使用 / 分发二进制 / 分发源码 / SaaS / 静态链接 / 动态链接 / 独立进程 / 容器镜像）。
3. 项目自身准备使用的 outbound 许可证；未决定就说 `pending`。

若用户没给场景或 outbound，**先问**，不要按最宽松默认继续。

### 第 2 步：扫描与归一化

```bash
licaudit scan path/to/package.json path/to/requirements.txt --out-dir out
```

产出 `out/inventory.json`。每条依赖带 `spdx_id`、`confidence`（四级可信度）与证据锚点。

### 第 3 步：判定

```bash
licaudit assess --inventory out/inventory.json \
  --scenario saas --network-interaction yes \
  --outbound-license pending \
  --scenario-note "用户原话：我们通过 Web 提供服务" --out-dir out
```

只做画像（只要许可证矩阵，不需要先回答场景）时用：

```bash
licaudit assess --inventory out/inventory.json --profile-only --out-dir out
```

`--scenario` 只接受八个 ID：`internal`、`distribute-binary`、`distribute-source`、`saas`、
`static-link`、`dynamic-link`、`separate-process`、`container-image`。其他取值是用法错误（exit 2）。
`static-link` / `dynamic-link` / `separate-process` 是**链接方式轴**场景，必须同时给出交付形态
（`--delivery internal|binary|source|saas|container`，或用 `--scenario` + `--linking` 的等价写法）；
`saas` 必须回答 `--network-interaction yes|no`，`container-image` 可选。

**`--outbound-license` 是全量模式必填**：写项目准备采用的 SPDX 表达式（如 `MIT`、`MIT OR Apache-2.0`），
尚未决定就写 `pending`。写 `pending` 时兼容性判定全部输出「待定」并返回 `1`——**这是规定行为，不是故障**。

产出 `out/profile.json`、`out/scenario.json`、`out/conflicts.json`、`out/actions.json`。

### 第 4 步：出清单

```bash
licaudit report --out-dir out --format md
licaudit report --out-dir out --format csv
```

产出 `out/license-report.md` / `out/license-report.csv`，八个固定章节。报告只消费
`actions.json` / `conflicts.json` / `scenario.json` / `profile.json` 的既有字段，不重算判定；
有阻断级或待确认项时 `report` 返回 `1`。

### 第 5 步：转述

把报告里的**结论**转述给用户，保留：

- 每个阻断项的五个证据锚点（包名 + 版本 + 声明位置 + SPDX ID + 依据条款）；
- 「待人工确认项」——不要替用户补全；
- 固定免责声明原文。

**不要**在转述时新增判定、改档位或补义务项。

## 输出契约

### inventory.json

每条依赖记录字段（顺序固定）：
`package` `version` `raw_license` `spdx_id` `confidence` `evidence`

`confidence` 四值：`license_expression` / `trove_classifier` / `license_first_line` / `truncated_fallback`。

### profile.json

`spdx_id` `tier` `obligations` `is_osi_approved` `is_fsf_libre` `patent_clause` `trademark_clause` `evidence`

`tier` 五档：`permissive` / `weak-copyleft` / `strong-copyleft` / `network-copyleft` / `source-available`。

- 每个**不同**的 SPDX 原子 ID 一条；`AND` / `OR` 表达式先拆原子，求值属于冲突分析。
- 档位与义务只查规则包；未覆盖的 ID 输出 `tier: null` + `obligations: null`，并进 `pending_confirmation`，**不猜**。
- `is_osi_approved` / `is_fsf_libre` 只从 SPDX 快照取（不在快照里 → `null`）；FSF 仅展示，不参与判定。
- 无规则时 `patent_clause.present` / `trademark_clause.present` 为 `null`（不知道），不是 `false`（没有条款）。
- `disabled_rules` 列出被加载器拒绝的规则条目；它们不参与任何判定。

### scenario.json

`package` `scenario` `link_mode` `triggers` `verdict` `evidence`

`verdict` 三态：`triggered` / `not_triggered` / `pending_confirmation`。

- 每条依赖一条记录；`triggers` 是命中的触发名集合（如 `distribution` / `network-interaction` / `static-link`）。
- 触发判定只查规则包 `scenario-triggers.json`：`tier` + `scenarios` + `link_modes` +（可选）`network_interaction` 四项全中才算触发；未命中 = `not_triggered`（该场景不触发）。
- **「商用」不是输入项、不是触发条件**；AGPL §13 是独立触发点：`network_interaction = true` 时即使是内部使用或未分发也触发。
- 用户回答原样落盘：顶层 `scenario` / `delivery` / `link_mode` / `network_interaction` / `answered_by` / `raw_answer` / `outbound_license`。
- 未回答或回答矛盾（如 SaaS 却答「无网络交互」、链接方式轴场景没给交付形态、未覆盖档位）→ `pending_confirmation`，**不按最宽松默认**；条目落在顶层 `pending_confirmation` 并写明 `reasons`。
- `container-image` 的网络交互为可选；没回答时，网络传染档位输出待确认而不是「不触发」。
- 表达式依赖（`MIT OR GPL-3.0-only`）按冲突层同一套规则求值后下结论：`OR` 取最宽松、`AND` 取最严格；
  选择过程写在 `evidence.expression_evaluation` 里。求值不出（有原子未覆盖档位）→ 待确认 +
  `expression_unresolved`。**任一原子本身待确认时整体仍待确认**（不按选中分支把「不知道」说成「不触发」）。

### conflicts.json

`pair_id` `left` `right` `basis` `resolution` `evidence`

`resolution` 三态：`compatible` / `incompatible` / `pending`。

- 两类条目共用上面的字段：`dependency_conflicts`（依赖之间）、`outbound_conflicts`（依赖 × 项目 outbound）。
- 冲突对**无向匹配**：`(left, right)` 与 `(right, left)` 等价；结论按规则表 `conflict-pairs.json` 给，
  `basis` 与 `anchor` 原样来自规则表（引擎不自己编依据）。
- `OR` 取最宽松、`AND` 取最严格（按五档序）；求值记录在 `expression_evaluations`，带所选原子与理由。
- `outbound = pending` → 所有「依赖 × outbound」条目 `pending`，依据固定「项目自身许可证待定」。
- 依赖档位强于 outbound → `incompatible`；依赖要求同许可发布而 outbound 选了另一个许可证
  （且 outbound 档位不高于依赖档位）→ `incompatible`。
- 档位未覆盖（`tier: null`）→ `pending`，不猜。
- 规则表未登记的许可证组合只计 `uncovered_pairs`（覆盖度事实，不改退出码）。
- 顶层 `pending_confirmation` 是 `pending` 条目的投影，带原因码。

### actions.json

`package` `version` `spdx_id` `level` `reasons` `evidence`

`level` 四级：`ok` / `declare` / `isolate` / `replace_or_license`。

- 每条依赖一条记录；`level` 为 `null` 表示**该条不进处置建议**，只在「待人工确认项」里出现。
- 分级**只查规则包** `action-rules.json` 的决策表（义务轴 + 冲突结论 + 链接方式，从上到下先命中者生效）；
  引擎不写任何「义务项 → 处置级别」的条件分支，义务项到义务轴的映射也来自同一份规则表。
- **五锚点门**：`package` / `version`（未知时 `*` 并降级）/ `declaration_location`（文件 + 字段/行号）/
  `spdx_id` / `basis_clause`（规则包锚点）缺任一 → 该条不进处置建议，进 `pending_confirmation` 并写明缺哪一项
  （`evidence.missing_anchors` + `evidence.reason_codes`）。
- 场景结论或兼容性结论为待定 → 同样待确认，不猜级别（K7）。
- 四级语义：`ok` 未触发任何需要行动的义务；`declare` 仅触发声明类义务；
  `isolate` 可通过进程/容器边界隔离规避（含档位级不相容但可分离的情形）；
  `replace_or_license` 同许可义务与 outbound 不相容、或依赖间冲突无法隔离。
- 退出码联动：存在 `isolate` / `replace_or_license` 或任一待确认项 → `1`。

### 报告章节（顺序固定）

概述 / 口径声明 / 证据锚点 / 逐包明细 / 风险分级 / 处置建议 / 待人工确认项 / 免责声明

## 退出码

| 码 | 含义 |
| --- | --- |
| `0` | 分析完成且无阻断项 |
| `1` | 分析完成，检出阻断/隔离级项（**这是正常语义，不是故障**） |
| `2` | 用法错误、输入不可用、未知许可证 ID |
| `3` | 规则包缺失或校验失败（**不会被降级成「零依赖无风险」**） |

## 限制与边界

- 纯本地运行：不联网、不上传清单；SPDX 快照随包冻结。
- 运行时零第三方依赖，Python ≥ 3.8。
- 规则包位于仓库 `references/ruleset/`；首期发布形态是源码包 / git clone，**不支持 wheel 安装后直接使用**（用 `--rules-dir` 指定）。
- 只覆盖清单里出现的许可证；未覆盖的 SPDX ID 输出 `tier: null` + 待人工确认，不猜档位。
- 版本语义保留：`GPL-2.0-only` 不会归一化成 `GPL-2.0`；族名不明输出 `<族>-unknown`。
- 不做源码许可头扫描、不做 SBOM、不做 CVE 评分、不做许可证全文自动分类。

## 免责声明（原样输出）

> 本清单由自动化工具生成，不构成法律意见（非法律意见）。涉及商业分发、诉讼或高价值交易时，请咨询执业律师。

## 当前实现状态

**M1 已完成**：SPDX 3.29.0 快照、规则包（48 条已核验档位规则）、11 个合成用例与冻结真值已入仓；
`scan` 产出 `inventory.json`，`verify-data` 用参照实现逐条对账，`bench --only m1` 可跑。

**M2 已完成**：`assess --profile-only` 产出 `profile.json`（52 个原子 ID：48 条有档位 + 4 条未覆盖）；
`bench --only m2` 用 `data/truth/profile.json`（规则表的投影）逐条对账。

**M3 已完成**：`assess --scenario ... --outbound-license ...` 产出 `profile.json` + `scenario.json`；
规则包含 6 条已核验场景触发条目（分发 / 网络交互 / 静态链接 / 托管服务限制），
`bench --only m3` 用 `data/truth/scenario.json`（八场景 × 链接方式 × 档位 × 网络交互的判定表，
230 行）逐行对账。

**M4 已完成**：`assess` 全量模式追加 `conflicts.json`（依赖间冲突 / 依赖 × outbound / 表达式求值记录 /
未登记组合覆盖度）；规则包含 4 条已核验冲突对（GPL-2.0-only × Apache-2.0 / AGPL-3.0 /
GPL-3.0，GPL-3.0-only × Apache-2.0），`bench --only m4` 用 `data/truth/conflicts.json`
逐条对账（16 条）。表达式求值（`OR` 最宽松 / `AND` 最严格）同时回填 `scenario.json`，
两个产物对同一条表达式给一致的选择。

**M5 已完成**：`assess` 全量模式追加 `actions.json`（四级处置 + 五锚点门 + 待人工确认）；
`report --format md|csv` 渲染八章节中文《第三方开源清单》（MD 与 CSV 共用同一章节结构函数，
CSV 列序固定、UTF-8 无 BOM、LF 行尾）；规则包含 8 条已核验处置决策规则；
`bench --only m5` 用 `data/truth/actions.json`（192 组确定输入 + 四级样本，共 196 条）逐条对账；
报告层三条 AST 守门（不 import 判定模块 / 无算术拼接 / 无内联判定表）落进测试；
入仓示例报告 `examples/report/`（两份运行，合起来覆盖四级处置）。
传染范围聚合（按链接/分发边界）**仍未实现**：处置分级用决策表的 `link_mode` 维度表达
「边界是否可分离」，`conflicts.json.notes` 与 `actions.json.notes` 里有明文登记。

**M6 发布动作进行中**：本版目标为 `v0.1.0`。GitHub 公开仓库 + git tag + Release（附真实产物：
sdist 源码包、规则包与快照数据留档、示例报告 MD/CSV、`SHA256SUMS`）；
`plan/RELEASE-M6.md` 在 tag 之前入库，按「tag 时点事实 / tag 后追加事实」两栏记录，
禁止预填；`tools/check_release.py` 是发布终态自检门（离线查留档与版本一致性，
`--online` 核对 tag / Release 附件 / sha256）。M6 **不新增任何判定能力**。

各里程碑 DoD 见 `plan/05-里程碑.md`；发布事实见 `plan/RELEASE-M6.md`。

### 数据刷新（人工步骤，运行时零网络）

```bash
py -3.12 -X utf8 tools/fetch_spdx.py --out references/spdx
py -3.12 -X utf8 tools/gen_ruleset.py
py -3.12 -X utf8 tools/gen_synthetic.py
py -3.12 -X utf8 tools/gen_profile_truth.py
py -3.12 -X utf8 tools/gen_scenario_truth.py
py -3.12 -X utf8 tools/gen_conflict_truth.py
py -3.12 -X utf8 tools/gen_action_truth.py
```

生成物禁止手改；七个生成器都支持 `--check`（重生成后逐字节比对）。
