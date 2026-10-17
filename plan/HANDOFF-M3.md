# HANDOFF-M3：进入「场景判定」

> 上一棒：M2 画像矩阵（2026-10-17 完成）。本文件是下一棒的**唯一入口**。
> 库内一律相对路径；用户侧启动命令用绝对路径指向本文件。

## 一、当前进度与证据

### 已交付

| 交付物 | 位置 | 证据 |
| --- | --- | --- |
| SPDX 快照（3.29.0） | `references/spdx/` | 50 文件；`manifest.json` 记 sha256、`captured_on=2026-10-17` |
| curated 人工表 | `references/curated/` | `tiers.json` 48 条（带 `anchor.quote`/`checked_on`）、`trove-map.json` 7 条、`trap-packages.json` 4 条 |
| 规则包 r0.1.0 | `references/ruleset/` | 6 份文件 + manifest；48/48 条过锚点门，`disabled=0` |
| 三个 M1 生成器 | `tools/` | `fetch_spdx.py` / `gen_ruleset.py` / `gen_synthetic.py`，`--check` 两层 |
| M1 解析器 + `scan` | `src/licaudit/inventory/`、`pipeline.py` | 六形态分派、四级可信度链、SPDX 表达式；产 `inventory.json` |
| **M2 画像引擎** | `src/licaudit/assess/profile.py` | 原子拆分、档位查表、OSI/FSF、条款锚点、待确认原因码 |
| **`assess --profile-only`** | `src/licaudit/pipeline.py`、`cli.py` | 产 `profile.json`；有待确认 → exit 1，全覆盖 → exit 0 |
| **画像真值生成器** | `tools/gen_profile_truth.py` | 由 curated 规则表直接推导；`--check` 两层 |
| **画像真值** | `data/truth/profile.json` | 52 个输入 ID → 48 覆盖 + 4 未覆盖 |
| **`bench --only m2`** | `src/licaudit/verify.py` | `verify_profile`：52/52 命中 |
| 测试 | `tests/` | 双解释器 **288 passed, 1 skipped** |
| 变异脚本 | `tools/_mutate_m2.py` | 9 组「弄坏 → 变红 → 恢复 → 变绿」（一次性，不入发布面） |

### 实测记录（当轮真跑）

```
py -3.8  -X utf8 -m pytest -q                     → 288 passed, 1 skipped
py -3.12 -X utf8 -m pytest -q                     → 288 passed, 1 skipped

PYTHONPATH=src py -3.12 -X utf8 -m licaudit --version          → rc=0
PYTHONPATH=src py -3.12 -X utf8 -m licaudit status             → rc=0
PYTHONPATH=src py -3.12 -X utf8 -m licaudit verify-data        → rc=0（11 用例 / 44 记录 / F1 1.0）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m1    → rc=0
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m2    → rc=0（条目 52 / 命中 52）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench              → rc=0（m1 + m2）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m3    → rc=2（尚未实现，不装通过）

# 端到端
licaudit scan data/synthetic/npm-basic/package.json --out-dir out      → rc=0
licaudit assess --inventory out/inventory.json --profile-only --out-dir out → rc=0（2 原子 / 2 有档位）
licaudit scan data/synthetic/expr-complex/package.json --out-dir out   → rc=0
licaudit assess --inventory out/inventory.json --profile-only --out-dir out → rc=0（4 原子，表达式已拆）
licaudit assess --inventory out/inventory.json --scenario saas --outbound-license pending → rc=2（M3–M4 未实现）

# 退出码语义
licaudit --rules-dir nope status                                → rc=3（显式目录无效不回退）
全采样集（含未覆盖 ID）assess --profile-only                     → rc=1（有待确认项）
仅覆盖 ID 的清单 assess --profile-only                          → rc=0

py -3.12 tools/fetch_spdx.py --check --out references/spdx      → rc=0
py -3.12 tools/gen_ruleset.py --check                           → rc=0
py -3.12 tools/gen_synthetic.py --check                         → rc=0
py -3.12 tools/gen_profile_truth.py --check                     → rc=0
```

`1 skipped` = `test_trap_case_is_absent_from_example_project`（`example-project` 属 M5）。

### 变异验证（全部「弄坏 → 变红 → 恢复 → 变绿」，`tools/_mutate_m2.py` 实测）

