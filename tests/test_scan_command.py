# -*- coding: utf-8 -*-
"""``scan`` 命令：产物形态、退出码、确定性、单件隔离（K29 / K30）。"""

import io
import json
import os

import pytest

from _helpers import REPO_ROOT, make_ruleset_dir

from licaudit import cli, contract
from licaudit.exit_codes import EXIT_OK, EXIT_RULESET, EXIT_USAGE

SYNTHETIC = os.path.join(REPO_ROOT, "data", "synthetic")


def run(argv, capsys=None):
    code = cli.main(argv)
    out = err = ""
    if capsys is not None:
        captured = capsys.readouterr()
        out, err = captured.out, captured.err
    return code, out, err


def write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def read_json(path):
    with io.open(path, encoding="utf-8") as stream:
        return json.load(stream)


def test_scan_writes_inventory_with_contract_fields(tmp_path, capsys):
    manifest = write(tmp_path, "package.json", """{
  "dependencies": {
    "example-pkg-a": {"version": "1.0.0", "license": "MIT"}
  }
}
""")
    out_dir = tmp_path / "out"
    code, out, err = run(["scan", manifest, "--out-dir", str(out_dir)], capsys)
    assert code == EXIT_OK, out + err

    payload = read_json(str(out_dir / "inventory.json"))
    assert payload["format"] == contract.INVENTORY_FORMAT
    assert payload["format_version"] == contract.FORMAT_VERSION
    assert payload["ruleset_version"]
    assert payload["license_list_version"]

    record = payload["dependencies"][0]
    assert tuple(record) == contract.INVENTORY_RECORD_FIELDS
    assert record["spdx_id"] == "MIT"
    assert record["confidence"] == "license_expression"
    assert record["evidence"]["ruleset_version"] == payload["ruleset_version"]
    assert record["evidence"]["details_url"].startswith("https://spdx.org/licenses/MIT")


def test_scan_is_byte_stable_across_runs(tmp_path, capsys):
    manifest = str(os.path.join(SYNTHETIC, "npm-basic", "package.json"))
    first = tmp_path / "a"
    second = tmp_path / "b"
    assert run(["scan", manifest, "--out-dir", str(first)], capsys)[0] == EXIT_OK
    assert run(["scan", manifest, "--out-dir", str(second)], capsys)[0] == EXIT_OK
    left = (first / "inventory.json").read_bytes()
    right = (second / "inventory.json").read_bytes()
    assert left == right


def test_scan_text_has_no_bom_and_uses_lf(tmp_path, capsys):
    manifest = str(os.path.join(SYNTHETIC, "npm-basic", "package.json"))
    out_dir = tmp_path / "out"
    assert run(["scan", manifest, "--out-dir", str(out_dir)], capsys)[0] == EXIT_OK
    raw = (out_dir / "inventory.json").read_bytes()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")


