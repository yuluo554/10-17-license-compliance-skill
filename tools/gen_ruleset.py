#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""规则包生成器：curated（人工核对表）+ SPDX 快照 → ``references/ruleset/``。

输入（唯一手写数据）：

- ``references/curated/tiers.json``     —— 档位 + 义务 + 条款锚点
- ``references/curated/trove-map.json``  —— trove classifier → SPDX ID
- ``references/curated/scenario-triggers.json``（M3 才有内容，可缺）
- ``references/curated/conflict-pairs.json``（M4 才有内容，可缺）
- ``references/curated/action-rules.json``（M5 才有内容，可缺）
- ``references/spdx/licenses.json`` / ``exceptions.json`` / ``texts/*.json``

输出：``references/ruleset/*.json`` + ``manifest.json``。

两道硬门：

1. **锚点必须可定位**：``anchor.ref`` 指向的 ``texts/<id>.json`` 中，``anchor.quote``
   必须真的出现在对应文本里（空白归一化后）。做不到 → 该条 ``verified=false``，不生效。
2. **义务项 / 档位 / ID 必须合法**：枚举来自 ``licaudit.contract``，ID 必须存在于 SPDX 快照。

处置决策表（``action-rules.json``）另有两条结构门：**覆盖完备**（对场景触发表推出的每一组
「确定输入」都必须给出结论）与**无死规则**；表格按「从上到下、先命中者生效」解释，
因此条目不排序。

``--check`` 两层：冻结产物形态正确 + 重生成到临时目录逐字节一致。

用法::

    py -3.12 -X utf8 tools/gen_ruleset.py
    py -3.12 -X utf8 tools/gen_ruleset.py --check
"""

import argparse
import io
import json
import os
import shutil
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from licaudit import contract  # noqa: E402
from licaudit.ruleset.loader import ALLOWED_RULE_FILES, sha256_file  # noqa: E402

CURATED_DIR = os.path.join(REPO_ROOT, "references", "curated")
SPDX_DIR = os.path.join(REPO_ROOT, "references", "spdx")
RULESET_DIR = os.path.join(REPO_ROOT, "references", "ruleset")

RULESET_VERSION = "r0.1.0"

# 规则集复核元数据（阶段三 任务 5，字段规范见 plan/03 与 10-6-scaffold-formwork-checker v2.0.0）。
# 只登记「复核事实」，不参与任何判定；随 manifest.json 一起打进 sdist 与 wheel。
REVIEW = {
    "ruleset_version": RULESET_VERSION,
    "reviewed_on": "2026-10-19",
    "cycle_months": 12,
    "next_review_due": "2027-10-19",
    "reviewer": "执行方（阶段三 任务 5，权威渠道直连核实）",
    "standards": [
        {
            "standard": "SPDX License List",
            "version": "3.29.0",
            "issued": "2023-11-30",
            "effective": "2023-11-30",
            "currency": "现行（3.29.0 为本规则包冻结的快照版本；上游列表持续更新，本仓库以「随包冻结 + "
                        "--check 逐字节比对」代替运行时联网，刷新需人工跑 fetch_spdx.py + gen_ruleset.py）",
            "authority_url": "https://spdx.org/licenses/",
            "conclusion": "本规则包的档位/义务/锚点全部由该版本快照的许可证原文与 curated 人工表推导，"
                          "引用范围即该快照本身；上游发布新版本不改写历史报告的依据，"
                          "刷新快照属规则集变更（按阶段三任务 3 的版本规则升版）。",
        },
        {
            "standard": "SPDX License Exceptions",
            "version": "3.29.0",
            "issued": "2023-11-30",
            "effective": "2023-11-30",
            "currency": "现行（与 License List 同一 release 数据集；exceptions.json 为同批采集）",
            "authority_url": "https://spdx.org/licenses/exceptions-index.html",
            "conclusion": "例外条目只用于表达式拆分与展示，不参与档位判定；本轮复核确认快照内 "
                          "exceptions.json 与 licenses.json 同批（captured_on 2026-10-17），无版本错配。",
        },
    ],
}

VALID_TIERS = set(contract.TIERS)
VALID_OBLIGATIONS = set(contract.OBLIGATIONS)
VALID_ACTIONS = set(contract.ACTION_LEVELS)
VALID_RESOLUTIONS = set(contract.CONFLICT_RESOLUTIONS)
VALID_SCENARIOS = set(contract.SCENARIO_IDS)
VALID_LINK_MODES = set(contract.LINK_MODES)

# 处置决策表的谓词与取值域（plan/03 §5.1–§5.2；引擎按同一套谓词做通用匹配）。
ACTION_PREDICATES = (
    "axes_any",
    "axes_only",
    "conflict",
    "pair_conflict",
    "link_mode",
    "verdict",
)
DETERMINATE_CONFLICTS = ("compatible", "incompatible")
# ``none`` = 没有判定为不兼容的已登记冲突对（含未登记与登记为 compatible 的组合）；
# ``pending`` 的冲突对条目由引擎挡在「待人工确认」，不进决策表。
PAIR_CONFLICT_VALUES = ("none", "incompatible")
DETERMINATE_VERDICTS = ("triggered", "not_triggered")


CLASSIFIER_POLICY = "source"


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
# 锚点定位
# ---------------------------------------------------------------------------


def _normalize_ws(text):
    return " ".join(text.split())


class TextCache(object):
    def __init__(self, spdx_dir):
        self.spdx_dir = spdx_dir
        self._cache = {}

    def get(self, rel_ref):
        """``texts/MIT.json#licenseText`` → 文本；缺失返回 ``None``。"""
        path_part = rel_ref.split("#", 1)[0]
        if path_part not in self._cache:
            path = os.path.join(self.spdx_dir, path_part.replace("/", os.sep))
            if not os.path.isfile(path):
                self._cache[path_part] = None
            else:
                payload = read_json(path)
                text = payload.get("licenseText") or payload.get("licenseExceptionText")
                self._cache[path_part] = text
        return self._cache[path_part]

    def contains(self, ref, quote):
        text = self.get(ref)
        if not isinstance(text, str):
            return False
        if not isinstance(quote, str) or not quote.strip():
            return False
        return _normalize_ws(quote) in _normalize_ws(text)


def check_anchor(anchor, texts):
    """锚点是否可解析：结构齐全 + 引文能在原文中定位。"""
    if not isinstance(anchor, dict):
        return False, "anchor_missing"
    for key in ("source", "ref"):
        value = anchor.get(key)
        if not isinstance(value, str) or not value.strip():
            return False, "anchor_missing"
    quote = anchor.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        return False, "anchor_quote_missing"
    if not texts.contains(anchor["ref"], quote):
        return False, "anchor_not_locatable"
    return True, ""


# ---------------------------------------------------------------------------
# 文档构建
# ---------------------------------------------------------------------------


def build_tiers(curated, licenses, texts, problems):
    entries = []
    covered = set()
    for index, entry in enumerate(curated.get("entries", [])):
        license_id = entry.get("license_id")
        if license_id not in licenses:
            problems.append("tiers[{0}] 的 license_id 不在 SPDX 清单中：{1}".format(index, license_id))
            continue
        tier = entry.get("tier")
        if tier not in VALID_TIERS:
            problems.append("tiers[{0}] 档位非法：{1}".format(license_id, tier))
            continue
        obligations = list(entry.get("obligations") or [])
        unknown = [item for item in obligations if item not in VALID_OBLIGATIONS]
        if unknown:
            problems.append("tiers[{0}] 义务项非法：{1}".format(license_id, unknown))
            continue

        verified, reason = check_anchor(entry.get("anchor"), texts)
        if not verified:
            problems.append("tiers[{0}] 锚点不可定位（{1}）".format(license_id, reason))

        entry_flags = []
        patent = entry.get("patent_clause") or {"present": False, "anchor": None}
        trademark = entry.get("trademark_clause") or {"present": False, "anchor": None}
        for label, clause in (("patent", patent), ("trademark", trademark)):
            if clause.get("present"):
                ok, why = check_anchor(clause.get("anchor"), texts)
                if not ok:
                    problems.append(
                        "tiers[{0}] 的 {1}_clause 锚点不可定位（{2}）".format(
                            license_id, label, why
                        )
                    )
                    clause = {"present": False, "anchor": None}
            if clause.get("present"):
                entry_flags.append(label)

        entries.append({
            "license_id": license_id,
            "tier": tier,
            "obligations": obligations,
            "patent_clause": patent,
            "trademark_clause": trademark,
            "anchor": entry.get("anchor"),
            "verified": bool(entry.get("verified")) and verified,
            "checked_on": entry.get("checked_on"),
        })
        covered.add(license_id)

    document = {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "entries": sorted(entries, key=lambda item: item["license_id"]),
    }
    return document, covered


def build_trove_map(curated, licenses, problems):
    entries = []
    for index, entry in enumerate(curated.get("entries", [])):
        classifier = entry.get("classifier")
        spdx_id = entry.get("spdx_id")
        if not isinstance(classifier, str) or not classifier.startswith("License ::"):
            problems.append("trove-map[{0}] classifier 形态非法".format(index))
            continue
        if spdx_id not in licenses:
            problems.append("trove-map[{0}] 的 spdx_id 不在 SPDX 清单中：{1}".format(index, spdx_id))
            continue
        source_url = entry.get("source_url")
        if not isinstance(source_url, str) or not source_url.strip():
            problems.append("trove-map[{0}] 缺少 source_url".format(index))
            continue
        if not entry.get("checked_on"):
            problems.append("trove-map[{0}] 缺少 checked_on".format(index))
            continue
        entries.append({
            "classifier": classifier,
            "spdx_id": spdx_id,
            "source_url": source_url,
            "checked_on": entry["checked_on"],
        })
    return {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "entries": sorted(entries, key=lambda item: item["classifier"]),
    }


def build_scenario_triggers(curated, texts, problems):
    """场景触发表：与 tiers 同口径的锚点硬门（D20 / K5）。"""
    entries = []
    seen = set()
    for index, entry in enumerate(curated.get("entries", [])):
        rule_id = entry.get("id")
        if not isinstance(rule_id, str) or not rule_id.strip():
            problems.append("scenario-triggers[{0}] 缺少 id".format(index))
            continue
        if rule_id in seen:
            problems.append("scenario-triggers[{0}] id 重复：{1}".format(index, rule_id))
            continue
        seen.add(rule_id)
        tier = entry.get("tier")
        if tier not in VALID_TIERS:
            problems.append("scenario-triggers[{0}] 档位非法：{1}".format(rule_id, tier))
            continue
        scenarios = entry.get("scenarios") or []
        if not scenarios:
            problems.append("scenario-triggers[{0}] scenarios 为空".format(rule_id))
            continue
        bad = [item for item in scenarios if item not in VALID_SCENARIOS]
        if bad:
            problems.append("scenario-triggers[{0}] 场景非法：{1}".format(rule_id, bad))
            continue
        link_modes = entry.get("link_modes") or []
        if not link_modes:
            problems.append("scenario-triggers[{0}] link_modes 为空".format(rule_id))
            continue
        bad = [item for item in link_modes if item not in VALID_LINK_MODES]
        if bad:
            problems.append("scenario-triggers[{0}] 链接方式非法：{1}".format(rule_id, bad))
            continue
        obligations = entry.get("obligations") or []
        bad = [item for item in obligations if item not in VALID_OBLIGATIONS]
        if bad:
            problems.append("scenario-triggers[{0}] 义务项非法：{1}".format(rule_id, bad))
            continue
        trigger = entry.get("trigger")
        if not isinstance(trigger, str) or not trigger.strip():
            problems.append("scenario-triggers[{0}] 缺少 trigger".format(rule_id))
            continue
        if "network_interaction" in entry and not isinstance(
            entry.get("network_interaction"), bool
        ):
            problems.append(
                "scenario-triggers[{0}] network_interaction 必须是布尔值".format(rule_id)
            )
            continue

        verified, reason = check_anchor(entry.get("anchor"), texts)
        if not verified:
            problems.append(
                "scenario-triggers[{0}] 锚点不可定位（{1}）".format(rule_id, reason)
            )

        built = {
            "id": rule_id,
            "tier": tier,
            "scenarios": list(scenarios),
            "link_modes": list(link_modes),
        }
        if "network_interaction" in entry:
            built["network_interaction"] = bool(entry["network_interaction"])
        built.update({
            "trigger": trigger,
            "obligations": list(obligations),
            "anchor": entry.get("anchor"),
            "verified": bool(entry.get("verified")) and verified,
            "checked_on": entry.get("checked_on"),
        })
        entries.append(built)
    return {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "entries": sorted(entries, key=lambda item: item["id"]),
    }


def _normalize_cross_check(value, pair_id, problems):
    """``cross_check`` 只作交叉验证留痕，不参与判定；畸形则丢弃并记问题。"""
    if value is None:
        return None
    if not isinstance(value, dict):
        problems.append("conflict-pairs[{0}] cross_check 必须是对象".format(pair_id))
        return None
    source = value.get("source")
    if not isinstance(source, str) or not source.strip():
        problems.append("conflict-pairs[{0}] cross_check 缺少 source".format(pair_id))
        return None
    return {
        "source": source,
        "status": value.get("status") or "advisory",
        "checked_on": value.get("checked_on"),
    }


def build_conflict_pairs(curated, licenses, texts, problems):
    """冲突对表：与 tiers / scenario-triggers 同口径的锚点硬门（D20 / K5 / K15）。

    除锚点门外另加三道：
      - ``left`` / ``right`` 必须是非空且互不相同的字符串，并且都在 SPDX 快照里
        （否则该条根本不产出，避免「指向不存在的许可证」的判定）；
      - 无向组合（``left × right`` 排序后）不得重复登记两条 —— ``pair_id`` 唯一只是第一道；
      - 锚点不可定位 → 该条 ``verified=false``（loader 会拒进 ``disabled``），仍保留可见。
    """
    entries = []
    seen = set()
    seen_pairs = {}
    for index, entry in enumerate(curated.get("entries", [])):
        pair_id = entry.get("pair_id")
        if not isinstance(pair_id, str) or not pair_id.strip():
            problems.append("conflict-pairs[{0}] pair_id 缺失".format(index))
            continue
        if pair_id in seen:
            problems.append("conflict-pairs[{0}] pair_id 重复：{1}".format(index, pair_id))
            continue
        seen.add(pair_id)

        left = entry.get("left")
        right = entry.get("right")
        missing = [
            name for name, value in (("left", left), ("right", right))
            if not isinstance(value, str) or not value.strip()
        ]
        if missing:
            problems.append(
                "conflict-pairs[{0}] {1} 缺失".format(pair_id, "/".join(missing))
            )
            continue
        if left == right:
            problems.append(
                "conflict-pairs[{0}] left 与 right 相同：{1}".format(pair_id, left)
            )
            continue
        unknown = [value for value in (left, right) if value not in licenses]
        if unknown:
            problems.append(
                "conflict-pairs[{0}] 的许可证 ID 不在 SPDX 清单中：{1}".format(
                    pair_id, ", ".join(unknown)
                )
            )
            continue
        key = tuple(sorted((left, right)))
        if key in seen_pairs:
            problems.append(
                "conflict-pairs[{0}] 无向组合重复登记：{1} × {2}（已由 {3} 覆盖）".format(
                    pair_id, left, right, seen_pairs[key]
                )
            )
            continue
        seen_pairs[key] = pair_id

        resolution = entry.get("resolution")
        if resolution not in VALID_RESOLUTIONS:
            problems.append(
                "conflict-pairs[{0}] resolution 非法：{1}".format(pair_id, resolution)
            )
            continue
        basis = entry.get("basis")
        if not isinstance(basis, str) or not basis.strip():
            problems.append("conflict-pairs[{0}] 缺少 basis".format(pair_id))
            continue

        verified, reason = check_anchor(entry.get("anchor"), texts)
        if not verified:
            problems.append("conflict-pairs[{0}] 锚点不可定位（{1}）".format(pair_id, reason))

        entries.append({
            "pair_id": pair_id,
            "left": left,
            "right": right,
            "resolution": resolution,
            "basis": basis,
            "anchor": entry.get("anchor"),
            "cross_check": _normalize_cross_check(
                entry.get("cross_check"), pair_id, problems
            ),
            "verified": bool(entry.get("verified")) and verified,
            "checked_on": entry.get("checked_on"),
        })
    return {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "entries": sorted(entries, key=lambda item: item["pair_id"]),
    }


def _axis_map(curated_action, problems):
    """``obligation_axes``：义务项 → 义务轴。必须**恰好**覆盖 ``contract.OBLIGATIONS``。

    轴名由本表定义（引擎不写任何义务项字面量），因此这里同时产出可用轴集合，
    供 ``when`` 谓词校验使用。
    """
    raw = curated_action.get("obligation_axes")
    if not isinstance(raw, dict):
        problems.append("action-rules 缺少 obligation_axes 映射（引擎不得内联义务项）")
        return None, set()
    missing = [item for item in contract.OBLIGATIONS if item not in raw]
    extra = [item for item in sorted(raw) if item not in VALID_OBLIGATIONS]
    if missing:
        problems.append(
            "action-rules.obligation_axes 未覆盖义务项：{0}".format(", ".join(missing))
        )
    if extra:
        problems.append(
            "action-rules.obligation_axes 含未知义务项：{0}".format(", ".join(extra))
        )
    bad = [
        item for item in sorted(raw)
        if not isinstance(raw[item], str) or not raw[item].strip()
    ]
    if bad:
        problems.append(
            "action-rules.obligation_axes 的轴名非法：{0}".format(", ".join(bad))
        )
    if missing or extra or bad:
        return None, set()
    return dict(raw), set(raw.values())


def scenario_axis_sets(curated_triggers, axes):
    """由场景触发表推出**可达**的义务轴集合（真值与生成器共用这一口径）。

    引擎看到的是「同一档位下命中条目的义务并集」：不同档位的许可证不会互相叠加，
    因此按 ``tier`` 分组求并集闭包，再加上「一条都没命中」的空集。
    """
    by_tier = {}
    for entry in curated_triggers.get("entries", []):
        tier = entry.get("tier")
        if tier not in VALID_TIERS:
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


def _validate_axis_values(key, values, available_axes, problems, label):
    bad = [
        item for item in values
        if not isinstance(item, str) or item not in available_axes
    ]
    if bad:
        problems.append(
            "action-rules[{0}] {1} 含未定义的义务轴：{2}".format(
                label, key, ", ".join(str(item) for item in bad)
            )
        )
        return False
    return True


def _validate_when(when, available_axes, problems, label):
    if not isinstance(when, dict) or not when:
        problems.append("action-rules[{0}] 缺少 when 条件".format(label))
        return False
    ok = True
    for key in sorted(when):
        if key not in ACTION_PREDICATES:
            problems.append("action-rules[{0}] 未知谓词：{1}".format(label, key))
            ok = False
            continue
        values = when[key]
        if not isinstance(values, list) or not values:
            problems.append("action-rules[{0}] {1} 必须是非空数组".format(label, key))
            ok = False
            continue
        if key == "axes_any":
            ok = _validate_axis_values(key, values, available_axes, problems, label) and ok
        elif key == "axes_only":
            for item in values:
                if not isinstance(item, list):
                    problems.append(
                        "action-rules[{0}] axes_only 的元素必须是义务轴数组".format(label)
                    )
                    ok = False
                    break
                ok = (
                    _validate_axis_values(key, item, available_axes, problems, label) and ok
                )
        elif key == "conflict":
            bad = [item for item in values if item not in contract.CONFLICT_RESOLUTIONS]
            if bad:
                problems.append(
                    "action-rules[{0}] conflict 非法：{1}".format(label, bad)
                )
                ok = False
        elif key == "pair_conflict":
            bad = [item for item in values if item not in PAIR_CONFLICT_VALUES]
            if bad:
                problems.append(
                    "action-rules[{0}] pair_conflict 非法：{1}".format(label, bad)
                )
                ok = False
        elif key == "link_mode":
            bad = [item for item in values if item not in VALID_LINK_MODES]
            if bad:
                problems.append(
                    "action-rules[{0}] link_mode 非法：{1}".format(label, bad)
                )
                ok = False
        elif key == "verdict":
            bad = [item for item in values if item not in contract.VERDICTS]
            if bad:
                problems.append("action-rules[{0}] verdict 非法：{1}".format(label, bad))
                ok = False
    return ok


def matches_when(when, facts):
    """通用谓词匹配（生成器的朴素实现；引擎有独立实现，两边不得共用代码）。"""
    for key in sorted(when):
        wanted = when[key]
        if key == "axes_any":
            if not (set(facts["axes"]) & set(wanted)):
                return False
        elif key == "axes_only":
            if set(facts["axes"]) not in [set(item) for item in wanted]:
                return False
        else:
            if facts.get(key) not in wanted:
                return False
    return True


def action_fact_space(curated_triggers, axes):
    """可达且**确定**的事实组合（``pending`` 一类不确定输入由引擎挡在待确认）。"""
    space = []
    for axes_set in scenario_axis_sets(curated_triggers, axes):
        for conflict in DETERMINATE_CONFLICTS:
            for pair_conflict in PAIR_CONFLICT_VALUES:
                for link_mode in contract.LINK_MODES:
                    for verdict in DETERMINATE_VERDICTS:
                        space.append({
                            "axes": sorted(axes_set),
                            "conflict": conflict,
                            "pair_conflict": pair_conflict,
                            "link_mode": link_mode,
                            "verdict": verdict,
                        })
    return space


def _check_decision_table(entries, curated_triggers, axes, problems):
    """决策表两道结构门：**覆盖完备**（确定输入的组合都有结论）+ **无死规则**。

    不完全的决策表会把「确定的情形」推给待人工确认，那是把口径漏洞伪装成谨慎；
    死规则则意味着表里写了永不生效的条目。
    """
    if not entries or not axes:
        return
    space = action_fact_space(curated_triggers, axes)
    first_hit = {}
    uncovered = []
    for facts in space:
        hit = None
        for index, entry in enumerate(entries):
            if matches_when(entry["when"], facts):
                hit = index
                break
        if hit is None:
            uncovered.append(facts)
            continue
        first_hit.setdefault(hit, facts)

    if uncovered:
        problems.append(
            "action-rules 决策表未覆盖 {0} 组确定输入，例如：{1}".format(
                len(uncovered), _describe_facts(uncovered[0])
            )
        )
    for index, entry in enumerate(entries):
        if index not in first_hit:
            problems.append(
                "action-rules[{0}] 是死规则（没有任何确定输入会先命中它）".format(
                    entry.get("id")
                )
            )


def _describe_facts(facts):
    return "义务轴 {0} / conflict={1} / pair_conflict={2} / link_mode={3} / verdict={4}".format(
        "{" + ",".join(facts["axes"]) + "}",
        facts["conflict"],
        facts["pair_conflict"],
        facts["link_mode"],
        facts["verdict"],
    )


def build_action_rules(curated, curated_triggers, texts, problems):
    """处置决策表：与 tiers / 触发表 / 冲突对同口径的锚点硬门（D20 / K5 / K18）。

    除锚点门外另加四道：
      - ``level`` 必须命中 ``contract.ACTION_LEVELS``；``id`` 非空且唯一；
      - ``when`` 的谓词与取值域必须在 ``ACTION_PREDICATES`` 内，义务轴必须已在
        ``obligation_axes`` 中定义（引擎不写任何义务项/档位/处置字面量）；
      - 决策表必须**覆盖全部确定输入**（见 :func:`_check_decision_table`）；
      - 表内不得有死规则。

    **条目不排序**：与其它规则文件不同，决策表是「从上到下、先命中者生效」的有序表，
    书写顺序即优先级，因此生成器保持 curated 的原始顺序。
    """
    axes, available_axes = _axis_map(curated, problems)
    entries = []
    seen = set()
    for index, entry in enumerate(curated.get("entries", [])):
        rule_id = entry.get("id")
        label = rule_id if isinstance(rule_id, str) and rule_id.strip() else "[{0}]".format(index)
        if not isinstance(rule_id, str) or not rule_id.strip():
            problems.append("action-rules[{0}] 缺少 id".format(index))
            continue
        if rule_id in seen:
            problems.append("action-rules[{0}] id 重复：{1}".format(index, rule_id))
            continue
        seen.add(rule_id)
        if entry.get("level") not in VALID_ACTIONS:
            problems.append(
                "action-rules[{0}] level 非法：{1}".format(label, entry.get("level"))
            )
            continue
        basis = entry.get("basis")
        if not isinstance(basis, str) or not basis.strip():
            problems.append("action-rules[{0}] 缺少 basis".format(label))
            continue
        if not _validate_when(entry.get("when"), available_axes, problems, label):
            continue

        verified, reason = check_anchor(entry.get("anchor"), texts)
        if not verified:
            problems.append("action-rules[{0}] 锚点不可定位（{1}）".format(label, reason))

        if not entry.get("checked_on"):
            problems.append("action-rules[{0}] 缺少 checked_on".format(label))

        entries.append({
            "id": rule_id,
            "level": entry["level"],
            "basis": basis,
            "when": entry["when"],
            "anchor": entry.get("anchor"),
            "verified": bool(entry.get("verified")) and verified,
            "checked_on": entry.get("checked_on"),
        })

    _check_decision_table(entries, curated_triggers, axes or {}, problems)

    document = {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "obligation_axes": axes or {},
        "entries": entries,
    }
    return document



def build_obligations():
    labels = {
        "retain-copyright": "保留版权声明",
        "include-license-text": "附许可证全文",
        "mark-modifications": "标注修改",
        "provide-source": "提供对应源码",
        "network-source": "网络交互提供源码",
        "patent-grant": "专利授权",
        "trademark-restriction": "商标限制",
        "same-license": "同许可发布",
    }
    return {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "entries": [
            {"id": obligation, "label": labels[obligation]}
            for obligation in contract.OBLIGATIONS
        ],
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def load_inputs():
    licenses_payload = read_json(os.path.join(SPDX_DIR, "licenses.json"))
    exceptions_payload = read_json(os.path.join(SPDX_DIR, "exceptions.json"))
    licenses = {item["licenseId"]: item for item in licenses_payload["licenses"]}
    exceptions = {
        item["licenseExceptionId"]: item for item in exceptions_payload["exceptions"]
    }
    curated = {}
    for name in ("tiers", "trove-map", "scenario-triggers", "conflict-pairs",
                 "action-rules"):
        path = os.path.join(CURATED_DIR, name + ".json")
        curated[name] = read_json(path) if os.path.isfile(path) else {"entries": []}
    return licenses_payload, exceptions_payload, licenses, exceptions, curated


def generate(target_dir=None):
    """生成规则包到 ``target_dir``（默认仓库 ``references/ruleset``）。

    返回 ``(documents, manifest, problems)``。
    """
    target_dir = target_dir or RULESET_DIR
    licenses_payload, exceptions_payload, licenses, exceptions, curated = load_inputs()
    texts = TextCache(SPDX_DIR)
    problems = []

    documents = {}
    documents["tiers.json"], covered = build_tiers(curated["tiers"], licenses, texts, problems)
    documents["obligations.json"] = build_obligations()
    documents["trove-map.json"] = build_trove_map(curated["trove-map"], licenses, problems)
    documents["scenario-triggers.json"] = build_scenario_triggers(
        curated["scenario-triggers"], texts, problems
    )
    documents["conflict-pairs.json"] = build_conflict_pairs(
        curated["conflict-pairs"], licenses, texts, problems
    )
    documents["action-rules.json"] = build_action_rules(
        curated["action-rules"], curated["scenario-triggers"], texts, problems
    )

    # 覆盖口径：总数与采样数双登记（plan/04 §3.3）
    total_ids = len(licenses)
    sampled = len(covered)
    documents["tiers.json"]["coverage"] = {
        "tiers_total_ids": total_ids,
        "tiers_sampled_ids": sampled,
        "note": "首期只覆盖清单实际出现的 SPDX ID；抽样覆盖，非全量穷举",
    }

    if not os.path.isdir(target_dir):
        os.makedirs(target_dir)

    files = {}
    for name in ALLOWED_RULE_FILES:
        if name not in documents:
            continue
        path = os.path.join(target_dir, name)
        write_text_atomic(path, dumps(documents[name]))
        files[name] = sha256_file(path)

    manifest = {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "license_list_version": licenses_payload.get("licenseListVersion"),
        "license_list_captured_on": _captured_on(),
        "ruleset_coverage": documents["tiers.json"]["coverage"],
        "files": files,
        # 复核元数据：文件级 meta.review（阶段三 任务 5 的字段规范）
        "meta": {"review": REVIEW},
    }
    write_text_atomic(os.path.join(target_dir, "manifest.json"), dumps(manifest))
    return documents, manifest, problems


def _captured_on():
    path = os.path.join(SPDX_DIR, "manifest.json")
    if os.path.isfile(path):
        return read_json(path).get("captured_on")
    return None


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------


def check_against(target_dir=None):
    """两层校验：冻结产物形态 + 重生成逐字节一致。返回问题列表。"""
    target_dir = target_dir or RULESET_DIR
    problems = []

    manifest_path = os.path.join(target_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return ["缺少 {0}".format(manifest_path)]

    frozen = read_json(manifest_path)
    if frozen.get("schema_version") != 1:
        problems.append("manifest.schema_version 不是 1")
    if frozen.get("ruleset_version") != RULESET_VERSION:
        problems.append("manifest.ruleset_version 与生成器常量不一致")
    if not frozen.get("license_list_version"):
        problems.append("manifest 缺少 license_list_version")
    declared = frozen.get("files") or {}
    for name in sorted(declared):
        if name not in ALLOWED_RULE_FILES:
            problems.append("manifest 登记了白名单外的文件：{0}".format(name))
            continue
        path = os.path.join(target_dir, name)
        if not os.path.isfile(path):
            problems.append("登记的文件不存在：{0}".format(name))
            continue
        if sha256_file(path) != declared[name]:
            problems.append("冻结产物哈希不符（被手改或生成器漂移）：{0}".format(name))

    temp_root = tempfile.mkdtemp(prefix="licaudit-ruleset-")
    try:
        _documents, _manifest, generation_problems = generate(temp_root)
        for problem in generation_problems:
            problems.append("生成期问题：" + problem)
        names = sorted(set(declared) | set(_manifest["files"]))
        for name in names:
            regenerated = os.path.join(temp_root, name)
            if not os.path.isfile(regenerated):
                problems.append("重生成缺少文件：{0}".format(name))
                continue
            existing = os.path.join(target_dir, name)
            if not os.path.isfile(existing):
                continue
            with io.open(existing, "rb") as stream:
                left = stream.read()
            with io.open(regenerated, "rb") as stream:
                right = stream.read()
            if left != right:
                problems.append(
                    "重生成结果与冻结产物不一致：{0}（首个差异偏移 {1}）".format(
                        name, _first_difference(left, right)
                    )
                )
        manifest_regenerated = os.path.join(temp_root, "manifest.json")
        if os.path.isfile(manifest_regenerated):
            with io.open(manifest_path, "rb") as stream:
                left = stream.read()
            with io.open(manifest_regenerated, "rb") as stream:
                right = stream.read()
            if left != right:
                problems.append("manifest.json 与重生成结果不一致")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    return problems


def _first_difference(left, right):
    limit = min(len(left), len(right))
    for index in range(limit):
        if left[index] != right[index]:
            return index
    return limit


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="gen_ruleset",
        description="由 curated 表 + SPDX 快照生成规则包（生成物禁手改）",
    )
    parser.add_argument("--check", action="store_true",
                        help="校验冻结产物（形态 + 重生成逐字节一致）")
    parser.add_argument("--out", default=RULESET_DIR, help="输出目录")
    args = parser.parse_args(argv)

    out_dir = os.path.abspath(args.out)

    if args.check:
        problems = check_against(out_dir)
        if problems:
            for problem in problems:
                sys.stdout.write("[FAIL] {0}\n".format(problem))
            return 1
        sys.stdout.write("[OK] 规则包与重生成结果逐字节一致：{0}\n".format(out_dir))
        return 0

    documents, manifest, problems = generate(out_dir)
    for problem in problems:
        sys.stdout.write("[WARN] {0}\n".format(problem))
    sys.stdout.write(
        "[OK] 规则包已生成：{0}；ruleset_version={1}；license_list_version={2}；"
        "tiers={3}/{4}\n".format(
            out_dir,
            manifest["ruleset_version"],
            manifest["license_list_version"],
            manifest["ruleset_coverage"]["tiers_sampled_ids"],
            manifest["ruleset_coverage"]["tiers_total_ids"],
        )
    )
    return 1 if any("非法" in problem or "不在 SPDX" in problem for problem in problems) else 0


if __name__ == "__main__":
    sys.exit(main())
