# -*- coding: utf-8 -*-
"""M5 报告层：八章节顺序、MD/CSV 同源、免责声明逐字、AST 零判定守门。

「同源」不靠肉眼：CSV 的行即章节结构函数给出的「逐包明细」行，两个渲染器共用它。
AST 三条守门（import / BinOp / 内联判定表）在这里落地（plan/06 D13 / K23）。
"""

import ast
import io
import json
import os
import shutil

import pytest

from _helpers import REPO_ROOT, write_json

from licaudit import cli, contract
from licaudit.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_USAGE
from licaudit.report import REPORT_FILES
from licaudit.report import csv_render, markdown, sections
from licaudit.report.sections import build_report

REPORT_DIR = os.path.join(REPO_ROOT, "src", "licaudit", "report")
REPORT_MODULES = ("__init__.py", "sections.py", "markdown.py", "csv_render.py")
EXAMPLES_DIR = os.path.join(REPO_ROOT, "examples", "report")
SYNTHETIC_DIR = os.path.join(REPO_ROOT, "data", "synthetic", "example-project")
SPDX_DIR = os.path.join(REPO_ROOT, "references", "spdx")

# 示例项目的两份运行（单场景下四级处置无法同时出现，故给两份；见 plan/06 §五）。
EXAMPLE_RUNS = (
    {
        "name": "license-report",
        "scenario": "saas",
        "extra": ["--network-interaction", "yes"],
        "outbound": "Elastic-2.0",
        "note": "示例项目以 SaaS 形式对外提供服务",
    },
    {
        "name": "license-report-distribute",
        "scenario": "distribute-binary",
        "extra": [],
        "outbound": "MIT",
        "note": "示例项目分发二进制产物",
    },
)


def run(argv, capsys=None):
    code = cli.main(argv)
    out = err = ""
    if capsys is not None:
        captured = capsys.readouterr()
        out, err = captured.out, captured.err
    return code, out, err


def read_text(path):
    with io.open(path, encoding="utf-8") as stream:
        return stream.read()


def read_json(path):
    with io.open(path, encoding="utf-8") as stream:
        return json.load(stream)


def _example_manifests():
    names = ("package.json", "package-lock.json", "requirements.txt",
             "pyproject.toml", "go.mod", "pom.xml")
    return [os.path.join(SYNTHETIC_DIR, name) for name in names]


def _run_example(target, spec, formats=("md", "csv")):
    """跑一遍 scan → assess → report，返回 ``{格式: 产物路径}``。"""
    out_dir = os.path.join(str(target), spec["name"])
    code, out, err = run(["scan"] + _example_manifests() + ["--out-dir", out_dir])
    assert code == EXIT_OK, out + err
    argv = [
        "assess", "--inventory", os.path.join(out_dir, "inventory.json"),
        "--scenario", spec["scenario"], "--outbound-license", spec["outbound"],
        "--scenario-note", spec["note"], "--out-dir", out_dir,
    ]
    argv.extend(spec["extra"])
    run(argv)  # 有阻断级 → 1，属预期语义
    produced = {}
    for fmt in formats:
        run(["report", "--out-dir", out_dir, "--format", fmt])
        produced[fmt] = os.path.join(out_dir, REPORT_FILES[fmt])
    return produced


@pytest.fixture(scope="module")
def example_artifacts(tmp_path_factory):
    """示例项目的一份完整产物（读盘用；生成路径与入仓报告一致）。"""
    target = tmp_path_factory.mktemp("report")
    produced = _run_example(target, EXAMPLE_RUNS[0])
    out_dir = os.path.dirname(produced["md"])
    return {
        "profile": read_json(os.path.join(out_dir, "profile.json")),
        "scenario": read_json(os.path.join(out_dir, "scenario.json")),
        "conflicts": read_json(os.path.join(out_dir, "conflicts.json")),
        "actions": read_json(os.path.join(out_dir, "actions.json")),
    }


# ---------------------------------------------------------------------------
# 章节结构
# ---------------------------------------------------------------------------


def test_sections_follow_the_contract_order(example_artifacts):
    report = build_report(example_artifacts)
    titles = [section["title"] for section in report["sections"]]
    assert titles == list(contract.REPORT_SECTIONS)
    assert titles[-1] == "免责声明"


def test_every_section_is_rendered_in_markdown(example_artifacts):
    text = markdown.render_artifacts(example_artifacts)
    positions = [text.find("## " + title) for title in contract.REPORT_SECTIONS]
    assert all(position >= 0 for position in positions), positions
    assert positions == sorted(positions), "章节顺序不固定"


def test_disclaimer_is_verbatim(example_artifacts):
    text = markdown.render_artifacts(example_artifacts)
    assert contract.DISCLAIMER in text


