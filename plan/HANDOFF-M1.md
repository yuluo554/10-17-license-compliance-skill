# HANDOFF-M1：进入「数据先行 + M1 解析」

> 上一棒：M0 计划与骨架（2026-10-17 完成）。本文件是下一棒的**唯一入口**。
> 库内一律相对路径；用户侧启动命令用绝对路径指向本文件。

## 一、当前进度与证据

### 已交付

| 交付物 | 位置 | 证据 |
| --- | --- | --- |
| 计划文档 00–06 | `plan/` | 00 索引已回写，02–06 新建 |
| Skill 主入口 + 契约块 | `SKILL.md` | 7 个机器可解析块，`tests/test_skill_contract.py` 双向断言 |
| 确定性引擎骨架 | `src/licaudit/` | 13 个模块，`tests/` 137 项全绿 |
| 规则包加载硬门 | `src/licaudit/ruleset/loader.py` | 19 项测试覆盖未核验/缺锚点/缺日期/哈希不符/缺文件/白名单外文件 |
| 可证伪自检 | `src/licaudit/selftest.py` | 6 项核心 check + 规则包 check；9 项变异用例 |
| 三条调用通路 | `cli.py` / `__main__.py` / `scripts/launcher_licaudit.py` | `tests/test_entrypoints.py` 子进程实跑 |
| 序列化确定性 | `src/licaudit/serialize.py` | 15 项测试（中文不转义、LF、无 BOM、字段序、CSV 列序、未知格式拒绝） |
| 零网络守门 | `tests/test_no_network.py` | AST 扫描 + 阳性/阴性对照 |
| README 指令面 | `tests/test_readme_surface.py` | 子命令/旗标/路径/extras 四类断言 |
| CI 配置 | `.github/workflows/ci.yml` | **未推送、未跑过** |
| LICENSE / .gitattributes | 仓库根 | MIT；快照 `-text` 冻结 |

### 实测记录（当轮真跑）

```
py -3.8  -X utf8 -m pytest -q   → 137 passed
py -3.12 -X utf8 -m pytest -q   → 137 passed
干净 venv + pip install -e ".[dev]" → pytest 137 passed
./.tmp-venv/Scripts/licaudit.exe selftest --core        → rc=0
./.tmp-venv/Scripts/licaudit.exe selftest               → rc=1（缺规则包，可证伪）
./.tmp-venv/Scripts/licaudit.exe status                 → rc=3
./.tmp-venv/Scripts/licaudit.exe scan README.md         → rc=3
./.tmp-venv/Scripts/licaudit.exe verify-data            → rc=3
./.tmp-venv/Scripts/licaudit.exe bench                  → rc=3
./.tmp-venv/Scripts/licaudit.exe nope                   → rc=2
py -3.8 scripts/launcher_licaudit.py selftest --core    → rc=0
```

### 变异验证（全部「弄坏 → 变红 → 恢复 → 变绿」）

1. 关掉 loader 的 `if policy == "anchor"` 分支 → 3 项锚点测试红。
2. `RulesetError` 分支返回 `EXIT_OK` → 8 项退出码测试红。
3. 序列化改 `ensure_ascii=True, indent=4, sort_keys=True` → 3 项红。
4. 契约字段加 `evidence_extra` → 契约双向断言红。

## 二、下一棒待办（M1）

按 `plan/04-数据计划.md` §八启动清单顺序执行：

1. **`tools/fetch_spdx.py`**：抓 `licenses.json` / `exceptions.json` → `references/spdx/`；
   登记 `license_list_version`、`captured_on`、sha256 到 `references/spdx/manifest.json`。
   - 先跑一次真实请求，**回读版本字段**再落库（不照抄 3.29.0，以响应为准）。
   - 失败重试 ≤3 次；不写半份文件。
2. **`references/curated/tiers.json`**：先覆盖合成清单出现的 ID；每条带 `anchor` + `checked_on` + `verified`。
   宁缺勿造：没核对过的 ID 不写。
3. **`tools/gen_ruleset.py`**：curated + SPDX 快照 → `references/ruleset/*.json` + `manifest.json`；
   实现 `--check`（重生成到临时目录逐字节比对）。
   - 注意：`tests/test_ruleset_loader.py::test_repo_has_no_ruleset_yet` 当前断言「仓库无 manifest」，
     **M1 生成后必须同步改为「manifest 存在且可加载」**，否则测试会红。
4. **`tools/gen_synthetic.py`**：产 `data/synthetic/*` + `data/truth/truth.json`；
   自研 splitmix64；期望值用独立朴素 oracle；`--check` 两层。
5. **M1 解析器**（`src/licaudit/inventory/`）：六个文件名分派 + 四级可信度链 + SPDX 表达式解析。
6. **`scan` 命令**：打通 `inventory.json`；`pipeline.run_scan` 从 `_not_yet` 换为真实实现。
7. **`verify-data`**：读冻结真值 + 参照实现复算；必须由 CLI 真读（不是测试里读）。
8. **坑位回归**：pandas / psycopg2 / PyMySQL / PyQt5 四条，期望值人工核对后写入并标日期。
9. 跑 `licaudit bench --only m1`；回写 `plan/00`、`plan/05`、`plan/06`；写 `plan/HANDOFF-M2.md`。

## 三、既定口径清单（动了会打挂测试）

完整 K 清单见 `plan/05-里程碑.md` §二。M1 直接相关：

