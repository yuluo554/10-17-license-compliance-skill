# -*- coding: utf-8 -*-
"""M4 冲突与兼容性分析：无向查表、表达式求值、outbound 判定、真值对账。

这些测试刻意不"回放"引擎输出：冲突对期望值来自 ``references/curated/conflict-pairs.json``
（规则表是唯一真相），档位期望值来自 ``references/curated/tiers.json``。
"""

import io
import json
import os
import shutil

import pytest

from _helpers import REPO_ROOT, make_ruleset_dir, write_json

from licaudit import cli, contract
from licaudit.assess import conflict as conflict_mod
from licaudit.assess import profile as profile_mod
from licaudit.assess import scenario as scenario_mod
from licaudit.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE
from licaudit.ruleset import loader, load_ruleset
from licaudit.serialize import dumps_json

DATA_DIR = os.path.join(REPO_ROOT, "data")
SPDX_DIR = os.path.join(REPO_ROOT, "references", "spdx")
CURATED_DIR = os.path.join(REPO_ROOT, "references", "curated")
TRUTH_PATH = os.path.join(DATA_DIR, "truth", "conflicts.json")


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


def _curated_pairs():
    payload = read_json(os.path.join(CURATED_DIR, "conflict-pairs.json"))
    return {entry["pair_id"]: entry for entry in payload["entries"]}


def _curated_tiers():
    payload = read_json(os.path.join(CURATED_DIR, "tiers.json"))
    return {entry["license_id"]: entry for entry in payload["entries"]}


def _snapshot_license_ids():
    payload = read_json(os.path.join(SPDX_DIR, "licenses.json"))
    return {item["licenseId"] for item in payload["licenses"]}


def _inventory_with(tmp_path, spdx_ids, name="inventory.json"):
    os.makedirs(str(tmp_path), exist_ok=True)
    path = tmp_path / name
    write_json(str(path), {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "dependencies": [
            {
                "package": "example-pkg-{0:03d}".format(index),
                "version": "1.0.0",
                "raw_license": spdx_id,
                "spdx_id": spdx_id,
                "confidence": "license_expression",
                # 五锚点齐全（M5 起处置分级要求声明位置可定位）：
                # 缺 file/locator 的清单会在处置层降级为待确认，从而把「全相容 → 0」的
                # 用例变成 exit 1，掩盖 M4 要验的冲突语义。
                "evidence": {
                    "file": "package.json",
                    "locator": "dependencies.example-pkg-{0:03d}".format(index),
                    "line": 3 + index,
                    "ruleset_version": "r0.1.0",
                    "details_url": None,
                },
            }
            for index, spdx_id in enumerate(spdx_ids)
        ],
        "pending_confirmation": [],
    })
    return str(path)


def _assess(tmp_path, spdx_ids, outbound, scenario="distribute-binary", capsys=None,
            extra=()):
    inventory = _inventory_with(tmp_path, spdx_ids)
    argv = [
        "assess", "--inventory", inventory, "--scenario", scenario,
        "--outbound-license", outbound, "--scenario-note", "用例",
        "--out-dir", str(tmp_path / "out"),
    ]
    argv.extend(extra)
    code, out, err = run(argv, capsys)
    artifact = tmp_path / "out" / "conflicts.json"
    if not os.path.isfile(str(artifact)):
        # 输入被拒（exit 2）时不该写出任何产物
        return code, None, out + err
    return code, read_json(str(artifact)), out + err


def _tier_map(profile_payload):
    return {
        item["spdx_id"]: item.get("tier")
        for item in profile_payload.get("profiles") or []
    }


def _license_level(payload):
    """许可证级结论（不含证据里的包名归属），用于跨清单顺序比对。"""
    return {
        "dependency": [
            (item["pair_id"], item["left"], item["right"], item["resolution"], item["basis"])
            for item in payload["dependency_conflicts"]
        ],
        "outbound": [
            (item["left"], item["right"], item["resolution"], item["basis"])
            for item in payload["outbound_conflicts"]
        ],
    }


