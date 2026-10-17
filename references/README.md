# references/ — 规则包与 SPDX 快照

> 本目录是**数据**，不是代码。运行时由 `licaudit.ruleset.loader` 读取并校验。
> **M1 起已冻结就位**：SPDX 3.29.0 快照（740 许可 / 86 例外 / 48 份按需全文）、
> curated 人工表、规则包 r0.1.0（48 条已核验档位规则）。
>
> 若规则包缺失或被手改，`loader` 仍会真实返回 exit 3——「规则包缺失」不得退化成
> 「零依赖、无风险」的 exit 0。

## 目录结构（M1 已就位）

```
references/
  spdx/
    licenses.json                     # SPDX 许可证清单快照（3.29.0）
    exceptions.json                   # SPDX 例外清单快照
    texts/<licenseId>.json            # 按需取的许可证全文（条款锚点来源）
  curated/                            # 人工核对表（唯一手写数据）
    tiers.json
    trove-map.json
    scenario-triggers.json
    conflict-pairs.json
    action-rules.json
  ruleset/                            # 生成物（禁手改）
    manifest.json                     # license_list_version + ruleset_version + 各文件 sha256
    tiers.json
    obligations.json
    scenario-triggers.json
    conflict-pairs.json
    action-rules.json
    trove-map.json
```

## 生成与校验

```bash
py -3.12 -X utf8 tools/fetch_spdx.py --out references/spdx
py -3.12 -X utf8 tools/gen_ruleset.py --out references/ruleset
py -3.12 -X utf8 tools/gen_ruleset.py --check
```

- `curated/` 是人工核对的输入；`ruleset/` 是生成物，**禁止手改**。
- 每条判定规则必须带 `anchor`（原文来源 + 定位）与 `checked_on`（人工核对日期）。
- `verified != true` 或锚点缺失的条目在加载时被拒绝，并出现在 `disabled` 清单里。
- `manifest.json` 登记每个文件的 sha256；手工改动会让加载直接 exit 3。
- 显式 `--rules-dir` 指向无效目录时**不回退**（决策 D21），直接 exit 3。

## M1 实测数字（2026-10-17）

| 项 | 值 |
| --- | --- |
| `licenseListVersion` | 3.29.0（`captured_on` = 2026-10-17） |
| SPDX 许可总数 / 例外总数 | 740 / 86 |
| 快照文件数（含 manifest） | 50（2 份清单 + 48 份全文） |
| 规则包档位规则 | 48 条，全部 `verified=true`、`disabled=0` |
| 覆盖口径 | `tiers_sampled_ids` 48 / `tiers_total_ids` 740（抽样，非全量） |
| trove 映射 | 7 条（只收无歧义分类器） |

## 定位顺序（K24）

1. `--rules-dir <path>`
2. 环境变量 `LICAUDIT_RULES_DIR`
3. 仓库推导（`src/licaudit/ruleset/loader.py` 向上三级 + `references/ruleset`）
4. 当前工作目录下的 `references/ruleset`

四条都取不到 → exit 3。**不提供内置默认规则**。

## 许可与来源

- SPDX 快照来自 <https://spdx.org/licenses/>，遵循 CC0-1.0（SPDX 许可证清单数据）。
- 单许可证全文按需取用，不整包入仓；引用时保留 `detailsUrl` 与许可证原文归属。
- curated 判定数据为本项目人工核对结果，每条挂核对日期，不转载全文。
