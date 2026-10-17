# -*- coding: utf-8 -*-
"""SPDX 表达式解析与版本语义（M1）。

文法（充分子集，plan/03 §1.4）::

    expr   := term (OR term)*
    term   := factor (AND factor)*
    factor := id ['+'] | id 'WITH' exception | '(' expr ')'

纪律：

- ``AND`` / ``OR`` / ``WITH`` 必须大写；小写按普通标识符处理 → 解析失败 → 降级。
- 标识符必须命中 SPDX ``licenses.json`` 的 ``licenseId``；``-only`` / ``-or-later`` 原样保留。
- 族名（``GPL`` / ``Apache`` / ``BSD`` …）→ ``<族>-unknown`` 并标待确认，**不取最新版**。
- ``WITH`` 例外必须命中 ``exceptions.json``；未命中 → 保留表达式并标 ``unknown-exception``。
- 不做版本归一化，不展开、不重排 ``AND`` / ``OR``。
"""

import re

FAMILIES = ("GPL", "LGPL", "AGPL", "Apache", "BSD", "MPL", "EPL", "CDDL")

# 族名别名（按 token 序列匹配；允许 "The" 前缀与 license / licence / software 等修饰）
_FAMILY_TOKENS = (
    ("AGPL", (("agpl",), ("gnu", "affero", "general", "public", "license"))),
    ("LGPL", (
        ("lgpl",),
        ("gnu", "lesser", "general", "public", "license"),
        ("gnu", "library", "general", "public", "license"),
    )),
    ("GPL", (("gpl",), ("gnu", "general", "public", "license"))),
    ("Apache", (("apache",), ("asl",))),
    ("BSD", (("bsd",),)),
    ("MPL", (("mpl",), ("mozilla", "public", "license"))),
    ("EPL", (("epl",), ("eclipse", "public", "license"))),
    ("CDDL", (("cddl",),)),
)

_FILLER_TOKENS = frozenset(
    ("the", "license", "licence", "software", "version", "public", "general", "v")
)

_TOKEN_SPLIT = re.compile(r"[\s,;/]+")

# 版本 token 归一：允许 "v3" / "version 2.0" / "3.0" 等写法
_VERSION_PREFIX = ("v", "version")

_VERSION_TOKENS = {
    "GPL": {
        "1": ("GPL-1.0", True),
        "1.0": ("GPL-1.0", True),
        "2": ("GPL-2.0", True),
        "2.0": ("GPL-2.0", True),
        "3": ("GPL-3.0", True),
        "3.0": ("GPL-3.0", True),
    },
    "LGPL": {
        "2": ("LGPL-2.0", True),
        "2.0": ("LGPL-2.0", True),
        "2.1": ("LGPL-2.1", True),
        "3": ("LGPL-3.0", True),
        "3.0": ("LGPL-3.0", True),
    },
    "AGPL": {
        "1": ("AGPL-1.0", True),
        "3": ("AGPL-3.0", True),
        "3.0": ("AGPL-3.0", True),
    },
    "Apache": {
        "1": ("Apache-1.0", False),
        "1.0": ("Apache-1.0", False),
        "1.1": ("Apache-1.1", False),
        "2": ("Apache-2.0", False),
        "2.0": ("Apache-2.0", False),
    },
    "MPL": {
        "1": ("MPL-1.0", False),
        "1.0": ("MPL-1.0", False),
        "1.1": ("MPL-1.1", False),
        "2": ("MPL-2.0", False),
        "2.0": ("MPL-2.0", False),
    },
    "EPL": {
        "1": ("EPL-1.0", False),
        "1.0": ("EPL-1.0", False),
        "2": ("EPL-2.0", False),
        "2.0": ("EPL-2.0", False),
    },
    "CDDL": {
        "1": ("CDDL-1.0", False),
        "1.0": ("CDDL-1.0", False),
        "1.1": ("CDDL-1.1", False),
    },
    "BSD": {},
}

OPERATORS = ("AND", "OR", "WITH")

_TOKEN_SPLIT = re.compile(r"[\s,;/]+")
_VERSION_RE = re.compile(r"^(?:v|version)?(\d+(?:\.\d+)?)$")


class ExprError(ValueError):
    """表达式无法按 SPDX 文法解析。"""


