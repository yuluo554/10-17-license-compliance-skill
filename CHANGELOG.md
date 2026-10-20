# Changelog

licaudit 的版本分两层：

- **代码版本**（本文件）：修 bug、加功能、改发布形态
- **规则集版本**：规则包 `ruleset_version` 与所依据的标准/快照及其生效日期

> 规则判定逻辑发生变化时，主版本号 +1，并在发布说明中提示「历史报告需重跑」。
> 本仓判定逻辑的载体是规则包 `references/ruleset/`（`ruleset_version`）与 SPDX 快照版本。

## [0.1.2] - 2026-10-20

本轮不动判定逻辑、不动规则包与 SPDX 快照，只修元数据 / CI / 文档事实
（**发布形态改变**：Python floor 从 3.8 抬到 3.12）。

### 变更

- **`license` 改用 PEP 639 形式**：`license = "MIT"` + `license-files = ["LICENSE"]`，
  删掉 `License :: OSI Approved :: MIT License` classifier，`build-system.requires` 抬到
  `setuptools>=77`。实测 `prepare_metadata_for_build_wheel` 的 `SetuptoolsDeprecationWarning`
  从 **3 条降到 0 条**，元数据升到 2.4 并带 `License-Expression: MIT`（口径见 `plan/06` D39）。
- **Python floor 3.8 → 3.12**（`requires-python = ">=3.12"`，classifiers 同步），CI 矩阵收为
  `3.12` × 双 OS（2 个 job），actions 升 `actions/checkout@v7` / `actions/setup-python@v7`。
  原因：PEP 639 的 license 表达式需要 setuptools≥77，而 setuptools 77 起要求 Python≥3.9，
  3.8 腿无法构建元数据（实测：3.8 + 可装的最新 setuptools 75.3.0 下 `license = "MIT"` 直接
  `ValueError`）。**3.8 用户请留在 `v0.1.1`。**
- 文档事实修正：`SKILL.md` 的 `metadata.version` 由 `0.1.0`（v0.1.1 时漏改）改为 `0.1.2`、
  限制段去掉「不支持 wheel 安装后直接使用」（D38 起 wheel 已自带规则包）、README 补当前版本与
  M6 说明、`plan/00`·`plan/02`·`plan/05`·`plan/06` 同步写清 floor 与矩阵的新口径。
- `tools/check_release.py` 的发布留档不再写死 `plan/RELEASE-M6.md`：改为按包版本匹配
  `plan/RELEASE-*.md` 的 `tag` 字段（`--online` 的 CI 检查本就是「该提交所有 job success」，
  与新矩阵 2 个 job 兼容）。

### 测试

- **457 passed, 0 skipped**（`py -3.12 -X utf8 -m pytest -o addopts= -q`）；`licaudit selftest`
  rc=0；七个生成器 `--check` 全部 rc=0；`licaudit bench` m1–m5 全绿。
- 干净 venv 装 wheel 后 `licaudit status` / `selftest` 均 rc=0（wheel 含 `licaudit` 30 /
  `references` 65 / `data` 39 个文件）。

### 规则集

- 无变更。当前依据：**SPDX License List 3.29.0**（快照采集日 2026-10-17），规则包 **r0.1.0**。

### 是否需要重跑历史报告

**否。** 判定结果与 0.1.1 一致（本轮只改元数据、文档与打包面）。

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

- **安装态资源定位（阶段三实测踩到并修掉）**：`default_spdx_dir()` 原先只按打包文件位置上溯三级，
  wheel 安装后得到 `<venv>/Lib`，于是 `licaudit assess` / `report` 报「SPDX 快照不可读（exit 2）」——
  即「装完不能用」。现将随包资源定位统一为「**源码态仓库根 + 安装态 site-packages**」两处都找
  （`ruleset.loader.resource_roots`，规则包与 SPDX 快照共用），并新增
  `tests/test_bundled_paths.py`（4 用例，含假安装态布局与缺快照报错）。
- 包内 `__version__` 与 `pyproject.toml` 的 `version` 对齐。

### 规则集

- 无变更。当前依据：**SPDX License List 3.29.0**（2023-11-30 发布，快照采集日 2026-10-17），
  规则包 **r0.1.0**。
- 本次只补记复核元数据与打包形态，不改任何档位 / 义务 / 锚点 / 冲突对 / 决策表。

### 测试

- 本版实测 **457 passed, 0 skipped**（`py -3.8` 与 `py -3.12` 各跑一次，命令
  `-X utf8 -m pytest -o addopts= -q`；复核时点 `8173867` = tag `v0.1.1`）；
  干净 venv 装 wheel 后 `licaudit status` / `licaudit selftest` 均 rc=0。
- 457 比 M5/M6 的 467 少 20 项，原因是 README 改成产品页后 `tests/test_readme_surface.py`
  的参数化样本减少（不是删断言）；成因与代价记在 `plan/06` §五。
  里程碑时点的 467 按纪律保留在 `plan/05` §二之五/二之六、`plan/RELEASE-M6.md`、`plan/HANDOFF-M6.md`。

### 是否需要重跑历史报告

**否。** 判定结果与 0.1.0 一致（示例报告差异仅概述区新增两行版本信息）。

### 校验和

```
306b0625019f86be4158fd707f58c3d3bdd38dd57efd8716be23a0dd51d1d37f  licaudit-0.1.1-py3-none-any.whl
5f399d9569343a6531511cc44ce77ccb7f497c43dc6d424a1756057276ab86cc  licaudit-0.1.1.tar.gz
```

## [0.1.0] - 2026-10-17

首个发布版本，发布形态为 **sdist / git clone + editable**（当时 wheel 不含规则包，见 D12）。

### 规则集

- 当前依据：**SPDX License List 3.29.0**（快照采集日 2026-10-17）
- 规则包 `ruleset_version` = **r0.1.0**：48/740 抽样覆盖；档位/义务/场景触发/冲突对/处置决策表
  全部挂可逐字定位的原文锚点