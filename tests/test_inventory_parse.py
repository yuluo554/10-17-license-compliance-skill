# -*- coding: utf-8 -*-
"""M1 解析器：四级可信度链、SPDX 表达式、六种清单形态。

覆盖顺序与 ``plan/03-模块详设.md`` M1 一致：
1.1 输入识别 / 1.2 记录结构 / 1.3 四级链 / 1.4 表达式 / 1.5 拒绝条件 / 1.6 输出门禁。
"""

import io
import os

import pytest

from _helpers import REPO_ROOT

from licaudit.errors import UsageError
from licaudit.inventory import manifests
from licaudit.inventory.normalize import FALLBACK_TEXT_LIMIT, normalize_license
from licaudit.inventory.spdx_expr import (
    ExprError,
    SpdxIndex,
    anchored_first_line,
    family_version_of,
    normalize_for_anchor,
    parse_expression,
)
from licaudit.inventory.spdx_snapshot import load_snapshot

LICENSES, EXCEPTIONS, _MANIFEST = load_snapshot()
INDEX = SpdxIndex(LICENSES, EXCEPTIONS)
TROVE_MAP = [
    {"classifier": "License :: OSI Approved :: MIT License", "spdx_id": "MIT"},
    {"classifier": "License :: OSI Approved :: BSD License", "spdx_id": "BSD-3-Clause"},
]


def norm(raw, classifiers=None, structured=True):
    return normalize_license(
        raw, INDEX, trove_classifiers=classifiers, trove_map=TROVE_MAP,
        structured=structured,
    )


# ---------------------------------------------------------------------------
# 四级可信度链（K1）
# ---------------------------------------------------------------------------


def test_confidence_levels_are_exactly_four():
    from licaudit import contract

    assert contract.CONFIDENCE_LEVELS == (
        "license_expression",
        "trove_classifier",
        "license_first_line",
        "truncated_fallback",
    )


def test_expression_wins_over_trove_and_first_line():
    result = norm("MIT", classifiers=["License :: OSI Approved :: BSD License"])
    assert result.confidence == "license_expression"
    assert result.spdx_id == "MIT"


def test_trove_used_only_when_expression_unavailable():
    result = norm(None, classifiers=["License :: OSI Approved :: MIT License"])
    assert result.confidence == "trove_classifier"
    assert result.spdx_id == "MIT"


def test_trove_is_not_fuzzy_matched():
    result = norm(None, classifiers=["License :: OSI Approved :: MIT-ish License"])
    assert result.confidence == "truncated_fallback"
    assert result.spdx_id is None


def test_first_line_used_when_no_expression_no_trove():
    result = norm("Apache-2.0\n\nFull text follows")
    assert result.confidence == "license_first_line"
    assert result.spdx_id == "Apache-2.0"


def test_chain_stops_at_first_hit_no_merging():
    """命中即停：表达式成功时不再叠加 trove/首行的任何结论。"""
    result = norm("Apache-2.0", classifiers=["License :: OSI Approved :: MIT License"])
    assert result.spdx_id == "Apache-2.0"
    assert result.flags == []


# ---------------------------------------------------------------------------
# K2：禁全文关键词匹配
# ---------------------------------------------------------------------------


def test_long_first_line_is_not_matched():
    long_line = "MIT " + ("x" * (FALLBACK_TEXT_LIMIT + 10))
    result = norm(long_line)
    assert result.spdx_id is None
    assert result.confidence == "truncated_fallback"


def test_anchor_length_gate_rejects_over_200():
    """直接锁 200 字符门。

    空白会被归一化折叠，所以「在 ID 与 License 之间塞满空格」的原始行虽然超长，
    归一化后仍等于 ``mit-license`` —— 拦住它的**只有**长度门。去掉上限时这条会红。
    """
    over_limit = "MIT" + " " * (FALLBACK_TEXT_LIMIT + 10) + "License"
    assert len(over_limit) > FALLBACK_TEXT_LIMIT
    assert normalize_for_anchor(over_limit) == "mit-license"
    assert anchored_first_line(over_limit, INDEX) == (None, [])

    # 对照：同样结构但长度在门内的文本会命中
    within_limit = "MIT License"
    assert anchored_first_line(within_limit, INDEX)[0] == "MIT"


def test_line_exactly_200_chars_still_matches():
    """边界内侧：正好 200 字符仍然允许命中（上限是 >200 才拒绝）。"""
    line = "MIT License" + " " * (FALLBACK_TEXT_LIMIT - len("MIT License"))
    assert len(line) == FALLBACK_TEXT_LIMIT
    assert anchored_first_line(line, INDEX)[0] == "MIT"


