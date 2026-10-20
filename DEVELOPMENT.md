# DEVELOPMENT — licaudit 开发细节索引

> 本文件**只做索引与现状摘要**，不复制 `plan/` 下的内容（避免双份维护）。
> 里程碑 / DoD 的**唯一状态表**在 [plan/05-里程碑.md](plan/05-里程碑.md)；架构细节在
> [plan/02-架构与技术选型.md](plan/02-架构与技术选型.md)；模块级口径在 [plan/03-模块详设.md](plan/03-模块详设.md)。
> 面向用户的功能说明、判定依据与已知限制在 [README.md](README.md)。

---

## 一、按需查哪份文档

| 想了解 | 看这里 |
| --- | --- |
| 这个项目是什么、给谁用、怎么跑 | [README.md](README.md) |
| 里程碑 M0–M6 与 DoD、K 口径清单（唯一一份） | [plan/05-里程碑.md](plan/05-里程碑.md) |
| 交付形态、分层架构、目录结构、退出码契约、技术选型 | [plan/02-架构与技术选型.md](plan/02-架构与技术选型.md) |
| M1–M5 实现级设计、判定语义总纲、失败路径 | [plan/03-模块详设.md](plan/03-模块详设.md) |
| SPDX 快照、规则包生成、合成清单与真值、冻结纪律 | [plan/04-数据计划.md](plan/04-数据计划.md)、[data/README.md](data/README.md) |
| 评分对标、决策记录 D1–D36、待定决策、风险 | [plan/06-交付对标与决策记录.md](plan/06-交付对标与决策记录.md) |
| 十段式题目定稿（历史文档，不改写） | [plan/01-题目文档.md](plan/01-题目文档.md) |
| 阶段交接记录（M0→M6 逐棒唯一入口） | [plan/HANDOFF-M1.md](plan/HANDOFF-M1.md) … [plan/HANDOFF-M6.md](plan/HANDOFF-M6.md) |
| `v0.1.0` 发布留档（tag 时点事实 + tag 后追加事实） | [plan/RELEASE-M6.md](plan/RELEASE-M6.md) |
| agent 入口与契约块（Skill 形态） | [SKILL.md](SKILL.md) |
| 计划总览与文档索引 | [plan/00-README总览.md](plan/00-README总览.md) |

---

## 二、架构分层（摘要，细节见 plan/02）

```
SKILL.md                agent 入口与契约块（触发条件 / 工作流 / 退出码）
scripts/launcher_licaudit.py   Skill 场景薄启动器（编码守卫 + 转交包内 main）
src/licaudit/           确定性引擎（纯标准库，零运行时依赖）
  inventory/            清单解析与 SPDX 归一化（四级可信度链）
  assess/               画像 / 场景 / 冲突 / 处置（M2–M5）
  report/               中文清单渲染（MD / CSV，同源）
references/             数据不是代码：spdx 快照 + curated 人工表 + ruleset 生成物
data/                   合成清单与冻结真值（只存输入与期望）
tests/                  pytest（双解释器）
tools/                  生成器与发布自检（不是用户 CLI）
```

判定链：`scan` → `assess`（`profile.json` → `scenario.json` → `conflicts.json` → `actions.json`）
→ `report`。三种调用方式（控制台脚本 / `python -m` / 启动器）语义完全等价，见 plan/02 §一。

---

## 三、CI 矩阵

工作流：`.github/workflows/ci.yml`。矩阵 `os × python`：
`ubuntu-latest` 与 `windows-latest` 各跑 `3.12` 共 2 个 job
（2026-10-20 起：floor 由 3.8 抬到 3.12，原因见 `plan/06` D39；actions 用 `checkout@v7` /
`setup-python@v7`）；
job env 统一 `PYTHONUTF8=1`、`PYTHONDONTWRITEBYTECODE=1`。
步骤：`pip install -e ".[dev]"` → `pytest`（addopts 已是 `-q`，CI 不再叠 `-q`）。

本机等价命令（`py` 而非 `python`；本机 `python` 指向 Store stub）：

```bash
py -3.12 -m pytest -q
py -3.12 -X utf8 tools/gen_ruleset.py --check
```

---

## 四、规则包与快照的生成流程（细节见 plan/04）

七个生成器全部支持 `--check`：重生成到临时目录并**逐字节**比对冻结产物。

```bash
py -3.12 -X utf8 tools/fetch_spdx.py --out references/spdx      # SPDX 快照
py -3.12 -X utf8 tools/gen_ruleset.py                            # 规则包（禁手改）
py -3.12 -X utf8 tools/gen_synthetic.py                          # 合成清单 + 真值
py -3.12 -X utf8 tools/gen_profile_truth.py
py -3.12 -X utf8 tools/gen_scenario_truth.py
py -3.12 -X utf8 tools/gen_conflict_truth.py
py -3.12 -X utf8 tools/gen_action_truth.py
```

| 目录 | 内容 | 生成方式 |
| --- | --- | --- |
| `references/spdx/` | SPDX 3.29.0 快照（740 条许可 + 86 条例外 + 48 份全文） | `tools/fetch_spdx.py` |
| `references/curated/` | 人工核对表（档位/义务/锚点、trove 映射、场景触发、冲突对、处置决策表） | 人工维护 |
| `references/ruleset/` | 生成物（**禁手改**） | `tools/gen_ruleset.py` |
| `data/synthetic/` | 合成依赖清单（12 个用例） | `tools/gen_synthetic.py` |
| `data/truth/` | 冻结真值（只存输入与期望） | 五个 `gen_*_truth.py` |
| `examples/report/` | 入仓示例报告（MD / CSV 各两份运行） | `scan → assess → report`，测试逐字节复现 |

---

## 五、发布对账

发布留档（机器可读契约）：[plan/RELEASE-M6.md](plan/RELEASE-M6.md)，由 `tools/check_release.py` 按契约核对。

```bash
py -3.12 -X utf8 tools/check_release.py            # 离线：留档两栏 / tag 与版本一致 / 状态表已翻转
py -3.12 -X utf8 tools/check_release.py --online   # 联网：tag 已推 / Release 附件与登记的 sha256 一致
```

| 项 | 值 |
| --- | --- |
| 版本 | `v0.1.0`（包版本 `0.1.0`，`pyproject.toml`） |
| 规则包 | `ruleset_version = r0.1.0`，`licenseListVersion = 3.29.0` |
| 发布三件套 | `plan/RELEASE-M6.md`（tag 前入库）+ git tag + GitHub Release（附真实产物） |

---

## 六、本地开发约定

- 运行校验脚本用 `py`（本机 `python` 是 Windows Store stub，不可用）。
- 编码：所有工具链命令带 `-X utf8`；落盘文本统一 `\n`。
- 数据目录严格分层：`references/` 是数据不是代码，`ruleset/` 禁手改，改 `curated/` 后必须重生成并跑 `--check`。