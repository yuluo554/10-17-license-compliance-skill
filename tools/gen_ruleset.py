#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""规则包生成器：curated（人工核对表）+ SPDX 快照 → ``references/ruleset/``。

输入（唯一手写数据）：

- ``references/curated/tiers.json``     —— 档位 + 义务 + 条款锚点
- ``references/curated/trove-map.json``  —— trove classifier → SPDX ID
- ``references/curated/scenario-triggers.json``（M3 才有内容，可缺）
- ``references/curated/conflict-pairs.json``（M4 才有内容，可缺）
- ``references/curated/action-rules.json``（M5 才有内容，可缺）
- ``references/spdx/licenses.json`` / ``exceptions.json`` / ``texts/*.json``

输出：``references/ruleset/*.json`` + ``manifest.json``。

两道硬门：

1. **锚点必须可定位**：``anchor.ref`` 指向的 ``texts/<id>.json`` 中，``anchor.quote``
   必须真的出现在对应文本里（空白归一化后）。做不到 → 该条 ``verified=false``，不生效。
2. **义务项 / 档位 / ID 必须合法**：枚举来自 ``licaudit.contract``，ID 必须存在于 SPDX 快照。

``--check`` 两层：冻结产物形态正确 + 重生成到临时目录逐字节一致。

用法::

    py -3.12 -X utf8 tools/gen_ruleset.py
    py -3.12 -X utf8 tools/gen_ruleset.py --check
"""

import argparse
import io
import json
import os
import shutil
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from licaudit import contract  # noqa: E402
from licaudit.ruleset.loader import ALLOWED_RULE_FILES, sha256_file  # noqa: E402

CURATED_DIR = os.path.join(REPO_ROOT, "references", "curated")
SPDX_DIR = os.path.join(REPO_ROOT, "references", "spdx")
RULESET_DIR = os.path.join(REPO_ROOT, "references", "ruleset")

RULESET_VERSION = "r0.1.0"

VALID_TIERS = set(contract.TIERS)
VALID_OBLIGATIONS = set(contract.OBLIGATIONS)
VALID_ACTIONS = set(contract.ACTION_LEVELS)
VALID_RESOLUTIONS = set(contract.CONFLICT_RESOLUTIONS)
VALID_SCENARIOS = set(contract.SCENARIO_IDS)
VALID_LINK_MODES = set(contract.LINK_MODES)

CLASSIFIER_POLICY = "source"


# ---------------------------------------------------------------------------
# IO
# ---------------------------------------------------------------------------


def read_json(path):
    with io.open(path, "r", encoding="utf-8") as stream:
        return json.load(stream)


def dumps(payload):
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


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


# ---------------------------------------------------------------------------
# 锚点定位
# ---------------------------------------------------------------------------


def _normalize_ws(text):
    return " ".join(text.split())


class TextCache(object):
    def __init__(self, spdx_dir):
        self.spdx_dir = spdx_dir
        self._cache = {}

    def get(self, rel_ref):
        """``texts/MIT.json#licenseText`` → 文本；缺失返回 ``None``。"""
        path_part = rel_ref.split("#", 1)[0]
        if path_part not in self._cache:
            path = os.path.join(self.spdx_dir, path_part.replace("/", os.sep))
            if not os.path.isfile(path):
                self._cache[path_part] = None
            else:
                payload = read_json(path)
                text = payload.get("licenseText") or payload.get("licenseExceptionText")
                self._cache[path_part] = text
        return self._cache[path_part]

    def contains(self, ref, quote):
        text = self.get(ref)
        if not isinstance(text, str):
            return False
        if not isinstance(quote, str) or not quote.strip():
            return False
        return _normalize_ws(quote) in _normalize_ws(text)


def check_anchor(anchor, texts):
    """锚点是否可解析：结构齐全 + 引文能在原文中定位。"""
    if not isinstance(anchor, dict):
        return False, "anchor_missing"
    for key in ("source", "ref"):
        value = anchor.get(key)
        if not isinstance(value, str) or not value.strip():
            return False, "anchor_missing"
    quote = anchor.get("quote")
    if not isinstance(quote, str) or not quote.strip():
        return False, "anchor_quote_missing"
    if not texts.contains(anchor["ref"], quote):
        return False, "anchor_not_locatable"
    return True, ""


# ---------------------------------------------------------------------------
# 文档构建
# ---------------------------------------------------------------------------


def build_tiers(curated, licenses, texts, problems):
    entries = []
    covered = set()
    for index, entry in enumerate(curated.get("entries", [])):
        license_id = entry.get("license_id")
        if license_id not in licenses:
            problems.append("tiers[{0}] 的 license_id 不在 SPDX 清单中：{1}".format(index, license_id))
            continue
        tier = entry.get("tier")
        if tier not in VALID_TIERS:
            problems.append("tiers[{0}] 档位非法：{1}".format(license_id, tier))
            continue
        obligations = list(entry.get("obligations") or [])
        unknown = [item for item in obligations if item not in VALID_OBLIGATIONS]
        if unknown:
            problems.append("tiers[{0}] 义务项非法：{1}".format(license_id, unknown))
            continue

        verified, reason = check_anchor(entry.get("anchor"), texts)
        if not verified:
            problems.append("tiers[{0}] 锚点不可定位（{1}）".format(license_id, reason))

        entry_flags = []
        patent = entry.get("patent_clause") or {"present": False, "anchor": None}
        trademark = entry.get("trademark_clause") or {"present": False, "anchor": None}
        for label, clause in (("patent", patent), ("trademark", trademark)):
            if clause.get("present"):
                ok, why = check_anchor(clause.get("anchor"), texts)
                if not ok:
                    problems.append(
                        "tiers[{0}] 的 {1}_clause 锚点不可定位（{2}）".format(
                            license_id, label, why
                        )
                    )
                    clause = {"present": False, "anchor": None}
            if clause.get("present"):
                entry_flags.append(label)

        entries.append({
            "license_id": license_id,
            "tier": tier,
            "obligations": obligations,
            "patent_clause": patent,
            "trademark_clause": trademark,
            "anchor": entry.get("anchor"),
            "verified": bool(entry.get("verified")) and verified,
            "checked_on": entry.get("checked_on"),
        })
        covered.add(license_id)

    document = {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "entries": sorted(entries, key=lambda item: item["license_id"]),
    }
    return document, covered


def build_trove_map(curated, licenses, problems):
    entries = []
    for index, entry in enumerate(curated.get("entries", [])):
        classifier = entry.get("classifier")
        spdx_id = entry.get("spdx_id")
        if not isinstance(classifier, str) or not classifier.startswith("License ::"):
            problems.append("trove-map[{0}] classifier 形态非法".format(index))
            continue
        if spdx_id not in licenses:
            problems.append("trove-map[{0}] 的 spdx_id 不在 SPDX 清单中：{1}".format(index, spdx_id))
            continue
        source_url = entry.get("source_url")
        if not isinstance(source_url, str) or not source_url.strip():
            problems.append("trove-map[{0}] 缺少 source_url".format(index))
            continue
        if not entry.get("checked_on"):
            problems.append("trove-map[{0}] 缺少 checked_on".format(index))
            continue
        entries.append({
            "classifier": classifier,
            "spdx_id": spdx_id,
            "source_url": source_url,
            "checked_on": entry["checked_on"],
        })
    return {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "entries": sorted(entries, key=lambda item: item["classifier"]),
    }


def build_scenario_triggers(curated, problems):
    entries = []
    for index, entry in enumerate(curated.get("entries", [])):
        scenarios = entry.get("scenarios") or []
        bad = [item for item in scenarios if item not in VALID_SCENARIOS]
        if bad:
            problems.append("scenario-triggers[{0}] 场景非法：{1}".format(index, bad))
            continue
        link_modes = entry.get("link_modes") or []
        bad = [item for item in link_modes if item not in VALID_LINK_MODES]
        if bad:
            problems.append("scenario-triggers[{0}] 链接方式非法：{1}".format(index, bad))
            continue
        obligations = entry.get("obligations") or []
        bad = [item for item in obligations if item not in VALID_OBLIGATIONS]
        if bad:
            problems.append("scenario-triggers[{0}] 义务项非法：{1}".format(index, bad))
            continue
        entries.append(dict(entry))
    return {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "entries": entries,
    }


def build_conflict_pairs(curated, problems):
    entries = []
    seen = set()
    for index, entry in enumerate(curated.get("entries", [])):
        pair_id = entry.get("pair_id")
        if not pair_id or pair_id in seen:
            problems.append("conflict-pairs[{0}] pair_id 缺失或重复".format(index))
            continue
        seen.add(pair_id)
        if entry.get("resolution") not in VALID_RESOLUTIONS:
            problems.append("conflict-pairs[{0}] resolution 非法".format(pair_id))
            continue
        entries.append(dict(entry))
    return {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "entries": entries,
    }


def build_action_rules(curated, problems):
    entries = []
    for index, entry in enumerate(curated.get("entries", [])):
        if entry.get("level") not in VALID_ACTIONS:
            problems.append("action-rules[{0}] level 非法".format(index))
            continue
        entries.append(dict(entry))
    return {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "entries": entries,
    }


def build_obligations():
    labels = {
        "retain-copyright": "保留版权声明",
        "include-license-text": "附许可证全文",
        "mark-modifications": "标注修改",
        "provide-source": "提供对应源码",
        "network-source": "网络交互提供源码",
        "patent-grant": "专利授权",
        "trademark-restriction": "商标限制",
        "same-license": "同许可发布",
    }
    return {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "entries": [
            {"id": obligation, "label": labels[obligation]}
            for obligation in contract.OBLIGATIONS
        ],
    }


# ---------------------------------------------------------------------------
# 主流程
# ---------------------------------------------------------------------------


def load_inputs():
    licenses_payload = read_json(os.path.join(SPDX_DIR, "licenses.json"))
    exceptions_payload = read_json(os.path.join(SPDX_DIR, "exceptions.json"))
    licenses = {item["licenseId"]: item for item in licenses_payload["licenses"]}
    exceptions = {
        item["licenseExceptionId"]: item for item in exceptions_payload["exceptions"]
    }
    curated = {}
    for name in ("tiers", "trove-map", "scenario-triggers", "conflict-pairs",
                 "action-rules"):
        path = os.path.join(CURATED_DIR, name + ".json")
        curated[name] = read_json(path) if os.path.isfile(path) else {"entries": []}
    return licenses_payload, exceptions_payload, licenses, exceptions, curated


def generate(target_dir=None):
    """生成规则包到 ``target_dir``（默认仓库 ``references/ruleset``）。

    返回 ``(documents, manifest, problems)``。
    """
    target_dir = target_dir or RULESET_DIR
    licenses_payload, exceptions_payload, licenses, exceptions, curated = load_inputs()
    texts = TextCache(SPDX_DIR)
    problems = []

    documents = {}
    documents["tiers.json"], covered = build_tiers(curated["tiers"], licenses, texts, problems)
    documents["obligations.json"] = build_obligations()
    documents["trove-map.json"] = build_trove_map(curated["trove-map"], licenses, problems)
    documents["scenario-triggers.json"] = build_scenario_triggers(
        curated["scenario-triggers"], problems
    )
    documents["conflict-pairs.json"] = build_conflict_pairs(
        curated["conflict-pairs"], problems
    )
    documents["action-rules.json"] = build_action_rules(curated["action-rules"], problems)

    # 覆盖口径：总数与采样数双登记（plan/04 §3.3）
    total_ids = len(licenses)
    sampled = len(covered)
    documents["tiers.json"]["coverage"] = {
        "tiers_total_ids": total_ids,
        "tiers_sampled_ids": sampled,
        "note": "首期只覆盖清单实际出现的 SPDX ID；抽样覆盖，非全量穷举",
    }

    if not os.path.isdir(target_dir):
        os.makedirs(target_dir)

    files = {}
    for name in ALLOWED_RULE_FILES:
        if name not in documents:
            continue
        path = os.path.join(target_dir, name)
        write_text_atomic(path, dumps(documents[name]))
        files[name] = sha256_file(path)

    manifest = {
        "schema_version": 1,
        "ruleset_version": RULESET_VERSION,
        "license_list_version": licenses_payload.get("licenseListVersion"),
        "license_list_captured_on": _captured_on(),
        "ruleset_coverage": documents["tiers.json"]["coverage"],
        "files": files,
    }
    write_text_atomic(os.path.join(target_dir, "manifest.json"), dumps(manifest))
    return documents, manifest, problems


def _captured_on():
    path = os.path.join(SPDX_DIR, "manifest.json")
    if os.path.isfile(path):
        return read_json(path).get("captured_on")
    return None


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------


def check_against(target_dir=None):
    """两层校验：冻结产物形态 + 重生成逐字节一致。返回问题列表。"""
    target_dir = target_dir or RULESET_DIR
    problems = []

    manifest_path = os.path.join(target_dir, "manifest.json")
    if not os.path.isfile(manifest_path):
        return ["缺少 {0}".format(manifest_path)]

    frozen = read_json(manifest_path)
    if frozen.get("schema_version") != 1:
        problems.append("manifest.schema_version 不是 1")
    if frozen.get("ruleset_version") != RULESET_VERSION:
        problems.append("manifest.ruleset_version 与生成器常量不一致")
    if not frozen.get("license_list_version"):
        problems.append("manifest 缺少 license_list_version")
    declared = frozen.get("files") or {}
    for name in sorted(declared):
        if name not in ALLOWED_RULE_FILES:
            problems.append("manifest 登记了白名单外的文件：{0}".format(name))
            continue
        path = os.path.join(target_dir, name)
        if not os.path.isfile(path):
            problems.append("登记的文件不存在：{0}".format(name))
            continue
        if sha256_file(path) != declared[name]:
            problems.append("冻结产物哈希不符（被手改或生成器漂移）：{0}".format(name))

    temp_root = tempfile.mkdtemp(prefix="licaudit-ruleset-")
    try:
        _documents, _manifest, generation_problems = generate(temp_root)
        for problem in generation_problems:
            problems.append("生成期问题：" + problem)
        names = sorted(set(declared) | set(_manifest["files"]))
        for name in names:
            regenerated = os.path.join(temp_root, name)
            if not os.path.isfile(regenerated):
                problems.append("重生成缺少文件：{0}".format(name))
                continue
            existing = os.path.join(target_dir, name)
            if not os.path.isfile(existing):
                continue
            with io.open(existing, "rb") as stream:
                left = stream.read()
            with io.open(regenerated, "rb") as stream:
                right = stream.read()
            if left != right:
                problems.append(
                    "重生成结果与冻结产物不一致：{0}（首个差异偏移 {1}）".format(
                        name, _first_difference(left, right)
                    )
                )
        manifest_regenerated = os.path.join(temp_root, "manifest.json")
        if os.path.isfile(manifest_regenerated):
            with io.open(manifest_path, "rb") as stream:
                left = stream.read()
            with io.open(manifest_regenerated, "rb") as stream:
                right = stream.read()
            if left != right:
                problems.append("manifest.json 与重生成结果不一致")
    finally:
        shutil.rmtree(temp_root, ignore_errors=True)
    return problems


def _first_difference(left, right):
    limit = min(len(left), len(right))
    for index in range(limit):
        if left[index] != right[index]:
            return index
    return limit


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="gen_ruleset",
        description="由 curated 表 + SPDX 快照生成规则包（生成物禁手改）",
    )
    parser.add_argument("--check", action="store_true",
                        help="校验冻结产物（形态 + 重生成逐字节一致）")
    parser.add_argument("--out", default=RULESET_DIR, help="输出目录")
    args = parser.parse_args(argv)

    out_dir = os.path.abspath(args.out)

    if args.check:
        problems = check_against(out_dir)
        if problems:
            for problem in problems:
                sys.stdout.write("[FAIL] {0}\n".format(problem))
            return 1
        sys.stdout.write("[OK] 规则包与重生成结果逐字节一致：{0}\n".format(out_dir))
        return 0

    documents, manifest, problems = generate(out_dir)
    for problem in problems:
        sys.stdout.write("[WARN] {0}\n".format(problem))
    sys.stdout.write(
        "[OK] 规则包已生成：{0}；ruleset_version={1}；license_list_version={2}；"
        "tiers={3}/{4}\n".format(
            out_dir,
            manifest["ruleset_version"],
            manifest["license_list_version"],
            manifest["ruleset_coverage"]["tiers_sampled_ids"],
            manifest["ruleset_coverage"]["tiers_total_ids"],
        )
    )
    return 1 if any("非法" in problem or "不在 SPDX" in problem for problem in problems) else 0


if __name__ == "__main__":
    sys.exit(main())