| # | 弄坏什么 | 变红的测试 |
| --- | --- | --- |
| 1 | 档位判定读 `is_fsf_libre` | `test_fsf_libre_does_not_participate_in_judgement` |
| 2 | OSI 状态不查快照、恒 `True` | `test_osi_and_fsf_come_from_snapshot_only` |
| 3 | `_is_disabled_entry` 恒不拒 | `test_disabled_rule_never_produces_a_tier`、`test_engine_ignores_unverified_rule_even_if_caller_bypasses_loader` |
| 4 | 义务项按规则表原序输出 | `test_tier_and_obligations_come_from_ruleset` |
| 5 | 表达式不拆原子 | `test_expression_is_split_into_atoms` |
| 6 | 未覆盖 `reasons` 缺基码 `tier_uncovered` | `test_uncovered_id_gets_null_tier_and_pending` |
| 7 | 锚点 `quote` 被截断到 20 字符 | `test_every_tiered_profile_carries_locatable_anchor` |
| 8 | `bench m2` 恒判通过 | `test_bench_m2_turns_red_when_truth_drifts` |
| 9 | `pending_confirmation` 记录不进画像 | `test_pending_records_also_contribute_atoms` |

## 二、下一棒待办（M3）

按 `plan/03-模块详设.md` §M3 实现场景判定：

1. **`assess` 全量模式**：去掉 `_not_yet` 的 M3 分支；`--scenario` 与 `--outbound-license` 在
   非 `--profile-only` 模式下变为**必填**（现在是可选，因为画像不需要）。缺任一项 → `UsageError`（exit 2）。
2. **`assess/scenario.py`**：八场景 × `(delivery, link_mode)` 映射（`contract.SCENARIO_AXES` 已就位）、
   触发表查 `references/ruleset/scenario-triggers.json`（**目前是空表，需先在
   `references/curated/scenario-triggers.json` 写条目并重跑 `gen_ruleset.py`**）。
3. **用户回答必须落盘**：`scenario.json` 带 `network_interaction` / `answered_by` / `raw_answer`；
   不得由模型代填（K12/K14）。
4. **未回答或矛盾 → `pending_confirmation`**，不按最宽松默认（K14）。
5. **AGPL §13 独立触发点**：`saas` + `network_interaction=true` 即触发（K13）。
6. **`data/truth/scenario.json`**：八场景 × 链接方式判定表，由 curated 触发表直接推导。
7. **`bench --only m3`**：`verify.IMPLEMENTED_SUITES` 加 `m3`；同时把
   `test_bench_unimplemented_suite_is_usage_error`（现在用 `m3`）改成 `m4`，
   `test_verify_data.py` 里那条 `bench --only m3` 的断言同理。
8. 回写 `plan/00`、`plan/05`、`plan/06`；写 `plan/HANDOFF-M4.md`。

### M3 开工前必须知道的既有约束

- **`scenario-triggers.json` 目前是空表**（`entries: []`）。M3 的第一件事是补
  `references/curated/scenario-triggers.json` 并重跑 `tools/gen_ruleset.py`——规则包哈希会变，
  这是**预期变更**，`--check` 会先红后绿。
- 触发表条目的锚点必须能在 SPDX 全文里逐字定位（D20）。AGPL §13 的锚点可用
  `texts/AGPL-3.0-only.json#licenseText` 的 `"13. Remote Network Interaction"`。
- **`assess --profile-only` 的退出码语义不要改**：有待确认项 → 1。
  M3 全量模式的退出码另算（场景触发的阻断级属 M5 的处置分级）。
- `profile.json` 是 M3 的输入之一，字段序 == `contract.PROFILE_FIELDS`，不要新增顶层字段。

## 三、既定口径清单（动了会打挂测试）

完整 K 清单见 `plan/05-里程碑.md` §三。M3 直接相关的既有口径：

| 编号 | 口径 | 影响面 |
| --- | --- | --- |
| K7 | 五档枚举与顺序 | `contract.TIERS` / `TIER_RANK`；M3 只查表 |
| K9 | OSI/FSF 只从快照取；FSF 不参与判定 | `assess/profile.py`，M3 不要把它接进判定 |
| K10 | 未核验规则拒绝加载并显式输出 | `loader.py` + `profile._is_disabled_entry` 两道门 |
| K11 | 八场景 ID 与 `(delivery, link_mode)` 映射固定 | `contract.SCENARIO_AXES`；改一处要同步 4 处 |
| K12 | 「商用」不是输入项、不是触发条件 | 输入 schema + 测试断言无 `commercial` 字段 |
| K13 | AGPL §13 网络交互为独立触发点 | `scenario-triggers.json` |
| K14 | 未回答/矛盾 → `pending_confirmation`，不按最宽松默认 | `assess/scenario.py` |
| K24 | 规则包定位顺序；显式目录无效不回退 | `loader.locate_ruleset` |
| K26 | 真值只存输入与期望；`observed_*` 即红 | `verify.py` + 测试 |
| K27 | 生成物 `--check` 两层 | 四个生成器 |
| K31 | 画像按原子 ID 出；未覆盖不猜档位 | `assess/profile.py`（M3 直接消费，不要再拆一次） |
| K32 | 条款三态：无规则 = `null`，不是 `false` | `assess/profile.py` |

