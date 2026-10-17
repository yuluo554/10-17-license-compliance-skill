#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""冲突真值生成器（M4）：``references/curated/conflict-pairs.json`` → ``data/truth/conflicts.json``。

纪律（plan/04 §5.2 / K26）：

- 真值是**规则表的投影**，不是引擎输出回填。本脚本不 import 生产冲突引擎
  （``licaudit.assess.conflict``），也不 import 生产画像引擎。
- 只存输入与期望：输入是许可证集合、待求值的表达式清单与 ``outbound = pending``；
  期望是「已知冲突对全命中」「未登记组合」「``OR``/``AND`` 求值结果」「待定文案」。
- 表达式求值用本文件内的**独立朴素实现**（自带迷你文法解析器 + ``contract.TIER_RANK``
  排序），与引擎走 ``licaudit.inventory.spdx_expr`` 的 AST 分写，避免同一份代码自证。
- 期望记录里**不含**引擎生成的中文 ``reason`` 文案（那是表达方式，不是判定）；
  比对只落在可机检字段（operator / atoms / selected / tier / resolved / exceptions）。
- 三侧覆盖：① 已知冲突对全命中（含 ``GPL-2.0-only × Apache-2.0``）；
  ② ``OR`` 最宽松 / ``AND`` 最严格（含嵌套与 ``WITH``）；③ ``outbound = pending`` → 全部待定。
- ``--check`` 两层：冻结产物形态正确 + 重生成逐字节一致。

用法::

    py -3.12 -X utf8 tools/gen_conflict_truth.py
    py -3.12 -X utf8 tools/gen_conflict_truth.py --check
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
TRUTH_FILE = os.path.join(DATA_DIR, "truth", "conflicts.json")

TRUTH_FORMAT = "licaudit-conflicts-truth"

OUTBOUND_PENDING_VALUE = "pending"
# 与 ``assess/conflict.py`` 的 BASIS_OUTBOUND_PENDING 同文案；真值独立登记，
# 引擎若改文案而真值不改，``bench m4`` 会红。
OUTBOUND_PENDING_BASIS = "项目自身许可证待定"

# 待求值的表达式清单（输入，不是期望）。覆盖 OR / AND / 嵌套 / WITH / 未覆盖档位。
EVALUATION_EXPRESSIONS = (
    "MIT OR GPL-3.0-only",
    "GPL-2.0-only AND MIT",
    "(MIT OR Apache-2.0) AND GPL-3.0-only",
    "GPL-2.0-only OR AGPL-3.0-only",
    "MIT OR (GPL-2.0-only WITH Classpath-exception-2.0)",
    "MIT OR BlueOak-1.0.0",
)

# 真值必须有一个「档位未覆盖」的原子，否则 ``resolved = false`` 分支无人守。
UNCOVERED_ATOM = "BlueOak-1.0.0"


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
# 独立朴素的档位表与锚点校验
# ---------------------------------------------------------------------------


def flatten_ws(text):
    return " ".join(text.split())


def quote_is_locatable(spdx_root, reference, quote):
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


def tier_by_atom(curated_tiers, spdx_root, known_ids):
    """curated 档位表 → ``{license_id: tier}``；只收可用条目（与 loader 同口径的朴素版）。"""
    tiers = {}
    for entry in curated_tiers.get("entries", []):
        license_id = entry.get("license_id")
        if license_id not in known_ids:
            continue
        if entry.get("tier") not in contract.TIERS:
            continue
        if any(item not in contract.OBLIGATIONS for item in entry.get("obligations") or []):
            continue
        if entry.get("verified") is not True or not entry.get("checked_on"):
            continue
        anchor = entry.get("anchor") or {}
        if not quote_is_locatable(spdx_root, anchor.get("ref"), anchor.get("quote")):
            continue
        tiers[license_id] = entry["tier"]
    return tiers


def usable_pairs(curated, spdx_root, known_ids):
    """冲突对表里可用条目（``--check`` 与真值同口径）。返回 ``(usable, dropped)``。"""
    usable = []
    dropped = []
    for entry in curated.get("entries", []):
        pair_id = entry.get("pair_id")
        left = entry.get("left")
        right = entry.get("right")
        ok = True
        if not isinstance(pair_id, str) or not pair_id.strip():
            ok = False
        if left not in known_ids or right not in known_ids or left == right:
            ok = False
        if entry.get("resolution") not in contract.CONFLICT_RESOLUTIONS:
            ok = False
        if not isinstance(entry.get("basis"), str) or not entry["basis"].strip():
            ok = False
        if entry.get("verified") is not True or not entry.get("checked_on"):
            ok = False
        anchor = entry.get("anchor") or {}
        if not quote_is_locatable(spdx_root, anchor.get("ref"), anchor.get("quote")):
            ok = False
        if ok:
            usable.append(entry)
        else:
            dropped.append(pair_id)
    return usable, dropped