@pytest.fixture(scope="module")
def output(tmp_path_factory):
    """真实规则包 + 真实快照：GPL-2.0-only / Apache-2.0 / MIT OR GPL-3.0-only + MIT outbound。"""
    out_dir = tmp_path_factory.mktemp("conflict")
    inventory = os.path.join(str(out_dir), "inventory.json")
    write_json(inventory, {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "dependencies": [
            {
                "package": "example-pkg-{0:03d}".format(index),
                "version": "1.0.0",
                "raw_license": spdx_id,
                "spdx_id": spdx_id,
                "confidence": "license_expression",
                "evidence": {"ruleset_version": "r0.1.0", "details_url": None},
            }
            for index, spdx_id in enumerate(
                ["GPL-2.0-only", "Apache-2.0", "MIT OR GPL-3.0-only"]
            )
        ],
        "pending_confirmation": [],
    })
    code = cli.main([
        "assess", "--inventory", inventory, "--scenario", "distribute-binary",
        "--outbound-license", "MIT", "--scenario-note", "分发二进制",
        "--out-dir", str(out_dir),
    ])
    # 依赖间冲突（GPL-2.0-only × Apache-2.0）与 GPL-2.0-only 对 MIT outbound 都不兼容 → 1
    assert code == EXIT_FINDINGS
    return out_dir, read_json(os.path.join(str(out_dir), "conflicts.json")), inventory


# ---------------------------------------------------------------------------
# 契约形态与确定性
# ---------------------------------------------------------------------------


def test_conflict_record_field_order_matches_contract(output):
    _out_dir, payload, _inventory = output
    assert payload["format"] == contract.CONFLICT_FORMAT
    assert payload["format_version"] == contract.FORMAT_VERSION
    assert payload["dependency_conflicts"]
    assert payload["outbound_conflicts"]
    for record in payload["dependency_conflicts"] + payload["outbound_conflicts"]:
        assert tuple(record) == contract.CONFLICT_FIELDS
        assert record["resolution"] in contract.CONFLICT_RESOLUTIONS
        assert record["basis"]


def test_conflict_artifact_field_order(output):
    _out_dir, payload, _inventory = output
    assert tuple(payload) == conflict_mod.CONFLICT_TOP_LEVEL_FIELDS


def test_conflicts_json_is_byte_stable_across_two_runs(output, tmp_path):
    out_dir, payload, inventory = output
    second = tmp_path / "second"
    code = cli.main([
        "assess", "--inventory", inventory, "--scenario", "distribute-binary",
        "--outbound-license", "MIT", "--scenario-note", "分发二进制",
        "--out-dir", str(second),
    ])
    assert code == EXIT_FINDINGS
    first_text = io.open(
        os.path.join(str(out_dir), "conflicts.json"), encoding="utf-8"
    ).read()
    second_text = io.open(str(second / "conflicts.json"), encoding="utf-8").read()
    assert first_text == second_text
    assert first_text == dumps_json(payload)
    assert first_text.endswith("\n")


def test_conflict_records_declare_the_curated_basis(output):
    """依赖间冲突必须挂规则表的 ``basis`` 与可定位锚点，不允许引擎自己编依据。"""
    _out_dir, payload, _inventory = output
    curated = _curated_pairs()
    for record in payload["dependency_conflicts"]:
        entry = curated[record["pair_id"]]
        assert record["basis"] == entry["basis"]
        assert record["left"] == entry["left"] and record["right"] == entry["right"]
        assert record["resolution"] == entry["resolution"]
        assert record["evidence"]["anchor"] == entry["anchor"]
        assert record["evidence"]["checked_on"] == entry["checked_on"]


# ---------------------------------------------------------------------------
# 依赖间冲突：已知对全命中、无向匹配、未登记组合
# ---------------------------------------------------------------------------


def test_every_curated_pair_is_hit_with_its_curated_resolution(tmp_path, capsys):
    curated = _curated_pairs()
    for pair_id, entry in sorted(curated.items()):
        code, payload, err = _assess(
            tmp_path / pair_id, [entry["left"], entry["right"]], "pending", capsys=capsys
        )
        records = {item["pair_id"]: item for item in payload["dependency_conflicts"]}
        assert pair_id in records, (pair_id, err)
        assert records[pair_id]["resolution"] == entry["resolution"]
        assert (records[pair_id]["left"], records[pair_id]["right"]) == (
            entry["left"], entry["right"],
        )


