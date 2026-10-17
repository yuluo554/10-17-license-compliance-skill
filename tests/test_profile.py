# -*- coding: utf-8 -*-
"""M2 画像矩阵：档位/义务查表、原子拆分、OSI/FSF 来源、待确认与可证伪性。

这些测试刻意不"回放"引擎输出：档位期望值来自 ``references/curated/tiers.json``
（规则表是唯一真相），快照字段期望值直接读 ``references/spdx/licenses.json``。
"""

import io
import json
import os
import shutil

import pytest

from _helpers import REPO_ROOT, make_ruleset_dir, write_json

from licaudit import cli, contract
from licaudit.assess import profile as profile_mod
from licaudit.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE
from licaudit.ruleset import loader, load_ruleset
from licaudit.serialize import dumps_json

DATA_DIR = os.path.join(REPO_ROOT, "data")
SPDX_DIR = os.path.join(REPO_ROOT, "references", "spdx")
CURATED_DIR = os.path.join(REPO_ROOT, "references", "curated")
TRUTH_PATH = os.path.join(DATA_DIR, "truth", "profile.json")


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


@pytest.fixture(scope="module")
def output(tmp_path_factory):
    """用真实规则包 + 真实快照产一次画像（全量采样 ID，含未覆盖 ID）。"""
    out_dir = tmp_path_factory.mktemp("profile")
    inventory = os.path.join(str(out_dir), "inventory.json")
    truth = read_json(TRUTH_PATH)
    records = {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "license_list_version": "3.29.0",
        "ruleset_version": "r0.1.0",
        "source_files": ["synthetic.json"],
        "dependencies": [
            {
                "package": "example-pkg-{0:03d}".format(index),
                "version": "1.0.0",
                "raw_license": spdx_id,
                "spdx_id": spdx_id,
                "confidence": "license_expression",
                "evidence": {"ruleset_version": "r0.1.0", "details_url": None},
            }
            for index, spdx_id in enumerate(truth["inputs"]["spdx_ids"])
        ],
        "pending_confirmation": [],
        "parse_notes": [],
    }
    write_json(inventory, records)
    code = cli.main(
        ["assess", "--inventory", inventory, "--profile-only", "--out-dir", str(out_dir)]
    )
    # 采样集里含未覆盖 ID → 按 plan/03 §六 退出码 1（分析完成、有待确认项）
    assert code == EXIT_FINDINGS
    return out_dir, read_json(os.path.join(str(out_dir), "profile.json"))


def _inventory_with(tmp_path, spdx_ids, name="inventory.json"):
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
                "evidence": {},
            }
            for index, spdx_id in enumerate(spdx_ids)
        ],
        "pending_confirmation": [],
    })
    return str(path)


def _curated_rules():
    payload = read_json(os.path.join(CURATED_DIR, "tiers.json"))
    return {entry["license_id"]: entry for entry in payload["entries"]}


def _snapshot_licenses():
    payload = read_json(os.path.join(SPDX_DIR, "licenses.json"))
    return {item["licenseId"]: item for item in payload["licenses"]}


# ---------------------------------------------------------------------------
# 契约形态
# ---------------------------------------------------------------------------


def test_profile_record_field_order_matches_contract(output):
    _out_dir, payload = output
    assert payload["format"] == contract.PROFILE_FORMAT
    assert payload["format_version"] == contract.FORMAT_VERSION
    assert payload["profiles"]
    for record in payload["profiles"]:
        assert tuple(record) == contract.PROFILE_FIELDS


def test_profile_is_byte_stable_across_two_runs(output, tmp_path):
    out_dir, payload = output
    inventory_source = os.path.join(str(out_dir), "inventory.json")
    second = tmp_path / "second"
    code = cli.main(
        ["assess", "--inventory", inventory_source, "--profile-only",
         "--out-dir", str(second)]
    )
    assert code == EXIT_FINDINGS
    first_text = io.open(os.path.join(str(out_dir), "profile.json"), encoding="utf-8").read()
    second_text = io.open(str(second / "profile.json"), encoding="utf-8").read()
    assert first_text == second_text
    assert first_text == dumps_json(payload)


def test_all_covered_inventory_exits_zero(tmp_path):
    """全部覆盖时退出码必须是 0：1 只用于「有待确认项」，不能被滥用成常态。"""
    inventory = _inventory_with(tmp_path, ["MIT", "Apache-2.0", "GPL-2.0-only"])
    code = cli.main(
        ["assess", "--inventory", inventory, "--profile-only",
         "--out-dir", str(tmp_path / "out")]
    )
    assert code == EXIT_OK
    payload = read_json(str(tmp_path / "out" / "profile.json"))
    assert payload["pending_confirmation"] == []