class SpdxIndex(object):
    """SPDX 快照的只读索引。"""

    def __init__(self, licenses_payload, exceptions_payload):
        self.licenses = {}
        for item in licenses_payload.get("licenses", []):
            license_id = item.get("licenseId")
            if license_id:
                self.licenses[license_id] = item
        self.exceptions = {}
        for item in exceptions_payload.get("exceptions", []):
            exception_id = item.get("licenseExceptionId")
            if exception_id:
                self.exceptions[exception_id] = item
        self._lower = {}
        for license_id in self.licenses:
            self._lower.setdefault(license_id.lower(), []).append(license_id)

    def has_license(self, license_id):
        return license_id in self.licenses

    def has_exception(self, exception_id):
        return exception_id in self.exceptions

    def details_url(self, license_id):
        item = self.licenses.get(license_id) or {}
        return item.get("detailsUrl")

    def is_deprecated(self, license_id):
        item = self.licenses.get(license_id) or {}
        return bool(item.get("isDeprecatedLicenseId"))

    def is_osi_approved(self, license_id):
        item = self.licenses.get(license_id) or {}
        return item.get("isOsiApproved")

    def is_fsf_libre(self, license_id):
        item = self.licenses.get(license_id) or {}
        return item.get("isFsfLibre")

    def lookup_case_insensitive(self, token):
        candidates = self._lower.get(token.lower(), [])
        if len(candidates) == 1:
            return candidates[0]
        return None


class Token(object):
    __slots__ = ("kind", "value", "offset")

    def __init__(self, kind, value, offset):
        self.kind = kind
        self.value = value
        self.offset = offset

    def __repr__(self):
        return "Token({0!r}, {1!r})".format(self.kind, self.value)


def tokenize(text):
    tokens = []
    index = 0
    length = len(text)
    while index < length:
        char = text[index]
        if char.isspace():
            index += 1
            continue
        if char in "()":
            tokens.append(Token(char, char, index))
            index += 1
            continue
        start = index
        while index < length and not text[index].isspace() and text[index] not in "()":
            index += 1
        word = text[start:index]
        if word in OPERATORS:
            tokens.append(Token("op", word, start))
        else:
            tokens.append(Token("word", word, start))
    if not tokens:
        raise ExprError("空表达式")
    return tokens


class _Parser(object):
    def __init__(self, tokens, index):
        self.tokens = tokens
        self.pos = 0
        self.spdx = index

    def peek(self):
        if self.pos >= len(self.tokens):
            return None
        return self.tokens[self.pos]

    def take(self):
        token = self.peek()
        if token is None:
            raise ExprError("表达式意外结束")
        self.pos += 1
        return token

    def parse(self):
        node = self.parse_expr()
        if self.peek() is not None:
            raise ExprError("表达式尾部有多余记号：{0}".format(self.peek().value))
        return node

    def parse_expr(self):
        operands = [self.parse_term()]
        while True:
            token = self.peek()
            if token is None or token.kind != "op" or token.value != "OR":
                break
            self.take()
            operands.append(self.parse_term())
        if len(operands) == 1:
            return operands[0]
        return {"op": "OR", "args": operands}

    def parse_term(self):
        operands = [self.parse_factor()]
        while True:
            token = self.peek()
            if token is None or token.kind != "op" or token.value != "AND":
                break
            self.take()
            operands.append(self.parse_factor())
        if len(operands) == 1:
            return operands[0]
        return {"op": "AND", "args": operands}

    def parse_factor(self):
        token = self.take()
        if token.kind == "(":
            inner = self.parse_expr()
            closing = self.peek()
            if closing is None or closing.kind != ")":
                raise ExprError("括号未闭合")
            self.take()
            if isinstance(inner, dict) and "op" in inner:
                inner["parenthesized"] = True
            return inner
        if token.kind != "word":
            raise ExprError("此处不应出现 {0!r}".format(token.value))

        identifier, plus = self._resolve_id(token.value)
        node = {"id": identifier, "token": token.value, "plus": plus}
        following = self.peek()
        if following is not None and following.kind == "op" and following.value == "WITH":
            self.take()
            exception_token = self.take()
            if exception_token.kind != "word":
                raise ExprError("WITH 后必须是例外标识符")
            node["exception"] = exception_token.value
            node["exception_known"] = self.spdx.has_exception(exception_token.value)
        return node

    def _resolve_id(self, token):
        if self.spdx.has_license(token):
            return token, False
        if token.endswith("+"):
            stripped = token[:-1]
            if self.spdx.has_license(stripped):
                return stripped, True
        family = family_of(token)
        if family:
            return family + "-unknown", False
        case_match = self.spdx.lookup_case_insensitive(token)
        if case_match:
            return case_match, False
        raise ExprError("未知的许可证标识符：{0}".format(token))


