# -*- coding: utf-8 -*-
"""M3 使用场景判定。

输入：``inventory.json`` + ``profile.json``（或由画像引擎现算）+ 用户给出的
场景 / 链接方式 / 网络交互回答 + 规则包 ``scenario-triggers.json``。
输出：``scenario.json`` —— 每条依赖一条记录，三态 ``triggered`` / ``not_triggered`` /
``pending_confirmation``。

判定纪律（plan/03 §3，K11–K14）：

- 八场景是唯一对外枚举；内部由 ``contract.SCENARIO_AXES`` 的 ``(delivery, link_mode)``
  双轴表达，引擎不另写一份映射。触发表按**交付形态场景**（``distribute-binary`` 等）
  匹配，链接方式作为第二维细化；链接方式轴场景（``static-link`` 等）必须同时给出交付形态。
- 触发只查规则表：``tier`` + ``scenarios`` + ``link_modes`` + ``network_interaction``
  四项全部满足才算命中；未命中任何条目 = ``not_triggered``（该场景不触发），
  不是「不适用」。
- 「商用」既不是输入项也不是触发条件（K12）。
- AGPL §13 是独立触发点：``network_interaction = true`` 时网络交互条目参与匹配，
  与是否分发无关（K13）。
- 未回答 / 组合非法 → ``pending_confirmation``，**不按最宽松默认**（K14）。
- 用户回答原样落盘（``answered_by`` + ``raw_answer``），引擎不代填。
- 多原子表达式在 M4 起**参与求值**（K16，决策 D32）：``OR`` 取最宽松、``AND`` 取最严格，
  由所选原子给出结论；求值过程写进 ``evidence.expression_evaluation``。无法求值
  （解析失败 / 参与求值的原子缺档位）→ ``pending_confirmation`` + ``expression_unresolved``。
- 引擎不复制档位 / 义务枚举，一律从 :mod:`licaudit.contract` 取。
"""

from .. import contract
from ..errors import UsageError
from ..inventory.spdx_expr import ExprError, parse_expression
from .conflict import evaluate_expression
from .profile import (
    canonical_obligations,
    inventory_records,
    split_atoms,
)

SCENARIO_RULE_FILE = "scenario-triggers.json"

SCENARIO_TOP_LEVEL_FIELDS = (
    "format",
    "format_version",
    "ruleset_version",
    "scenario",
    "delivery",
    "link_mode",
    "delivery_scenario",
    "network_interaction",
    "answered_by",
    "raw_answer",
    "outbound_license",
    "entries",
    "pending_confirmation",
    "notes",
)

# 交付形态 → 交付形态场景（触发表的第一维）。
_DELIVERY_SCENARIO = {
    "internal": "internal",
    "binary": "distribute-binary",
    "source": "distribute-source",
    "saas": "saas",
    "container": "container-image",
}

# 链接方式轴场景 → 链接方式；这些场景必须由用户再给出交付形态。
_LINK_SCENARIOS = {
    "static-link": "static",
    "dynamic-link": "dynamic",
    "separate-process": "separate-process",
}

# 必须回答网络交互的场景（plan/03 §3.1）；``container-image`` 可选，其余不问。
_NETWORK_REQUIRED = ("saas",)
# 网络交互「可选」的场景：没回答时，凡是有网络触发条目的档位一律待确认，不取宽松默认。
_NETWORK_OPTIONAL = ("container-image",)

# 原因 / 注记码（写进产物，便于报告层原样展示）。
REASON_TIER_UNAVAILABLE = "tier_unavailable"
REASON_NETWORK_UNANSWERED = "network_interaction_unanswered"
REASON_NETWORK_CONTRADICTION = "network_interaction_contradicts_scenario"
REASON_DELIVERY_UNANSWERED = "delivery_unanswered"
REASON_EXPRESSION_UNRESOLVED = "expression_unresolved"
REASON_SPDX_MISSING = "spdx_id_missing"

NOTE_RAW_ANSWER_MISSING = "raw_answer_missing"
NOTE_OUTBOUND_PENDING = "outbound_pending"


