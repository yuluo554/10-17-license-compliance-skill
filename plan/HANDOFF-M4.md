# HANDOFF-M4：进入「冲突与兼容性分析」

> 上一棒：M3 场景判定（2026-10-17 完成）。本文件是下一棒的**唯一入口**。
> 库内一律相对路径；用户侧启动命令用绝对路径指向本文件。
> **注意**：本轮未要求 commit，工作区保留全部变更（其中也包含上一棒 M2 尚未提交的部分）。

## 一、当前进度与证据

### 已交付

| 交付物 | 位置 | 证据 |
| --- | --- | --- |
| SPDX 快照（3.29.0） | `references/spdx/` | 50 文件；`manifest.json` 记 sha256、`captured_on=2026-10-17` |
| curated 人工表 | `references/curated/` | `tiers.json` 48 条、`trove-map.json` 7 条、`trap-packages.json` 4 条、**`scenario-triggers.json` 6 条** |
| 规则包 r0.1.0 | `references/ruleset/` | 6 份文件 + manifest；48/48 条档位规则 + **6/6 条场景触发规则**过锚点门，`disabled=0` |
| 五个生成器 | `tools/` | `fetch_spdx.py` / `gen_ruleset.py` / `gen_synthetic.py` / `gen_profile_truth.py` / **`gen_scenario_truth.py`**，`--check` 各两层 |
| M1 解析器 + `scan` | `src/licaudit/inventory/`、`pipeline.py` | 六形态分派、四级可信度链、SPDX 表达式；产 `inventory.json` |
| M2 画像引擎 | `src/licaudit/assess/profile.py` | 原子拆分、档位查表、OSI/FSF、条款锚点、待确认原因码 |
| **M3 场景引擎** | `src/licaudit/assess/scenario.py` | 场景轴解析、`(delivery, link_mode)` 归一、触发查表、三态结论、用户回答落盘 |
| **`assess` 全量模式** | `src/licaudit/pipeline.py`、`cli.py` | 产 `profile.json` + `scenario.json`；`--scenario` 与 `--outbound-license` 必填 |
| **场景真值生成器** | `tools/gen_scenario_truth.py` | 由 curated 触发表直接推导；`--check` 两层 |
| **场景真值** | `data/truth/scenario.json` | 230 行判定表 + 1 条 `tier: null`；6 条可用规则 |
| **`bench --only m3`** | `src/licaudit/verify.py` | `verify_scenario`：231/231 命中（含未实现套件断言已从 m3 换到 m4） |
| 测试 | `tests/` | 双解释器 **346 passed, 1 skipped** |
| 变异脚本 | `tools/_mutate_m3.py` | 9 组「弄坏 → 变红 → 恢复 → 变绿」（一次性，不入发布面） |

### 场景触发表（6 条，全部 `verified=true`、锚点可在 SPDX 全文逐字定位）

| 规则 id | 档位 | 触发 | 依据锚点 |
| --- | --- | --- | --- |
| `T-DIST-STRONG-001` | strong-copyleft | distribution | GPL-2.0-only §3(b) |
| `T-DIST-NET-001` | network-copyleft | distribution | AGPL-3.0-only §6 |
| `T-NET-001` | network-copyleft | network-interaction（需 `network_interaction: true`） | AGPL-3.0-only §13 |
| `T-DIST-WEAK-001` | weak-copyleft | distribution | MPL-2.0 §3.2 |
| `T-STATIC-WEAK-001` | weak-copyleft | static-link | LGPL-2.1-only §6 |
| `T-SA-HOSTED-001` | source-available | hosted-service-restriction | Elastic-2.0 Limitations |

宽松档（permissive）**不写条目 → 永不触发**；引擎没有档位特判（K4）。

### 实测记录（当轮真跑）

