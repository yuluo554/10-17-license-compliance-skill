# -*- coding: utf-8 -*-
"""M3 场景判定：八场景轴、触发查表、三态结论、AGPL §13、「商用非触发」、真值对账。

这些测试刻意不"回放"引擎输出：触发期望值来自 ``references/curated/scenario-triggers.json``
（规则表是唯一真相），场景轴期望来自 ``contract.SCENARIO_AXES``。
"""

import io
import json
import os
import shutil

import pytest

from _helpers import REPO_ROOT, make_ruleset_dir, write_json

from licaudit import cli, contract
from licaudit.assess import scenario as scenario_mod
from licaudit.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE
from licaudit.ruleset import load_ruleset
from licaudit.serialize import dumps_json

DATA_DIR = os.path.join(REPO_ROOT, "data")
SPDX_DIR = os.path.join(REPO_ROOT, "references", "spdx")
CURATED_DIR = os.path.join(REPO_ROOT, "references", "curated")
TRUTH_PATH = os.path.join(DATA_DIR, "truth", "scenario.json")


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


def _curated_triggers():
    payload = read_json(os.path.join(CURATED_DIR, "scenario-triggers.json"))
    return [entry for entry in payload["entries"] if entry.get("verified") is True]


def _entries():
    """真实规则包里的场景触发条目（经 loader 硬门过滤）。"""
    ruleset = load_ruleset()
    return ruleset.entries("scenario-triggers.json")


@pytest.fixture(scope="module")
def output(tmp_path_factory):
    """真实规则包 + 真实快照，跑一次 SaaS + 网络交互的全量 assess。

    用画像真值的采样 ID 构造清单，覆盖五个档位与一个未覆盖 ID。
    """
    out_dir = tmp_path_factory.mktemp("scenario")
    tier_ids = ["MIT", "LGPL-2.1-only", "GPL-3.0-only", "AGPL-3.0-only", "BlueOak-1.0.0"]
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
            for index, spdx_id in enumerate(tier_ids)
        ],
        "pending_confirmation": [],
    })
    code = cli.main([
        "assess", "--inventory", inventory,
        "--scenario", "saas", "--network-interaction", "yes",
        "--outbound-license", "pending",
        "--scenario-note", "用户原话：我们通过 Web 提供服务",
        "--out-dir", str(out_dir),
    ])
    assert code == EXIT_FINDINGS  # 未覆盖 ID（BlueOak）→ 待确认
    return out_dir, read_json(os.path.join(str(out_dir), "scenario.json")), inventory


def _inventory_with(tmp_path, spdx_ids, name="inv.json"):
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
                "evidence": {"ruleset_version": "r0.1.0", "details_url": None},
            }
            for index, spdx_id in enumerate(spdx_ids)
        ],
        "pending_confirmation": [],
    })
    return str(path)


# ---------------------------------------------------------------------------
# 场景轴与契约
# ---------------------------------------------------------------------------


def test_scenario_axes_cover_all_eight_ids():
    assert set(contract.SCENARIO_AXES) == set(contract.SCENARIO_IDS)
    assert set(contract.DELIVERIES) == {"internal", "binary", "source", "saas", "container"}
    for scenario, axes in contract.SCENARIO_AXES.items():
        assert axes["link_mode"] in contract.LINK_MODES
        assert axes["delivery"] is None or axes["delivery"] in contract.DELIVERIES


def test_scenario_record_field_order_matches_contract(output):
    _out_dir, payload, _inventory = output
    assert payload["format"] == contract.SCENARIO_FORMAT
    assert payload["format_version"] == contract.FORMAT_VERSION
    assert payload["entries"]
    for record in payload["entries"]:
        assert tuple(record) == contract.SCENARIO_FIELDS
        assert record["verdict"] in contract.VERDICTS


def test_scenario_artifact_field_order(output):
    _out_dir, payload, _inventory = output
    assert tuple(payload) == scenario_mod.SCENARIO_TOP_LEVEL_FIELDS


