# -*- coding: utf-8 -*-
"""受限 TOML 子集解析器（Python 3.8 无 ``tomllib``，且运行时零第三方依赖）。

只支持本项目需要的形态（plan/02 §5.1）：

- 表头 ``[a.b]``、空行、``#`` 注释
- 键值：``key = "string"``、``'string'``、``\"\"\"多行\"\"\"``、布尔、整数、浮点
- 数组（可跨行、尾部逗号）、内联表 ``{ text = "MIT" }``
- 点号键 ``project.name = "x"``

超出子集 → 抛 :class:`TomlUnsupported`；调用方记 ``toml_unsupported`` 注记并把该文件判为不可用，
**不静默跳过**（决策 D14）。
"""

import re

__all__ = ["TomlError", "TomlUnsupported", "parse"]

_BARE_KEY = re.compile(r"^[A-Za-z0-9_-]+$")
_TABLE_HEADER = re.compile(r"^\[([^\[\]]+)\]$")
_ARRAY_HEADER = re.compile(r"^\[\[([^\[\]]+)\]\]$")


class TomlError(ValueError):
    """语法错误。"""


class TomlUnsupported(TomlError):
    """落在受限子集之外。"""


class _Reader(object):
    def __init__(self, text, line_number):
        self.text = text
        self.pos = 0
        self.line = line_number

    def peek(self):
        if self.pos >= len(self.text):
            return ""
        return self.text[self.pos]

    def skip_ws(self):
        while self.pos < len(self.text) and self.text[self.pos] in " \t":
            self.pos += 1

    def parse_value(self):
        self.skip_ws()
        char = self.peek()
        if char == "":
            raise TomlError("第 {0} 行：缺少值".format(self.line))
        if char == '"' or char == "'":
            return self.parse_string()
        if char == "[":
            return self.parse_array()
        if char == "{":
            return self.parse_inline_table()
        return self.parse_bare()

    def parse_string(self):
        quote = self.peek()
        triple = quote * 3
        if self.text.startswith(triple, self.pos):
            self.pos += 3
            end = self.text.find(triple, self.pos)
            if end < 0:
                raise TomlError("第 {0} 行：多行字符串未闭合".format(self.line))
            raw = self.text[self.pos:end]
            self.pos = end + 3
            if raw.startswith("\n"):
                raw = raw[1:]
            return _unescape(raw, self.line, multiline=True)
        self.pos += 1
        chunks = []
        while True:
            if self.pos >= len(self.text):
                raise TomlError("第 {0} 行：字符串未闭合".format(self.line))
            char = self.text[self.pos]
            if char == "\\" and quote == '"':
                chunks.append(self.text[self.pos:self.pos + 2])
                self.pos += 2
                continue
            if char == quote:
                self.pos += 1
                break
            chunks.append(char)
            self.pos += 1
        raw = "".join(chunks)
        if quote == "'":
            return raw
        return _unescape(raw, self.line)

    def parse_array(self):
        self.pos += 1
        items = []
        while True:
            self.skip_ws()
            while self.peek() in ("\n", "\r"):
                self.pos += 1
                self.line += 1
                self.skip_ws()
                if self.peek() == "#":
                    while self.pos < len(self.text) and self.text[self.pos] != "\n":
                        self.pos += 1
            if self.peek() == "]":
                self.pos += 1
                return items
            if self.peek() == "":
                raise TomlError("第 {0} 行：数组未闭合".format(self.line))
            items.append(self.parse_value())
            self.skip_ws()
            while self.peek() in ("\n", "\r"):
                self.pos += 1
                self.line += 1
                self.skip_ws()
                if self.peek() == "#":
                    while self.pos < len(self.text) and self.text[self.pos] != "\n":
                        self.pos += 1
                    self.skip_ws()
            if self.peek() == ",":
                self.pos += 1
                continue
            if self.peek() == "]":
                self.pos += 1
                return items
            raise TomlUnsupported(
                "第 {0} 行：数组元素后不是逗号或右括号".format(self.line)
            )

    def parse_inline_table(self):
        self.pos += 1
        table = {}
        self.skip_ws()
        if self.peek() == "}":
            self.pos += 1
            return table
        while True:
            self.skip_ws()
            key = self.parse_key()
            self.skip_ws()
            if self.peek() != "=":
                raise TomlError("第 {0} 行：内联表缺少 =".format(self.line))
            self.pos += 1
            table[key] = self.parse_value()
            self.skip_ws()
            if self.peek() == ",":
                self.pos += 1
                continue
            if self.peek() == "}":
                self.pos += 1
                return table
            raise TomlUnsupported("第 {0} 行：内联表形态超出受限子集".format(self.line))

    def parse_key(self):
        self.skip_ws()
        char = self.peek()
        if char in ('"', "'"):
            return self.parse_string()
        start = self.pos
        while self.pos < len(self.text) and (
            self.text[self.pos].isalnum() or self.text[self.pos] in "_-."
        ):
            self.pos += 1
        key = self.text[start:self.pos]
        if not key or not _BARE_KEY.match(key.replace(".", "")):
            raise TomlUnsupported("第 {0} 行：键名形态超出受限子集".format(self.line))
        return key

    def parse_bare(self):
        start = self.pos
        while self.pos < len(self.text) and self.text[self.pos] not in ",]}\n#":
            self.pos += 1
        raw = self.text[start:self.pos].strip()
        if raw in ("true", "false"):
            return raw == "true"
        if re.match(r"^[+-]?\d+$", raw):
            return int(raw)
        if re.match(r"^[+-]?\d+\.\d+$", raw):
            return float(raw)
        raise TomlUnsupported("第 {0} 行：裸值 {1!r} 超出受限子集".format(self.line, raw))


