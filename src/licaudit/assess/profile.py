# -*- coding: utf-8 -*-
"""M2 许可证画像矩阵。

输入：``inventory.json`` + 规则包 ``tiers.json`` + SPDX 快照。
输出：``profile.json`` —— 每个**不同的 SPDX 原子 ID** 一条。

判定纪律（plan/03 §2）：

- 档位与义务只查 ``references/ruleset/tiers.json``；未覆盖 → ``tier: null`` +
  待人工确认，**不猜档位**。
- OSI / FSF 只从 SPDX 快照取；FSF 只展示，不参与任何判定（K9）。
- 专利 / 商标条款沿用 curated 已带原文锚点的条目（K7 / K8 约束档位与义务枚举）。
- ``AND`` / ``OR`` 表达式在 M2 只拆原子，不求值（求值属 M4，D23）。
- 规则包 ``disabled`` 条目一律不参与判定；命中 → ``tier: null`` + 待确认（K10）。
- 引擎不复制五档 / 义务枚举：一律从 :mod:`licaudit.contract` 取。
"""

from .. import contract
from ..inventory.spdx_expr import ExprError, SpdxIndex, parse_expression
from ..inventory.spdx_snapshot import load_snapshot

TIER_RULE_FILE = "tiers.json"

PROFILE_TOP_LEVEL_FIELDS = (
    "format",
    "format_version",
    "ruleset_version",
    "license_list_version",
    "profiles",
    "pending_confirmation",
    "disabled_rules",
    "notes",
)

_ANCHOR_FIELDS = ("source", "ref", "section", "quote")


def canonical_obligations(obligations):
    """按 ``contract.OBLIGATIONS`` 的固定顺序输出义务项。

    规则包可以按可读顺序书写，但产物必须稳定：报告/CSV 后续直接消费这份顺序。
    """
    wanted = set(obligations or [])
    return [item for item in contract.OBLIGATIONS if item in wanted]


# ---------------------------------------------------------------------------
# 原子拆分
# ---------------------------------------------------------------------------


def split_atoms(spdx_id, index):
    """把一条 ``spdx_id`` 拆成原子 ID（按出现顺序去重）。

    返回 ``(atoms, note_code)``。表达式无法解析时**不丢弃**该记录：整串作为一个
    原子保留，并返回 ``"expression_unparsed"`` 让调用方落注记。
    """
    if not isinstance(spdx_id, str):
        return [], None
    text = spdx_id.strip()
    if not text:
        return [], None
    try:
        parsed = parse_expression(text, index)
    except ExprError:
        return [text], "expression_unparsed"
    return parsed.atoms, None


def collect_atoms(inventory, index):
    """从 inventory 的两种记录里收集原子 ID（``dependencies`` + ``pending_confirmation``）。

    两个列表**不是互斥**的（D22）：同一条记录可能同时出现，因此按 ID 去重。
    """
    records = list(inventory.get("dependencies") or [])
    for entry in inventory.get("pending_confirmation") or []:
        if isinstance(entry, dict):
            records.append(entry.get("record") or {})

    atoms = []
    notes = []
    for record in records:
        if not isinstance(record, dict):
            continue
        found, note_code = split_atoms(record.get("spdx_id"), index)
        if note_code:
            notes.append((note_code, record.get("spdx_id")))
        for atom in found:
            if atom not in atoms:
                atoms.append(atom)
    return sorted(atoms), notes


def inventory_records(inventory):
    """``dependencies`` + ``pending_confirmation`` 两条非互斥列表（D22），去重后排序。

    M3 场景引擎与 M4 冲突引擎共用这一份读取口径：两列表都可能带记录，
    同 ``(package, spdx_id)`` 只算一条。
    """
    records = list(inventory.get("dependencies") or [])
    for entry in inventory.get("pending_confirmation") or []:
        if isinstance(entry, dict):
            records.append(entry.get("record") or {})

    unique = []
    seen = set()
    for record in records:
        if not isinstance(record, dict):
            continue
        key = (record.get("package"), record.get("spdx_id"))
        if key in seen:
            continue
        seen.add(key)
        unique.append(record)
    return sorted(
        unique, key=lambda item: (item.get("package") or "", item.get("spdx_id") or "")
    )


# ---------------------------------------------------------------------------
# 快照上下文
# ---------------------------------------------------------------------------


def load_context(spdx_dir=None):
    """返回 ``(SpdxIndex, license_list_version)``。快照缺失 → ``UsageError``（exit 2）。"""
    licenses, exceptions, manifest = load_snapshot(spdx_dir)
    version = manifest.get("license_list_version") or licenses.get("licenseListVersion")
    return SpdxIndex(licenses, exceptions), version


