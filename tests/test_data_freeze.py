# -*- coding: utf-8 -*-
"""冻结数据与生成器守门（K27 / K28 / K26）。

这些测试不验证「代码能跑」，而验证「冻结的东西真的是冻结的」：
- 生成器 ``--check`` 位级一致；
- 合成数据只出现白名单包名（坑位用例例外）；
- 真值只存输入与期望；
- 规则包与 SPDX 快照版本成对。
"""

import io
import json
import os
import re
import subprocess
import sys

import pytest

from _helpers import REPO_ROOT

DATA_DIR = os.path.join(REPO_ROOT, "data")
SYNTHETIC_DIR = os.path.join(DATA_DIR, "synthetic")
TRUTH_PATH = os.path.join(DATA_DIR, "truth", "truth.json")
RULESET_DIR = os.path.join(REPO_ROOT, "references", "ruleset")
SPDX_DIR = os.path.join(REPO_ROOT, "references", "spdx")
TOOLS = os.path.join(REPO_ROOT, "tools")

TRAP_CASE = "known-traps"
PACKAGE_PATTERN = re.compile(r"^example-pkg-[a-z]$")


def read_json(path):
    with io.open(path, encoding="utf-8") as stream:
        return json.load(stream)


def run_tool(name, *args):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return subprocess.run(
        [sys.executable, os.path.join(TOOLS, name)] + list(args),
        cwd=REPO_ROOT,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=300,
    )


# ---------------------------------------------------------------------------
# 生成器 --check
# ---------------------------------------------------------------------------


def test_gen_ruleset_check_passes():
    result = run_tool("gen_ruleset.py", "--check")
    text = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
    assert result.returncode == 0, text
    assert "逐字节一致" in text


def test_gen_synthetic_check_passes():
    result = run_tool("gen_synthetic.py", "--check")
    text = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
    assert result.returncode == 0, text
    assert "逐字节一致" in text


def test_fetch_spdx_check_passes_offline():
    result = run_tool("fetch_spdx.py", "--check", "--out", "references/spdx")
    text = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
    assert result.returncode == 0, text
    assert "完整" in text


def test_gen_ruleset_check_detects_handedit(tmp_path):
    """阳性对照：手改生成物后 ``--check`` 必须变红。"""
    import shutil

    target = tmp_path / "ruleset"
    shutil.copytree(RULESET_DIR, str(target))
    tiers = target / "tiers.json"
    original = tiers.read_text(encoding="utf-8")
    tiers.write_text(original.replace('"tier": "permissive"', '"tier": "source-available"', 1),
                     encoding="utf-8")

    result = run_tool("gen_ruleset.py", "--check", "--out", str(target))
    text = result.stdout.decode("utf-8", "replace")
    assert result.returncode == 1, text
    assert "[FAIL]" in text


def test_anchor_locatability_gate_is_falsifiable(tmp_path):
    """把一条 curated 的 quote 改成原文里没有的句子 → 生成器必须拒绝该条。

    这条测试直接验 `check_anchor`，防止「锚点门」退化成恒真。
    """
    import shutil
    import sys

    sys.path.insert(0, TOOLS)
    import gen_ruleset  # noqa: E402

    texts = gen_ruleset.TextCache(SPDX_DIR)
    good = {
        "source": "spdx-license-text",
        "ref": "texts/MIT.json#licenseText",
        "quote": "The above copyright notice and this permission notice shall be included",
    }
    assert gen_ruleset.check_anchor(good, texts)[0] is True

    bad = dict(good, quote="这是一句 MIT 原文里不存在的话")
    ok, reason = gen_ruleset.check_anchor(bad, texts)
    assert ok is False
    assert reason == "anchor_not_locatable"

    missing_quote = {"source": "spdx-license-text", "ref": "texts/MIT.json#licenseText"}
    assert gen_ruleset.check_anchor(missing_quote, texts) == (False, "anchor_quote_missing")

    missing_file = dict(good, ref="texts/NoSuchLicense.json#licenseText")
    assert gen_ruleset.check_anchor(missing_file, texts) == (False, "anchor_not_locatable")