def test_first_line_exactly_at_limit_is_still_considered():
    padded = "MIT" + " " * (FALLBACK_TEXT_LIMIT - 3)
    matched, flags = anchored_first_line(padded, INDEX)
    assert matched == "MIT"


def test_full_text_mention_of_mit_does_not_match():
    """pandas 形态：首行不是 ID，正文里出现 MIT 字样。"""
    text = "Some proprietary notice\n\nYou may not use MIT or any other license.\n"
    result = norm(text)
    assert result.spdx_id is None
    assert result.confidence == "truncated_fallback"


def test_pandas_trap_first_line_is_bsd3():
    import json

    path = os.path.join(REPO_ROOT, "references", "curated", "trap-packages.json")
    with io.open(path, encoding="utf-8") as stream:
        traps = json.load(stream)
    pandas = next(item for item in traps["entries"] if item["package"] == "pandas")
    text = pandas["license"]
    assert len(text) > 60000
    assert text.count("MIT") >= 30

    result = norm(text)
    assert result.confidence == "license_first_line"
    assert result.spdx_id == "BSD-3-Clause"

    # 阴性对照：正文不动，只改首行 → 不再命中
    mutated = "Example Proprietary License\n" + text.split("\n", 1)[1]
    assert norm(mutated).spdx_id is None


def test_truncated_fallback_keeps_first_200_chars_only():
    text = "Custom License " + ("z" * 400)
    result = norm(text)
    assert result.confidence == "truncated_fallback"
    assert len(result.raw_license) == FALLBACK_TEXT_LIMIT
    assert result.needs_confirmation is True


# ---------------------------------------------------------------------------
# K3：版本语义
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spdx_id", ["GPL-2.0-only", "GPL-3.0-or-later", "LGPL-2.1-only"])
def test_only_and_or_later_are_preserved(spdx_id):
    result = norm(spdx_id)
    assert result.spdx_id == spdx_id


def test_family_name_without_version_becomes_unknown():
    result = norm("GPL")
    assert result.spdx_id == "GPL-unknown"
    assert "family-unknown" in result.flags
    assert result.needs_confirmation is True


@pytest.mark.parametrize("text", ["Apache", "BSD", "LGPL", "AGPL", "MPL"])
def test_all_families_map_to_unknown(text):
    result = norm(text)
    assert result.spdx_id == text + "-unknown"


def test_family_version_without_only_or_later_is_flagged():
    spdx_id, ambiguous = family_version_of("GPL v3", INDEX)
    assert spdx_id == "GPL-3.0"
    assert ambiguous is True


def test_lowercase_operators_are_not_treated_as_operators():
    result = norm("MIT or Apache-2.0")
    assert result.confidence != "license_expression"


# ---------------------------------------------------------------------------
# K4：WITH 例外
# ---------------------------------------------------------------------------


def test_known_exception_is_accepted():
    result = norm("GPL-2.0-only WITH Classpath-exception-2.0")
    assert result.spdx_id == "GPL-2.0-only WITH Classpath-exception-2.0"
    assert "unknown-exception" not in result.flags


def test_unknown_exception_keeps_expression_but_flags():
    result = norm("GPL-2.0-only WITH Not-A-Real-Exception-9.9")
    assert result.spdx_id == "GPL-2.0-only WITH Not-A-Real-Exception-9.9"
    assert "unknown-exception" in result.flags
    assert result.needs_confirmation is True


# ---------------------------------------------------------------------------
# 表达式解析
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text,expected",
    [
        ("MIT", "MIT"),
        ("MIT OR Apache-2.0", "MIT OR Apache-2.0"),
        ("MIT   AND   Apache-2.0", "MIT AND Apache-2.0"),
        ("(MIT OR Apache-2.0) AND BSD-3-Clause", "(MIT OR Apache-2.0) AND BSD-3-Clause"),
        ("GPL-2.0-only WITH Classpath-exception-2.0",
         "GPL-2.0-only WITH Classpath-exception-2.0"),
    ],
)
def test_expression_normalization(text, expected):
    assert parse_expression(text, INDEX).text == expected


def test_operator_order_is_not_rearranged():
    parsed = parse_expression("Apache-2.0 OR MIT", INDEX)
    assert parsed.text == "Apache-2.0 OR MIT"
    assert parsed.atoms == ["Apache-2.0", "MIT"]


@pytest.mark.parametrize(
    "text",
    ["", "   ", "MIT AND", "(MIT", "MIT)", "MIT Apache-2.0", "and MIT"],
)
def test_malformed_expressions_raise(text):
    with pytest.raises(ExprError):
        parse_expression(text, INDEX)


def test_unknown_identifier_raises_in_strict_parse():
    with pytest.raises(ExprError):
        parse_expression("Not-A-License 1.0", INDEX)


