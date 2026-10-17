# -*- coding: utf-8 -*-
"""M5 处置分级（判定侧）。

输入：``inventory.json`` + ``profile.json`` + ``scenario.json`` + ``conflicts.json``
+ 规则包 ``action-rules.json``。输出：``actions.json`` —— 每条依赖一条处置记录，
字段序 == :data:`licaudit.contract.ACTION_FIELDS`。

判定纪律（plan/03 §5，K18 / K20）：

- **分级只查决策表**：``level`` 一律来自 ``action-rules.json`` 的 ``when`` 谓词匹配
  （第一命中者生效），本模块不写任何「义务项 → 处置级别」的条件分支，也不内联
  义务项 / 档位 / 处置级别字面量；义务项到「义务轴」的映射同样来自规则表
  （``obligation_axes``）。
- **五锚点门**（K20）：``package`` + ``version`` + ``declaration_location`` +
  ``spdx_id`` + ``basis_clause`` 缺任一 → 该条**不进处置建议**（``level`` 为 ``null``），
  只进 ``pending_confirmation`` 并写明缺哪一项。
- **不确定就不分级**：场景结论或兼容性结论为 ``pending``、依赖间冲突对未定、
  义务轴映射不可用 → 同样只进待确认。这与 K7 / K14 同口径：不知道不猜。
- **退出码**：存在 ``replace_or_license`` / ``isolate``（``contract.BLOCKING_ACTION_LEVELS``）
  或存在待确认项 → 编排层返回 1。
- 传染范围聚合仍未实现（决策 D34 / D36）：本里程碑用决策表的 ``link_mode`` 维度表达
  「边界可分离」，聚合本身不做；产物 ``notes`` 里明文登记。
"""

from .. import contract
from .profile import canonical_obligations, inventory_records

ACTION_RULE_FILE = "action-rules.json"

ACTIONS_TOP_LEVEL_FIELDS = (
    "format",
    "format_version",
    "ruleset_version",
    "scenario",
    "delivery",
    "link_mode",
    "outbound_license",
    "actions",
    "pending_confirmation",
    "notes",
)

# 决策表谓词（与 ``tools/gen_ruleset.py`` 同一份取值域）。
PREDICATES = (
    "axes_any",
    "axes_only",
    "conflict",
    "pair_conflict",
    "link_mode",
    "verdict",
)

PAIR_CONFLICT_NONE = "none"
PAIR_CONFLICT_INCOMPATIBLE = "incompatible"

# 原因码（写进产物，便于报告层原样展示）。
REASON_ACTION_UNCOVERED = "action_rule_uncovered"
REASON_ACTION_RULES_UNAVAILABLE = "action_rules_unavailable"
REASON_PACKAGE_MISSING = "package_missing"
REASON_VERSION_UNKNOWN = "version_unknown"
REASON_SPDX_MISSING = "spdx_id_missing"
REASON_DECLARATION_MISSING = "declaration_location_missing"
REASON_BASIS_MISSING = "basis_clause_missing"
REASON_SCENARIO_MISSING = "scenario_record_missing"
REASON_SCENARIO_PENDING = "scenario_pending_confirmation"
REASON_CONFLICT_MISSING = "conflict_record_missing"
REASON_CONFLICT_PENDING = "conflict_pending"
REASON_PAIR_PENDING = "pair_conflict_pending"

NOTE_TABLE_DRIVEN = "action_level_is_table_driven"
NOTE_SCOPE_AGGREGATION = "scope_aggregation_not_implemented"

# 五锚点名称（缺项时写进 ``evidence.missing_anchors``，与 plan/03 §5.2 同名）。
ANCHOR_NAMES = (
    "package",
    "version",
    "declaration_location",
    "spdx_id",
    "basis_clause",
)

