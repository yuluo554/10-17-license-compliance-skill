# -*- coding: utf-8 -*-
"""M4 冲突与兼容性分析。

输入：``inventory.json`` + ``profile.json``（档位与义务）+ 规则包 ``conflict-pairs.json``
+ 用户给出的项目 outbound 许可证（SPDX 表达式或 ``pending``）；场景上下文只落盘、不参与判定。
输出：``conflicts.json`` —— 两类冲突条目，共用 ``contract.CONFLICT_FIELDS`` 记录形态：

1. **依赖间冲突**：两条依赖的许可证不可同时满足 —— 只查 ``conflict-pairs.json``；
2. **依赖 × outbound 冲突**：依赖的档位/义务与项目准备采用的 outbound 许可证比较。

判定纪律（plan/03 §4，K15–K17）：

- 冲突对**无向匹配**：``(left, right)`` 与 ``(right, left)`` 等价；产物里按规则表书写顺序输出。
- ``OR`` 取最宽松、``AND`` 取最严格（按 :data:`contract.TIER_RANK`），按文法递归求值；
  求值过程写进 ``expression_evaluations``（含所选原子与理由），**不得只给最终 ID**。
- ``outbound = pending`` → 全部「依赖 × outbound」条目为 ``pending``，文案固定
  :data:`BASIS_OUTBOUND_PENDING`，**不按最宽松默认**（K17）。
- 档位未覆盖（``tier: null``）→ ``pending``，不猜档位（K31）。
- 引擎不复制五档 / 义务 / 冲突三态枚举：一律从 :mod:`licaudit.contract` 取（K4）。
- outbound 的合法性与「未知 ID → exit 2」由
  :func:`licaudit.assess.scenario.validate_outbound` 在编排层挡住；本模块只做判定。
- 传染范围聚合（plan/03 §4.6）本里程碑未实现：判定只做**档位级比较**，产物以 ``notes``
  显式登记这一口径，避免把粗判读成「按链接边界聚合后」的结论。
"""

from .. import contract
from ..inventory.spdx_expr import ExprError, parse_expression
from .profile import canonical_obligations, inventory_records, profile_ids, split_atoms

CONFLICT_RULE_FILE = "conflict-pairs.json"

CONFLICT_TOP_LEVEL_FIELDS = (
    "format",
    "format_version",
    "ruleset_version",
    "scenario",
    "delivery",
    "link_mode",
    "outbound_license",
    "outbound_tier",
    "dependency_conflicts",
    "outbound_conflicts",
    "expression_evaluations",
    "uncovered_pairs",
    "pending_confirmation",
    "notes",
)

# 原因码（写进产物，便于报告层原样展示）。
REASON_OUTBOUND_PENDING = "outbound_pending"
REASON_OUTBOUND_TIER_UNAVAILABLE = "outbound_tier_unavailable"
REASON_TIER_UNAVAILABLE = "tier_unavailable"
REASON_SPDX_MISSING = "spdx_id_missing"
REASON_EXPRESSION_UNRESOLVED = "expression_unresolved"

# outbound 待定时的固定文案（plan/03 §4.5：不按最宽松默认）。
BASIS_OUTBOUND_PENDING = "项目自身许可证待定"

NOTE_SCOPE_AGGREGATION = "scope_aggregation_not_implemented"

# ``uncovered_pairs`` 只作覆盖度登记，列出上限；``count`` 恒为真实值。
UNCOVERED_PAIR_LIMIT = 100


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


def usable_pairs(entries):
    """过滤出可参与判定的冲突对条目（不依赖调用方是否经过 loader）。"""
    usable = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        if _is_disabled_entry(entry):
            continue
        left = entry.get("left")
        right = entry.get("right")
        if not isinstance(left, str) or not left.strip():
            continue
        if not isinstance(right, str) or not right.strip():
            continue
        if left == right:
            continue
        if entry.get("resolution") not in contract.CONFLICT_RESOLUTIONS:
            continue
        if not isinstance(entry.get("basis"), str) or not entry["basis"].strip():
            continue
        usable.append(entry)
    return usable