# ---------------------------------------------------------------------------
# 独立朴素的表达式求值（自带迷你文法）
# ---------------------------------------------------------------------------


class ExprError(ValueError):
    pass


def tokenize(text):
    tokens = []
    for raw in text.replace("(", " ( ").replace(")", " ) ").split():
        tokens.append(raw)
    if not tokens:
        raise ExprError("空表达式")
    return tokens


class Parser(object):
    """``expr := term (OR term)*`` / ``term := factor (AND factor)*``。"""

    def __init__(self, tokens):
        self.tokens = tokens
        self.pos = 0

    def peek(self):
        return self.tokens[self.pos] if self.pos < len(self.tokens) else None

    def take(self):
        token = self.peek()
        if token is None:
            raise ExprError("表达式意外结束")
        self.pos += 1
        return token

    def parse(self):
        node = self.parse_expr()
        if self.peek() is not None:
            raise ExprError("尾部多余记号")
        return node

    def parse_expr(self):
        operands = [self.parse_term()]
        while self.peek() == "OR":
            self.take()
            operands.append(self.parse_term())
        return operands[0] if len(operands) == 1 else ("OR", operands)

    def parse_term(self):
        operands = [self.parse_factor()]
        while self.peek() == "AND":
            self.take()
            operands.append(self.parse_factor())
        return operands[0] if len(operands) == 1 else ("AND", operands)

    def parse_factor(self):
        token = self.take()
        if token == "(":
            node = self.parse_expr()
            if self.take() != ")":
                raise ExprError("括号未闭合")
            return node
        node = [token, None]
        if self.peek() == "WITH":
            self.take()
            node[1] = self.take()
        return tuple(node)


def node_atoms(node, out=None):
    if out is None:
        out = []
    if node[0] in ("AND", "OR"):
        for child in node[1]:
            node_atoms(child, out)
    elif node[0] not in out:
        out.append(node[0])
    return out


def node_exceptions(node, out=None):
    if out is None:
        out = []
    if node[0] in ("AND", "OR"):
        for child in node[1]:
            node_exceptions(child, out)
    elif node[1] and node[1] not in out:
        out.append(node[1])
    return out


def eval_node(node, tiers, missing):
    """``OR`` 取最宽松、``AND`` 取最严格；同档位并列取出现顺序在前者（确定性）。"""
    if node[0] in ("AND", "OR"):
        best = None
        for child in node[1]:
            leaf = eval_node(child, tiers, missing)
            if leaf is None:
                return None
            if best is None:
                best = leaf
                continue
            best_rank = contract.TIER_RANK[best[1]]
            leaf_rank = contract.TIER_RANK[leaf[1]]
            if (node[0] == "OR" and leaf_rank < best_rank) or (
                node[0] == "AND" and leaf_rank > best_rank
            ):
                best = leaf
        return best
    tier = tiers.get(node[0])
    if tier not in contract.TIERS:
        if node[0] not in missing:
            missing.append(node[0])
        return None
    return (node[0], tier)


def evaluate(expression, tiers):
    """返回可机检的期望记录（不含引擎文案）。"""
    record = {
        "expression": expression,
        "operator": None,
        "atoms": [],
        "selected": None,
        "tier": None,
        "resolved": False,
        "exceptions": [],
    }
    try:
        node = Parser(tokenize(expression)).parse()
    except ExprError:
        record["atoms"] = [expression]
        return record
    record["operator"] = node[0] if node[0] in ("AND", "OR") else "single"
    record["atoms"] = node_atoms(node)
    record["exceptions"] = node_exceptions(node)
    missing = []
    leaf = eval_node(node, tiers, missing)
    if leaf is None:
        return record
    record["selected"] = leaf[0]
    record["tier"] = leaf[1]
    record["resolved"] = True
    return record


# ---------------------------------------------------------------------------
# 真值构建
# ---------------------------------------------------------------------------


