# -*- coding: utf-8 -*-
"""M5 处置分级：决策表查表、五锚点门、退出码联动、真值对账。

这些测试刻意不「回放」引擎输出：级别期望值来自 ``references/curated/action-rules.json``
（规则表是唯一真相），并且用**假规则表**证明级别真的来自表而不是代码里的分支。
"""

import io
import json
import os
import shutil

import pytest

from _helpers import REPO_ROOT, write_json

from licaudit import cli, contract
from licaudit.assess import action as action_mod
from licaudit.assess.action import (
    ACTIONS_TOP_LEVEL_FIELDS,
    ACTION_RULE_FILE,
    build_actions,
    has_blocking_action,
    match_rule,
    obligation_axes,
    usable_rules,
)
from licaudit.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE
from licaudit.ruleset import load_ruleset
from licaudit.serialize import dumps_json

DATA_DIR = os.path.join(REPO_ROOT, "data")
CURATED_DIR = os.path.join(REPO_ROOT, "references", "curated")
TRUTH_PATH = os.path.join(DATA_DIR, "truth", "actions.json")


def run(argv, capsys=None):
    code = cli.main(argv)
    out = err = ""
    if capsys is not None:
        captured = capsys.readouterr()
        out, err = captured.out, captured.err
    return code, out, err


def read_json(path):
    with io.open(path, encoding="utf-8") as stream:
        return json.load(stream)


def read_text(path):
    with io.open(path, encoding="utf-8") as stream:
        return stream.read()


# ---------------------------------------------------------------------------
# 构造上游产物（只造字段，不跑引擎）
# ---------------------------------------------------------------------------


def _record(package, spdx_id, version="1.0.0", **evidence_extra):
    evidence = {"file": "package.json", "locator": "dependencies." + package, "line": 10}
    evidence.update(evidence_extra)
    return {
        "package": package,
        "version": version,
        "raw_license": spdx_id,
        "spdx_id": spdx_id,
        "confidence": "license_expression",
        "evidence": evidence,
    }


def _profile(entries):
    return {
        "format": contract.PROFILE_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "profiles": [
            {"spdx_id": spdx_id, "tier": tier} for spdx_id, tier in sorted(entries.items())
        ],
        "pending_confirmation": [],
    }


def _scenario(per_package, link_mode="none", scenario="distribute-binary"):
    entries = []
    for package, spec in sorted(per_package.items()):
        entries.append({
            "package": package,
            "scenario": scenario,
            "link_mode": link_mode,
            "triggers": list(spec.get("triggers") or []),
            "verdict": spec.get("verdict", "triggered"),
            "evidence": {
                "rule_ids": list(spec.get("rule_ids") or []),
                "obligations": list(spec.get("obligations") or []),
                "expression_evaluation": None,
                "user_answer": "用例",
                "answered_by": "user",
            },
        })
    return {
        "format": contract.SCENARIO_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "scenario": scenario,
        "delivery": "binary",
        "link_mode": link_mode,
        "entries": entries,
        "pending_confirmation": [],
        "notes": [],
    }


def _conflicts(outbound, per_package, pairs=(), tier="permissive"):
    records = []
    for package, spec in sorted(per_package.items()):
        records.append({
            "pair_id": "OB-{0}-{1}".format(spec.get("left") or "unidentified", outbound),
            "left": spec.get("left"),
            "right": outbound,
            "basis": "档位比较",
            "resolution": spec.get("resolution", "compatible"),
            "evidence": {
                "source": "tier-comparison",
                "node_tier": spec.get("tier", tier),
                "packages": [package],
            },
        })
    dependency = []
    for pair_id, sides, resolution in pairs:
        dependency.append({
            "pair_id": pair_id,
            "left": sides[0],
            "right": sides[1],
            "basis": "规则表",
            "resolution": resolution,
            "evidence": {"source": "curated", "packages": {sides[0]: [sides[2]], sides[1]: [sides[3]]}},
        })
    return {
        "format": contract.CONFLICT_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "outbound_license": outbound,
        "outbound_tier": tier,
        "dependency_conflicts": dependency,
        "outbound_conflicts": records,
        "pending_confirmation": [],
        "notes": [],
    }


