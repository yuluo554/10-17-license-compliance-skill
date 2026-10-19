# -*- coding: utf-8 -*-
"""SPDX 冻结快照的只读装载。

快照随仓库冻结（``references/spdx/``），运行时**不联网**；缺失或形态不对 →
:class:`UsageError`（exit 2，输入不可用），而不是静默降级成"没覆盖"。
"""

import io
import json
import os

from ..errors import UsageError

LICENSES_FILE = "licenses.json"
EXCEPTIONS_FILE = "exceptions.json"
MANIFEST_FILE = "manifest.json"


def default_spdx_dir():
    """SPDX 快照目录：源码态取仓库根，安装态取 site-packages（见 loader.resource_roots）。

    阶段三实测坑：只按「打包文件位置」上溯三级在安装态会得到 ``<venv>/Lib``，
    于是 `licaudit assess` 报「SPDX 快照不可读」——随包资源必须两处都找。
    """
    from ..ruleset.loader import resource_roots

    roots = resource_roots()
    for root in roots:
        candidate = os.path.join(root, "references", "spdx")
        if os.path.isdir(candidate):
            return candidate
    return os.path.join(roots[0], "references", "spdx")


def _read_json(path, what):
    try:
        with io.open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)
    except OSError as exc:
        raise UsageError(
            "SPDX 快照不可读，请先运行 tools/fetch_spdx.py",
            file=what,
            reason=str(exc),
        )
    except (UnicodeDecodeError, ValueError) as exc:
        raise UsageError("SPDX 快照不是合法 UTF-8 JSON", file=what, reason=str(exc))


def load_snapshot(spdx_dir=None):
    """返回 ``(licenses_payload, exceptions_payload, manifest)``。"""
    root = os.path.abspath(spdx_dir or default_spdx_dir())
    licenses = _read_json(os.path.join(root, LICENSES_FILE), LICENSES_FILE)
    exceptions = _read_json(os.path.join(root, EXCEPTIONS_FILE), EXCEPTIONS_FILE)

    if not isinstance(licenses, dict) or not isinstance(licenses.get("licenses"), list):
        raise UsageError("licenses.json 缺少 licenses 数组", path=root)
    if not isinstance(exceptions, dict) or not isinstance(exceptions.get("exceptions"), list):
        raise UsageError("exceptions.json 缺少 exceptions 数组", path=root)

    license_version = licenses.get("licenseListVersion")
    exception_version = exceptions.get("licenseListVersion")
    if not license_version:
        raise UsageError("licenses.json 缺少 licenseListVersion", path=root)
    if license_version != exception_version:
        raise UsageError(
            "SPDX 快照版本不一致",
            licenses=license_version,
            exceptions=exception_version,
        )

    manifest_path = os.path.join(root, MANIFEST_FILE)
    manifest = {}
    if os.path.isfile(manifest_path):
        manifest = _read_json(manifest_path, MANIFEST_FILE)
        declared = manifest.get("license_list_version")
        if declared and declared != license_version:
            raise UsageError(
                "快照 manifest 与数据版本不一致（可能是手改或半份抓取）",
                manifest=declared,
                data=license_version,
            )
    return licenses, exceptions, manifest


__all__ = ["default_spdx_dir", "load_snapshot"]
