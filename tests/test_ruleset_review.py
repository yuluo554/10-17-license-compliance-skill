# -*- coding: utf-8 -*-
"""规则集复核元数据守门（阶段三 任务 5）。

字段规范 = ``10-6-scaffold-formwork-checker`` v2.0.0 的实测形态（文件级 ``meta.review``：
``reviewed_on`` / ``cycle_months`` / ``next_review_due`` / ``reviewer`` / ``standards[]``）。

本仓的「规则集定义文件」是 ``references/ruleset/manifest.json`` —— 它是规则包的描述符，
由 ``tools/gen_ruleset.py`` 生成、随包冻结、并受 loader 硬门校验，因此复核元数据写在它的
``meta.review`` 下（而不是逐份规则文件重复同一段结论）。

scaffold 的 5 条用例中，第 4/5 条是它特有的形态（``panorama`` 条目级 status 一致 /
``not_used_by`` 声明），本仓没有对应物，替换为同等强度的两条：

4. 复核元数据登记的版本必须与 manifest 实际版本一致（防「元数据写的不是这一版」）；
5. 每部标准必须给出 ``currency``（是否现行）与 ``conclusion``（对引用范围的影响）。

以上任一判据被破坏都必须报红 —— 负控记录见 plan/audits 的阶段三交接文档。
"""

import datetime
import io
import json
import os

import pytest

from _helpers import REPO_ROOT

MANIFEST = os.path.join(REPO_ROOT, "references", "ruleset", "manifest.json")
REQUIRED_REVIEW_KEYS = ("reviewed_on", "cycle_months", "next_review_due", "reviewer",
                        "standards")
REQUIRED_STANDARD_KEYS = ("standard", "issued", "effective", "currency",
                          "authority_url", "conclusion")


def _manifest():
    with io.open(MANIFEST, encoding="utf-8") as stream:
        return json.load(stream)


def _review():
    return (_manifest().get("meta") or {}).get("review") or {}


def _date(text):
    return datetime.datetime.strptime(text, "%Y-%m-%d").date()


def test_ruleset_manifest_carries_review_metadata():
    review = _review()
    assert review, "manifest.json 缺 meta.review（阶段三 任务 5 的字段规范）"
    for key in REQUIRED_REVIEW_KEYS:
        assert review.get(key) not in (None, "", []), "meta.review 缺字段：%s" % key
    assert isinstance(review.get("cycle_months"), int) and review["cycle_months"] > 0


def test_review_dates_are_parsable_and_next_due_is_after_reviewed_on():
    review = _review()
    reviewed = _date(review["reviewed_on"])
    due = _date(review["next_review_due"])
    assert due > reviewed, "next_review_due 必须晚于 reviewed_on"
    # cycle_months 与两个日期之间的跨度一致（±1 个月，容忍月末）
    months = (due.year - reviewed.year) * 12 + (due.month - reviewed.month)
    assert abs(months - review["cycle_months"]) <= 1, (
        "cycle_months=%s 与 %s→%s 的跨度不符" % (review["cycle_months"],
                                                reviewed, due))


def test_every_standard_carries_authority_url():
    for item in _review().get("standards") or []:
        url = (item.get("authority_url") or "").strip()
        assert url, "标准 %r 缺 authority_url" % item.get("standard")
        assert all(part.strip().startswith("http") for part in url.split(";") if part.strip())


@pytest.mark.parametrize("key", ["ruleset_version", "license_list_version"])
def test_review_versions_match_manifest(key):
    """复核元数据里的版本号必须与 manifest 实际版本一致（防元数据脱离版本）。"""
    manifest = _manifest()
    declared = str(manifest.get(key) or "")
    assert declared, "manifest 缺 %s" % key
    joined = json.dumps(_review(), ensure_ascii=False)
    assert declared in joined, "meta.review 未登记当前 %s=%s" % (key, declared)


def test_every_standard_declares_currency_and_conclusion():
    standards = _review().get("standards") or []
    assert standards, "meta.review.standards 为空 —— 复核没有出处"
    for item in standards:
        for key in REQUIRED_STANDARD_KEYS:
            assert (item.get(key) or "").strip(), (
                "标准 %r 缺 %s" % (item.get("standard"), key))