def test_report_cites_the_judicial_anchor(example_artifacts):
    """M5 承诺：依据条款给出中国司法参照（罗盒案），只引用方向性结论。"""
    text = markdown.render_artifacts(example_artifacts)
    assert "（2021）最高法知民终2063号" in text
    assert "不构成法律意见" in text


def test_markdown_contains_every_package_row(example_artifacts):
    report = build_report(example_artifacts)
    text = markdown.render_artifacts(example_artifacts)
    assert len(report["rows"]) == len(example_artifacts["actions"]["actions"])
    for row in report["rows"]:
        assert row["package"] in text


def test_pending_section_unions_all_artifacts(example_artifacts):
    report = build_report(example_artifacts)
    sources = {item["source"] for item in report["pending"]}
    assert "actions" in sources
    assert report["pending"], "示例项目应至少有一条待人工确认项"


# ---------------------------------------------------------------------------
# CSV 契约
# ---------------------------------------------------------------------------


def test_csv_columns_match_contract(example_artifacts):
    text = csv_render.render_artifacts(example_artifacts)
    header = text.split("\n")[0]
    assert header == ",".join(contract.REPORT_CSV_COLUMNS)


def test_csv_rows_are_the_same_source_as_the_detail_section(example_artifacts):
    report = build_report(example_artifacts)
    rows = csv_render.rows_of(example_artifacts)
    detail = [section for section in report["sections"] if section["title"] == "逐包明细"][0]
    assert rows == detail["data"]
    assert len(rows) == len(report["rows"])


def test_csv_has_no_bom_and_lf_endings(tmp_path):
    target = tmp_path / "out"
    produced = _run_example(target, EXAMPLE_RUNS[1], formats=("csv",))
    raw = open(produced["csv"], "rb").read()
    assert not raw.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" not in raw
    assert raw.endswith(b"\n")


def test_csv_columns_are_stable_across_formats(example_artifacts):
    """MD 明细表的列序与 CSV 列序一致（同一份列定义）。"""
    report = build_report(example_artifacts)
    detail = [section for section in report["sections"] if section["title"] == "逐包明细"][0]
    assert list(detail["columns"]) == list(contract.REPORT_CSV_COLUMNS)


# ---------------------------------------------------------------------------
# 确定性与输入处理
# ---------------------------------------------------------------------------


def test_report_is_byte_stable_across_two_runs(tmp_path):
    first = _run_example(tmp_path / "a", EXAMPLE_RUNS[0])
    second = _run_example(tmp_path / "b", EXAMPLE_RUNS[0])
    for fmt in ("md", "csv"):
        assert open(first[fmt], "rb").read() == open(second[fmt], "rb").read(), fmt


def test_unknown_fields_are_ignored(example_artifacts):
    """报告只消费契约字段：多出来的字段既不该崩，也不该改变输出。"""
    baseline = markdown.render_artifacts(example_artifacts)
    mutated = {key: dict(value) for key, value in example_artifacts.items()}
    mutated["actions"]["unknown_section"] = {"x": 1}
    mutated["actions"]["actions"][0]["unknown_field"] = "should-be-ignored"
    assert markdown.render_artifacts(mutated) == baseline


def test_report_without_artifacts_is_usage_error(tmp_path, capsys):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    code, out, err = run(["report", "--out-dir", str(out_dir)], capsys)
    assert code == EXIT_USAGE
    assert "不存在" in err


def test_report_rejects_artifact_of_wrong_format(tmp_path, capsys):
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    write_json(str(out_dir / "profile.json"), {"format": "licaudit-nope", "format_version": 1})
    code, out, err = run(["report", "--out-dir", str(out_dir)], capsys)
    assert code == EXIT_USAGE
    assert "格式" in err


def test_report_exit_code_excludes_pending_only_when_nothing_is_pending(tmp_path):
    """只有 declare / ok 且无待确认 → 0（§5.5）。"""
    out_dir = tmp_path / "out"
    out_dir.mkdir()
    write_json(str(out_dir / "inventory.json"), {
        "format": contract.INVENTORY_FORMAT, "format_version": 1,
        "dependencies": [{
            "package": "example-pkg-a", "version": "1.0.0", "raw_license": "BUSL-1.1",
            "spdx_id": "BUSL-1.1", "confidence": "license_expression",
            "evidence": {"file": "package.json", "locator": "dependencies.example-pkg-a",
                         "line": 3},
        }],
        "pending_confirmation": [],
    })
    code, out, err = run([
        "assess", "--inventory", str(out_dir / "inventory.json"), "--scenario", "saas",
        "--network-interaction", "yes", "--outbound-license", "Elastic-2.0",
        "--scenario-note", "SaaS", "--out-dir", str(out_dir),
    ])
    assert code == EXIT_OK, out + err
    code, out, err = run(["report", "--out-dir", str(out_dir)], capsys=None)
    assert code == EXIT_OK, out + err


