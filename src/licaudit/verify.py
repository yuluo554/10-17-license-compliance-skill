# -*- coding: utf-8 -*-
"""真值对账与内置基准（M1 起）。

``verify-data``：读 **冻结** 的 ``data/truth/truth.json``，用运行时解析器复算，
逐条比对；同时校验冻结数据本身的形态（无 ``observed_*``、输入文件存在）。

``bench``：按套件跑内置基准，返回 ``(结果, 退出码)``。
M1 只有 ``m1`` 套件；其余套件如实报「未实现」而不是假装通过。
"""

import io
import json
import os

from . import contract
from .errors import UsageError
from .inventory.build import build_inventory
from .serialize import load_artifact

TRUTH_FORMAT = "licaudit-truth"
BENCH_SUITES = ("m1", "m2", "m3", "m4", "m5")


def repo_root():
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _read_truth(data_dir):
    path = os.path.join(data_dir, "truth", "truth.json")
    if not os.path.isfile(path):
        raise UsageError(
            "真值库不存在，先运行 tools/gen_synthetic.py",
            path=path,
        )
    try:
        with io.open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (UnicodeDecodeError, ValueError) as exc:
        raise UsageError("真值库不是合法 UTF-8 JSON", path=path, reason=str(exc))
    if payload.get("format") != TRUTH_FORMAT:
        raise UsageError(
            "真值库格式不受支持",
            path=path,
            got=payload.get("format"),
            expected=TRUTH_FORMAT,
        )
    if payload.get("format_version") != contract.FORMAT_VERSION:
        raise UsageError(
            "真值库格式版本不受支持",
            path=path,
            got=payload.get("format_version"),
        )
    return payload, path


def _forbidden_observed_keys(payload):
    problems = []
    for case in payload.get("cases", []):
        case_id = case.get("case_id")

        def walk(node, trail):
            if isinstance(node, dict):
                for key in sorted(node):
                    if key.startswith("observed_"):
                        problems.append(
                            "{0}: {1} 出现观测字段 {2}".format(case_id, trail, key)
                        )
                    walk(node[key], trail + "." + key if trail else key)
            elif isinstance(node, list):
                for index, item in enumerate(node):
                    walk(item, "{0}[{1}]".format(trail, index))

        walk(case, "")
    return problems


def _expected_records(payload):
    """把真值展开成 ``{case_id: {package: expect}}``，并按落点分组。"""
    result = {}
    for case in payload.get("cases", []):
        case_id = case.get("case_id")
        expect = case.get("expect") or {}
        result[case_id] = {
            "dependencies": {
                item["package"]: item for item in expect.get("dependencies", [])
            },
            "pending_confirmation": {
                item["package"]: item for item in expect.get("pending_confirmation", [])
            },
        }
    return result


def _score(resolved_expected, resolved_actual):
    """把「是否给出 SPDX ID」当成二分类，算精确率 / 召回率 / F1。

    正类 = 「成功归一化到某个 SPDX ID」。截断兜底（``spdx_id = null``）是负类：
    解析器在拿不准时不猜，比猜错更可取。
    """
    true_positive = 0
    false_positive = 0
    false_negative = 0
    for package in sorted(resolved_expected):
        want = resolved_expected[package]
        got = resolved_actual.get(package)
        if want and got == want:
            true_positive += 1
        elif want and got != want:
            false_negative += 1
        elif not want and got:
            false_positive += 1
    for package in sorted(resolved_actual):
        if package not in resolved_expected:
            false_positive += 1
    precision = (
        true_positive / float(true_positive + false_positive)
        if (true_positive + false_positive)
        else 1.0
    )
    recall = (
        true_positive / float(true_positive + false_negative)
        if (true_positive + false_negative)
        else 1.0
    )
    f1 = (
        2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    )
    return {
        "true_positive": true_positive,
        "false_positive": false_positive,
        "false_negative": false_negative,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
    }


def _actual_records(inventory):
    dependencies = {}
    for item in inventory.get("dependencies", []):
        dependencies[item["package"]] = {
            "version": item["version"],
            "spdx_id": item["spdx_id"],
            "confidence": item["confidence"],
            "flags": list(item["evidence"].get("flags") or []),
        }
    pending = {}
    for entry in inventory.get("pending_confirmation", []):
        record = entry.get("record") or {}
        pending[record.get("package")] = {
            "version": record.get("version"),
            "spdx_id": record.get("spdx_id"),
            "confidence": record.get("confidence"),
            "flags": list((record.get("evidence") or {}).get("flags") or []),
        }
    return {"dependencies": dependencies, "pending_confirmation": pending}


