# -*- coding: utf-8 -*-
"""六个清单形态的解析器（M1）。

每个解析器把文件解析成「原始依赖记录」：

    {"package", "version", "raw_license", "structured", "classifiers",
     "locator", "line", "source_file"}

归一化（四级可信度链）在 :mod:`licaudit.inventory.normalize`，本层不做判定。
单件失败隔离（K30）：单条解析失败进 ``notes`` 并继续，不中断整批。

## 依赖许可证从哪来（重要口径）

清单文件本身多数**不含依赖各自的许可证**（``requirements.txt`` / ``go.mod`` 只有名字与版本）。
本解析器只接受**显式写出来的**许可证文本，绝不从包名或生态惯例推断。支持的注记形态：

| 文件 | 形态 |
| --- | --- |
| ``package.json`` | 依赖值可为对象 ``{"version": "1.0.0", "license": "MIT"}`` |
| ``package-lock.json`` | v2/v3 ``packages[*].license``（原生字段）；v1 ``dependencies[*].license`` |
| ``requirements.txt`` | 行尾注记 ``example-pkg-a==1.0.0  # license: MIT`` |
| ``pyproject.toml`` | ``dependencies`` 数组元素可为内联表 ``{name="x", version="1", license="MIT"}`` |
| ``go.mod`` | 行尾注记 ``// license: MIT`` |
| ``pom.xml`` | ``<dependency>`` 内可含 ``<license>`` 元素 |

没有注记 → ``raw_license = None`` → 第 4 级 ``truncated_fallback`` + 待人工确认。
这是「宁缺勿造」在数据层的落点：不写就是不知道。
"""

import io
import os
import re

from ..errors import UsageError
from .jsonpos import JsonPositionError, parse_with_positions
from . import toml_reader

__all__ = [
    "PARSERS",
    "ParsedFile",
    "detect_parser",
    "parse_manifest",
    "read_text",
]

NPM_DEPENDENCY_FIELDS = (
    "dependencies",
    "devDependencies",
    "peerDependencies",
    "optionalDependencies",
)

_REQUIREMENT_NAME = re.compile(r"^([A-Za-z0-9][A-Za-z0-9._-]*)(\[[^\]]*\])?")
_LICENSE_COMMENT = re.compile(r"(?:^|\s)#\s*license\s*:\s*(.+)$", re.I)
_GO_LICENSE_COMMENT = re.compile(r"//\s*license\s*:\s*(.+)$", re.I)
_VCS_PREFIXES = ("git+", "hg+", "svn+", "bzr+", "git:", "hg:", "svn:", "bzr:")


class ParsedFile(object):
    def __init__(self, path):
        self.path = path
        self.name = os.path.basename(path)
        self.records = []
        self.notes = []

    def note(self, code, message, line=None):
        self.notes.append(
            {"code": code, "message": message, "file": self.name, "line": line}
        )


def read_text(path):
    """按 UTF-8 读取；BOM 去掉；非 UTF-8 / 空 → ``UsageError``。"""
    try:
        with io.open(path, "rb") as stream:
            raw = stream.read()
    except OSError as exc:
        raise UsageError("清单文件不可读", path=path, reason=str(exc))
    if not raw.strip():
        raise UsageError("清单文件为空", path=path)
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise UsageError("清单文件不是 UTF-8 编码", path=path, reason=str(exc))
    if not text.strip():
        raise UsageError("清单文件只有空白", path=path)
    return text


def detect_parser(path):
    name = os.path.basename(path)
    if name in PARSERS:
        return PARSERS[name]
    raise UsageError(
        "不是受支持的依赖清单文件名",
        path=path,
        supported=", ".join(sorted(PARSERS)),
    )


def _record(package, version, raw_license, structured, locator, line,
            classifiers=None, source_file=None):
    return {
        "package": package,
        "version": version if isinstance(version, str) and version.strip() else None,
        "raw_license": raw_license,
        "structured": bool(structured),
        "classifiers": list(classifiers or []),
        "locator": locator,
        "line": line,
        "source_file": source_file,
    }


def _classifiers_from_value(value):
    if not isinstance(value, dict):
        return []
    candidates = value.get("classifiers")
    if not isinstance(candidates, list):
        return []
    return [
        item for item in candidates
        if isinstance(item, str) and item.startswith("License ::")
    ]


