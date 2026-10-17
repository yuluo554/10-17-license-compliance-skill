# -*- coding: utf-8 -*-
"""编码守卫。

CI 的管道可能是 cp1252；``py -X utf8`` 只改「我们敲的那条命令」，
改不了子进程与 CI。这里用 cp1252 流复现，断言不崩且中文可写。
"""

import io

from licaudit.encoding import ensure_utf8_stdio


def _cp1252_stream():
    return io.TextIOWrapper(io.BytesIO(), encoding="cp1252", errors="strict", newline="")


def test_cp1252_stream_is_reconfigured_to_utf8():
    stream = _cp1252_stream()
    ensure_utf8_stdio(stdout=stream, stderr=stream)
    assert stream.encoding.lower().replace("_", "-") == "utf-8"


def test_chinese_can_be_written_after_guard():
    raw = io.BytesIO()
    stream = io.TextIOWrapper(raw, encoding="cp1252", errors="strict")
    ensure_utf8_stdio(stdout=stream, stderr=stream)
    stream.write("中文输出")
    stream.flush()
    assert raw.getvalue().decode("utf-8") == "中文输出"


def test_utf8_stream_is_left_alone():
    stream = io.TextIOWrapper(io.BytesIO(), encoding="utf-8")
    before = stream.encoding
    ensure_utf8_stdio(stdout=stream, stderr=stream)
    assert stream.encoding == before


def test_stream_without_encoding_is_ignored():
    class Dummy(object):
        def write(self, text):
            return len(text)

    dummy = Dummy()
    ensure_utf8_stdio(stdout=dummy, stderr=dummy)  # 不抛错即可


def test_reconfigure_failure_does_not_crash():
    class Broken(object):
        encoding = "cp1252"

        def reconfigure(self, **kwargs):
            raise ValueError("already detached")

    ensure_utf8_stdio(stdout=Broken(), stderr=Broken())


def test_none_streams_fall_back_to_sys_stdout():
    # 不传参不应抛错（真实入口形态）
    ensure_utf8_stdio()