def test_resolve_axes_derives_scenario_from_axes():
    for scenario, axes in contract.SCENARIO_AXES.items():
        delivery, link_mode = axes["delivery"], axes["link_mode"]
        if delivery is None:
            resolved = scenario_mod.resolve_axes(scenario, delivery="binary")
            assert resolved[0] == scenario
            assert resolved[2] == link_mode
        else:
            resolved = scenario_mod.resolve_axes(scenario)
            assert resolved == (scenario, delivery, link_mode)


def test_resolve_axes_accepts_delivery_plus_linking():
    assert scenario_mod.resolve_axes(None, "binary", "none") == (
        "distribute-binary", "binary", "none",
    )
    assert scenario_mod.resolve_axes(None, "saas", "none")[0] == "saas"
    assert scenario_mod.resolve_axes(None, "binary", "static")[0] == "static-link"
    assert scenario_mod.resolve_axes(None, "container", "none")[0] == "container-image"


def test_resolve_axes_rejects_unknown_scenario():
    with pytest.raises(Exception):
        scenario_mod.resolve_axes("not-a-scenario")


def test_resolve_axes_rejects_scenario_delivery_contradiction():
    with pytest.raises(Exception):
        scenario_mod.resolve_axes("internal", delivery="binary")


def test_resolve_axes_rejects_scenario_linking_contradiction():
    with pytest.raises(Exception):
        scenario_mod.resolve_axes("static-link", linking="dynamic")


def test_resolve_axes_link_scenario_without_delivery_is_unresolved():
    assert scenario_mod.resolve_axes("static-link") == ("static-link", None, "static")


# ---------------------------------------------------------------------------
# 触发表：八场景判定表（期望值来自 curated 规则表）
# ---------------------------------------------------------------------------


def _expected(entries, tier, scenario, link_mode, network):
    hits = [
        entry for entry in entries
        if entry["tier"] == tier
        and scenario in entry["scenarios"]
        and link_mode in entry["link_modes"]
        and ("network_interaction" not in entry or (
            entry["network_interaction"] is True and network is True
        ))
    ]
    if not hits:
        return "not_triggered", [], []
    triggers = sorted({entry["trigger"] for entry in hits})
    rule_ids = sorted({entry["id"] for entry in hits if entry.get("id")})
    return "triggered", triggers, rule_ids


@pytest.mark.parametrize("tier", list(contract.TIERS))
def test_every_tier_scenario_link_combination_matches_curated_table(tier):
    entries = _entries()
    for scenario, axes in contract.SCENARIO_AXES.items():
        delivery = axes["delivery"] or "binary"
        match_scenario = scenario_mod.delivery_scenario(delivery)
        for link_mode in contract.LINK_MODES:
            for network in (None, True):
                result = scenario_mod.evaluate_tier(
                    tier, match_scenario, link_mode, network, entries
                )
                want_verdict, want_triggers, want_rules = _expected(
                    entries, tier, match_scenario, link_mode, network
                )
                context = (tier, scenario, link_mode, network)
                assert result["verdict"] == want_verdict, context
                assert result["triggers"] == want_triggers, context
                assert result["rule_ids"] == want_rules, context


def test_eight_scenarios_have_a_judgement_for_every_tier():
    """八场景 × 链接方式：每个档位都能给出三态结论之一（不崩、不漏）。"""
    entries = _entries()
    seen = 0
    for scenario, axes in contract.SCENARIO_AXES.items():
        delivery = axes["delivery"] or "binary"
        match_scenario = scenario_mod.delivery_scenario(delivery)
        for link_mode in contract.LINK_MODES:
            for tier in contract.TIERS:
                result = scenario_mod.evaluate_tier(
                    tier, match_scenario, link_mode, None, entries
                )
                assert result["verdict"] in contract.VERDICTS
                seen += 1
    assert seen == len(contract.SCENARIO_IDS) * len(contract.LINK_MODES) * len(contract.TIERS)


# ---------------------------------------------------------------------------
# 「商用」不是输入 / 不是触发条件（K12）
# ---------------------------------------------------------------------------


def test_commercial_is_not_an_input_field(output):
    _out_dir, payload, _inventory = output
    text = dumps_json(payload)
    assert "commercial" not in text
    assert "商用" not in text