def test_generator_marks_unlocatable_rule_as_unverified(tmp_path):
    """端到端：curated 里某条锚点坏了 → 生成的规则包该条 verified=false。

    用临时 curated 副本跑一遍生成，不碰仓库冻结产物。
    """
    import shutil
    import sys

    sys.path.insert(0, TOOLS)
    import gen_ruleset  # noqa: E402

    curated = tmp_path / "curated"
    shutil.copytree(os.path.join(REPO_ROOT, "references", "curated"), str(curated))
    tiers_path = curated / "tiers.json"
    payload = read_json(str(tiers_path))
    payload["entries"][0]["anchor"]["quote"] = "原文里不存在的一句话"
    tiers_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )

    original = gen_ruleset.CURATED_DIR
    gen_ruleset.CURATED_DIR = str(curated)
    try:
        documents, _manifest, problems = gen_ruleset.generate(str(tmp_path / "out"))
    finally:
        gen_ruleset.CURATED_DIR = original

    license_id = payload["entries"][0]["license_id"]
    entry = next(
        item for item in documents["tiers.json"]["entries"]
        if item["license_id"] == license_id
    )
    assert entry["verified"] is False
    assert any("锚点不可定位" in problem for problem in problems)


# ---------------------------------------------------------------------------
# 合成数据白名单（K28）
# ---------------------------------------------------------------------------


def _collect_synthetic_packages():
    found = {}
    for case_id in sorted(os.listdir(SYNTHETIC_DIR)):
        case_dir = os.path.join(SYNTHETIC_DIR, case_id)
        if not os.path.isdir(case_dir):
            continue
        truth = read_json(TRUTH_PATH)
        case = next(
            (item for item in truth["cases"] if item["case_id"] == case_id), None
        )
        if case is None:
            continue
        names = set()
        for group in ("dependencies", "pending_confirmation"):
            for item in case["expect"][group]:
                names.add(item["package"])
        found[case_id] = names
    return found


def test_synthetic_packages_are_whitelisted():
    violations = []
    for case_id, names in sorted(_collect_synthetic_packages().items()):
        if case_id == TRAP_CASE:
            continue
        for name in sorted(names):
            if not (PACKAGE_PATTERN.match(name) or name.startswith("example.com/")
                    or name.startswith("com.example:")):
                violations.append("{0}: {1}".format(case_id, name))
    assert not violations, "合成数据出现非白名单包名：{0}".format(", ".join(violations))


def test_trap_case_uses_only_real_names():
    names = _collect_synthetic_packages()["known-traps"]
    assert names == {"pandas", "psycopg2", "PyMySQL", "PyQt5"}


def test_trap_case_is_absent_from_example_project():
    """坑位用例不得进入示例项目（示例项目 M5 才建，这里守反向）。"""
    example_dir = os.path.join(SYNTHETIC_DIR, "example-project")
    if not os.path.isdir(example_dir):
        pytest.skip("example-project 属于 M5")
    for dirpath, _dirnames, filenames in os.walk(example_dir):
        for filename in filenames:
            path = os.path.join(dirpath, filename)
            with io.open(path, encoding="utf-8", errors="replace") as stream:
                text = stream.read()
            for name in ("pandas", "psycopg2", "PyMySQL", "PyQt5"):
                assert name not in text


# ---------------------------------------------------------------------------
# 真值纪律（K26）
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    [TRUTH_PATH],
    ids=["truth"],
)
def test_truth_has_no_observed_fields(path):
    text = io.open(path, encoding="utf-8").read()
    assert "observed_" not in text


def test_truth_cases_declare_inputs_and_expectations():
    payload = read_json(TRUTH_PATH)
    assert payload["format"] == "licaudit-truth"
    assert payload["format_version"] == 1
    assert payload["cases"]
    for case in payload["cases"]:
        assert case["inputs"]["files"], "用例 {0} 未登记输入".format(case["case_id"])
        for group in ("dependencies", "pending_confirmation"):
            for item in case["expect"][group]:
                assert set(item) == {"package", "version", "spdx_id", "confidence", "flags"}
                assert item["confidence"] in (
                    "license_expression",
                    "trove_classifier",
                    "license_first_line",
                    "truncated_fallback",
                )


def test_trap_expectations_carry_checked_on():
    payload = read_json(TRUTH_PATH)
    trap = next(case for case in payload["cases"] if case["case_id"] == TRAP_CASE)
    assert trap["expect"]["checked_on"]


