# -*- coding: utf-8 -*-
"""一次性变异验证：弄坏 → 变红 → 恢复 → 变绿。

用法：py -3.12 -X utf8 tools/_mutate_m2.py
"""

import io
import os
import re
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROFILE = os.path.join(REPO, "src", "licaudit", "assess", "profile.py")
VERIFY = os.path.join(REPO, "src", "licaudit", "verify.py")

MUTATIONS = [
    (
        "M1：档位判定读 FSF（K9 破坏）",
        PROFILE,
        "def _profile_entry(atom, rule, index, ruleset_version):\n",
        "def _profile_entry(atom, rule, index, ruleset_version):\n"
        "    if rule is not None and index.is_fsf_libre(atom) is False:\n"
        "        rule = None\n",
        ["tests/test_profile.py::test_fsf_libre_does_not_participate_in_judgement"],
    ),
    (
        "M2：OSI 状态伪造（不从快照取）",
        PROFILE,
        '    is_osi = index.is_osi_approved(atom) if in_snapshot else None\n',
        "    is_osi = True\n",
        ["tests/test_profile.py::test_osi_and_fsf_come_from_snapshot_only"],
    ),
    (
        "M3：disabled 规则照用",
        PROFILE,
        "    if entry.get(\"verified\") is not True:\n        return True\n",
        "    if False:\n        return True\n",
        [
            "tests/test_profile.py::test_disabled_rule_never_produces_a_tier",
            "tests/test_profile.py::test_engine_ignores_unverified_rule_even_if_caller_bypasses_loader",
        ],
    ),
    (
        "M4：义务项按规则表原序输出（不规范化）",
        PROFILE,
        "        \"obligations\": canonical_obligations(rule[\"obligations\"]),",
        "        \"obligations\": list(rule[\"obligations\"]),",
        ["tests/test_profile.py::test_tier_and_obligations_come_from_ruleset"],
    ),
    (
        "M5：表达式不拆原子（整串当原子）",
        PROFILE,
        "    try:\n        parsed = parse_expression(text, index)\n    except ExprError:\n        return [text], \"expression_unparsed\"\n    return parsed.atoms, None",
        "    return [text], None",
        ["tests/test_profile.py::test_expression_is_split_into_atoms"],
    ),
    (
        "M6：未覆盖 ID 的 reasons 少基码",
        PROFILE,
        "    reasons = {\"tier_uncovered\"}\n",
        "    reasons = set()\n",
        ["tests/test_profile.py::test_uncovered_id_gets_null_tier_and_pending"],
    ),
    (
        "M7：条款锚点被截断（不再逐字一致）",
        PROFILE,
        "        copied[field] = anchor.get(field)",
        "        copied[field] = (anchor.get(field) or \"\")[:20] if field == \"quote\" else anchor.get(field)",
        ["tests/test_profile.py::test_every_tiered_profile_carries_locatable_anchor"],
    ),
    (
        "M8：m2 基准恒判通过",
        VERIFY,
        '                "ok": not report["structural_problems"] and not report["mismatches"],',
        '                "ok": True,',
        ["tests/test_profile.py::test_bench_m2_turns_red_when_truth_drifts"],
    ),
    (
        "M9：pending 记录不进画像（D22 破坏）",
        PROFILE,
        "        if isinstance(entry, dict):\n            records.append(entry.get(\"record\") or {})",
        "        if False:\n            records.append(entry.get(\"record\") or {})",
        ["tests/test_profile.py::test_pending_records_also_contribute_atoms"],
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
