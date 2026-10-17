# HANDOFF-M2：进入「画像矩阵」

> 上一棒：M1 数据先行 + M1 解析（2026-10-17 完成）。本文件是下一棒的**唯一入口**。
> 库内一律相对路径；用户侧启动命令用绝对路径指向本文件。

## 一、当前进度与证据

### 已交付

| 交付物 | 位置 | 证据 |
| --- | --- | --- |
| SPDX 快照（3.29.0） | `references/spdx/` | 50 文件：2 份清单（740 许可 / 86 例外）+ 48 份按需全文；`manifest.json` 记 sha256、`captured_on=2026-10-17` |
| curated 人工表 | `references/curated/` | `tiers.json` 48 条（每条带 `anchor.quote`/`checked_on`/`verified`）、`trove-map.json` 7 条、`trap-packages.json` 4 条 |
| 规则包 r0.1.0 | `references/ruleset/` | 6 份文件 + manifest；48/48 条过锚点门，`disabled=0` |
| 抓取器 | `tools/fetch_spdx.py` | 重试 ≤3、失败不写半份、`--check` 离线校验 |
| 规则包生成器 | `tools/gen_ruleset.py` | 锚点 quote 必须在原文可定位；`--check` 两层；双计数覆盖登记 |
| 合成数据生成器 | `tools/gen_synthetic.py` | splitmix64 + 独立朴素 oracle；`--check` 两层 |
| 合成清单与真值 | `data/synthetic/`、`data/truth/` | 11 用例 / 44 条期望；坑位 4 条真实包名 |
| M1 解析器 | `src/licaudit/inventory/` | 六形态分派、四级可信度链、SPDX 表达式、受限 TOML、带行号 JSON |
| `scan` 命令 | `src/licaudit/pipeline.py` | 产 `inventory.json`（字段序 == contract） |
| `verify-data` / `bench` | `src/licaudit/verify.py` | 读冻结真值复算；F1 实算并卡 0.95 阈值 |
| 测试 | `tests/` | 双解释器 **247 passed, 1 skipped** |

### 实测记录（当轮真跑）

```
py -3.8  -X utf8 -m pytest -q                     → 247 passed, 1 skipped
py -3.12 -X utf8 -m pytest -q                     → 247 passed, 1 skipped
干净 venv + pip install -e ".[dev]"               → 装好可用

licaudit --version                                → rc=0
licaudit selftest --core                          → rc=0
licaudit selftest                                 → rc=0（规则包可加载）
licaudit status                                   → rc=0（tiers=48, disabled=0）
licaudit scan data/synthetic/npm-basic/package.json --out-dir out → rc=0
licaudit verify-data                              → rc=0（11 用例 / 44 记录 / 命中 44 / F1 1.0）
licaudit bench --only m1                          → rc=0
licaudit bench --only m3                          → rc=2（尚未实现，不装通过）
licaudit nope                                     → rc=2
licaudit --rules-dir does-not-exist status        → rc=3

py -3.12 tools/fetch_spdx.py --check --out references/spdx   → rc=0
py -3.12 tools/gen_ruleset.py --check                        → rc=0
py -3.12 tools/gen_synthetic.py --check                      → rc=0
```

`1 skipped` = `test_trap_case_is_absent_from_example_project`（`example-project` 属 M5）。

### 变异验证（全部「弄坏 → 变红 → 恢复 → 变绿」）

| # | 弄坏什么 | 变红的测试 |
| --- | --- | --- |
| 1 | 首行锚定去掉 200 字符上限 | `test_anchor_length_gate_rejects_over_200` |
| 2 | 生成器跳过 `texts.contains(quote)` | `test_anchor_locatability_gate_is_falsifiable`、`test_generator_marks_unlocatable_rule_as_unverified` |
| 3 | 兜底不再截断到 200 字符 | `test_truncated_fallback_keeps_first_200_chars_only` |
| 4 | 显式 `--rules-dir` 静默回退 | `test_explicit_rules_dir_does_not_fall_back`、4 条 exit-3 测试 |
| 5 | 关掉第 1 级表达式分支 | 6 条（四级链顺序 + 真值对账） |
| 6 | `verify-data` 恒返回 0 | 3 条（改真值 / `observed_*` / 输入缺失） |
| 7 | 无 `spdx_id` 时伪造 `details_url` | 4 条（含 `test_scan_unknown_family_has_no_fabricated_details_url`） |