def test_known_pair_gpl2_apache2_is_incompatible(tmp_path, capsys):
    """DoD 点名的一条：``GPL-2.0-only × Apache-2.0`` 必须命中且为不兼容。"""
    _code, payload, _err = _assess(
        tmp_path, ["GPL-2.0-only", "Apache-2.0"], "pending", capsys=capsys
    )
    record = next(
        item for item in payload["dependency_conflicts"]
        if item["pair_id"] == "CP-GPL2-APACHE2"
    )
    assert record["resolution"] == "incompatible"
    assert record["evidence"]["anchor"]["ref"].startswith("texts/")
    assert record["evidence"]["packages"] == {
        "GPL-2.0-only": ["example-pkg-000"],
        "Apache-2.0": ["example-pkg-001"],
    }


def test_pair_matching_is_undirected():
    """``(left, right)`` 与 ``(right, left)`` 等价（K15）。"""
    ruleset = load_ruleset()
    lookup = conflict_mod.pair_lookup(ruleset.entries("conflict-pairs.json"))
    for key in sorted(lookup):
        left, right = key
        assert lookup[conflict_mod.pair_key(left, right)] is lookup[
            conflict_mod.pair_key(right, left)
        ]


def test_undirected_matching_survives_record_order(tmp_path, capsys):
    """清单里两条依赖的先后顺序不得改变结论（包名归属会变，许可证级结论不变）。"""
    _code, forward, _err = _assess(
        tmp_path / "a", ["GPL-2.0-only", "Apache-2.0"], "pending", capsys=capsys
    )
    _code, backward, _err = _assess(
        tmp_path / "b", ["Apache-2.0", "GPL-2.0-only"], "pending", capsys=capsys
    )
    assert _license_level(forward) == _license_level(backward)


def test_licenses_with_the_same_id_are_one_group(tmp_path, capsys):
    """同一许可证的多条依赖归并成一条条目，包名全部登记在证据里。"""
    _code, payload, _err = _assess(
        tmp_path, ["GPL-2.0-only", "Apache-2.0", "Apache-2.0"], "pending", capsys=capsys
    )
    record = next(
        item for item in payload["dependency_conflicts"]
        if item["pair_id"] == "CP-GPL2-APACHE2"
    )
    assert record["evidence"]["packages"]["Apache-2.0"] == [
        "example-pkg-001", "example-pkg-002",
    ]


def test_uncovered_license_pairs_are_counted_not_judged(tmp_path, capsys):
    """未登记的许可证组合不产出冲突条目，只计覆盖度（不改退出码）。"""
    _code, payload, _err = _assess(
        tmp_path, ["AGPL-3.0-only", "Apache-2.0"], "MIT", capsys=capsys
    )
    assert payload["dependency_conflicts"] == []
    uncovered = payload["uncovered_pairs"]
    assert uncovered["count"] == 1
    assert uncovered["items"] == [["AGPL-3.0-only", "Apache-2.0"]]
    assert uncovered["items_truncated"] is False


# ---------------------------------------------------------------------------
# 表达式求值（K16）
# ---------------------------------------------------------------------------


def _evaluation(payload, expression, source="dependency"):
    for item in payload["expression_evaluations"]:
        if item["expression"] == expression and item["source"] == source:
            return item
    raise AssertionError("缺少求值记录：{0}".format(expression))


def test_or_takes_the_most_permissive_atom(tmp_path, capsys):
    _code, payload, _err = _assess(
        tmp_path, ["MIT OR GPL-3.0-only"], "pending", capsys=capsys
    )
    evaluation = _evaluation(payload, "MIT OR GPL-3.0-only")
    assert evaluation["operator"] == "OR"
    assert evaluation["atoms"] == ["MIT", "GPL-3.0-only"]
    assert evaluation["selected"] == "MIT"
    assert evaluation["tier"] == "permissive"
    assert evaluation["resolved"] is True
    assert "OR" in evaluation["reason"]


def test_and_takes_the_strictest_atom(tmp_path, capsys):
    _code, payload, _err = _assess(
        tmp_path, ["MIT AND GPL-3.0-only"], "pending", capsys=capsys
    )
    evaluation = _evaluation(payload, "MIT AND GPL-3.0-only")
    assert evaluation["operator"] == "AND"
    assert evaluation["selected"] == "GPL-3.0-only"
    assert evaluation["tier"] == "strong-copyleft"


