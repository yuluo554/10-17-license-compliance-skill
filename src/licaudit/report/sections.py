# -*- coding: utf-8 -*-
"""M5 报告章节结构（**零判定**：只消费既有产物字段，不重算任何结论）。

八个章节顺序固定（:data:`licaudit.contract.REPORT_SECTIONS`）：
概述 / 口径声明 / 证据锚点 / 逐包明细 / 风险分级 / 处置建议 / 待人工确认项 / 免责声明。

Markdown 渲染器与 CSV 渲染器**共用本模块**：CSV 是「逐包明细」章节的行投影，
列序 == :data:`licaudit.contract.REPORT_CSV_COLUMNS`；两格式内容一致因此是结构性质。

硬边界（plan/03 §5.4 / K23，AST 守门）：

- 不 import ``licaudit.inventory`` / ``licaudit.assess``；
- 不出现算术 / 拼接 ``BinOp``（一律用 ``str.join`` / ``str.format``）；
- 不内联「许可证 ID → 档位/处置」判定表，也不写档位名 / 处置级别名的字面量
  （展示标签从 :mod:`licaudit.contract` 取）。

遇到未知字段一律忽略，不推导。
"""

from .. import contract

# ---------------------------------------------------------------------------
# 固定文案（口径声明 / 司法参照）
# ---------------------------------------------------------------------------

SCOPE_STATEMENTS = (
    "判定链：依赖清单 → SPDX 归一化（四级可信度链）→ 许可证画像（五档 + 义务项）→ "
    "使用场景（八场景 × 链接方式）→ 冲突与兼容性 → 四级处置建议。",
    "档位、义务项、场景触发、冲突对、处置级别全部来自仓库内可审阅的规则包，"
    "并由生成器校验锚点可定位；引擎不新增义务项、不改档位。",
    "未知即待确认：未覆盖档位、未回答的场景问题、未决定的 outbound 许可证一律输出"
    "「待人工确认」，不按最宽松默认放过。",
    "档位级粗判：依赖 × 项目 outbound 的比较只到档位与义务层级，**未**按链接/分发边界聚合"
    "传染范围；已知偏差（例如弱传染档位高于宽松档位的依赖会被判不相容）在产物 notes 中登记。",
    "许可证识别只认清单里显式写出的值，不按包名或生态惯例推断；缺失即降级并标待确认。",
)

JUDICIAL_ANCHOR = (
    "依据条款的司法参照（不构成法律意见）：中国法院已有承认 GPL 类协议对衍生作品约束力的"
    "公开裁判（（2021）最高法知民终2063号，2023-05-05 终审）。本清单引用其方向性结论，"
    "不据此对具体项目下法律结论。"
)

PENDING_SOURCES = {
    "profile": "画像",
    "scenario": "场景",
    "conflicts": "冲突",
    "actions": "处置",
}


# ---------------------------------------------------------------------------
# 行（CSV 的唯一来源）
# ---------------------------------------------------------------------------


def _join(values, separator):
    return separator.join(item for item in values if item)


def _notes_cell(record, evidence):
    parts = list(record.get("reasons") or [])
    codes = evidence.get("reason_codes") or []
    if record.get("level") is None and codes:
        parts.append("原因码：{0}".format("、".join(codes)))
    return _join(parts, "；")


def package_rows(artifacts):
    """逐包明细行：每个依赖一条，列序 == ``contract.REPORT_CSV_COLUMNS``。"""
    rows = []
    for record in artifacts["actions"].get("actions") or []:
        evidence = record.get("evidence") or {}
        rows.append({
            "package": record.get("package"),
            "version": record.get("version"),
            "spdx_id": record.get("spdx_id"),
            "tier": evidence.get("tier"),
            "scenario": evidence.get("scenario"),
            "verdict": evidence.get("verdict"),
            "action_level": record.get("level"),
            "basis_clause": evidence.get("basis_clause"),
            "declaration_location": evidence.get("declaration_location"),
            "notes": _notes_cell(record, evidence),
        })
    rows.sort(key=lambda item: (item.get("package") or "", item.get("spdx_id") or ""))
    return rows


def pending_items(artifacts):
    """待人工确认项：四个产物的待确认投影取并集（同一来源同一键只出现一次）。"""
    items = []
    seen = set()
    for source, key, entries in (
        ("profile", "spdx_id", artifacts["profile"].get("pending_confirmation") or []),
        ("scenario", "package", artifacts["scenario"].get("pending_confirmation") or []),
        ("conflicts", "pair_id", artifacts["conflicts"].get("pending_confirmation") or []),
        ("actions", "package", artifacts["actions"].get("pending_confirmation") or []),
    ):
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            identifier = entry.get(key)
            if identifier is None:
                identifier = entry.get("spdx_id")
            mark = (source, identifier)
            if mark in seen:
                continue
            seen.add(mark)
            items.append({
                "source": source,
                "source_label": PENDING_SOURCES.get(source, source),
                "key": identifier,
                "spdx_id": entry.get("spdx_id"),
                "missing": list(entry.get("missing") or []),
                "reasons": sorted(set(entry.get("reasons") or [])),
            })
    items.sort(key=lambda item: (item["source"], item["key"] or ""))
    return items


# ---------------------------------------------------------------------------
# 章节
# ---------------------------------------------------------------------------


