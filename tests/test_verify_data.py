# -*- coding: utf-8 -*-
"""``verify-data`` 与 ``bench``：读冻结真值、复算、可证伪。"""

import io
import json
import os
import shutil

import pytest

from _helpers import REPO_ROOT

from licaudit import cli
from licaudit.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_RULESET, EXIT_USAGE

DATA_DIR = os.path.join(REPO_ROOT, "data")
TRUTH = os.path.join(DATA_DIR, "truth", "truth.json")


def run(argv, capsys=None):
    code = cli.main(argv)
    out = err = ""
    if capsys is not None:
        captured = capsys.readouterr()
        out, err = captured.out, captured.err
    return code, out, err


def load_truth():
    with io.open(TRUTH, encoding="utf-8") as stream:
        return json.load(stream)


def write_truth(payload, path):
    with io.open(str(path), "w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2))
        stream.write("\n")


def test_verify_data_passes_on_frozen_truth(capsys):
    code, out, err = run(["verify-data"], capsys)
    assert code == EXIT_OK, out + err
    assert "[OK]" in out
    assert "命中" in out


def test_verify_data_reads_the_frozen_file_not_a_recomputation(tmp_path, capsys):
    """把真值改坏（不重生成数据）→ 必须变红，证明 CLI 真读了冻结件。"""
    shutil.copytree(DATA_DIR, str(tmp_path / "data"))
    truth_path = tmp_path / "data" / "truth" / "truth.json"
    payload = load_truth()
    target = payload["cases"][0]["expect"]["dependencies"][0]
    target["spdx_id"] = "Apache-2.0"
    write_truth(payload, truth_path)

    code, out, err = run(["verify-data", "--data-dir", str(tmp_path / "data")], capsys)
    assert code == EXIT_FINDINGS
    assert "[FAIL]" in out


def test_verify_data_rejects_observed_fields(tmp_path, capsys):
    shutil.copytree(DATA_DIR, str(tmp_path / "data"))
    truth_path = tmp_path / "data" / "truth" / "truth.json"
    payload = load_truth()
    payload["cases"][0]["expect"]["dependencies"][0]["observed_spdx_id"] = "MIT"
    write_truth(payload, truth_path)

    code, out, err = run(["verify-data", "--data-dir", str(tmp_path / "data")], capsys)
    assert code == EXIT_FINDINGS
    assert "observed_" in out


def test_verify_data_reports_missing_input_file(tmp_path, capsys):
    shutil.copytree(DATA_DIR, str(tmp_path / "data"))
    removed = tmp_path / "data" / "synthetic" / "npm-basic" / "package.json"
    os.unlink(str(removed))
    code, out, err = run(["verify-data", "--data-dir", str(tmp_path / "data")], capsys)
    assert code == EXIT_FINDINGS
    assert "输入文件缺失" in out


def test_verify_data_without_truth_is_usage_error(tmp_path, capsys):
    empty = tmp_path / "empty"
    empty.mkdir()
    code, out, err = run(["verify-data", "--data-dir", str(empty)], capsys)
    assert code == EXIT_USAGE
    assert "真值库" in err


def test_verify_data_requires_ruleset(tmp_path, capsys, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(str(tmp_path))
    monkeypatch.delenv("LICAUDIT_RULES_DIR", raising=False)
    code, out, err = run(["--rules-dir", str(empty), "verify-data"], capsys)
    assert code == EXIT_RULESET


def test_bench_m1_passes(capsys):
    code, out, err = run(["bench", "--only", "m1"], capsys)
    assert code == EXIT_OK, out + err
    assert "[OK] m1" in out
    assert "F1" in out


def test_bench_m2_without_profile_truth_is_usage_error(tmp_path, capsys):
    """缺画像真值时 bench m2 必须明确报输入不可用，而不是跑零条通过。"""
    empty = tmp_path / "data"
    (empty / "truth").mkdir(parents=True)
    code, out, err = run(["bench", "--only", "m2", "--data-dir", str(empty)], capsys)
    assert code == EXIT_USAGE
    assert "画像真值" in err


def test_verify_data_reports_f1_for_dod(capsys):
    """M1 DoD 要求解析 F1 ≥ 0.95；这个数必须由 CLI 实算并打印。"""
    code, out, err = run(["verify-data"], capsys)
    assert code == EXIT_OK, out + err
    assert "F1 1.0" in out


def test_bench_f1_threshold_is_enforced(tmp_path, monkeypatch, capsys):
    """把一条期望改错 → F1 掉下 0.95 且 bench 必须变红（不是只看对账文本）。"""
    import json as _json
    import shutil

    shutil.copytree(DATA_DIR, str(tmp_path / "data"))
    truth_path = tmp_path / "data" / "truth" / "truth.json"
    payload = load_truth()
    # 把 5 条已归一化记录的期望 ID 改成不存在的值（制造假阴 + 假阳）
    changed = 0
    for case in payload["cases"]:
        for item in case["expect"]["dependencies"]:
            if changed >= 5:
                break
            if item["spdx_id"]:
                item["spdx_id"] = "Apache-2.0" if item["spdx_id"] != "Apache-2.0" else "MIT"
                changed += 1
    write_truth(payload, truth_path)

    code, out, err = run(
        ["bench", "--only", "m1", "--data-dir", str(tmp_path / "data")], capsys
    )
    assert code == EXIT_FINDINGS, out + err


def test_bench_default_runs_implemented_suites(capsys):
    code, out, err = run(["bench"], capsys)
    assert code == EXIT_OK, out + err
    assert "m1" in out
    assert "m3" in out
    assert "m4" in out


def test_bench_unknown_suite_is_usage_error(capsys):
    code, out, err = run(["bench", "--only", "m9"], capsys)
    assert code == EXIT_USAGE
    assert "未知" in err


def test_bench_m5_passes_on_action_truth(capsys):
    code, out, err = run(["bench", "--only", "m5"], capsys)
    assert code == EXIT_OK, out + err
    assert "[OK] m5" in out
    assert "处置分级" in out


def test_bench_unimplemented_suite_is_usage_error(capsys):
    """``m6``（发布里程碑）没有判定套件：必须明确拒绝，而不是跑一个空套件返回通过。"""
    code, out, err = run(["bench", "--only", "m6"], capsys)
    assert code == EXIT_USAGE
    assert "尚未实现" in err


def test_bench_and_implemented_suites_agree():
    """``BENCH_SUITES`` 是全部里程碑套件，``IMPLEMENTED_SUITES`` 是其子集。"""
    from licaudit import verify

    assert set(verify.IMPLEMENTED_SUITES) <= set(verify.BENCH_SUITES)
    assert verify.IMPLEMENTED_SUITES == ("m1", "m2", "m3", "m4", "m5")


def test_bench_m3_without_scenario_truth_is_usage_error(tmp_path, capsys):
    """缺场景真值时 bench m3 必须明确报输入不可用，而不是跑零条通过。"""
    empty = tmp_path / "data"
    (empty / "truth").mkdir(parents=True)
    code, out, err = run(["bench", "--only", "m3", "--data-dir", str(empty)], capsys)
    assert code == EXIT_USAGE
    assert "场景真值" in err


def test_bench_m4_without_conflict_truth_is_usage_error(tmp_path, capsys):
    """缺冲突真值时 bench m4 必须明确报输入不可用，而不是跑零条通过。"""
    empty = tmp_path / "data"
    (empty / "truth").mkdir(parents=True)
    code, out, err = run(["bench", "--only", "m4", "--data-dir", str(empty)], capsys)
    assert code == EXIT_USAGE
    assert "冲突真值" in err


def test_bench_requires_ruleset(tmp_path, capsys, monkeypatch):
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(str(tmp_path))
    monkeypatch.delenv("LICAUDIT_RULES_DIR", raising=False)
    code, out, err = run(["--rules-dir", str(empty), "bench", "--only", "m1"], capsys)
    assert code == EXIT_RULESET