# ---------------------------------------------------------------------------
# 规则索引
# ---------------------------------------------------------------------------


def _index_rules(ruleset):
    """返回 ``(enabled_by_id, disabled_reasons_by_id, duplicated_ids)``。

    ``disabled`` 条目只用于解释「为什么没有档位」，**绝不参与判定**。
    """
    enabled = {}
    duplicated = set()
    for entry in ruleset.entries(TIER_RULE_FILE):
        license_id = entry.get("license_id")
        if not isinstance(license_id, str) or not license_id:
            continue
        if license_id in enabled:
            duplicated.add(license_id)
        enabled[license_id] = entry

    disabled = {}
    for item in ruleset.disabled:
        if not isinstance(item, dict):
            continue
        if item.get("file") != TIER_RULE_FILE:
            continue
        license_id = item.get("id")
        if not license_id:
            continue
        disabled.setdefault(license_id, []).extend(item.get("reasons") or [])
    return enabled, disabled, duplicated


def _copy_anchor(anchor):
    if not isinstance(anchor, dict):
        return None
    copied = {}
    for field in _ANCHOR_FIELDS:
        copied[field] = anchor.get(field)
    return copied


def _rule_problem(entry):
    """规则是否可用于判定；不可用时返回原因码。"""
    tier = entry.get("tier")
    if tier not in contract.TIERS:
        return "tier_not_in_contract"
    obligations = entry.get("obligations")
    if not isinstance(obligations, list):
        return "obligations_missing"
    for obligation in obligations:
        if obligation not in contract.OBLIGATIONS:
            return "obligation_not_in_contract"
    anchor = entry.get("anchor")
    if not isinstance(anchor, dict):
        return "anchor_missing"
    for key in ("source", "ref"):
        value = anchor.get(key)
        if not isinstance(value, str) or not value.strip():
            return "anchor_missing"
    return None


def _clause(rule_clause, checked_on):
    """把规则包里的条款描述投影为画像字段。

    无规则时 ``present = None``（不知道），**不写成 False**（没有条款）。
    """
    if not isinstance(rule_clause, dict):
        return {"present": None, "anchor": None, "checked_on": None}
    if rule_clause.get("present") is True:
        return {
            "present": True,
            "anchor": _copy_anchor(rule_clause.get("anchor")),
            "checked_on": checked_on,
        }
    return {"present": False, "anchor": None, "checked_on": checked_on}


def _missing_fields(has_rule, in_snapshot):
    missing = []
    if not has_rule:
        missing.extend(["tier", "obligations", "patent_clause", "trademark_clause"])
    if not in_snapshot:
        missing.extend(["is_osi_approved", "is_fsf_libre"])
    return missing


def _profile_entry(atom, rule, index, ruleset_version):
    """单条原子画像；``rule`` 为 ``None`` 表示无可用规则（档位留空，不猜）。"""
    in_snapshot = index.has_license(atom)
    details_url = index.details_url(atom) if in_snapshot else None
    is_osi = index.is_osi_approved(atom) if in_snapshot else None
    is_fsf = index.is_fsf_libre(atom) if in_snapshot else None

    if rule is None:
        entry = {
            "spdx_id": atom,
            "tier": None,
            "obligations": None,
            "is_osi_approved": is_osi,
            "is_fsf_libre": is_fsf,
            "patent_clause": _clause(None, None),
            "trademark_clause": _clause(None, None),
            "evidence": {
                "ruleset_version": ruleset_version,
                "rule_file": TIER_RULE_FILE,
                "rule_id": None,
                "license_text_anchor": None,
                "checked_on": None,
                "details_url": details_url,
            },
        }
        return entry, _missing_fields(False, in_snapshot)

    entry = {
        "spdx_id": atom,
        "tier": rule["tier"],
        "obligations": canonical_obligations(rule["obligations"]),
        "is_osi_approved": is_osi,
        "is_fsf_libre": is_fsf,
        "patent_clause": _clause(rule.get("patent_clause"), rule.get("checked_on")),
        "trademark_clause": _clause(rule.get("trademark_clause"), rule.get("checked_on")),
        "evidence": {
            "ruleset_version": ruleset_version,
            "rule_file": TIER_RULE_FILE,
            "rule_id": atom,
            "license_text_anchor": _copy_anchor(rule.get("anchor")),
            "checked_on": rule.get("checked_on"),
            "details_url": details_url,
        },
    }
    return entry, _missing_fields(True, in_snapshot)


def _is_disabled_entry(entry):
    """规则**本身**是否已失效（K10）：loader 会拒的条目不能用于判定。

    loader 的硬门是 ``verified is True`` + 锚点结构齐全 + ``checked_on``；
    画像再守一层，避免调用方拿未经 loader 过滤的规则表直接构造 :class:`Ruleset`。
    """
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


