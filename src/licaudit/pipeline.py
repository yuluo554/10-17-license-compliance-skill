# -*- coding: utf-8 -*-
"""编排层：串步骤、合并退出码、落中间产物。

本模块**零判定**：只负责调用、写盘与退出码合并，不重新判定任何结论。
骨架阶段的行为：
  - ``status`` 只加载规则包并报告其摘要；规则包缺失 → ``RulesetError`` → exit 3
  - ``scan`` / ``assess`` / ``report`` 同样先过规则包硬门，再明确告知「该阶段未实现」
  - **不产出任何占位产物**，也不返回 exit 0 假装成功
"""

import os
import sys

from . import __version__, contract
from .errors import UsageError
from .inventory.build import build_inventory, inventory_path
from .ruleset import load_ruleset
from .serialize import write_json
from .verify import (
    format_bench_report,
    format_verify_report,
    run_bench as run_bench_suites,
    verify_data,
)

DEFAULT_OUT_DIR = "out"


def _ensure_out_dir(out_dir):
    target = os.path.abspath(out_dir or DEFAULT_OUT_DIR)
    if not os.path.isdir(target):
        os.makedirs(target)
    return target


def _not_yet(step, milestone):
    raise UsageError(
        "{0} 属于 {1} 交付范围，当前骨架尚未实现".format(step, milestone),
        step=step,
        milestone=milestone,
        hint="骨架阶段只提供规则包硬门与自检；见 plan/05-里程碑.md",
    )


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
    load_ruleset(explicit=getattr(args, "rules_dir", None), verify_hashes=True)
    _not_yet("assess", "M2–M4")


def run_report(args):
    load_ruleset(explicit=getattr(args, "rules_dir", None), verify_hashes=True)
    _not_yet("report", "M5")


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
    "DEFAULT_OUT_DIR",
    "run_assess",
    "run_bench",
    "run_report",
    "run_scan",
    "run_status",
    "run_verify_data",
    "write_status_artifact",
]
