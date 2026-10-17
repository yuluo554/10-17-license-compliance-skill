# -*- coding: utf-8 -*-
"""M1：清单解析与 SPDX 归一化。

骨架阶段只占位（M0）：本模块尚未提供可调用实现，``pipeline`` 的分派表里对应项为 ``None``。
M1 落地时在此实现以下公开函数，并同步更新 ``plan/02`` 的目录职责表与 ``plan/05`` 的 DoD：

- ``parse_manifest(path)`` → 单个清单文件的记录列表
- ``normalize_license(raw, spdx_ids, exception_ids)`` → (spdx_id, confidence, evidence)
- ``build_inventory(paths)`` → ``inventory.json`` 的字典形态

纪律见 ``plan/03-模块详设.md`` §M1：四级可信度链、禁止全文关键词匹配、
``-only``/``-or-later`` 原样保留、未挂证据不落库。
"""

MILESTONE = "M1"

SUPPORTED_FILE_NAMES = (
    "package.json",
    "package-lock.json",
    "requirements.txt",
    "pyproject.toml",
    "go.mod",
    "pom.xml",
)

__all__ = ["MILESTONE", "SUPPORTED_FILE_NAMES"]
