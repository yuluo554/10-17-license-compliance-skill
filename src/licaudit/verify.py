# -*- coding: utf-8 -*-
"""真值对账与内置基准（M1 起）。

``verify-data``：读 **冻结** 的 ``data/truth/truth.json``，用运行时解析器复算，
逐条比对；同时校验冻结数据本身的形态（无 ``observed_*``、输入文件存在）。

``bench``：按套件跑内置基准，返回 ``(结果, 退出码)``。
已实现 ``m1`` / ``m2`` / ``m3`` / ``m4`` / ``m5``；``m6`` 属发布里程碑（无判定套件），
其余未实现套件如实报「未实现」而不是假装通过。
"""

import io
import json
import os

from . import contract
from .assess.action import (
    ACTION_RULE_FILE,
    match_rule,
    obligation_axes,
    usable_rules,
)
from .assess.conflict import build_conflicts
from .assess.profile import load_context, profile_ids
from .assess.scenario import SCENARIO_RULE_FILE, build_scenario, evaluate_tier
from .errors import UsageError
from .inventory.build import build_inventory
from .serialize import load_artifact

TRUTH_FORMAT = "licaudit-truth"
PROFILE_TRUTH_FORMAT = "licaudit-profile-truth"
SCENARIO_TRUTH_FORMAT = "licaudit-scenario-truth"
CONFLICT_TRUTH_FORMAT = "licaudit-conflicts-truth"
ACTIONS_TRUTH_FORMAT = "licaudit-actions-truth"
# ``BENCH_SUITES`` 是「本题全部里程碑套件」；``IMPLEMENTED_SUITES`` 是已实现子集。
# 未实现的套件必须显式报错，而不是跑一个空套件返回通过。
BENCH_SUITES = ("m1", "m2", "m3", "m4", "m5", "m6")
FACT_FIELDS = ("axes", "conflict", "pair_conflict", "link_mode", "verdict")


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


IMPLEMENTED_SUITES = ("m1", "m2", "m3", "m4", "m5")


def _read_profile_truth(data_dir):
    path = os.path.join(data_dir, "truth", "profile.json")
    if not os.path.isfile(path):
        raise UsageError(
            "画像真值不存在，先运行 tools/gen_profile_truth.py",
            path=path,
        )
    try:
        with io.open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (UnicodeDecodeError, ValueError) as exc:
        raise UsageError("画像真值不是合法 UTF-8 JSON", path=path, reason=str(exc))
    if payload.get("format") != PROFILE_TRUTH_FORMAT:
        raise UsageError(
            "画像真值格式不受支持",
            path=path,
            got=payload.get("format"),
            expected=PROFILE_TRUTH_FORMAT,
        )
    if payload.get("format_version") != contract.FORMAT_VERSION:
        raise UsageError(
            "画像真值格式版本不受支持",
            path=path,
            got=payload.get("format_version"),
        )
    return payload, path


def _profile_actual_entries(payload):
    """把 ``profile.json`` 摊成 ``{spdx_id: 便于比对的平面记录}``。"""
    records = {}
    for item in payload.get("profiles") or []:
        if not isinstance(item, dict) or not item.get("spdx_id"):
            continue
        evidence = item.get("evidence") or {}
        patent = item.get("patent_clause") or {}
        trademark = item.get("trademark_clause") or {}
        records[item["spdx_id"]] = {
            "tier": item.get("tier"),
            "obligations": item.get("obligations"),
            "is_osi_approved": item.get("is_osi_approved"),
            "is_fsf_libre": item.get("is_fsf_libre"),
            "patent_clause_present": patent.get("present"),
            "trademark_clause_present": trademark.get("present"),
            # 有档位就必须有完整证据锚点；下面用它做「五锚点」式完整性断言。
            "evidence_anchor": evidence.get("license_text_anchor"),
            "evidence_checked_on": evidence.get("checked_on"),
            "evidence_details_url": evidence.get("details_url"),
        }
    pending = {}
    for item in payload.get("pending_confirmation") or []:
        if isinstance(item, dict) and item.get("spdx_id"):
            pending[item["spdx_id"]] = {
                "reasons": list(item.get("reasons") or []),
                "missing": list(item.get("missing") or []),
            }
    return records, pending