def test_profile_has_one_entry_per_atom(output):
    _out_dir, payload = output
    ids = [record["spdx_id"] for record in payload["profiles"]]
    assert ids == sorted(set(ids)), "画像必须一 ID 一条且按 ID 排序"


# ---------------------------------------------------------------------------
# 档位与义务：只查规则表
# ---------------------------------------------------------------------------


def test_tier_and_obligations_come_from_ruleset(output):
    _out_dir, payload = output
    curated = _curated_rules()
    checked = 0
    for record in payload["profiles"]:
        rule = curated.get(record["spdx_id"])
        if rule is None:
            continue
        assert record["tier"] == rule["tier"]
        # 义务集合相等，且按 contract.OBLIGATIONS 的固定顺序输出
        assert set(record["obligations"]) == set(rule["obligations"])
        order = [item for item in contract.OBLIGATIONS if item in record["obligations"]]
        assert record["obligations"] == order
        checked += 1
    assert checked == 48


def test_uncovered_id_gets_null_tier_and_pending(output):
    _out_dir, payload = output
    pending = {item["spdx_id"]: item for item in payload["pending_confirmation"]}
    for spdx_id in ("BlueOak-1.0.0", "CC-BY-4.0"):
        record = next(item for item in payload["profiles"] if item["spdx_id"] == spdx_id)
        assert record["tier"] is None
        assert record["obligations"] is None
        assert "tier_uncovered" in pending[spdx_id]["reasons"]
        assert "tier" in pending[spdx_id]["missing"]


def test_unknown_family_has_no_tier_and_no_fabricated_snapshot_facts(output):
    _out_dir, payload = output
    record = next(
        item for item in payload["profiles"] if item["spdx_id"] == "GPL-unknown"
    )
    assert record["tier"] is None
    assert record["is_osi_approved"] is None
    assert record["is_fsf_libre"] is None
    assert record["evidence"]["details_url"] is None
    pending = {
        item["spdx_id"]: item for item in payload["pending_confirmation"]
    }
    assert "unknown_family" in pending["GPL-unknown"]["reasons"]


def test_obligations_are_never_invented(output):
    _out_dir, payload = output
    allowed = set(contract.OBLIGATIONS)
    for record in payload["profiles"]:
        for obligation in record["obligations"] or []:
            assert obligation in allowed


# ---------------------------------------------------------------------------
# 原子拆分
# ---------------------------------------------------------------------------


def test_expression_is_split_into_atoms():
    index, _version = profile_mod.load_context(SPDX_DIR)
    atoms, note = profile_mod.split_atoms("(MIT OR Apache-2.0) AND BSD-3-Clause", index)
    assert atoms == ["MIT", "Apache-2.0", "BSD-3-Clause"]
    assert note is None


def test_only_and_or_later_are_preserved_verbatim():
    index, _version = profile_mod.load_context(SPDX_DIR)
    atoms, _note = profile_mod.split_atoms("GPL-2.0-only OR GPL-3.0-or-later", index)
    assert atoms == ["GPL-2.0-only", "GPL-3.0-or-later"]


def test_unparsable_expression_is_kept_as_single_atom_with_note():
    index, _version = profile_mod.load_context(SPDX_DIR)
    atoms, note = profile_mod.split_atoms("Proprietary Internal Use Only", index)
    assert atoms == ["Proprietary Internal Use Only"]
    assert note == "expression_unparsed"


def test_pending_records_also_contribute_atoms():
    """D22：两个列表不互斥；只在 pending 里的记录也必须进画像。"""
    inventory = {
        "dependencies": [],
        "pending_confirmation": [
            {
                "record": {"package": "example-pkg-a", "spdx_id": "MIT"},
                "missing": [],
                "reason": "needs_confirmation",
            }
        ],
    }
    index, _version = profile_mod.load_context(SPDX_DIR)
    atoms, notes = profile_mod.collect_atoms(inventory, index)
    assert atoms == ["MIT"]
    assert notes == []


def test_with_expression_splits_to_licence_atom_only():
    index, _version = profile_mod.load_context(SPDX_DIR)
    atoms, _note = profile_mod.split_atoms(
        "GPL-2.0-only WITH Classpath-exception-2.0", index
    )
    assert atoms == ["GPL-2.0-only"]