def _license_from_value(value):
    """从依赖值里取 ``(version, license_text)``。

    ``value`` 是字符串时视为版本范围；是对象时额外可带 ``license`` / ``licenses``。
    """
    if isinstance(value, str):
        return value, None
    if not isinstance(value, dict):
        return None, None
    version = value.get("version") if isinstance(value.get("version"), str) else None
    license_value = value.get("license")
    if isinstance(license_value, str) and license_value.strip():
        return version, license_value.strip()
    if isinstance(license_value, dict):
        license_type = license_value.get("type")
        if isinstance(license_type, str) and license_type.strip():
            return version, license_type.strip()
        url = license_value.get("url")
        if isinstance(url, str) and url.strip():
            return version, url.strip()
    licenses = value.get("licenses")
    if isinstance(licenses, list):
        parts = []
        for item in licenses:
            if isinstance(item, str) and item.strip():
                parts.append(item.strip())
            elif isinstance(item, dict):
                item_type = item.get("type")
                if isinstance(item_type, str) and item_type.strip():
                    parts.append(item_type.strip())
        if parts:
            return version, (parts[0] if len(parts) == 1 else " AND ".join(parts))
    return version, None


# ---------------------------------------------------------------------------
# package.json
# ---------------------------------------------------------------------------


def parse_package_json(path, text):
    parsed = ParsedFile(path)
    try:
        payload, positions = parse_with_positions(text)
    except JsonPositionError as exc:
        raise UsageError("JSON 语法错误", path=path, reason=str(exc))
    if not isinstance(payload, dict):
        raise UsageError("package.json 顶层必须是对象", path=path)

    if "license" in payload or "licenses" in payload:
        parsed.note(
            "root_license_ignored",
            "根包的 license 属于项目自身，不传递给依赖（避免猜测）",
            positions.get(("license",)) or positions.get(("licenses",)),
        )

    saw_block = False
    for field in NPM_DEPENDENCY_FIELDS:
        block = payload.get(field)
        if block is None:
            continue
        if not isinstance(block, dict):
            parsed.note(
                "invalid_dependency_block",
                "依赖块不是对象，已跳过",
                positions.get((field,)),
            )
            continue
        saw_block = True
        for package_name in block:
            if not isinstance(package_name, str) or not package_name.strip():
                parsed.note("invalid_dependency_name", "依赖名为空，已跳过",
                            positions.get((field,)))
                continue
            version, raw_license = _license_from_value(block[package_name])
            parsed.records.append(
                _record(
                    package_name,
                    version,
                    raw_license,
                    raw_license is not None,
                    "{0}.{1}".format(field, package_name),
                    positions.get((field, package_name)),
                    classifiers=_classifiers_from_value(block[package_name]),
                    source_file=parsed.name,
                )
            )

    if not saw_block:
        parsed.note("no_dependencies", "package.json 中没有可识别的依赖块", None)
    return parsed


def parse_package_lock(path, text):
    parsed = ParsedFile(path)
    try:
        payload, positions = parse_with_positions(text)
    except JsonPositionError as exc:
        raise UsageError("JSON 语法错误", path=path, reason=str(exc))
    if not isinstance(payload, dict):
        raise UsageError("package-lock.json 顶层必须是对象", path=path)

    lock_version = payload.get("lockfileVersion")
    try:
        normalized_version = int(lock_version)
    except (TypeError, ValueError):
        normalized_version = None
    if normalized_version not in (1, 2, 3):
        raise UsageError(
            "package-lock.json 的 lockfileVersion 不受支持（只支持 1/2/3）",
            path=path,
            lockfileVersion=lock_version,
        )

    if normalized_version in (2, 3) and isinstance(payload.get("packages"), dict):
        _parse_lock_packages(parsed, payload["packages"], positions)
    elif isinstance(payload.get("dependencies"), dict):
        _parse_lock_dependencies(parsed, payload["dependencies"], positions, "")
    else:
        parsed.note(
            "no_dependencies",
            "package-lock.json 中没有 packages / dependencies",
            None,
        )
    return parsed


def _parse_lock_packages(parsed, packages, positions):
    for key in packages:
        if key == "":
            continue  # 根包跳过（plan/03 §1.1）
        entry = packages[key]
        if not isinstance(entry, dict):
            parsed.note(
                "invalid_lock_entry",
                "lock 条目不是对象，已跳过",
                positions.get(("packages", key)),
            )
            continue
        name = entry.get("name")
        if not isinstance(name, str) or not name:
            name = key.split("node_modules/")[-1] if key else None
        if not name:
            parsed.note("invalid_lock_entry", "无法从路径推出包名，已跳过",
                        positions.get(("packages", key)))
            continue
        raw_license = entry.get("license")
        if isinstance(raw_license, dict):
            raw_license = _license_from_value({"license": raw_license})[1]
        if not isinstance(raw_license, str) or not raw_license.strip():
            raw_license = None
        parsed.records.append(
            _record(
                name,
                entry.get("version"),
                raw_license,
                raw_license is not None,
                "packages.{0}.license".format(key),
                positions.get(("packages", key)),
                source_file=parsed.name,
            )
        )