def verify_profile(data_dir, ruleset, spdx_dir=None):
    """M2 画像对账：真值（规则表的投影）vs 运行时引擎。返回 ``report``。

    ``spdx_dir`` 只用于 OSI/FSF 展示字段；判定部分（档位/义务/条款）全部来自规则表。
    """
    payload, truth_path = _read_profile_truth(data_dir)
    structural = []
    text = io.open(truth_path, encoding="utf-8").read()
    if "observed_" in text:
        structural.append("画像真值出现观测字段 observed_*（K26）")

    inputs = payload.get("inputs") or {}
    spdx_ids = inputs.get("spdx_ids") or []
    if not spdx_ids:
        structural.append("画像真值未登记 inputs.spdx_ids")
    expect = payload.get("expect") or {}
    expected_profiles = {item["spdx_id"]: item for item in expect.get("profiles") or []}
    expected_pending = {item["spdx_id"]: item for item in expect.get("pending") or []}
    if not expected_profiles:
        structural.append("画像真值缺少 expect.profiles")
    if not expected_pending:
        structural.append("画像真值缺少 expect.pending（tier: null 分支无人守）")

    index, license_list_version = load_context(spdx_dir)
    actual_payload = profile_ids(
        spdx_ids, ruleset, index, license_list_version
    )
    actual, actual_pending = _profile_actual_entries(actual_payload)

    mismatches = []
    matched = 0
    checked = 0
    for spdx_id in sorted(expected_profiles):
        checked += 1
        want = expected_profiles[spdx_id]
        got = actual.get(spdx_id)
        if got is None:
            mismatches.append("{0}: 期望有画像，实际缺失".format(spdx_id))
            continue
        for key in ("tier", "obligations", "is_osi_approved", "is_fsf_libre",
                    "patent_clause_present", "trademark_clause_present"):
            if got.get(key) != want.get(key):
                mismatches.append(
                    "{0}.{1}: 期望 {2!r}，实际 {3!r}".format(
                        spdx_id, key, want.get(key), got.get(key)
                    )
                )
        # 有档位 → 必须有原文锚点与核对日期（plan/02 §M2 DoD）
        anchor = got.get("evidence_anchor") or {}
        if not anchor.get("ref") or not anchor.get("quote"):
            mismatches.append("{0}: 有档位却没有可定位的原文锚点".format(spdx_id))
        if not got.get("evidence_checked_on"):
            mismatches.append("{0}: 有档位却没有 checked_on".format(spdx_id))
        if spdx_id in expected_pending:
            mismatches.append("{0}: 有档位却被登记为待确认".format(spdx_id))
        matched += 1

    for spdx_id in sorted(expected_pending):
        checked += 1
        want = expected_pending[spdx_id]
        got_pending = actual_pending.get(spdx_id)
        got_profile = actual.get(spdx_id)
        if got_pending is None:
            mismatches.append("{0}: 期望待确认，实际未登记".format(spdx_id))
            continue
        if got_profile is not None and got_profile.get("tier") is not None:
            mismatches.append(
                "{0}: 待确认项不得有档位，实际 {1!r}".format(spdx_id, got_profile.get("tier"))
            )
        if list(want.get("reasons") or []) != list(got_pending.get("reasons") or []):
            mismatches.append(
                "{0}.reasons: 期望 {1!r}，实际 {2!r}".format(
                    spdx_id, want.get("reasons"), got_pending.get("reasons")
                )
            )
        matched += 1

    for spdx_id in sorted(actual):
        if spdx_id not in expected_profiles and spdx_id not in expected_pending:
            mismatches.append("{0}: 实际有画像，真值未登记".format(spdx_id))

    return {
        "truth_path": truth_path,
        "cases_checked": 1,
        "records_checked": checked,
        "matched": matched,
        "structural_problems": structural,
        "mismatches": mismatches,
    }


def format_profile_report(report):
    lines = [
        "画像真值: {0}".format(report["truth_path"]),
        "条目 {0} 条；命中 {1} 条".format(report["records_checked"], report["matched"]),
    ]
    for problem in report["structural_problems"]:
        lines.append("[FAIL] 结构: {0}".format(problem))
    for problem in report["mismatches"]:
        lines.append("[FAIL] 对账: {0}".format(problem))
    if not report["structural_problems"] and not report["mismatches"]:
        lines.append("[OK] 画像矩阵与规则表投影逐条一致")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# M3 场景判定对账
# ---------------------------------------------------------------------------