class FakeRuleset(object):
    """最小规则包替身：只提供处置决策表，用于证明「级别来自表，不来自代码」。"""

    version = "r-fake"

    def __init__(self, document):
        self.documents = {ACTION_RULE_FILE: document}
        self.disabled = []

    def entries(self, name):
        return (self.documents.get(name) or {}).get("entries", [])


def _document(entries, axes=None):
    document = {
        "schema_version": 1,
        "ruleset_version": "r-fake",
        "obligation_axes": axes or {
            obligation: "axis-" + obligation for obligation in contract.OBLIGATIONS
        },
        "entries": entries,
    }
    for entry in entries:
        entry.setdefault("basis", "假规则表依据")
        entry.setdefault("checked_on", "2026-10-17")
        entry.setdefault("verified", True)
        entry.setdefault("anchor", {"source": "test", "ref": "test#x"})
    return document


def _rule(rule_id, level, when):
    return {
        "id": rule_id,
        "level": level,
        "when": when,
        "basis": "假规则表依据",
        "checked_on": "2026-10-17",
        "verified": True,
        "anchor": {"source": "test", "ref": "test#x"},
    }


# ---------------------------------------------------------------------------
# 真实规则包上的端到端产物
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def output(tmp_path_factory):
    """真实规则包：GPL-2.0-only（同许可 + 不兼容）/ MIT（无义务）/ BUSL-1.1（仅声明）。"""
    out_dir = tmp_path_factory.mktemp("actions")
    inventory = os.path.join(str(out_dir), "inventory.json")
    write_json(inventory, {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "dependencies": [
            _record("example-pkg-gpl", "GPL-2.0-only"),
            _record("example-pkg-mit", "MIT"),
        ],
        "pending_confirmation": [],
    })
    code = cli.main([
        "assess", "--inventory", inventory, "--scenario", "distribute-binary",
        "--outbound-license", "MIT", "--scenario-note", "分发二进制",
        "--out-dir", str(out_dir),
    ])
    # GPL-2.0-only 依赖 + MIT outbound：同许可义务 + 不兼容 → replace_or_license → 1
    assert code == EXIT_FINDINGS
    return out_dir, read_json(os.path.join(str(out_dir), "actions.json")), inventory


def _by_package(payload):
    return {item["package"]: item for item in payload["actions"]}


def test_action_record_field_order_matches_contract(output):
    _out_dir, payload, _inventory = output
    assert payload["format"] == contract.ACTION_FORMAT
    assert payload["format_version"] == contract.FORMAT_VERSION
    assert payload["actions"]
    for record in payload["actions"]:
        assert tuple(record) == contract.ACTION_FIELDS
        assert record["level"] in contract.ACTION_LEVELS or record["level"] is None
        assert record["reasons"]


def test_actions_artifact_field_order(output):
    _out_dir, payload, _inventory = output
    assert tuple(payload) == ACTIONS_TOP_LEVEL_FIELDS


def test_gpl_dependency_against_permissive_outbound_is_replace_or_license(output):
    _out_dir, payload, _inventory = output
    record = _by_package(payload)["example-pkg-gpl"]
    assert record["level"] == "replace_or_license"
    assert record["evidence"]["rule_id"] == "A-REPL-001"
    assert record["evidence"]["axes"] == ["notice", "same-license", "source"]


def test_permissive_dependency_without_obligations_is_ok(output):
    _out_dir, payload, _inventory = output
    record = _by_package(payload)["example-pkg-mit"]
    assert record["level"] == "ok"
    assert record["evidence"]["rule_id"] == "A-OK-001"
    assert record["evidence"]["axes"] == []


def test_every_graded_action_carries_all_five_anchors(output):
    """K20：进处置建议的条目必须五锚点齐全（包名/版本/声明位置/SPDX ID/依据条款）。"""
    _out_dir, payload, _inventory = output
    graded = [item for item in payload["actions"] if item["level"] is not None]
    assert graded
    for record in graded:
        evidence = record["evidence"]
        assert record["package"]
        assert record["version"] and record["version"] != "*"
        assert record["spdx_id"]
        assert evidence["declaration_location"]
        assert evidence["basis_clause"]
        assert evidence["rule_id"]
        assert evidence["anchor"]
        assert evidence["missing_anchors"] == []