def pair_key(left, right):
    """无向键：排序后的两元组（不使用 ``set``，避免迭代序影响结果）。"""
    return (left, right) if left <= right else (right, left)


def pair_lookup(entries):
    """``{(left, right) 排序后: 条目}``；同一组合重复登记时先出现者生效。"""
    lookup = {}
    for entry in usable_pairs(entries):
        lookup.setdefault(pair_key(entry["left"], entry["right"]), entry)
    return lookup


# ---------------------------------------------------------------------------
# 画像索引（档位 / 义务）
# ---------------------------------------------------------------------------


def _profile_index(profile_payload):
    by_id = {}
    for item in profile_payload.get("profiles") or []:
        if isinstance(item, dict) and item.get("spdx_id"):
            by_id[item["spdx_id"]] = item
    return by_id


def _ensure_profiles(atoms, by_id, ruleset, index):
    """画像里没有的原子（典型：outbound 用的许可证不在依赖里）用同一份规则表现算补上。"""
    missing = sorted({atom for atom in atoms if atom and atom not in by_id})
    if missing and ruleset is not None:
        extra = profile_ids(missing, ruleset, index)
        for item in extra.get("profiles") or []:
            if item.get("spdx_id"):
                by_id[item["spdx_id"]] = item
    return by_id


def _atom_tier(atom, by_id):
    tier = (by_id.get(atom) or {}).get("tier")
    return tier if tier in contract.TIERS else None


def _atom_obligations(atom, by_id):
    return canonical_obligations((by_id.get(atom) or {}).get("obligations") or [])


# ---------------------------------------------------------------------------
# 表达式求值（K16）
# ---------------------------------------------------------------------------


def _exceptions_in(node, out):
    if "op" in node:
        for child in node["args"]:
            _exceptions_in(child, out)
    elif node.get("exception") and node["exception"] not in out:
        out.append(node["exception"])
    return out


def _eval_node(node, tier_by_atom, missing):
    """递归求值：``OR`` 取最宽松、``AND`` 取最严格（按 ``contract.TIER_RANK``）。

    同档位并列时取**出现顺序在前的**原子（确定性）。任一支缺少档位 → 返回 ``None``
    并把该原子记进 ``missing``：不知道就不能比较（K7/K31）。
    """
    if "op" in node:
        best = None
        for child in node["args"]:
            leaf = _eval_node(child, tier_by_atom, missing)
            if leaf is None:
                return None
            if best is None:
                best = leaf
                continue
            best_rank = contract.TIER_RANK[best[1]]
            leaf_rank = contract.TIER_RANK[leaf[1]]
            if node["op"] == "OR":
                if leaf_rank < best_rank:
                    best = leaf
            else:
                if leaf_rank > best_rank:
                    best = leaf
        return best

    atom = node["id"]
    tier = tier_by_atom.get(atom)
    if tier not in contract.TIERS:
        if atom not in missing:
            missing.append(atom)
        return None
    return (atom, tier)