def _read_scenario_truth(data_dir):
    path = os.path.join(data_dir, "truth", "scenario.json")
    if not os.path.isfile(path):
        raise UsageError(
            "场景真值不存在，先运行 tools/gen_scenario_truth.py",
            path=path,
        )
    try:
        with io.open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (UnicodeDecodeError, ValueError) as exc:
        raise UsageError("场景真值不是合法 UTF-8 JSON", path=path, reason=str(exc))
    if payload.get("format") != SCENARIO_TRUTH_FORMAT:
        raise UsageError(
            "场景真值格式不受支持",
            path=path,
            got=payload.get("format"),
            expected=SCENARIO_TRUTH_FORMAT,
        )
    if payload.get("format_version") != contract.FORMAT_VERSION:
        raise UsageError(
            "场景真值格式版本不受支持",
            path=path,
            got=payload.get("format_version"),
        )
    return payload, path


def _scenario_inventory(tier_samples):
    """按档位样本造一份合成 inventory（每条依赖一个许可证）。"""
    dependencies = []
    for index, tier in enumerate(contract.TIERS):
        license_id = tier_samples.get(tier)
        dependencies.append({
            "package": "example-pkg-{0}".format("abcdefg"[index]),
            "version": "1.0.0",
            "raw_license": license_id,
            "spdx_id": license_id,
            "confidence": "license_expression",
            "evidence": {"ruleset_version": "truth", "details_url": None},
        })
    return {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "dependencies": dependencies,
        "pending_confirmation": [],
        "parse_notes": [],
    }


def verify_scenario(data_dir, ruleset, spdx_dir=None):
    """M3 对账：真值（curated 触发表的投影）vs 运行时场景引擎。返回 ``report``。"""
    payload, truth_path = _read_scenario_truth(data_dir)
    structural = []
    text = io.open(truth_path, encoding="utf-8").read()
    if "observed_" in text:
        structural.append("场景真值出现观测字段 observed_*（K26）")

    inputs = payload.get("inputs") or {}
    tier_samples = inputs.get("tier_samples") or {}
    missing_tiers = [tier for tier in contract.TIERS if not tier_samples.get(tier)]
    if missing_tiers:
        structural.append("场景真值缺少档位样本：{0}".format(", ".join(missing_tiers)))
    matrix = (payload.get("expect") or {}).get("matrix") or []
    if not matrix:
        structural.append("场景真值缺少 expect.matrix")
    pending_rows = (payload.get("expect") or {}).get("pending") or []
    if not pending_rows:
        structural.append("场景真值缺少 expect.pending（tier: null 分支无人守）")

    covered_scenarios = {row.get("scenario") for row in matrix}
    missing_scenarios = [
        item for item in contract.SCENARIO_IDS if item not in covered_scenarios
    ]
    if missing_scenarios:
        structural.append(
            "场景真值未覆盖全部八场景：{0}".format(", ".join(missing_scenarios))
        )

    index, license_list_version = load_context(spdx_dir)
    sample_ids = [tier_samples[tier] for tier in contract.TIERS]
    profile_payload = profile_ids(sample_ids, ruleset, index, license_list_version)
    tier_by_id = {
        item["spdx_id"]: item.get("tier") for item in profile_payload.get("profiles") or []
    }
    for tier in contract.TIERS:
        sample = tier_samples[tier]
        if tier_by_id.get(sample) != tier:
            structural.append(
                "档位样本 {0} 的画像档位是 {1!r}，真值按 {2!r} 记账".format(
                    sample, tier_by_id.get(sample), tier
                )
            )

    inventory = _scenario_inventory(tier_samples)
    package_by_tier = {
        item["package"]: contract.TIERS[index]
        for index, item in enumerate(inventory["dependencies"])
    }
    entries = ruleset.entries(SCENARIO_RULE_FILE)

    groups = {}
    for row in matrix:
        key = (
            row.get("scenario"),
            row.get("delivery"),
            row.get("link_mode"),
            row.get("network_interaction"),
        )
        groups.setdefault(key, []).append(row)

    mismatches = []
    matched = 0
    checked = 0
    for key in sorted(groups, key=lambda item: (
        contract.SCENARIO_IDS.index(item[0]) if item[0] in contract.SCENARIO_IDS else 99,
        contract.LINK_MODES.index(item[2]) if item[2] in contract.LINK_MODES else 99,
        0 if item[3] else 1,
    )):
        scenario, delivery, link_mode, network = key
        scenario_payload = build_scenario(
            inventory, profile_payload, ruleset,
            scenario, delivery, link_mode, network,
            "user", "truth", outbound_license="pending", spdx_index=index,
        )
        actual_by_package = {
            item["package"]: item for item in scenario_payload.get("entries") or []
        }
        for row in groups[key]:
            checked += 1
            package = None
            for candidate, tier in package_by_tier.items():
                if tier == row.get("tier"):
                    package = candidate
                    break
            if package is None:
                mismatches.append("{0}: 真值档位不在样本表中".format(row.get("tier")))
                continue
            got = actual_by_package.get(package)
            if got is None:
                mismatches.append(
                    "{0}/{1}: 期望有场景记录，实际缺失".format(scenario, row.get("tier"))
                )
                continue
            evidence = got.get("evidence") or {}
            row_problems = []
            if got.get("verdict") != row.get("verdict"):
                row_problems.append(
                    ".verdict: 期望 {0!r}，实际 {1!r}".format(
                        row.get("verdict"), got.get("verdict")
                    )
                )
            if got.get("triggers") != row.get("triggers"):
                row_problems.append(
                    ".triggers: 期望 {0!r}，实际 {1!r}".format(
                        row.get("triggers"), got.get("triggers")
                    )
                )
            if evidence.get("rule_ids") != row.get("rule_ids"):
                row_problems.append(
                    ".rule_ids: 期望 {0!r}，实际 {1!r}".format(
                        row.get("rule_ids"), evidence.get("rule_ids")
                    )
                )
            if evidence.get("obligations") != row.get("obligations"):
                row_problems.append(
                    ".obligations: 期望 {0!r}，实际 {1!r}".format(
                        row.get("obligations"), evidence.get("obligations")
                    )
                )
            if row_problems:
                for problem in row_problems:
                    mismatches.append(
                        "{0}/{1}/{2}/网络={3}{4}".format(
                            scenario, row.get("tier"), link_mode, network, problem
                        )
                    )
                continue
            matched += 1

    checked += len(pending_rows)
    for row in pending_rows:
        result = evaluate_tier(
            row.get("tier"), row.get("delivery_scenario"), row.get("link_mode"),
            row.get("network_interaction"), entries,
        )
        if result["verdict"] != row.get("verdict"):
            mismatches.append(
                "pending/tier={0}: 期望 {1!r}，实际 {2!r}".format(
                    row.get("tier"), row.get("verdict"), result["verdict"]
                )
            )
        else:
            matched += 1

    return {
        "truth_path": truth_path,
        "cases_checked": 1,
        "records_checked": checked,
        "matched": matched,
        "structural_problems": structural,
        "mismatches": mismatches,
    }