def test_pending_action_declares_which_anchor_is_missing(tmp_path):
    """缺声明位置（清单里没有 file 字段）→ 该条不进处置建议，并写明缺哪一项。"""
    inventory = {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "dependencies": [
            {
                "package": "example-pkg-a",
                "version": "1.0.0",
                "raw_license": "MIT",
                "spdx_id": "MIT",
                "confidence": "license_expression",
                "evidence": {"locator": "dependencies.example-pkg-a", "line": 3},
            }
        ],
        "pending_confirmation": [],
    }
    payload = build_actions(
        inventory,
        _profile({"MIT": "permissive"}),
        _scenario({"example-pkg-a": {"obligations": []}}),
        _conflicts("MIT", {"example-pkg-a": {"left": "MIT", "resolution": "compatible"}}),
        load_ruleset(),
    )
    record = payload["actions"][0]
    assert record["level"] is None
    assert "declaration_location_missing" in record["evidence"]["reason_codes"]
    assert record["evidence"]["missing_anchors"] == ["declaration_location"]
    assert payload["pending_confirmation"] == [{
        "package": "example-pkg-a",
        "spdx_id": "MIT",
        "reasons": ["declaration_location_missing"],
    }]


def test_unknown_version_degrades_the_action(tmp_path):
    """版本未知（``*``）→ 按 ``*`` 记账并自动降级为待人工确认（plan/03 §5.2）。"""
    inventory = {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "dependencies": [_record("example-pkg-a", "MIT", version="*")],
        "pending_confirmation": [],
    }
    payload = build_actions(
        inventory,
        _profile({"MIT": "permissive"}),
        _scenario({"example-pkg-a": {"obligations": []}}),
        _conflicts("MIT", {"example-pkg-a": {"left": "MIT", "resolution": "compatible"}}),
        load_ruleset(),
    )
    record = payload["actions"][0]
    assert record["version"] == "*"
    assert record["level"] is None
    assert "version_unknown" in record["evidence"]["reason_codes"]


def test_unresolved_inputs_go_to_pending_not_to_ok(tmp_path):
    """场景未定 / 兼容性待定 → 待人工确认，绝不落到 ``ok``（K7 / K14）。"""
    inventory = {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "dependencies": [_record("example-pkg-a", "MIT")],
        "pending_confirmation": [],
    }
    payload = build_actions(
        inventory,
        _profile({"MIT": "permissive"}),
        _scenario({"example-pkg-a": {"verdict": contract.PENDING, "obligations": []}}),
        _conflicts("MIT", {"example-pkg-a": {"left": "MIT", "resolution": "pending"}}),
        load_ruleset(),
    )
    record = payload["actions"][0]
    assert record["level"] is None
    assert sorted(record["evidence"]["reason_codes"]) == [
        "conflict_pending", "scenario_pending_confirmation",
    ]


def test_decision_table_is_the_only_source_of_the_level(tmp_path):
    """假规则表把「仅声明义务」映射成 isolate → 引擎必须跟着表走（K18）。"""
    axes = {"retain-copyright": "notice"}
    for obligation in contract.OBLIGATIONS:
        axes.setdefault(obligation, "other-" + obligation)
    document = _document([
        _rule("A-FAKE-001", "isolate", {"axes_any": ["notice"], "conflict": ["compatible"]}),
        _rule("A-FAKE-002", "ok", {"conflict": ["compatible"]}),
    ], axes=axes)
    payload = build_actions(
        {"dependencies": [_record("example-pkg-a", "MIT")], "pending_confirmation": []},
        _profile({"MIT": "permissive"}),
        _scenario({"example-pkg-a": {"obligations": ["retain-copyright"]}}),
        _conflicts("MIT", {"example-pkg-a": {"left": "MIT", "resolution": "compatible"}}),
        FakeRuleset(document),
    )
    record = payload["actions"][0]
    assert record["level"] == "isolate"
    assert record["evidence"]["rule_id"] == "A-FAKE-001"


