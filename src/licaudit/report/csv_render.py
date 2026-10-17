# -*- coding: utf-8 -*-
"""《第三方开源清单》CSV 渲染（**零判定**：只投影 :mod:`licaudit.report.sections` 的行）。

契约（plan/03 §5.3，P2 关闭）：列序 == :data:`licaudit.contract.REPORT_CSV_COLUMNS`，
``lineterminator="\\n"``，UTF-8 **无 BOM**。行内容与 Markdown 的「逐包明细」章节同源。
"""

from .. import contract
from ..serialize import dumps_csv
from .sections import build_report


def rows_of(artifacts):
    """逐包明细行（列序即 CSV 列序）。"""
    report = build_report(artifacts)
    rows = []
    for row in report["rows"]:
        rows.append({column: row.get(column) for column in contract.REPORT_CSV_COLUMNS})
    return rows


def render(rows):
    """渲染 CSV 文本（无 BOM、LF 行尾、固定列序）。"""
    return dumps_csv(rows, contract.REPORT_CSV_COLUMNS)


def render_artifacts(artifacts):
    return render(rows_of(artifacts))


__all__ = ["render", "render_artifacts", "rows_of"]