```
py -3.8  -X utf8 -m pytest          → 346 passed, 1 skipped
py -3.12 -X utf8 -m pytest          → 346 passed, 1 skipped

PYTHONPATH=src py -3.12 -X utf8 -m licaudit --version      → rc=0
PYTHONPATH=src py -3.12 -X utf8 -m licaudit status         → rc=0
PYTHONPATH=src py -3.12 -X utf8 -m licaudit verify-data    → rc=0（11 用例 / 44 记录 / F1 1.0）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m1 → rc=0
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m2 → rc=0（条目 52 / 命中 52）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m3 → rc=0（条目 231 / 命中 231）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench          → rc=0（m1 + m2 + m3）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit bench --only m4 → rc=2（尚未实现，不装通过）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit report          → rc=2（M5 未实现，不写占位产物）

# 端到端
licaudit scan data/synthetic/npm-basic/package.json --out-dir out        → rc=0
licaudit assess --inventory out/inventory.json --profile-only --out-dir out → rc=0
licaudit assess --inventory out/inventory.json --scenario saas \
  --network-interaction yes --outbound-license pending \
  --scenario-note "用户原话：我们通过 Web 提供服务" --out-dir out          → rc=1（含未覆盖 ID → 待确认）

# 退出码语义（未变）
licaudit --rules-dir nope status                                   → rc=3（显式目录无效不回退）
licaudit assess ... --scenario static-link（未给 --delivery）       → rc=1（待确认，不是默认交付形态）
licaudit assess ... --scenario saas（未答网络交互）                 → rc=1（待确认）
licaudit assess ... --scenario static-link --linking dynamic       → rc=2（场景与链接方式矛盾）

py -3.12 tools/fetch_spdx.py --check --out references/spdx → rc=0
py -3.12 tools/gen_ruleset.py --check                      → rc=0
py -3.12 tools/gen_synthetic.py --check                    → rc=0
py -3.12 tools/gen_profile_truth.py --check                → rc=0
py -3.12 tools/gen_scenario_truth.py --check               → rc=0
```

`1 skipped` = `test_trap_case_is_absent_from_example_project`（`example-project` 属 M5）。

### 变异验证（`tools/_mutate_m3.py` 实测，9 组全部「弄坏 → 变红 → 恢复 → 变绿」）

| # | 弄坏什么 | 变红的测试 |
| --- | --- | --- |
| 1 | 网络交互条目不再要求 `network_interaction=true` | `test_internal_agpl_without_network_interaction_does_not_trigger` 等 |
| 2 | SaaS 未回答网络交互时按「不触发」放过 | `test_saas_without_network_answer_is_pending` |
| 3 | 链接方式轴场景缺交付形态时不待确认 | `test_link_scenario_without_delivery_is_pending` |
| 4 | 触发匹配忽略 `link_modes` | `test_dynamic_link_of_weak_copyleft_triggers_distribution_not_static` |
| 5 | 触发匹配忽略 `scenarios` | `test_internal_use_does_not_trigger_copyleft` |
| 6 | 未覆盖档位不再待确认（改成猜 permissive） | `test_uncovered_id_is_pending_not_guessed` |
| 7 | disabled 触发条目照用 | `test_disabled_trigger_rule_never_produces_a_judgement` |
| 8 | 用户回答不落盘 | `test_user_answer_is_persisted_verbatim` |
| 9 | `bench m3` 恒判通过 | `test_bench_m3_turns_red_when_truth_drifts` |

`tools/_mutate_m2.py`（9 组）随规则包更新复跑仍全绿。

## 二、下一棒待办（M4）

按 `plan/03-模块详设.md` §M4 实现冲突与兼容性分析：

1. **`references/curated/conflict-pairs.json`**：补齐已知冲突对（至少 `CP-GPL2-APACHE2`：
   `GPL-2.0-only` × `Apache-2.0` 不兼容），每条带 `basis` + 可定位 `anchor` + `checked_on`；
   重跑 `tools/gen_ruleset.py`（哈希变更属预期）。
   **同时要改 `tools/gen_ruleset.py` 的 `build_conflict_pairs`**：现在只校验 pair_id/resolution，
   没有锚点门，也没校验 left/right 在 SPDX 快照里——按 tiers/触发表的同口径补上（D20）。
2. **`src/licaudit/assess/conflict.py`**：
   - 依赖间冲突：`conflict-pairs.json` **无向匹配**（`(left,right)` 与 `(right,left)` 等价，K15）；
   - 依赖 × outbound：outbound 已知 → 比档位/义务；`outbound = pending` → 全部 `pending`（K17，不猜）；
   - 表达式求值（K16）：`OR` 取最宽松、`AND` 取最严格（按 `contract.TIER_RANK`），
     `WITH` 保留例外标签；结果写 `expression_evaluations`，**不得只给最终 ID**；
   - `outbound` 校验直接复用 M3 的 `scenario.validate_outbound`（M3 已把未知 ID 挡在 exit 2）。
3. **`conflicts.json` 契约**：`pair_id` / `left` / `right` / `basis` / `resolution` / `evidence`；
   `resolution` 三态 `compatible` / `incompatible` / `pending`。顶层形态参照
   `profile.json` / `scenario.json`（`SCENARIO_TOP_LEVEL_FIELDS` 那种写法）。
4. **`assess` 全量模式接上冲突**：M3 已产 `profile.json` + `scenario.json`，M4 追加 `conflicts.json`；
   退出码：任一 `pending` 或 `incompatible` → 1（plan/03 §六；阻断分级仍属 M5）。
