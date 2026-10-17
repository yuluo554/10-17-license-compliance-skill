# -*- coding: utf-8 -*-
"""M5 一次性变异验证：弄坏 → 变红 → 恢复 → 变绿。

用法：py -3.12 -X utf8 tools/_mutate_m5.py
"""

import io
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ACTION = os.path.join(REPO, "src", "licaudit", "assess", "action.py")
PIPELINE = os.path.join(REPO, "src", "licaudit", "pipeline.py")
VERIFY = os.path.join(REPO, "src", "licaudit", "verify.py")
SECTIONS = os.path.join(REPO, "src", "licaudit", "report", "sections.py")

MUTATIONS = [
    (
        "M1：义务轴任一命中即算命中（义务轴形同虚设）",
        ACTION,
        '        if key == "axes_any":\n'
        '            if not (set(facts.get("axes") or []) & set(wanted)):\n'
        "                return False\n",
        '        if key == "axes_any":\n'
        '            if False:\n'
        "                return False\n",
        ["tests/test_action.py::test_permissive_dependency_without_obligations_is_ok"],
    ),
    (
        "M2：五锚点门不再要求声明位置（K20 破坏）",
        ACTION,
        "    if declaration_location(record.get(\"evidence\")) is None:\n"
        "        reasons.append(REASON_DECLARATION_MISSING)\n"
        "        missing.append(\"declaration_location\")\n",
        "",
        [
            "tests/test_action.py::test_pending_action_declares_which_anchor_is_missing",
            "tests/test_action.py::test_action_layer_alone_can_force_exit_one",
        ],
    ),
    (
        "M3：版本未知不再降级（plan/03 §5.2 破坏）",
        ACTION,
        '    if not isinstance(version, str) or not version.strip() or version == "*":\n',
        "    if False:\n",
        ["tests/test_action.py::test_unknown_version_degrades_the_action"],
    ),
    (
        "M4：输入不确定时照给级别（K7/K14 破坏）",
        ACTION,
        '    elif facts["verdict"] == contract.PENDING:\n'
        "        reasons.append(REASON_SCENARIO_PENDING)\n",
        "",
        ["tests/test_action.py::test_unresolved_inputs_go_to_pending_not_to_ok"],
    ),
    (
        "M5：义务轴映射不可用时不再禁用整张表（K4 破坏）",
        ACTION,
        "    if not axes:\n        return []\n",
        "    if not axes:\n        pass\n",
        [
            "tests/test_action.py::test_unusable_obligation_axes_never_yield_ok",
            "tests/test_action.py::test_usable_rules_rejects_entries_with_undefined_axis",
        ],
    ),
    (
        "M6：不校验 when 里的义务轴是否已定义",
        ACTION,
        "        if _when_uses_undefined_axis(when, axes):\n            continue\n",
        "",
        ["tests/test_action.py::test_usable_rules_rejects_entries_with_undefined_axis"],
    ),
    (
        "M7：决策表改成「最后命中者生效」（顺序语义破坏）",
        ACTION,
        "    for rule in rules:\n"
        "        if matches(rule.get(\"when\") or {}, facts):\n"
        "            return rule\n"
        "    return None\n",
        "    found = None\n"
        "    for rule in rules:\n"
        "        if matches(rule.get(\"when\") or {}, facts):\n"
        "            found = rule\n"
        "    return found\n",
        ["tests/test_action.py::test_first_matching_rule_wins"],
    ),
    (
        "M8：待确认项不再算阻断（§5.5 破坏）",
        ACTION,
        '    return bool(payload.get("pending_confirmation"))\n',
        "    return False\n",
        ["tests/test_action.py::test_has_blocking_action_covers_levels_and_pending"],
    ),
    (
        "M9：退出码聚合漏掉处置层",
        PIPELINE,
        "        or has_blocking_action(action_payload)\n",
        "",
        ["tests/test_action.py::test_action_layer_alone_can_force_exit_one"],
    ),
    (
        "M10：m5 基准恒判通过",
        VERIFY,
        '                "suite": "m5",\n'
        '                "name": "处置分级与真值对账",\n'
        '                "cases": report["records_checked"],\n'
        '                "records": report["records_checked"],\n'
        '                "matched": report["matched"],\n'
        '                "scores": {},\n'
        '                "ok": not report["structural_problems"] and not report["mismatches"],\n',
        '                "suite": "m5",\n'
        '                "name": "处置分级与真值对账",\n'
        '                "cases": report["records_checked"],\n'
        '                "records": report["records_checked"],\n'
        '                "matched": report["matched"],\n'
        '                "scores": {},\n'
        '                "ok": True,\n',
        ["tests/test_action.py::test_bench_m5_turns_red_when_truth_drifts"],
    ),
    (
        "M11：报告层内联档位名（AST 内联判定表守门）",
        SECTIONS,
        "    for tier in contract.TIERS:\n",
        '    for tier in ("permissive", "weak-copyleft", "strong-copyleft",\n'
        '                 "network-copyleft", "source-available"):\n',
        ["tests/test_report.py::test_report_layer_has_no_inline_license_or_level_table"],
    ),
    (
        "M12：报告层引入判定模块（AST import 守门）",
        SECTIONS,
        "from .. import contract\n",
        "from .. import contract\nfrom ..assess import action as _judgement  # noqa: F401\n",
        ["tests/test_report.py::test_report_layer_does_not_import_judgement_modules"],
    ),
    (
        "M13：报告层出现非常量字符串拼接（AST BinOp 守门）",
        SECTIONS,
        '        parts.append("原因码：{0}".format("、".join(codes)))\n',
        '        parts.append("原因码：" + "、".join(codes))\n',
        ["tests/test_report.py::test_report_layer_has_no_arithmetic_or_concatenation_binop"],
    ),
]


def read(path):
    return io.open(path, encoding="utf-8").read()


def write(path, text):
    io.open(path, "w", encoding="utf-8", newline="\n").write(text)


def run_tests(paths):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.path.join(REPO, "src")
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q"] + paths,
        cwd=REPO, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
    )


def main():
    failures = []
    for label, path, old, new, tests in MUTATIONS:
        original = read(path)
        if old not in original:
            print("[SKIP] {0}：变异点未找到".format(label))
            failures.append(label)
            continue
        write(path, original.replace(old, new, 1))
        try:
            result = run_tests(tests)
            red = result.returncode != 0
            print("[{0}] {1} → 目标测试 {2}".format(
                "OK" if red else "FAIL", label, "变红" if red else "仍是绿（变异未被发现）"
            ))
            if not red:
                failures.append(label)
                print(result.stdout.decode("utf-8", "replace")[-1500:])
        finally:
            write(path, original)
        green = run_tests(tests)
        print("     恢复后 {0}".format("变绿" if green.returncode == 0 else "仍红（恢复失败）"))
        if green.returncode != 0:
            failures.append(label + "（恢复后仍红）")
            print(green.stdout.decode("utf-8", "replace")[-1500:])

    print()
    if failures:
        print("[FAIL] 变异验证未全通过：{0}".format("；".join(failures)))
        return 1
    print("[OK] {0} 组变异全部「弄坏 → 变红 → 恢复 → 变绿」".format(len(MUTATIONS)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
