# tools/ — 生成器与维护脚本（不是用户 CLI）

本目录在 **M1** 起存放数据生成与校验脚本。它们是**发布/维护期工具**，不挂到用户 CLI 上，
也不进运行时安装面。

## 计划中的脚本

| 脚本 | 作用 | 里程碑 |
| --- | --- | --- |
| `fetch_spdx.py` | ✅ 抓取 SPDX 清单与按需全文快照，登记 sha256 与版本（含离线 `--check`） | M1 |
| `gen_ruleset.py` | ✅ 由 SPDX 快照 + `references/curated/` 生成规则包；锚点 quote 必须可在原文定位 | M1 |
| `gen_synthetic.py` | ✅ 产合成依赖清单与真值库（splitmix64、独立朴素 oracle） | M1 |
| `gen_profile_truth.py` | ✅ 由 curated 规则表推导画像真值（规则表是唯一真相，真值是它的投影） | M2 |
| `gen_scenario_truth.py` | ✅ 由 curated 场景触发表推导八场景判定表真值（不 import 生产引擎） | M3 |
| `gen_conflict_truth.py` | ✅ 由 curated 冲突对表推导冲突真值：已知对全命中 / `OR`·`AND` 求值 / `outbound = pending`（不 import 生产引擎，自带迷你文法） | M4 |
| `gen_action_truth.py` | ✅ 由 curated 处置决策表推导处置真值：192 组确定输入 + 四级样本（不 import 生产引擎，独立谓词匹配） | M5 |
| `check_release.py` | ✅ 发布终态自检（tag / Release 附件 / 留档三件套；离线 + `--online`） | M6 |

## 纪律

- 每个生成器必须提供 `--check`：重生成到临时目录并逐字节比对冻结产物。
- `--check` 两层：冻结产物形态正确 + 重生成结果一致（只断言前者是假门）。
- 生成器不读时钟、不用 `set` 迭代序、不使用 stdlib `random`（用自研 splitmix64）。
- 落盘一律经 `licaudit.serialize` 的原子写与冻结序列化参数。
- 这些脚本**不是**用户命令：用户面向的命令只有 `licaudit <subcommand>`。

## M1 实测（2026-10-17）

```bash
py -3.12 -X utf8 tools/fetch_spdx.py --check --out references/spdx   # rc=0
py -3.12 -X utf8 tools/gen_ruleset.py --check                        # rc=0
py -3.12 -X utf8 tools/gen_synthetic.py --check                      # rc=0
```

三个 `--check` 都是两层：形态校验 + 重生成到临时目录逐字节比对。
手改冻结产物会让 `--check` 变红（`test_gen_ruleset_check_detects_handedit` 是阳性对照）。

## M2 实测（2026-10-17）

```bash
py -3.12 -X utf8 tools/gen_profile_truth.py --check                  # rc=0
```

## M3 实测（2026-10-17）

```bash
py -3.12 -X utf8 tools/gen_scenario_truth.py --check                 # rc=0
```

`data/truth/scenario.json` 由 curated 场景触发表直接推导（230 行判定表 + 1 条 `tier: null` 待确认）。
生成器不 import 生产场景引擎，锚点可定位性用本文件内的朴素实现独立校验。
`_mutate_m3.py` 是 M3 的一次性变异验证脚本（9 组「弄坏 → 变红 → 恢复 → 变绿」），不参与发布。

`data/truth/profile.json` 由 curated 规则表直接推导（52 个 ID：48 覆盖 + 4 未覆盖）。
生成器**不 import** 生产画像引擎；锚点可定位性用本文件内的朴素实现独立校验。
`test_gen_profile_truth_check_detects_handedit` 是阳性对照（手改 → 变红）。

`_mutate_m2.py` 是一次性变异验证脚本（弄坏 → 变红 → 恢复 → 变绿，9 组），
不参与发布，也不被 pytest 收集。

## M4 实测（2026-10-17）

```bash
py -3.12 -X utf8 tools/gen_conflict_truth.py --check                 # rc=0
```

`data/truth/conflicts.json` 由 curated 冲突对表 + curated 档位表直接推导（4 条冲突对 / 2 对未登记组合 /
6 条求值样例 / 1 条 `outbound = pending`）。生成器不 import 生产冲突引擎，表达式求值用本文件内
自带的迷你文法独立实现；真值只存可机检字段（不含引擎生成的中文 `reason` 文案）。
`_mutate_m4.py` 是一次性变异验证脚本（12 组），不参与发布。

