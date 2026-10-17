# examples/ — 示例报告（M5 产出）

本目录在 **M5** 起存放由冻结数据跑出的示例中文《第三方开源清单》：

```
examples/report/
  license-report.md      # 人读版
  license-report.csv     # 机读版（列序固定，UTF-8 无 BOM，LF 行尾）
```

## 生成

```bash
licaudit scan data/synthetic/example-project/package.json --out-dir out
licaudit assess --inventory out/inventory.json --scenario distribute-binary \
  --outbound-license MIT --out-dir out
licaudit report --out-dir out --format md
licaudit report --out-dir out --format csv
```

## 入仓前断言（M5 DoD）

- 八个章节俱全且顺序固定（`contract.REPORT_SECTIONS`）；
- 免责声明逐字出现；
- 每条处置五个锚点非空（包名 / 版本 / 声明位置 / SPDX ID / 依据条款）；
- 同输入双跑逐字节一致；
- CSV 无 BOM、LF 行尾、列序 == `contract.REPORT_CSV_COLUMNS`；
- 全部输入为合成清单，不含真实包名。

M0 骨架阶段本目录为空占位；不要手写示例报告。