def _tokens(text):
    raw = _TOKEN_SPLIT.split(text.strip())
    return [token for token in raw if token]


def _match_family(tokens):
    """返回 ``(family, rest_tokens)``；不匹配返回 ``(None, tokens)``。"""
    lowered = [token.lower().strip(".") for token in tokens]
    if lowered and lowered[0] == "the":
        lowered = lowered[1:]
        tokens = tokens[1:]
    best = None
    for family, sequences in _FAMILY_TOKENS:
        for sequence in sequences:
            if len(lowered) >= len(sequence) and tuple(lowered[: len(sequence)]) == sequence:
                if best is None or len(sequence) > best[0]:
                    best = (len(sequence), family)
    if best is None:
        return None, tokens
    family = best[1]
    rest = tokens[best[0]:]
    filtered = [token for token in rest if token.lower().strip(".") not in _FILLER_TOKENS]
    return family, filtered


def family_of(text):
    """整串只是族名（可带 License / The 等修饰）时返回族名，否则 ``None``。"""
    tokens = _tokens(text)
    if not tokens:
        return None
    family, rest = _match_family(tokens)
    if family and not rest:
        return family
    return None


def family_version_of(text, index=None):
    """``GPL v3`` / ``GPLv3`` / ``Apache License, Version 2.0`` 这类「族名 + 版本」。

    返回 ``(spdx_id, ambiguous)``；无法判定返回 ``(None, False)``。
    ``ambiguous=True`` 表示原文没说 ``-only`` / ``-or-later``，归一化到旧式 ID 并标待确认。
    """
    tokens = _tokens(text)
    if not tokens:
        return None, False
    family, rest = _match_family(tokens)
    if not family or not rest:
        return None, False

    version = _extract_version(rest)
    if version is None:
        return None, False
    mapping = _VERSION_TOKENS.get(family, {})
    if version not in mapping:
        return None, False
    spdx_id, ambiguous = mapping[version]
    if index is not None and not index.has_license(spdx_id):
        return None, False
    return spdx_id, ambiguous


def _extract_version(rest):
    """从族名之后的 token 里取出纯版本号（去 ``v`` / ``version`` 前缀）。"""
    tokens = [token.lower().strip(".") for token in rest]
    while tokens and tokens[0] in _VERSION_PREFIX:
        tokens = tokens[1:]
    tokens = [token for token in tokens if token]
    if not tokens:
        return None
    # "2.0" / "2" / "v3"（若 v 与数字连写）
    candidate = tokens[0]
    if candidate.startswith("v") and candidate[1:2].isdigit():
        candidate = candidate[1:]
    if not re.match(r"^\d+(?:\.\d+)?$", candidate):
        return None
    return candidate


def render(node):
    """把 AST 渲染为规范化字符串；``AND``/``OR`` 不展开、不重排。"""
    if "op" in node:
        text = (" {0} ".format(node["op"])).join(render(child) for child in node["args"])
        if node.get("parenthesized"):
            return "(" + text + ")"
        return text
    text = node["id"]
    if node.get("plus"):
        text += "+"
    if node.get("exception"):
        text += " WITH " + node["exception"]
    return text


def atoms(node, out=None):
    """收集原子 ID（含 ``<族>-unknown``），按出现顺序去重。"""
    if out is None:
        out = []
    if "op" in node:
        for child in node["args"]:
            atoms(child, out)
    elif node["id"] not in out:
        out.append(node["id"])
    return out


def unknown_exceptions(node, out=None):
    if out is None:
        out = []
    if "op" in node:
        for child in node["args"]:
            unknown_exceptions(child, out)
    elif node.get("exception") and not node.get("exception_known"):
        out.append(node["exception"])
    return out


class ParsedExpression(object):
    def __init__(self, node, text):
        self.node = node
        self.text = text

    @property
    def atoms(self):
        return atoms(self.node)

    @property
    def unknown_exceptions(self):
        return unknown_exceptions(self.node)

    @property
    def flags(self):
        result = []
        if self.unknown_exceptions:
            result.append("unknown-exception")
        if any(atom.endswith("-unknown") for atom in self.atoms):
            result.append("family-unknown")
        return result

    def details_urls(self, index):
        urls = []
        for atom in self.atoms:
            url = index.details_url(atom)
            if url and url not in urls:
                urls.append(url)
        return urls

    def deprecated_atoms(self, index):
        return [atom for atom in self.atoms if index.is_deprecated(atom)]


