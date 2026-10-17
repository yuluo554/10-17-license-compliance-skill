# -*- coding: utf-8 -*-
"""测试辅助：让 ``src`` 可导入，并提供临时规则包构造器。"""

import io
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

__all__ = ["REPO_ROOT", "SRC", "make_ruleset_dir", "write_json"]


def write_json(path, payload):
    with io.open(path, "w", encoding="utf-8", newline="\n") as stream:
        stream.write(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False))
        stream.write("\n")


def make_ruleset_dir(root, complete=True, bad_hash=False):
    """在 ``root`` 下造一个最小但合法的规则包。

    ``complete=False`` 时只写 manifest 与一个文件，用于制造「缺文件」场景。
    ``bad_hash=True`` 时写入与 manifest 不符的哈希，用于制造「文件被手改」场景。
    """
    from licaudit.ruleset.loader import sha256_file

    os.makedirs(root, exist_ok=True)

    documents = {
        "tiers.json": {
            "schema_version": 1,
            "entries": [
                {
                    "license_id": "MIT",
                    "tier": "permissive",
                    "obligations": ["retain-copyright", "include-license-text"],
                    "anchor": {"source": "spdx-license-text", "ref": "MIT.json#licenseText"},
                    "verified": True,
                    "checked_on": "2026-10-17",
                }
            ],
        },
        "obligations.json": {
            "schema_version": 1,
            "entries": [
                {"id": "retain-copyright", "label": "保留版权声明"},
                {"id": "include-license-text", "label": "附许可证全文"},
            ],
        },
        "scenario-triggers.json": {
            "schema_version": 1,
            "entries": [
                {
                    "id": "T-NET-001",
                    "tier": "network-copyleft",
                    "scenarios": ["saas"],
                    "link_modes": ["none"],
                    "network_interaction": True,
                    "trigger": "network-interaction",
                    "obligations": ["network-source"],
                    "anchor": {"source": "agpl-3.0", "ref": "§13"},
                    "verified": True,
                    "checked_on": "2026-10-17",
                }
            ],
        },
        "conflict-pairs.json": {
            "schema_version": 1,
            "entries": [
                {
                    "pair_id": "CP-GPL2-APACHE2",
                    "left": "GPL-2.0-only",
                    "right": "Apache-2.0",
                    "resolution": "incompatible",
                    "basis": "Apache-2.0 的附加条款构成 GPLv2 不允许的额外限制",
                    "anchor": {"source": "license-text", "ref": "Apache-2.0.json#licenseText"},
                    "verified": True,
                    "checked_on": "2026-10-17",
                }
            ],
        },
        "action-rules.json": {
            "schema_version": 1,
            "entries": [
                {
                    "id": "A-DECLARE-001",
                    "from_obligations": ["retain-copyright"],
                    "level": "declare",
                    "anchor": {"source": "license-text", "ref": "MIT.json#licenseText"},
                    "verified": True,
                    "checked_on": "2026-10-17",
                }
            ],
        },
        "trove-map.json": {
            "schema_version": 1,
            "entries": [
                {
                    "classifier": "License :: OSI Approved :: MIT License",
                    "spdx_id": "MIT",
                    "source_url": "https://spdx.org/licenses/MIT.json",
                    "checked_on": "2026-10-17",
                }
            ],
        },
    }

    if not complete:
        documents = {"tiers.json": documents["tiers.json"]}

    files = {}
    for name, payload in documents.items():
        path = os.path.join(root, name)
        write_json(path, payload)
        files[name] = sha256_file(path)

    if bad_hash:
        files["tiers.json"] = "0" * 64

    manifest = {
        "schema_version": 1,
        "ruleset_version": "r0.1.0-test",
        "license_list_version": "3.29.0",
        "files": files,
    }
    write_json(os.path.join(root, "manifest.json"), manifest)
    return root