5. **`data/truth/conflicts.json` + `tools/gen_conflict_truth.py`**：真值由 curated
   `conflict-pairs.json` **直接推导**，生成器不 import 生产冲突引擎；覆盖「已知冲突对全命中」
   「OR/AND 求值」「outbound = pending → 全部 pending」三侧。
6. **`bench --only m4`**：`verify.IMPLEMENTED_SUITES` 加 `m4`；把
   `tests/test_verify_data.py::test_bench_unimplemented_suite_is_usage_error` 从 `m4` 改成 `m5`。
7. **`tests/test_conflict.py`**：冲突对无向、表达式求值、outbound pending、字段序 ==
   `contract.CONFLICT_FIELDS`、双跑逐字节一致、`bench m4` 阳性/阴性对照。
8. **M3 遗留的跨里程碑问题要在 M4 拍板**：M3 对「原子结论不一致」的表达式依赖输出
   `pending_confirmation`（`expression_unresolved`）。M4 有了求值规则后，需要决定
   **是回填 scenario 判定，还是维持待确认**；无论选哪个都写进 `plan/06`（D32）并加测试。
9. 回写 `plan/00`、`plan/03`（§4 落地补充）、`plan/05`、`plan/06`；写 `plan/HANDOFF-M5.md`。

### M4 开工前必须知道的既有约束

- **`conflict-pairs.json` 目前是空表**（`entries: []`），loader 策略是 `anchor`：
  条目必须有 `verified=true` + `anchor`（source/ref）+ `checked_on`，否则被拒进 `disabled`。
- `assess` 全量模式**已经要求** `--outbound-license`（M3 起），并在 M3 校验到「快照内 SPDX
  表达式或 `pending`」；M4 不要重复实现，但要把 `pending` 的语义（全部待定）落实。
- **`conflicts.json` 不得靠 profile/scenario 的字段倒推**；三者都只消费 `inventory` + 规则包。
- 报告层（M5）零判定守门（K23）：`report/` 不许 import `inventory` / `assess`；这是 M5 的事，
  M4 只要保证 `conflicts.json` 自带 `basis` + 锚点即可。
- 场景真值（`data/truth/scenario.json`）由 curated 触发表推导；**改触发表要同时重跑
  `gen_ruleset.py` 与 `gen_scenario_truth.py`**，否则 `--check` 会红。

## 三、既定口径清单（动了会打挂测试）

完整 K 清单见 `plan/05-里程碑.md` §三。M4 直接相关的既有口径：

| 编号 | 口径 | 影响面 |
| --- | --- | --- |
| K7 | 五档枚举与顺序 | `contract.TIERS` / `TIER_RANK`；表达式求值按它排序 |
| K11 | 八场景 ID 与 `(delivery, link_mode)` 映射固定 | `contract.SCENARIO_AXES`；触发表按交付形态场景匹配 |
| K12 | 「商用」不是输入项、不是触发条件 | 输入 schema + 测试断言无 `commercial` |
| K13 | AGPL §13 网络交互为独立触发点 | `scenario-triggers.json` 的 `network_interaction` |
| K14 | 未回答/矛盾 → `pending_confirmation`，不按最宽松默认 | `assess/scenario.py`（M4 的 pending 同口径） |
| K15 | 冲突对无向匹配；`pair_id` 唯一 | `curated/conflict-pairs.json`（M4 新锁） |
| K16 | `OR` 取最宽松、`AND` 取最严格（按 K7 档位序） | `assess/conflict.py`（M4 新锁） |
| K17 | outbound 未提供 → exit 2；outbound = `pending` → 全部条目 `pending` | `assess/conflict.py` |
| K24 | 规则包定位顺序；显式目录无效不回退 | `loader.locate_ruleset` |
| K26 | 真值只存输入与期望；`observed_*` 即红 | `verify.py` + 测试 |
| K27 | 生成物 `--check` 两层 | 五个生成器 |
| K31 | 画像按原子 ID 出；未覆盖不猜档位 | `assess/profile.py`（M4 直接消费） |
| K32 | 条款三态：无规则 = `null`，不是 `false` | `assess/profile.py` |

### M3 新增/收紧的口径（已登记 plan/06）

| 编号 | 内容 |
| --- | --- |
| D27 | 触发表按交付形态场景匹配，链接方式为第二维；`--scenario` 与 `--delivery`+`--linking` 等价，矛盾 → exit 2 |
| D28 | 未回答/矛盾一律 `pending_confirmation`，不取宽松默认（SaaS 未答、链接轴缺交付形态、container-image 网络未答） |
| D29 | M3 只收 outbound、不判兼容性；`pending` 或快照内 SPDX 表达式以外的值 → exit 2 |
| D30 | 全量模式退出码：有待确认项 → 1；触发本身不改退出码（阻断分级属 M5） |
| D31 | 表达式求值仍属 M4；原子结论不一致 → `expression_unresolved` 待确认 |