## 二、下一棒待办（M2）

按 `plan/03-模块详设.md` §M2 实现画像矩阵：

1. **`assess --profile-only`**（或 `assess --profile`）：读 `inventory.json` + 规则包 + SPDX 快照，
   产出 `profile.json`（字段序 == `contract.PROFILE_FIELDS`）。
2. **原子 ID 拆分**：表达式先拆成原子（表达式求值属 M4，M2 只给原子画像）。
3. **档位与义务**：只从 `references/ruleset/tiers.json` 查表；未覆盖 ID → `tier: null` + 待确认，**不猜**。
4. **OSI / FSF**：只从 SPDX 快照取；FSF 不参与判定（测试断言判定函数不读该字段）。
5. **专利/商标条款**：沿用 curated 里已带锚点的 `patent_clause` / `trademark_clause`。
6. **`data/truth/profile.json`**：由 curated 规则表**直接推导**（它是规则表的投影，不是引擎输出回填）。
7. **`bench --only m2`**：在 `verify.py` 的 `implemented` 元组里加 `m2`，并写对应套件。
8. **同步改测试**：`test_bench_unimplemented_suite_is_usage_error` 用的是 `m3`，M2 完成后仍成立；
   但若先做 M3 需换一个未实现套件。`test_verify_data.py` 里 `bench --only m3` 的断言同理。
9. 跑 `licaudit bench --only m2`；回写 `plan/00`、`plan/05`、`plan/06`；写 `plan/HANDOFF-M3.md`。

### M2 开工前必须知道的既有约束

- **`ruleset.disabled` 不参与任何判定**；画像遇到 disabled 条目 → `tier: null` + 待确认。
- `tiers.json` 的 `verified` 是**生成器算出**的（锚点不可定位即 false），不是手填。
- 别在代码里复制五档/义务枚举：一律 `from licaudit import contract`。
- `profile.json` 里的 SPDX ID 必须原样保留 `-only` / `-or-later`。

## 三、既定口径清单（动了会打挂测试）

完整 K 清单见 `plan/05-里程碑.md` §三。M2 直接相关的既有口径：

| 编号 | 口径 | 影响面 |
| --- | --- | --- |
| K1 | 四级链顺序 `license_expression` > `trove_classifier` > `license_first_line` > `truncated_fallback` | 已实现；改顺序 → 6 条测试红（变异 5 实测） |
| K2 | 禁全文关键词匹配；首行 >200 字符不匹配 | 已实现；`test_anchor_length_gate_rejects_over_200` |
| K3 | `-only`/`-or-later` 原样保留；族名不明 → `<族>-unknown`；包版本不明 → `*` | 已实现 |
| K4 | `WITH` 未命中例外 → `unknown-exception` 但表达式不整体丢弃 | 已实现 |
| K5 | 产物顶层 `format` + `format_version` | `serialize.load_artifact` |
| K6 | 序列化冻结参数 | `serialize.py`，15 项测试锁死 |
| K7 | 五档枚举与顺序 | `contract.TIERS` / `TIER_RANK`；M2 只查表 |
| K8 | 义务项八项固定 | `contract.OBLIGATIONS`；`obligations.json` 由生成器产 |
| K9 | OSI/FSF 只从 SPDX 快照取；FSF 不参与判定 | M2 新测试 |
| K10 | `verified != true` 或锚点不可解析 → 拒绝加载进 `disabled` | `loader.py`，19 项测试 |
| K24 | 规则包定位顺序；**显式目录无效不回退** | `loader.locate_ruleset`（D21 收紧） |
| K26 | 真值只存输入与期望；`observed_*` 即红 | `verify.py` + 测试 |
| K27 | 生成物 `--check` 两层 | 三个生成器 |
| K28 | 合成包名白名单 `example-pkg-*`（坑位例外） | `test_synthetic_packages_are_whitelisted` |
| K29 | 中间产物全落 `--out-dir` | `pipeline.py` |
| K30 | 单件失败隔离，进 `parse_notes` | 已实现 |