# ---------------------------------------------------------------------------
# OSI / FSF：只从快照取；FSF 不参与判定
# ---------------------------------------------------------------------------


def test_osi_and_fsf_come_from_snapshot_only(output):
    _out_dir, payload = output
    licenses = _snapshot_licenses()
    for record in payload["profiles"]:
        snapshot = licenses.get(record["spdx_id"])
        if snapshot is None:
            assert record["is_osi_approved"] is None
            assert record["is_fsf_libre"] is None
            continue
        assert record["is_osi_approved"] == snapshot.get("isOsiApproved")
        assert record["is_fsf_libre"] == snapshot.get("isFsfLibre")


def test_fsf_libre_does_not_participate_in_judgement(output):
    """把 FSF 标记全体翻转，档位/义务/条款必须一字不变（K9）。"""
    _out_dir, payload = output
    baseline = {
        item["spdx_id"]: (
            item["tier"], item["obligations"],
            item["patent_clause"]["present"], item["trademark_clause"]["present"],
        )
        for item in payload["profiles"]
    }

    real = profile_mod.load_context(SPDX_DIR)[0]

    class FlippedFsf(object):
        """只翻转 is_fsf_libre，其余行为完全代理。"""

        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def is_fsf_libre(self, license_id):
            value = self._inner.is_fsf_libre(license_id)
            if value is None:
                return True
            return not value

    flipped = FlippedFsf(real)
    ruleset = load_ruleset()
    payload2 = profile_mod.profile_ids(
        [item["spdx_id"] for item in payload["profiles"]], ruleset, flipped,
        payload["license_list_version"],
    )
    for record in payload2["profiles"]:
        assert (
            record["tier"], record["obligations"],
            record["patent_clause"]["present"], record["trademark_clause"]["present"],
        ) == baseline[record["spdx_id"]]
        if record["is_fsf_libre"] is not None:
            assert record["is_fsf_libre"] != next(
                item["is_fsf_libre"] for item in payload["profiles"]
                if item["spdx_id"] == record["spdx_id"]
            )


def test_judgement_function_does_not_take_snapshot():
    """判定入口的签名里没有快照参数：结构上就拿不到 FSF 字段。"""
    import inspect

    parameters = inspect.signature(profile_mod.evaluate_rule).parameters
    assert list(parameters) == ["atom", "rule", "disabled", "duplicated"]


# ---------------------------------------------------------------------------
# 条款锚点
# ---------------------------------------------------------------------------


def test_every_tiered_profile_carries_locatable_anchor(output):
    _out_dir, payload = output
    curated = _curated_rules()
    for record in payload["profiles"]:
        if record["tier"] is None:
            continue
        anchor = record["evidence"]["license_text_anchor"]
        assert anchor["source"] and anchor["ref"] and anchor["quote"]
        assert record["evidence"]["checked_on"]
        # 锚点必须与规则表逐字一致（不是引擎重写/截断的版本）
        assert anchor == curated[record["spdx_id"]]["anchor"]


def test_patent_and_trademark_clauses_follow_ruleset(output):
    _out_dir, payload = output
    curated = _curated_rules()
    for record in payload["profiles"]:
        rule = curated.get(record["spdx_id"])
        if rule is None:
            assert record["patent_clause"]["present"] is None
            assert record["trademark_clause"]["present"] is None
            continue
        for field in ("patent_clause", "trademark_clause"):
            expected = bool((rule.get(field) or {}).get("present"))
            assert record[field]["present"] is expected
            if expected:
                assert record[field]["anchor"] == rule[field]["anchor"]
                assert record[field]["checked_on"] == rule["checked_on"]
            else:
                assert record[field]["anchor"] is None


# ---------------------------------------------------------------------------
# disabled 规则：不参与判定
# ---------------------------------------------------------------------------


def _ruleset_with_disabled_entry(root):
    """造一份「MIT 规则 verified=false」的规则包；loader 会把它拒进 disabled。"""
    make_ruleset_dir(root)
    tiers_path = os.path.join(root, "tiers.json")
    payload = read_json(tiers_path)
    assert payload["entries"][0]["license_id"] == "MIT"
    payload["entries"][0]["verified"] = False
    write_json(tiers_path, payload)

    manifest_path = os.path.join(root, "manifest.json")
    manifest = read_json(manifest_path)
    manifest["files"]["tiers.json"] = loader.sha256_file(tiers_path)
    write_json(manifest_path, manifest)
    return root