_REASON_TEXTS = {
    REASON_ACTION_UNCOVERED: "决策表没有覆盖当前情形，未给出处置级别",
    REASON_ACTION_RULES_UNAVAILABLE: "规则包的处置决策表不可用（义务轴映射缺失或条目全被拒绝）",
    REASON_PACKAGE_MISSING: "缺少包名",
    REASON_VERSION_UNKNOWN: "依赖版本未知，按 * 记账并降级为待人工确认",
    REASON_SPDX_MISSING: "缺少 SPDX 标识，无法确定许可证义务",
    REASON_DECLARATION_MISSING: "缺少声明位置（清单文件 + 字段/行号）",
    REASON_BASIS_MISSING: "缺少依据条款（规则包锚点或触发表 rule_id + 条款）",
    REASON_SCENARIO_MISSING: "缺少该依赖的场景判定记录",
    REASON_SCENARIO_PENDING: "场景结论为待确认，未触发义务集合未知",
    REASON_CONFLICT_MISSING: "缺少该依赖的兼容性判定记录",
    REASON_CONFLICT_PENDING: "兼容性结论为待定，与项目 outbound 是否相容未知",
    REASON_PAIR_PENDING: "涉及未定的依赖间冲突对，冲突结论未知",
}

_ANCHOR_TEXT_KEYS = {
    "package": REASON_PACKAGE_MISSING,
    "version": REASON_VERSION_UNKNOWN,
    "declaration_location": REASON_DECLARATION_MISSING,
    "spdx_id": REASON_SPDX_MISSING,
    "basis_clause": REASON_BASIS_MISSING,
}


# ---------------------------------------------------------------------------
# 规则表（第二道门）
# ---------------------------------------------------------------------------


def _is_disabled_entry(entry):
    """规则本身是否已失效（K10）：与 loader 同口径的第二道门。"""
    if entry.get("verified") is not True:
        return True
    if not entry.get("checked_on"):
        return True
    anchor = entry.get("anchor")
    if not isinstance(anchor, dict):
        return True
    for key in ("source", "ref"):
        value = anchor.get(key)
        if not isinstance(value, str) or not value.strip():
            return True
    return False


def obligation_axes(document):
    """从规则包文档取 «义务项 → 义务轴» 映射。

    映射不完整（或缺失）时返回 ``None``：此时**整张表都不可用**，
    否则「轴为空」会被误读成「没有义务」，从而给出 ``ok``。这是 K4/K18 的硬边界：
    义务项字面量只在规则表里出现一次。
    """
    if not isinstance(document, dict):
        return None
    raw = document.get("obligation_axes")
    if not isinstance(raw, dict):
        return None
    mapped = {}
    for obligation in contract.OBLIGATIONS:
        axis = raw.get(obligation)
        if not isinstance(axis, str) or not axis.strip():
            return None
        mapped[obligation] = axis
    return mapped


def usable_rules(entries, axes):
    """过滤出可参与分级的决策表条目（不依赖调用方是否经过 loader）。

    ``axes`` 不可用时返回空表：调用方据此把全部条目标为待人工确认，
    而不是让「无轴」的规则把未知说成 ``ok``。
    """
    if not axes:
        return []
    usable = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        if _is_disabled_entry(entry):
            continue
        if entry.get("level") not in contract.ACTION_LEVELS:
            continue
        if not isinstance(entry.get("basis"), str) or not entry["basis"].strip():
            continue
        when = entry.get("when")
        if not isinstance(when, dict) or not when:
            continue
        if any(key not in PREDICATES for key in when):
            continue
        if _when_uses_undefined_axis(when, axes):
            continue
        usable.append(entry)
    return usable


def _when_uses_undefined_axis(when, axes):
    known = set(axes.values())
    for key in ("axes_any", "axes_only"):
        for item in when.get(key) or []:
            names = item if isinstance(item, list) else [item]
            for name in names:
                if not isinstance(name, str) or name not in known:
                    return True
    return False


def matches(when, facts):
    """通用谓词匹配；谓词种类由规则表数据决定，这里不含任何档位/义务分支。"""
    for key in sorted(when):
        wanted = when[key]
        if key == "axes_any":
            if not (set(facts.get("axes") or []) & set(wanted)):
                return False
        elif key == "axes_only":
            if set(facts.get("axes") or []) not in [set(item) for item in wanted]:
                return False
        else:
            if facts.get(key) not in wanted:
                return False
    return True


def match_rule(facts, rules):
    """决策表按书写顺序**第一命中者生效**；都不命中返回 ``None``（不猜级别）。"""
    for rule in rules:
        if matches(rule.get("when") or {}, facts):
            return rule
    return None


# ---------------------------------------------------------------------------
# 事实（只读上游产物的字段，不重新判定）
# ---------------------------------------------------------------------------


def axes_for(obligations, axes):
    """义务项集合 → 义务轴集合（去重、排序，确定性输出）。"""
    found = set()
    for obligation in obligations or []:
        axis = (axes or {}).get(obligation)
        if axis:
            found.add(axis)
    return sorted(found)