def format_scenario_report(report):
    lines = [
        "场景真值: {0}".format(report["truth_path"]),
        "判定表 {0} 行；命中 {1} 行".format(report["records_checked"], report["matched"]),
    ]
    for problem in report["structural_problems"]:
        lines.append("[FAIL] 结构: {0}".format(problem))
    for problem in report["mismatches"]:
        lines.append("[FAIL] 对账: {0}".format(problem))
    if not report["structural_problems"] and not report["mismatches"]:
        lines.append("[OK] 场景判定表与 curated 触发表投影逐行一致")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# M4 冲突分析对账
# ---------------------------------------------------------------------------


def _read_conflict_truth(data_dir):
    path = os.path.join(data_dir, "truth", "conflicts.json")
    if not os.path.isfile(path):
        raise UsageError(
            "冲突真值不存在，先运行 tools/gen_conflict_truth.py",
            path=path,
        )
    try:
        with io.open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (UnicodeDecodeError, ValueError) as exc:
        raise UsageError("冲突真值不是合法 UTF-8 JSON", path=path, reason=str(exc))
    if payload.get("format") != CONFLICT_TRUTH_FORMAT:
        raise UsageError(
            "冲突真值格式不受支持",
            path=path,
            got=payload.get("format"),
            expected=CONFLICT_TRUTH_FORMAT,
        )
    if payload.get("format_version") != contract.FORMAT_VERSION:
        raise UsageError(
            "冲突真值格式版本不受支持",
            path=path,
            got=payload.get("format_version"),
        )
    return payload, path


