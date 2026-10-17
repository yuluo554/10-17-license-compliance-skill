# -*- coding: utf-8 -*-
"""三条调用通路：控制台脚本 / 模块 / 启动器。

三者必须行为等价。这里用子进程真跑：
- 未安装也可用 ``PYTHONPATH=src python -m licaudit``；
- 启动器自己会把 ``src`` 放进 ``sys.path``。
"""

import io
import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")
LAUNCHER = os.path.join(REPO_ROOT, "scripts", "launcher_licaudit.py")


def _env():
    env = dict(os.environ)
    env["PYTHONPATH"] = SRC + (os.pathsep + env["PYTHONPATH"] if env.get("PYTHONPATH") else "")
    env["PYTHONUTF8"] = "1"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run(args, cwd=None):
    return subprocess.run(
        [sys.executable] + args,
        cwd=cwd or REPO_ROOT,
        env=_env(),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=120,
    )


def test_module_entry_point():
    result = run(["-m", "licaudit", "--version"])
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert b"licaudit" in result.stdout


def test_launcher_entry_point():
    result = run([LAUNCHER, "--version"])
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert b"licaudit" in result.stdout


def test_launcher_selftest_core():
    result = run([LAUNCHER, "selftest", "--core"])
    assert result.returncode == 0, result.stderr.decode("utf-8", "replace")
    assert b"OK" in result.stdout


def test_module_reports_chinese_without_crash():
    """模块方式在 UTF-8 环境下输出中文不应崩（编码守卫覆盖）。

    M1 起仓库自带规则包，``status`` 成功返回 0；这里关心「中文可读、无 traceback」。
    """
    result = run(["-m", "licaudit", "status"])
    text = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
    assert result.returncode == 0, text
    assert "规则包" in text
    assert "Traceback" not in text


def test_module_reports_chinese_error_without_crash():
    """缺规则包时必须输出中文错误而非 traceback。"""
    result = run(["-m", "licaudit", "--rules-dir", "does-not-exist", "status"])
    text = result.stdout.decode("utf-8", "replace") + result.stderr.decode("utf-8", "replace")
    assert result.returncode == 3
    assert "规则包" in text
    assert "Traceback" not in text


def test_module_and_launcher_agree_on_missing_ruleset():
    module = run(["-m", "licaudit", "--rules-dir", "does-not-exist", "status"])
    launcher = run([LAUNCHER, "--rules-dir", "does-not-exist", "status"])
    assert module.returncode == launcher.returncode == 3