def test_unusable_obligation_axes_never_yield_ok(tmp_path):
    """义务轴映射缺失 → 整张表不可用 → 全部待确认，而不是「没有义务」的 ok。"""
    document = _document([_rule("A-FAKE-001", "ok", {"conflict": ["compatible"]})])
    document["obligation_axes"] = {"retain-copyright": "notice"}
    payload = build_actions(
        {"dependencies": [_record("example-pkg-a", "MIT")], "pending_confirmation": []},
        _profile({"MIT": "permissive"}),
        _scenario({"example-pkg-a": {"obligations": ["retain-copyright"]}}),
        _conflicts("MIT", {"example-pkg-a": {"left": "MIT", "resolution": "compatible"}}),
        FakeRuleset(document),
    )
    record = payload["actions"][0]
    assert record["level"] is None
    assert record["evidence"]["reason_codes"] == ["action_rules_unavailable"]
    assert any(
        note["code"] == "action_rules_unavailable" for note in payload["notes"]
    )


def test_first_matching_rule_wins():
    """决策表按书写顺序解释：先命中者生效（顺序即优先级）。"""
    table = [
        _rule("A-FIRST", "isolate", {"conflict": ["incompatible"]}),
        _rule("A-SECOND", "ok", {"link_mode": ["none"]}),
    ]
    facts = {"axes": [], "conflict": "incompatible", "pair_conflict": "none",
             "link_mode": "none", "verdict": "triggered"}
    assert match_rule(facts, table)["id"] == "A-FIRST"


def test_usable_rules_rejects_entries_with_undefined_axis():
    axes = {obligation: "axis" for obligation in contract.OBLIGATIONS}
    good = _rule("A-GOOD", "ok", {"axes_any": ["axis"]})
    bad = _rule("A-BAD", "ok", {"axes_any": ["not-declared"]})
    usable = usable_rules([good, bad], axes)
    assert [item["id"] for item in usable] == ["A-GOOD"]
    # 映射整体不可用时，连合法条目也不能用（否则「无轴」会被读成「无义务」）。
    assert usable_rules([good], None) == []


def test_obligation_axes_comes_from_the_rule_package():
    ruleset = load_ruleset()
    axes = obligation_axes(ruleset.documents[ACTION_RULE_FILE])
    assert set(axes) == set(contract.OBLIGATIONS)
    assert axes == ruleset.documents[ACTION_RULE_FILE]["obligation_axes"]


def test_has_blocking_action_covers_levels_and_pending():
    assert has_blocking_action({"actions": [{"level": "isolate"}], "pending_confirmation": []})
    assert has_blocking_action({
        "actions": [{"level": "replace_or_license"}], "pending_confirmation": [],
    })
    assert not has_blocking_action({"actions": [{"level": "ok"}], "pending_confirmation": []})
    assert has_blocking_action({"actions": [{"level": "declare"}], "pending_confirmation": [{}]})


# ---------------------------------------------------------------------------
# 退出码联动（plan/03 §5.5）
# ---------------------------------------------------------------------------


def _assess_with(tmp_path, spdx_id, outbound, extra=(), capsys=None):
    inventory = os.path.join(str(tmp_path), "inventory.json")
    write_json(inventory, {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "dependencies": [_record("example-pkg-a", spdx_id)],
        "pending_confirmation": [],
    })
    argv = [
        "assess", "--inventory", inventory, "--scenario", "distribute-binary",
        "--outbound-license", outbound, "--scenario-note", "用例",
        "--out-dir", str(tmp_path / "out"),
    ]
    argv.extend(extra)
    code, out, err = run(argv, capsys)
    artifact = tmp_path / "out" / "actions.json"
    payload = read_json(str(artifact)) if os.path.isfile(str(artifact)) else None
    return code, payload, out + err


def test_blocking_level_exits_one(tmp_path):
    code, payload, text = _assess_with(tmp_path, "GPL-2.0-only", "MIT")
    assert code == EXIT_FINDINGS, text
    assert _by_package(payload)["example-pkg-a"]["level"] == "replace_or_license"


def test_isolate_level_exits_one(tmp_path):
    """弱传染依赖 + 宽松 outbound：档位级不相容但无同许可义务 → isolate → 1。"""
    code, payload, text = _assess_with(tmp_path, "MPL-2.0", "MIT")
    assert code == EXIT_FINDINGS, text
    record = _by_package(payload)["example-pkg-a"]
    assert record["level"] == "isolate"
    # 档位级粗判的行为锁（plan/06 §五 偏差①）：可边界分离 → isolate 而不是 replace。
    assert "same-license" not in record["evidence"]["axes"]