def parse_expression(text, index):
    """解析并规范化；无法按文法解析 → :class:`ExprError`（调用方降级）。"""
    if not isinstance(text, str) or not text.strip():
        raise ExprError("空表达式")
    tokens = tokenize(text)
    parser = _Parser(tokens, index)
    node = parser.parse()
    return ParsedExpression(node, render(node))


def normalize_for_anchor(text):
    """首行锚定用的归一化：大小写、空白、连字符、下划线等价，去尾部标点。"""
    lowered = text.strip().lower()
    lowered = lowered.replace("_", "-")
    lowered = lowered.rstrip(".")
    chars = []
    previous_was_separator = False
    for char in lowered:
        if char.isspace() or char == "-":
            if not previous_was_separator:
                chars.append("-")
            previous_was_separator = True
            continue
        chars.append(char)
        previous_was_separator = False
    return "".join(chars).strip("-")


# 首行允许的「ID + 后缀」形态（plan/03 §1.3 第 3 级：受限形态开头）。
# 只接受 license 类后缀：表达式类的 or/and/with 交给表达式解析器；
# 表达式解析失败时应当降级，而不是在这里猜一个 ID。
_ANCHOR_SUFFIXES = ("license", "licence")


def anchored_first_line(line, index):
    """第 3 级：首行锚定匹配。

    只接受「整行就是标识符 / 表达式 / 族名」「标识符 + 受限后缀开头」两种形态；
    **不在整段文本里搜关键词**。返回 ``(spdx_id, flags)``，不匹配返回 ``(None, [])``。
    """
    if not isinstance(line, str):
        return None, []
    stripped = line.strip()
    if not stripped or len(stripped) > 200:
        return None, []

    # 1) 整行就是合规表达式（"MIT OR Apache-2.0"）
    try:
        parsed = parse_expression(stripped, index)
        if parsed.atoms:
            return parsed.text, parsed.flags
    except ExprError:
        pass

    normalized = normalize_for_anchor(stripped)

    # 2) 整行等于 ID，或 ID + "license"
    for license_id in index.licenses:
        candidate = normalize_for_anchor(license_id)
        if normalized == candidate or normalized == candidate + "-license":
            flags = []
            if index.is_deprecated(license_id):
                flags.append("deprecated-id")
            return license_id, flags

    # 3) ID + 受限后缀开头（如 "Apache-2.0 License"、"MIT (Expat)"）
    matched = _prefix_id(normalized, index)
    if matched:
        license_id, flags = matched
        return license_id, flags

    # 4) 族名（可带 License 修饰）→ <族>-unknown，不取最新版
    family = family_of(stripped)
    if family:
        return family + "-unknown", ["family-unknown"]

    # 5) 族名 + 版本但未声明 only/or-later → 旧式 ID + 歧义标记
    spdx_id, ambiguous = family_version_of(stripped, index)
    if spdx_id:
        flags = []
        if ambiguous:
            flags.append("version-ambiguous")
        if index.is_deprecated(spdx_id):
            flags.append("deprecated-id")
        return spdx_id, flags

    # 6) 以族名开头（如 "LGPL with exceptions"）→ <族>-unknown，仍属首行锚定
    tokens = _tokens(stripped)
    if tokens:
        family, _rest = _match_family(tokens)
        if family:
            return family + "-unknown", ["family-unknown"]

    return None, []


def _prefix_id(normalized, index):
    """``ID + license`` 整行形态；返回 ``(id, flags)`` 或 ``None``。

    只接受「标识符后紧跟 license/licence 且再没有别的内容」，
    避免把 ``MIT License permission is hereby granted ...`` 这类正文首行当成授权声明。
    """
    best = None
    for license_id in index.licenses:
        candidate = normalize_for_anchor(license_id)
        for suffix in _ANCHOR_SUFFIXES:
            if normalized == candidate + "-" + suffix:
                if best is None or len(candidate) > len(best[0]):
                    best = (candidate, license_id)
    if best is None:
        return None
    license_id = best[1]
    flags = []
    if index.is_deprecated(license_id):
        flags.append("deprecated-id")
    return license_id, flags


__all__ = [
    "ExprError",
    "FAMILIES",
    "ParsedExpression",
    "SpdxIndex",
    "anchored_first_line",
    "atoms",
    "family_of",
    "family_version_of",
    "normalize_for_anchor",
    "parse_expression",
    "render",
    "tokenize",
]
