# licauait

开源许可证合规审查 Skill：读依赖清单，归一化为 SPDX 标识，结合分发 / 链接 / 网络交互判定传染与冲突，输出中文《第三方开源清单》。

> 当前状态：**M0 骨架**。CLI 契约、退出码、规则包硬门、自检与三条调用通路已就绪；
> `scan` / `assess` / `report` 在规则包缺失时真实返回 `3`，实现分别落在 M1 / M2–M4 / M5。
> 里程碑与 DoD 见 [plan/05-里程碑.md](plan/05-里程碑.md)。

## 它解决什么

取证层（syft / scancode / ORT / license-checker）已经能告诉你「这个包是什么许可证」。
真正卡住人的是判定层：**我这个用法会不会被传染、要不要开源、能不能卖。**

本 Skill 只做判定层：

1. **归一化**：依赖清单 → SPDX 标识，四级可信度链，禁止全文关键词匹配。
2. **画像**：传染强度五档 + 义务项集合 + OSI/FSF 状态 + 专利/商标条款。
3. **场景**：八种交付形态 × 链接方式 × 网络交互 → 是否触发义务。
4. **冲突**：依赖之间、依赖与项目 outbound 许可证之间的不兼容。
5. **处置**：可直接用 / 需补声明 / 需隔离 / 需替换或取得商业授权，每条挂五个证据锚点。

## 安装

```bash
pip install -e ".[dev]"
```

要求 Python ≥ 3.8，运行时零第三方依赖。`dev` 只多一个 `pytest`。

## 快速开始

### 现在就能跑（M0 骨架）

```bash
# 1. 只跑纯内部不变量自检（不依赖规则包）
licaudit selftest --core

# 2. 查看规则包定位情况：M0 尚无规则包 → 预期 exit 3
licaudit status

# 3. 完整自检：同样因缺规则包而 exit 1（这是自检可证伪的证据）
licaudit selftest
```

未安装时的等价入口（启动器会把仓库 `src` 放进 `sys.path`）：

```bash
py -3.12 scripts/launcher_licaudit.py selftest --core
PYTHONPATH=src python -m licaudit selftest --core
```

**未安装时 `python -m licaudit` 会报 `No module named licaudit`**——模块方式依赖安装；
Skill 场景（agent 直接读仓库）用启动器，或设置 `PYTHONPATH=src`。

### M1–M5 落地后可用

```bash
# 扫描依赖清单 → inventory.json
licaudit scan data/synthetic/example-project/package.json --out-dir out

# 画像 + 场景 + 冲突判定
licaudit assess --inventory out/inventory.json --scenario saas \
  --outbound-license pending --scenario-note "用户原话" --out-dir out

# 中文《第三方开源清单》
licaudit report --out-dir out --format md
licaudit report --out-dir out --format csv

# 真值对账与内置基准
licaudit verify-data
licaudit bench
```

目前这些命令**先过规则包硬门**：规则包缺失直接 `exit 3`，规则包就绪后明确提示「该阶段未实现」并 `exit 2`，
**不会写出占位产物，也不会返回 `exit 0` 假装成功**。

**M0 阶段说明**：规则包 `manifest.json` 尚未生成（由 M1 的规则包生成器产出），
因此 `status` / `scan` / `assess` / `report` 都会返回 `exit 3`（规则包缺失）。
这是**刻意**的——规则包缺失不得退化成「零依赖、无风险」的 `exit 0`。

## 退出码

| 码 | 含义 |
| --- | --- |
| `0` | 分析完成且无阻断项 |
| `1` | 分析完成，检出阻断/隔离级项（既定语义，不是故障）；或自检未通过 |
| `2` | 用法错误、输入不可用、未知许可证 ID |
| `3` | 规则包缺失或校验失败 |

## 场景（八种）

`internal` 内部使用 / `distribute-binary` 分发二进制 / `distribute-source` 分发源码 / `saas` /
`static-link` 静态链接 / `dynamic-link` 动态链接 / `separate-process` 独立进程 / `container-image` 容器镜像

**商用本身不是 GPL / AGPL 的触发要件。** 触发点是分发（GPL 系）与网络交互（AGPL §13，独立触发点）。

## 目录

```
SKILL.md              agent 入口与契约块
src/licaudit/         确定性引擎（纯标准库）
scripts/              Skill 场景启动器
references/           SPDX 快照 + 规则包（数据，不是代码）
data/                 合成清单与真值（M1 起）
tests/                pytest
plan/                 计划、决策、里程碑、留档
```

## 隐私

纯本地处理：不联网、不上传依赖清单、不读取用户主目录。SPDX 快照随仓库冻结，刷新是人工生成步骤。

## 限制

- 不做源码许可头扫描、不生成 SBOM、不做 CVE 评分。
- 只覆盖清单里出现的许可证；未覆盖 ID 输出 `tier: null` + 待人工确认。
- 首期发布形态是源码包 / git clone + editable 安装。**不支持 wheel 安装后直接使用**——规则包在仓库 `references/`，wheel 不含它；需要时用 `--rules-dir` 显式指定。
- 规则包缺失 / 校验失败一律 `exit 3`，不会产出空报告。

## 许可

本项目代码以 MIT 发布（见 [LICENSE](LICENSE)）。`references/spdx/` 下的 SPDX 数据来自
<https://spdx.org/licenses/>，遵循 CC0-1.0。

## 免责声明

> 本清单由自动化工具生成，不构成法律意见（非法律意见）。涉及商业分发、诉讼或高价值交易时，请咨询执业律师。