# ---------------------------------------------------------------------------
# 场景轴解析
# ---------------------------------------------------------------------------


def delivery_scenario(delivery):
    """交付形态 → 触发表第一维场景 ID；未知交付形态返回 ``None``。"""
    return _DELIVERY_SCENARIO.get(delivery)


def resolve_axes(scenario=None, delivery=None, linking=None):
    """解析用户给的两套等价写法，返回 ``(scenario, delivery, link_mode)``。

    ``--scenario`` 与 ``--delivery`` + ``--linking`` 等价；两者同时给出且矛盾 →
    :class:`UsageError`（exit 2）。缺场景 → 同样是用法错误，**不默认 internal**。
    链接方式轴场景未给交付形态时 ``delivery`` 返回 ``None``：这是「回答不完整」，
    调用方据此输出 ``pending_confirmation``，而不是猜一个交付形态。
    """
    if linking is not None and linking not in contract.LINK_MODES:
        raise UsageError(
            "链接方式非法", linking=linking, allowed=", ".join(contract.LINK_MODES)
        )
    if delivery is not None and delivery not in contract.DELIVERIES:
        raise UsageError(
            "交付形态非法", delivery=delivery, allowed=", ".join(contract.DELIVERIES)
        )

    if scenario is None:
        if delivery is None:
            raise UsageError(
                "缺少使用场景",
                hint="用 --scenario 指定八场景之一，或用 --delivery + --linking 等价表达",
            )
        link_mode = linking or "none"
        for candidate in contract.SCENARIO_IDS:
            axes = contract.SCENARIO_AXES[candidate]
            if axes.get("delivery") == delivery and axes.get("link_mode") == link_mode:
                return candidate, delivery, link_mode
        # 组合不在八场景表内（如 binary + separate-process 只有 separate-process 一解）。
        if link_mode in _LINK_SCENARIOS.values():
            return _scenario_id_for_link(link_mode), delivery, link_mode
        raise UsageError(
            "交付形态与链接方式的组合不构成八场景之一",
            delivery=delivery,
            linking=link_mode,
        )

    if scenario not in contract.SCENARIO_IDS:
        raise UsageError(
            "未知的场景 ID", scenario=scenario, allowed=", ".join(contract.SCENARIO_IDS)
        )

    axes = contract.SCENARIO_AXES[scenario]
    base_delivery = axes.get("delivery")
    base_link = axes.get("link_mode")

    if delivery is not None and base_delivery is not None and delivery != base_delivery:
        raise UsageError(
            "场景与交付形态矛盾",
            scenario=scenario,
            scenario_delivery=base_delivery,
            delivery=delivery,
        )
    if linking is not None and base_link not in (None, "none") and linking != base_link:
        raise UsageError(
            "场景与链接方式矛盾",
            scenario=scenario,
            scenario_link_mode=base_link,
            linking=linking,
        )

    resolved_delivery = delivery if delivery is not None else base_delivery
    resolved_link = linking if linking is not None else base_link
    return scenario, resolved_delivery, resolved_link


def _scenario_id_for_link(link_mode):
    for scenario, value in _LINK_SCENARIOS.items():
        if value == link_mode:
            return scenario
    raise UsageError("内部错误：无法从链接方式反查场景", link_mode=link_mode)


# ---------------------------------------------------------------------------
# 规则表
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


def usable_entries(entries):
    """过滤出可参与判定的条目（第二道门，不依赖调用方是否经过 loader）。"""
    usable = []
    for entry in entries or []:
        if not isinstance(entry, dict):
            continue
        if _is_disabled_entry(entry):
            continue
        if entry.get("tier") not in contract.TIERS:
            continue
        scenarios = entry.get("scenarios")
        link_modes = entry.get("link_modes")
        if not isinstance(scenarios, list) or not scenarios:
            continue
        if not isinstance(link_modes, list) or not link_modes:
            continue
        if any(item not in contract.SCENARIO_IDS for item in scenarios):
            continue
        if any(item not in contract.LINK_MODES for item in link_modes):
            continue
        if not isinstance(entry.get("trigger"), str) or not entry["trigger"].strip():
            continue
        obligations = entry.get("obligations")
        if not isinstance(obligations, list):
            continue
        if any(item not in contract.OBLIGATIONS for item in obligations):
            continue
        if "network_interaction" in entry and not isinstance(
            entry.get("network_interaction"), bool
        ):
            continue
        usable.append(entry)
    return usable