def _scenario_index(scenario_payload):
    index = {}
    for entry in scenario_payload.get("entries") or []:
        if isinstance(entry, dict) and entry.get("package") not in index:
            index[entry.get("package")] = entry
    return index


def _outbound_index(conflicts_payload):
    """``{package: 依赖 × outbound 条目}``。

    兼容性条目按「起支配作用的许可证」归并，包名登记在 ``evidence.packages``；
    一个包只可能落在一个许可证组里，因此取第一条即可（冲突引擎保证互斥）。
    """
    index = {}
    for record in conflicts_payload.get("outbound_conflicts") or []:
        if not isinstance(record, dict):
            continue
        packages = (record.get("evidence") or {}).get("packages") or []
        for package in packages:
            index.setdefault(package, record)
    return index


def _pair_index(conflicts_payload):
    """``{package: [(pair_id, resolution), ...]}``（依赖间冲突两侧都登记）。"""
    index = {}
    for record in conflicts_payload.get("dependency_conflicts") or []:
        if not isinstance(record, dict):
            continue
        packages = (record.get("evidence") or {}).get("packages") or {}
        if not isinstance(packages, dict):
            continue
        seen = []
        for side in sorted(packages):
            for package in packages[side] or []:
                if package in seen:
                    continue
                seen.append(package)
                index.setdefault(package, []).append(
                    (record.get("pair_id"), record.get("resolution"))
                )
    return index


def pair_conflict_state(records):
    """依赖间冲突的最坏结论：``incompatible`` > ``pending`` > ``none``。

    ``compatible``（已登记为相容）与「未登记」同归 ``none``：两者都表示
    「没有判定为不兼容的已登记组合」，证据保留在 ``evidence.pair_ids``。
    """
    state = PAIR_CONFLICT_NONE
    for _pair_id, resolution in records or []:
        if resolution == "incompatible":
            return PAIR_CONFLICT_INCOMPATIBLE
        if resolution == "pending":
            state = "pending"
    return state


def declaration_location(evidence):
    """声明位置字符串：``文件 :: 字段路径（第 N 行）``；给不出时返回 ``None``。"""
    if not isinstance(evidence, dict):
        return None
    path = evidence.get("file")
    if not isinstance(path, str) or not path.strip():
        return None
    field = evidence.get("locator")
    line = evidence.get("line")
    has_field = isinstance(field, str) and bool(field.strip())
    has_line = isinstance(line, int)
    if not has_field and not has_line:
        return None
    if has_field:
        text = "{0} :: {1}".format(path, field)
    else:
        text = "{0} :: 第 {1} 行".format(path, line)
    if has_field and has_line:
        text = "{0}（第 {1} 行）".format(text, line)
    return text


def basis_clause(rule):
    """依据条款字符串：``规则条目 id｜锚点 ref 节号``；锚点不可用时返回 ``None``。"""
    anchor = (rule or {}).get("anchor")
    if not isinstance(anchor, dict):
        return None
    reference = anchor.get("ref")
    if not isinstance(reference, str) or not reference.strip():
        return None
    text = "{0}｜{1}".format(rule.get("id") or "", reference)
    section = anchor.get("section")
    if isinstance(section, str) and section.strip():
        text = "{0} {1}".format(text, section)
    return text


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def _facts_for(scenario_entry, outbound_record, pairs, link_mode, axes):
    obligations = []
    rule_ids = []
    verdict = None
    if scenario_entry is not None:
        evidence = scenario_entry.get("evidence") or {}
        obligations = list(evidence.get("obligations") or [])
        rule_ids = list(evidence.get("rule_ids") or [])
        verdict = scenario_entry.get("verdict")
    conflict = (outbound_record or {}).get("resolution")
    return {
        "axes": axes_for(obligations, axes),
        "conflict": conflict,
        "pair_conflict": pair_conflict_state(pairs),
        "link_mode": link_mode,
        "verdict": verdict,
    }, canonical_obligations(obligations), rule_ids