def verify_data(data_dir, ruleset, spdx_dir=None):
    """返回 ``(report, exit_code)``。"""
    payload, truth_path = _read_truth(data_dir)
    structural = _forbidden_observed_keys(payload)

    expected = _expected_records(payload)
    mismatches = []
    cases_checked = 0
    records_checked = 0
    total_matched = 0
    resolved_expected = {}
    resolved_actual = {}

    for case_id in sorted(expected):
        case_dir = os.path.join(data_dir, "synthetic", case_id)
        if not os.path.isdir(case_dir):
            structural.append("{0}: 缺少输入目录 {1}".format(case_id, case_dir))
            continue
        # 真值登记的是相对该用例目录的路径
        case_entry = next(
            (item for item in payload["cases"] if item.get("case_id") == case_id), None
        )
        files = ((case_entry or {}).get("inputs") or {}).get("files") or []
        if not files:
            structural.append("{0}: 真值未登记输入文件".format(case_id))
            continue
        paths = [os.path.join(case_dir, name) for name in files]
        missing_files = [path for path in paths if not os.path.isfile(path)]
        if missing_files:
            structural.append(
                "{0}: 输入文件缺失 {1}".format(case_id, ", ".join(missing_files))
            )
            continue

        inventory = build_inventory(paths, ruleset, spdx_dir=spdx_dir)
        actual = _actual_records(inventory)
        cases_checked += 1

        for group in ("dependencies", "pending_confirmation"):
            for package, want in expected[case_id][group].items():
                resolved_expected[package] = want.get("spdx_id")
            for package, got in actual[group].items():
                resolved_actual[package] = got.get("spdx_id")

        for group in ("dependencies", "pending_confirmation"):
            want_group = expected[case_id][group]
            got_group = actual[group]
            for package in sorted(want_group):
                records_checked += 1
                want = want_group[package]
                got = got_group.get(package)
                if got is None:
                    mismatches.append(
                        "{0}/{1}: 期望在 {2}，实际不在".format(case_id, package, group)
                    )
                    continue
                for key in ("version", "spdx_id", "confidence", "flags"):
                    if got.get(key) != want.get(key):
                        mismatches.append(
                            "{0}/{1}.{2}: 期望 {3!r}，实际 {4!r}".format(
                                case_id, package, key, want.get(key), got.get(key)
                            )
                        )
                else:
                    total_matched += 1
            for package in sorted(got_group):
                if package not in want_group:
                    mismatches.append(
                        "{0}/{1}: 实际在 {2}，真值未登记".format(case_id, package, group)
                    )

    score = _score(resolved_expected, resolved_actual)

    report = {
        "truth_path": truth_path,
        "cases_checked": cases_checked,
        "records_checked": records_checked,
        "matched": total_matched,
        "scores": score,
        "structural_problems": structural,
        "mismatches": mismatches,
    }
    ok = not structural and not mismatches
    return report, (0 if ok else 1)


def format_verify_report(report):
    scores = report.get("scores") or {}
    lines = [
        "真值库: {0}".format(report["truth_path"]),
        "用例 {0} 个；记录 {1} 条；命中 {2} 条".format(
            report["cases_checked"], report["records_checked"], report["matched"]
        ),
        "SPDX 归一化：精确率 {0} / 召回率 {1} / F1 {2}".format(
            scores.get("precision"), scores.get("recall"), scores.get("f1")
        ),
    ]
    for problem in report["structural_problems"]:
        lines.append("[FAIL] 结构: {0}".format(problem))
    for problem in report["mismatches"]:
        lines.append("[FAIL] 对账: {0}".format(problem))
    if not report["structural_problems"] and not report["mismatches"]:
        lines.append("[OK] 冻结真值与参考实现逐条一致")
    return "\n".join(lines)


def run_bench(only, ruleset, data_dir, spdx_dir=None):
    """执行基准套件；返回 ``(report, exit_code)``。

    ``only`` 为 ``None`` 时跑全部**已实现**套件；指定未实现套件 → ``UsageError``。
    """
    if only is not None and only not in BENCH_SUITES:
        raise UsageError(
            "未知的基准套件",
            got=only,
            known=", ".join(BENCH_SUITES),
        )

    implemented = ("m1",)
    if only is not None and only not in implemented:
        raise UsageError(
            "该基准套件尚未实现",
            suite=only,
            implemented=", ".join(implemented),
        )

    suites = [only] if only else list(implemented)
    results = []
    failures = []
    for suite in suites:
        if suite == "m1":
            report, code = verify_data(data_dir, ruleset, spdx_dir=spdx_dir)
            scores = report.get("scores") or {}
            results.append({
                "suite": "m1",
                "name": "清单解析与真值对账",
                "cases": report["cases_checked"],
                "records": report["records_checked"],
                "matched": report["matched"],
                "scores": scores,
                "ok": code == 0 and scores.get("f1", 0.0) >= 0.95,
                "failures": report["structural_problems"] + report["mismatches"],
            })
            if code != 0:
                failures.extend(report["mismatches"])

    exit_code = 0 if all(item["ok"] for item in results) else 1
    return {"suites": results, "failures": failures}, exit_code


def format_bench_report(report):
    lines = []
    for suite in report["suites"]:
        mark = "OK" if suite["ok"] else "FAIL"
        scores = suite.get("scores") or {}
        lines.append(
            "[{0}] {1} {2}：用例 {3} 个 / 记录 {4} 条 / 命中 {5} 条 / F1 {6}".format(
                mark, suite["suite"], suite["name"], suite["cases"],
                suite["records"], suite["matched"], scores.get("f1"),
            )
        )
        if scores and scores.get("f1", 0.0) < 0.95:
            lines.append(
                "    F1 低于 DoD 阈值 0.95：{0}".format(scores)
            )
        for failure in suite["failures"][:10]:
            lines.append("    {0}".format(failure))
        if len(suite["failures"]) > 10:
            lines.append("    …… 其余 {0} 条见 verify-data".format(len(suite["failures"]) - 10))
    return "\n".join(lines)


__all__ = [
    "BENCH_SUITES",
    "format_bench_report",
    "format_verify_report",
    "run_bench",
    "verify_data",
]