def test_disabled_rule_never_produces_a_tier(tmp_path):
    root = _ruleset_with_disabled_entry(str(tmp_path / "rs"))
    ruleset = load_ruleset(explicit=root)
    assert [item.get("id") for item in ruleset.disabled] == ["MIT"]

    index, _version = profile_mod.load_context(SPDX_DIR)
    payload = profile_mod.profile_ids(["MIT"], ruleset, index)
    record = payload["profiles"][0]
    assert record["tier"] is None
    assert payload["pending_confirmation"][0]["spdx_id"] == "MIT"
    assert "rule_disabled" in payload["pending_confirmation"][0]["reasons"]
    # 被拒绝的规则必须显式可见，不能静默消失
    assert payload["disabled_rules"] == [
        {"file": "tiers.json", "index": 0, "id": "MIT", "reasons": ["not_verified"]}
    ]


def test_engine_ignores_unverified_rule_even_if_caller_bypasses_loader():
    """K10 的第二道门：规则表未经 loader 过滤时，画像引擎也不得使用未核验规则。

    直接构造一个"已启用但 verified=false"的规则包对象 —— 这是 loader 不该放过、
    引擎也绝不能信的形状。
    """
    index, _version = profile_mod.load_context(SPDX_DIR)
    unverified = {
        "license_id": "MIT",
        "tier": "permissive",
        "obligations": ["retain-copyright"],
        "anchor": {"source": "spdx-license-text", "ref": "texts/MIT.json#licenseText"},
        "verified": False,
        "checked_on": "2026-10-17",
    }

    class FakeRuleset(object):
        version = "r-test"
        disabled = []
        enabled = {"tiers.json": [unverified]}

        def entries(self, name):
            return self.enabled.get(name, [])

    payload = profile_mod.profile_ids(["MIT"], FakeRuleset(), index)
    assert payload["profiles"][0]["tier"] is None
    assert payload["profiles"][0]["obligations"] is None
    reasons = payload["pending_confirmation"][0]["reasons"]
    assert "rule_disabled" in reasons
    assert "tier_uncovered" in reasons


def test_duplicate_rules_are_not_trusted(tmp_path):
    """同一 ID 两条规则时，两条都不采信：挑一条或合并都是猜测。"""
    make_ruleset_dir(str(tmp_path / "rs"))
    root = str(tmp_path / "rs")
    tiers_path = os.path.join(root, "tiers.json")
    payload = read_json(tiers_path)
    duplicate = dict(payload["entries"][0])
    duplicate["tier"] = "strong-copyleft"
    payload["entries"].append(duplicate)
    write_json(tiers_path, payload)

    manifest_path = os.path.join(root, "manifest.json")
    manifest = read_json(manifest_path)
    manifest["files"]["tiers.json"] = loader.sha256_file(tiers_path)
    write_json(manifest_path, manifest)

    ruleset = load_ruleset(explicit=root)
    index, _version = profile_mod.load_context(SPDX_DIR)
    result = profile_mod.profile_ids(["MIT"], ruleset, index)
    assert result["profiles"][0]["tier"] is None
    assert "rule_duplicated" in result["pending_confirmation"][0]["reasons"]


def test_rule_present_but_id_absent_from_snapshot_is_pending():
    """规则可用但快照里没有该 ID → 档位照给，OSI/FSF 无法回答，必须待确认。"""
    index, _version = profile_mod.load_context(SPDX_DIR)
    rule = {
        "license_id": "Made-Up-1.0",
        "tier": "permissive",
        "obligations": ["retain-copyright"],
        "patent_clause": {"present": False, "anchor": None},
        "trademark_clause": {"present": False, "anchor": None},
        "anchor": {"source": "spdx-license-text", "ref": "texts/Made-Up-1.0.json#licenseText"},
        "verified": True,
        "checked_on": "2026-10-17",
    }

    class FakeRuleset(object):
        version = "r-test"
        disabled = []
        enabled = {"tiers.json": [rule]}

        def entries(self, name):
            return self.enabled.get(name, [])

    result = profile_mod.profile_ids(["Made-Up-1.0"], FakeRuleset(), index)
    record = result["profiles"][0]
    assert record["tier"] == "permissive"
    assert record["is_osi_approved"] is None
    assert result["pending_confirmation"][0]["reasons"] == ["not_in_spdx_snapshot"]
    assert "is_osi_approved" in result["pending_confirmation"][0]["missing"]


