# -*- coding: utf-8 -*-
"""编排层：串步骤、合并退出码、落中间产物。

本模块**零判定**：只负责调用、写盘与退出码合并，不重新判定任何结论。
当前行为：
  - ``status`` 只加载规则包并报告其摘要；规则包缺失 → ``RulesetError`` → exit 3
  - ``scan`` / ``verify-data`` / ``bench`` 先过规则包硬门，再跑各自引擎
  - ``assess --profile-only``（M2）只产 ``profile.json``；有待确认项 → exit 1
  - ``assess`` 全量模式（M3–M5）产 ``profile.json`` + ``scenario.json`` + ``conflicts.json``
    + ``actions.json``；``--scenario`` 与 ``--outbound-license`` 必填；有阻断级/待确认项 → exit 1
  - ``report``（M5）读上述产物渲染 ``license-report.md`` / ``license-report.csv``
  - **不产出任何占位产物**，也不返回 exit 0 假装成功
"""

import os
import sys

from . import __version__, contract
from .assess.action import build_actions, has_blocking_action
from .assess.conflict import build_conflicts, has_blocking_finding
from .assess.profile import build_profile, load_context
from .assess.scenario import build_scenario, resolve_axes, validate_outbound
from .exit_codes import EXIT_FINDINGS, EXIT_OK
from .inventory.build import build_inventory, inventory_path
from .report import REPORT_FILES
from .report.csv_render import render_artifacts as render_csv_artifacts
from .report.markdown import render_artifacts as render_markdown_artifacts
from .report.sections import build_report, has_blocking_levels
from .ruleset import load_ruleset
from .serialize import load_artifact, write_json, write_text_atomic
from .verify import (
    format_bench_report,
    format_verify_report,
    run_bench as run_bench_suites,
    verify_data,
)

DEFAULT_OUT_DIR = "out"
PROFILE_ARTIFACT = "profile.json"
SCENARIO_ARTIFACT = "scenario.json"
CONFLICT_ARTIFACT = "conflicts.json"
ACTION_ARTIFACT = "actions.json"


def _ensure_out_dir(out_dir):
    target = os.path.abspath(out_dir or DEFAULT_OUT_DIR)
    if not os.path.isdir(target):
        os.makedirs(target)
    return target


def run_status(args):
    ruleset = load_ruleset(explicit=getattr(args, "rules_dir", None),
                           verify_hashes=True)
    summary = ruleset.summary()
    summary["package_version"] = __version__
    summary["rules_dir"] = ruleset.root
    return summary, 0


def run_scan(args):
    # 先过规则包硬门：缺规则包必须是 exit 3，而不是「没有依赖、零风险」的 exit 0。
    ruleset = load_ruleset(explicit=getattr(args, "rules_dir", None), verify_hashes=True)
    payload = build_inventory(args.manifests, ruleset)
    target = _ensure_out_dir(args.out_dir)
    path = inventory_path(target)
    write_json(path, payload)
    _print_scan_summary(payload, path)
    return payload, 0


def _print_scan_summary(payload, path):
    dependencies = payload.get("dependencies", [])
    pending = payload.get("pending_confirmation", [])
    notes = payload.get("parse_notes", [])
    resolvable = [item for item in dependencies if item.get("spdx_id")]
    sys.stdout.write(
        "依赖 {0} 条；已归一化 {1} 条；待人工确认 {2} 条；解析注记 {3} 条\n".format(
            len(dependencies), len(resolvable), len(pending), len(notes)
        )
    )
    sys.stdout.write("产物: {0}\n".format(path))


def run_assess(args):
    # 先过规则包硬门：缺规则包必须是 exit 3（D15/K24），与阶段是否实现无关。
    ruleset = load_ruleset(explicit=getattr(args, "rules_dir", None), verify_hashes=True)
    if getattr(args, "profile_only", False):
        return _run_profile_only(args, ruleset)
    return _run_full_assess(args, ruleset)


def _load_profile_context(args, ruleset):
    inventory = load_artifact(args.inventory, (contract.INVENTORY_FORMAT,))
    index, license_list_version = load_context(getattr(args, "spdx_dir", None))
    payload = build_profile(
        inventory,
        ruleset,
        index=index,
        license_list_version=license_list_version,
    )
    return inventory, index, payload


def _run_profile_only(args, ruleset):
    _inventory, _index, payload = _load_profile_context(args, ruleset)
    target = _ensure_out_dir(args.out_dir)
    path = os.path.join(target, PROFILE_ARTIFACT)
    write_json(path, payload)
    _print_profile_summary(payload, path)
    # plan/03 §六：未覆盖 ID / 被拒规则命中的条目都要「输出待确认」，退出码 1。
    # 这不是故障，而是「分析完成，但有需要人工确认的条目」。
    return payload, (EXIT_FINDINGS if payload.get("pending_confirmation") else EXIT_OK)