def evaluate_expression(text, tier_by_atom, index):
    """把一条 SPDX 表达式求值为「起支配作用的原子」（纯函数，不读盘、不读时钟）。

    返回记录含 ``expression`` / ``operator`` / ``atoms`` / ``selected`` / ``tier`` /
    ``resolved`` / ``reason`` / ``exceptions``；无法求值（解析失败或缺档位）时
    ``resolved = False`` 且 ``selected = None``（不猜）。
    """
    evaluation = {
        "expression": text,
        "operator": None,
        "atoms": [],
        "selected": None,
        "tier": None,
        "resolved": False,
        "reason": "",
        "exceptions": [],
    }
    if not isinstance(text, str) or not text.strip():
        evaluation["reason"] = "空表达式，未求值"
        return evaluation
    try:
        parsed = parse_expression(text, index)
    except ExprError:
        evaluation["atoms"] = [text]
        evaluation["reason"] = "表达式无法按 SPDX 文法解析，整串作为单个原子保留"
        return evaluation

    node = parsed.node
    evaluation["atoms"] = list(parsed.atoms)
    evaluation["operator"] = node.get("op") if "op" in node else "single"
    evaluation["exceptions"] = _exceptions_in(node, [])

    missing = []
    leaf = _eval_node(node, tier_by_atom, missing)
    if leaf is None:
        evaluation["reason"] = "参与求值的原子缺少档位：{0}".format("、".join(missing))
        return evaluation
    evaluation["selected"] = leaf[0]
    evaluation["tier"] = leaf[1]
    evaluation["resolved"] = True
    if "op" not in node:
        text_reason = "单原子，无需求值"
    elif node["op"] == "OR":
        text_reason = "OR 取最宽松：{0}（{1}）".format(leaf[0], leaf[1])
    else:
        text_reason = "AND 取最严格：{0}（{1}）".format(leaf[0], leaf[1])
    if evaluation["exceptions"]:
        text_reason += "；保留例外标签：" + "、".join(evaluation["exceptions"])
    evaluation["reason"] = text_reason
    return evaluation


# ---------------------------------------------------------------------------
# 依赖记录：按「起支配作用的许可证」归并
# ---------------------------------------------------------------------------


def _group_record(groups, license_id, tier, obligations, package, spdx_id, evaluation):
    group = groups.get(license_id)
    if group is None:
        group = {
            "license_id": license_id,
            "tier": tier,
            "obligations": canonical_obligations(obligations),
            "packages": [],
            "raw_spdx_ids": [],
            "evaluation": evaluation,
        }
        groups[license_id] = group
    if package and package not in group["packages"]:
        group["packages"].append(package)
    if spdx_id and spdx_id not in group["raw_spdx_ids"]:
        group["raw_spdx_ids"].append(spdx_id)
    return group


def _sorted_names(values):
    return sorted(values, key=lambda item: item or "")


def license_groups(inventory, by_id, index):
    """把依赖按求值后的许可证归并；返回 ``(groups, evaluations, unresolved)``。

    多原子表达式在这里求值（K16），并记进 ``expression_evaluations``；
    单原子记录不求值、不登记。``unresolved`` 是「无法定档」的包级原因，供待确认项使用。
    """
    tier_by_atom = {spdx_id: _atom_tier(spdx_id, by_id) for spdx_id in by_id}
    groups = {}
    evaluations = []
    unresolved = []
    for record in inventory_records(inventory):
        spdx_id = record.get("spdx_id")
        package = record.get("package")
        atoms, _note = split_atoms(spdx_id, index)
        if not atoms:
            _group_record(groups, None, None, [], package, spdx_id, None)
            unresolved.append({"package": package, "reasons": [REASON_SPDX_MISSING]})
            continue
        if len(atoms) == 1:
            atom = atoms[0]
            _group_record(
                groups, atom, _atom_tier(atom, by_id), _atom_obligations(atom, by_id),
                package, spdx_id, None,
            )
            continue

        evaluation = evaluate_expression(spdx_id, tier_by_atom, index)
        evaluation["source"] = "dependency"
        evaluation["package"] = package
        evaluations.append(evaluation)
        if evaluation["resolved"]:
            atom = evaluation["selected"]
            _group_record(
                groups, atom, evaluation["tier"], _atom_obligations(atom, by_id),
                package, spdx_id, evaluation,
            )
            continue
        _group_record(groups, None, None, [], package, spdx_id, evaluation)
        unresolved.append({
            "package": package,
            "reasons": [REASON_EXPRESSION_UNRESOLVED, REASON_TIER_UNAVAILABLE],
        })

    ordered = []
    for key in sorted(groups, key=lambda item: (item is None, item or "")):
        group = groups[key]
        group["packages"] = _sorted_names(group["packages"])
        group["raw_spdx_ids"] = _sorted_names(group["raw_spdx_ids"])
        ordered.append(group)
    evaluations.sort(key=lambda item: (item.get("package") or "", item["expression"] or ""))
    return ordered, evaluations, unresolved


