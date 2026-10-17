# -*- coding: utf-8 -*-
"""可证伪自检。

设计要点：**每一项 check 都能被弄坏**（改成返回恒真就没有意义）。
``--core`` 只验纯内部不变量；完整自检额外要求规则包真的能加载 ——
把 ``LICAUDIT_RULES_DIR`` 指向空目录时，完整自检必须失败（exit 1），
这就是它「可证伪」的证据，也锁在测试里。
"""

import os

from . import contract
from .errors import RulesetError
from .ruleset import load_ruleset

CORE_CHECK_IDS = (
    "exit_codes",
    "contract_fields",
    "contract_unique",
    "scenario_axes",
    "tier_rank",
    "enums_disjoint",
)


def _check_exit_codes():
    from .exit_codes import EXIT_CODES, EXIT_FINDINGS, EXIT_OK, EXIT_RULESET, EXIT_USAGE

    expected = {0, 1, 2, 3}
    actual = {EXIT_OK, EXIT_FINDINGS, EXIT_USAGE, EXIT_RULESET}
    return actual == expected and set(EXIT_CODES) == expected


def _check_contract_fields():
    groups = {
        "inventory": contract.INVENTORY_RECORD_FIELDS,
        "profile": contract.PROFILE_FIELDS,
        "scenario": contract.SCENARIO_FIELDS,
        "conflict": contract.CONFLICT_FIELDS,
        "action": contract.ACTION_FIELDS,
    }
    for name, fields in groups.items():
        if not fields:
            return False
        if any(not isinstance(field, str) or not field for field in fields):
            return False
    if not contract.REPORT_SECTIONS:
        return False
    return contract.REPORT_SECTIONS[-1] == "免责声明"


def _check_contract_unique():
    groups = [
        contract.INVENTORY_RECORD_FIELDS,
        contract.PROFILE_FIELDS,
        contract.SCENARIO_FIELDS,
        contract.CONFLICT_FIELDS,
        contract.ACTION_FIELDS,
        contract.REPORT_SECTIONS,
        contract.REPORT_CSV_COLUMNS,
    ]
    for fields in groups:
        if len(fields) != len(set(fields)):
            return False
    # 四级可信度链必须严格四级，且顺序即优先级
    return contract.CONFIDENCE_LEVELS == (
        "license_expression",
        "trove_classifier",
        "license_first_line",
        "truncated_fallback",
    )


def _check_scenario_axes():
    if set(contract.SCENARIO_AXES) != set(contract.SCENARIO_IDS):
        return False
    for scenario, axes in contract.SCENARIO_AXES.items():
        link_mode = axes.get("link_mode")
        delivery = axes.get("delivery")
        if link_mode not in contract.LINK_MODES:
            return False
        if delivery is not None and delivery not in (
            "internal",
            "binary",
            "source",
            "saas",
            "container",
        ):
            return False
    return True


def _check_tier_rank():
    if set(contract.TIER_RANK) != set(contract.TIERS):
        return False
    values = [contract.TIER_RANK[tier] for tier in contract.TIERS]
    return values == sorted(values) and len(set(values)) == len(values)


def _check_enums_disjoint():
    # 处置级别与冲突结论是两套枚举，不得互相包含
    if set(contract.ACTION_LEVELS) & set(contract.CONFLICT_RESOLUTIONS):
        return False
    # 阻断级别必须是处置级别的子集
    return set(contract.BLOCKING_ACTION_LEVELS) <= set(contract.ACTION_LEVELS)


_CHECK_FUNCTIONS = {
    "exit_codes": _check_exit_codes,
    "contract_fields": _check_contract_fields,
    "contract_unique": _check_contract_unique,
    "scenario_axes": _check_scenario_axes,
    "tier_rank": _check_tier_rank,
    "enums_disjoint": _check_enums_disjoint,
}


def run_selftest(core_only=False, rules_dir=None):
    """返回 ``(checks, ok)``；``checks`` 是 ``{id, ok, detail}`` 列表。"""
    checks = []
    for check_id in CORE_CHECK_IDS:
        try:
            passed = bool(_CHECK_FUNCTIONS[check_id]())
            detail = "" if passed else "invariant violated"
        except Exception as exc:  # 自检本身不能因某项崩溃而整体崩
            passed = False
            detail = "{0}: {1}".format(type(exc).__name__, exc)
        checks.append({"id": check_id, "ok": passed, "detail": detail})

    if not core_only:
        try:
            ruleset = load_ruleset(explicit=rules_dir, verify_hashes=True)
            checks.append(
                {
                    "id": "ruleset_loadable",
                    "ok": True,
                    "detail": "ruleset={0} ids={1} disabled={2}".format(
                        ruleset.version,
                        ruleset.license_list_version,
                        len(ruleset.disabled),
                    ),
                }
            )
        except RulesetError as exc:
            checks.append(
                {
                    "id": "ruleset_loadable",
                    "ok": False,
                    "detail": str(exc),
                }
            )

    ok = all(item["ok"] for item in checks)
    return checks, ok


def format_checks(checks):
    lines = []
    for item in checks:
        mark = "OK" if item["ok"] else "FAIL"
        if item["detail"]:
            lines.append("[{0}] {1} — {2}".format(mark, item["id"], item["detail"]))
        else:
            lines.append("[{0}] {1}".format(mark, item["id"]))
    return "\n".join(lines)


def default_rules_hint():
    return os.path.join("references", "ruleset")


__all__ = [
    "CORE_CHECK_IDS",
    "default_rules_hint",
    "format_checks",
    "run_selftest",
]
