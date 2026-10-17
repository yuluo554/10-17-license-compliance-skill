#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""画像真值生成器（M2）：``references/curated/tiers.json`` → ``data/truth/profile.json``。

纪律（plan/04 §5.2 / K26）：

- 真值是**规则表的投影**，不是引擎输出回填。本脚本不 import 生产画像引擎。
- 只存输入与期望：输入是 SPDX ID 清单与数据版本，期望是档位 / 义务 / 状态 / 条款。
- 判断「规则是否生效」用一份**独立的朴素锚点校验**（空白归一化后逐字包含），
  与 ``tools/gen_ruleset.py`` 的实现分写，避免同一份代码自证。
- ``--check`` 两层：冻结产物形态正确 + 重生成逐字节一致。

用法::

    py -3.12 -X utf8 tools/gen_profile_truth.py
    py -3.12 -X utf8 tools/gen_profile_truth.py --check
"""

import argparse
import io
import json
import os
import sys
import tempfile

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO_ROOT, "src")
if SRC not in sys.path:
    sys.path.insert(0, SRC)

from licaudit import contract  # noqa: E402

CURATED_DIR = os.path.join(REPO_ROOT, "references", "curated")
SPDX_DIR = os.path.join(REPO_ROOT, "references", "spdx")
DATA_DIR = os.path.join(REPO_ROOT, "data")
TRUTH_FILE = os.path.join(DATA_DIR, "truth", "profile.json")

TRUTH_FORMAT = "licaudit-profile-truth"

# 真值必须同时覆盖「规则表覆盖」与「不覆盖」两侧，否则 ``tier: null`` 分支无人守。
NOT_COVERED_IDS = (
    "BlueOak-1.0.0",
    "CC-BY-4.0",
)

# ``<族>-unknown`` 是解析器造的 ID，**本来就不在 SPDX 清单里**（K3）：
# 画像必须同时表现为「无档位」+「OSI/FSF 未知」+ 待确认。
UNKNOWN_FAMILY_IDS = (
    "GPL-unknown",
    "LGPL-unknown",
)

CLAUSE_FIELDS = ("patent_clause", "trademark_clause")


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
# 独立朴素判定
# ---------------------------------------------------------------------------


def flatten_ws(text):
    return " ".join(text.split())


def quote_is_locatable(spdx_root, reference, quote):
    """朴素锚点校验：``texts/X.json`` 的正文里能不能找到这句话。"""
    if not isinstance(reference, str) or "#" not in reference:
        return False
    if not isinstance(quote, str) or not quote.strip():
        return False
    relative = reference.split("#", 1)[0]
    path = os.path.join(spdx_root, relative.replace("/", os.sep))
    if not os.path.isfile(path):
        return False
    payload = read_json(path)
    text = payload.get("licenseText") or payload.get("licenseExceptionText") or ""
    return flatten_ws(quote) in flatten_ws(text)


def rule_status(entry, spdx_root, known_ids):
    """仿 ``gen_ruleset`` 的收录规则，返回 ``covered`` / ``disabled`` / ``absent``。

    - ``absent``：ID 不在 SPDX 快照、档位或义务项非法 —— 生成器根本不会收录该条；
    - ``disabled``：收录了，但 ``verified`` 不为真或锚点不可定位 —— loader 会拒进 disabled；
    - ``covered``：收录且可用。

    与 :func:`gen_ruleset.build_tiers` 的口径一致，但锚点校验用本文件的朴素实现，
    不复用生产侧代码。
    """
    license_id = entry.get("license_id")
    if license_id not in known_ids:
        return "absent"
    if entry.get("tier") not in contract.TIERS:
        return "absent"
    for obligation in entry.get("obligations") or []:
        if obligation not in contract.OBLIGATIONS:
            return "absent"
    if entry.get("verified") is not True:
        return "disabled"
    if not entry.get("checked_on"):
        # loader 的硬门之一（checked_on_missing）；画像与真值必须同口径。
        return "disabled"
    anchor = entry.get("anchor") or {}
    if not quote_is_locatable(spdx_root, anchor.get("ref"), anchor.get("quote")):
        return "disabled"
    return "covered"


def canonical_obligations(obligations):
    """按 ``contract.OBLIGATIONS`` 顺序输出；真值必须与引擎同序。"""
    wanted = set(obligations or [])
    return [item for item in contract.OBLIGATIONS if item in wanted]


def clause_expectation(clause, spdx_root):
    """条款三元组 → 真值形态 ``present``；``present`` 为真时要求锚点可定位。"""
    if not isinstance(clause, dict) or not clause.get("present"):
        return False
    anchor = clause.get("anchor") or {}
    if not quote_is_locatable(spdx_root, anchor.get("ref"), anchor.get("quote")):
        return False
    return True


# ---------------------------------------------------------------------------
# 真值构建
# ---------------------------------------------------------------------------


def build_truth():
    curated = read_json(os.path.join(CURATED_DIR, "tiers.json"))
    licenses = read_json(os.path.join(SPDX_DIR, "licenses.json"))
    snapshot_manifest_path = os.path.join(SPDX_DIR, "manifest.json")
    snapshot_manifest = (
        read_json(snapshot_manifest_path) if os.path.isfile(snapshot_manifest_path) else {}
    )
    by_id = {item["licenseId"]: item for item in licenses.get("licenses", [])}
    known_ids = set(by_id)

    covered = []
    disabled = []
    for entry in curated.get("entries", []):
        license_id = entry.get("license_id")
        status = rule_status(entry, SPDX_DIR, known_ids)
        if status == "disabled":
            # 规则表里存在但 loader 会拒：画像与 loader 同口径 → tier: null + 待确认。
            disabled.append({"spdx_id": license_id, "reasons": ["rule_disabled"]})
            continue
        if status == "absent":
            # 生成器不会收录该条，等价于「未覆盖」。
            disabled.append({"spdx_id": license_id, "reasons": ["tier_uncovered"]})
            continue
        snapshot = by_id[license_id]
        covered.append({
            "spdx_id": license_id,
            "tier": entry["tier"],
            "obligations": canonical_obligations(entry.get("obligations")),
            "is_osi_approved": snapshot.get("isOsiApproved"),
            "is_fsf_libre": snapshot.get("isFsfLibre"),
            "patent_clause_present": clause_expectation(entry.get("patent_clause"), SPDX_DIR),
            "trademark_clause_present": clause_expectation(
                entry.get("trademark_clause"), SPDX_DIR
            ),
        })

    pending = []
    for license_id in NOT_COVERED_IDS:
        if license_id not in known_ids:
            raise SystemExit(
                "真值声明的未覆盖 ID 不在 SPDX 快照中：{0}".format(license_id)
            )
        if license_id in {item["spdx_id"] for item in covered}:
            raise SystemExit("真值自相矛盾：{0} 既覆盖又未覆盖".format(license_id))
        pending.append({"spdx_id": license_id, "reasons": ["tier_uncovered"]})

    for license_id in UNKNOWN_FAMILY_IDS:
        if license_id in known_ids:
            raise SystemExit(
                "<族>-unknown 不应出现在 SPDX 清单里：{0}".format(license_id)
            )
        pending.append({"spdx_id": license_id, "reasons": ["tier_uncovered", "unknown_family"]})

    pending.extend(disabled)
    pending.sort(key=lambda item: item["spdx_id"])
    profile_items = sorted(covered, key=lambda item: item["spdx_id"])
    inputs = [item["spdx_id"] for item in profile_items] + [
        item["spdx_id"] for item in pending
    ]
    return {
        "format": TRUTH_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "inputs": {
            "spdx_ids": sorted(inputs),
            "ruleset_source": "references/curated/tiers.json",
            "license_list_version": licenses.get("licenseListVersion"),
            "captured_on": snapshot_manifest.get("captured_on"),
        },
        "expect": {
            "profiles": profile_items,
            "pending": pending,
        },
    }


# ---------------------------------------------------------------------------
# --check
# ---------------------------------------------------------------------------


def check_against(path=None):
    path = path or TRUTH_FILE
    problems = []
    if not os.path.isfile(path):
        return ["缺少 {0}".format(path)]

    frozen = read_json(path)
    if frozen.get("format") != TRUTH_FORMAT:
        problems.append("format 不是 {0}".format(TRUTH_FORMAT))
    if frozen.get("format_version") != contract.FORMAT_VERSION:
        problems.append("format_version 与 contract.FORMAT_VERSION 不一致")
    inputs = frozen.get("inputs") or {}
    if not inputs.get("spdx_ids"):
        problems.append("缺少 inputs.spdx_ids（真值必须登记输入）")
    expect = frozen.get("expect") or {}
    if not expect.get("profiles"):
        problems.append("缺少 expect.profiles")
    if not expect.get("pending"):
        problems.append("缺少 expect.pending（tier: null 分支无人守）")

    text = io.open(path, encoding="utf-8").read()
    if "observed_" in text:
        problems.append("真值出现观测字段 observed_*（K26）")

    regenerated = dumps(build_truth())
    if text != regenerated:
        problems.append("重生成结果与冻结真值不一致（首个差异偏移 {0}）".format(
            _first_difference(text, regenerated)
        ))
    return problems


def _first_difference(left, right):
    limit = min(len(left), len(right))
    for index in range(limit):
        if left[index] != right[index]:
            return index
    return limit


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="gen_profile_truth",
        description="由 curated 规则表推导 M2 画像真值（禁手改）",
    )
    parser.add_argument("--check", action="store_true",
                        help="校验冻结真值（形态 + 重生成逐字节一致）")
    parser.add_argument("--out", default=TRUTH_FILE, help="输出文件")
    args = parser.parse_args(argv)

    target = os.path.abspath(args.out)

    if args.check:
        problems = check_against(target)
        if problems:
            for problem in problems:
                sys.stdout.write("[FAIL] {0}\n".format(problem))
            return 1
        sys.stdout.write("[OK] 画像真值与重生成结果逐字节一致：{0}\n".format(target))
        return 0

    payload = build_truth()
    write_text_atomic(target, dumps(payload))
    sys.stdout.write(
        "[OK] 画像真值已生成：{0}；输入 {1} 个 ID；覆盖 {2} / 待确认 {3}\n".format(
            target,
            len(payload["inputs"]["spdx_ids"]),
            len(payload["expect"]["profiles"]),
            len(payload["expect"]["pending"]),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