def test_scan_without_ruleset_still_exits_three(tmp_path, capsys, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    manifest = write(tmp_path, "package.json", '{"dependencies": {}}')
    monkeypatch.chdir(str(tmp_path))
    monkeypatch.delenv("LICAUDIT_RULES_DIR", raising=False)
    code, _out, err = run(
        ["--rules-dir", str(empty), "scan", manifest, "--out-dir", str(tmp_path / "o")],
        capsys,
    )
    assert code == EXIT_RULESET
    assert "规则包" in err


def test_scan_unknown_manifest_name_is_usage_error(tmp_path, capsys):
    manifest = write(tmp_path, "deps.txt", "example-pkg-a==1.0.0")
    code, _out, err = run(
        ["scan", manifest, "--out-dir", str(tmp_path / "o")], capsys
    )
    assert code == EXIT_USAGE
    assert "受支持" in err


def test_scan_missing_file_is_usage_error(tmp_path, capsys):
    code, _out, err = run(
        ["scan", str(tmp_path / "package.json"), "--out-dir", str(tmp_path / "o")], capsys
    )
    assert code == EXIT_USAGE


def test_scan_isolates_single_bad_record(tmp_path, capsys):
    """单件失败隔离：一条坏记录不阻断整批（K30）。"""
    manifest = write(tmp_path, "package.json", """{
  "dependencies": {
    "example-pkg-a": {"version": "1.0.0", "license": "MIT"},
    "example-pkg-b": {"version": "2.0.0"},
    "example-pkg-c": {"version": "3.0.0", "license": "Apache-2.0"}
  }
}
""")
    out_dir = tmp_path / "out"
    code, out, err = run(["scan", manifest, "--out-dir", str(out_dir)], capsys)
    assert code == EXIT_OK, out + err
    payload = read_json(str(out_dir / "inventory.json"))
    resolved = [item["package"] for item in payload["dependencies"]]
    assert resolved == ["example-pkg-a", "example-pkg-c"]
    pending = [entry["record"]["package"] for entry in payload["pending_confirmation"]]
    assert "example-pkg-b" in pending


def test_scan_pending_entry_explains_missing_evidence(tmp_path, capsys):
    manifest = write(tmp_path, "package.json", """{
  "dependencies": {"example-pkg-b": {"version": "2.0.0"}}
}
""")
    out_dir = tmp_path / "out"
    assert run(["scan", manifest, "--out-dir", str(out_dir)], capsys)[0] == EXIT_OK
    payload = read_json(str(out_dir / "inventory.json"))
    entry = payload["pending_confirmation"][0]
    assert entry["record"]["spdx_id"] is None
    assert entry["record"]["confidence"] == "truncated_fallback"
    assert "evidence.details_url" in entry["missing"]


def test_scan_multiple_files_records_sources(tmp_path, capsys):
    first = write(tmp_path, "package.json", """{
  "dependencies": {"example-pkg-a": {"version": "1.0.0", "license": "MIT"}}
}
""")
    second = write(tmp_path, "requirements.txt", "example-pkg-b==2.0.0  # license: ISC\n")
    out_dir = tmp_path / "out"
    assert run(["scan", first, second, "--out-dir", str(out_dir)], capsys)[0] == EXIT_OK
    payload = read_json(str(out_dir / "inventory.json"))
    assert payload["source_files"] == ["package.json", "requirements.txt"]
    files = sorted(item["evidence"]["file"] for item in payload["dependencies"])
    assert files == ["package.json", "requirements.txt"]


def test_scan_records_parse_notes_for_ignored_lines(tmp_path, capsys):
    manifest = write(tmp_path, "requirements.txt", "-r other.txt\nexample-pkg-a==1.0.0\n")
    out_dir = tmp_path / "out"
    assert run(["scan", manifest, "--out-dir", str(out_dir)], capsys)[0] == EXIT_OK
    payload = read_json(str(out_dir / "inventory.json"))
    codes = {note["code"] for note in payload["parse_notes"]}
    assert "requirements_include_ignored" in codes


def test_scan_unknown_family_has_no_fabricated_details_url(tmp_path, capsys):
    manifest = write(tmp_path, "package.json", """{
  "dependencies": {"example-pkg-a": {"version": "1.0.0", "license": "GPL"}}
}
""")
    out_dir = tmp_path / "out"
    assert run(["scan", manifest, "--out-dir", str(out_dir)], capsys)[0] == EXIT_OK
    payload = read_json(str(out_dir / "inventory.json"))
    entry = payload["pending_confirmation"][0]
    assert entry["record"]["spdx_id"] == "GPL-unknown"
    assert entry["record"]["evidence"]["details_url"] is None


def test_scan_uses_explicit_rules_dir(tmp_path, capsys):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    manifest = write(tmp_path, "package.json", """{
  "dependencies": {"example-pkg-a": {"version": "1.0.0", "license": "MIT"}}
}
""")
    out_dir = tmp_path / "out"
    code, _out, _err = run(
        ["--rules-dir", root, "scan", manifest, "--out-dir", str(out_dir)], capsys
    )
    assert code == EXIT_OK
    payload = read_json(str(out_dir / "inventory.json"))
    assert payload["dependencies"][0]["evidence"]["ruleset_version"] == "r0.1.0-test"
