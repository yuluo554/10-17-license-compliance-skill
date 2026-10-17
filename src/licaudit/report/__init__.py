# -*- coding: utf-8 -*-
"""M5：报告渲染（零判定）。

三层：

- :mod:`licaudit.report.sections` —— 八章节结构（MD 与 CSV 的唯一来源）；
- :mod:`licaudit.report.markdown` —— 中文 Markdown 渲染；
- :mod:`licaudit.report.csv_render` —— CSV 渲染（列序 == ``contract.REPORT_CSV_COLUMNS``）。

三条 AST 守门（plan/06 D13，见 ``tests/test_report.py``）：

1. 不 import ``licaudit.inventory`` / ``licaudit.assess``；
2. 不出现算术 / 拼接 ``BinOp``；
3. 不内联「许可证 ID → 档位/处置」判定表，也不写档位名 / 处置级别名字面量。

渲染层只消费 ``actions.json`` / ``conflicts.json`` / ``scenario.json`` / ``profile.json``
的既有字段；遇到未知字段忽略，不重算任何判定。
"""

MILESTONE = "M5"

REPORT_FILES = {
    "md": "license-report.md",
    "csv": "license-report.csv",
}

__all__ = ["MILESTONE", "REPORT_FILES"]