def entry_matches(entry, tier, scenario, link_mode, network_interaction):
    """单条规则是否命中。纯查表，不含任何档位特判（K4）。"""
    if entry.get("tier") != tier:
        return False
    if scenario not in (entry.get("scenarios") or []):
        return False
    if link_mode not in (entry.get("link_modes") or []):
        return False
    if "network_interaction" in entry:
        # 条目声明了网络交互前提 → 用户回答必须明确为 true。
        return entry.get("network_interaction") is True and network_interaction is True
    return True


def has_network_candidate(tier, scenario, link_mode, entries):
    """该档位是否存在「声明了网络交互前提」的候选条目（忽略网络回答本身）。"""
    for entry in usable_entries(entries):
        if entry.get("network_interaction") is not True:
            continue
        if entry.get("tier") != tier:
            continue
        if scenario not in (entry.get("scenarios") or []):
            continue
        if link_mode not in (entry.get("link_modes") or []):
            continue
        return True
    return False


def evaluate_tier(tier, scenario, link_mode, network_interaction, entries,
                  network_optional=False):
    """单个档位在给定场景下的判定（纯查表，不读盘、不读时钟）。

    返回 ``verdict`` / ``triggers`` / ``rule_ids`` / ``obligations`` / ``reasons``。
    ``tier`` 为 ``None``（无画像）→ ``pending_confirmation``，**不猜档位**。
    ``network_optional`` 为真且网络回答缺失、而该档位确有网络候选条目时，
    结论降为 ``pending_confirmation``（K14：不按最宽松默认），但仍保留已命中的
    非网络触发项，便于报告层展示已知部分。
    """
    if tier is None:
        return {
            "verdict": contract.PENDING,
            "triggers": [],
            "rule_ids": [],
            "obligations": [],
            "reasons": [REASON_TIER_UNAVAILABLE],
        }

    hits = [
        entry for entry in usable_entries(entries)
        if entry_matches(entry, tier, scenario, link_mode, network_interaction)
    ]
    reasons = []
    verdict = "triggered" if hits else "not_triggered"
    if (
        network_optional
        and network_interaction is None
        and has_network_candidate(tier, scenario, link_mode, entries)
    ):
        verdict = contract.PENDING
        reasons.append(REASON_NETWORK_UNANSWERED)

    triggers = set()
    rule_ids = set()
    obligations = []
    for entry in hits:
        triggers.add(entry["trigger"])
        if entry.get("id"):
            rule_ids.add(entry["id"])
        obligations.extend(entry.get("obligations") or [])
    return {
        "verdict": verdict,
        "triggers": sorted(triggers),
        "rule_ids": sorted(rule_ids),
        "obligations": canonical_obligations(obligations),
        "reasons": reasons,
    }


# ---------------------------------------------------------------------------
# 包级汇总
# ---------------------------------------------------------------------------


def tier_index(profile_payload):
    index = {}
    for item in profile_payload.get("profiles") or []:
        if isinstance(item, dict) and item.get("spdx_id"):
            index[item["spdx_id"]] = item.get("tier")
    return index


