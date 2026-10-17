# -*- coding: utf-8 -*-
"""退出码契约与 CLI 语义。

这些断言把 ``SKILL.md`` 的退出码表锁进行为：改任何一处语义都会红。
"""

import io

import pytest

from _helpers import make_ruleset_dir, write_json

from licaudit import cli
from licaudit.exit_codes import EXIT_FINDINGS, EXIT_OK, EXIT_RULESET, EXIT_USAGE
from licaudit.ruleset import loader


def run(argv, capsys=None):
    code = cli.main(argv)
    out = err = ""
    if capsys is not None:
        captured = capsys.readouterr()
        out, err = captured.out, captured.err
    return code, out, err


def test_exit_codes_are_exactly_four():
    from licaudit import exit_codes

    assert {EXIT_OK, EXIT_FINDINGS, EXIT_USAGE, EXIT_RULESET} == {0, 1, 2, 3}
    assert set(exit_codes.EXIT_CODES) == {0, 1, 2, 3}


def test_no_arguments_is_usage_error(capsys):
    code, out, err = run([], capsys)
    assert code == EXIT_USAGE
    assert "子命令" in err


def test_unknown_command_is_usage_error(capsys):
    with pytest.raises(SystemExit) as excinfo:
        run(["definitely-not-a-command"], capsys)
    assert excinfo.value.code == EXIT_USAGE


def test_version_exits_zero(capsys):
    with pytest.raises(SystemExit) as excinfo:
        run(["--version"], capsys)
    assert excinfo.value.code == EXIT_OK
    assert "licaudit" in capsys.readouterr().out


def test_selftest_core_passes_without_ruleset(capsys):
    code, out, err = run(["selftest", "--core"], capsys)
    assert code == EXIT_OK
    assert "FAIL" not in out


def test_selftest_full_fails_when_ruleset_dir_is_empty(tmp_path, capsys):
    """规则包不可用时完整自检必须失败——否则自检是假的。

    M1 起仓库自带规则包，所以这里显式指向空目录制造「无规则包」。
    """
    empty = tmp_path / "empty"
    empty.mkdir()
    code, out, err = run(["--rules-dir", str(empty), "selftest"], capsys)
    assert code == EXIT_FINDINGS
    assert "ruleset_loadable" in out
    assert "FAIL" in out


def test_selftest_full_passes_with_ruleset(tmp_path, capsys, monkeypatch):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    code, out, err = run(["--rules-dir", root, "selftest"], capsys)
    assert code == EXIT_OK, out + err


