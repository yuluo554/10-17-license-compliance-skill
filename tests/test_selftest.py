# -*- coding: utf-8 -*-
"""自检的可证伪性（K10 / 阶段 5 探活纪律）。

「自检通过」只有在**它能失败**时才有意义。这里对每一项 check 做变异：
弄坏被测不变量 → 自检必须报 FAIL。
"""

import pytest

from _helpers import make_ruleset_dir

from licaudit import contract
from licaudit import selftest


def test_core_selftest_passes_by_default():
    checks, ok = selftest.run_selftest(core_only=True)
    assert ok is True
    assert all(item["ok"] for item in checks)


def test_full_selftest_fails_without_ruleset(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    checks, ok = selftest.run_selftest(core_only=False, rules_dir=str(empty))
    assert ok is False
    failed = [item["id"] for item in checks if not item["ok"]]
    assert "ruleset_loadable" in failed


def test_full_selftest_passes_with_ruleset(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    checks, ok = selftest.run_selftest(core_only=False, rules_dir=root)
    assert ok is True, selftest.format_checks(checks)


def test_every_core_check_is_registered():
    assert set(selftest.CORE_CHECK_IDS) == set(selftest._CHECK_FUNCTIONS)


@pytest.mark.parametrize("broken_field", ["INVENTORY_RECORD_FIELDS", "REPORT_SECTIONS"])
def test_contract_fields_check_goes_red_when_broken(monkeypatch, broken_field):
    """变异：把字段元组清空 → contract_fields 必须变红。"""
    monkeypatch.setattr(contract, broken_field, ())
    checks, ok = selftest.run_selftest(core_only=True)
    assert ok is False
    failed = [item["id"] for item in checks if not item["ok"]]
    assert "contract_fields" in failed


def test_contract_unique_check_goes_red_when_duplicated(monkeypatch):
    monkeypatch.setattr(
        contract, "INVENTORY_RECORD_FIELDS", ("package", "package", "version")
    )
    checks, ok = selftest.run_selftest(core_only=True)
    assert ok is False
    assert "contract_unique" in [item["id"] for item in checks if not item["ok"]]


def test_scenario_axes_check_goes_red_when_missing(monkeypatch):
    broken = dict(contract.SCENARIO_AXES)
    broken.pop("saas")
    monkeypatch.setattr(contract, "SCENARIO_AXES", broken)
    checks, ok = selftest.run_selftest(core_only=True)
    assert ok is False
    assert "scenario_axes" in [item["id"] for item in checks if not item["ok"]]


def test_scenario_axes_check_goes_red_on_bad_link_mode(monkeypatch):
    broken = dict(contract.SCENARIO_AXES)
    broken["saas"] = {"delivery": "saas", "link_mode": "telepathy"}
    monkeypatch.setattr(contract, "SCENARIO_AXES", broken)
    checks, ok = selftest.run_selftest(core_only=True)
    assert ok is False
    assert "scenario_axes" in [item["id"] for item in checks if not item["ok"]]


def test_tier_rank_check_goes_red_when_rank_wrong(monkeypatch):
    broken = dict(contract.TIER_RANK)
    broken["permissive"] = 99
    monkeypatch.setattr(contract, "TIER_RANK", broken)
    checks, ok = selftest.run_selftest(core_only=True)
    assert ok is False
    assert "tier_rank" in [item["id"] for item in checks if not item["ok"]]


def test_enums_disjoint_check_goes_red_when_overlapping(monkeypatch):
    monkeypatch.setattr(contract, "CONFLICT_RESOLUTIONS", ("ok", "pending"))
    checks, ok = selftest.run_selftest(core_only=True)
    assert ok is False
    assert "enums_disjoint" in [item["id"] for item in checks if not item["ok"]]


def test_blocking_levels_must_subset_of_action_levels(monkeypatch):
    monkeypatch.setattr(contract, "BLOCKING_ACTION_LEVELS", ("isolate", "nope"))
    checks, ok = selftest.run_selftest(core_only=True)
    assert ok is False
    assert "enums_disjoint" in [item["id"] for item in checks if not item["ok"]]


def test_format_checks_marks_failures():
    text = selftest.format_checks(
        [
            {"id": "a", "ok": True, "detail": ""},
            {"id": "b", "ok": False, "detail": "boom"},
        ]
    )
    assert "[OK] a" in text
    assert "[FAIL] b — boom" in text


def test_selftest_does_not_crash_on_broken_ruleset(tmp_path):
    """规则包畸形时自检要报 FAIL，而不是抛异常把 CLI 打崩。"""
    root = tmp_path / "bad"
    root.mkdir()
    (root / "manifest.json").write_text('{not json', encoding="utf-8")
    checks, ok = selftest.run_selftest(core_only=False, rules_dir=str(root))
    assert ok is False
    assert "ruleset_loadable" in [item["id"] for item in checks if not item["ok"]]