def test_disabled_rules_are_visible_in_artifact(tmp_path, capsys):
    root = _ruleset_with_disabled_entry(str(tmp_path / "rs"))
    inventory = tmp_path / "inventory.json"
    write_json(str(inventory), {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "dependencies": [{
            "package": "example-pkg-a", "version": "1.0.0", "raw_license": "MIT",
            "spdx_id": "MIT", "confidence": "license_expression", "evidence": {},
        }],
        "pending_confirmation": [],
    })
    code, out, err = run(
        ["--rules-dir", root, "assess", "--inventory", str(inventory),
         "--profile-only", "--out-dir", str(tmp_path / "out")],
        capsys,
    )
    assert code == EXIT_FINDINGS, out + err
    payload = read_json(str(tmp_path / "out" / "profile.json"))
    assert payload["profiles"][0]["tier"] is None
    assert payload["disabled_rules"]


# ---------------------------------------------------------------------------
# CLI 与基准
# ---------------------------------------------------------------------------


def test_assess_profile_only_requires_no_scenario(tmp_path, capsys):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    code, out, err = run(
        ["--rules-dir", root, "assess", "--inventory", "missing.json",
         "--profile-only", "--out-dir", str(tmp_path / "out")],
        capsys,
    )
    # 场景与 outbound 都不是必填；错误只来自 inventory 缺失（exit 2）
    assert code == EXIT_USAGE
    assert "产物文件不存在" in err


def test_assess_rejects_non_inventory_artifact(tmp_path, capsys):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    other = tmp_path / "other.json"
    write_json(str(other), {"format": "licaudit-profile", "format_version": 1,
                            "profiles": []})
    code, out, err = run(
        ["--rules-dir", root, "assess", "--inventory", str(other),
         "--profile-only", "--out-dir", str(tmp_path / "out")],
        capsys,
    )
    assert code == EXIT_USAGE
    assert "格式" in err


def test_assess_writes_profile_with_expected_top_level_fields(output, capsys):
    out_dir, _payload = output
    text = io.open(os.path.join(str(out_dir), "profile.json"), encoding="utf-8").read()
    assert text.endswith("\n")
    assert "\r" not in text
    payload = json.loads(text)
    assert list(payload) == list(profile_mod.PROFILE_TOP_LEVEL_FIELDS)


def test_bench_m2_passes(capsys):
    code, out, err = run(["bench", "--only", "m2"], capsys)
    assert code == EXIT_OK, out + err
    assert "[OK] m2" in out


def test_bench_m2_turns_red_when_truth_drifts(tmp_path, capsys):
    """改一条真值档位 → m2 必须红（证明基准真的读了冻结真值）。"""
    shutil.copytree(DATA_DIR, str(tmp_path / "data"))
    truth_path = tmp_path / "data" / "truth" / "profile.json"
    payload = read_json(str(truth_path))
    payload["expect"]["profiles"][0]["tier"] = "source-available"
    write_json(str(truth_path), payload)

    code, out, err = run(
        ["bench", "--only", "m2", "--data-dir", str(tmp_path / "data")], capsys
    )
    assert code == EXIT_FINDINGS, out + err
    assert "FAIL" in out


def test_bench_m2_turns_red_when_truth_gains_observed_field(tmp_path, capsys):
    shutil.copytree(DATA_DIR, str(tmp_path / "data"))
    truth_path = tmp_path / "data" / "truth" / "profile.json"
    payload = read_json(str(truth_path))
    payload["expect"]["profiles"][0]["observed_tier"] = "permissive"
    write_json(str(truth_path), payload)

    code, out, err = run(
        ["bench", "--only", "m2", "--data-dir", str(tmp_path / "data")], capsys
    )
    assert code == EXIT_FINDINGS
    assert "observed_" in out


def test_bench_default_includes_m2(capsys):
    code, out, err = run(["bench"], capsys)
    assert code == EXIT_OK, out + err
    assert "m1" in out and "m2" in out


def test_profile_truth_declares_inputs_and_expectations():
    payload = read_json(TRUTH_PATH)
    assert payload["format"] == "licaudit-profile-truth"
    assert payload["format_version"] == contract.FORMAT_VERSION
    assert payload["inputs"]["spdx_ids"]
    assert payload["inputs"]["license_list_version"] == "3.29.0"
    assert payload["inputs"]["captured_on"]
    assert payload["expect"]["profiles"]
    assert payload["expect"]["pending"]
    text = io.open(TRUTH_PATH, encoding="utf-8").read()
    assert "observed_" not in text
