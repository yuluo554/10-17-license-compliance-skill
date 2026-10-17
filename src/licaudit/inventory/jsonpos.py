# -*- coding: utf-8 -*-
"""带行号的 JSON 解析（stdlib ``json`` 不提供位置信息）。

只做两件事：按标准 JSON 语法解析，并记录「每个键值对的行号」。
行号从 1 开始；用于 ``evidence.line``，必须可复算。
"""

import json

__all__ = ["JsonPositionError", "parse_with_positions"]


class JsonPositionError(ValueError):
    pass


class _Scanner(object):
    def __init__(self, text):
        self.text = text
        self.pos = 0
        self.length = len(text)
        self.positions = {}
        self._line_starts = [0]
        for index, char in enumerate(text):
            if char == "\n":
                self._line_starts.append(index + 1)

    def line_of(self, offset):
        low = 0
        high = len(self._line_starts) - 1
        while low < high:
            middle = (low + high + 1) // 2
            if self._line_starts[middle] <= offset:
                low = middle
            else:
                high = middle - 1
        return low + 1

    def skip_ws(self):
        while self.pos < self.length and self.text[self.pos] in " \t\r\n":
            self.pos += 1

    def parse(self):
        self.skip_ws()
        value = self.parse_value(())
        self.skip_ws()
        if self.pos != self.length:
            raise JsonPositionError("尾部有多余内容（偏移 {0}）".format(self.pos))
        return value

    def parse_value(self, path):
        self.skip_ws()
        if self.pos >= self.length:
            raise JsonPositionError("意外结束")
        char = self.text[self.pos]
        if char == "{":
            return self.parse_object(path)
        if char == "[":
            return self.parse_array(path)
        if char == '"':
            return self.parse_string()
        return self.parse_scalar()

    def parse_object(self, path):
        result = {}
        self.pos += 1
        self.skip_ws()
        if self.pos < self.length and self.text[self.pos] == "}":
            self.pos += 1
            return result
        while True:
            self.skip_ws()
            if self.pos >= self.length or self.text[self.pos] != '"':
                raise JsonPositionError("对象键必须是字符串（偏移 {0}）".format(self.pos))
            key_line = self.line_of(self.pos)
            key = self.parse_string()
            self.skip_ws()
            if self.pos >= self.length or self.text[self.pos] != ":":
                raise JsonPositionError("缺少冒号（偏移 {0}）".format(self.pos))
            self.pos += 1
            self.skip_ws()
            value_line = self.line_of(self.pos)
            child_path = path + (key,)
            self.positions[child_path] = min(key_line, value_line)
            result[key] = self.parse_value(child_path)
            self.skip_ws()
            if self.pos < self.length and self.text[self.pos] == ",":
                self.pos += 1
                continue
            if self.pos < self.length and self.text[self.pos] == "}":
                self.pos += 1
                return result
            raise JsonPositionError("对象未正确闭合（偏移 {0}）".format(self.pos))

    def parse_array(self, path):
        result = []
        self.pos += 1
        self.skip_ws()
        if self.pos < self.length and self.text[self.pos] == "]":
            self.pos += 1
            return result
        index = 0
        while True:
            self.skip_ws()
            child_path = path + (index,)
            self.positions[child_path] = self.line_of(self.pos)
            result.append(self.parse_value(child_path))
            index += 1
            self.skip_ws()
            if self.pos < self.length and self.text[self.pos] == ",":
                self.pos += 1
                continue
            if self.pos < self.length and self.text[self.pos] == "]":
                self.pos += 1
                return result
            raise JsonPositionError("数组未正确闭合（偏移 {0}）".format(self.pos))

    def parse_string(self):
        start = self.pos
        self.pos += 1
        while self.pos < self.length:
            char = self.text[self.pos]
            if char == "\\":
                self.pos += 2
                continue
            if char == '"':
                self.pos += 1
                return json.loads(self.text[start:self.pos])
            self.pos += 1
        raise JsonPositionError("字符串未闭合（偏移 {0}）".format(start))

    def parse_scalar(self):
        start = self.pos
        while self.pos < self.length and self.text[self.pos] not in ",]} \t\r\n":
            self.pos += 1
        raw = self.text[start:self.pos]
        if not raw:
            raise JsonPositionError("空标量（偏移 {0}）".format(start))
        try:
            return json.loads(raw)
        except ValueError:
            raise JsonPositionError("非法标量 {0!r}（偏移 {1}）".format(raw, start))


def parse_with_positions(text):
    """返回 ``(value, positions)``；``positions`` 键为路径元组。"""
    scanner = _Scanner(text)
    value = scanner.parse()
    return value, scanner.positions
