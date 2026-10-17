# examples/ — 示例报告（M5 产出）

本目录在 **M5** 起存放由冻结数据跑出的示例中文《第三方开源清单》：

```
examples/report/
  license-report.md              # SaaS 场景（outbound = Elastic-2.0）：ok / declare / replace_or_license
  license-report.csv             # 同一次运行的机读版（列序固定，UTF-8 无 BOM，LF 行尾）
  license-report-distribute.md   # 分发二进制场景（outbound = MIT）：ok / isolate / replace_or_license
  license-report-distribute.csv
```

输入全部来自 `data/synthetic/example-project/`（15 个依赖、六种清单形态、包名全合成）。

## 生成

```bash
EX=data/synthetic/example-project

# 一次 scan 产出 inventory.json，两种场景共用同一份清单
licaudit scan $EX/package.json $EX/package-lock.json $EX/requirements.txt \
  $EX/pyproject.toml $EX/go.mod $EX/pom.xml --out-dir out

# 主示例：SaaS 场景
licaudit assess --inventory out/inventory.json --scenario saas \
  --network-interaction yes --outbound-license Elastic-2.0 \
  --scenario-note "示例项目以 SaaS 形式对外提供服务" --out-dir out
licaudit report --out-dir out --format md
licaudit report --out-dir out --format csv

# 分发示例（换 out-dir）
licaudit assess --inventory out/inventory.json --scenario distribute-binary \
  --outbound-license MIT --scenario-note "示例项目分发二进制产物" --out-dir out/dist
licaudit report --out-dir out/dist --format md
licaudit report --out-dir out/dist --format csv
```

> 两次运行的分级不同是**口径使然**，不是数据不一致：`declare` 需要「SaaS 场景 + 源可用档位 outbound」，
> `replace_or_license` 需要「依赖间不兼容对」或「同许可义务 + 不相容 outbound」——
> 单一场景下四级处置无法同时出现，因此给两份运行，合起来覆盖
> `ok` / `declare` / `isolate` / `replace_or_license`（见 `plan/06` §五 诚实口径）。

## 入仓前断言（M5 DoD，已锁进 `tests/test_report.py`）

- 八个章节俱全且顺序固定（`contract.REPORT_SECTIONS`）；
- 免责声明逐字出现，并引用中国司法参照（罗盒案）；
- 每条处置五个锚点非空（包名 / 版本 / 声明位置 / SPDX ID / 依据条款）；
- 同输入双跑逐字节一致，且与入仓文件**逐字节相同**（重跑即校验）；
- CSV 无 BOM、LF 行尾、列序 == `contract.REPORT_CSV_COLUMNS`；
- 全部输入为合成清单，不含真实包名。

具体命令与退出码记录见 `plan/HANDOFF-M6.md`。不要手写示例报告。