### M2 新增/收紧的口径（已登记 plan/06）

| 编号 | 内容 |
| --- | --- |
| D23 | 画像按原子 ID 出，M2 只拆不求值 |
| D24 | 条款三态：`null`（不知道）≠ `false`（没有此条款） |
| D25 | 画像退出码：有待确认项 → 1，全覆盖 → 0 |
| D26 | 画像真值由 curated 规则表直接推导，生成器不 import 生产引擎 |

## 四、本机环境坑（M1/M2 实测）

- **`py` 不是 `python`**（`python` 是商店占位符）。跑脚本一律 `py -3.12 -X utf8`。
- **本仓库未安装时用 `PYTHONPATH=src`**：`py -3.12 -m licaudit` 直接跑会 `No module named licaudit`。
- **多行 heredoc 写文件会被吞**：本机 Git Bash 对 `cat > file <<'PY'` 的收尾不稳，
  写脚本请用文件写入工具，或先写到临时文件再执行。
- **抓取 48 份全文约需 2–3 分钟**（串行 + 1s 退避）。别在前台用短超时跑。
- **显式 `--rules-dir` 指向空目录会 exit 3**，不会静默回退（D21）。
- **`references/spdx/` 是 2.8 MB 冻结数据**：`.gitattributes` 已标 `-text`，别让编辑器改行尾。
- **Windows 路径**：`os.path.relpath` 跨盘符会抛 `ValueError`；展示路径要兜底。
- **编码**：`encoding.ensure_utf8_stdio` 已按 `stream.encoding` 探针处理；CI 另设 `PYTHONUTF8=1`。
- **改生成器后必须重跑**：`gen_ruleset.py` 会重写 manifest 哈希；只改 curated 不重跑会让
  loader 报「哈希不一致」。

## 五、DoD 逐项 checklist（M2）

- [x] `assess --profile-only` 产 `profile.json`，字段序 == `contract.PROFILE_FIELDS`
- [x] 52 个原子 ID 全部有画像；48 条有档位 + 义务集合，4 条 `tier: null` + 待确认
- [x] 每条有档位的画像挂可定位锚点（`evidence.license_text_anchor`）与 `checked_on`
- [x] 无锚点/未核验规则**不生效**且 `disabled_rules` 可见（两道门 + 变异 3）
- [x] 未覆盖 ID 不猜档位（`tier_uncovered`）
- [x] OSI/FSF 只从 SPDX 快照取；FSF 不参与判定（变异 1/2）
- [x] 表达式先拆原子；`-only` / `-or-later` 原样保留；`WITH` 只拆出许可证 ID
- [x] `data/truth/profile.json` 由 curated 规则表直接推导，`--check` 位级一致
- [x] `bench --only m2` 52/52；`bench` 默认跑 m1 + m2
- [x] 纯函数：双跑逐字节一致
- [x] 双解释器 288 passed
- [x] 9 组变异验证
- [ ] **CI 首推**：配置已更新（含 `gen_profile_truth.py --check` 与 `bench --only m2`），
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

# 生成物自检
py -3.12 -X utf8 tools/fetch_spdx.py --check --out references/spdx
py -3.12 -X utf8 tools/gen_ruleset.py --check
py -3.12 -X utf8 tools/gen_synthetic.py --check
py -3.12 -X utf8 tools/gen_profile_truth.py --check

# 变异验证（一次性；会临时改源码再恢复）
py -3.12 -X utf8 tools/_mutate_m2.py

# 交付态入口
licaudit status
licaudit scan data/synthetic/npm-basic/package.json --out-dir out
licaudit assess --inventory out/inventory.json --profile-only --out-dir out
licaudit verify-data
licaudit bench --only m1
licaudit bench --only m2

# 未安装时（Skill 场景）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit assess --inventory out/inventory.json --profile-only --out-dir out
```

## 七、启动提示词（新对话用）

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M3.md" 继续完成任务
```
