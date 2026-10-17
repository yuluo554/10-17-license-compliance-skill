# -*- coding: utf-8 -*-
"""SKILL.md 机器契约块 ↔ 代码常量 双向一致性。

三方断言：
1. 契约块存在且唯一；
2. 契约块字段集合 == 代码常量（双向：文档不许多、不许少）；
3. 契约块字段序 == 代码常量序（顺序相等）。

另加：报告章节声明、退出码表、人读字段表各自独立成门——
「N 处对齐」必须是 N 个门，不是一个门看 N 处。
"""

import io
import os
import re

import pytest

from licaudit import contract

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_PATH = os.path.join(REPO_ROOT, "SKILL.md")


def read_skill():
    with io.open(SKILL_PATH, encoding="utf-8") as stream:
        return stream.read()


def extract_block(text, name):
    pattern = re.compile(r"<!--\s*" + re.escape(name) + r":\s*(.*?)\s*-->")
    matches = pattern.findall(text)
    assert len(matches) == 1, "契约块 {0} 应恰好出现一次，实际 {1}".format(name, len(matches))
    return matches[0].split()


@pytest.mark.parametrize(
    "block_name,constant_name",
    [
        ("contract-fields", "INVENTORY_RECORD_FIELDS"),
        ("contract-profile", "PROFILE_FIELDS"),
        ("contract-scenario", "SCENARIO_FIELDS"),
        ("contract-conflict", "CONFLICT_FIELDS"),
        ("contract-action", "ACTION_FIELDS"),
    ],
)
def test_contract_block_matches_code(block_name, constant_name):
    declared = extract_block(read_skill(), block_name)
    expected = list(getattr(contract, constant_name))
    # 集合相等（双向）
    assert set(declared) == set(expected), (
        "契约块与代码字段集合不一致: 文档多 {0} / 代码多 {1}".format(
            set(declared) - set(expected), set(expected) - set(declared)
        )
    )
    # 顺序相等
    assert declared == expected, "契约块字段序与代码常量序不一致"


def test_report_sections_block_matches_code():
    declared = extract_block(read_skill(), "report-sections")
    assert declared == list(contract.REPORT_SECTIONS)


def test_report_sections_end_with_disclaimer():
    assert contract.REPORT_SECTIONS[-1] == "免责声明"


def test_exit_code_block_matches_code():
    declared = extract_block(read_skill(), "exit-codes")
    codes = {}
    for token in declared:
        match = re.match(r"^(\d)=(.*)$", token)
        assert match, "退出码块条目形态应为 N=含义: {0}".format(token)
        codes[int(match.group(1))] = match.group(2)
    assert set(codes) == {0, 1, 2, 3}

    from licaudit import exit_codes

    assert set(codes) == set(exit_codes.EXIT_CODES)


def test_skill_has_disclaimer_verbatim():
    assert contract.DISCLAIMER in read_skill()


def test_skill_declares_all_eight_scenarios():
    text = read_skill()
    for scenario in contract.SCENARIO_IDS:
        assert scenario in text, "SKILL.md 未声明场景 {0}".format(scenario)


def test_skill_declares_all_tiers():
    text = read_skill()
    for tier in contract.TIERS:
        assert tier in text, "SKILL.md 未声明档位 {0}".format(tier)


def test_skill_declares_all_action_levels():
    text = read_skill()
    for level in contract.ACTION_LEVELS:
        assert level in text, "SKILL.md 未声明处置级别 {0}".format(level)


def test_contract_blocks_are_not_duplicated():
    text = read_skill()
    for name in (
        "contract-fields",
        "contract-profile",
        "contract-scenario",
        "contract-conflict",
        "contract-action",
        "report-sections",
        "exit-codes",
    ):
        count = len(re.findall(r"<!--\s*" + re.escape(name) + r":", text))
        assert count == 1, "契约块 {0} 重复出现 {1} 次".format(name, count)