## 四、本机环境坑（M1–M3 实测）

- **`py` 不是 `python`**（`python` 是商店占位符）。跑脚本一律 `py -3.12 -X utf8`。
- **本仓库未安装时用 `PYTHONPATH=src`**：`py -3.12 -m licaudit` 直接跑会 `No module named licaudit`。
- **多行 heredoc 写文件会被吞**：本机 Git Bash 对 `cat > file <<'PY'` 的收尾不稳，
  写脚本请用文件写入工具，或先写到临时文件再执行。
- **改 curated 必须重跑生成器**：`gen_ruleset.py` 重写 manifest 哈希；场景触发条目还要重跑
  `gen_scenario_truth.py`（真值是触发表的投影）。只改一处会让 `--check` 变红。
- **链接方式轴场景必须给交付形态**：`--scenario static-link` 不带 `--delivery` → 全部待确认（exit 1），
  这是 K14 的行为，不是 bug；测试里要跑 `--scenario static-link --delivery binary`。
- **`saas` 必须回答网络交互**：不答 → 整批待确认（exit 1）；答 `no` 是矛盾 → 同样待确认。
- **显式 `--rules-dir` 指向空目录会 exit 3**，不会静默回退（D21）。
- **`references/spdx/` 是 2.8 MB 冻结数据**：`.gitattributes` 已标 `-text`，别让编辑器改行尾。
- **Windows 路径**：`os.path.relpath` 跨盘符会抛 `ValueError`；展示路径要兜底。
- **编码**：`encoding.ensure_utf8_stdio` 已按 `stream.encoding` 探针处理；CI 另设 `PYTHONUTF8=1`。
- **变异脚本是一次性的**：`_mutate_m2.py` / `_mutate_m3.py` 会临时改源码再恢复；
  跑完务必复跑一次全量测试确认恢复无损。

## 五、DoD 逐项 checklist（M3）

- [x] 八场景 × 链接方式判定表全绿：`bench --only m3` 231/231（230 行判定表 + 1 条 `tier: null`）
- [x] SaaS 未分发但网络交互 → 触发（`T-NET-001` / `network-source`）
- [x] GPL 在 SaaS 未被网络误触发（反例锁定）
- [x] 「商用」不在输入字段、不是触发条件（产物 / 规则表 / CLI 三处断言）
- [x] 未回答/矛盾 → 待确认：SaaS 未答、SaaS 答 no、链接轴缺交付形态、未覆盖档位、表达式不一致
- [x] 用户回答原样落盘：`network_interaction` / `answered_by` / `raw_answer` / `outbound_license`
- [x] 触发表 6/6 条锚点可在 SPDX 全文逐字定位；`disabled=0`
- [x] `data/truth/scenario.json` 由 curated 触发表直接推导，`--check` 位级一致
- [x] `scenario.json` 字段序 == `contract.SCENARIO_FIELDS`
- [x] 纯函数：双跑逐字节一致
- [x] 双解释器 346 passed
- [x] 9 组变异验证（`tools/_mutate_m3.py`）
- [ ] **CI 首推**：配置已更新（含 `gen_scenario_truth.py --check` 与 `bench --only m3`），
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

# 生成物自检
py -3.12 -X utf8 tools/fetch_spdx.py --check --out references/spdx
py -3.12 -X utf8 tools/gen_ruleset.py --check
py -3.12 -X utf8 tools/gen_synthetic.py --check
py -3.12 -X utf8 tools/gen_profile_truth.py --check
py -3.12 -X utf8 tools/gen_scenario_truth.py --check

# 变异验证（一次性；会临时改源码再恢复）
py -3.12 -X utf8 tools/_mutate_m2.py
py -3.12 -X utf8 tools/_mutate_m3.py

# 交付态入口
licaudit status
licaudit scan data/synthetic/npm-basic/package.json --out-dir out
licaudit assess --inventory out/inventory.json --profile-only --out-dir out
licaudit assess --inventory out/inventory.json --scenario saas \
  --network-interaction yes --outbound-license pending --scenario-note "用户原话" --out-dir out
licaudit assess --inventory out/inventory.json --scenario static-link \
  --delivery binary --outbound-license pending --scenario-note "分发 + 静态链接" --out-dir out
licaudit verify-data
licaudit bench --only m1
licaudit bench --only m2
licaudit bench --only m3

# 未安装时（Skill 场景）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit assess --inventory out/inventory.json \
  --scenario saas --network-interaction yes --outbound-license pending \
  --scenario-note "用户原话" --out-dir out
```

## 七、启动提示词（新对话用）

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M4.md" 继续完成任务
```