def _gate_reasons(record, facts, scenario_entry, outbound_record, rules_available):
    """五锚点门 + 确定性门；返回 ``(原因码列表, 缺项名列表)``。"""
    reasons = []
    missing = []
    if not isinstance(record.get("package"), str) or not record["package"].strip():
        reasons.append(REASON_PACKAGE_MISSING)
        missing.append("package")
    version = record.get("version")
    if not isinstance(version, str) or not version.strip() or version == "*":
        reasons.append(REASON_VERSION_UNKNOWN)
        missing.append("version")
    if not record.get("spdx_id"):
        reasons.append(REASON_SPDX_MISSING)
        missing.append("spdx_id")
    if declaration_location(record.get("evidence")) is None:
        reasons.append(REASON_DECLARATION_MISSING)
        missing.append("declaration_location")
    if not rules_available:
        reasons.append(REASON_ACTION_RULES_UNAVAILABLE)
    if scenario_entry is None:
        reasons.append(REASON_SCENARIO_MISSING)
    elif facts["verdict"] == contract.PENDING:
        reasons.append(REASON_SCENARIO_PENDING)
    if outbound_record is None:
        reasons.append(REASON_CONFLICT_MISSING)
    elif facts["conflict"] == "pending":
        reasons.append(REASON_CONFLICT_PENDING)
    if facts["pair_conflict"] == "pending":
        reasons.append(REASON_PAIR_PENDING)
    return reasons, missing


def _record(package, version, spdx_id, level, reasons, evidence):
    """按 ``contract.ACTION_FIELDS`` 的字段序构造记录（契约变更会被断言拦住）。"""
    record = {
        "package": package,
        "version": version,
        "spdx_id": spdx_id,
        "level": level,
        "reasons": list(reasons),
        "evidence": evidence,
    }
    assert tuple(record) == contract.ACTION_FIELDS
    return record


