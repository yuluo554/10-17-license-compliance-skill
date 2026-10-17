#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""场景真值生成器（M3）：``references/curated/scenario-triggers.json`` → ``data/truth/scenario.json``。

纪律（plan/04 §5.2 / K26）：

- 真值是**规则表的投影**，不是引擎输出回填。本脚本不 import 生产场景引擎。
- 只存输入与期望：输入是「八场景 × 链接方式 × 档位 × 网络交互」的判定表，
  期望是三态结论 + 触发名 + 命中规则 id + 义务项。
- 「规则是否生效」用**独立的朴素门槛**判断（verified / checked_on / 锚点 quote 可定位），
  与 ``tools/gen_ruleset.py`` 的实现分写，避免同一份代码自证。
- 真值行同时登记 ``delivery`` 与匹配用的 ``delivery_scenario``：
  链接方式轴场景（static-link 等）取代表性交付形态 ``binary``，由 ``inputs`` 说明。
- ``--check`` 两层：冻结产物形态正确 + 重生成逐字节一致。

用法::

    py -3.12 -X utf8 tools/gen_scenario_truth.py
    py -3.12 -X utf8 tools/gen_scenario_truth.py --check
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
TRUTH_FILE = os.path.join(DATA_DIR, "truth", "scenario.json")

TRUTH_FORMAT = "licaudit-scenario-truth"

# 链接方式轴场景只接受自己的链接方式；其余场景默认 none 并允许细化。
_LINK_SCENARIOS = {
    "static-link": "static",
    "dynamic-link": "dynamic",
    "separate-process": "separate-process",
}

# 链接方式轴场景的代表性交付形态：判定表要给出可复算的 ``(delivery, link_mode)``。
_LINK_SCENARIO_DELIVERY = {
    "static-link": "binary",
    "dynamic-link": "binary",
    "separate-process": "binary",
}

# 交付形态 → 触发表第一维场景（与 ``assess/scenario.py`` 同口径，独立写在生成器里）。
_DELIVERY_SCENARIO = {
    "internal": "internal",
    "binary": "distribute-binary",
    "source": "distribute-source",
    "saas": "saas",
    "container": "container-image",
}

NETWORK_VALUES = (True, False)

# 必答网络交互的场景（与 assess/scenario.py 同口径，独立写在生成器里）。
_NETWORK_REQUIRED = ("saas",)

PENDING = "pending_confirmation"
REASON_NETWORK_CONTRADICTION = "network_interaction_contradicts_scenario"


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
# 独立朴素门槛与匹配
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


def entry_is_usable(entry, spdx_root):
    """仿 ``gen_ruleset.build_scenario_triggers`` 的收录规则，独立实现。"""
    if entry.get("verified") is not True:
        return False
    if not entry.get("checked_on"):
        return False
    if entry.get("tier") not in contract.TIERS:
        return False
    scenarios = entry.get("scenarios") or []
    link_modes = entry.get("link_modes") or []
    if not scenarios or not link_modes:
        return False
    if any(item not in contract.SCENARIO_IDS for item in scenarios):
        return False
    if any(item not in contract.LINK_MODES for item in link_modes):
        return False
    obligations = entry.get("obligations")
    if not isinstance(obligations, list):
        return False
    if any(item not in contract.OBLIGATIONS for item in obligations):
        return False
    if not isinstance(entry.get("trigger"), str) or not entry["trigger"].strip():
        return False
    if "network_interaction" in entry and not isinstance(
        entry.get("network_interaction"), bool
    ):
        return False
    anchor = entry.get("anchor") or {}
    return quote_is_locatable(spdx_root, anchor.get("ref"), anchor.get("quote"))


def matches(entry, tier, delivery_scenario, link_mode, network_interaction):
    if entry["tier"] != tier:
        return False
    if delivery_scenario not in entry["scenarios"]:
        return False
    if link_mode not in entry["link_modes"]:
        return False
    if "network_interaction" in entry:
        return entry["network_interaction"] is True and network_interaction is True
    return True


def canonical_obligations(obligations):
    wanted = set(obligations or [])
    return [item for item in contract.OBLIGATIONS if item in wanted]


def expected_for(entries, tier, delivery_scenario, link_mode, network_interaction):
    if delivery_scenario in _NETWORK_REQUIRED and network_interaction is False:
        # SaaS 本身就是「通过网络向用户提供服务」；回答「无网络交互」是矛盾（K14）。
        return {
            "verdict": PENDING,
            "triggers": [],
            "rule_ids": [],
            "obligations": [],
        }
    hits = [
        entry for entry in entries
        if matches(entry, tier, delivery_scenario, link_mode, network_interaction)
    ]
    if not hits:
        return {
            "verdict": "not_triggered",
            "triggers": [],
            "rule_ids": [],
            "obligations": [],
        }
    triggers = set()
    rule_ids = set()
    obligations = []
    for entry in hits:
        triggers.add(entry["trigger"])
        if entry.get("id"):
            rule_ids.add(entry["id"])
        obligations.extend(entry.get("obligations") or [])
    return {
        "verdict": "triggered",
        "triggers": sorted(triggers),
        "rule_ids": sorted(rule_ids),
        "obligations": canonical_obligations(obligations),
    }


