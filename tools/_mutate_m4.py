# -*- coding: utf-8 -*-
"""M4 一次性变异验证：弄坏 → 变红 → 恢复 → 变绿。

用法：py -3.12 -X utf8 tools/_mutate_m4.py
"""

import io
import os
import subprocess
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFLICT = os.path.join(REPO, "src", "licaudit", "assess", "conflict.py")
SCENARIO = os.path.join(REPO, "src", "licaudit", "assess", "scenario.py")
VERIFY = os.path.join(REPO, "src", "licaudit", "verify.py")

MUTATIONS = [
    (
        "M1：冲突对不再无向匹配（K15 破坏）",
        CONFLICT,
        "    return (left, right) if left <= right else (right, left)\n",
        "    return (left, right)\n",
        [
            "tests/test_conflict.py::test_undirected_matching_survives_record_order",
            "tests/test_conflict.py::test_every_curated_pair_is_hit_with_its_curated_resolution",
        ],
    ),
    (
        "M2：OR 取最严格（K16 破坏）",
        CONFLICT,
        "                if leaf_rank < best_rank:\n                    best = leaf\n",
        "                if leaf_rank > best_rank:\n                    best = leaf\n",
        ["tests/test_conflict.py::test_or_takes_the_most_permissive_atom"],
    ),
    (
        "M3：AND 取最宽松（K16 破坏）",
        CONFLICT,
        "                if leaf_rank > best_rank:\n                    best = leaf\n",
        "                if leaf_rank < best_rank:\n                    best = leaf\n",
        ["tests/test_conflict.py::test_and_takes_the_strictest_atom"],
    ),
    (
        "M4：outbound = pending 时按 compatible 放过（K17 破坏）",
        CONFLICT,
        '    if outbound == "pending":\n        return "pending"\n',
        '    if outbound == "pending":\n        return "compatible"\n',
        ["tests/test_conflict.py::test_outbound_pending_makes_every_entry_pending"],
    ),
    (
        "M5：依赖强于 outbound 时判 compatible（plan/03 §4.5 破坏）",
        CONFLICT,
        '    if contract.TIER_RANK[group["tier"]] > contract.TIER_RANK[outbound_tier]:\n'
        '        return "incompatible"\n',
        '    if contract.TIER_RANK[group["tier"]] > contract.TIER_RANK[outbound_tier]:\n'
        '        return "compatible"\n',
        ["tests/test_conflict.py::test_stronger_dependency_than_outbound_is_incompatible"],
    ),
    (
        "M6：未覆盖档位按 permissive 猜（K31 破坏）",
        CONFLICT,
        '    if group["license_id"] is None or group["tier"] is None:\n'
        '        return "pending"\n',
        '    if group["license_id"] is None or group["tier"] is None:\n'
        '        group["tier"] = group["tier"] or "permissive"\n',
        ["tests/test_conflict.py::test_uncovered_license_is_pending_not_guessed"],
    ),
    (
        "M7：求值时缺档位的原子按 permissive 猜（K7/K31 破坏）",
        CONFLICT,
        "    tier = tier_by_atom.get(atom)\n"
        "    if tier not in contract.TIERS:\n"
        "        if atom not in missing:\n"
        "            missing.append(atom)\n"
        "        return None\n"
        "    return (atom, tier)\n",
        "    tier = tier_by_atom.get(atom)\n"
        "    if tier not in contract.TIERS:\n"
        '        tier = "permissive"\n'
        "    return (atom, tier)\n",
        ["tests/test_conflict.py::test_expression_with_uncovered_atom_is_not_evaluated"],
    ),
    (
        "M8：单原子记录也进 expression_evaluations",
        CONFLICT,
        "        if len(atoms) == 1:\n",
        "        if len(atoms) < 0:\n",
        ["tests/test_conflict.py::test_single_atom_records_are_not_evaluated"],
    ),
    (
        "M9：冲突依据不再来自 curated 规则表",
        CONFLICT,
        '                entry["basis"],\n',
        '                "冲突",\n',
        [
            "tests/test_conflict.py::test_conflict_records_declare_the_curated_basis",
            "tests/test_conflict.py::test_conflict_record_field_order_matches_contract",
        ],
    ),
    (
        "M10：disabled 冲突对条目照用（K10 破坏）",
        CONFLICT,
        '    if entry.get("verified") is not True:\n        return True\n',
        "    if False:\n        return True\n",
        [
            "tests/test_conflict.py::test_unverified_pair_is_rejected_by_the_loader_and_ignored_by_the_engine"
        ],
    ),
    (
        "M11：m4 基准恒判通过",
        VERIFY,
        '                "suite": "m4",\n'
        '                "name": "冲突判定与真值对账",\n'
        '                "cases": report["records_checked"],\n'
        '                "records": report["records_checked"],\n'
        '                "matched": report["matched"],\n'
        '                "scores": {},\n'
        '                "ok": not report["structural_problems"] and not report["mismatches"],\n',
        '                "suite": "m4",\n'
        '                "name": "冲突判定与真值对账",\n'
        '                "cases": report["records_checked"],\n'
        '                "records": report["records_checked"],\n'
        '                "matched": report["matched"],\n'
        '                "scores": {},\n'
        '                "ok": True,\n',
        ["tests/test_conflict.py::test_bench_m4_turns_red_when_truth_drifts"],
    ),
    (
        "M12：表达式求值不再回填 scenario 判定（D32 破坏）",
        SCENARIO,
        "    for position, item in enumerate(atom_results):\n"
        '        if item["spdx_id"] == evaluation["selected"]:\n'
        "            return item[\"verdict\"], position, [], evaluation\n"
        "    return contract.PENDING, None, [REASON_EXPRESSION_UNRESOLVED], evaluation\n",
        "    verdicts = [item[\"verdict\"] for item in atom_results]\n"
        "    if len(set(verdicts)) == 1:\n"
        "        return verdicts[0], 0, [], evaluation\n"
        "    return contract.PENDING, None, [REASON_EXPRESSION_UNRESOLVED], evaluation\n",
        [
            "tests/test_scenario.py::test_expression_is_evaluated_and_the_most_permissive_atom_wins",
            "tests/test_conflict.py::test_expression_scenario_backfill_matches_the_conflict_evaluation",
        ],
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
