# licaudit

开源许可证合规审查 Skill：读依赖清单，归一化为 SPDX 标识，结合分发 / 链接 / 网络交互判定传染与冲突，输出中文《第三方开源清单》。

> 当前状态：**M0–M5 已完成；M6 发布动作进行中**（tag 之前的留档见 [plan/RELEASE-M6.md](plan/RELEASE-M6.md)）。
> SPDX 快照、规则包（含场景触发表、冲突对表与处置决策表）、合成清单与四份真值库已冻结入仓；
> `scan` → `assess`（`profile.json` / `scenario.json` / `conflicts.json` / `actions.json`）→ `report`（MD / CSV）
> 全链可用；`verify-data` 与 `bench --only m1|m2|m3|m4|m5` 可跑。
> 里程碑与 DoD 见 [plan/05-里程碑.md](plan/05-里程碑.md)，示例报告见 [examples/report/license-report.md](examples/report/license-report.md)。

## 它解决什么

取证层（syft / scancode / ORT / license-checker）已经能告诉你「这个包是什么许可证」。
真正卡住人的是判定层：**我这个用法会不会被传染、要不要开源、能不能卖。**

本 Skill 只做判定层：

1. **归一化**：依赖清单 → SPDX 标识，四级可信度链，禁止全文关键词匹配。
2. **画像**：传染强度五档 + 义务项集合 + OSI/FSF 状态 + 专利/商标条款（M2 已交付）。
3. **场景**：八种交付形态 × 链接方式 × 网络交互 → 是否触发义务（M3 已交付）。
4. **冲突**：依赖之间、依赖与项目 outbound 许可证之间的不兼容（M4 已交付）。
5. **处置**：可直接用 / 需补声明 / 需隔离 / 需替换或取得商业授权，每条挂五个证据锚点（M5 已交付）。

## 安装

```bash
pip install -e ".[dev]"
```

要求 Python ≥ 3.8，运行时零第三方依赖。`dev` 只多一个 `pytest`。

发布物有两份源码包：

- **git clone**（推荐）：仓库根即 Skill 根，规则包在 `references/`，clone 后 `pip install -e ".[dev]"` 即可。
- **sdist**（`licaudit-0.1.0.tar.gz`）：解包后同样是完整的仓库快照——`MANIFEST.in` 明确把
  `references/`（规则包 + SPDX 快照）、`data/`（合成清单与真值）、`examples/`、`plan/`、`tools/`
  一起打进源码包，因此解包 → `pip install -e .` → `licaudit status` 直接可用。
  （D12 的「规则包不打进 wheel」只约束 wheel，见 [plan/02-架构与技术选型.md](plan/02-架构与技术选型.md) §1.2。）

## 快速开始

### 现在就能跑（M1–M5）

```bash
# 1. 只跑纯内部不变量自检
licaudit selftest --core

# 2. 规则包与快照状态
licaudit status

# 3. 扫描依赖清单 → inventory.json
licaudit scan data/synthetic/npm-basic/package.json --out-dir out

# 4. 依赖许可证画像矩阵 → profile.json（M2）
licaudit assess --inventory out/inventory.json --profile-only --out-dir out

# 5. 场景判定 + 冲突 + 处置分级 → scenario.json + conflicts.json + actions.json（M3 / M4 / M5）
#    --outbound-license 写项目准备采用的 SPDX 表达式；尚未决定就写 pending
licaudit assess --inventory out/inventory.json --scenario saas \
  --network-interaction yes --outbound-license MIT \
  --scenario-note "用户原话：我们通过 Web 提供服务" --out-dir out

# 6. 中文《第三方开源清单》 → license-report.md / license-report.csv（M5）
licaudit report --out-dir out --format md
licaudit report --out-dir out --format csv

# 7. 用参照实现对账冻结真值库
licaudit verify-data

# 8. 内置基准（M1 / M2 / M3 / M4 / M5）
licaudit bench --only m1
licaudit bench --only m2
licaudit bench --only m3
licaudit bench --only m4
licaudit bench --only m5
```

未安装时的等价入口（启动器会把仓库 `src` 放进 `sys.path`）：

```bash
py -3.12 scripts/launcher_licaudit.py selftest --core
PYTHONPATH=src python -m licaudit selftest --core
```

**未安装时 `python -m licaudit` 会报 `No module named licaudit`**——模块方式依赖安装；
Skill 场景（agent 直接读仓库）用启动器，或设置 `PYTHONPATH=src`。

### 退出码要看全量产物

`assess` 全量模式（不是 `--profile-only`）的退出码是**四份产物的聚合**：

- 任一依赖的许可证未覆盖、场景未回答 / 矛盾 → `1`（待人工确认）；
- 任一冲突条目 `pending` 或 `incompatible` → `1`；
- 任一处置条目为 `isolate` / `replace_or_license`（阻断级）→ `1`；
  五锚点（包名 / 版本 / 声明位置 / SPDX ID / 依据条款）缺任一 → 该条不进处置建议并 → `1`；
- `--outbound-license pending` → 冲突与处置全部待定 → 一律 `1`（**规定行为**，不是故障）；
- 全部相容、处置只有 `ok` / `declare` 且无待确认项 → `0`。

摘要里会分别打印「待确认（不猜判定）」「待确认（不猜兼容性）」「待确认（五锚点缺项 / 输入未定）」
三行，便于定位原因。`report` 的退出码与该报告内容一致：有阻断级或待确认项 → `1`。

## 数据与规则包