def _run_full_assess(args, ruleset):
    scenario = getattr(args, "scenario", None)
    delivery = getattr(args, "delivery", None)
    linking = getattr(args, "linking", None)
    # 场景与 outbound 是全量模式的必填项（HANDOFF-M3 §二.1）；缺任一项 → exit 2。
    resolved_scenario, resolved_delivery, resolved_link = resolve_axes(
        scenario, delivery, linking
    )

    inventory, index, profile_payload = _load_profile_context(args, ruleset)
    outbound = validate_outbound(getattr(args, "outbound_license", None), index)

    network = getattr(args, "network_interaction", None)
    if network is not None:
        network = network == "yes"

    scenario_payload = build_scenario(
        inventory,
        profile_payload,
        ruleset,
        resolved_scenario,
        resolved_delivery,
        resolved_link,
        network,
        answered_by="user",
        raw_answer=getattr(args, "scenario_note", "") or "",
        outbound_license=outbound,
        spdx_index=index,
    )

    target = _ensure_out_dir(args.out_dir)
    profile_path = os.path.join(target, PROFILE_ARTIFACT)
    scenario_path = os.path.join(target, SCENARIO_ARTIFACT)
    conflict_path = os.path.join(target, CONFLICT_ARTIFACT)
    action_path = os.path.join(target, ACTION_ARTIFACT)
    write_json(profile_path, profile_payload)
    write_json(scenario_path, scenario_payload)
    _print_profile_summary(profile_payload, profile_path)
    _print_scenario_summary(scenario_payload, scenario_path)

    conflict_payload = build_conflicts(
        inventory,
        profile_payload,
        ruleset,
        outbound,
        scenario=resolved_scenario,
        delivery=resolved_delivery,
        link_mode=resolved_link,
        spdx_index=index,
    )
    write_json(conflict_path, conflict_payload)
    _print_conflict_summary(conflict_payload, conflict_path)

    # M5：处置分级只查 action-rules.json 决策表，输入是上面三份产物（D35）。
    action_payload = build_actions(
        inventory, profile_payload, scenario_payload, conflict_payload, ruleset
    )
    write_json(action_path, action_payload)
    _print_action_summary(action_payload, action_path)

    pending = (
        bool(profile_payload.get("pending_confirmation"))
        or bool(scenario_payload.get("pending_confirmation"))
        or has_blocking_finding(conflict_payload)
        or has_blocking_action(action_payload)
    )
    return action_payload, (EXIT_FINDINGS if pending else EXIT_OK)


def _print_action_summary(payload, path):
    actions = payload.get("actions") or []
    counts = {}
    for level in contract.ACTION_LEVELS:
        counts[level] = len(
            [item for item in actions if item.get("level") == level]
        )
    pending = payload.get("pending_confirmation") or []
    blocking = len([
        item for item in actions
        if item.get("level") in contract.BLOCKING_ACTION_LEVELS
    ])
    sys.stdout.write(
        "处置：条目 {0} 条；阻断/隔离级 {1} 条（ok {2} / declare {3} / isolate {4} / "
        "replace_or_license {5}）；待人工确认 {6} 条\n".format(
            len(actions),
            blocking,
            counts.get("ok"),
            counts.get("declare"),
            counts.get("isolate"),
            counts.get("replace_or_license"),
            len(pending),
        )
    )
    if pending:
        sys.stdout.write(
            "待确认（五锚点缺项 / 输入未定）: {0}\n".format(
                ", ".join(item.get("package") or "?" for item in pending)
            )
        )
    sys.stdout.write("产物: {0}\n".format(path))


def _print_profile_summary(payload, path):
    profiles = payload.get("profiles") or []
    with_tier = [item for item in profiles if item.get("tier")]
    pending = payload.get("pending_confirmation") or []
    sys.stdout.write(
        "原子画像 {0} 条；有档位 {1} 条；待人工确认 {2} 条；被拒绝规则 {3} 条\n".format(
            len(profiles),
            len(with_tier),
            len(pending),
            len(payload.get("disabled_rules") or []),
        )
    )
    if pending:
        sys.stdout.write(
            "待确认（不猜档位）: {0}\n".format(
                ", ".join(item.get("spdx_id") or "?" for item in pending)
            )
        )
    sys.stdout.write("产物: {0}\n".format(path))


def _print_scenario_summary(payload, path):
    entries = payload.get("entries") or []
    triggered = [item for item in entries if item.get("verdict") == "triggered"]
    not_triggered = [item for item in entries if item.get("verdict") == "not_triggered"]
    pending = payload.get("pending_confirmation") or []
    sys.stdout.write(
        "场景 {0}（交付 {1} / 链接 {2}）：依赖 {3} 条；触发 {4} 条；不触发 {5} 条；待确认 {6} 条\n".format(
            payload.get("scenario"),
            payload.get("delivery"),
            payload.get("link_mode"),
            len(entries),
            len(triggered),
            len(not_triggered),
            len(pending),
        )
    )
    if pending:
        sys.stdout.write(
            "待确认（不猜判定）: {0}\n".format(
                ", ".join(item.get("package") or "?" for item in pending)
            )
        )
    sys.stdout.write("产物: {0}\n".format(path))