# ---------------------------------------------------------------------------
# 两类冲突条目
# ---------------------------------------------------------------------------


def _conflict_record(pair_id, left, right, basis, resolution, evidence):
    """按 ``contract.CONFLICT_FIELDS`` 的字段序构造记录（契约变更会被断言拦住）。"""
    record = {
        "pair_id": pair_id,
        "left": left,
        "right": right,
        "basis": basis,
        "resolution": resolution,
        "evidence": evidence,
    }
    assert tuple(record) == contract.CONFLICT_FIELDS
    return record


def dependency_conflicts(groups, lookup):
    """依赖间冲突：无向查表；未登记的组合返回给调用方登记为 ``uncovered_pairs``。

    返回 ``(records, uncovered, reasons)``；``reasons`` 是 ``pair_id → 原因码``，
    供待确认项复用（规则表里若登记 ``pending`` 条目，也要说清为什么）。
    """
    records = []
    uncovered = []
    reasons = {}
    by_license = {group["license_id"]: group for group in groups}
    for first in range(len(groups)):
        for second in range(first + 1, len(groups)):
            left = groups[first]["license_id"]
            right = groups[second]["license_id"]
            if left is None or right is None:
                continue
            entry = lookup.get(pair_key(left, right))
            if entry is None:
                uncovered.append(pair_key(left, right))
                continue
            packages = {}
            for side in (entry["left"], entry["right"]):
                group = by_license.get(side)
                packages[side] = list(group["packages"]) if group else []
            reasons[entry["pair_id"]] = ["curated_pair_pending"]
            records.append(_conflict_record(
                entry["pair_id"],
                entry["left"],
                entry["right"],
                entry["basis"],
                entry["resolution"],
                {
                    "source": "curated",
                    "rule_file": CONFLICT_RULE_FILE,
                    "anchor": entry.get("anchor"),
                    "cross_check": entry.get("cross_check"),
                    "checked_on": entry.get("checked_on"),
                    "packages": packages,
                },
            ))
    records.sort(key=lambda item: item["pair_id"])
    uncovered.sort()
    return records, uncovered, reasons


def outbound_resolution(group, outbound, outbound_tier, outbound_selected):
    """单条依赖 × outbound 的三态结论。

    ``outbound == "pending"``、依赖档位未覆盖、outbound 表达式无法求值 → ``pending``；
    依赖档位强于 outbound → ``incompatible``；依赖要求 ``same-license`` 而 outbound
    选了**另一个**许可证（且 outbound 档位不高于依赖档位）→ ``incompatible``。
    """
    if outbound == "pending":
        return "pending"
    if group["license_id"] is None or group["tier"] is None:
        return "pending"
    if outbound_tier is None or outbound_selected is None:
        return "pending"
    if contract.TIER_RANK[group["tier"]] > contract.TIER_RANK[outbound_tier]:
        return "incompatible"
    if (
        "same-license" in group["obligations"]
        and group["license_id"] != outbound_selected
        and contract.TIER_RANK[group["tier"]] >= contract.TIER_RANK[outbound_tier]
    ):
        return "incompatible"
    return "compatible"


def outbound_basis(group, outbound, evaluation, outbound_tier, outbound_selected):
    """依据文案；与 :func:`outbound_resolution` 的分支一一对应。"""
    if outbound == "pending":
        return BASIS_OUTBOUND_PENDING
    if group["license_id"] is None:
        return "依赖的许可证未识别，无法与项目 outbound 许可证比较"
    if group["tier"] is None:
        return "依赖档位未覆盖（{0}），无法与项目 outbound 许可证比较".format(
            group["license_id"]
        )
    if outbound_tier is None or outbound_selected is None:
        return "项目 outbound 表达式无法求值（{0}），不猜测档位高低".format(
            (evaluation or {}).get("reason") or outbound
        )
    if contract.TIER_RANK[group["tier"]] > contract.TIER_RANK[outbound_tier]:
        return (
            "依赖档位 {0}（{1}）强于项目 outbound 档位 {2}（{3}）；"
            "分发时同一作品无法只按 outbound 许可证发布".format(
                group["tier"], group["license_id"], outbound_tier, outbound_selected
            )
        )
    if (
        "same-license" in group["obligations"]
        and group["license_id"] != outbound_selected
        and contract.TIER_RANK[group["tier"]] >= contract.TIER_RANK[outbound_tier]
    ):
        return (
            "依赖要求同许可发布（same-license，{0}），项目 outbound 选定的是 {1}".format(
                group["license_id"], outbound_selected
            )
        )
    return (
        "依赖档位 {0}（{1}）不高于项目 outbound 档位 {2}（{3}）；未发现档位级冲突".format(
            group["tier"], group["license_id"], outbound_tier, outbound_selected
        )
    )