def test_coarse_grading_is_registered_in_the_artifact(output):
    """D36：传染范围聚合未实现、分级只查决策表 —— 都必须在产物 notes 里明文登记。

    不登记的话，读者会把「档位级粗判」读成「按链接/分发边界聚合后的结论」。
    """
    out_dir, payload, _inventory = output
    codes = {note["code"] for note in payload["notes"]}
    assert "scope_aggregation_not_implemented" in codes
    assert "action_level_is_table_driven" in codes
    conflicts = read_json(os.path.join(str(out_dir), "conflicts.json"))
    assert "scope_aggregation_not_implemented" in {
        note["code"] for note in conflicts["notes"]
    }


def test_only_declare_and_ok_exit_zero(tmp_path):
    """BUSL-1.1 依赖 + Elastic-2.0 outbound + SaaS：仅声明义务 → 全 0（无待确认）。"""
    inventory = os.path.join(str(tmp_path), "inventory.json")
    write_json(inventory, {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "dependencies": [_record("example-pkg-a", "BUSL-1.1")],
        "pending_confirmation": [],
    })
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "saas",
        "--network-interaction", "yes", "--outbound-license", "Elastic-2.0",
        "--scenario-note", "SaaS", "--out-dir", str(tmp_path / "out"),
    ])
    payload = read_json(str(tmp_path / "out" / "actions.json"))
    assert code == EXIT_OK, out + err
    assert _by_package(payload)["example-pkg-a"]["level"] == "declare"


def test_outbound_pending_keeps_every_action_pending(tmp_path):
    """K17 的既有口径不得被 M5 冲掉：outbound = pending → 全待定 + exit 1。"""
    code, payload, text = _assess_with(tmp_path, "MIT", "pending")
    assert code == EXIT_FINDINGS, text
    assert _by_package(payload)["example-pkg-a"]["level"] is None
    assert payload["pending_confirmation"]


def test_action_layer_alone_can_force_exit_one(tmp_path):
    """五锚点缺项（缺声明位置）本身就让全量模式 exit 1：处置层参与退出码聚合。

    冲突层这里全部相容、画像与场景都无待确认项，因此 1 只可能来自处置层。
    """
    inventory = os.path.join(str(tmp_path), "inventory.json")
    write_json(inventory, {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "dependencies": [{
            "package": "example-pkg-a",
            "version": "1.0.0",
            "raw_license": "MIT",
            "spdx_id": "MIT",
            "confidence": "license_expression",
            "evidence": {"locator": "dependencies.example-pkg-a", "line": 3},
        }],
        "pending_confirmation": [],
    })
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "distribute-binary",
        "--outbound-license", "MIT", "--scenario-note", "分发二进制",
        "--out-dir", str(tmp_path / "out"),
    ])
    assert code == EXIT_FINDINGS, out + err
    conflicts = read_json(str(tmp_path / "out" / "conflicts.json"))
    assert all(
        record["resolution"] == "compatible" for record in conflicts["outbound_conflicts"]
    )
    payload = read_json(str(tmp_path / "out" / "actions.json"))
    assert payload["actions"][0]["level"] is None
    assert payload["pending_confirmation"]


def test_report_command_returns_one_for_blocking_levels(tmp_path, capsys):
    """``report`` 的退出码与处置分级联动（plan/03 §5.5）。"""
    code, _payload, text = _assess_with(tmp_path, "GPL-2.0-only", "MIT")
    assert code == EXIT_FINDINGS, text
    code, out, err = run(["report", "--out-dir", str(tmp_path / "out")], capsys)
    assert code == EXIT_FINDINGS, out + err


# ---------------------------------------------------------------------------
# 真值与基准
# ---------------------------------------------------------------------------


def test_action_truth_is_a_projection_of_the_curated_table():
    truth = read_json(TRUTH_PATH)
    curated = read_json(os.path.join(CURATED_DIR, "action-rules.json"))
    assert truth["format"] == "licaudit-actions-truth"
    assert truth["inputs"]["obligation_axes"] == curated["obligation_axes"]
    assert truth["inputs"]["rule_ids"] == [entry["id"] for entry in curated["entries"]]
    assert "observed_" not in read_text(TRUTH_PATH)