def _overview(artifacts, rows, pending):
    actions = artifacts["actions"]
    counts = {
        level: len([row for row in rows if row.get("action_level") == level])
        for level in contract.ACTION_LEVELS
    }
    blocking = len([
        row for row in rows
        if row.get("action_level") in contract.BLOCKING_ACTION_LEVELS
    ])
    scenario = artifacts["scenario"]
    pairs = [
        ("规则包版本", actions.get("ruleset_version")),
        ("依赖条目", "{0} 条".format(len(rows))),
        ("场景", "{0}（交付 {1} / 链接 {2}）".format(
            scenario.get("scenario"), scenario.get("delivery"), scenario.get("link_mode")
        )),
        ("项目 outbound 许可证", actions.get("outbound_license")),
        ("阻断/隔离级条目", "{0} 条".format(blocking)),
        ("待人工确认项", "{0} 条".format(len(pending))),
    ]
    for level in contract.ACTION_LEVELS:
        pairs.append((
            "处置级别 {0}".format(contract.ACTION_LEVEL_LABELS.get(level, level)),
            "{0} 条".format(counts.get(level, 0)),
        ))
    return pairs


def _anchor_items(artifacts):
    anchors = []
    for record in artifacts["actions"].get("actions") or []:
        evidence = record.get("evidence") or {}
        if record.get("level") is None:
            continue
        anchors.append({
            "package": record.get("package"),
            "version": record.get("version"),
            "spdx_id": record.get("spdx_id"),
            "declaration_location": evidence.get("declaration_location"),
            "basis_clause": evidence.get("basis_clause"),
            "rule_id": evidence.get("rule_id"),
            "anchor": evidence.get("anchor"),
            "checked_on": evidence.get("checked_on"),
            "missing_anchors": list(evidence.get("missing_anchors") or []),
        })
    return anchors


def _risk_groups(artifacts, rows):
    groups = []
    for tier in contract.TIERS:
        members = [row for row in rows if row.get("tier") == tier]
        if not members:
            continue
        groups.append({
            "label": "{0}（{1}）".format(contract.TIER_LABELS.get(tier, tier), tier),
            "items": [
                "{0} {1}（{2}）".format(
                    row.get("package"), row.get("version"), row.get("spdx_id")
                )
                for row in members
            ],
        })
    ungraded = [row for row in rows if not row.get("tier")]
    if ungraded:
        groups.append({
            "label": "档位未覆盖（待人工确认）",
            "items": [
                "{0} {1}".format(row.get("package"), row.get("version"))
                for row in ungraded
            ],
        })
    return groups


def _advice(artifacts):
    records = []
    for record in artifacts["actions"].get("actions") or []:
        level = record.get("level")
        if level is None:
            continue
        evidence = record.get("evidence") or {}
        records.append({
            "level": level,
            "level_label": contract.ACTION_LEVEL_LABELS.get(level, level),
            "package": record.get("package"),
            "version": record.get("version"),
            "spdx_id": record.get("spdx_id"),
            "reasons": list(record.get("reasons") or []),
            "basis_clause": evidence.get("basis_clause"),
            "declaration_location": evidence.get("declaration_location"),
        })
    records.sort(key=lambda item: (
        contract.ACTION_LEVELS.index(item["level"])
        if item["level"] in contract.ACTION_LEVELS else len(contract.ACTION_LEVELS),
        item.get("package") or "",
    ))
    return records


def build_report(artifacts):
    """把五份产物折成「八章节结构 + 逐包明细行」。纯函数：不读盘、不判判定。"""
    rows = package_rows(artifacts)
    pending = pending_items(artifacts)
    anchors = _anchor_items(artifacts)
    sections = [
        {
            "title": contract.REPORT_SECTIONS[0],
            "kind": "pairs",
            "data": _overview(artifacts, rows, pending),
        },
        {
            "title": contract.REPORT_SECTIONS[1],
            "kind": "lines",
            "data": list(SCOPE_STATEMENTS),
        },
        {
            "title": contract.REPORT_SECTIONS[2],
            "kind": "anchors",
            "data": anchors,
            "note": JUDICIAL_ANCHOR,
        },
        {
            "title": contract.REPORT_SECTIONS[3],
            "kind": "table",
            "data": rows,
            "columns": list(contract.REPORT_CSV_COLUMNS),
        },
        {
            "title": contract.REPORT_SECTIONS[4],
            "kind": "groups",
            "data": _risk_groups(artifacts, rows),
        },
        {
            "title": contract.REPORT_SECTIONS[5],
            "kind": "advice",
            "data": _advice(artifacts),
        },
        {
            "title": contract.REPORT_SECTIONS[6],
            "kind": "pending",
            "data": pending,
        },
        {
            "title": contract.REPORT_SECTIONS[7],
            "kind": "quote",
            "data": contract.DISCLAIMER,
        },
    ]
    titles = [section["title"] for section in sections]
    assert titles == list(contract.REPORT_SECTIONS)
    return {"rows": rows, "sections": sections, "pending": pending}


def has_blocking_levels(report):
    """报告中是否存在阻断/隔离级条目（退出码联动用；不做任何判定）。"""
    for section in report["sections"]:
        if section["kind"] != "advice":
            continue
        for item in section["data"]:
            if item["level"] in contract.BLOCKING_ACTION_LEVELS:
                return True
    return False


__all__ = [
    "JUDICIAL_ANCHOR",
    "PENDING_SOURCES",
    "SCOPE_STATEMENTS",
    "build_report",
    "has_blocking_levels",
    "package_rows",
    "pending_items",
]
