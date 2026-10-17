#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""抓取并冻结 SPDX 许可证清单快照（人工步骤，不在运行时执行）。

纪律（plan/04 §二）：
- 只抓 ``licenses.json`` / ``exceptions.json`` 与规则包实际引用到的许可证全文；
- 失败重试 ≤3 次；任一请求失败 → 中止且**不写半份文件**（全部在内存中就绪后才落盘）；
- ``captured_on`` 是 UTC 日期（不带时刻）；``license_list_version`` 以响应为准，不照抄常量；
- 快照统一 ``ensure_ascii=False`` + ``indent=2`` + ``sort_keys=True`` + LF + 结尾换行，
  只为稳定 diff；外部数据本身不排序会导致每次重抓字节漂移。
- ``--check`` 不联网：只校验已冻结快照的形态与 sha256。

用法::

    py -3.12 -X utf8 tools/fetch_spdx.py --out references/spdx
    py -3.12 -X utf8 tools/fetch_spdx.py --check --out references/spdx
"""

import argparse
import datetime
import hashlib
import io
import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request

BASE_URL = "https://spdx.org/licenses/"
LIST_FILES = ("licenses.json", "exceptions.json")
TEXT_URL = BASE_URL + "{0}.json"
RETRY_LIMIT = 3
TIMEOUT_SECONDS = 30
USER_AGENT = "licaudit-fetch-spdx/0.1 (+https://github.com/yuluo554)"
MANIFEST_NAME = "manifest.json"

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


# ---------------------------------------------------------------------------
# 序列化（工具侧独立实现：不 import 引擎，避免生成器被运行时契约反绑）
# ---------------------------------------------------------------------------


def dumps_sorted(payload):
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)
    return text + "\n"


def dumps_ordered(payload):
    text = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=False)
    return text + "\n"


def write_text_atomic(path, text):
    directory = os.path.dirname(os.path.abspath(path))
    if directory and not os.path.isdir(directory):
        os.makedirs(directory)
    handle, tmp_path = tempfile.mkstemp(prefix=".licaudit-", suffix=".tmp", dir=directory)
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


def sha256_bytes(payload):
    return hashlib.sha256(payload).hexdigest()


def sha256_file(path):
    digest = hashlib.sha256()
    with io.open(path, "rb") as stream:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# 抓取
# ---------------------------------------------------------------------------


class FetchError(Exception):
    pass


def http_get(url):
    """带重试的 GET；返回 ``(status, body_bytes)``。"""
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    last_error = None
    for attempt in range(1, RETRY_LIMIT + 1):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                status = getattr(response, "status", None) or response.getcode()
                body = response.read()
                if status != 200:
                    raise FetchError("HTTP {0}".format(status))
                if not body:
                    raise FetchError("空响应")
                return status, body
        except (urllib.error.URLError, urllib.error.HTTPError, OSError, FetchError) as exc:
            last_error = exc
            if attempt < RETRY_LIMIT:
                time.sleep(1.0 * attempt)
    raise FetchError("重试 {0} 次仍失败：{1} ({2})".format(RETRY_LIMIT, url, last_error))


def parse_json(body, what):
    try:
        return json.loads(body.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise FetchError("{0} 不是合法 UTF-8 JSON：{1}".format(what, exc))


def text_ids_from_curated(curated_dir):
    """从 curated 表推导需要抓全文的许可证 / 例外 ID。

    取 tiers 的 ``license_id``、trove-map 的 ``spdx_id``、以及冲突对的首尾 ID；
    ``WITH`` 例外由 tiers 条目的 ``exceptions`` 字段显式声明（没有则不抓）。
    """
    ids = set()
    exceptions = set()

    def _load(name):
        path = os.path.join(curated_dir, name)
        if not os.path.isfile(path):
            return None
        with io.open(path, "r", encoding="utf-8") as stream:
            return json.load(stream)

    tiers = _load("tiers.json")
    if tiers:
        for entry in tiers.get("entries", []):
            if entry.get("license_id"):
                ids.add(entry["license_id"])
            for exception_id in entry.get("exceptions", []):
                exceptions.add(exception_id)

    trove = _load("trove-map.json")
    if trove:
        for entry in trove.get("entries", []):
            if entry.get("spdx_id"):
                ids.add(entry["spdx_id"])

    conflicts = _load("conflict-pairs.json")
    if conflicts:
        for entry in conflicts.get("entries", []):
            for key in ("left", "right"):
                if entry.get(key):
                    ids.add(entry[key])

    return sorted(ids), sorted(exceptions)


def build_snapshot(out_dir):
    """抓取全部数据，返回 ``(files, manifest)``；不写盘。"""
    captured_on = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    curated_dir = os.path.join(REPO_ROOT, "references", "curated")
    text_ids, exception_text_ids = text_ids_from_curated(curated_dir)

    files = {}
    entries = {}

    for name in LIST_FILES:
        url = BASE_URL + name
        status, body = http_get(url)
        payload = parse_json(body, name)
        text = dumps_sorted(payload)
        encoded = text.encode("utf-8")
        files[name] = text
        entries[name] = {
            "url": url,
            "http_status": status,
            "download_bytes": len(body),
            "snapshot_bytes": len(encoded),
            "sha256": sha256_bytes(encoded),
            "captured_on": captured_on,
        }

    licenses = parse_json(files["licenses.json"].encode("utf-8"), "licenses.json")
    exceptions = parse_json(files["exceptions.json"].encode("utf-8"), "exceptions.json")
    license_version = licenses.get("licenseListVersion")
    exception_version = exceptions.get("licenseListVersion")
    if not license_version:
        raise FetchError("licenses.json 缺少 licenseListVersion")
    if not exception_version:
        raise FetchError("exceptions.json 缺少 licenseListVersion")
    if license_version != exception_version:
        raise FetchError(
            "两份清单版本不一致：licenses={0} exceptions={1}".format(
                license_version, exception_version
            )
        )

    known_licenses = set(item.get("licenseId") for item in licenses.get("licenses", []))
    known_exceptions = set(
        item.get("licenseExceptionId") for item in exceptions.get("exceptions", [])
    )

    missing = [license_id for license_id in text_ids if license_id not in known_licenses]
    if missing:
        raise FetchError("curated 引用了清单中不存在的许可证 ID：{0}".format(", ".join(missing)))
    missing = [
        exception_id
        for exception_id in exception_text_ids
        if exception_id not in known_exceptions
    ]
    if missing:
        raise FetchError("curated 引用了清单中不存在的例外 ID：{0}".format(", ".join(missing)))

    for license_id in text_ids:
        url = TEXT_URL.format(license_id)
        status, body = http_get(url)
        payload = parse_json(body, license_id + ".json")
        if payload.get("licenseId") != license_id:
            raise FetchError(
                "全文响应的 licenseId 与请求不一致：{0} != {1}".format(
                    payload.get("licenseId"), license_id
                )
            )
        text = dumps_sorted(payload)
        encoded = text.encode("utf-8")
        rel = "texts/{0}.json".format(license_id)
        files[rel] = text
        entries[rel] = {
            "url": url,
            "http_status": status,
            "download_bytes": len(body),
            "snapshot_bytes": len(encoded),
            "sha256": sha256_bytes(encoded),
            "captured_on": captured_on,
        }

    for exception_id in exception_text_ids:
        url = TEXT_URL.format(exception_id)
        status, body = http_get(url)
        payload = parse_json(body, exception_id + ".json")
        if payload.get("licenseExceptionId") != exception_id:
            raise FetchError(
                "例外全文响应的 licenseExceptionId 与请求不一致：{0} != {1}".format(
                    payload.get("licenseExceptionId"), exception_id
                )
            )
        text = dumps_sorted(payload)
        encoded = text.encode("utf-8")
        rel = "texts/{0}.json".format(exception_id)
        files[rel] = text
        entries[rel] = {
            "url": url,
            "http_status": status,
            "download_bytes": len(body),
            "snapshot_bytes": len(encoded),
            "sha256": sha256_bytes(encoded),
            "captured_on": captured_on,
        }

    manifest = {
        "format": "licaudit-spdx-snapshot",
        "format_version": 1,
        "license_list_version": license_version,
        "captured_on": captured_on,
        "license_total_ids": len(known_licenses),
        "exception_total_ids": len(known_exceptions),
        "text_ids": text_ids,
        "exception_text_ids": exception_text_ids,
        "files": entries,
    }
    return files, manifest


def write_snapshot(out_dir, files, manifest):
    """先写全部数据文件，最后写 manifest；manifest 是「快照已完整」的标志。"""
    if not os.path.isdir(out_dir):
        os.makedirs(out_dir)
    for rel in sorted(files):
        write_text_atomic(os.path.join(out_dir, rel), files[rel])
    write_text_atomic(
        os.path.join(out_dir, MANIFEST_NAME), dumps_ordered(manifest)
    )


# ---------------------------------------------------------------------------
# 离线校验
# ---------------------------------------------------------------------------


def check_snapshot(out_dir):
    """不联网校验冻结快照；返回问题列表。"""
    problems = []
    manifest_path = os.path.join(out_dir, MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        return ["缺少 {0}".format(MANIFEST_NAME)]
    try:
        with io.open(manifest_path, "r", encoding="utf-8") as stream:
            manifest = json.load(stream)
    except (OSError, UnicodeDecodeError, ValueError) as exc:
        return ["manifest.json 不可读：{0}".format(exc)]

    if manifest.get("format") != "licaudit-spdx-snapshot":
        problems.append("manifest format 不是 licaudit-spdx-snapshot")
    if manifest.get("format_version") != 1:
        problems.append("manifest format_version 不是 1")
    if not manifest.get("license_list_version"):
        problems.append("manifest 缺少 license_list_version")
    if not manifest.get("captured_on"):
        problems.append("manifest 缺少 captured_on")

    declared = manifest.get("files")
    if not isinstance(declared, dict) or not declared:
        return problems + ["manifest 缺少 files 清单"]

    for rel in sorted(declared):
        path = os.path.join(out_dir, rel.replace("/", os.sep))
        if not os.path.isfile(path):
            problems.append("登记的文件不存在：{0}".format(rel))
            continue
        actual = sha256_file(path)
        expected = declared[rel].get("sha256")
        if actual != expected:
            problems.append("sha256 不一致：{0}".format(rel))

    for name in LIST_FILES:
        if name not in declared:
            problems.append("缺少清单快照：{0}".format(name))
            continue
        with io.open(os.path.join(out_dir, name), "r", encoding="utf-8") as stream:
            payload = json.load(stream)
        version = payload.get("licenseListVersion")
        if version != manifest.get("license_list_version"):
            problems.append(
                "licenseListVersion 漂移：{0} 内为 {1}，manifest 为 {2}".format(
                    name, version, manifest.get("license_list_version")
                )
            )

    declared_texts = sorted(rel for rel in declared if rel.startswith("texts/"))
    if declared_texts != sorted(
        ["texts/{0}.json".format(item) for item in manifest.get("text_ids", [])]
        + ["texts/{0}.json".format(item) for item in manifest.get("exception_text_ids", [])]
    ):
        problems.append("manifest 的 text_ids 与实际登记全文不一致")

    return problems


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="fetch_spdx",
        description="抓取并冻结 SPDX 清单快照（人工步骤；运行时零网络）",
    )
    parser.add_argument("--out", default=os.path.join("references", "spdx"), help="输出目录")
    parser.add_argument(
        "--check",
        action="store_true",
        help="离线校验已冻结快照（不联网、不写盘）；不一致 exit 1",
    )
    args = parser.parse_args(argv)

    out_dir = os.path.abspath(args.out)

    if args.check:
        problems = check_snapshot(out_dir)
        if problems:
            for problem in problems:
                sys.stdout.write("[FAIL] {0}\n".format(problem))
            return 1
        sys.stdout.write("[OK] SPDX 快照完整：{0}\n".format(out_dir))
        return 0

    try:
        files, manifest = build_snapshot(out_dir)
    except FetchError as exc:
        sys.stderr.write("抓取失败（未写入任何文件）：{0}\n".format(exc))
        return 1

    write_snapshot(out_dir, files, manifest)
    sys.stdout.write(
        "[OK] SPDX {0}；{1} 个文件；license_list_version={2}；captured_on={3}\n".format(
            out_dir,
            len(files),
            manifest["license_list_version"],
            manifest["captured_on"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
