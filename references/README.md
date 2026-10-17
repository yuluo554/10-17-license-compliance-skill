# references/ — 规则包与 SPDX 快照

> 本目录是**数据**，不是代码。运行时由 `licaudit.ruleset.loader` 读取并校验。
> **M1 起已冻结就位**：SPDX 3.29.0 快照（740 许可 / 86 例外 / 48 份按需全文）、
> curated 人工表、规则包 r0.1.0（48 条已核验档位规则 + 6 条已核验场景触发条目 +
> 4 条已核验冲突对 + 8 条已核验处置决策规则）。
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
    conflict-pairs.json               # 冲突对（M4：4 条已核验）
    action-rules.json                 # 处置决策表（M5：8 条已核验 + 义务轴映射）
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
- 每条判定规则必须带 `anchor`（原文来源 + 定位 + **可在原文逐字定位的 `quote`**）与
  `checked_on`（人工核对日期）。冲突对另外要求 `left`/`right` 都在 SPDX 快照内、
  且同一无向组合不得重复登记（生成器直接拒绝）。
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

## M2 实测（2026-10-17）

规则包内容未变（48 条档位规则、`disabled=0`）；M2 只是把这份规则包**真正用起来**：

| 项 | 值 |
| --- | --- |
| 画像覆盖 | 52 个原子 ID：48 条有档位 / 4 条未覆盖（`BlueOak-1.0.0`、`CC-BY-4.0`、`GPL-unknown`、`LGPL-unknown`） |
| 有档位条目的锚点 | 48/48 与 `tiers.json` 的 `anchor` 逐字一致，带 `checked_on` |
| `disabled` | 0（`disabled_rules` 为空）；伪造未核验条目会被引擎拒绝并显式列出 |

## M3 实测（2026-10-17）

场景触发表从空表补齐为 **6 条已核验条目**，每条挂可在 SPDX 全文逐字定位的 quote：

| 规则 id | 档位 | 触发 | 依据锚点 |
| --- | --- | --- | --- |
| `T-DIST-STRONG-001` | strong-copyleft | distribution | GPL-2.0-only §3(b) |
| `T-DIST-NET-001` | network-copyleft | distribution | AGPL-3.0-only §6 |
| `T-NET-001` | network-copyleft | network-interaction（需网络交互为真） | AGPL-3.0-only §13 |
| `T-DIST-WEAK-001` | weak-copyleft | distribution | MPL-2.0 §3.2 |
| `T-STATIC-WEAK-001` | weak-copyleft | static-link | LGPL-2.1-only §6 |
| `T-SA-HOSTED-001` | source-available | hosted-service-restriction | Elastic-2.0 Limitations |

规则包哈希随内容变更（**预期变更**）；`tools/gen_ruleset.py --check` 与重生成逐字节一致，
`disabled=0`。

> `GPL-unknown` / `LGPL-unknown` 是解析器造的 ID，本来就不在 SPDX 清单里（K3），
> 因此画像对它们必然 `is_osi_approved = null`、`is_fsf_libre = null`——这是正确行为，不是缺数据。

## M4 实测（2026-10-17）

冲突对表从空表补齐为 **4 条已核验条目**，每条带 `basis` + 可在 SPDX 全文逐字定位的 quote：

| pair_id | left × right | resolution | 依据锚点 |
| --- | --- | --- | --- |
| `CP-GPL2-APACHE2` | GPL-2.0-only × Apache-2.0 | incompatible | Apache-2.0 §3（专利诉讼终止） |
| `CP-GPL2-AGPL3` | GPL-2.0-only × AGPL-3.0-only | incompatible | AGPL-3.0-only §13 |
| `CP-GPL2-GPL3` | GPL-2.0-only × GPL-3.0-only | incompatible | GPL-2.0-only §6（禁止进一步限制） |
| `CP-GPL3-APACHE2` | GPL-3.0-only × Apache-2.0 | compatible | GPL-3.0-only §7（允许的附加条款） |

`cross_check` 登记 `osadl-mirror / advisory`，**不参与判定**（决策 D3 / P4 关闭）。
规则包哈希随内容变更（**预期变更**）；`tools/gen_ruleset.py --check` 与重生成逐字节一致，`disabled=0`。

## M5 实测（2026-10-17）

处置决策表从空表补齐为 **8 条已核验条目**，条目顺序即优先级（从上到下、先命中者生效）；
义务项 → 义务轴的映射（`obligation_axes`）也在同一份表里，引擎不写任何义务项字面量。

| rule_id | level | when（义务轴 / 冲突结论 / 依赖间冲突 / 链接方式） | 依据锚点 |
| --- | --- | --- | --- |
| `A-REPL-001` | replace_or_license | 轴含 `same-license` + 与 outbound 不相容 | GPL-2.0-only §6（禁止进一步限制） |
| `A-REPL-002` | replace_or_license | 依赖间冲突为不兼容 + 链接方式 `none`/`static` | Apache-2.0 §3（专利诉讼终止） |
| `A-DECL-001` | declare | 轴恰为 `{notice}` + 相容 + 无依赖间冲突 | MIT（保留版权与许可声明） |
| `A-ISOL-001` | isolate | 轴含 `source` + 无依赖间冲突 | LGPL-2.1-only §6(b)（改用共享库机制） |
| `A-ISOL-002` | isolate | 轴含 `network-source` + 无依赖间冲突 | AGPL-3.0-only §13（网络交互提供源码） |
| `A-ISOL-003` | isolate | 与 outbound 不相容（档位级粗判）+ 无依赖间冲突 | MPL-2.0 §3.3（Larger Work 按你的条款发布） |
| `A-ISOL-004` | isolate | 依赖间冲突为不兼容 + 链接方式 `dynamic`/`separate-process` | GPL-2.0-only §2（mere aggregation） |
| `A-OK-001` | ok | 轴为空 + 相容 + 无依赖间冲突 | 0BSD（无附加义务） |

生成器另加两道结构门（`tools/gen_ruleset.py`）：**覆盖完备**（由 curated 场景触发表推出的
6 组可达义务轴 × 确定冲突结论 × 链接方式 × 场景结论，共 192 组输入都必须有结论）与
**无死规则**。规则包哈希随内容变更（**预期变更**）；`--check` 与重生成逐字节一致，`disabled=0`。

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