def _outbound_reasons(group, outbound, evaluation, outbound_tier):
    """该条待定的原因码（``resolution`` 为 pending 时才有内容）。"""
    reasons = []
    if outbound == "pending":
        reasons.append(REASON_OUTBOUND_PENDING)
    node_evaluation = group.get("evaluation")
    if node_evaluation is not None and node_evaluation.get("resolved") is not True:
        reasons.append(REASON_EXPRESSION_UNRESOLVED)
    if group["license_id"] is None:
        if node_evaluation is None:
            reasons.append(REASON_SPDX_MISSING)
        else:
            reasons.append(REASON_TIER_UNAVAILABLE)
    elif group["tier"] is None:
        reasons.append(REASON_TIER_UNAVAILABLE)
    if outbound != "pending" and evaluation is not None and outbound_tier is None:
        reasons.append(REASON_OUTBOUND_TIER_UNAVAILABLE)
    return sorted(set(reasons), key=lambda item: item)


def outbound_conflicts(groups, outbound, evaluation, outbound_tier, ruleset_version):
    """依赖 × outbound 条目（每个不同的依赖许可证一条）。

    返回 ``(records, reasons)``；``reasons`` 是 ``pair_id → 原因码``。
    """
    selected = (evaluation or {}).get("selected")
    if (evaluation or {}).get("resolved") is not True:
        selected = None
    records = []
    reasons = {}
    for group in groups:
        pair_id = "OB-{0}-{1}".format(group["license_id"] or "unidentified", outbound)
        resolution = outbound_resolution(group, outbound, outbound_tier, selected)
        records.append(_conflict_record(
            pair_id,
            group["license_id"],
            selected,
            outbound_basis(group, outbound, evaluation, outbound_tier, selected),
            resolution,
            {
                "source": "tier-comparison",
                "ruleset_version": ruleset_version,
                "node_spdx_id": group["license_id"],
                "node_raw_spdx_ids": list(group["raw_spdx_ids"]),
                "node_tier": group["tier"],
                "node_obligations": list(group["obligations"]),
                "outbound_spdx_id": selected,
                "outbound_tier": outbound_tier,
                "packages": list(group["packages"]),
            },
        ))
        reasons[pair_id] = _outbound_reasons(group, outbound, evaluation, outbound_tier)
    records.sort(key=lambda item: (item["left"] or "", item["pair_id"]))
    return records, reasons


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def _uncovered_payload(uncovered):
    items = [list(key) for key in uncovered[:UNCOVERED_PAIR_LIMIT]]
    return {
        "count": len(uncovered),
        "items": items,
        "items_truncated": len(uncovered) > len(items),
        "note": "规则包未登记的许可证组合；不参与判定，也不改变退出码",
    }


def _pending_entries(records, reasons):
    """``resolution = pending`` 的条目 → 顶层待确认列表（原因码来自判定分支）。"""
    pending = []
    for record in records:
        if record["resolution"] != "pending":
            continue
        pending.append({
            "pair_id": record["pair_id"],
            "left": record["left"],
            "right": record["right"],
            "reasons": sorted(set(reasons.get(record["pair_id"]) or [])),
        })
    pending.sort(key=lambda item: item["pair_id"])
    return pending