# ---------------------------------------------------------------------------
# 入仓示例报告：可逐字节复现
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("spec", EXAMPLE_RUNS, ids=[item["name"] for item in EXAMPLE_RUNS])
def test_example_reports_are_reproducible(tmp_path, spec):
    produced = _run_example(tmp_path, spec)
    for fmt, path in sorted(produced.items()):
        frozen = os.path.join(EXAMPLES_DIR, spec["name"] + "." + fmt)
        assert os.path.isfile(frozen), frozen
        assert open(path, "rb").read() == open(frozen, "rb").read(), (
            "入仓示例报告与重跑结果不一致：{0}".format(frozen)
        )


def test_example_reports_avoid_real_package_names():
    for name in sorted(os.listdir(EXAMPLES_DIR)):
        text = read_text(os.path.join(EXAMPLES_DIR, name))
        for real in ("pandas", "psycopg2", "PyMySQL", "PyQt5"):
            assert real not in text, "{0} 出现真实包名 {1}".format(name, real)


def test_example_project_uses_all_six_manifest_forms():
    names = {os.path.basename(path) for path in _example_manifests()}
    assert names == {"package.json", "package-lock.json", "requirements.txt",
                     "pyproject.toml", "go.mod", "pom.xml"}
    for path in _example_manifests():
        assert os.path.isfile(path), path


# ---------------------------------------------------------------------------
# AST 三条守门（plan/06 D13 / K23）
# ---------------------------------------------------------------------------


def _module_paths():
    return [os.path.join(REPORT_DIR, name) for name in REPORT_MODULES]


def _parse_all():
    return [(path, ast.parse(read_text(path))) for path in _module_paths()]


def _imported_modules(tree):
    names = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            prefix = "." * (node.level or 0)
            names.append(prefix + (node.module or ""))
    return names


def test_report_layer_does_not_import_judgement_modules():
    banned = ("licaudit.inventory", "licaudit.assess")
    for path, tree in _parse_all():
        for name in _imported_modules(tree):
            assert not name.startswith(banned), "{0} 引入了判定模块 {1}".format(path, name)
            assert name.lstrip(".") not in ("inventory", "assess"), (
                "{0} 相对引入了判定模块 {1}".format(path, name)
            )


def _is_constant_str(node):
    return isinstance(node, ast.Constant) and isinstance(node.value, str)


def test_report_layer_has_no_arithmetic_or_concatenation_binop():
    """字符串拼接豁免仅限两侧都是常量 / f-string；其余 BinOp 一律红。"""
    for path, tree in _parse_all():
        for node in ast.walk(tree):
            if not isinstance(node, ast.BinOp):
                continue
            if not isinstance(node.op, ast.Add):
                raise AssertionError("{0} 出现算术运算 {1}".format(path, type(node.op).__name__))
            allowed = (_is_constant_str(node.left) or isinstance(node.left, ast.JoinedStr),
                       _is_constant_str(node.right) or isinstance(node.right, ast.JoinedStr))
            assert all(allowed), "{0} 出现非常量字符串拼接".format(path)


def _string_literals(tree):
    found = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            found.add(node.value)
    return found


def test_report_layer_has_no_inline_license_or_level_table():
    """不得内联「许可证 ID → 档位/处置」判定表，也不得写档位名 / 处置级别名字面量。"""
    with io.open(os.path.join(SPDX_DIR, "licenses.json"), encoding="utf-8") as stream:
        license_ids = {item["licenseId"] for item in json.load(stream)["licenses"]}
    banned = set(contract.TIERS) | set(contract.ACTION_LEVELS)
    for path, tree in _parse_all():
        literals = _string_literals(tree)
        assert not (literals & license_ids), "{0} 内联了 SPDX ID".format(path)
        assert not (literals & banned), "{0} 内联了档位/处置级别名".format(path)


def test_report_layer_imports_contract_for_presentation_labels():
    """展示用中文标签也从契约取，不在渲染层写第二份枚举。"""
    assert set(contract.TIER_LABELS) == set(contract.TIERS)
    assert set(contract.ACTION_LEVEL_LABELS) == set(contract.ACTION_LEVELS)
    text = read_text(os.path.join(REPORT_DIR, "sections.py"))
    assert "contract.TIER_LABELS" in text
    assert "contract.ACTION_LEVEL_LABELS" in text


def test_report_modules_are_pure_python_without_io():
    """渲染层不读盘、不读时钟：``sections.py`` / 两个渲染器都不出现 IO 调用。"""
    for path, tree in _parse_all():
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                assert name not in ("open", "read_text", "system", "now", "time"), (
                    "{0} 出现 IO/时钟调用 {1}".format(path, name)
                )


def test_shutil_import_is_not_needed_in_report_layer():
    """占位守卫：报告层不得引入文件系统工具（渲染只吃结构化数据）。"""
    for path, _tree in _parse_all():
        text = read_text(path)
        assert "import shutil" not in text
        assert "import os" not in text
