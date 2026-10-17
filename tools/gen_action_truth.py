#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""处置真值生成器（M5）：``references/curated/action-rules.json`` → ``data/truth/actions.json``。

纪律（plan/04 §5.2 / K26）：

- 真值是**规则表的投影**，不是引擎输出回填。本脚本不 import 生产处置引擎
  （``licaudit.assess.action``），也不 import 生产场景引擎。
- 只存输入与期望：输入是决策表、义务轴映射，以及由 curated 场景触发表推出的
  **可达事实域**；期望是每一组「确定输入」应该得到的处置级别与命中的规则条目。
- 谓词匹配用本文件内的**独立朴素实现**，与引擎分写（避免同一份代码自证）。
- 表结构两道门与 ``tools/gen_ruleset.py`` 同口径但独立实现：**覆盖完备**
  （每一组确定输入都有结论）+ **无死规则**。
- 每级处置至少一个植入真值（``expect.levels``）：四级枚举都有人守。
- ``--check`` 两层：冻结产物形态正确 + 重生成逐字节一致。

用法::

    py -3.12 -X utf8 tools/gen_action_truth.py
    py -3.12 -X utf8 tools/gen_action_truth.py --check
"""

import argparse
import io
import json
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from licaudit import contract  # noqa: E402

CURATED_DIR = os.path.join(REPO_ROOT, "references", "curated")
SPDX_DIR = os.path.join(REPO_ROOT, "references", "spdx")
DATA_DIR = os.path.join(REPO_ROOT, "data")
TRUTH_FILE = os.path.join(DATA_DIR, "truth", "actions.json")

TRUTH_FORMAT = "licaudit-actions-truth"

# 决策表只看「确定输入」：``pending`` 一类不确定情形由引擎挡在待人工确认，
# 因此事实域不含 pending，真值也不为它记账。
FACT_CONFLICTS = ("compatible", "incompatible")
FACT_PAIR_CONFLICTS = ("none", "incompatible")
FACT_VERDICTS = ("triggered", "not_triggered")

PREDICATES = ("axes_any", "axes_only", "conflict", "pair_conflict", "link_mode", "verdict")


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------


def read_json(path):
    with io.open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def dumps(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


def write_text_atomic(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    handle, tmp_path = tempfile.mkstemp(prefix=".licaudit-", suffix=".tmp", dir=directory)
    try:
        with io.open(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


# ---------------------------------------------------------------------------
# 独立朴素的锚点 / 用法表校验
# ---------------------------------------------------------------------------


def flatten_ws(text):
    return " ".join(text.split())


def quote_is_locatable(spdx_root, reference, quote):
    if not isinstance(reference, str) or "#" not in reference:
        return False
    if not isinstance(quote, str) or not quote.strip():
        return False
    relative = reference.split("#", 1)[0]
    path = os.path.join(spdx_root, relative.replace("/", os.sep))
    if not os.path.isfile(path):
        return False
    payload = read_json(path)
    text = payload.get("licenseText") or payload.get("licenseExceptionText") or ""
    return flatten_ws(quote) in flatten_ws(text)


def obligation_axes(curated, known_obligations):
    raw = curated.get("obligation_axes")
    if not isinstance(raw, dict):
        return None
    mapped = {}
    for obligation in known_obligations:
        axis = raw.get(obligation)
        if not isinstance(axis, str) or not axis.strip():
            return None
        mapped[obligation] = axis
    return mapped


def usable_rules(curated, spdx_root, axes):
    """可参与分级的决策表条目（与引擎同口径的朴素版）。"""
    if not axes:
        return [], []
    usable = []
    dropped = []
    known_axes = set(axes.values())
    for entry in curated.get("entries", []):
        rule_id = entry.get("id")
        ok = isinstance(rule_id, str) and bool(rule_id.strip())
        ok = ok and entry.get("level") in contract.ACTION_LEVELS
        ok = ok and isinstance(entry.get("basis"), str) and bool(entry["basis"].strip())
        when = entry.get("when")
        ok = ok and isinstance(when, dict) and bool(when)
        if ok:
            for key in sorted(when):
                if key not in PREDICATES:
                    ok = False
                    break
                values = when[key]
                if not isinstance(values, list) or not values:
                    ok = False
                    break
                if key in ("axes_any", "axes_only"):
                    for item in values:
                        names = item if isinstance(item, list) else [item]
                        if any(name not in known_axes for name in names):
                            ok = False
                            break
        ok = ok and entry.get("verified") is True and bool(entry.get("checked_on"))
        anchor = entry.get("anchor") or {}
        ok = ok and quote_is_locatable(spdx_root, anchor.get("ref"), anchor.get("quote"))
        if ok:
            usable.append(entry)
        else:
            dropped.append(rule_id)
    return usable, dropped


def reachable_axis_sets(curated_triggers, axes):
    """由 curated 场景触发表推出可达义务轴集合（按档位分组求并集闭包）。"""
    by_tier = {}
    for entry in curated_triggers.get("entries", []):
        tier = entry.get("tier")
        if tier not in contract.TIERS:
            continue
        entry_axes = frozenset(
            axes[item] for item in entry.get("obligations") or [] if item in axes
        )
        by_tier.setdefault(tier, []).append(entry_axes)
    reachable = set()
    for tier in sorted(by_tier):
        subsets = [frozenset()]
        for entry_axes in by_tier[tier]:
            subsets = subsets + [item | entry_axes for item in subsets]
        reachable.update(subsets)
    reachable.add(frozenset())
    return sorted(reachable, key=lambda item: (len(item), sorted(item)))


# ---------------------------------------------------------------------------
# 独立朴素的谓词匹配
# ---------------------------------------------------------------------------


def matches_when(when, facts):
    for key in sorted(when):
        wanted = when[key]
        if key == "axes_any":
            if not (set(facts["axes"]) & set(wanted)):
                return False
        elif key == "axes_only":
            if set(facts["axes"]) not in [set(item) for item in wanted]:
                return False
        elif facts.get(key) not in wanted:
            return False
    return True


def first_match(rules, facts):
    for rule in rules:
        if matches_when(rule["when"], facts):
            return rule
    return None


def fact_space(axis_sets):
    space = []
    for axes_set in axis_sets:
        for conflict in FACT_CONFLICTS:
            for pair_conflict in FACT_PAIR_CONFLICTS:
                for link_mode in contract.LINK_MODES:
                    for verdict in FACT_VERDICTS:
                        space.append({
                            "axes": sorted(axes_set),
                            "conflict": conflict,
                            "pair_conflict": pair_conflict,
                            "link_mode": link_mode,
                            "verdict": verdict,
                        })
    return space


# ---------------------------------------------------------------------------
# 真值构建
# ---------------------------------------------------------------------------


def build_truth():
    curated = read_json(os.path.join(CURATED_DIR, "action-rules.json"))
    curated_triggers = read_json(os.path.join(CURATED_DIR, "scenario-triggers.json"))
    licenses = read_json(os.path.join(SPDX_DIR, "licenses.json"))
    snapshot_manifest_path = os.path.join(SPDX_DIR, "manifest.json")
    snapshot_manifest = (
        read_json(snapshot_manifest_path) if os.path.isfile(snapshot_manifest_path) else {}
    )

    axes = obligation_axes(curated, contract.OBLIGATIONS)
    if not axes:
        raise SystemExit("curated/action-rules.json 的 obligation_axes 不完整")
    rules, dropped = usable_rules(curated, SPDX_DIR, axes)
    if not rules:
        raise SystemExit("curated/action-rules.json 没有任何可用条目")

    axis_sets = reachable_axis_sets(curated_triggers, axes)
    space = fact_space(axis_sets)

    matrix = []
    uncovered = []
    for facts in space:
        rule = first_match(rules, facts)
        row = dict(facts)
        row["level"] = rule["level"] if rule is not None else None
        row["rule_id"] = rule["id"] if rule is not None else None
        matrix.append(row)
        if rule is None:
            uncovered.append(dict(facts))

    if uncovered:
        raise SystemExit(
            "决策表未覆盖 {0} 组确定输入，例如 {1}".format(
                len(uncovered), json.dumps(uncovered[0], ensure_ascii=False)
            )
        )
    dead = [
        rule["id"] for rule in rules
        if not any(row["rule_id"] == rule["id"] for row in matrix)
    ]
    if dead:
        raise SystemExit("决策表存在死规则：{0}".format(", ".join(sorted(set(dead)))))

    # 每级处置至少一个植入真值（四级枚举都有人守）。
    levels = {}
    for level in contract.ACTION_LEVELS:
        sample = next((row for row in matrix if row["level"] == level), None)
        if sample is None:
            raise SystemExit("决策表未覆盖处置级别：{0}".format(level))
        levels[level] = {
            "rule_id": sample["rule_id"],
            "axes": sample["axes"],
            "conflict": sample["conflict"],
            "pair_conflict": sample["pair_conflict"],
            "link_mode": sample["link_mode"],
            "verdict": sample["verdict"],
        }

    return {
        "format": TRUTH_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "inputs": {
            "ruleset_source": "references/curated/action-rules.json",
            "triggers_source": "references/curated/scenario-triggers.json",
            "license_list_version": licenses.get("licenseListVersion"),
            "captured_on": snapshot_manifest.get("captured_on"),
            "level_order": list(contract.ACTION_LEVELS),
            "rule_ids": [rule["id"] for rule in rules],
            "dropped_rule_ids": sorted(item for item in dropped if item),
            "obligation_axes": {item: axes[item] for item in contract.OBLIGATIONS},
            "reachable_axes": [sorted(item) for item in axis_sets],
            "fact_domain": {
                "conflict": list(FACT_CONFLICTS),
                "pair_conflict": list(FACT_PAIR_CONFLICTS),
                "link_mode": list(contract.LINK_MODES),
                "verdict": list(FACT_VERDICTS),
            },
        },
        "expect": {
            "matrix": matrix,
            "levels": levels,
            "coverage": {
                "rows": len(matrix),
                "uncovered": len(uncovered),
                "dead_rules": sorted(set(dead)),
            },
        },
    }


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------


def check_against(path=None):
    path = path or TRUTH_FILE
    problems = []
    if not os.path.isfile(path):
        return ["缺少 {0}".format(path)]

    frozen = read_json(path)
    if frozen.get("format") != TRUTH_FORMAT:
        problems.append("format 不是 {0}".format(TRUTH_FORMAT))
    if frozen.get("format_version") != contract.FORMAT_VERSION:
        problems.append("format_version 与 contract.FORMAT_VERSION 不一致")
    inputs = frozen.get("inputs") or {}
    for key in ("rule_ids", "obligation_axes", "reachable_axes", "fact_domain"):
        if not inputs.get(key):
            problems.append("缺少 inputs.{0}".format(key))
    expect = frozen.get("expect") or {}
    if not expect.get("matrix"):
        problems.append("缺少 expect.matrix")
    if not expect.get("levels"):
        problems.append("缺少 expect.levels（四级处置分支无人守）")
    levels = expect.get("levels") or {}
    missing_levels = [
        level for level in contract.ACTION_LEVELS if level not in levels
    ]
    if missing_levels:
        problems.append("每级处置至少一个真值样本：缺 {0}".format(", ".join(missing_levels)))
    if "coverage" not in expect:
        problems.append("缺少 expect.coverage")

    text = io.open(path, encoding="utf-8").read()
    if "observed_" in text:
        problems.append("真值出现观测字段 observed_*（K26）")

    regenerated = dumps(build_truth())
    if text != regenerated:
        problems.append("重生成结果与冻结真值不一致（首个差异偏移 {0}）".format(
            _first_difference(text, regenerated)
        ))
    return problems


def _first_difference(left, right):
    limit = min(len(left), len(right))
    for index in range(limit):
        if left[index] != right[index]:
            return index
    return limit


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="gen_action_truth",
        description="由 curated 处置决策表推导 M5 处置真值（禁手改）",
    )
    parser.add_argument("--check", action="store_true",
                        help="校验冻结真值（形态 + 重生成逐字节一致）")
    parser.add_argument("--out", default=TRUTH_FILE, help="输出文件")
    args = parser.parse_args(argv)

    target = os.path.abspath(args.out)

    if args.check:
        problems = check_against(target)
        if problems:
            for problem in problems:
                sys.stdout.write("[FAIL] {0}\n".format(problem))
            return 1
        sys.stdout.write("[OK] 处置真值与重生成结果逐字节一致：{0}\n".format(target))
        return 0

    payload = build_truth()
    write_text_atomic(target, dumps(payload))
    expect = payload["expect"]
    sys.stdout.write(
        "[OK] 处置真值已生成：{0}；决策表条目 {1} 条；可达事实组合 {2} 组；"
        "四级样本 {3} 级\n".format(
            target,
            len(payload["inputs"]["rule_ids"]),
            expect["coverage"]["rows"],
            len(expect["levels"]),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