def _conflict_inventory(spdx_ids):
    """按给定 SPDX 值（可以是表达式）造一份合成 inventory，每行一条依赖。"""
    dependencies = []
    for index, spdx_id in enumerate(spdx_ids):
        dependencies.append({
            "package": "example-pkg-{0:03d}".format(index),
            "version": "1.0.0",
            "raw_license": spdx_id,
            "spdx_id": spdx_id,
            "confidence": "license_expression",
            "evidence": {"ruleset_version": "truth", "details_url": None},
        })
    return {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "dependencies": dependencies,
        "pending_confirmation": [],
        "parse_notes": [],
    }


def _conflict_pair_rows(payload):
    return {
        item["pair_id"]: (item["left"], item["right"], item["resolution"])
        for item in payload.get("dependency_conflicts") or []
    }


def verify_conflicts(data_dir, ruleset, spdx_dir=None):
    """M4 对账：真值（curated 冲突对表 + 独立朴素求值的投影）vs 运行时冲突引擎。

    三侧覆盖：已知冲突对全命中（含无向与未登记组合）、``OR``/``AND`` 求值、
    ``outbound = pending`` → 全部待定。返回 ``report``。
    """
    payload, truth_path = _read_conflict_truth(data_dir)
    structural = []
    text = io.open(truth_path, encoding="utf-8").read()
    if "observed_" in text:
        structural.append("冲突真值出现观测字段 observed_*（K26）")

    inputs = payload.get("inputs") or {}
    expect = payload.get("expect") or {}
    for key in ("pair_ids", "pair_sample_licenses", "tier_by_atom",
                "evaluation_expressions", "outbound_pending_value"):
        if not inputs.get(key):
            structural.append("冲突真值缺少 inputs.{0}".format(key))
    for key in ("pairs", "evaluations", "outbound_pending"):
        if not expect.get(key):
            structural.append("冲突真值缺少 expect.{0}".format(key))
    if "uncovered_pairs" not in expect:
        structural.append("冲突真值缺少 expect.uncovered_pairs")
    if not inputs.get("pair_sample_licenses") or not inputs.get("evaluation_expressions"):
        return {
            "truth_path": truth_path,
            "cases_checked": 1,
            "records_checked": 0,
            "matched": 0,
            "structural_problems": structural,
            "mismatches": [],
        }

    index, license_list_version = load_context(spdx_dir)

    # 档位真值（输入）必须与规则包一致：否则下面的对账是在比两份不同的前提。
    atoms = sorted(inputs.get("tier_by_atom") or {})
    tier_snapshot = profile_ids(atoms, ruleset, index, license_list_version)
    actual_tiers = {
        item["spdx_id"]: item.get("tier") for item in tier_snapshot.get("profiles") or []
    }
    for atom in atoms:
        if actual_tiers.get(atom) != inputs["tier_by_atom"][atom]:
            structural.append(
                "档位不一致：{0} 规则包 {1!r}，真值按 {2!r} 记账".format(
                    atom, actual_tiers.get(atom), inputs["tier_by_atom"][atom]
                )
            )

    mismatches = []
    matched = 0
    checked = 0
    outbound = inputs["outbound_pending_value"]

    # ① 已知冲突对：样本许可证一次性进清单，逐条对账（含无向与未登记组合）。
    sample = list(inputs["pair_sample_licenses"])
    inventory = _conflict_inventory(sample)
    result = build_conflicts(
        inventory, tier_snapshot, ruleset, outbound, spdx_index=index
    )
    for record in result["dependency_conflicts"] + result["outbound_conflicts"]:
        if tuple(record) != contract.CONFLICT_FIELDS:
            structural.append(
                "冲突记录字段序与 contract.CONFLICT_FIELDS 不一致：{0}".format(
                    tuple(record)
                )
            )
            break

    actual_pairs = _conflict_pair_rows(result)
    expected_pairs = {
        item["pair_id"]: (item["left"], item["right"], item["resolution"])
        for item in expect["pairs"]
    }
    for pair_id in sorted(set(actual_pairs) | set(expected_pairs)):
        checked += 1
        want = expected_pairs.get(pair_id)
        got = actual_pairs.get(pair_id)
        if want is None:
            mismatches.append("{0}: 实际命中冲突对，真值未登记".format(pair_id))
            continue
        if got is None:
            mismatches.append("{0}: 期望命中冲突对，实际缺失".format(pair_id))
            continue
        if got != want:
            mismatches.append(
                "{0}: 期望 {1!r}，实际 {2!r}".format(pair_id, want, got)
            )
            continue
        matched += 1

    # 无向：把清单顺序倒过来（left/right 互换）必须给出同一组结论。
    reversed_result = build_conflicts(
        _conflict_inventory(list(reversed(sample))), tier_snapshot, ruleset, outbound,
        spdx_index=index,
    )
    checked += 1
    if _conflict_pair_rows(reversed_result) != actual_pairs:
        mismatches.append("冲突对匹配不是无向的：倒序清单给出了不同结论")
    else:
        matched += 1

    # 未登记组合：覆盖度必须与真值一致（多算/少算都是错的）。
    checked += 1
    uncovered = result["uncovered_pairs"]
    if [list(item) for item in uncovered.get("items") or []] != [
        list(item) for item in expect["uncovered_pairs"]
    ] or uncovered.get("count") != len(expect["uncovered_pairs"]):
        mismatches.append(
            "uncovered_pairs: 期望 {0!r}，实际 {1!r}".format(
                expect["uncovered_pairs"], uncovered.get("items")
            )
        )
    else:
        matched += 1

    # ② 表达式求值（OR 最宽松 / AND 最严格 / 嵌套 / WITH / 未覆盖档位）。
    expressions = list(inputs["evaluation_expressions"])
    evaluation_result = build_conflicts(
        _conflict_inventory(expressions), tier_snapshot, ruleset, outbound,
        spdx_index=index,
    )
    evaluated = {
        item["expression"]: item
        for item in evaluation_result["expression_evaluations"]
        if item.get("source") == "dependency"
    }
    for want in expect["evaluations"]:
        checked += 1
        got = evaluated.get(want["expression"])
        if got is None:
            mismatches.append("{0}: 期望有求值记录，实际缺失".format(want["expression"]))
            continue
        problems = []
        for key in ("operator", "atoms", "selected", "tier", "resolved", "exceptions"):
            if got.get(key) != want.get(key):
                problems.append(
                    ".{0}: 期望 {1!r}，实际 {2!r}".format(key, want.get(key), got.get(key))
                )
        if problems:
            mismatches.append(
                "{0}{1}".format(want["expression"], "".join(problems))
            )
            continue
        matched += 1
    for item in evaluated.values():
        if len(item.get("atoms") or []) < 2:
            structural.append(
                "单原子记录不该进 expression_evaluations：{0}".format(item["expression"])
            )
            break

    # ③ outbound = pending → 全部条目待定，文案固定，且都进待确认列表。
    pending_expect = expect["outbound_pending"]
    rows = evaluation_result["outbound_conflicts"]
    if not rows:
        structural.append("outbound = pending 时没有任何「依赖 × outbound」条目")
    pending_ids = {item["pair_id"] for item in evaluation_result["pending_confirmation"]}
    for record in rows:
        checked += 1
        if record["resolution"] != pending_expect["resolution"]:
            mismatches.append(
                "{0}.resolution: 期望 {1!r}，实际 {2!r}".format(
                    record["pair_id"], pending_expect["resolution"], record["resolution"]
                )
            )
            continue
        if record["basis"] != pending_expect["basis"]:
            mismatches.append(
                "{0}.basis: 期望 {1!r}，实际 {2!r}".format(
                    record["pair_id"], pending_expect["basis"], record["basis"]
                )
            )
            continue
        if record["pair_id"] not in pending_ids:
            mismatches.append("{0}: 待定条目未进待确认列表".format(record["pair_id"]))
            continue
        matched += 1

    return {
        "truth_path": truth_path,
        "cases_checked": 1,
        "records_checked": checked,
        "matched": matched,
        "structural_problems": structural,
        "mismatches": mismatches,
    }