def _reasons_for_uncovered(atom, disabled, duplicated, extra=None):
    """未覆盖原因码；按字典序输出，保证同输入同产物。

    ``tier_uncovered`` 是基码（没有可用档位规则），其余码说明具体原因；
    引擎与真值生成器必须用同一套码，否则 M2 基准会红。
    """
    reasons = {"tier_uncovered"}
    reasons.update(extra or [])
    if atom in duplicated:
        reasons.add("rule_duplicated")
    if atom in disabled:
        reasons.add("rule_disabled")
    if atom.endswith("-unknown"):
        reasons.add("unknown_family")
    return sorted(reasons)


def evaluate_rule(atom, rule, disabled, duplicated):
    """档位判定：**只看规则表与 disabled 集合**，不接触 SPDX 快照。

    刻意不接收 ``SpdxIndex``：OSI/FSF 是展示字段（K9），FSF 不参与判定。
    返回 ``(usable, reasons)``；``usable=False`` 时 ``reasons`` 非空且含基码
    ``tier_uncovered``。
    """
    if atom in duplicated:
        # 同一 ID 有两条规则时，哪条都不采信：合并/挑一条都是猜测。
        return False, _reasons_for_uncovered(atom, disabled, duplicated)

    reason = None
    if rule is None:
        reason = "tier_uncovered"
    elif _is_disabled_entry(rule):
        reason = "rule_disabled"
    else:
        reason = _rule_problem(rule)
    if reason is None:
        return True, []
    # 基码由 _reasons_for_uncovered 负责；这里只补非基码的具体原因。
    extra = [reason] if reason != "tier_uncovered" else None
    return False, _reasons_for_uncovered(atom, disabled, duplicated, extra=extra)


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def profile_ids(spdx_ids, ruleset, index, license_list_version=None):
    """对一组 SPDX 原子 ID 产画像（核心；不读盘）。返回 profile.json 的字典形态。"""
    enabled, disabled, duplicated = _index_rules(ruleset)
    ruleset_version = ruleset.version

    profiles = []
    pending = []
    for atom in sorted(set(spdx_ids)):
        rule = enabled.get(atom)
        usable, reasons = evaluate_rule(atom, rule, disabled, duplicated)
        if not usable:
            # 规则不可用 = 没有规则：档位留空 + 待确认，绝不按「看起来像什么」猜。
            entry, missing = _profile_entry(atom, None, index, ruleset_version)
            profiles.append(entry)
            pending.append({"spdx_id": atom, "reasons": reasons, "missing": missing})
            continue

        entry, missing = _profile_entry(atom, rule, index, ruleset_version)
        profiles.append(entry)
        if missing:
            # 有规则但快照里没有该 ID（例如手写的 <族>-unknown 混进来）：
            # 档位仍按规则表给，但 OSI/FSF 无法回答 → 同样要人工确认。
            pending.append({
                "spdx_id": atom,
                "reasons": ["not_in_spdx_snapshot"],
                "missing": missing,
            })

    disabled_rules = []
    for item in ruleset.disabled:
        if not isinstance(item, dict):
            continue
        disabled_rules.append({
            "file": item.get("file"),
            "index": item.get("index"),
            "id": item.get("id"),
            "reasons": list(item.get("reasons") or []),
        })

    return {
        "format": contract.PROFILE_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "ruleset_version": ruleset_version,
        "license_list_version": license_list_version,
        "profiles": profiles,
        "pending_confirmation": pending,
        "disabled_rules": disabled_rules,
        "notes": [],
    }


def build_profile(inventory, ruleset, spdx_dir=None, index=None,
                  license_list_version=None):
    """``inventory.json`` → ``profile.json`` 字典形态。

    原子先按出现顺序收集，再按 ID 排序输出，保证同输入同产物。
    """
    if index is None:
        index, license_list_version = load_context(spdx_dir)
    atoms, notes = collect_atoms(inventory, index)
    payload = profile_ids(atoms, ruleset, index, license_list_version)
    payload["notes"] = [
        {
            "code": code,
            "spdx_id": spdx_id,
            "message": "表达式无法解析，整串作为单个原子保留，需人工确认",
        }
        for code, spdx_id in sorted(set(notes), key=lambda item: (item[0], item[1] or ""))
    ]
    return payload


__all__ = [
    "PROFILE_TOP_LEVEL_FIELDS",
    "TIER_RULE_FILE",
    "build_profile",
    "canonical_obligations",
    "collect_atoms",
    "evaluate_rule",
    "inventory_records",
    "load_context",
    "profile_ids",
    "split_atoms",
]