def test_truth_input_files_exist():
    payload = read_json(TRUTH_PATH)
    for case in payload["cases"]:
        case_dir = os.path.join(SYNTHETIC_DIR, case["case_id"])
        for name in case["inputs"]["files"]:
            assert os.path.isfile(os.path.join(case_dir, name)), (
                "{0}/{1} 不存在".format(case["case_id"], name)
            )


# ---------------------------------------------------------------------------
# 规则包（K7 / K10 / 版本成对）
# ---------------------------------------------------------------------------


def test_ruleset_manifest_pairs_with_spdx_snapshot():
    manifest = read_json(os.path.join(RULESET_DIR, "manifest.json"))
    licenses = read_json(os.path.join(SPDX_DIR, "licenses.json"))
    snapshot = read_json(os.path.join(SPDX_DIR, "manifest.json"))

    assert manifest["license_list_version"] == licenses["licenseListVersion"]
    assert manifest["license_list_version"] == snapshot["license_list_version"]
    assert manifest["license_list_captured_on"] == snapshot["captured_on"]
    assert manifest["ruleset_version"]


def test_ruleset_coverage_registers_both_counts():
    """只写采样数 = 假覆盖：总数与采样数必须同时登记。"""
    manifest = read_json(os.path.join(RULESET_DIR, "manifest.json"))
    coverage = manifest["ruleset_coverage"]
    assert coverage["tiers_total_ids"] > 100
    assert 0 < coverage["tiers_sampled_ids"] <= coverage["tiers_total_ids"]
    assert "抽样" in coverage["note"]


def test_every_tier_rule_passes_anchor_gate():
    from licaudit.ruleset import load_ruleset

    ruleset = load_ruleset()
    tiers = ruleset.entries("tiers.json")
    assert len(tiers) >= 40
    for entry in tiers:
        assert entry["verified"] is True
        assert entry["checked_on"]
        assert entry["anchor"]["ref"].startswith("texts/")
        assert entry["anchor"]["quote"]
        assert entry["tier"] in (
            "permissive",
            "weak-copyleft",
            "strong-copyleft",
            "network-copyleft",
            "source-available",
        )
    assert ruleset.disabled == []


def test_tier_anchors_are_locatable_in_snapshots():
    """每条锚点的 quote 必须真的出现在对应 SPDX 全文里（不是编的节号）。"""
    from licaudit.ruleset import load_ruleset

    ruleset = load_ruleset()
    problems = []
    for entry in ruleset.entries("tiers.json"):
        reference = entry["anchor"]["ref"]
        relative = reference.split("#", 1)[0]
        path = os.path.join(SPDX_DIR, relative.replace("/", os.sep))
        if not os.path.isfile(path):
            problems.append("{0}: 全文缺失 {1}".format(entry["license_id"], relative))
            continue
        payload = read_json(path)
        text = payload.get("licenseText") or ""
        quote = " ".join(entry["anchor"]["quote"].split())
        if quote not in " ".join(text.split()):
            problems.append("{0}: quote 无法定位".format(entry["license_id"]))
    assert not problems, "; ".join(problems)


def test_obligations_match_contract_enum():
    from licaudit import contract

    document = read_json(os.path.join(RULESET_DIR, "obligations.json"))
    ids = [entry["id"] for entry in document["entries"]]
    assert ids == list(contract.OBLIGATIONS)


def test_covered_licenses_are_known_spdx_ids():
    licenses = read_json(os.path.join(SPDX_DIR, "licenses.json"))
    known = {item["licenseId"] for item in licenses["licenses"]}
    document = read_json(os.path.join(RULESET_DIR, "tiers.json"))
    unknown = [entry["license_id"] for entry in document["entries"]
               if entry["license_id"] not in known]
    assert not unknown, "规则包收录了 SPDX 清单外的 ID：{0}".format(unknown)


def test_osfsf_status_not_duplicated_in_ruleset():
    """OSI/FSF 只从 SPDX 快照取，规则包不得写第二份真相（K9 的 M1 版）。"""
    text = io.open(os.path.join(RULESET_DIR, "tiers.json"), encoding="utf-8").read()
    assert "is_osi_approved" not in text
    assert "is_fsf_libre" not in text
