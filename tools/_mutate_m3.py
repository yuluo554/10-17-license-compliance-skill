# -*- coding: utf-8 -*-
"""M3 一次性变异验证：弄坏 → 变红 → 恢复 → 变绿。

用法：py -3.12 -X utf8 tools/_mutate_m3.py
"""

import io
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCENARIO = os.path.join(REPO, "src", "licaudit", "assess", "scenario.py")
PIPELINE = os.path.join(REPO, "src", "licaudit", "pipeline.py")
VERIFY = os.path.join(REPO, "src", "licaudit", "verify.py")
RULESET = os.path.join(REPO, "references", "ruleset", "scenario-triggers.json")

MUTATIONS = [
    (
        "M1：AGPL §13 不再要求 network_interaction（K13 破坏）",
        SCENARIO,
        '        return entry.get("network_interaction") is True and network_interaction is True\n',
        "        return True\n",
        [
            "tests/test_scenario.py::test_internal_agpl_without_network_interaction_does_not_trigger",
            "tests/test_scenario.py::test_container_image_without_network_answer_is_pending_for_network_tier",
        ],
    ),
    (
        "M2：SaaS 未回答网络交互时按「不触发」放过（K14 破坏）",
        SCENARIO,
        "    if match_scenario in _NETWORK_REQUIRED:\n"
        "        if network_interaction is None:\n"
        "            run_pending.append(REASON_NETWORK_UNANSWERED)\n",
        "    if match_scenario in _NETWORK_REQUIRED:\n"
        "        if False:\n"
        "            run_pending.append(REASON_NETWORK_UNANSWERED)\n",
        ["tests/test_scenario.py::test_saas_without_network_answer_is_pending"],
    ),
    (
        "M3：链接方式轴场景缺交付形态时不再待确认（K14 破坏）",
        SCENARIO,
        "    if match_scenario is None:\n"
        "        run_pending.append(REASON_DELIVERY_UNANSWERED)\n",
        "    if match_scenario is None:\n"
        "        match_scenario = \"internal\"\n",
        ["tests/test_scenario.py::test_link_scenario_without_delivery_is_pending"],
    ),
    (
        "M4：触发匹配忽略 link_modes",
        SCENARIO,
        '    if link_mode not in (entry.get("link_modes") or []):\n        return False\n',
        "    if False:\n        return False\n",
        ["tests/test_scenario.py::test_dynamic_link_of_weak_copyleft_triggers_distribution_not_static"],
    ),
    (
        "M5：触发匹配忽略 scenarios",
        SCENARIO,
        '    if scenario not in (entry.get("scenarios") or []):\n        return False\n',
        "    if False:\n        return False\n",
        ["tests/test_scenario.py::test_internal_use_does_not_trigger_copyleft"],
    ),
    (
        "M6：未覆盖档位不再待确认（猜档位）",
        SCENARIO,
        "    if tier is None:\n"
        "        return {\n"
        "            \"verdict\": contract.PENDING,",
        "    if tier is None:\n"
        "        tier = \"permissive\"\n"
        "    if False:\n"
        "        return {\n"
        "            \"verdict\": contract.PENDING,",
        ["tests/test_scenario.py::test_uncovered_id_is_pending_not_guessed"],
    ),
    (
        "M7：disabled 触发条目照用（K10 破坏）",
        SCENARIO,
        '    if entry.get("verified") is not True:\n        return True\n',
        "    if False:\n        return True\n",
        ["tests/test_scenario.py::test_disabled_trigger_rule_never_produces_a_judgement"],
    ),
    (
        "M8：用户回答不落盘（K12/K14 破坏）",
        SCENARIO,
        '            "user_answer": raw_answer,',
        '            "user_answer": None,',
        ["tests/test_scenario.py::test_user_answer_is_persisted_verbatim"],
    ),
    (
        "M9：m3 基准恒判通过",
        VERIFY,
        '                "suite": "m3",\n'
        '                "name": "场景判定表与真值对账",\n'
        '                "cases": report["records_checked"],\n'
        '                "records": report["records_checked"],\n'
        '                "matched": report["matched"],\n'
        '                "scores": {},\n'
        '                "ok": not report["structural_problems"] and not report["mismatches"],\n',
        '                "suite": "m3",\n'
        '                "name": "场景判定表与真值对账",\n'
        '                "cases": report["records_checked"],\n'
        '                "records": report["records_checked"],\n'
        '                "matched": report["matched"],\n'
        '                "scores": {},\n'
        '                "ok": True,\n',
        ["tests/test_scenario.py::test_bench_m3_turns_red_when_truth_drifts"],
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
