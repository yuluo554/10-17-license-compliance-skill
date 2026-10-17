# -*- coding: utf-8 -*-
"""规则包加载硬门（K10 / K24）。

重点不是「能加载」，而是**每一种坏规则包都必须被拒绝**：
未核验、缺锚点、缺核对日期、哈希不符、manifest 缺文件、schema 版本不认识。
"""

import io
import json
import os

import pytest

from _helpers import make_ruleset_dir, write_json

from licaudit.errors import RulesetError
from licaudit.ruleset import loader


def test_locates_explicit_dir(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    ruleset = loader.load_ruleset(explicit=root)
    assert ruleset.root == os.path.abspath(root)
    assert ruleset.version == "r0.1.0-test"
    assert ruleset.license_list_version == "3.29.0"


def test_env_var_is_second_priority(tmp_path, monkeypatch):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    monkeypatch.setenv(loader.ENV_RULES_DIR, root)
    monkeypatch.chdir(str(tmp_path))
    ruleset = loader.load_ruleset()
    assert ruleset.root == os.path.abspath(root)


def test_explicit_beats_env(tmp_path, monkeypatch):
    env_root = make_ruleset_dir(str(tmp_path / "env-rs"))
    explicit_root = make_ruleset_dir(str(tmp_path / "explicit-rs"))
    monkeypatch.setenv(loader.ENV_RULES_DIR, env_root)
    ruleset = loader.load_ruleset(explicit=explicit_root)
    assert ruleset.root == os.path.abspath(explicit_root)


def test_missing_ruleset_raises_with_tried_paths(tmp_path, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(str(tmp_path))
    monkeypatch.delenv(loader.ENV_RULES_DIR, raising=False)
    with pytest.raises(RulesetError) as excinfo:
        loader.load_ruleset(explicit=str(empty))
    assert "tried" in excinfo.value.details


def test_bad_hash_is_rejected(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"), bad_hash=True)
    with pytest.raises(RulesetError) as excinfo:
        loader.load_ruleset(explicit=root)
    assert "哈希" in str(excinfo.value)


def test_missing_declared_file_is_rejected(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"), complete=False)
    # manifest 只登记了 tiers.json；删掉它模拟「登记了但文件不在」
    os.unlink(os.path.join(root, "tiers.json"))
    with pytest.raises(RulesetError):
        loader.load_ruleset(explicit=root)


def test_unsupported_schema_version_is_rejected(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    manifest_path = os.path.join(root, "manifest.json")
    with io.open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    manifest["schema_version"] = 99
    write_json(manifest_path, manifest)
    with pytest.raises(RulesetError) as excinfo:
        loader.load_ruleset(explicit=root, verify_hashes=False)
    assert "schema" in str(excinfo.value)


def test_missing_ruleset_version_is_rejected(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    manifest_path = os.path.join(root, "manifest.json")
    with io.open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    manifest.pop("ruleset_version")
    write_json(manifest_path, manifest)
    with pytest.raises(RulesetError):
        loader.load_ruleset(explicit=root, verify_hashes=False)


def test_missing_license_list_version_is_rejected(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    manifest_path = os.path.join(root, "manifest.json")
    with io.open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    manifest.pop("license_list_version")
    write_json(manifest_path, manifest)
    with pytest.raises(RulesetError):
        loader.load_ruleset(explicit=root, verify_hashes=False)


def test_file_outside_whitelist_is_rejected(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    manifest_path = os.path.join(root, "manifest.json")
    with io.open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    manifest["files"]["../evil.json"] = "0" * 64
    write_json(manifest_path, manifest)
    with pytest.raises(RulesetError):
        loader.load_ruleset(explicit=root, verify_hashes=False)


def _patch_entries(root, filename, entries):
    path = os.path.join(root, filename)
    with io.open(path, encoding="utf-8") as stream:
        payload = json.load(stream)
    payload["entries"] = entries
    write_json(path, payload)
    # 重算哈希，避免被哈希门先拦下（我们要验的是锚点门本身）
    manifest_path = os.path.join(root, "manifest.json")
    with io.open(manifest_path, encoding="utf-8") as stream:
        manifest = json.load(stream)
    manifest["files"][filename] = loader.sha256_file(path)
    write_json(manifest_path, manifest)


def test_unverified_rule_is_disabled_not_dropped(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    _patch_entries(
        root,
        "tiers.json",
        [
            {
                "license_id": "MIT",
                "tier": "permissive",
                "obligations": [],
                "anchor": {"source": "x", "ref": "y"},
                "verified": False,
                "checked_on": "2026-10-17",
            }
        ],
    )
    ruleset = loader.load_ruleset(explicit=root)
    assert ruleset.entries("tiers.json") == []
    assert any(item.get("reasons") == ["not_verified"] for item in ruleset.disabled)


def test_rule_without_anchor_is_disabled(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    _patch_entries(
        root,
        "tiers.json",
        [
            {
                "license_id": "MIT",
                "tier": "permissive",
                "obligations": [],
                "verified": True,
                "checked_on": "2026-10-17",
            }
        ],
    )
    ruleset = loader.load_ruleset(explicit=root)
    assert ruleset.entries("tiers.json") == []
    assert any("anchor_missing" in item.get("reasons", []) for item in ruleset.disabled)


def test_rule_without_checked_on_is_disabled(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    _patch_entries(
        root,
        "tiers.json",
        [
            {
                "license_id": "MIT",
                "tier": "permissive",
                "obligations": [],
                "anchor": {"source": "x", "ref": "y"},
                "verified": True,
            }
        ],
    )
    ruleset = loader.load_ruleset(explicit=root)
    assert any("checked_on_missing" in item.get("reasons", []) for item in ruleset.disabled)


def test_anchor_with_blank_ref_is_disabled(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    _patch_entries(
        root,
        "tiers.json",
        [
            {
                "license_id": "MIT",
                "tier": "permissive",
                "obligations": [],
                "anchor": {"source": "x", "ref": "   "},
                "verified": True,
                "checked_on": "2026-10-17",
            }
        ],
    )
    ruleset = loader.load_ruleset(explicit=root)
    assert any("anchor_missing" in item.get("reasons", []) for item in ruleset.disabled)


def test_trove_map_uses_source_url_policy(tmp_path):
    """映射表没有许可证原文锚点，硬门是 source_url 而不是 anchor。"""
    root = make_ruleset_dir(str(tmp_path / "rs"))
    _patch_entries(
        root,
        "trove-map.json",
        [
            {
                "classifier": "License :: OSI Approved :: MIT License",
                "spdx_id": "MIT",
                "checked_on": "2026-10-17",
            }
        ],
    )
    ruleset = loader.load_ruleset(explicit=root)
    assert ruleset.entries("trove-map.json") == []
    assert any("source_url_missing" in item.get("reasons", []) for item in ruleset.disabled)


def test_trove_map_with_source_url_is_enabled(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    ruleset = loader.load_ruleset(explicit=root)
    assert len(ruleset.entries("trove-map.json")) == 1


def test_obligations_document_has_no_anchor_requirement(tmp_path):
    """义务项定义表是命名文档，不参与判定，不应被 anchor 门拦下。"""
    root = make_ruleset_dir(str(tmp_path / "rs"))
    ruleset = loader.load_ruleset(explicit=root)
    assert len(ruleset.entries("obligations.json")) == 2
    assert ruleset.disabled == []


def test_summary_counts_enabled_and_disabled(tmp_path):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    ruleset = loader.load_ruleset(explicit=root)
    summary = ruleset.summary()
    assert summary["ruleset_version"] == "r0.1.0-test"
    assert summary["license_list_version"] == "3.29.0"
    assert summary["disabled"] == 0
    assert summary["enabled"]["tiers.json"] == 1


def test_repo_has_no_ruleset_yet():
    """骨架阶段仓库里不应有 manifest.json —— 否则 exit 3 的语义就失真了。"""
    manifest = os.path.join(
        loader.repo_root_from_package(), "references", "ruleset", "manifest.json"
    )
    assert not os.path.isfile(manifest), (
        "骨架阶段不应存在规则包 manifest；M1 生成后再更新本断言"
    )