### 本轮新增/收紧的口径（已登记 plan/06）

| 编号 | 内容 |
| --- | --- |
| D19 | 依赖级许可证只认清单显式写出的值，**绝不按包名/生态推断** |
| D20 | 规则包锚点必须带可在原文逐字定位的 `quote` |
| D21 | 显式 `--rules-dir` 无效时不回退 |
| D22 | 真值是「两个非互斥列表」：`dependencies` + `pending_confirmation` |

## 四、本机环境坑（M1 新增实测）

- **`py` 不是 `python`**（`python` 是商店占位符）。跑脚本一律 `py -3.12 -X utf8`。
- **多行 heredoc 写文件会被吞**：本机 Git Bash 对 `cat > file <<'PY'` 的收尾不稳，
  写脚本请用文件写入工具，或先写到临时文件再执行。
- **抓取 48 份全文约需 2–3 分钟**（串行 + 1s 退避）。别在前台用短超时跑。
- **`explicit --rules-dir` 指向空目录会 exit 3**（M1 之前的实现会静默回退到仓库规则，
  已修；写测试时别指望回退）。
- **`tools/` 下的生成器需要 `src` 在 `sys.path`**：三个脚本都在文件头自己注入，直接跑即可。
- **`references/spdx/` 是 2.8 MB 冻结数据**：`.gitattributes` 已标 `-text`，别让编辑器改行尾。
- **Windows 路径**：`os.path.relpath` 跨盘符会抛 `ValueError`；展示路径要兜底。
- **编码**：`encoding.ensure_utf8_stdio` 已按 `stream.encoding` 探针处理；CI 另设 `PYTHONUTF8=1`。

## 五、DoD 逐项 checklist（M1）

- [x] SPDX 快照入仓，manifest 记版本 + sha256 + `captured_on`，`--check` 通过
- [x] 规则包由 curated + 快照生成，48/48 过锚点门，`--check` 位级一致
- [x] 合成清单 11 用例 + 真值 44 条期望，`--check` 位级一致
- [x] 四条坑位全部有真值断言（含 `checked_on`）
- [x] pandas 阴性对照：改首行即不命中（证明禁全文匹配）
- [x] `verify-data` 由 CLI 真读冻结件（改真值 → 变红）
- [x] 解析 F1 = 1.0（DoD ≥ 0.95）
- [x] `scan` 全链可跑，字段序 == contract，双跑逐字节一致
- [x] 退出码 0/1/2/3 语义未被削弱（缺规则包仍 exit 3；未实现套件 exit 2）
- [x] 双解释器 247 passed
- [x] 7 组变异验证
- [ ] **CI 首推**：配置已就位但仍**未推送、未运行**；M6 首推时据实补记

## 六、关键命令速查

```bash
# 安装（干净环境）
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"

# 双解释器全量测试
PYTHONDONTWRITEBYTECODE=1 py -3.8  -X utf8 -m pytest -q
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest -q

# 生成器（数据刷新是人工步骤）
py -3.12 -X utf8 tools/fetch_spdx.py --out references/spdx
py -3.12 -X utf8 tools/gen_ruleset.py
py -3.12 -X utf8 tools/gen_synthetic.py

# 生成物自检
py -3.12 -X utf8 tools/fetch_spdx.py --check --out references/spdx
py -3.12 -X utf8 tools/gen_ruleset.py --check
py -3.12 -X utf8 tools/gen_synthetic.py --check

# 交付态入口
licaudit status
licaudit scan data/synthetic/npm-basic/package.json --out-dir out
licaudit verify-data
licaudit bench --only m1

# 未安装时（Skill 场景）
PYTHONPATH=src py -3.12 -X utf8 -m licaudit scan data/synthetic/npm-basic/package.json --out-dir out
```

## 七、启动提示词（新对话用）

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M2.md" 继续完成任务
```