def test_status_without_ruleset_is_ruleset_error(tmp_path, capsys, monkeypatch):
    """缺规则包必须是 exit 3，不能是「零依赖无风险」的 exit 0。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(str(tmp_path))
    monkeypatch.delenv(loader.ENV_RULES_DIR, raising=False)
    code, out, err = run(["--rules-dir", str(empty), "status"], capsys)
    assert code == EXIT_RULESET
    assert "规则包" in err


def test_status_with_ruleset_writes_artifact(tmp_path, capsys):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    out_dir = tmp_path / "out"
    code, out, err = run(
        ["--rules-dir", root, "status", "--out-dir", str(out_dir)], capsys
    )
    assert code == EXIT_OK, out + err
    artifact = out_dir / "status.json"
    assert artifact.is_file()
    text = io.open(str(artifact), encoding="utf-8").read()
    assert '"format": "licaudit-status"' in text
    assert text.endswith("\n")


@pytest.mark.parametrize("command", ["scan", "assess", "report", "bench", "verify-data"])
def test_unimplemented_commands_need_ruleset_first(tmp_path, command, capsys, monkeypatch):
    """所有命令都必须先过规则包硬门：缺规则包 → exit 3，而不是 exit 0 空承诺。"""
    empty = tmp_path / "empty"
    empty.mkdir()
    monkeypatch.chdir(str(tmp_path))
    monkeypatch.delenv(loader.ENV_RULES_DIR, raising=False)
    argv = ["--rules-dir", str(empty), command]
    if command == "scan":
        argv.append("package.json")
    elif command == "assess":
        argv += ["--inventory", "inv.json", "--scenario", "saas", "--outbound-license", "pending"]
    elif command == "report":
        argv += ["--out-dir", str(tmp_path / "out")]
    code, out, err = run(argv, capsys)
    assert code == EXIT_RULESET, (command, out, err)


def test_assess_full_mode_requires_scenario_and_outbound(tmp_path, capsys):
    """M3 全量模式：缺 ``--scenario`` / ``--outbound-license`` → exit 2，且不写产物。"""
    root = make_ruleset_dir(str(tmp_path / "rs"))
    inventory = tmp_path / "inv.json"
    write_json(str(inventory), {
        "format": "licaudit-inventory",
        "format_version": 1,
        "dependencies": [],
        "pending_confirmation": [],
    })
    out_dir = tmp_path / "out"

    code, out, err = run(
        ["--rules-dir", root, "assess", "--inventory", str(inventory),
         "--outbound-license", "pending", "--out-dir", str(out_dir)],
        capsys,
    )
    assert code == EXIT_USAGE
    assert "场景" in err
    assert not (out_dir / "scenario.json").exists()

    code, out, err = run(
        ["--rules-dir", root, "assess", "--inventory", str(inventory),
         "--scenario", "saas", "--out-dir", str(out_dir)],
        capsys,
    )
    assert code == EXIT_USAGE
    assert "outbound" in err
    assert not (out_dir / "scenario.json").exists()


def test_assess_full_mode_rejects_unknown_outbound_id(tmp_path, capsys):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    inventory = tmp_path / "inv.json"
    write_json(str(inventory), {
        "format": "licaudit-inventory",
        "format_version": 1,
        "dependencies": [],
        "pending_confirmation": [],
    })
    code, out, err = run(
        ["--rules-dir", root, "assess", "--inventory", str(inventory),
         "--scenario", "saas", "--outbound-license", "Not-A-Real-License",
         "--out-dir", str(tmp_path / "out")],
        capsys,
    )
    assert code == EXIT_USAGE
    assert "outbound" in err


def test_scan_missing_manifest_is_usage_error(tmp_path, capsys):
    """M1 起 scan 已实现：文件不存在是输入错误（exit 2），不是「未实现」。"""
    root = make_ruleset_dir(str(tmp_path / "rs"))
    out_dir = tmp_path / "out"
    code, out, err = run(
        ["--rules-dir", root, "scan", "package.json", "--out-dir", str(out_dir)], capsys
    )
    assert code == EXIT_USAGE
    assert "不可读" in err
    assert not (out_dir / "inventory.json").exists()


def test_assess_rejects_unknown_scenario(tmp_path, capsys):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    with pytest.raises(SystemExit) as excinfo:
        run(
            [
                "--rules-dir",
                root,
                "assess",
                "--inventory",
                "inv.json",
                "--scenario",
                "not-a-scenario",
                "--outbound-license",
                "pending",
            ],
            capsys,
        )
    assert excinfo.value.code == EXIT_USAGE


def test_report_rejects_unknown_format(tmp_path, capsys):
    root = make_ruleset_dir(str(tmp_path / "rs"))
    with pytest.raises(SystemExit) as excinfo:
        run(["--rules-dir", root, "report", "--format", "pdf"], capsys)
    assert excinfo.value.code == EXIT_USAGE


def test_ruleset_hash_mismatch_is_ruleset_error(tmp_path, capsys):
    root = make_ruleset_dir(str(tmp_path / "rs"), bad_hash=True)
    code, out, err = run(["--rules-dir", root, "status"], capsys)
    assert code == EXIT_RULESET
    assert "哈希" in err


def test_ruleset_missing_declared_file_is_ruleset_error(tmp_path, capsys):
    """manifest 登记了文件但文件不在 → exit 3（不是「少了就跳过」）。"""
    import os

    root = make_ruleset_dir(str(tmp_path / "rs"))
    os.unlink(os.path.join(root, "tiers.json"))
    code, out, err = run(["--rules-dir", root, "status"], capsys)
    assert code == EXIT_RULESET
    assert "不存在" in err