def test_nested_expression_evaluates_recursively(tmp_path, capsys):
    """``(MIT OR Apache-2.0) AND GPL-3.0-only`` → 内层取最宽松，外层取最严格。"""
    _code, payload, _err = _assess(
        tmp_path, ["(MIT OR Apache-2.0) AND GPL-3.0-only"], "pending", capsys=capsys
    )
    evaluation = _evaluation(payload, "(MIT OR Apache-2.0) AND GPL-3.0-only")
    assert evaluation["atoms"] == ["MIT", "Apache-2.0", "GPL-3.0-only"]
    assert evaluation["selected"] == "GPL-3.0-only"
    assert evaluation["tier"] == "strong-copyleft"


def test_with_expression_keeps_the_exception_label(tmp_path, capsys):
    """``WITH`` 例外不改变档位，但要留在求值记录里。"""
    _code, payload, _err = _assess(
        tmp_path, ["MIT OR (GPL-2.0-only WITH Classpath-exception-2.0)"],
        "pending", capsys=capsys,
    )
    evaluation = _evaluation(
        payload, "MIT OR (GPL-2.0-only WITH Classpath-exception-2.0)"
    )
    assert evaluation["atoms"] == ["MIT", "GPL-2.0-only"]
    assert evaluation["exceptions"] == ["Classpath-exception-2.0"]
    assert evaluation["selected"] == "MIT"


def test_expression_with_uncovered_atom_is_not_evaluated(tmp_path, capsys):
    """缺档位的原子无法比较 → ``resolved = false``，不猜（K7/K31）。"""
    _code, payload, _err = _assess(
        tmp_path, ["MIT OR BlueOak-1.0.0"], "MIT", capsys=capsys
    )
    evaluation = _evaluation(payload, "MIT OR BlueOak-1.0.0")
    assert evaluation["resolved"] is False
    assert evaluation["selected"] is None
    assert evaluation["tier"] is None
    assert "BlueOak-1.0.0" in evaluation["reason"]
    # 求值不了 → 该依赖的 outbound 条目待定，并写明原因
    record = next(
        item for item in payload["outbound_conflicts"]
        if item["evidence"]["node_spdx_id"] is None
    )
    assert record["resolution"] == "pending"
    pending = {item["pair_id"]: item for item in payload["pending_confirmation"]}
    assert "expression_unresolved" in pending[record["pair_id"]]["reasons"]


def test_single_atom_records_are_not_evaluated(tmp_path, capsys):
    _code, payload, _err = _assess(tmp_path, ["MIT", "GPL-3.0-only"], "MIT", capsys=capsys)
    dependencies = [
        item for item in payload["expression_evaluations"] if item["source"] == "dependency"
    ]
    assert dependencies == []
    # outbound 本身的求值记录保留（说明档位是怎么来的）
    outbound = [item for item in payload["expression_evaluations"] if item["source"] == "outbound"]
    assert outbound and outbound[0]["operator"] == "single"


def test_evaluated_atom_drives_the_outbound_verdict(tmp_path, capsys):
    """``MIT OR GPL-3.0-only`` 求值为 MIT → 与 MIT outbound 相容。"""
    _code, payload, _err = _assess(
        tmp_path, ["MIT OR GPL-3.0-only"], "MIT", capsys=capsys
    )
    record = next(
        item for item in payload["outbound_conflicts"]
        if item["evidence"]["node_spdx_id"] == "MIT"
    )
    assert record["resolution"] == "compatible"
    # 原始表达式也留在证据里，便于审计
    assert record["evidence"]["node_raw_spdx_ids"] == ["MIT OR GPL-3.0-only"]


# ---------------------------------------------------------------------------
# 依赖 × outbound
# ---------------------------------------------------------------------------


def test_outbound_pending_makes_every_entry_pending(tmp_path, capsys):
    code, payload, _err = _assess(
        tmp_path, ["MIT", "GPL-2.0-only", "Elastic-2.0"], "pending", capsys=capsys
    )
    assert code == EXIT_FINDINGS
    assert payload["outbound_tier"] is None
    assert payload["outbound_conflicts"]
    for record in payload["outbound_conflicts"]:
        assert record["resolution"] == "pending"
        assert record["basis"] == conflict_mod.BASIS_OUTBOUND_PENDING
    pending = {item["pair_id"] for item in payload["pending_confirmation"]}
    for record in payload["outbound_conflicts"]:
        assert record["pair_id"] in pending