def _parse_lock_dependencies(parsed, dependencies, positions, prefix):
    for name in dependencies:
        entry = dependencies[name]
        if not isinstance(entry, dict):
            continue
        raw_license = entry.get("license")
        if not isinstance(raw_license, str) or not raw_license.strip():
            raw_license = None
        locator = "{0}dependencies.{1}.license".format(prefix, name)
        parsed.records.append(
            _record(
                name,
                entry.get("version"),
                raw_license,
                raw_license is not None,
                locator,
                positions.get(("dependencies", name)) if not prefix else None,
                source_file=parsed.name,
            )
        )
        nested = entry.get("dependencies")
        if isinstance(nested, dict):
            _parse_lock_dependencies(
                parsed, nested, {}, "{0}dependencies.{1}.".format(prefix, name)
            )


# ---------------------------------------------------------------------------
# requirements.txt
# ---------------------------------------------------------------------------


def parse_requirements(path, text):
    parsed = ParsedFile(path)
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        stripped = raw_line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("-"):
            token = stripped.split()[0]
            if token in ("-r", "--requirement"):
                parsed.note(
                    "requirements_include_ignored",
                    "包含文件未展开，依赖完整性需人工确认",
                    line_number,
                )
            elif token in ("-e", "--editable"):
                parsed.note(
                    "requirements_editable_ignored", "editable 行不解析为依赖", line_number
                )
            else:
                parsed.note(
                    "requirements_option_ignored", "选项行不产依赖", line_number
                )
            continue

        license_match = _LICENSE_COMMENT.search(stripped)
        raw_license = license_match.group(1).strip() if license_match else None
        line = _LICENSE_COMMENT.sub("", stripped).strip()
        line = _strip_trailing_comment(line)
        if not line:
            continue
        if line.lower().startswith(_VCS_PREFIXES) or "://" in line:
            parsed.note("requirements_vcs_ignored", "VCS/URL 依赖不解析", line_number)
            continue

        record = _parse_requirement_line(line, line_number)
        if record is None:
            parsed.note("requirements_unparsed", "无法解析的依赖行", line_number)
            continue
        record["raw_license"] = raw_license
        record["structured"] = raw_license is not None
        record["source_file"] = parsed.name
        parsed.records.append(record)

    if not parsed.records and not parsed.notes:
        parsed.note("no_dependencies", "requirements.txt 中没有依赖行", None)
    return parsed


def _strip_trailing_comment(line):
    match = re.search(r"\s+#", line)
    if match:
        return line[: match.start()].strip()
    return line


def _parse_requirement_line(line, line_number):
    if ";" in line:
        line = line.split(";", 1)[0].strip()
    match = _REQUIREMENT_NAME.match(line)
    if not match:
        return None
    name = match.group(1)
    rest = line[match.end():].strip()
    version = None
    if rest.startswith("==="):
        version = rest[3:].strip()
    elif rest.startswith("=="):
        version = rest[2:].strip()
        if version.endswith(".*"):
            version = version[:-2]
    version = version or None
    return {
        "package": name,
        "version": version,
        "raw_license": None,
        "structured": False,
        "classifiers": [],
        "locator": "line {0}".format(line_number),
        "line": line_number,
    }


# ---------------------------------------------------------------------------
# pyproject.toml
# ---------------------------------------------------------------------------