def format_conflict_report(report):
    lines = [
        "冲突真值: {0}".format(report["truth_path"]),
        "条目 {0} 条；命中 {1} 条".format(report["records_checked"], report["matched"]),
    ]
    for problem in report["structural_problems"]:
        lines.append("[FAIL] 结构: {0}".format(problem))
    for problem in report["mismatches"]:
        lines.append("[FAIL] 对账: {0}".format(problem))
    if not report["structural_problems"] and not report["mismatches"]:
        lines.append("[OK] 冲突判定与 curated 冲突对表投影逐条一致")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# M5 处置分级对账
# ---------------------------------------------------------------------------


def _read_actions_truth(data_dir):
    path = os.path.join(data_dir, "truth", "actions.json")
    if not os.path.isfile(path):
        raise UsageError(
            "处置真值不存在，先运行 tools/gen_action_truth.py",
            path=path,
        )
    try:
        with io.open(path, "r", encoding="utf-8") as stream:
            payload = json.load(stream)
    except (UnicodeDecodeError, ValueError) as exc:
        raise UsageError("处置真值不是合法 UTF-8 JSON", path=path, reason=str(exc))
    if payload.get("format") != ACTIONS_TRUTH_FORMAT:
        raise UsageError(
            "处置真值格式不受支持",
            path=path,
            got=payload.get("format"),
            expected=ACTIONS_TRUTH_FORMAT,
        )
    if payload.get("format_version") != contract.FORMAT_VERSION:
        raise UsageError(
            "处置真值格式版本不受支持",
            path=path,
            got=payload.get("format_version"),
        )
    return payload, path