| 编号 | 口径 | 影响面 |
| --- | --- | --- |
| K1 | 四级链 `license_expression` > `trove_classifier` > `license_first_line` > `truncated_fallback`，命中即停 | 常量 `CONFIDENCE_LEVELS`、真值、`selftest` |
| K2 | 禁全文关键词匹配；第 3 级只取首行，首行 >200 字符不匹配 | 解析器 + pandas 阴性对照 |
| K3 | `-only`/`-or-later` 原样保留；族名不明 → `<族>-unknown`；包版本不明 → `*` | 归一化函数 + 真值 |
| K4 | `WITH` 例外必须命中 `exceptions.json`，未命中 → `unknown-exception` 但表达式不整体丢弃 | 表达式解析器 |
| K5 | 产物顶层带 `format` + `format_version`，装载器白名单分派 | `serialize.load_artifact` |
| K6 | 序列化冻结参数（`ensure_ascii=False`、`indent=2`、插入序、LF、尾换行、原子写） | `serialize.py`，已被 15 项测试锁死 |
| K24 | 规则包定位顺序：`--rules-dir` > `LICAUDIT_RULES_DIR` > 仓库推导 > CWD | `loader.candidate_dirs` |
| K26 | 真值只存输入与期望，出现 `observed_*` 即红 | 真值结构 |
| K27 | `--check` 两层：冻结产物形态 + 重生成逐字节一致 | 每个生成器 |
| K28 | 合成包名白名单 `example-pkg-*`（坑位用例例外） | 数据 |
| K29 | 中间产物全落 `--out-dir` | `pipeline` |
| K30 | 单件失败隔离，进 `parse_notes`，不中断整批 | 解析器 |

## 四、本机环境坑（实测）

- **用 `py` 不是 `python`**（`python` 是商店占位符，直接报 exit 49）。跑脚本一律 `py -X utf8`。
- **`py -0p` 有 3.8.8 与 3.12 两条通道**，都装了 pytest（7.4.4 / 8.4.2）。跨版本差异仍以 CI 为准。
- **`python -m licaudit` 未安装时会报 `No module named licaudit`**——README 已写明；Skill 场景用
  `scripts/launcher_licaudit.py`（自带 `sys.path` 注入）或 `PYTHONPATH=src`。
- **pip 可能被系统代理污染**；本机实测 `NO_PROXY="*" no_proxy="*" py -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple` 可用。
- **`.tmp-venv` 与 `out/`、`*.egg-info`、`__pycache__` 都是运行产物**，提交前清理；`.gitignore` 已覆盖。
- **Git Bash 下 `cd /d/...` 用 `/d/` 形式**；`os.path.relpath` 跨盘符会抛 `ValueError`，展示路径要兜底。
- **Windows 控制台可能 cp936/cp1252**；`encoding.ensure_utf8_stdio` 已按 `stream.encoding` 探针处理，
  CI 另设 `PYTHONUTF8=1`。写测试时用 `TextIOWrapper(BytesIO(), encoding="cp1252", errors="strict")` 复现。

## 五、DoD 逐项 checklist（M0）

- [x] `plan/02`–`plan/06` 五份文档齐备并被 `plan/00` 索引
- [x] `pyproject.toml` 可 `pip install -e ".[dev]"`（干净 venv 实测）
- [x] 三条调用通路：控制台脚本 / `python -m` / launcher，子进程实跑
- [x] 退出码 0/1/2/3 锁进测试（`tests/test_cli_contract.py`）
- [x] `scan`/`assess`/`report` 缺规则包时真实 `exit 3`，规则包就绪后 `exit 2` 且不写占位产物
- [x] 规则包加载硬门 19 项测试
- [x] selftest 可证伪（空规则包 → exit 1；9 项变异用例）
- [x] 契约块三方断言（集合 / 顺序 / 章节 / 退出码）
- [x] 编码守卫（cp1252 流复现）
- [x] 零网络 AST 守门 + 阳性/阴性对照
- [x] README 指令面四类断言（子命令 / 旗标 / 路径 / extras）
- [x] LICENSE 存在且为 MIT
- [x] 双解释器 137 项全绿
- [x] 4 组变异验证（弄坏 → 红 → 恢复 → 绿）
- [ ] **CI 首推**：配置已就位但**未推送、未运行**；M6 首推时据实补记

## 六、关键命令速查（本轮全部实跑过）

```bash
# 安装（干净环境）
py -3.12 -m venv .venv
./.venv/Scripts/python.exe -m pip install -e ".[dev]"

# 双解释器全量测试
PYTHONDONTWRITEBYTECODE=1 py -3.8  -X utf8 -m pytest -q
PYTHONDONTWRITEBYTECODE=1 py -3.12 -X utf8 -m pytest -q

# 未安装时（Skill 场景）
py -3.12 scripts/launcher_licaudit.py selftest --core
py -3.12 scripts/launcher_licaudit.py status          # 预期 rc=3（M0）

# 已安装
licaudit selftest --core
licaudit selftest                                     # 预期 rc=1（缺规则包）
licaudit status                                       # 预期 rc=3

# M1 落地后
py -3.12 tools/fetch_spdx.py --out references/spdx
py -3.12 tools/gen_ruleset.py --check
py -3.12 tools/gen_synthetic.py --check
licaudit verify-data
licaudit bench --only m1
```

> 表内命令本轮均实跑或断言过（`--check`、`verify-data`、`bench` 为 M1 新增，届时当轮实跑后再进 HANDOFF）。

## 七、启动提示词（新对话用）

```
/goal 读取 "<项目绝对路径>\plan\HANDOFF-M1.md" 继续完成任务
```
