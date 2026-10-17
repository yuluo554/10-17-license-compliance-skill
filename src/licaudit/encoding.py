# -*- coding: utf-8 -*-
"""控制台编码守卫。

Windows 的默认控制台编码可能是 cp936 / cp1252；CI 的管道更可能是 cp1252。
这里按 ``stream.encoding`` 探针决定是否 reconfigure，而不是无条件改编码：
中文控制台（cp936）保持不动，避免把本来能显示的中文改成乱码。
"""

import io
import sys

_UTF8_NAMES = ("utf-8", "utf8", "utf_8", "cp65001")


def _needs_utf8(stream):
    encoding = getattr(stream, "encoding", None)
    if encoding is None:
        return False
    return encoding.lower().replace("_", "-") not in (
        "utf-8",
        "utf-8-sig",
        "cp65001",
    )


def _reconfigure(stream):
    if stream is None:
        return
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return
    try:
        reconfigure(encoding="utf-8", errors="replace")
    except (ValueError, OSError, io.UnsupportedOperation):
        # 只读流、已关闭流或测试替身：保持原样，不因编码守卫而崩溃。
        pass


def ensure_utf8_stdio(stdout=None, stderr=None):
    """在需要时把 stdout/stderr 切到 UTF-8。

    传入自定义流（测试用）时按其 ``encoding`` 判断；传 ``None`` 用 ``sys.stdout``。
    """
    if stdout is None:
        stdout = sys.stdout
    if stderr is None:
        stderr = sys.stderr
    if _needs_utf8(stdout):
        _reconfigure(stdout)
    if _needs_utf8(stderr):
        _reconfigure(stderr)
