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
  --scenario saas --outbound-license pending \
  --scenario-note "用户原话：我们通过 Web 提供服务" --out-dir out
```

`--scenario` 只接受八个 ID：`internal`、`distribute-binary`、`distribute-source`、`saas`、
`static-link`、`dynamic-link`、`separate-process`、`container-image`。其他取值是用法错误（exit 2）。

产出 `out/profile.json`、`out/scenario.json`、`out/conflicts.json`、`out/actions.json`。

### 第 4 步：出清单

```bash
licaudit report --out-dir out --format md
licaudit report --out-dir out --format csv
```

产出 `out/license-report.md` / `out/license-report.csv`，八个固定章节。

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

### scenario.json

`package` `scenario` `link_mode` `triggers` `verdict` `evidence`

`verdict` 三态：`triggered` / `not_triggered` / `pending_confirmation`。

### conflicts.json

`pair_id` `left` `right` `basis` `resolution` `evidence`

`resolution` 三态：`compatible` / `incompatible` / `pending`。

### actions.json

`package` `version` `spdx_id` `level` `reasons` `evidence`

`level` 四级：`ok` / `declare` / `isolate` / `replace_or_license`。

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

**骨架（M0）**：CLI 契约、退出码、规则包加载硬门、自检、三条调用通路已就绪；`scan` / `assess` / `report` 在规则包缺失时**真实返回 3**，实现分别落在 M1 / M2–M4 / M5。各里程碑 DoD 见 `plan/05-里程碑.md`。
