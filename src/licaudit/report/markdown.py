# -*- coding: utf-8 -*-
"""中文《第三方开源清单》Markdown 渲染（**零判定**：只排版 :mod:`licaudit.report.sections`）。

八章节顺序由章节结构函数给出，本模块按出现顺序输出，不重排、不筛选、不补结论。
行内一律用 ``str.join`` / ``str.format`` 组装（AST 守门禁止算术与拼接 ``BinOp``）。
"""

from .sections import build_report


def _render_pairs(data):
    lines = []
    for label, value in data:
        lines.append("- **{0}**：{1}".format(label, "" if value is None else value))
    return lines


def _render_lines(data):
    return ["- {0}".format(item) for item in data]


def _render_anchors(section):
    lines = []
    for item in section["data"]:
        lines.append("### {0} {1}".format(item["package"], item["version"]))
        lines.append("- SPDX 标识：{0}".format(item["spdx_id"]))
        lines.append("- 声明位置：{0}".format(item["declaration_location"]))
        lines.append("- 依据条款：{0}".format(item["basis_clause"]))
        lines.append("- 处置规则：{0}（核对日期 {1}）".format(
            item["rule_id"], item["checked_on"]
        ))
        anchor = item.get("anchor") or {}
        quote = anchor.get("quote")
        if quote:
            lines.append("  > {0}".format(quote))
        if item.get("missing_anchors"):
            lines.append("- 缺失锚点：{0}".format("、".join(item["missing_anchors"])))
        lines.append("")
    if not section["data"]:
        lines.append("（无：本次没有可给出处置建议的条目）")
    return lines


def _render_table(section):
    columns = section["columns"]
    lines = [
        "| {0} |".format(" | ".join(columns)),
        "| {0} |".format(" | ".join("---" for _column in columns)),
    ]
    for row in section["data"]:
        cells = []
        for column in columns:
            value = row.get(column, "")
            cells.append("" if value is None else str(value))
        lines.append("| {0} |".format(" | ".join(cells)))
    return lines


def _render_groups(data):
    lines = []
    for group in data:
        lines.append("### {0}".format(group["label"]))
        for item in group["items"]:
            lines.append("- {0}".format(item))
        lines.append("")
    return lines


def _render_advice(data):
    lines = []
    current = None
    for item in data:
        if item["level"] != current:
            current = item["level"]
            lines.append("### {0}".format(item["level_label"]))
        lines.append("#### {0} {1}（{2}）".format(
            item["package"], item["version"], item["spdx_id"]
        ))
        for reason in item["reasons"]:
            lines.append("- {0}".format(reason))
        lines.append("- 依据条款：{0}".format(item["basis_clause"]))
        lines.append("- 声明位置：{0}".format(item["declaration_location"]))
        lines.append("")
    if not data:
        lines.append("（无：本次没有给出处置建议的条目）")
    return lines


def _render_pending(data):
    lines = []
    for item in data:
        lines.append("- [{0}] {1}（SPDX 标识：{2}）— 原因码：{3}".format(
            item["source_label"],
            item["key"],
            item["spdx_id"] or "未识别",
            "、".join(item["reasons"]) or "未登记",
        ))
    if not data:
        lines.append("（无：本次没有待人工确认项）")
    return lines


def section_lines(section):
    """单个章节的正文行（不含标题）。"""
    kind = section["kind"]
    if kind == "pairs":
        return _render_pairs(section["data"])
    if kind == "lines":
        return _render_lines(section["data"])
    if kind == "anchors":
        lines = _render_anchors(section)
        lines.append("> {0}".format(section["note"]))
        return lines
    if kind == "table":
        return _render_table(section)
    if kind == "groups":
        return _render_groups(section["data"])
    if kind == "advice":
        return _render_advice(section["data"])
    if kind == "pending":
        return _render_pending(section["data"])
    if kind == "quote":
        return ["> {0}".format(section["data"])]
    return []


def render(report):
    """渲染完整 Markdown 文本（结尾 LF）。"""
    lines = ["# 第三方开源清单（licaudit）", ""]
    for section in report["sections"]:
        lines.append("## {0}".format(section["title"]))
        lines.append("")
        lines.extend(section_lines(section))
        lines.append("")
    return "{0}\n".format("\n".join(lines))


def render_artifacts(artifacts):
    return render(build_report(artifacts))


__all__ = ["render", "render_artifacts", "section_lines"]