def test_all_compatible_exits_zero(tmp_path, capsys):
    """全部相容时退出码必须是 0：1 只用于「待定/不兼容」，不能被滥用成常态。"""
    code, payload, err = _assess(tmp_path, ["MIT", "Apache-2.0"], "MIT", capsys=capsys)
    assert code == EXIT_OK, err
    assert payload["pending_confirmation"] == []
    assert all(
        item["resolution"] == "compatible" for item in payload["outbound_conflicts"]
    )
    assert conflict_mod.has_blocking_finding(payload) is False


def test_stronger_dependency_than_outbound_is_incompatible(tmp_path, capsys):
    """GPL 依赖 + MIT outbound → 不兼容（plan/03 §4.5）。"""
    code, payload, _err = _assess(tmp_path, ["GPL-2.0-only"], "MIT", capsys=capsys)
    assert code == EXIT_FINDINGS
    record = payload["outbound_conflicts"][0]
    assert record["resolution"] == "incompatible"
    assert "强于" in record["basis"]
    assert conflict_mod.has_blocking_finding(payload) is True


def test_same_license_rule_flags_a_different_outbound(tmp_path, capsys):
    """同档位但依赖要求 ``same-license`` 而 outbound 选了别的许可证 → 不兼容。"""
    _code, payload, _err = _assess(tmp_path, ["GPL-3.0-only"], "GPL-2.0-only", capsys=capsys)
    record = payload["outbound_conflicts"][0]
    assert record["resolution"] == "incompatible"
    assert "same-license" in record["basis"]


def test_same_license_rule_does_not_flag_a_stricter_outbound(tmp_path, capsys):
    """GPLv3 代码合并进 AGPLv3 由 AGPL §13 明文允许 → 不因 same-license 判不兼容。"""
    _code, payload, _err = _assess(tmp_path, ["GPL-3.0-only"], "AGPL-3.0-only", capsys=capsys)
    record = payload["outbound_conflicts"][0]
    assert record["resolution"] == "compatible"


def test_same_license_and_same_license_id_is_compatible(tmp_path, capsys):
    _code, payload, _err = _assess(tmp_path, ["GPL-2.0-only"], "GPL-2.0-only", capsys=capsys)
    assert payload["outbound_conflicts"][0]["resolution"] == "compatible"


def test_uncovered_license_is_pending_not_guessed(tmp_path, capsys):
    code, payload, _err = _assess(tmp_path, ["BlueOak-1.0.0"], "MIT", capsys=capsys)
    assert code == EXIT_FINDINGS
    record = payload["outbound_conflicts"][0]
    assert record["resolution"] == "pending"
    assert record["evidence"]["node_tier"] is None
    reasons = payload["pending_confirmation"][0]["reasons"]
    assert "tier_unavailable" in reasons


def test_outbound_expression_is_evaluated_to_a_tier(tmp_path, capsys):
    """outbound 是表达式时按同一套求值规则定档（OR 最宽松）。"""
    _code, payload, _err = _assess(
        tmp_path, ["GPL-3.0-only"], "MIT OR GPL-3.0-only", capsys=capsys
    )
    assert payload["outbound_tier"] == "permissive"
    evaluation = _evaluation(payload, "MIT OR GPL-3.0-only", source="outbound")
    assert evaluation["selected"] == "MIT"
    record = payload["outbound_conflicts"][0]
    assert record["resolution"] == "incompatible"


def test_outbound_license_absent_from_inventory_still_gets_a_tier(tmp_path, capsys):
    """outbound 用的许可证不在依赖里时，档位由规则包现算（不能因为没画像就待定）。"""
    index, version = profile_mod.load_context(SPDX_DIR)
    ruleset = load_ruleset()
    profile_payload = profile_mod.profile_ids(["GPL-2.0-only"], ruleset, index, version)
    assert "MIT" not in _tier_map(profile_payload)
    inventory = {
        "dependencies": [{"package": "example-pkg-000", "spdx_id": "GPL-2.0-only"}],
        "pending_confirmation": [],
    }
    payload = conflict_mod.build_conflicts(
        inventory, profile_payload, ruleset, "MIT", spdx_index=index
    )
    assert payload["outbound_tier"] == "permissive"
    assert payload["outbound_conflicts"][0]["resolution"] == "incompatible"