def _unescape(raw, line, multiline=False):
    result = []
    index = 0
    table = {"n": "\n", "t": "\t", "r": "\r", '"': '"', "\\": "\\", "b": "\b", "f": "\f"}
    while index < len(raw):
        char = raw[index]
        if char != "\\":
            result.append(char)
            index += 1
            continue
        if index + 1 >= len(raw):
            raise TomlError("第 {0} 行：非法转义".format(line))
        escape = raw[index + 1]
        if escape in table:
            result.append(table[escape])
            index += 2
            continue
        if escape == "u" and index + 5 < len(raw) + 1:
            try:
                result.append(chr(int(raw[index + 2:index + 6], 16)))
            except ValueError:
                raise TomlError("第 {0} 行：非法 \\u 转义".format(line))
            index += 6
            continue
        if multiline and escape in ("\n", " "):
            # 行尾反斜杠：续行，吞掉换行与后续空白
            index += 2
            while index < len(raw) and raw[index] in " \t\r\n":
                index += 1
            continue
        raise TomlError("第 {0} 行：不支持的转义 \\{1}".format(line, escape))
    return "".join(result)


def _split_key(key):
    """点号键 → 路径（不做引号内点号拆分）。"""
    return key.split(".")


def _assign(root, path, value):
    node = root
    for part in path[:-1]:
        existing = node.get(part)
        if existing is None:
            existing = {}
            node[part] = existing
        elif not isinstance(existing, dict):
            raise TomlError("键 {0} 既不是表也不是值".format(part))
        node = existing
    node[path[-1]] = value


def parse(text):
    """解析 TOML 文本 → 嵌套 dict。"""
    root = {}
    current = root
    lines = text.splitlines()
    index = 0
    while index < len(lines):
        raw_line = lines[index]
        stripped = raw_line.strip()
        index += 1
        if not stripped or stripped.startswith("#"):
            continue

        header = _ARRAY_HEADER.match(stripped)
        if header:
            raise TomlUnsupported(
                "第 {0} 行：数组表 [[...]] 超出受限子集".format(index)
            )
        header = _TABLE_HEADER.match(stripped)
        if header:
            path = _split_key(header.group(1).strip())
            node = root
            for part in path:
                existing = node.get(part)
                if existing is None:
                    existing = {}
                    node[part] = existing
                if not isinstance(existing, dict):
                    raise TomlError("表 {0} 与已有值冲突".format(header.group(1)))
                node = existing
            current = node
            continue

        # 累积多行值：括号/引号未闭合时把后续行拼进来
        buffer = raw_line
        while _needs_more(buffer):
            if index >= len(lines):
                raise TomlError("第 {0} 行：值未闭合".format(index))
            buffer += "\n" + lines[index]
            index += 1

        reader = _Reader(buffer, index - buffer.count("\n"))
        key = reader.parse_key()
        reader.skip_ws()
        if reader.peek() != "=":
            raise TomlUnsupported("第 {0} 行：不是键值对".format(index))
        reader.pos += 1
        value = reader.parse_value()
        reader.skip_ws()
        if reader.peek() not in ("", "#"):
            raise TomlUnsupported("第 {0} 行：值后有未识别内容".format(index))
        _assign(current, _split_key(key), value)
    return root


def _needs_more(buffer):
    """粗略判断值是否跨行：括号/引号未配平，或行尾是逗号/等号。"""
    depth_square = 0
    depth_curly = 0
    in_single = False
    in_double = False
    triple_single = False
    triple_double = False
    index = 0
    while index < len(buffer):
        char = buffer[index]
        if triple_double:
            if buffer.startswith('"""', index):
                triple_double = False
                index += 3
                continue
            index += 1
            continue
        if triple_single:
            if buffer.startswith("'''", index):
                triple_single = False
                index += 3
                continue
            index += 1
            continue
        if in_double:
            if char == "\\":
                index += 2
                continue
            if char == '"':
                in_double = False
            index += 1
            continue
        if in_single:
            if char == "'":
                in_single = False
            index += 1
            continue
        if char == "#":
            newline = buffer.find("\n", index)
            if newline < 0:
                break
            index = newline + 1
            continue
        if buffer.startswith('"""', index):
            triple_double = True
            index += 3
            continue
        if buffer.startswith("'''", index):
            triple_single = True
            index += 3
            continue
        if char == '"':
            in_double = True
        elif char == "'":
            in_single = True
        elif char == "[":
            depth_square += 1
        elif char == "]":
            depth_square -= 1
        elif char == "{":
            depth_curly += 1
        elif char == "}":
            depth_curly -= 1
        index += 1
    if triple_double or triple_single or in_double or in_single:
        return True
    if depth_square > 0 or depth_curly > 0:
        return True
    return buffer.rstrip().endswith((",", "="))
