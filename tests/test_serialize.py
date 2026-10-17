# -*- coding: utf-8 -*-
"""序列化的确定性契约（K6）。

同输入双跑逐字节一致；字段序稳定；CSV 无 BOM、LF 行尾；未知格式产物被拒绝。
"""

import io
import json
import os

import pytest

from licaudit import contract
from licaudit import serialize
from licaudit.errors import UsageError


def test_json_dumps_is_stable_across_runs():
    payload = {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "dependencies": [
            {"package": "example-pkg-a", "version": "1.0.0", "spdx_id": "MIT"},
            {"package": "example-pkg-b", "version": "2.0.0", "spdx_id": "Apache-2.0"},
        ],
        "notes": "中文内容不转义",
    }
    first = serialize.dumps_json(payload)
    second = serialize.dumps_json(payload)
    assert first == second


def test_json_dumps_keeps_chinese_readable():
    text = serialize.dumps_json({"note": "保留中文"})
    assert "保留中文" in text
    assert "\\u" not in text


def test_json_dumps_uses_lf_and_trailing_newline():
    text = serialize.dumps_json({"a": 1})
    assert "\r" not in text
    assert text.endswith("\n")
    assert not text.endswith("\n\n")


def test_json_dumps_preserves_insertion_order():
    payload = {"z": 1, "a": 2, "m": 3}
    text = serialize.dumps_json(payload)
    assert text.index('"z"') < text.index('"a"') < text.index('"m"')


def test_write_text_atomic_is_byte_identical(tmp_path):
    path = str(tmp_path / "a.json")
    serialize.write_text_atomic(path, "hello\n")
    with io.open(path, "rb") as stream:
        assert stream.read() == b"hello\n"


def test_write_json_has_no_bom(tmp_path):
    path = str(tmp_path / "a.json")
    serialize.write_json(path, {"k": "中文"})
    with io.open(path, "rb") as stream:
        raw = stream.read()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert raw.endswith(b"\n")


def test_csv_columns_and_line_endings():
    rows = [
        {
            "package": "example-pkg-a",
            "version": "1.0.0",
            "spdx_id": "MIT",
            "tier": "permissive",
            "scenario": "saas",
            "verdict": "not_triggered",
            "action_level": "declare",
            "basis_clause": "MIT §1",
            "declaration_location": "package.json:12",
            "notes": "",
        }
    ]
    text = serialize.dumps_csv(rows, contract.REPORT_CSV_COLUMNS)
    assert "\r" not in text
    assert not text.startswith("\ufeff")
    header = text.split("\n")[0]
    assert header == ",".join(contract.REPORT_CSV_COLUMNS)


def test_csv_missing_field_becomes_empty_not_none():
    rows = [{"package": "example-pkg-a"}]
    text = serialize.dumps_csv(rows, ("package", "version", "notes"))
    assert "None" not in text
    assert text.split("\n")[1] == "example-pkg-a,,"


def test_load_artifact_rejects_unknown_format(tmp_path):
    path = str(tmp_path / "x.json")
    serialize.write_json(path, {"format": "something-else", "format_version": 1})
    with pytest.raises(UsageError):
        serialize.load_artifact(path, (contract.INVENTORY_FORMAT,))


def test_load_artifact_rejects_unknown_version(tmp_path):
    path = str(tmp_path / "x.json")
    serialize.write_json(
        path, {"format": contract.INVENTORY_FORMAT, "format_version": 99}
    )
    with pytest.raises(UsageError):
        serialize.load_artifact(path, (contract.INVENTORY_FORMAT,))


def test_load_artifact_accepts_known_format(tmp_path):
    path = str(tmp_path / "x.json")
    serialize.write_json(
        path, {"format": contract.INVENTORY_FORMAT, "format_version": 1, "dependencies": []}
    )
    payload = serialize.load_artifact(path, (contract.INVENTORY_FORMAT,))
    assert payload["dependencies"] == []


def test_load_artifact_rejects_missing_file(tmp_path):
    with pytest.raises(UsageError):
        serialize.load_artifact(str(tmp_path / "nope.json"), (contract.INVENTORY_FORMAT,))


def test_load_artifact_rejects_broken_json(tmp_path):
    path = str(tmp_path / "bad.json")
    with io.open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write("{not json")
    with pytest.raises(UsageError):
        serialize.load_artifact(path, (contract.INVENTORY_FORMAT,))


def test_status_artifact_is_reproducible(tmp_path):
    from licaudit import pipeline

    summary = {
        "package_version": "0.1.0",
        "ruleset_version": "r0.1.0",
        "license_list_version": "3.29.0",
        "enabled": {"tiers.json": 1},
        "disabled": 0,
    }
    first = pipeline.write_status_artifact(summary, str(tmp_path / "o1"))
    second = pipeline.write_status_artifact(summary, str(tmp_path / "o2"))
    with io.open(first, "rb") as stream:
        left = stream.read()
    with io.open(second, "rb") as stream:
        right = stream.read()
    assert left == right


def test_status_artifact_fields_are_stable(tmp_path):
    from licaudit import pipeline

    summary = {
        "package_version": "0.1.0",
        "ruleset_version": "r0.1.0",
        "license_list_version": "3.29.0",
        "enabled": {},
        "disabled": 0,
    }
    path = pipeline.write_status_artifact(summary, str(tmp_path / "o"))
    with io.open(path, encoding="utf-8") as stream:
        payload = json.load(stream)
    assert list(payload) == [
        "format",
        "format_version",
        "package_version",
        "ruleset_version",
        "license_list_version",
        "enabled",
        "disabled",
    ]
