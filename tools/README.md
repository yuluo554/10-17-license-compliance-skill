# tools/ — 生成器与维护脚本（不是用户 CLI）

本目录在 **M1** 起存放数据生成与校验脚本。它们是**发布/维护期工具**，不挂到用户 CLI 上，
也不进运行时安装面。

## 计划中的脚本

| 脚本 | 作用 | 里程碑 |
| --- | --- | --- |
| `fetch_spdx.py` | ✅ 抓取 SPDX 清单与按需全文快照，登记 sha256 与版本（含离线 `--check`） | M1 |
| `gen_ruleset.py` | ✅ 由 SPDX 快照 + `references/curated/` 生成规则包；锚点 quote 必须可在原文定位 | M1 |
| `gen_synthetic.py` | ✅ 产合成依赖清单与真值库（splitmix64、独立朴素 oracle） | M1 |
| `check_release.py` | M6 发布终态自检（tag / Release 附件 / 留档） | M6 |

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