def _facts_of(row):
    return {key: row.get(key) for key in FACT_FIELDS}


def _facts_text(facts):
    return "义务轴 {{{0}}} / conflict={1} / pair_conflict={2} / link_mode={3} / verdict={4}".format(
        ",".join(facts.get("axes") or []),
        facts.get("conflict"),
        facts.get("pair_conflict"),
        facts.get("link_mode"),
        facts.get("verdict"),
    )


def verify_actions(data_dir, ruleset, spdx_dir=None):
    """M5 对账：真值（curated 决策表的投影）vs 运行时处置分级（纯查表）。

    三侧覆盖：① 可达事实域里每一组「确定输入」的处置级别与命中条目；
    ② 四级处置各至少一个植入样本；③ 义务轴映射 / 可用条目集合与真值登记一致。
    返回 ``report``。
    """
    payload, truth_path = _read_actions_truth(data_dir)
    structural = []
    text = io.open(truth_path, encoding="utf-8").read()
    if "observed_" in text:
        structural.append("处置真值出现观测字段 observed_*（K26）")

    inputs = payload.get("inputs") or {}
    expect = payload.get("expect") or {}
    matrix = expect.get("matrix") or []
    levels = expect.get("levels") or {}
    for key in ("rule_ids", "obligation_axes", "reachable_axes", "fact_domain"):
        if not inputs.get(key):
            structural.append("处置真值缺少 inputs.{0}".format(key))
    if not matrix:
        structural.append("处置真值缺少 expect.matrix")
    missing_levels = [
        level for level in contract.ACTION_LEVELS if level not in levels
    ]
    if missing_levels:
        structural.append(
            "每级处置至少一个真值样本，缺：{0}".format(", ".join(missing_levels))
        )
    if (expect.get("coverage") or {}).get("uncovered"):
        structural.append("决策表在真值里仍留有未覆盖的确定输入")
    if not inputs.get("rule_ids") or not matrix:
        return {
            "truth_path": truth_path,
            "cases_checked": 1,
            "records_checked": 0,
            "matched": 0,
            "structural_problems": structural,
            "mismatches": [],
        }

    # 规则包与真值必须建立在同一份义务轴映射上，否则下面的对账是在比两份不同的前提。
    document = ruleset.documents.get(ACTION_RULE_FILE)
    axes = obligation_axes(document)
    if axes != inputs.get("obligation_axes"):
        structural.append("规则包 obligation_axes 与真值登记不一致")
    rules = usable_rules(ruleset.entries(ACTION_RULE_FILE), axes)
    actual_ids = [rule.get("id") for rule in rules]
    if actual_ids != list(inputs["rule_ids"]):
        structural.append(
            "可用决策条目与真值登记不一致：期望 {0}，实际 {1}".format(
                inputs["rule_ids"], actual_ids
            )
        )

    mismatches = []
    matched = 0
    checked = 0
    for row in matrix:
        checked += 1
        facts = _facts_of(row)
        rule = match_rule(facts, rules)
        level = rule.get("level") if rule is not None else None
        rule_id = rule.get("id") if rule is not None else None
        if level != row.get("level") or rule_id != row.get("rule_id"):
            mismatches.append(
                "{0}: 期望 {1}/{2}，实际 {3}/{4}".format(
                    _facts_text(facts), row.get("level"), row.get("rule_id"), level, rule_id
                )
            )
            continue
        matched += 1

    for level in sorted(levels):
        checked += 1
        sample = levels[level]
        facts = _facts_of(sample)
        rule = match_rule(facts, rules)
        got_level = rule.get("level") if rule is not None else None
        got_id = rule.get("id") if rule is not None else None
        if got_level != level or got_id != sample.get("rule_id"):
            mismatches.append(
                "样本 {0}（{1}）：期望 {2}，实际 {3}".format(
                    level, _facts_text(facts), sample.get("rule_id"), got_id
                )
            )
            continue
        matched += 1

    return {
        "truth_path": truth_path,
        "cases_checked": 1,
        "records_checked": checked,
        "matched": matched,
        "structural_problems": structural,
        "mismatches": mismatches,
    }


