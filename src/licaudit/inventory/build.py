# -*- coding: utf-8 -*-
"""扫描编排：多清单 → ``inventory.json``（M1）。

边界：

- 单件失败隔离（K30）：一个文件/一条依赖失败 → 进 ``parse_notes``，整批继续；
  只有「整个输入不可用」（文件不存在、非 UTF-8、未知文件名、lockfileVersion 不支持）
  才抛 :class:`UsageError`（exit 2）。
- 每条记录必须挂 ``evidence.ruleset_version`` 与 ``evidence.details_url``；
  缺任一 → 该条不进 ``dependencies``，进 ``pending_confirmation``（plan/03 §1.6）。
- 纯函数：同输入同输出，双跑逐字节一致。
"""

import os

from .. import contract
from ..errors import UsageError
from ..serialize import write_json
from .manifests import parse_manifest
from .normalize import normalize_license
from .spdx_expr import SpdxIndex
from .spdx_snapshot import load_snapshot

__all__ = ["build_inventory", "write_inventory", "inventory_path"]


def _ordered_record(package, version, raw_license, spdx_id, confidence, evidence):
    return {
        "package": package,
        "version": version,
        "raw_license": raw_license,
        "spdx_id": spdx_id,
        "confidence": confidence,
        "evidence": evidence,
    }


def _evidence(source_file, locator, line, ruleset_version, details_url,
              matched_token, flags):
    return {
        "file": source_file,
        "locator": locator,
        "line": line,
        "ruleset_version": ruleset_version,
        "details_url": details_url,
        "matched_token": matched_token,
        "flags": list(flags),
    }


def build_inventory(paths, ruleset, spdx_dir=None):
    """返回 ``inventory.json`` 的字典形态（含 ``format`` / ``format_version``）。"""
    licenses_payload, exceptions_payload, snapshot_manifest = load_snapshot(spdx_dir)
    spdx_index = SpdxIndex(licenses_payload, exceptions_payload)

    trove_map = ruleset.entries("trove-map.json") if ruleset is not None else []
    ruleset_version = ruleset.version if ruleset is not None else None

    dependencies = []
    pending = []
    parse_notes = []
    source_files = []
    seen = {}

    for path in paths:
        absolute = os.path.abspath(path)
        parsed = None
        try:
            parsed = parse_manifest(path)
        except UsageError as exc:
            # 整个文件不可用：输入级错误，直接失败（不是「单件隔离」范围）
            raise exc
        source_files.append(parsed.name)

        for note in parsed.notes:
            parse_notes.append(note)

        for raw in parsed.records:
            normalized = normalize_license(
                raw.get("raw_license"),
                spdx_index,
                trove_classifiers=raw.get("classifiers"),
                trove_map=trove_map,
                structured=raw.get("structured", True),
            )
            details_url = normalized.details_urls[0] if normalized.details_urls else None
            version = raw.get("version") or "*"
            evidence = _evidence(
                source_file=raw.get("source_file") or parsed.name,
                locator=raw.get("locator"),
                line=raw.get("line"),
                ruleset_version=ruleset_version,
                details_url=details_url,
                matched_token=normalized.matched_token,
                flags=normalized.flags,
            )
            record = _ordered_record(
                raw.get("package"),
                version,
                normalized.raw_license,
                normalized.spdx_id,
                normalized.confidence,
                evidence,
            )

            missing = []
            if not evidence["ruleset_version"]:
                missing.append("evidence.ruleset_version")
            # plan/03 §1.6：缺 ruleset_version 或 details_url 的记录不落 dependencies。
            # 截断兜底（spdx_id 为 null）与 <族>-unknown 没有可指向的 SPDX 原文，
            # 因此也不伪造 URL —— 它们只出现在 pending_confirmation 里。
            if not evidence["details_url"]:
                missing.append("evidence.details_url")
            if not record["package"]:
                missing.append("package")

            if missing:
                pending.append({
                    "record": record,
                    "missing": missing,
                    "reason": "evidence_incomplete",
                })
                continue

            key = (record["package"], record["version"], raw.get("source_file") or parsed.name)
            if key in seen:
                parse_notes.append({
                    "code": "duplicate_dependency",
                    "message": "同一文件内重复声明，保留首次出现",
                    "file": raw.get("source_file") or parsed.name,
                    "line": raw.get("line"),
                })
                continue
            seen[key] = True

            if normalized.needs_confirmation:
                pending.append({
                    "record": record,
                    "missing": [],
                    "reason": "needs_confirmation",
                })
            dependencies.append(record)

    payload = {
        "format": contract.INVENTORY_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "license_list_version": snapshot_manifest.get("license_list_version")
        or licenses_payload.get("licenseListVersion"),
        "ruleset_version": ruleset_version,
        "source_files": source_files,
        "dependencies": dependencies,
        "pending_confirmation": pending,
        "parse_notes": parse_notes,
    }
    return payload


def inventory_path(out_dir):
    return os.path.join(out_dir, "inventory.json")


def write_inventory(payload, out_dir):
    write_json(inventory_path(out_dir), payload)
    return inventory_path(out_dir)
