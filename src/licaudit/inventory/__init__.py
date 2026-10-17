# -*- coding: utf-8 -*-
"""M1：清单解析与 SPDX 归一化。

公开函数：

- :func:`parse_manifest` → 单个清单文件的原始记录
- :func:`normalize_license` → 四级可信度链归一化
- :func:`build_inventory` → ``inventory.json`` 的字典形态

纪律见 ``plan/03-模块详设.md`` §M1：四级可信度链、禁止全文关键词匹配、
``-only``/``-or-later`` 原样保留、未挂证据不落库。
"""

from .build import build_inventory, inventory_path, write_inventory
from .manifests import PARSERS, parse_manifest
from .normalize import CONFIDENCE_LEVELS, Normalized, normalize_license
from .spdx_expr import SpdxIndex, parse_expression
from .spdx_snapshot import load_snapshot

MILESTONE = "M1"

SUPPORTED_FILE_NAMES = (
    "package.json",
    "package-lock.json",
    "requirements.txt",
    "pyproject.toml",
    "go.mod",
    "pom.xml",
)

__all__ = [
    "CONFIDENCE_LEVELS",
    "MILESTONE",
    "Normalized",
    "PARSERS",
    "SUPPORTED_FILE_NAMES",
    "SpdxIndex",
    "build_inventory",
    "inventory_path",
    "load_snapshot",
    "normalize_license",
    "parse_expression",
    "parse_manifest",
    "write_inventory",
]