def axes_for(scenario):
    """场景 ID → ``(delivery, [link_mode...])``；链接方式轴场景取代表性交付形态。"""
    axes = contract.SCENARIO_AXES[scenario]
    delivery = axes.get("delivery")
    if scenario in _LINK_SCENARIOS:
        delivery = _LINK_SCENARIO_DELIVERY[scenario]
        return delivery, [_LINK_SCENARIOS[scenario]]
    return delivery, list(contract.LINK_MODES)


def tier_samples(curated_tiers):
    """每个档位取一个代表性 license_id（按 curated 书写顺序，确定性）。"""
    samples = {}
    for entry in curated_tiers.get("entries", []):
        tier = entry.get("tier")
        if tier in contract.TIERS and tier not in samples:
            samples[tier] = entry.get("license_id")
    missing = [tier for tier in contract.TIERS if tier not in samples]
    if missing:
        raise SystemExit("curated/tiers.json 缺少档位样本：{0}".format(", ".join(missing)))
    return samples


# ---------------------------------------------------------------------------
# 真值构建
# ---------------------------------------------------------------------------


def build_truth():
    curated = read_json(os.path.join(CURATED_DIR, "scenario-triggers.json"))
    curated_tiers = read_json(os.path.join(CURATED_DIR, "tiers.json"))
    licenses = read_json(os.path.join(SPDX_DIR, "licenses.json"))

    usable = [
        entry for entry in curated.get("entries", [])
        if entry_is_usable(entry, SPDX_DIR)
    ]
    dropped = [
        entry.get("id") for entry in curated.get("entries", [])
        if not entry_is_usable(entry, SPDX_DIR)
    ]
    if not usable:
        raise SystemExit("curated/scenario-triggers.json 没有任何可用条目")

    matrix = []
    for scenario in contract.SCENARIO_IDS:
        delivery, link_modes = axes_for(scenario)
        match_scenario = _DELIVERY_SCENARIO[delivery]
        for link_mode in link_modes:
            for tier in contract.TIERS:
                for network in NETWORK_VALUES:
                    expectation = expected_for(
                        usable, tier, match_scenario, link_mode, network
                    )
                    matrix.append({
                        "scenario": scenario,
                        "delivery": delivery,
                        "delivery_scenario": match_scenario,
                        "link_mode": link_mode,
                        "tier": tier,
                        "network_interaction": network,
                        "verdict": expectation["verdict"],
                        "triggers": expectation["triggers"],
                        "rule_ids": expectation["rule_ids"],
                        "obligations": expectation["obligations"],
                    })
    matrix.sort(key=lambda item: (
        contract.SCENARIO_IDS.index(item["scenario"]),
        contract.LINK_MODES.index(item["link_mode"]),
        contract.TIERS.index(item["tier"]),
        0 if item["network_interaction"] else 1,
    ))

    return {
        "format": TRUTH_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "inputs": {
            "ruleset_source": "references/curated/scenario-triggers.json",
            "tiers_source": "references/curated/tiers.json",
            "license_list_version": licenses.get("licenseListVersion"),
            "scenarios": list(contract.SCENARIO_IDS),
            "link_modes": list(contract.LINK_MODES),
            "tiers": list(contract.TIERS),
            "network_interaction_values": [True, False],
            "link_scenario_delivery": dict(_LINK_SCENARIO_DELIVERY),
            "tier_samples": tier_samples(curated_tiers),
            "enabled_rule_ids": sorted(entry["id"] for entry in usable),
            "dropped_rule_ids": sorted(item for item in dropped if item),
        },
        "expect": {
            "matrix": matrix,
            "pending": [
                {
                    "tier": None,
                    "scenario": "saas",
                    "delivery": "saas",
                    "delivery_scenario": "saas",
                    "link_mode": "none",
                    "network_interaction": True,
                    "verdict": contract.PENDING,
                    "triggers": [],
                    "rule_ids": [],
                    "obligations": [],
                },
            ],
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
    if not inputs.get("enabled_rule_ids"):
        problems.append("缺少 inputs.enabled_rule_ids")
    if not inputs.get("tier_samples"):
        problems.append("缺少 inputs.tier_samples")
    expect = frozen.get("expect") or {}
    if not expect.get("matrix"):
        problems.append("缺少 expect.matrix")
    if not expect.get("pending"):
        problems.append("缺少 expect.pending（tier: null 分支无人守）")

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
        prog="gen_scenario_truth",
        description="由 curated 场景触发表推导 M3 场景真值（禁手改）",
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
        sys.stdout.write("[OK] 场景真值与重生成结果逐字节一致：{0}\n".format(target))
        return 0

    payload = build_truth()
    write_text_atomic(target, dumps(payload))
    sys.stdout.write(
        "[OK] 场景真值已生成：{0}；判定表 {1} 行；可用规则 {2} 条\n".format(
            target,
            len(payload["expect"]["matrix"]),
            len(payload["inputs"]["enabled_rule_ids"]),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