def build_actions(inventory, profile_payload, scenario_payload, conflicts_payload,
                  ruleset):
    """产 ``actions.json`` 字典形态（核心；不读盘、不写盘）。

    ``profile_payload`` 只用于取档位展示字段；分级本身只查 ``action-rules.json``。
    """
    document = ruleset.documents.get(ACTION_RULE_FILE) if ruleset is not None else {}
    axes = obligation_axes(document)
    rules = usable_rules(
        ruleset.entries(ACTION_RULE_FILE) if ruleset is not None else [], axes
    )
    rules_available = bool(axes) and bool(rules)
    ruleset_version = ruleset.version if ruleset is not None else None

    tiers = {}
    for item in profile_payload.get("profiles") or []:
        if isinstance(item, dict) and item.get("spdx_id"):
            tiers[item["spdx_id"]] = item.get("tier")

    scenario_index = _scenario_index(scenario_payload)
    outbound_index = _outbound_index(conflicts_payload)
    pair_index = _pair_index(conflicts_payload)
    link_mode = scenario_payload.get("link_mode")
    scenario_id = scenario_payload.get("scenario")
    delivery = scenario_payload.get("delivery")
    outbound_license = conflicts_payload.get("outbound_license")

    actions = []
    pending = []
    for record in inventory_records(inventory):
        package = record.get("package")
        version = record.get("version")
        spdx_id = record.get("spdx_id")
        scenario_entry = scenario_index.get(package)
        outbound_record = outbound_index.get(package)
        pairs = pair_index.get(package) or []
        facts, obligations, trigger_rule_ids = _facts_for(
            scenario_entry, outbound_record, pairs, link_mode, axes
        )
        reasons, missing = _gate_reasons(
            record, facts, scenario_entry, outbound_record, rules_available
        )
        rule = match_rule(facts, rules) if not reasons else None
        if not reasons and rule is None:
            reasons.append(REASON_ACTION_UNCOVERED)
        level = rule.get("level") if rule is not None and not reasons else None
        basis = basis_clause(rule) if rule is not None else None
        if not reasons and basis is None:
            reasons.append(REASON_BASIS_MISSING)
            missing.append("basis_clause")
            level = None
            rule = None
            basis = None

        code_texts = [_REASON_TEXTS.get(code, code) for code in reasons]
        human = list(code_texts)
        if rule is not None:
            human = [rule["basis"]]
        normalized_version = version if isinstance(version, str) and version.strip() else "*"
        tier = tiers.get(spdx_id)
        if tier is None and outbound_record is not None:
            # 表达式依赖：画像按原子出，档位取冲突层求值选中的原子。
            tier = (outbound_record.get("evidence") or {}).get("node_tier")
        action = _record(
            package,
            normalized_version,
            spdx_id,
            level,
            human,
            {
                "ruleset_version": ruleset_version,
                "rule_file": ACTION_RULE_FILE,
                "rule_id": rule.get("id") if rule is not None else None,
                "rule_basis": rule.get("basis") if rule is not None else None,
                "basis_clause": basis,
                "anchor": rule.get("anchor") if rule is not None else None,
                "checked_on": rule.get("checked_on") if rule is not None else None,
                "declaration_location": declaration_location(record.get("evidence")),
                "declaration_file": (record.get("evidence") or {}).get("file"),
                "declaration_field": (record.get("evidence") or {}).get("locator"),
                "declaration_line": (record.get("evidence") or {}).get("line"),
                "raw_license": record.get("raw_license"),
                "tier": tier,
                "obligations": obligations,
                "axes": facts["axes"],
                "scenario": scenario_id,
                "delivery": delivery,
                "link_mode": link_mode,
                "verdict": facts["verdict"],
                "trigger_rule_ids": trigger_rule_ids,
                "outbound_license": outbound_license,
                "conflict_resolution": facts["conflict"],
                "pair_conflict": facts["pair_conflict"],
                "pair_ids": sorted({pair_id for pair_id, _r in pairs if pair_id}),
                "reason_codes": sorted(set(reasons)),
                "missing_anchors": sorted(set(missing)),
            },
        )
        actions.append(action)
        if level is None:
            pending.append({
                "package": package,
                "spdx_id": spdx_id,
                "reasons": sorted(set(reasons)),
            })

    actions.sort(key=lambda item: (item["package"] or "", item["spdx_id"] or ""))
    pending.sort(key=lambda item: (item["package"] or "", item["spdx_id"] or ""))

    notes = [{
        "code": NOTE_TABLE_DRIVEN,
        "message": "处置级别只查规则包 action-rules.json 决策表（义务轴 + 冲突结论 + "
                   "链接方式，先命中者生效）；输入的档位级粗判偏差见 conflicts.json.notes",
    }, {
        "code": NOTE_SCOPE_AGGREGATION,
        "message": "传染范围聚合（plan/03 §4.6）未实现：处置分级用决策表的 link_mode "
                   "维度表达「边界是否可分离」，不按链接/分发边界聚合",
    }]
    if not rules_available:
        notes.append({
            "code": REASON_ACTION_RULES_UNAVAILABLE,
            "message": "规则包的处置决策表不可用：义务轴映射缺失或全部条目被拒绝，"
                       "本次未给出任何处置级别",
        })

    return {
        "format": contract.ACTION_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "ruleset_version": ruleset_version,
        "scenario": scenario_id,
        "delivery": delivery,
        "link_mode": link_mode,
        "outbound_license": outbound_license,
        "actions": actions,
        "pending_confirmation": pending,
        "notes": notes,
    }


def has_blocking_action(payload):
    """是否存在阻断级处置或待确认项 —— 编排层据此决定退出码（plan/03 §5.5）。"""
    for record in payload.get("actions") or []:
        if record.get("level") in contract.BLOCKING_ACTION_LEVELS:
            return True
    return bool(payload.get("pending_confirmation"))


__all__ = [
    "ACTION_RULE_FILE",
    "ACTIONS_TOP_LEVEL_FIELDS",
    "ANCHOR_NAMES",
    "NOTE_SCOPE_AGGREGATION",
    "NOTE_TABLE_DRIVEN",
    "PAIR_CONFLICT_INCOMPATIBLE",
    "PAIR_CONFLICT_NONE",
    "PREDICATES",
    "REASON_ACTION_RULES_UNAVAILABLE",
    "REASON_ACTION_UNCOVERED",
    "REASON_BASIS_MISSING",
    "REASON_CONFLICT_MISSING",
    "REASON_CONFLICT_PENDING",
    "REASON_DECLARATION_MISSING",
    "REASON_PACKAGE_MISSING",
    "REASON_PAIR_PENDING",
    "REASON_SCENARIO_MISSING",
    "REASON_SCENARIO_PENDING",
    "REASON_SPDX_MISSING",
    "REASON_VERSION_UNKNOWN",
    "axes_for",
    "basis_clause",
    "build_actions",
    "declaration_location",
    "has_blocking_action",
    "match_rule",
    "matches",
    "obligation_axes",
    "pair_conflict_state",
    "usable_rules",
]