def test_unknown_outbound_id_is_still_a_usage_error(tmp_path, capsys):
    """outbound 校验复用 M3 的 ``validate_outbound``：未知 ID → exit 2（K17 前段）。"""
    code, _payload, err = _assess(
        tmp_path, ["MIT"], "Not-A-Real-License", capsys=capsys
    )
    assert code == EXIT_USAGE
    assert "outbound" in err


def test_scenario_context_is_recorded_but_not_used_for_judgement(tmp_path, capsys):
    """场景上下文只落盘；同一批依赖换个场景，冲突结论一字不变。"""
    _code, internal, _err = _assess(tmp_path / "x", ["GPL-2.0-only"], "MIT",
                                    scenario="internal", capsys=capsys)
    _code, binary, _err = _assess(tmp_path / "y", ["GPL-2.0-only"], "MIT",
                                  scenario="distribute-binary", capsys=capsys)
    assert internal["scenario"] == "internal"
    assert binary["scenario"] == "distribute-binary"
    assert internal["outbound_conflicts"] == binary["outbound_conflicts"]


# ---------------------------------------------------------------------------
# 规则表：锚点门、ID 成员、disabled 第二道门
# ---------------------------------------------------------------------------


def test_every_conflict_pair_passes_the_anchor_gate():
    ruleset = load_ruleset()
    entries = ruleset.entries("conflict-pairs.json")
    assert entries
    assert ruleset.disabled == []
    for entry in entries:
        assert entry["verified"] is True
        assert entry["checked_on"]
        assert entry["anchor"]["ref"].startswith("texts/")
        assert entry["anchor"]["quote"]
        assert entry["resolution"] in contract.CONFLICT_RESOLUTIONS
        assert entry["basis"]


def test_conflict_pair_anchors_are_locatable_in_snapshots():
    ruleset = load_ruleset()
    problems = []
    for entry in ruleset.entries("conflict-pairs.json"):
        relative = entry["anchor"]["ref"].split("#", 1)[0]
        path = os.path.join(SPDX_DIR, relative.replace("/", os.sep))
        if not os.path.isfile(path):
            problems.append("{0}: 全文缺失 {1}".format(entry["pair_id"], relative))
            continue
        text = read_json(path).get("licenseText") or ""
        quote = " ".join(entry["anchor"]["quote"].split())
        if quote not in " ".join(text.split()):
            problems.append("{0}: quote 无法定位".format(entry["pair_id"]))
    assert not problems, "; ".join(problems)


def test_pair_ids_and_unordered_combinations_are_unique():
    payload = read_json(
        os.path.join(REPO_ROOT, "references", "ruleset", "conflict-pairs.json")
    )
    ids = [entry["pair_id"] for entry in payload["entries"]]
    assert len(ids) == len(set(ids))
    keys = [conflict_mod.pair_key(entry["left"], entry["right"]) for entry in payload["entries"]]
    assert len(keys) == len(set(keys)), "无向组合不得重复登记（K15）"


def test_pair_licenses_exist_in_the_spdx_snapshot():
    known = _snapshot_license_ids()
    for entry in _curated_pairs().values():
        assert entry["left"] in known, entry["pair_id"]
        assert entry["right"] in known, entry["pair_id"]


def test_ruleset_pairs_are_a_projection_of_the_curated_table():
    curated = _curated_pairs()
    ruleset = load_ruleset()
    entries = {entry["pair_id"]: entry for entry in ruleset.entries("conflict-pairs.json")}
    assert set(entries) == set(curated)
    for pair_id, entry in entries.items():
        source = curated[pair_id]
        assert entry["left"] == source["left"]
        assert entry["right"] == source["right"]
        assert entry["resolution"] == source["resolution"]
        assert entry["basis"] == source["basis"]
        assert entry["anchor"] == source["anchor"]
        assert entry["checked_on"] == source["checked_on"]


