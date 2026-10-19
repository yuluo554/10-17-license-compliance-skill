# Changelog

licaudit 的版本分两层：

- **代码版本**（本文件）：修 bug、加功能、改发布形态
- **规则集版本**：规则包 `ruleset_version` 与所依据的标准/快照及其生效日期

> 规则判定逻辑发生变化时，主版本号 +1，并在发布说明中提示「历史报告需重跑」。
> 本仓判定逻辑的载体是规则包 `references/ruleset/`（`ruleset_version`）与 SPDX 快照版本。

## [0.1.1] - 2026-10-19

### 新增

- **wheel 首次自带规则包**：`pip install licaudit` 装完即可 `licaudit status`（修正 D12，见
  [plan/06](plan/06-交付对标与决策记录.md) 的 D38；`references/` 与 `data/` 通过
  `[tool.setuptools.package-data]` 打进 wheel，运行时定位顺序新增「site-packages 推导」）。
- `licaudit report` 概述区新增「工具版本」与「SPDX 许可证清单」两行（依据版本与工具版本同屏可见）。
- 规则集复核元数据 `meta.review`（`references/ruleset/manifest.json`）：复核日 / 复核周期 /
  下次复核到期 / 复核人 / `standards[]`（含 `currency` 与 `authority_url`）；
  新增守门测试 `tests/test_ruleset_review.py`（6 个用例）。

### 变更

- `[project.urls]` 增加 `Changelog`；classifiers 补齐 Development Status / Intended Audience /
  Natural Language / Topic。

### 修复

- 包内 `__version__` 与 `pyproject.toml` 的 `version` 对齐。

### 规则集

- 无变更。当前依据：**SPDX License List 3.29.0**（2023-11-30 发布，快照采集日 2026-10-17），
  规则包 **r0.1.0**。
- 本次只补记复核元数据与打包形态，不改任何档位 / 义务 / 锚点 / 冲突对 / 决策表。

### 是否需要重跑历史报告

**否。** 判定结果与 0.1.0 一致（示例报告差异仅概述区新增两行版本信息）。

### 校验和

```
0329a7eaba9f5c255482e5acb22bf45c3f7a1eb0790063a5c0b8160d8d1e93ad  licaudit-0.1.1-py3-none-any.whl
18f70f3d9f14bfed4c1f55c3598fa334fade610bcb2e6e509d5162ffffd83dac  licaudit-0.1.1.tar.gz
```

## [0.1.0] - 2026-10-17

首个发布版本，发布形态为 **sdist / git clone + editable**（当时 wheel 不含规则包，见 D12）。

### 规则集

- 当前依据：**SPDX License List 3.29.0**（快照采集日 2026-10-17）
- 规则包 `ruleset_version` = **r0.1.0**：48/740 抽样覆盖；档位/义务/场景触发/冲突对/处置决策表
  全部挂可逐字定位的原文锚点