# ---------------------------------------------------------------------------
# package.json / lock
# ---------------------------------------------------------------------------


def _write(tmp_path, name, text):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return str(path)


def test_package_json_parses_all_dependency_blocks(tmp_path):
    path = _write(tmp_path, "package.json", """{
  "dependencies": {"example-pkg-a": {"version": "1.0.0", "license": "MIT"}},
  "devDependencies": {"example-pkg-b": "2.0.0"},
  "peerDependencies": {"example-pkg-c": "3.0.0"},
  "optionalDependencies": {"example-pkg-d": "4.0.0"}
}
""")
    parsed = manifests.parse_manifest(path)
    packages = sorted(record["package"] for record in parsed.records)
    assert packages == ["example-pkg-a", "example-pkg-b", "example-pkg-c", "example-pkg-d"]


def test_package_json_licenses_array_merges_with_and(tmp_path):
    path = _write(tmp_path, "package.json", """{
  "dependencies": {
    "example-pkg-a": {
      "version": "1.0.0",
      "licenses": [{"type": "MIT"}, {"type": "Apache-2.0"}]
    }
  }
}
""")
    parsed = manifests.parse_manifest(path)
    assert parsed.records[0]["raw_license"] == "MIT AND Apache-2.0"


def test_package_json_root_license_is_not_inherited(tmp_path):
    path = _write(tmp_path, "package.json", """{
  "name": "example-app",
  "license": "MIT",
  "dependencies": {"example-pkg-a": "1.0.0"}
}
""")
    parsed = manifests.parse_manifest(path)
    assert parsed.records[0]["raw_license"] is None
    assert any(note["code"] == "root_license_ignored" for note in parsed.notes)


def test_lock_v2_v3_skips_root_package(tmp_path):
    for version in (2, 3):
        name = "package-lock.json"
        path = _write(tmp_path, name, """{
  "lockfileVersion": %d,
  "packages": {
    "": {"name": "example-app", "version": "1.0.0", "license": "MIT"},
    "node_modules/example-pkg-a": {"version": "1.0.0", "license": "MIT"}
  }
}
""" % version)
        parsed = manifests.parse_manifest(path)
        packages = [record["package"] for record in parsed.records]
        assert packages == ["example-pkg-a"], "v{0} 应跳过根包".format(version)


def test_lock_v1_uses_dependencies_tree(tmp_path):
    path = _write(tmp_path, "package-lock.json", """{
  "lockfileVersion": 1,
  "dependencies": {
    "example-pkg-a": {
      "version": "1.0.0",
      "license": "MIT",
      "dependencies": {"example-pkg-b": {"version": "2.0.0", "license": "ISC"}}
    }
  }
}
""")
    parsed = manifests.parse_manifest(path)
    packages = sorted(record["package"] for record in parsed.records)
    assert packages == ["example-pkg-a", "example-pkg-b"]


def test_unsupported_lockfile_version_is_usage_error(tmp_path):
    path = _write(tmp_path, "package-lock.json", '{"lockfileVersion": 9, "packages": {}}')
    with pytest.raises(UsageError) as excinfo:
        manifests.parse_manifest(path)
    assert "lockfileVersion" in str(excinfo.value)


# ---------------------------------------------------------------------------
# requirements.txt
# ---------------------------------------------------------------------------


def test_requirements_handles_versions_extras_comments_and_includes(tmp_path):
    path = _write(tmp_path, "requirements.txt", """# comment
example-pkg-a==1.0.0  # license: MIT
example-pkg-b[extra]==2.0.0
example-pkg-c>=3.0
-r dev.txt
-e git+https://example.invalid/x.git#egg=y
""")
    parsed = manifests.parse_manifest(path)
    by_name = {record["package"]: record for record in parsed.records}
    assert by_name["example-pkg-a"]["version"] == "1.0.0"
    assert by_name["example-pkg-a"]["raw_license"] == "MIT"
    assert by_name["example-pkg-b"]["version"] == "2.0.0"
    assert by_name["example-pkg-c"]["version"] is None
    codes = {note["code"] for note in parsed.notes}
    assert "requirements_include_ignored" in codes
    assert "requirements_editable_ignored" in codes


# ---------------------------------------------------------------------------
# pyproject.toml
# ---------------------------------------------------------------------------


def test_pyproject_pep621_and_optional_dependencies(tmp_path):
    path = _write(tmp_path, "pyproject.toml", """[project]
name = "example-app"
license = { text = "MIT" }
dependencies = [
  "example-pkg-a==1.0.0",
  { name = "example-pkg-b", version = "2.0.0", license = "Apache-2.0" },
]

[project.optional-dependencies]
test = ["example-pkg-c==3.0.0"]
""")
    parsed = manifests.parse_manifest(path)
    packages = sorted(record["package"] for record in parsed.records)
    assert packages == ["example-pkg-a", "example-pkg-b", "example-pkg-c"]