def build_truth():
    curated = read_json(os.path.join(CURATED_DIR, "conflict-pairs.json"))
    curated_tiers = read_json(os.path.join(CURATED_DIR, "tiers.json"))
    licenses = read_json(os.path.join(SPDX_DIR, "licenses.json"))
    snapshot_manifest_path = os.path.join(SPDX_DIR, "manifest.json")
    snapshot_manifest = (
        read_json(snapshot_manifest_path) if os.path.isfile(snapshot_manifest_path) else {}
    )
    known_ids = {item["licenseId"] for item in licenses.get("licenses", [])}

    usable, dropped = usable_pairs(curated, SPDX_DIR, known_ids)
    if not usable:
        raise SystemExit("curated/conflict-pairs.json 没有任何可用条目")

    tiers = tier_by_atom(curated_tiers, SPDX_DIR, known_ids)

    # 成对匹配的样本集合：规则表用到的全部许可证（覆盖表内每一条已知冲突对）。
    sample_licenses = sorted(
        {entry["left"] for entry in usable} | {entry["right"] for entry in usable}
    )

    covered = {tuple(sorted((entry["left"], entry["right"]))) for entry in usable}
    uncovered = []
    for first in range(len(sample_licenses)):
        for second in range(first + 1, len(sample_licenses)):
            key = (sample_licenses[first], sample_licenses[second])
            if key not in covered:
                uncovered.append([key[0], key[1]])
    uncovered.sort()

    expectations = [evaluate(expression, tiers) for expression in EVALUATION_EXPRESSIONS]
    atoms_used = sorted(
        {atom for item in expectations for atom in item["atoms"]}
        | set(sample_licenses)
    )
    if UNCOVERED_ATOM not in atoms_used:
        raise SystemExit("求值样本里必须有未覆盖档位的原子：{0}".format(UNCOVERED_ATOM))
    if not any(item["resolved"] is False for item in expectations):
        raise SystemExit("求值样本必须覆盖 resolved = false 分支")

    return {
        "format": TRUTH_FORMAT,
        "format_version": contract.FORMAT_VERSION,
        "inputs": {
            "ruleset_source": "references/curated/conflict-pairs.json",
            "tiers_source": "references/curated/tiers.json",
            "license_list_version": licenses.get("licenseListVersion"),
            "captured_on": snapshot_manifest.get("captured_on"),
            "pair_ids": sorted(entry["pair_id"] for entry in usable),
            "dropped_pair_ids": sorted(item for item in dropped if item),
            "pair_sample_licenses": sample_licenses,
            "evaluation_expressions": list(EVALUATION_EXPRESSIONS),
            "tier_by_atom": {
                atom: tiers.get(atom) for atom in atoms_used
            },
            "outbound_pending_value": OUTBOUND_PENDING_VALUE,
        },
        "expect": {
            "pairs": [
                {
                    "pair_id": entry["pair_id"],
                    "left": entry["left"],
                    "right": entry["right"],
                    "resolution": entry["resolution"],
                }
                for entry in sorted(usable, key=lambda item: item["pair_id"])
            ],
            "uncovered_pairs": uncovered,
            "evaluations": expectations,
            "outbound_pending": {
                "resolution": "pending",
                "basis": OUTBOUND_PENDING_BASIS,
            },
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
    if not inputs.get("pair_ids"):
        problems.append("缺少 inputs.pair_ids")
    if not inputs.get("pair_sample_licenses"):
        problems.append("缺少 inputs.pair_sample_licenses")
    if not inputs.get("tier_by_atom"):
        problems.append("缺少 inputs.tier_by_atom")
    expect = frozen.get("expect") or {}
    if not expect.get("pairs"):
        problems.append("缺少 expect.pairs")
    if not expect.get("evaluations"):
        problems.append("缺少 expect.evaluations（OR/AND 分支无人守）")
    if "uncovered_pairs" not in expect:
        problems.append("缺少 expect.uncovered_pairs（覆盖度分支无人守）")
    if not expect.get("outbound_pending"):
        problems.append("缺少 expect.outbound_pending（outbound 待定分支无人守）")

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
        prog="gen_conflict_truth",
        description="由 curated 冲突对表推导 M4 冲突真值（禁手改）",
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
        sys.stdout.write("[OK] 冲突真值与重生成结果逐字节一致：{0}\n".format(target))
        return 0

    payload = build_truth()
    write_text_atomic(target, dumps(payload))
    sys.stdout.write(
        "[OK] 冲突真值已生成：{0}；已知冲突对 {1} 条；未登记组合 {2} 对；"
        "求值样例 {3} 条\n".format(
            target,
            len(payload["expect"]["pairs"]),
            len(payload["expect"]["uncovered_pairs"]),
            len(payload["expect"]["evaluations"]),
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
