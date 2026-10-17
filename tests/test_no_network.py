# -*- coding: utf-8 -*-
"""零网络守门（K25）。

「纯本地、零上传」是声明，必须能被机器证明：
扫描 ``src/licaudit`` 全部模块的 import（含函数体内），禁止网络相关模块。
用 AST 而不是子串——docstring 里提到 ``socket`` 不该误红。
"""

import ast
import os

import pytest

from licaudit import contract  # noqa: F401  (确保包可导入)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC_ROOT = os.path.join(REPO_ROOT, "src", "licaudit")

FORBIDDEN_MODULES = (
    "socket",
    "ssl",
    "http",
    "urllib",
    "urllib2",
    "urllib3",
    "requests",
    "httpx",
    "aiohttp",
    "ftplib",
    "smtplib",
    "telnetlib",
    "xmlrpc",
    "asyncio",
)


def iter_python_files(root):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if d != "__pycache__")
        for name in sorted(filenames):
            if name.endswith(".py"):
                yield os.path.join(dirpath, name)


def collect_imports(path):
    with open(path, "rb") as stream:
        source = stream.read()
    tree = ast.parse(source, filename=path)
    modules = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.append(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                modules.append(node.module)
            elif node.module:
                modules.append(node.module)
    return modules


def test_source_tree_is_not_empty():
    files = list(iter_python_files(SRC_ROOT))
    assert len(files) >= 10, "扫描面异常：只找到 {0} 个源文件".format(len(files))


@pytest.mark.parametrize("path", list(iter_python_files(SRC_ROOT)), ids=lambda p: os.path.basename(p))
def test_no_network_imports(path):
    for module in collect_imports(path):
        root = module.split(".")[0]
        assert root not in FORBIDDEN_MODULES, (
            "{0} 引入了网络模块 {1}；本项目承诺纯本地零网络".format(
                os.path.relpath(path, REPO_ROOT), module
            )
        )


def test_forbidden_module_list_is_not_empty():
    """阴性对照：词表为空时上面的门会永远绿。"""
    assert FORBIDDEN_MODULES


def test_guard_would_catch_a_violation(tmp_path):
    """阳性对照：往临时文件里写 import socket，守卫必须能识别。"""
    sample = tmp_path / "bad_module.py"
    sample.write_text("import socket\n", encoding="utf-8")
    modules = collect_imports(str(sample))
    assert "socket" in modules
    assert any(m.split(".")[0] in FORBIDDEN_MODULES for m in modules)


def test_guard_ignores_mentions_in_docstrings(tmp_path):
    """阴性对照：docstring 提到 socket 不算违规（AST 而非子串）。"""
    sample = tmp_path / "doc_only.py"
    sample.write_text('"""这里只是说明我们不用 socket。"""\n', encoding="utf-8")
    assert collect_imports(str(sample)) == []