def test_pyproject_poetry_dependencies(tmp_path):
    path = _write(tmp_path, "pyproject.toml", """[tool.poetry.dependencies]
python = "^3.8"
example-pkg-a = { version = "1.0.0", license = "MIT" }
example-pkg-b = "^2.0.0"
""")
    parsed = manifests.parse_manifest(path)
    names = sorted(record["package"] for record in parsed.records)
    assert names == ["example-pkg-a", "example-pkg-b"]
    by_name = {record["package"]: record for record in parsed.records}
    assert by_name["example-pkg-b"]["version"] == "2.0.0"


def test_pyproject_unsupported_toml_is_usage_error(tmp_path):
    path = _write(tmp_path, "pyproject.toml", """[project]
dependencies = [
  { name = "a", version = "1" },
  { name = "b", version = "2" },
]

[[tool.poetry.source]]
name = "x"
""")
    with pytest.raises(UsageError) as excinfo:
        manifests.parse_manifest(path)
    assert "TOML" in str(excinfo.value)


# ---------------------------------------------------------------------------
# go.mod / pom.xml
# ---------------------------------------------------------------------------


def test_go_mod_block_and_single_line(tmp_path):
    path = _write(tmp_path, "go.mod", """module example.com/app

require (
\texample.com/pkg/a v1.0.0 // license: MIT
\texample.com/pkg/b v2.0.0
)

require example.com/pkg/c v3.0.0
""")
    parsed = manifests.parse_manifest(path)
    by_name = {record["package"]: record for record in parsed.records}
    assert sorted(by_name) == ["example.com/pkg/a", "example.com/pkg/b", "example.com/pkg/c"]
    assert by_name["example.com/pkg/a"]["raw_license"] == "MIT"


def test_pom_parses_dependencies_and_ignores_project_licenses(tmp_path):
    path = _write(tmp_path, "pom.xml", """<project>
  <licenses><license><name>Apache-2.0</name></license></licenses>
  <dependencies>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>pkg-a</artifactId>
      <version>1.0.0</version>
      <license>MIT</license>
    </dependency>
    <dependency>
      <groupId>com.example</groupId>
      <artifactId>pkg-b</artifactId>
      <version>2.0.0</version>
    </dependency>
  </dependencies>
</project>
""")
    parsed = manifests.parse_manifest(path)
    by_name = {record["package"]: record for record in parsed.records}
    assert sorted(by_name) == ["com.example:pkg-a", "com.example:pkg-b"]
    assert by_name["com.example:pkg-a"]["raw_license"] == "MIT"
    assert by_name["com.example:pkg-b"]["raw_license"] is None
    assert any(note["code"] == "root_license_ignored" for note in parsed.notes)


# ---------------------------------------------------------------------------
# 1.5 拒绝条件
# ---------------------------------------------------------------------------


def test_unknown_file_name_is_usage_error(tmp_path):
    path = _write(tmp_path, "deps.txt", "example-pkg-a==1.0.0")
    with pytest.raises(UsageError) as excinfo:
        manifests.parse_manifest(path)
    message = str(excinfo.value)
    assert "受支持" in message
    for name in ("package.json", "requirements.txt", "go.mod", "pom.xml"):
        assert name in message


def test_empty_file_is_usage_error(tmp_path):
    path = _write(tmp_path, "requirements.txt", "   \n\n")
    with pytest.raises(UsageError):
        manifests.parse_manifest(path)


def test_non_utf8_file_is_usage_error(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_bytes(b"example-pkg-a==1.0.0\n\xff\xfe\n")
    with pytest.raises(UsageError) as excinfo:
        manifests.parse_manifest(str(path))
    assert "UTF-8" in str(excinfo.value)


def test_utf8_bom_is_stripped(tmp_path):
    path = tmp_path / "requirements.txt"
    path.write_bytes(b"\xef\xbb\xbfexample-pkg-a==1.0.0\n")
    parsed = manifests.parse_manifest(str(path))
    assert parsed.records[0]["package"] == "example-pkg-a"


# ---------------------------------------------------------------------------
# 记录结构
# ---------------------------------------------------------------------------


def test_record_carries_locator_and_line(tmp_path):
    path = _write(tmp_path, "package.json", """{
  "dependencies": {
    "example-pkg-a": {"version": "1.0.0", "license": "MIT"}
  }
}
""")
    parsed = manifests.parse_manifest(path)
    record = parsed.records[0]
    assert record["locator"] == "dependencies.example-pkg-a"
    assert record["line"] == 3
    assert record["source_file"] == "package.json"
