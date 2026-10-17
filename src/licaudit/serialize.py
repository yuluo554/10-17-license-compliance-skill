# -*- coding: utf-8 -*-
"""确定性序列化与原子写。

所有产物都经本模块写出：换一个子命令，写盘形态不会变。
冻结契约（K6）：
  - JSON：``ensure_ascii=False``、``indent=2``、字段序由调用方/契约常量决定、LF、结尾换行
  - CSV：``lineterminator="\\n"``、UTF-8 无 BOM、列序由 ``contract.REPORT_CSV_COLUMNS`` 决定
  - 原子写：先写同目录临时文件，再 ``os.replace``
  - 不读时钟、不读随机数
"""

import csv
import io
import json
import os
import tempfile

from .errors import UsageError


def dumps_json(obj):
    """把对象序列化为冻结形态的 JSON 文本（不含 BOM，LF，结尾换行）。"""
    text = json.dumps(obj, ensure_ascii=False, indent=2, sort_keys=False)
    return text + "\n"


def write_text_atomic(path, text):
    """原子写文本：同目录临时文件 → ``os.replace``。"""
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    handle, tmp_path = tempfile.mkstemp(
        prefix=".licaudit-", suffix=".tmp", dir=directory or None
    )
    try:
        with io.open(handle, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(text)
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def write_json(path, obj):
    write_text_atomic(path, dumps_json(obj))


def dumps_csv(rows, columns):
    """按固定列序渲染 CSV 文本。

    ``rows`` 是 dict 序列；缺列的单元格写空串（不写 ``None`` 字面量）。
    """
    buffer = io.StringIO(newline="")
    writer = csv.DictWriter(
        buffer, fieldnames=list(columns), lineterminator="\n", extrasaction="ignore"
    )
    writer.writeheader()
    for row in rows:
        normalized = {}
        for column in columns:
            value = row.get(column, "")
            normalized[column] = "" if value is None else value
        writer.writerow(normalized)
    return buffer.getvalue()


def write_csv(path, rows, columns):
    write_text_atomic(path, dumps_csv(rows, columns))


def load_artifact(path, expected_formats):
    """读取自描述产物；``format`` 不在白名单即拒绝。"""
    if not os.path.isfile(path):
        raise UsageError("产物文件不存在", path=path)
    try:
        with io.open(path, "r", encoding="utf-8-sig") as stream:
            payload = json.load(stream)
    except (UnicodeDecodeError, ValueError) as exc:
        raise UsageError("产物不是合法 UTF-8 JSON", path=path, reason=str(exc))
    if not isinstance(payload, dict):
        raise UsageError("产物顶层必须是对象", path=path)
    fmt = payload.get("format")
    if fmt not in expected_formats:
        raise UsageError(
            "产物格式不受支持",
            path=path,
            got=fmt,
            expected="/".join(expected_formats),
        )
    if payload.get("format_version") != 1:
        raise UsageError(
            "产物格式版本不受支持",
            path=path,
            got=payload.get("format_version"),
        )
    return payload