def format_actions_report(report):
    lines = [
        "处置真值: {0}".format(report["truth_path"]),
        "事实组合 {0} 组（含四级样本）；命中 {1} 组".format(
            report["records_checked"], report["matched"]
        ),
    ]
    for problem in report["structural_problems"]:
        lines.append("[FAIL] 结构: {0}".format(problem))
    for problem in report["mismatches"]:
        lines.append("[FAIL] 对账: {0}".format(problem))
    if not report["structural_problems"] and not report["mismatches"]:
        lines.append("[OK] 处置分级与 curated 决策表投影逐条一致")
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

    implemented = IMPLEMENTED_SUITES
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
        elif suite == "m2":
            report = verify_profile(data_dir, ruleset, spdx_dir=spdx_dir)
            results.append({
                "suite": "m2",
                "name": "画像矩阵与真值对账",
                "cases": report["records_checked"],
                "records": report["records_checked"],
                "matched": report["matched"],
                "scores": {},
                "ok": not report["structural_problems"] and not report["mismatches"],
                "failures": report["structural_problems"] + report["mismatches"],
            })
            failures.extend(report["mismatches"])
        elif suite == "m3":
            report = verify_scenario(data_dir, ruleset, spdx_dir=spdx_dir)
            results.append({
                "suite": "m3",
                "name": "场景判定表与真值对账",
                "cases": report["records_checked"],
                "records": report["records_checked"],
                "matched": report["matched"],
                "scores": {},
                "ok": not report["structural_problems"] and not report["mismatches"],
                "failures": report["structural_problems"] + report["mismatches"],
            })
            failures.extend(report["mismatches"])
        elif suite == "m4":
            report = verify_conflicts(data_dir, ruleset, spdx_dir=spdx_dir)
            results.append({
                "suite": "m4",
                "name": "冲突判定与真值对账",
                "cases": report["records_checked"],
                "records": report["records_checked"],
                "matched": report["matched"],
                "scores": {},
                "ok": not report["structural_problems"] and not report["mismatches"],
                "failures": report["structural_problems"] + report["mismatches"],
            })
            failures.extend(report["mismatches"])
        elif suite == "m5":
            report = verify_actions(data_dir, ruleset, spdx_dir=spdx_dir)
            results.append({
                "suite": "m5",
                "name": "处置分级与真值对账",
                "cases": report["records_checked"],
                "records": report["records_checked"],
                "matched": report["matched"],
                "scores": {},
                "ok": not report["structural_problems"] and not report["mismatches"],
                "failures": report["structural_problems"] + report["mismatches"],
            })
            failures.extend(report["mismatches"])

    exit_code = 0 if all(item["ok"] for item in results) else 1
    return {"suites": results, "failures": failures}, exit_code


def format_bench_report(report):
    lines = []
    for suite in report["suites"]:
        mark = "OK" if suite["ok"] else "FAIL"
        scores = suite.get("scores") or {}
        if suite["suite"] == "m1":
            lines.append(
                "[{0}] {1} {2}：用例 {3} 个 / 记录 {4} 条 / 命中 {5} 条 / F1 {6}".format(
                    mark, suite["suite"], suite["name"], suite["cases"],
                    suite["records"], suite["matched"], scores.get("f1"),
                )
            )
        else:
            lines.append(
                "[{0}] {1} {2}：条目 {3} 条 / 命中 {4} 条".format(
                    mark, suite["suite"], suite["name"],
                    suite["records"], suite["matched"],
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
    "IMPLEMENTED_SUITES",
    "format_actions_report",
    "format_bench_report",
    "format_conflict_report",
    "format_profile_report",
    "format_scenario_report",
    "format_verify_report",
    "run_bench",
    "verify_actions",
    "verify_conflicts",
    "verify_data",
    "verify_profile",
    "verify_scenario",
]