def test_commercial_is_not_a_trigger_condition():
    for entry in _curated_triggers():
        assert "commercial" not in json.dumps(entry, ensure_ascii=False)
    for entry in _entries():
        assert "commercial" not in json.dumps(entry, ensure_ascii=False)


def test_cli_has_no_commercial_flag():
    parser = cli.build_parser()
    options = set()
    for action in parser._actions:
        options.update(action.option_strings)
        for choice_action in getattr(action, "choices", {}) or {}:
            sub = action.choices.get(choice_action) if isinstance(action.choices, dict) else None
            if sub is not None:
                for sub_action in sub._actions:
                    options.update(sub_action.option_strings)
    assert "--commercial" not in options


# ---------------------------------------------------------------------------
# K13：AGPL §13 独立触发点
# ---------------------------------------------------------------------------


def test_saas_agpl_with_network_interaction_triggers_network_source(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["AGPL-3.0-only"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "saas",
        "--network-interaction", "yes", "--outbound-license", "pending",
        "--scenario-note", "我们通过 Web 提供服务",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    # M4 起全量模式还产 conflicts.json：outbound 待定 → 冲突条目全部待定 → exit 1
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    record = payload["entries"][0]
    assert record["verdict"] == "triggered"
    assert record["triggers"] == ["network-interaction"]
    assert record["evidence"]["rule_ids"] == ["T-NET-001"]
    assert record["evidence"]["obligations"] == ["network-source"]


def test_saas_agpl_without_network_interaction_does_not_trigger(tmp_path, capsys):
    """用户明确回答「无网络交互」时才不触发；这与 internal 场景结论一致。"""
    inventory = _inventory_with(tmp_path, ["AGPL-3.0-only"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "saas",
        "--network-interaction", "no", "--outbound-license", "pending",
        "--scenario-note", "内部批处理，无远程交互",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    # saas + 无网络交互是矛盾回答 → 待确认，不按最宽松默认
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    assert payload["entries"][0]["verdict"] == contract.PENDING


def test_internal_agpl_network_interaction_triggers_network_source(tmp_path, capsys):
    """AGPL §13 与交付形态无关：内部网络服务同样触发（K13）。"""
    inventory = _inventory_with(tmp_path, ["AGPL-3.0-only"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "internal",
        "--network-interaction", "yes", "--outbound-license", "pending",
        "--scenario-note", "内网服务，用户远程访问",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    # M4 起全量模式还产 conflicts.json：outbound 待定 → 冲突条目全部待定 → exit 1
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    assert payload["entries"][0]["verdict"] == "triggered"


def test_internal_agpl_without_network_interaction_does_not_trigger(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["AGPL-3.0-only"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "internal",
        "--outbound-license", "pending", "--scenario-note", "纯本地工具",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    # M4 起全量模式还产 conflicts.json：outbound 待定 → 冲突条目全部待定 → exit 1
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    assert payload["entries"][0]["verdict"] == "not_triggered"


def test_saas_gpl_is_not_triggered_by_network_alone(tmp_path, capsys):
    """GPL 没有 §13：SaaS 未分发 + 网络交互 → 不触发（常见误解的反例）。"""
    inventory = _inventory_with(tmp_path, ["GPL-3.0-only"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "saas",
        "--network-interaction", "yes", "--outbound-license", "pending",
        "--scenario-note", "SaaS 服务",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    # M4 起全量模式还产 conflicts.json：outbound 待定 → 冲突条目全部待定 → exit 1
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    assert payload["entries"][0]["verdict"] == "not_triggered"


# ---------------------------------------------------------------------------
# K14：未回答 / 矛盾 → 待确认，不按最宽松默认
# ---------------------------------------------------------------------------


def test_saas_without_network_answer_is_pending(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["MIT", "AGPL-3.0-only"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "saas",
        "--outbound-license", "pending", "--scenario-note", "SaaS",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    for record in payload["entries"]:
        assert record["verdict"] == contract.PENDING
    assert payload["pending_confirmation"]


def test_saas_with_no_network_answer_is_contradiction_pending(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["MIT"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "saas",
        "--network-interaction", "no", "--outbound-license", "pending",
        "--scenario-note", "矛盾回答",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    assert payload["entries"][0]["verdict"] == contract.PENDING
    assert "network_interaction_contradicts_scenario" in (
        payload["pending_confirmation"][0]["reasons"]
    )


def test_link_scenario_without_delivery_is_pending(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["LGPL-2.1-only"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "static-link",
        "--outbound-license", "pending", "--scenario-note", "静态链接",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    assert payload["entries"][0]["verdict"] == contract.PENDING
    assert "delivery_unanswered" in payload["pending_confirmation"][0]["reasons"]


def test_container_image_without_network_answer_is_pending_for_network_tier(tmp_path, capsys):
    """container-image 的网络交互可选；没回答时，网络传染档位不能按「不触发」放过。"""
    inventory = _inventory_with(tmp_path, ["AGPL-3.0-only", "MIT"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "container-image",
        "--outbound-license", "pending", "--scenario-note", "镜像分发",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    by_package = {item["package"]: item for item in payload["entries"]}
    assert by_package["example-pkg-000"]["verdict"] == contract.PENDING
    assert by_package["example-pkg-001"]["verdict"] in ("not_triggered", "triggered")


def test_uncovered_id_is_pending_not_guessed(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["BlueOak-1.0.0"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "saas",
        "--network-interaction", "yes", "--outbound-license", "pending",
        "--scenario-note", "SaaS",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    record = payload["entries"][0]
    assert record["verdict"] == contract.PENDING
    assert record["evidence"]["atoms"][0]["tier"] is None


def test_expression_is_evaluated_and_the_most_permissive_atom_wins(tmp_path, capsys):
    """``MIT OR GPL-3.0-only`` 在 M4 起按 K16 求值：OR 取最宽松 → 按 MIT 判定（D32）。"""
    inventory = _inventory_with(tmp_path, ["MIT OR GPL-3.0-only"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "distribute-binary",
        "--outbound-license", "pending", "--scenario-note", "分发二进制",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    assert code == EXIT_FINDINGS, out + err  # outbound 待定 → 冲突待定
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    record = payload["entries"][0]
    assert record["verdict"] == "not_triggered"
    evaluation = record["evidence"]["expression_evaluation"]
    assert evaluation["selected"] == "MIT"
    assert evaluation["tier"] == "permissive"
    assert evaluation["resolved"] is True
    # 两个原子都留着（可审计），但结论只按选中的原子给
    assert [item["spdx_id"] for item in record["evidence"]["atoms"]] == [
        "MIT", "GPL-3.0-only",
    ]


def test_and_expression_takes_the_strictest_atom(tmp_path, capsys):
    """``MIT AND GPL-3.0-only``：AND 取最严格 → 按 GPL 判定（K16）。"""
    inventory = _inventory_with(tmp_path, ["MIT AND GPL-3.0-only"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "distribute-binary",
        "--outbound-license", "pending", "--scenario-note", "分发二进制",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    record = payload["entries"][0]
    assert record["verdict"] == "triggered"
    assert record["evidence"]["expression_evaluation"]["selected"] == "GPL-3.0-only"


def test_expression_with_uncovered_atom_stays_pending(tmp_path, capsys):
    """求值需要档位比较；有原子未覆盖 → 不猜，整条待确认（K7/K31）。"""
    inventory = _inventory_with(tmp_path, ["MIT OR BlueOak-1.0.0"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "distribute-binary",
        "--outbound-license", "pending", "--scenario-note", "分发二进制",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    record = payload["entries"][0]
    assert record["verdict"] == contract.PENDING
    assert record["evidence"]["expression_evaluation"]["resolved"] is False
    assert "expression_unresolved" in payload["pending_confirmation"][0]["reasons"]


# ---------------------------------------------------------------------------
# 分发 / 链接方式判定
# ---------------------------------------------------------------------------


def test_distribute_binary_triggers_strong_and_network_copyleft(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["GPL-3.0-only", "AGPL-3.0-only", "MIT"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "distribute-binary",
        "--outbound-license", "pending", "--scenario-note", "分发二进制",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    # M4 起全量模式还产 conflicts.json：outbound 待定 → 冲突条目全部待定 → exit 1
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    by_package = {item["package"]: item for item in payload["entries"]}
    assert by_package["example-pkg-000"]["verdict"] == "triggered"
    assert by_package["example-pkg-001"]["verdict"] == "triggered"
    assert by_package["example-pkg-002"]["verdict"] == "not_triggered"


def test_internal_use_does_not_trigger_copyleft(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["GPL-3.0-only", "LGPL-2.1-only"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "internal",
        "--outbound-license", "pending", "--scenario-note", "内部使用",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    # M4 起全量模式还产 conflicts.json：outbound 待定 → 冲突条目全部待定 → exit 1
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    for record in payload["entries"]:
        assert record["verdict"] == "not_triggered"


def test_static_link_triggers_weak_copyleft_source_duty(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["LGPL-2.1-only"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "static-link",
        "--delivery", "binary", "--outbound-license", "pending",
        "--scenario-note", "分发二进制 + 静态链接",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    # M4 起全量模式还产 conflicts.json：outbound 待定 → 冲突条目全部待定 → exit 1
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    record = payload["entries"][0]
    assert record["verdict"] == "triggered"
    assert "static-link" in record["triggers"]
    assert "provide-source" in record["evidence"]["obligations"]


def test_dynamic_link_of_weak_copyleft_triggers_distribution_not_static(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["LGPL-2.1-only"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "distribute-binary",
        "--linking", "dynamic", "--outbound-license", "pending",
        "--scenario-note", "分发二进制 + 动态链接",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    # M4 起全量模式还产 conflicts.json：outbound 待定 → 冲突条目全部待定 → exit 1
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    record = payload["entries"][0]
    assert "static-link" not in record["triggers"]
    assert record["triggers"] == ["distribution"]


def test_source_available_saas_hits_hosted_service_restriction(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["Elastic-2.0"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "saas",
        "--network-interaction", "yes", "--outbound-license", "pending",
        "--scenario-note", "SaaS 提供服务",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    # M4 起全量模式还产 conflicts.json：outbound 待定 → 冲突条目全部待定 → exit 1
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    record = payload["entries"][0]
    assert record["verdict"] == "triggered"
    assert record["triggers"] == ["hosted-service-restriction"]


def test_permissive_is_never_triggered_by_any_scenario():
    """宽松档不因链接方式/分发触发传染义务（载体是「触发表不写宽松条目」）。"""
    entries = _entries()
    for scenario, axes in contract.SCENARIO_AXES.items():
        delivery = axes["delivery"] or "binary"
        match_scenario = scenario_mod.delivery_scenario(delivery)
        for link_mode in contract.LINK_MODES:
            for network in (None, True):
                result = scenario_mod.evaluate_tier(
                    "permissive", match_scenario, link_mode, network, entries
                )
                assert result["verdict"] == "not_triggered"


# ---------------------------------------------------------------------------
# 用户回答落盘 / 可证伪门
# ---------------------------------------------------------------------------


def test_user_answer_is_persisted_verbatim(output):
    _out_dir, payload, _inventory = output
    assert payload["network_interaction"] is True
    assert payload["answered_by"] == "user"
    assert payload["raw_answer"] == "用户原话：我们通过 Web 提供服务"
    assert payload["outbound_license"] == "pending"
    for record in payload["entries"]:
        assert record["evidence"]["user_answer"] == payload["raw_answer"]
        assert record["evidence"]["answered_by"] == "user"


def test_missing_raw_answer_is_noted_not_invented(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["MIT"])
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "internal",
        "--outbound-license", "pending",
        "--out-dir", str(tmp_path / "out"),
    ], capsys)
    payload = read_json(str(tmp_path / "out" / "scenario.json"))
    assert payload["raw_answer"] == ""
    assert any(note["code"] == "raw_answer_missing" for note in payload["notes"])


def test_disabled_trigger_rule_never_produces_a_judgement(tmp_path):
    """K10 第二道门：绕过 loader 直接构造规则表时，未核验条目也不能生效。"""
    entry = {
        "id": "T-BROKEN-001",
        "tier": "strong-copyleft",
        "scenarios": ["distribute-binary"],
        "link_modes": ["none"],
        "trigger": "distribution",
        "obligations": ["same-license"],
        "anchor": {"source": "spdx-license-text", "ref": "texts/GPL-3.0-only.json#licenseText"},
        "verified": False,
        "checked_on": "2026-10-17",
    }
    result = scenario_mod.evaluate_tier(
        "strong-copyleft", "distribute-binary", "none", None, [entry]
    )
    assert result["verdict"] == "not_triggered"
    assert result["rule_ids"] == []


def test_entry_without_anchor_is_ignored():
    entry = {
        "id": "T-NOANCHOR-001",
        "tier": "strong-copyleft",
        "scenarios": ["distribute-binary"],
        "link_modes": ["none"],
        "trigger": "distribution",
        "obligations": ["same-license"],
        "verified": True,
        "checked_on": "2026-10-17",
    }
    result = scenario_mod.evaluate_tier(
        "strong-copyleft", "distribute-binary", "none", None, [entry]
    )
    assert result["verdict"] == "not_triggered"


# ---------------------------------------------------------------------------
# 产物形态与确定性
# ---------------------------------------------------------------------------


def test_scenario_json_is_byte_stable_across_two_runs(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["MIT", "GPL-3.0-only", "AGPL-3.0-only"])
    argv = [
        "assess", "--inventory", inventory, "--scenario", "saas",
        "--network-interaction", "yes", "--outbound-license", "pending",
        "--scenario-note", "SaaS",
    ]
    first = tmp_path / "out1"
    second = tmp_path / "out2"
    code, out, err = run(argv + ["--out-dir", str(first)], capsys)
    # M4 起全量模式还产 conflicts.json：outbound 待定 → 冲突条目全部待定 → exit 1
    assert code == EXIT_FINDINGS, out + err
    code, out, err = run(argv + ["--out-dir", str(second)], capsys)
    # M4 起全量模式还产 conflicts.json：outbound 待定 → 冲突条目全部待定 → exit 1
    assert code == EXIT_FINDINGS, out + err
    left = io.open(str(first / "scenario.json"), encoding="utf-8").read()
    right = io.open(str(second / "scenario.json"), encoding="utf-8").read()
    assert left == right
    assert left.endswith("\n")


def test_full_assess_writes_all_three_artifacts(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["MIT"])
    out_dir = tmp_path / "out"
    code, out, err = run([
        "assess", "--inventory", inventory, "--scenario", "internal",
        "--outbound-license", "pending", "--scenario-note", "内部",
        "--out-dir", str(out_dir),
    ], capsys)
    # M4 起全量模式还产 conflicts.json：outbound 待定 → 冲突条目全部待定 → exit 1
    assert code == EXIT_FINDINGS, out + err
    assert (out_dir / "profile.json").is_file()
    assert (out_dir / "scenario.json").is_file()
    assert (out_dir / "conflicts.json").is_file()


def test_profile_only_does_not_write_scenario(tmp_path, capsys):
    inventory = _inventory_with(tmp_path, ["MIT"])
    out_dir = tmp_path / "out"
    code, out, err = run([
        "assess", "--inventory", inventory, "--profile-only", "--out-dir", str(out_dir),
    ], capsys)
    assert code == EXIT_OK, out + err
    assert (out_dir / "profile.json").is_file()
    assert not (out_dir / "scenario.json").exists()
    assert not (out_dir / "conflicts.json").exists()


# ---------------------------------------------------------------------------
# 真值与基准
# ---------------------------------------------------------------------------


def test_scenario_truth_is_a_projection_of_the_curated_table():
    truth = read_json(TRUTH_PATH)
    curated = {entry["id"]: entry for entry in _curated_triggers()}
    assert set(truth["inputs"]["enabled_rule_ids"]) == set(curated)
    for row in truth["expect"]["matrix"]:
        hits = [
            entry for entry in curated.values()
            if entry["tier"] == row["tier"]
            and row["delivery_scenario"] in entry["scenarios"]
            and row["link_mode"] in entry["link_modes"]
            and (
                "network_interaction" not in entry
                or (entry["network_interaction"] is True and row["network_interaction"] is True)
            )
        ]
        if row["delivery_scenario"] == "saas" and row["network_interaction"] is False:
            assert row["verdict"] == contract.PENDING
            continue
        if not hits:
            assert row["verdict"] == "not_triggered"
            continue
        assert row["verdict"] == "triggered"
        assert row["triggers"] == sorted({entry["trigger"] for entry in hits})
        assert row["rule_ids"] == sorted({entry["id"] for entry in hits})


def test_scenario_truth_covers_all_eight_scenarios_and_link_modes():
    truth = read_json(TRUTH_PATH)
    matrix = truth["expect"]["matrix"]
    assert {row["scenario"] for row in matrix} == set(contract.SCENARIO_IDS)
    assert {row["link_mode"] for row in matrix} == set(contract.LINK_MODES)
    assert {row["tier"] for row in matrix} == set(contract.TIERS)


def test_trigger_rule_ids_are_unique():
    payload = read_json(os.path.join(REPO_ROOT, "references", "ruleset",
                                     "scenario-triggers.json"))
    ids = [entry["id"] for entry in payload["entries"]]
    assert len(ids) == len(set(ids))
    assert payload["entries"]


def test_every_trigger_rule_passes_anchor_gate():
    ruleset = load_ruleset()
    entries = ruleset.entries("scenario-triggers.json")
    assert entries
    assert ruleset.disabled == []
    for entry in entries:
        assert entry["verified"] is True
        assert entry["checked_on"]
        assert entry["anchor"]["ref"].startswith("texts/")
        assert entry["anchor"]["quote"]


def test_trigger_anchors_are_locatable_in_snapshots():
    ruleset = load_ruleset()
    problems = []
    for entry in ruleset.entries("scenario-triggers.json"):
        reference = entry["anchor"]["ref"]
        relative = reference.split("#", 1)[0]
        path = os.path.join(SPDX_DIR, relative.replace("/", os.sep))
        if not os.path.isfile(path):
            problems.append("{0}: 全文缺失 {1}".format(entry["id"], relative))
            continue
        text = read_json(path).get("licenseText") or ""
        quote = " ".join(entry["anchor"]["quote"].split())
        if quote not in " ".join(text.split()):
            problems.append("{0}: quote 无法定位".format(entry["id"]))
    assert not problems, "; ".join(problems)


def test_gen_scenario_truth_check_passes():
    import subprocess
    import sys

    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "tools", "gen_scenario_truth.py"), "--check"],
        cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=300,
    )
    text = result.stdout.decode("utf-8", "replace")
    assert result.returncode == 0, text
    assert "逐字节一致" in text


def test_gen_scenario_truth_check_detects_handedit(tmp_path):
    import subprocess
    import sys

    target = tmp_path / "scenario.json"
    target.write_text(
        io.open(TRUTH_PATH, encoding="utf-8").read().replace(
            '"verdict": "triggered"', '"verdict": "not_triggered"', 1
        ),
        encoding="utf-8",
    )
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    result = subprocess.run(
        [sys.executable, os.path.join(REPO_ROOT, "tools", "gen_scenario_truth.py"),
         "--check", "--out", str(target)],
        cwd=REPO_ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        timeout=300,
    )
    text = result.stdout.decode("utf-8", "replace")
    assert result.returncode == 1, text
    assert "[FAIL]" in text


def test_bench_m3_passes(capsys):
    code, out, err = run(["bench", "--only", "m3"], capsys)
    assert code == EXIT_OK, out + err
    assert "[OK] m3" in out


def test_bench_m3_turns_red_when_truth_drifts(tmp_path, capsys):
    """把场景真值的某一行改坏 → bench m3 必须变红。"""
    shutil.copytree(DATA_DIR, str(tmp_path / "data"))
    truth_path = tmp_path / "data" / "truth" / "scenario.json"
    payload = read_json(str(truth_path))
    row = next(item for item in payload["expect"]["matrix"] if item["verdict"] == "triggered")
    row["verdict"] = "not_triggered"
    write_json(str(truth_path), payload)
    code, out, err = run(
        ["bench", "--only", "m3", "--data-dir", str(tmp_path / "data")], capsys
    )
    assert code == EXIT_FINDINGS, out + err
    assert "[FAIL]" in out