def _choose_atom(atoms, atom_results, spdx_id, tiers, spdx_index):
    """多原子表达式的结论：先求值选原子，再定结论（K16 / D32）。

    顺序很重要：求值失败（有原子未覆盖）→ ``expression_unresolved``；
    求值成功但**任一**原子的结论本身待确认（未回答/矛盾）→ 整体仍待确认，
    否则会按选中分支把「不知道」说成「不触发」。返回
    ``(verdict, chosen, extra_reasons, evaluation)``；``chosen`` 为 ``None`` 时保留
    其它原子已命中的触发项，便于报告层展示已知部分。
    """
    evaluation = None
    if len(atoms) > 1:
        evaluation = evaluate_expression(spdx_id, tiers, spdx_index)
        if not evaluation["resolved"]:
            return contract.PENDING, None, [REASON_EXPRESSION_UNRESOLVED], evaluation
    if any(item["verdict"] == contract.PENDING for item in atom_results):
        return contract.PENDING, None, [], evaluation
    if len(atoms) == 1:
        return atom_results[0]["verdict"], 0, [], evaluation
    for position, item in enumerate(atom_results):
        if item["spdx_id"] == evaluation["selected"]:
            return item["verdict"], position, [], evaluation
    return contract.PENDING, None, [REASON_EXPRESSION_UNRESOLVED], evaluation


def _package_entry(record, spdx_index, tiers, scenario, link_mode,
                   network_interaction, entries, answered_by, raw_answer,
                   network_optional=False):
    spdx_id = record.get("spdx_id")
    atoms, _note = split_atoms(spdx_id, spdx_index)

    atom_results = []
    for atom in atoms:
        result = evaluate_tier(
            tiers.get(atom), scenario, link_mode, network_interaction, entries,
            network_optional=network_optional,
        )
        atom_results.append({
            "spdx_id": atom,
            "tier": tiers.get(atom),
            "verdict": result["verdict"],
            "triggers": result["triggers"],
            "rule_ids": result["rule_ids"],
            "obligations": result["obligations"],
            "reasons": result["reasons"],
        })

    reasons = set()
    evaluation = None
    chosen = None
    if not atoms:
        reasons.add(REASON_SPDX_MISSING)
        verdict = contract.PENDING
    else:
        verdict, chosen, extra, evaluation = _choose_atom(
            atoms, atom_results, spdx_id, tiers, spdx_index
        )
        reasons.update(extra)
    for item in atom_results:
        reasons.update(item["reasons"])

    triggers = set()
    rule_ids = set()
    obligations = []
    # 表达式求值选出原子后，义务/触发只取该原子：OR 的分支不该把未选中分支的义务算进来。
    chosen_results = (
        [atom_results[chosen]] if chosen is not None else atom_results
    )
    for item in chosen_results:
        triggers.update(item["triggers"])
        rule_ids.update(item["rule_ids"])
        obligations.extend(item["obligations"])

    entry = {
        "package": record.get("package"),
        "scenario": scenario,
        "link_mode": link_mode,
        "triggers": sorted(triggers),
        "verdict": verdict,
        "evidence": {
            "rule_ids": sorted(rule_ids),
            "atoms": atom_results,
            "obligations": canonical_obligations(obligations),
            "spdx_id": spdx_id,
            "expression_evaluation": evaluation,
            "user_answer": raw_answer,
            "answered_by": answered_by,
        },
    }
    return entry, sorted(reasons)