> 注意：`_mutate_m2.py` / `_mutate_m3.py` / `_mutate_m4.py` / `_mutate_m5.py` 里针对 `verify.py`
> 的变异点按 **suite 名**定位；新增/移动套件分支后要复跑这几个脚本，否则变异可能打到别的分支上
> （M4 就修过一次 M3 的 M9 锚点）。M5 收尾时四份脚本都已复跑（见 `plan/HANDOFF-M6.md`）。

## M5 实测（2026-10-17）

```bash
py -3.12 -X utf8 tools/gen_action_truth.py --check                   # rc=0
```

`data/truth/actions.json` 由 curated 处置决策表 + curated 场景触发表直接推导
（8 条决策规则 / 6 组可达义务轴 / 192 组确定输入 + 四级样本 = 196 条）。生成器不 import
生产处置引擎，谓词匹配用本文件内的独立朴素实现；`expect.levels` 保证四级处置各至少一个植入口。
`_mutate_m5.py` 是一次性变异验证脚本（13 组：决策表语义、五锚点门、退出码聚合、
`bench m5` 恒真、报告层 AST 三条守门），不参与发布。

## M6 实测（2026-10-17）

```bash
py -3.12 -X utf8 tools/check_release.py            # 离线：留档两栏 / 版本三方一致 / sdist 自足 / 口径已翻转
py -3.12 -X utf8 tools/check_release.py --online   # 追加：仓库公开 / tag 指向 / CI 全绿 / Release 附件原名下载回验
```

`check_release.py` 是**发布门**：不改文件、不产生新事实，只判断当前仓库状态够不够格叫一次发布。
它读 `plan/RELEASE-M6.md` 的两块 ```release 键值块（§一 写 tag 时点字段、§二 追加 tag 后字段）
与 `sums` 围栏块（附件 sha256），因此**发布终态必须没有占位标记**
（`TODO` / `待追加` / 待首推 …）——这一条在发布前故意是红的。

**附件契约**：`sums` 块登记的是**被哈希的载荷文件**；`SHA256SUMS` 是它们的伴随清单，
自身不进 `sums` 块。因此 `--online` 的判定是
「远端附件集合 == 登记的载荷 + `SHA256SUMS`」，并且**下载回来的 `SHA256SUMS` 必须恰好登记同一批载荷**
（否则一个会撒谎的校验和文件就能蒙混过关）。

**两处刻意的严格**（都是被变异验证逼出来的，见下表 M1/M6）：
栏目标题必须是**标题行**（正文里提到过这两个词不算）；`MANIFEST.in` 的
`recursive-include references` 必须真的覆盖 `*.json`（只要求「有这一行」太松）。

`sdist` 的完整性由 `MANIFEST.in` 负责：它把 `references/` 规则包与 SPDX 快照、`data/` 真值、
`examples/`、`plan/`、`tools/`、`tests/` 一起打进源码包，使「源码包」这一发布形态自足
（解包 → `pip install -e .` → `licaudit status` 不再 exit 3）；一次性变异脚本与 `out/`、`dist/`、
`*.egg-info` 不入包。这里守的是**清单别退化**；权威证明是真去解包构建出来的 sdist 跑一遍
`licaudit status`（记录在 `plan/RELEASE-M6.md` §2.5）。

`_mutate_m6.py` 是一次性变异验证脚本（11 组：「弄坏 → 变红 → 恢复 → 变绿」，
含 3 组要联网真下载附件），不参与发布：

```bash
py -3.12 -X utf8 tools/_mutate_m6.py                 # 11 组（含联网组）
py -3.12 -X utf8 tools/_mutate_m6.py --offline-only  # 8 组（快）
```

| # | 弄坏什么 | 变红的检查 |
| --- | --- | --- |
| M1 | 留档少了「tag 后追加事实」标题行 | 栏目标题（只有正文提到不算） |
| M2 | 留档里插入一个占位标记 | 无占位标记 |
| M3 | 校验和行截断成 40 位 | `sums` 行文法是 sha256 |
| M4 | 留档登记的规则包版本与 manifest 不符 | 规则包版本一致 |
| M5 | `plan/00` 的 M6 行回退成 ⬜ | 状态已翻转 |
| M6 | `MANIFEST.in` 的 `references` 不再覆盖 `*.json` | sdist 自足 |
| M7 | 包版本与 `SKILL.md` 版本不一致 | 版本三方一致 |
| M8 | 留档 tag 与包版本不匹配 | tag ↔ 版本 |
| M9 | `tag_commit` 与远端 tag 指向不符 | 远端 tag 指向 |
| M10 | 登记的附件名远端不存在 | 远端附件集合 |
| M11 | 校验和是合法 sha256 但值不对 | 附件下载回验 |

`_scan_desensitize.py` 是一次性的**脱敏自查**脚本（绝对路径 / 凭证 / 跨项目引用 / 模板占位），
不参与发布，也不被 pytest 收集。