def test_unverified_pair_is_rejected_by_the_loader_and_ignored_by_the_engine(tmp_path):
    """K10 第二道门：规则表未核验/缺锚点时，引擎不得使用该条目。"""
    entry = {
        "pair_id": "CP-BROKEN-001",
        "left": "GPL-2.0-only",
        "right": "Apache-2.0",
        "resolution": "incompatible",
        "basis": "伪造条目",
        "anchor": {"source": "license-text", "ref": "texts/GPL-2.0-only.json#licenseText"},
        "verified": False,
        "checked_on": "2026-10-17",
    }
    index, version = profile_mod.load_context(SPDX_DIR)
    ruleset = load_ruleset()

    class FakeRuleset(object):
        version = "r-test"
        disabled = []

        def entries(self, name):
            return [entry] if name == conflict_mod.CONFLICT_RULE_FILE else []

    inventory = {
        "dependencies": [
            {"package": "example-pkg-000", "spdx_id": "GPL-2.0-only"},
            {"package": "example-pkg-001", "spdx_id": "Apache-2.0"},
        ],
        "pending_confirmation": [],
    }
    payload = conflict_mod.build_conflicts(
        inventory, profile_mod.profile_ids(["GPL-2.0-only", "Apache-2.0"], ruleset, index, version),
        FakeRuleset(), "pending", spdx_index=index,
    )
    assert payload["dependency_conflicts"] == []
    assert payload["uncovered_pairs"]["count"] == 1


def test_pair_entry_without_anchor_is_ignored():
    entry = {
        "pair_id": "CP-NOANCHOR-001",
        "left": "GPL-2.0-only",
        "right": "Apache-2.0",
        "resolution": "incompatible",
        "basis": "缺锚点",
        "verified": True,
        "checked_on": "2026-10-17",
    }
    assert conflict_mod.usable_pairs([entry]) == []


def test_engine_bypassing_loader_still_respects_disabled_pairs(tmp_path):
    """直接构造规则包对象（未经 loader）时，未核验条目同样不得参与判定。"""
    make_ruleset_dir(str(tmp_path / "rs"))
    root = str(tmp_path / "rs")
    path = os.path.join(root, "conflict-pairs.json")
    payload = read_json(path)
    payload["entries"][0]["verified"] = False
    write_json(path, payload)
    manifest_path = os.path.join(root, "manifest.json")
    manifest = read_json(manifest_path)
    manifest["files"]["conflict-pairs.json"] = loader.sha256_file(path)
    write_json(manifest_path, manifest)

    ruleset = load_ruleset(explicit=root)
    assert [item.get("id") for item in ruleset.disabled] == ["CP-GPL2-APACHE2"]
    assert ruleset.entries("conflict-pairs.json") == []


# ---------------------------------------------------------------------------
# 真值与基准
# ---------------------------------------------------------------------------


def test_conflict_truth_declares_inputs_and_expectations():
    payload = read_json(TRUTH_PATH)
    assert payload["format"] == "licaudit-conflicts-truth"
    assert payload["format_version"] == contract.FORMAT_VERSION
    inputs = payload["inputs"]
    assert inputs["pair_ids"]
    assert inputs["pair_sample_licenses"]
    assert inputs["evaluation_expressions"]
    assert inputs["tier_by_atom"]
    assert inputs["outbound_pending_value"] == "pending"
    expect = payload["expect"]
    assert expect["pairs"]
    assert expect["evaluations"]
    assert "uncovered_pairs" in expect
    assert expect["outbound_pending"]["resolution"] == "pending"
    text = io.open(TRUTH_PATH, encoding="utf-8").read()
    assert "observed_" not in text


def test_conflict_truth_is_a_projection_of_the_curated_table():
    truth = read_json(TRUTH_PATH)
    curated = _curated_pairs()
    assert set(truth["inputs"]["pair_ids"]) == set(curated)
    for row in truth["expect"]["pairs"]:
        entry = curated[row["pair_id"]]
        assert row["left"] == entry["left"]
        assert row["right"] == entry["right"]
        assert row["resolution"] == entry["resolution"]
    # 档位侧同样是 curated 的投影
    tiers = _curated_tiers()
    for atom, tier in truth["inputs"]["tier_by_atom"].items():
        assert tiers.get(atom, {}).get("tier") == tier