def build_scenario(inventory, profile_payload, ruleset, scenario, delivery, link_mode,
                   network_interaction, answered_by, raw_answer,
                   outbound_license=None, spdx_index=None):
    """产 ``scenario.json`` 字典形态（核心；不读盘、不写盘）。

    ``scenario`` / ``delivery`` / ``link_mode`` 由 :func:`resolve_axes` 得出；
    ``network_interaction`` 为 ``True`` / ``False`` / ``None``（未回答）。
    """
    if spdx_index is None:
        from .profile import load_context

        spdx_index, _version = load_context()

    entries = usable_entries(
        ruleset.entries(SCENARIO_RULE_FILE) if ruleset is not None else []
    )
    tiers = tier_index(profile_payload)

    # 运行级待确认：交付形态没回答（链接方式轴场景缺 delivery）或必答项缺失/矛盾（K14）。
    match_scenario = delivery_scenario(delivery)
    run_pending = []
    if match_scenario is None:
        run_pending.append(REASON_DELIVERY_UNANSWERED)
    if match_scenario in _NETWORK_REQUIRED:
        if network_interaction is None:
            run_pending.append(REASON_NETWORK_UNANSWERED)
        elif network_interaction is False:
            # SaaS 本身就是「通过网络向用户提供服务」；回答「无网络交互」是矛盾。
            run_pending.append(REASON_NETWORK_CONTRADICTION)
    network_optional = match_scenario in _NETWORK_OPTIONAL

    scenario_entries = []
    pending = []
    for record in inventory_records(inventory):
        if run_pending:
            entry = {
                "package": record.get("package"),
                "scenario": scenario,
                "link_mode": link_mode,
                "triggers": [],
                "verdict": contract.PENDING,
                "evidence": {
                    "rule_ids": [],
                    "atoms": [],
                    "obligations": [],
                    "spdx_id": record.get("spdx_id"),
                    "expression_evaluation": None,
                    "user_answer": raw_answer,
                    "answered_by": answered_by,
                },
            }
            reasons = list(run_pending)
        else:
            entry, reasons = _package_entry(
                record, spdx_index, tiers, match_scenario, link_mode,
                network_interaction, entries, answered_by, raw_answer,
                network_optional=network_optional,
            )
        scenario_entries.append(entry)
        if entry["verdict"] == contract.PENDING:
            pending.append({
                "package": entry["package"],
                "spdx_id": record.get("spdx_id"),
                "reasons": reasons,
            })

    notes = []
    if not raw_answer:
        notes.append({
            "code": NOTE_RAW_ANSWER_MISSING,
            "message": "未记录用户原始回答；判定只依据命令行显式给出的场景与选项",
        })
    if (outbound_license or "").strip() == "pending":
        notes.append({
            "code": NOTE_OUTBOUND_PENDING,
            "message": "项目自身 outbound 许可证待定；兼容性判定（conflicts.json）将全部输出待定",
        })

    return {
        "format": contract.SCENARIO_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "ruleset_version": ruleset.version if ruleset is not None else None,
        "scenario": scenario,
        "delivery": delivery,
        "link_mode": link_mode,
        "delivery_scenario": match_scenario,
        "network_interaction": network_interaction,
        "answered_by": answered_by,
        "raw_answer": raw_answer,
        "outbound_license": outbound_license,
        "entries": scenario_entries,
        "pending_confirmation": pending,
        "notes": notes,
    }


# ---------------------------------------------------------------------------
# 输入校验
# ---------------------------------------------------------------------------


def validate_outbound(value, spdx_index):
    """``pending`` 显式表示未决定；其它值必须是 SPDX 表达式且原子都在快照里。

    返回规范化后的字符串。未知 ID / 解析失败 → ``UsageError``（exit 2）。
    """
    if value is None:
        raise UsageError(
            "缺少项目 outbound 许可证",
            hint="用 --outbound-license 指定 SPDX 表达式；尚未决定时写 pending",
        )
    text = value.strip()
    if not text:
        raise UsageError("outbound 许可证为空", hint="写 pending 表示尚未决定")
    if text == "pending":
        return text
    try:
        parsed = parse_expression(text, spdx_index)
    except ExprError as exc:
        raise UsageError("outbound 不是合法的 SPDX 表达式", value=value, reason=str(exc))
    unknown = [atom for atom in parsed.atoms if not spdx_index.has_license(atom)]
    if unknown:
        raise UsageError(
            "outbound 含未知许可证 ID",
            unknown=", ".join(sorted(unknown)),
            hint="请给出 SPDX 快照中的明确 ID；族名不会被推断",
        )
    return parsed.text


__all__ = [
    "REASON_DELIVERY_UNANSWERED",
    "REASON_EXPRESSION_UNRESOLVED",
    "REASON_NETWORK_UNANSWERED",
    "REASON_SPDX_MISSING",
    "REASON_TIER_UNAVAILABLE",
    "SCENARIO_RULE_FILE",
    "SCENARIO_TOP_LEVEL_FIELDS",
    "build_scenario",
    "delivery_scenario",
    "entry_matches",
    "evaluate_tier",
    "inventory_records",
    "resolve_axes",
    "tier_index",
    "usable_entries",
    "validate_outbound",
]