def _print_conflict_summary(payload, path):
    pairs = payload.get("dependency_conflicts") or []
    outbound = payload.get("outbound_conflicts") or []
    pending = payload.get("pending_confirmation") or []
    blocking = [item for item in pairs + outbound
                if item.get("resolution") in ("pending", "incompatible")]
    sys.stdout.write(
        "冲突：outbound={0}（档位 {1}）；依赖间 {2} 条；依赖×outbound {3} 条；"
        "待定/不兼容 {4} 条；未登记组合 {5} 对\n".format(
            payload.get("outbound_license"),
            payload.get("outbound_tier"),
            len(pairs),
            len(outbound),
            len(blocking),
            (payload.get("uncovered_pairs") or {}).get("count"),
        )
    )
    if pending:
        sys.stdout.write(
            "待确认（不猜兼容性）: {0}\n".format(
                ", ".join(item.get("pair_id") or "?" for item in pending)
            )
        )
    sys.stdout.write("产物: {0}\n".format(path))


REPORT_ARTIFACTS = (
    (PROFILE_ARTIFACT, (contract.PROFILE_FORMAT,), "profile"),
    (SCENARIO_ARTIFACT, (contract.SCENARIO_FORMAT,), "scenario"),
    (CONFLICT_ARTIFACT, (contract.CONFLICT_FORMAT,), "conflicts"),
    (ACTION_ARTIFACT, (contract.ACTION_FORMAT,), "actions"),
)


def load_report_artifacts(out_dir):
    """读 ``assess`` 的四份产物（``report`` 的输入；不重算任何判定）。"""
    artifacts = {}
    for filename, formats, key in REPORT_ARTIFACTS:
        artifacts[key] = load_artifact(os.path.join(out_dir, filename), formats)
    return artifacts


def run_report(args):
    # 先过规则包硬门：缺规则包必须是 exit 3，而不是「渲染一份空报告」。
    load_ruleset(explicit=getattr(args, "rules_dir", None), verify_hashes=True)
    target = _ensure_out_dir(args.out_dir)
    artifacts = load_report_artifacts(target)
    report = build_report(artifacts)
    fmt = getattr(args, "format", "md") or "md"
    if fmt == "csv":
        text = render_csv_artifacts(artifacts)
    else:
        text = render_markdown_artifacts(artifacts)
    path = os.path.join(target, REPORT_FILES[fmt])
    write_text_atomic(path, text)
    _print_report_summary(report, fmt, path)
    # plan/03 §5.5：存在阻断级 → 1；只有 declare/ok → 0；待确认项要被 CI 看见 → 1。
    blocked = has_blocking_levels(report) or bool(report["pending"])
    return report, (EXIT_FINDINGS if blocked else EXIT_OK)


def _print_report_summary(report, fmt, path):
    sys.stdout.write(
        "报告：格式 {0}；章节 {1} 个；逐包明细 {2} 行；待人工确认 {3} 条\n".format(
            fmt, len(report["sections"]), len(report["rows"]), len(report["pending"])
        )
    )
    titles = "、".join(section["title"] for section in report["sections"])
    sys.stdout.write("章节顺序: {0}\n".format(titles))
    sys.stdout.write("产物: {0}\n".format(path))


def run_verify_data(args):
    """读取冻结真值并用运行时解析器复算（M1）。"""
    ruleset = load_ruleset(explicit=getattr(args, "rules_dir", None), verify_hashes=True)
    data_dir = os.path.abspath(getattr(args, "data_dir", "data"))
    report, code = verify_data(data_dir, ruleset)
    sys.stdout.write(format_verify_report(report) + "\n")
    return report, code


def run_bench(args):
    ruleset = load_ruleset(explicit=getattr(args, "rules_dir", None), verify_hashes=True)
    data_dir = os.path.abspath(getattr(args, "data_dir", "data"))
    report, code = run_bench_suites(
        getattr(args, "only", None), ruleset, data_dir
    )
    sys.stdout.write(format_bench_report(report) + "\n")
    return report, code


def write_status_artifact(summary, out_dir):
    """把 status 摘要落盘，便于单步复查（K29）。"""
    target = _ensure_out_dir(out_dir)
    payload = {
        "format": "licaudit-status",
        "format_version": contract.FORMAT_VERSION,
        "package_version": summary.get("package_version"),
        "ruleset_version": summary.get("ruleset_version"),
        "license_list_version": summary.get("license_list_version"),
        "enabled": summary.get("enabled", {}),
        "disabled": summary.get("disabled", 0),
    }
    path = os.path.join(target, "status.json")
    write_json(path, payload)
    return path


__all__ = [
    "ACTION_ARTIFACT",
    "CONFLICT_ARTIFACT",
    "DEFAULT_OUT_DIR",
    "PROFILE_ARTIFACT",
    "SCENARIO_ARTIFACT",
    "load_report_artifacts",
    "run_assess",
    "run_bench",
    "run_report",
    "run_scan",
    "run_status",
    "run_verify_data",
    "write_status_artifact",
]