def test_conflict_truth_covers_all_three_sides():
    """三侧覆盖：已知冲突对（含 GPL-2.0-only × Apache-2.0）、OR/AND 求值、outbound 待定。"""
    expect = read_json(TRUTH_PATH)["expect"]
    pairs = {(item["left"], item["right"]): item for item in expect["pairs"]}
    assert ("GPL-2.0-only", "Apache-2.0") in pairs
    assert pairs[("GPL-2.0-only", "Apache-2.0")]["resolution"] == "incompatible"
    operators = {item["operator"] for item in expect["evaluations"]}
    assert "OR" in operators and "AND" in operators
    assert any(item["resolved"] is False for item in expect["evaluations"])
    assert expect["uncovered_pairs"]
    assert expect["outbound_pending"]["basis"] == conflict_mod.BASIS_OUTBOUND_PENDING


def test_gen_conflict_truth_check_passes():
    import subprocess
    import sys

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "tools", "gen_conflict_truth.py"), "--check"],
        cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=300,
    )
    text = result.stdout.decode("utf-8", "replace")
    assert result.returncode == 0, text
    assert "逐字节一致" in text


def test_gen_conflict_truth_check_detects_handedit(tmp_path):
    import subprocess
    import sys

    target = tmp_path / "conflicts.json"
    target.write_text(
        io.open(TRUTH_PATH, encoding="utf-8").read().replace(
            '"resolution": "compatible"', '"resolution": "incompatible"', 1
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "tools", "gen_conflict_truth.py"),
         "--check", "--out", str(target)],
        cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=300,
    )
    text = result.stdout.decode("utf-8", "replace")
    assert result.returncode == 1, text
    assert "[FAIL]" in text


def test_bench_m4_passes(capsys):
    code, out, err = run(["bench", "--only", "m4"], capsys)
    assert code == EXIT_OK, out + err
    assert "[OK] m4" in out


def test_bench_m4_turns_red_when_truth_drifts(tmp_path, capsys):
    """把冲突真值的一条 resolution 改坏 → bench m4 必须变红。"""
    shutil.copytree(DATA_DIR, str(tmp_path / "data"))
    truth_path = tmp_path / "data" / "truth" / "conflicts.json"
    payload = read_json(str(truth_path))
    payload["expect"]["pairs"][0]["resolution"] = "pending"
    write_json(str(truth_path), payload)
    code, out, err = run(
        ["bench", "--only", "m4", "--data-dir", str(tmp_path / "data")], capsys
    )
    assert code == EXIT_FINDINGS, out + err
    assert "[FAIL]" in out


def test_bench_m4_turns_red_when_truth_gains_observed_field(tmp_path, capsys):
    shutil.copytree(DATA_DIR, str(tmp_path / "data"))
    truth_path = tmp_path / "data" / "truth" / "conflicts.json"
    payload = read_json(str(truth_path))
    payload["expect"]["evaluations"][0]["observed_selected"] = "MIT"
    write_json(str(truth_path), payload)
    code, out, err = run(
        ["bench", "--only", "m4", "--data-dir", str(tmp_path / "data")], capsys
    )
    assert code == EXIT_FINDINGS
    assert "observed_" in out


def test_expression_scenario_backfill_matches_the_conflict_evaluation(tmp_path, capsys):
    """D32：scenario 与 conflicts 对同一条表达式使用同一套求值结论。"""
    out_dir = tmp_path / "out"
    inventory = _inventory_with(tmp_path, ["MIT OR GPL-3.0-only"])
    code = cli.main([
        "assess", "--inventory", inventory, "--scenario", "distribute-binary",
        "--outbound-license", "MIT", "--scenario-note", "分发二进制",
        "--out-dir", str(out_dir),
    ])
    assert code == EXIT_OK
    scenario_payload = read_json(str(out_dir / "scenario.json"))
    conflict_payload = read_json(str(out_dir / "conflicts.json"))
    scenario_choice = scenario_payload["entries"][0]["evidence"]["expression_evaluation"]
    conflict_choice = _evaluation(conflict_payload, "MIT OR GPL-3.0-only")
    assert scenario_choice["selected"] == conflict_choice["selected"] == "MIT"
    assert scenario_payload["entries"][0]["verdict"] == "not_triggered"


def test_scenario_module_shares_the_evaluation_implementation():
    """求值只有一份实现：场景引擎直接用冲突引擎的函数（plan/05 K16 落点）。"""
    assert scenario_mod.evaluate_expression is conflict_mod.evaluate_expression