def build_conflicts(inventory, profile_payload, ruleset, outbound, scenario=None,
                    delivery=None, link_mode=None, spdx_index=None):
    """产 ``conflicts.json`` 字典形态（核心；不读盘、不写盘）。

    ``outbound`` 已经过 :func:`licaudit.assess.scenario.validate_outbound`（未知 ID 在编排层
    就 exit 2）。``scenario`` / ``delivery`` / ``link_mode`` 只作上下文落盘，不参与判定。
    """
    if spdx_index is None:
        from .profile import load_context

        spdx_index, _version = load_context()

    entries = usable_pairs(
        ruleset.entries(CONFLICT_RULE_FILE) if ruleset is not None else []
    )
    lookup = pair_lookup(entries)
    outbound_atoms = [] if outbound == "pending" else split_atoms(outbound, spdx_index)[0]
    by_id = _ensure_profiles(
        outbound_atoms, _profile_index(profile_payload), ruleset, spdx_index
    )
    tier_by_atom = {spdx_id: _atom_tier(spdx_id, by_id) for spdx_id in by_id}

    groups, evaluations, unresolved = license_groups(inventory, by_id, spdx_index)

    if outbound == "pending":
        outbound_evaluation = None
        outbound_tier = None
    else:
        outbound_evaluation = evaluate_expression(outbound, tier_by_atom, spdx_index)
        outbound_evaluation["source"] = "outbound"
        outbound_evaluation["package"] = None
        outbound_tier = outbound_evaluation["tier"] if outbound_evaluation["resolved"] else None
        evaluations.append(outbound_evaluation)

    pairs, uncovered, pair_reasons = dependency_conflicts(groups, lookup)
    outbound_records, outbound_reasons = outbound_conflicts(
        groups, outbound, outbound_evaluation, outbound_tier,
        ruleset.version if ruleset is not None else None,
    )

    reasons = {}
    reasons.update(pair_reasons)
    reasons.update(outbound_reasons)
    # 表达式无法定档的包级原因要并进对应条目的待确认原因（同一批依赖可能落在同一许可证组）。
    for item in unresolved:
        for record in outbound_records:
            if item.get("package") in (record["evidence"].get("packages") or []):
                reasons.setdefault(record["pair_id"], [])
                reasons[record["pair_id"]] = sorted(
                    set(reasons[record["pair_id"]]) | set(item["reasons"])
                )
                break

    notes = [{
        "code": NOTE_SCOPE_AGGREGATION,
        "message": "传染范围聚合（plan/03 §4.6）本里程碑未实现：依赖 × outbound 只做档位级比较，"
                   "未按链接/分发边界聚合",
    }]

    return {
        "format": contract.CONFLICT_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "ruleset_version": ruleset.version if ruleset is not None else None,
        "scenario": scenario,
        "delivery": delivery,
        "link_mode": link_mode,
        "outbound_license": outbound,
        "outbound_tier": outbound_tier,
        "dependency_conflicts": pairs,
        "outbound_conflicts": outbound_records,
        "expression_evaluations": evaluations,
        "uncovered_pairs": _uncovered_payload(uncovered),
        "pending_confirmation": _pending_entries(pairs + outbound_records, reasons),
        "notes": notes,
    }


def has_blocking_finding(payload):
    """是否存在「待定」或「不兼容」条目 —— 编排层据此决定退出码（plan/03 §六）。"""
    for key in ("dependency_conflicts", "outbound_conflicts"):
        for record in payload.get(key) or []:
            if record.get("resolution") in ("pending", "incompatible"):
                return True
    return False


__all__ = [
    "BASIS_OUTBOUND_PENDING",
    "CONFLICT_RULE_FILE",
    "CONFLICT_TOP_LEVEL_FIELDS",
    "NOTE_SCOPE_AGGREGATION",
    "UNCOVERED_PAIR_LIMIT",
    "build_conflicts",
    "dependency_conflicts",
    "evaluate_expression",
    "has_blocking_finding",
    "license_groups",
    "outbound_basis",
    "outbound_conflicts",
    "outbound_resolution",
    "pair_key",
    "pair_lookup",
    "usable_pairs",
]
