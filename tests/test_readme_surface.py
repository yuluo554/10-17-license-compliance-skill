# -*- coding: utf-8 -*-
"""README 指令面可执行性。

子串断言证明不了「用户照抄能跑」。这里做三件事：
1. 抽取 README 中的 ``licaudit ...`` 命令，逐条断言子命令已注册、旗标存在；
2. 断言行内提到的文件路径真实存在；
3. 断言 README 的 extras 与 pyproject 双向一致。
"""

import io
import os
import re

import pytest

from licaudit.cli import build_parser

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
README_PATH = os.path.join(REPO_ROOT, "README.md")
SKILL_PATH = os.path.join(REPO_ROOT, "SKILL.md")
PYPROJECT_PATH = os.path.join(REPO_ROOT, "pyproject.toml")


def read(path):
    with io.open(path, encoding="utf-8") as stream:
        return stream.read()


def _command_lines(text):
    """抽取代码块里以 licaudit 开头的命令行（忽略注释与续行）。"""
    lines = []
    for raw in text.split("\n"):
        line = raw.strip()
        if not line.startswith("licaudit "):
            continue
        if line.startswith("#"):
            continue
        # 去掉行尾反斜杠续行标记
        line = line.rstrip("\\").strip()
        lines.append(line)
    return lines


def _parser_commands():
    parser = build_parser()
    for action in parser._actions:
        if action.__class__.__name__ == "_SubParsersAction":
            return dict(action.choices)
    return {}


def test_readme_has_commands():
    assert _command_lines(read(README_PATH)), "README 没有可执行命令示例"


@pytest.mark.parametrize("line", _command_lines(read(README_PATH)))
def test_readme_command_subcommand_exists(line):
    parts = line.split()
    commands = _parser_commands()
    # 允许全局旗标在子命令前
    index = 1
    while index < len(parts) and parts[index].startswith("--"):
        if parts[index] in ("--rules-dir",):
            index += 2
        else:
            index += 1
    assert index < len(parts), "命令缺少子命令: {0}".format(line)
    subcommand = parts[index]
    assert subcommand in commands, "README 命令的子命令未注册: {0}".format(subcommand)


@pytest.mark.parametrize("line", _command_lines(read(README_PATH)))
def test_readme_flags_exist_on_subcommand(line):
    parts = line.split()
    commands = _parser_commands()
    index = 1
    while index < len(parts) and parts[index].startswith("--"):
        if parts[index] in ("--rules-dir",):
            index += 2
        else:
            index += 1
    subcommand = parts[index]
    parser = commands[subcommand]
    known = set()
    for action in parser._actions:
        known.update(action.option_strings)

    for token in parts[index + 1 :]:
        if not token.startswith("-"):
            continue
        flag = token.split("=")[0]
        assert flag in known, "README 使用了未定义的旗标 {0}（子命令 {1}）".format(
            flag, subcommand
        )


def test_readme_referenced_files_exist():
    """README 里出现的仓库相对路径必须真实存在。"""
    text = read(README_PATH)
    candidates = set(re.findall(r"`([A-Za-z0-9_./-]+/[A-Za-z0-9_.-]+)`", text))
    missing = []
    for candidate in sorted(candidates):
        if candidate.startswith(("http://", "https://")):
            continue
        if "<" in candidate or "|" in candidate:
            continue
        path = os.path.join(REPO_ROOT, candidate)
        if not os.path.exists(path):
            missing.append(candidate)
    assert not missing, "README 引用了不存在的路径: {0}".format(", ".join(missing))


def test_readme_extras_match_pyproject():
    readme = read(README_PATH)
    pyproject = read(PYPROJECT_PATH)

    declared = set(re.findall(r"^([A-Za-z0-9_-]+)\s*=\s*\[", pyproject, re.MULTILINE))
    # 只取 optional-dependencies 段里的键（简单解析：位于 [project.optional-dependencies] 之后）
    section = pyproject.split("[project.optional-dependencies]", 1)
    extras = set()
    if len(section) == 2:
        body = section[1].split("\n[", 1)[0]
        extras = set(re.findall(r"^([A-Za-z0-9_-]+)\s*=\s*\[", body, re.MULTILINE))

    used = set(re.findall(r"pip install -e \"\.\[([^\]]+)\]\"" , readme))
    used_names = set()
    for group in used:
        for name in group.split(","):
            used_names.add(name.strip())

    assert used_names, "README 没有给出 pip install -e \".[...]\" 安装命令"
    assert used_names <= extras, "README 使用了未声明的 extra: {0}".format(
        used_names - extras
    )
    assert declared, "pyproject 缺少解析结果（探针可能切坏了文本）"


def test_readme_documents_exit_codes():
    text = read(README_PATH)
    for code in ("0", "1", "2", "3"):
        assert code in text
    assert "3" in text and "规则包" in text


def test_readme_documents_disclaimer():
    from licaudit import contract

    assert contract.DISCLAIMER in read(README_PATH)


def test_skill_md_commands_executable():
    """SKILL.md 中的命令同样要能对上 CLI 定义。"""
    commands = _parser_commands()
    for line in _command_lines(read(SKILL_PATH)):
        parts = line.split()
        index = 1
        while index < len(parts) and parts[index].startswith("--"):
            if parts[index] in ("--rules-dir",):
                index += 2
            else:
                index += 1
        if index >= len(parts):
            continue
        subcommand = parts[index]
        if subcommand.startswith("--"):
            continue
        assert subcommand in commands, "SKILL.md 引用了未注册子命令: {0}".format(subcommand)


def test_package_has_main_module():
    """``python -m licauit`` 依赖 ``__main__.py``；缺了它 README 指令会直接崩。"""
    assert os.path.isfile(
        os.path.join(REPO_ROOT, "src", "licaudit", "__main__.py")
    )


def test_launcher_exists():
    assert os.path.isfile(
        os.path.join(REPO_ROOT, "scripts", "launcher_licaudit.py")
    )


def test_license_file_exists():
    """README 声明 MIT，仓库必须有 LICENSE 文件。"""
    assert os.path.isfile(os.path.join(REPO_ROOT, "LICENSE"))
    assert "MIT License" in read(os.path.join(REPO_ROOT, "LICENSE"))