def parse_pyproject(path, text):
    parsed = ParsedFile(path)
    try:
        payload = toml_reader.parse(text)
    except toml_reader.TomlUnsupported as exc:
        parsed.note("toml_unsupported", str(exc), None)
        raise UsageError(
            "pyproject.toml 超出受限 TOML 子集，无法可靠解析",
            path=path,
            reason=str(exc),
        )
    except toml_reader.TomlError as exc:
        raise UsageError("pyproject.toml 语法错误", path=path, reason=str(exc))
    if not isinstance(payload, dict):
        raise UsageError("pyproject.toml 顶层必须是表", path=path)

    project = payload.get("project") if isinstance(payload.get("project"), dict) else {}
    tool = payload.get("tool")
    poetry = {}
    if isinstance(tool, dict) and isinstance(tool.get("poetry"), dict):
        poetry = tool["poetry"]

    if "license" in project or "license" in poetry:
        parsed.note(
            "root_license_ignored",
            "项目自身 license 不传递给依赖（避免猜测）",
            None,
        )

    classifiers = project.get("classifiers")
    if not isinstance(classifiers, list):
        classifiers = []
    project_classifiers = [
        item for item in classifiers if isinstance(item, str) and item.startswith("License ::")
    ]
    if project_classifiers:
        parsed.note(
            "root_classifier_ignored",
            "项目级 classifier 不传递给依赖（避免猜测）",
            None,
        )

    for dependency in project.get("dependencies") or []:
        record = _dependency_entry(dependency)
        if record is None:
            parsed.note("dependency_unparsed", "无法解析的 PEP 508 依赖", None)
            continue
        parsed.records.append(
            _record(
                record["package"],
                record["version"],
                record["raw_license"],
                record["raw_license"] is not None,
                "project.dependencies.{0}".format(record["package"]),
                None,
                classifiers=record["classifiers"],
                source_file=parsed.name,
            )
        )

    optional = project.get("optional-dependencies")
    if isinstance(optional, dict):
        for group in optional:
            for dependency in optional[group] or []:
                record = _dependency_entry(dependency)
                if record is None:
                    parsed.note("dependency_unparsed", "无法解析的可选依赖", None)
                    continue
                parsed.records.append(
                    _record(
                        record["package"],
                        record["version"],
                        record["raw_license"],
                        record["raw_license"] is not None,
                        "project.optional-dependencies.{0}.{1}".format(
                            group, record["package"]
                        ),
                        None,
                        classifiers=record["classifiers"],
                        source_file=parsed.name,
                    )
                )

    poetry_dependencies = poetry.get("dependencies")
    if isinstance(poetry_dependencies, dict):
        for name in poetry_dependencies:
            if name.lower() == "python":
                continue
            value = poetry_dependencies[name]
            version = None
            raw_license = None
            classifiers = []
            if isinstance(value, str):
                version = value
            elif isinstance(value, dict):
                if isinstance(value.get("version"), str):
                    version = value["version"]
                candidate = value.get("license")
                if isinstance(candidate, str) and candidate.strip():
                    raw_license = candidate.strip()
                classifiers = _classifiers_from_value(value)
            parsed.records.append(
                _record(
                    name,
                    _clean_poetry_version(version),
                    raw_license,
                    raw_license is not None,
                    "tool.poetry.dependencies.{0}".format(name),
                    None,
                    classifiers=classifiers,
                    source_file=parsed.name,
                )
            )

    if not parsed.records and not parsed.notes:
        parsed.note("no_dependencies", "pyproject.toml 中没有依赖声明", None)
    return parsed


def _dependency_entry(dependency):
    """PEP 508 字符串或内联表注记 → ``{package, version, raw_license, classifiers}``。"""
    if isinstance(dependency, dict):
        name = dependency.get("name")
        if not isinstance(name, str) or not name.strip():
            return None
        version = dependency.get("version")
        raw_license = dependency.get("license")
        if not isinstance(raw_license, str) or not raw_license.strip():
            raw_license = None
        return {
            "package": name.strip(),
            "version": version if isinstance(version, str) else None,
            "raw_license": raw_license,
            "classifiers": _classifiers_from_value(dependency),
        }
    if not isinstance(dependency, str):
        return None
    text = dependency.strip()
    if not text:
        return None
    if " @ " in text:
        text = text.split(" @ ", 1)[0].strip()
    if ";" in text:
        text = text.split(";", 1)[0].strip()
    match = _REQUIREMENT_NAME.match(text)
    if not match:
        return None
    name = match.group(1)
    rest = text[match.end():].strip()
    version = None
    if rest.startswith("==="):
        version = rest[3:].strip()
    elif rest.startswith("=="):
        version = rest[2:].strip()
    return {
        "package": name,
        "version": version or None,
        "raw_license": None,
        "classifiers": [],
    }


def _clean_poetry_version(version):
    if not isinstance(version, str):
        return None
    text = version.strip().lstrip("^~=<>! ").strip()
    if not text or text.startswith("*"):
        return None
    return text


# ---------------------------------------------------------------------------
# go.mod
# ---------------------------------------------------------------------------


def parse_go_mod(path, text):
    parsed = ParsedFile(path)
    in_require_block = False

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.strip()
        if not line or line.startswith("//"):
            continue
        if line.startswith("require ("):
            in_require_block = True
            continue
        if in_require_block and line == ")":
            in_require_block = False
            continue
        if in_require_block or line.startswith("require "):
            token_line = line[len("require "):] if line.startswith("require ") else line
            license_match = _GO_LICENSE_COMMENT.search(token_line)
            raw_license = license_match.group(1).strip() if license_match else None
            token_line = token_line.split("//", 1)[0].strip()
            record = _parse_go_require(token_line, line_number)
            if record is None:
                parsed.note("go_require_unparsed", "无法解析的 require 行", line_number)
                continue
            record["raw_license"] = raw_license
            record["structured"] = raw_license is not None
            record["source_file"] = parsed.name
            parsed.records.append(record)

    if not parsed.records:
        parsed.note("no_dependencies", "go.mod 中没有 require 声明", None)
    return parsed