| 目录 | 内容 | 生成方式 |
| --- | --- | --- |
| `references/spdx/` | SPDX 3.29.0 快照（740 条许可 + 86 条例外 + 48 份全文） | `py -3.12 tools/fetch_spdx.py --out references/spdx` |
| `references/curated/` | 人工核对表（档位/义务/锚点、trove 映射、场景触发、冲突对、处置决策表、坑位元数据） | 人工维护 |
| `references/ruleset/` | 生成物（**禁手改**） | `py -3.12 tools/gen_ruleset.py` |
| `data/synthetic/` | 合成依赖清单（12 个用例，含 M5 示例项目） | `py -3.12 tools/gen_synthetic.py` |
| `data/truth/` | 冻结真值（只存输入与期望） | `gen_synthetic.py`（解析）+ `gen_profile_truth.py`（画像）+ `gen_scenario_truth.py`（场景）+ `gen_conflict_truth.py`（冲突）+ `gen_action_truth.py`（处置） |
| `examples/report/` | 入仓示例报告（MD / CSV 各两份运行） | `scan → assess → report`，测试里逐字节复现 |

七个生成器都支持 `--check`：重生成到临时目录并**逐字节**比对冻结产物。

```bash
py -3.12 -X utf8 tools/fetch_spdx.py --check --out references/spdx
py -3.12 -X utf8 tools/gen_ruleset.py --check
py -3.12 -X utf8 tools/gen_synthetic.py --check
py -3.12 -X utf8 tools/gen_profile_truth.py --check
py -3.12 -X utf8 tools/gen_scenario_truth.py --check
py -3.12 -X utf8 tools/gen_conflict_truth.py --check
py -3.12 -X utf8 tools/gen_action_truth.py --check
```

## 退出码

| 码 | 含义 |
| --- | --- |
| `0` | 分析完成且无阻断项 |
| `1` | 分析完成，检出阻断/隔离级项（既定语义，不是故障）；或自检/基准未通过 |
| `2` | 用法错误、输入不可用、未知许可证 ID |
| `3` | 规则包缺失或校验失败 |

## 场景（八种）

`internal` 内部使用 / `distribute-binary` 分发二进制 / `distribute-source` 分发源码 / `saas` /
`static-link` 静态链接 / `dynamic-link` 动态链接 / `separate-process` 独立进程 / `container-image` 容器镜像

**商用本身不是 GPL / AGPL 的触发要件。** 触发点是分发（GPL 系）与网络交互（AGPL §13，独立触发点）。

## 发布与留档

| 项 | 值 |
| --- | --- |
| 版本 | `v0.1.0`（包版本 `0.1.0`，`pyproject.toml`） |
| 规则包 | `ruleset_version = r0.1.0`，`licenseListVersion = 3.29.0` |
| 发布三件套 | `plan/RELEASE-M6.md`（tag 前入库）+ git tag + GitHub Release（附真实产物） |
| 产物校验 | `tools/check_release.py`（离线自查 + `--online` 核对 tag / Release 附件 / sha256） |

```bash
# 离线发布终态自检（不联网）：留档两栏、tag 与版本一致、状态表已翻转
py -3.12 -X utf8 tools/check_release.py

# 联网核对：tag 是否推送、Release 附件是否与留档登记的 sha256 一致
py -3.12 -X utf8 tools/check_release.py --online
```

## 目录

```
SKILL.md              agent 入口与契约块
src/licaudit/         确定性引擎（纯标准库）
scripts/              Skill 场景启动器
references/           SPDX 快照 + 规则包（数据，不是代码）
data/                 合成清单与真值（M1 起）
examples/report/      入仓示例报告（M5）
tests/                pytest
tools/                生成器与发布自检（不是用户 CLI）
plan/                 计划、决策、里程碑、留档
MANIFEST.in           sdist 清单（让源码包自带 references/ 规则包）
```

## 隐私

纯本地处理：不联网、不上传依赖清单、不读取用户主目录。SPDX 快照随仓库冻结，刷新是人工生成步骤。

## 限制

- 不做源码许可头扫描、不生成 SBOM、不做 CVE 评分。
- 只覆盖清单里出现的许可证；未覆盖 ID 输出 `tier: null` + 待人工确认。
- 冲突对表是**抽样**的 4 条（GPL-2.0 × Apache-2.0 / AGPL-3.0 / GPL-3.0，GPL-3.0 × Apache-2.0）；
  未登记的许可证组合只计入 `conflicts.json.uncovered_pairs`（不判不猜）。
- 依赖 × outbound 是**档位级粗判**：例如 `MPL-2.0` 依赖 + `MIT` outbound 会输出 `incompatible`；
  判据暂不看场景是否真的分发。**传染范围聚合（按链接/分发边界）仍未实现**：
  处置分级改用决策表的 `link_mode` 维度表达「边界是否可分离」，`conflicts.json.notes` 与
  `actions.json.notes` 里都有明文登记。
- 处置决策表只有 8 条规则（义务轴 + 冲突结论 + 链接方式 → 四级处置），是**抽样口径**；
  单场景下四级处置无法同时出现（`declare` 需要 SaaS + source-available outbound，
  `replace_or_license` 需要依赖间不兼容对或同许可义务与不相容 outbound），示例报告因此给两份运行。
- 首期发布形态是源码包 / git clone + editable 安装。**不支持 wheel 安装后直接使用**——规则包在仓库 `references/`，wheel 不含它；需要时用 `--rules-dir` 显式指定。sdist 走 `MANIFEST.in` 白名单，自带 `references/` 规则包与快照，解包即自足。
- 规则包缺失 / 校验失败一律 `exit 3`，不会产出空报告。

## 许可

本项目代码以 MIT 发布（见 [LICENSE](LICENSE)）。`references/spdx/` 下的 SPDX 数据来自
<https://spdx.org/licenses/>，遵循 CC0-1.0。

## 免责声明

> 本清单由自动化工具生成，不构成法律意见（非法律意见）。涉及商业分发、诉讼或高价值交易时，请咨询执业律师。