def test_action_truth_covers_every_level_and_every_reachable_axis_set():
    truth = read_json(TRUTH_PATH)
    levels = truth["expect"]["levels"]
    assert set(levels) == set(contract.ACTION_LEVELS)
    rows = truth["expect"]["matrix"]
    axis_sets = {tuple(row["axes"]) for row in rows}
    assert axis_sets == {tuple(item) for item in truth["inputs"]["reachable_axes"]}
    assert truth["expect"]["coverage"]["uncovered"] == 0
    assert truth["expect"]["coverage"]["dead_rules"] == []


def test_bench_m5_passes(capsys):
    code, out, err = run(["bench", "--only", "m5"], capsys)
    assert code == EXIT_OK, out + err
    assert "[OK] m5" in out


def test_bench_m5_turns_red_when_truth_drifts(tmp_path, capsys):
    """阴性对照：改一条真值里的期望级别 → ``bench m5`` 必须变红。"""
    data_dir = tmp_path / "data"
    (data_dir / "truth").mkdir(parents=True)
    payload = read_json(TRUTH_PATH)
    for row in payload["expect"]["matrix"]:
        if row["level"] == "ok":
            row["level"] = "isolate"
            break
    (data_dir / "truth" / "actions.json").write_text(
        dumps_json(payload), encoding="utf-8"
    )
    code, out, err = run(["bench", "--only", "m5", "--data-dir", str(data_dir)], capsys)
    assert code == EXIT_FINDINGS, out + err
    assert "[FAIL] m5" in out


def test_bench_m5_without_action_truth_is_usage_error(tmp_path, capsys):
    empty = tmp_path / "data"
    (empty / "truth").mkdir(parents=True)
    code, out, err = run(["bench", "--only", "m5", "--data-dir", str(empty)], capsys)
    assert code == EXIT_USAGE
    assert "处置真值" in err


def test_gen_action_truth_check_detects_handedit(tmp_path):
    import subprocess
    import sys

    target = tmp_path / "actions.json"
    target.write_text(
        read_text(TRUTH_PATH).replace('"level": "ok"', '"level": "isolate"', 1),
        encoding="utf-8",
    )
    result = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "tools", "gen_action_truth.py"),
         "--check", "--out", str(target)],
        cwd=REPO_ROOT,
        env=dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
    )
    text = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
    assert result.returncode == 1, text
    assert "[FAIL]" in text


def test_gen_action_truth_check_passes():
    import subprocess
    import sys

    result = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "tools", "gen_action_truth.py"), "--check"],
        cwd=REPO_ROOT,
        env=dict(os.environ, PYTHONUTF8="1", PYTHONDONTWRITEBYTECODE="1"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
    )
    text = result.stdout.decode("utf-8", "replace")
    assert result.returncode == 0, text
    assert "逐字节一致" in text


def test_action_engine_does_not_reimport_scenario_or_conflict_judgements():
    """处置分级只读上游产物字段：模块不 import 场景 / 冲突引擎（零判定复用）。"""
    source = read_text(os.path.join(REPO_ROOT, "src", "licaudit", "assess", "action.py"))
    assert "from .scenario" not in source
    assert "from .conflict" not in source


def test_example_project_covers_four_levels_across_the_two_runs():
    """示例项目的两份报告合起来覆盖四级处置（单场景下四级无法同时出现）。"""
    found = set()
    for name in ("license-report.csv", "license-report-distribute.csv"):
        text = read_text(os.path.join(REPO_ROOT, "examples", "report", name))
        header = text.split("\n", 1)[0].split(",")
        index = header.index("action_level")
        for line in text.split("\n")[1:]:
            if not line.strip():
                continue
            cells = line.split(",")
            if index < len(cells) and cells[index]:
                found.add(cells[index])
    assert found == set(contract.ACTION_LEVELS)


def test_example_reports_are_present_and_clean():
    for name in ("license-report.md", "license-report.csv",
                 "license-report-distribute.md", "license-report-distribute.csv"):
        path = os.path.join(REPO_ROOT, "examples", "report", name)
        assert os.path.isfile(path), name
    raw = open(os.path.join(REPO_ROOT, "examples", "report", "license-report.csv"), "rb").read()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