def _parse_go_require(line, line_number):
    parts = line.split()
    if len(parts) < 2:
        return None
    return {
        "package": parts[0],
        "version": parts[1],
        "raw_license": None,
        "structured": False,
        "classifiers": [],
        "locator": "require {0}".format(parts[0]),
        "line": line_number,
    }


# ---------------------------------------------------------------------------
# pom.xml
# ---------------------------------------------------------------------------


_DEPENDENCY_BLOCK = re.compile(r"<dependency>(.*?)</dependency>", re.S)
_LICENSES_BLOCK = re.compile(r"<licenses>(.*?)</licenses>", re.S)
_LICENSE_ENTRY = re.compile(r"<license>(.*?)</license>", re.S)
_GROUP_ID = re.compile(r"<groupId>\s*(.*?)\s*</groupId>", re.S)
_ARTIFACT_ID = re.compile(r"<artifactId>\s*(.*?)\s*</artifactId>", re.S)
_VERSION_TAG = re.compile(r"<version>\s*(.*?)\s*</version>", re.S)
_NAME_TAG = re.compile(r"<name>\s*(.*?)\s*</name>", re.S)
_URL_TAG = re.compile(r"<url>\s*(.*?)\s*</url>", re.S)
_LICENSE_TAG = re.compile(r"<license>\s*(.*?)\s*</license>", re.S)
_COMMENT = re.compile(r"<!--.*?-->", re.S)


def parse_pom(path, text):
    parsed = ParsedFile(path)
    stripped = _COMMENT.sub("", text)

    project_licenses = _LICENSES_BLOCK.search(stripped)
    if project_licenses:
        parsed.note(
            "root_license_ignored",
            "项目 <licenses> 不传递给依赖（避免猜测）",
            _line_of(text, text.find("<licenses>")),
        )

    for match in _DEPENDENCY_BLOCK.finditer(stripped):
        body = match.group(1)
        group = _GROUP_ID.search(body)
        artifact = _ARTIFACT_ID.search(body)
        if not artifact:
            parsed.note(
                "pom_dependency_unparsed",
                "依赖缺少 artifactId，已跳过",
                _line_of(text, text.find(match.group(0))),
            )
            continue
        group_id = group.group(1).strip() if group else ""
        artifact_id = artifact.group(1).strip()
        package = "{0}:{1}".format(group_id, artifact_id) if group_id else artifact_id
        version = _VERSION_TAG.search(body)

        raw_license = None
        # 依赖级注记：<dependency><license>MIT</license></dependency>
        license_tag = _LICENSE_TAG.search(body)
        if license_tag:
            raw_license = license_tag.group(1).strip() or None
        else:
            # 单依赖也可写 <licenses><license><name>...</name></license></licenses>
            nested_licenses = _LICENSES_BLOCK.search(body)
            if nested_licenses:
                for entry in _LICENSE_ENTRY.finditer(nested_licenses.group(1)):
                    entry_body = entry.group(1)
                    name = _NAME_TAG.search(entry_body)
                    url = _URL_TAG.search(entry_body)
                    if name:
                        raw_license = name.group(1).strip() or None
                    elif url:
                        raw_license = url.group(1).strip() or None
                    if raw_license:
                        break

        parsed.records.append(
            _record(
                package,
                version.group(1).strip() if version else None,
                raw_license,
                raw_license is not None,
                "<dependency> {0}".format(package),
                _line_of(text, text.find(match.group(0))),
                source_file=parsed.name,
            )
        )

    if not parsed.records:
        parsed.note("no_dependencies", "pom.xml 中没有 <dependencies>", None)
    return parsed


def _line_of(text, offset):
    if offset < 0:
        return None
    return text.count("\n", 0, offset) + 1


PARSERS = {
    "package.json": parse_package_json,
    "package-lock.json": parse_package_lock,
    "requirements.txt": parse_requirements,
    "pyproject.toml": parse_pyproject,
    "go.mod": parse_go_mod,
    "pom.xml": parse_pom,
}


def parse_manifest(path):
    """解析单个清单文件 → :class:`ParsedFile`。"""
    parser = detect_parser(path)
    text = read_text(path)
    return parser(path, text)
