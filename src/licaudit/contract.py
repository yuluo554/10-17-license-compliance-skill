# -*- coding: utf-8 -*-
"""对外契约的唯一来源。

``SKILL.md`` 里的机器可解析契约块、报告章节声明、退出码表都以本模块为准；
测试做「契约块 ≡ 本模块常量 ≡ 实际序列化字段序」三方断言。

改这里的任何元组顺序都是一次契约变更：同步改 ``SKILL.md`` 与测试。
"""

FORMAT_VERSION = 1

INVENTORY_FORMAT = "licaudit-inventory"
PROFILE_FORMAT = "licaudit-profile"
SCENARIO_FORMAT = "licaudit-scenario"
CONFLICT_FORMAT = "licaudit-conflicts"
ACTION_FORMAT = "licaudit-actions"

KNOWN_FORMATS = (
    INVENTORY_FORMAT,
    PROFILE_FORMAT,
    SCENARIO_FORMAT,
    CONFLICT_FORMAT,
    ACTION_FORMAT,
)

INVENTORY_RECORD_FIELDS = (
    "package",
    "version",
    "raw_license",
    "spdx_id",
    "confidence",
    "evidence",
)

PROFILE_FIELDS = (
    "spdx_id",
    "tier",
    "obligations",
    "is_osi_approved",
    "is_fsf_libre",
    "patent_clause",
    "trademark_clause",
    "evidence",
)

SCENARIO_FIELDS = (
    "package",
    "scenario",
    "link_mode",
    "triggers",
    "verdict",
    "evidence",
)

CONFLICT_FIELDS = (
    "pair_id",
    "left",
    "right",
    "basis",
    "resolution",
    "evidence",
)

ACTION_FIELDS = (
    "package",
    "version",
    "spdx_id",
    "level",
    "reasons",
    "evidence",
)

REPORT_SECTIONS = (
    "概述",
    "口径声明",
    "证据锚点",
    "逐包明细",
    "风险分级",
    "处置建议",
    "待人工确认项",
    "免责声明",
)

REPORT_CSV_COLUMNS = (
    "package",
    "version",
    "spdx_id",
    "tier",
    "scenario",
    "verdict",
    "action_level",
    "basis_clause",
    "declaration_location",
    "notes",
)

DISCLAIMER = (
    "本清单由自动化工具生成，不构成法律意见（非法律意见）。"
    "涉及商业分发、诉讼或高价值交易时，请咨询执业律师。"
)

CONFIDENCE_LEVELS = (
    "license_expression",
    "trove_classifier",
    "license_first_line",
    "truncated_fallback",
)

TIERS = (
    "permissive",
    "weak-copyleft",
    "strong-copyleft",
    "network-copyleft",
    "source-available",
)

TIER_RANK = {
    "permissive": 0,
    "weak-copyleft": 1,
    "strong-copyleft": 2,
    "network-copyleft": 3,
    "source-available": 4,
}

OBLIGATIONS = (
    "retain-copyright",
    "include-license-text",
    "mark-modifications",
    "provide-source",
    "network-source",
    "patent-grant",
    "trademark-restriction",
    "same-license",
)

ACTION_LEVELS = (
    "ok",
    "declare",
    "isolate",
    "replace_or_license",
)

BLOCKING_ACTION_LEVELS = ("isolate", "replace_or_license")

SCENARIO_IDS = (
    "internal",
    "distribute-binary",
    "distribute-source",
    "saas",
    "static-link",
    "dynamic-link",
    "separate-process",
    "container-image",
)

SCENARIO_AXES = {
    "internal": {"delivery": "internal", "link_mode": "none"},
    "distribute-binary": {"delivery": "binary", "link_mode": "none"},
    "distribute-source": {"delivery": "source", "link_mode": "none"},
    "saas": {"delivery": "saas", "link_mode": "none"},
    "static-link": {"delivery": None, "link_mode": "static"},
    "dynamic-link": {"delivery": None, "link_mode": "dynamic"},
    "separate-process": {"delivery": None, "link_mode": "separate-process"},
    "container-image": {"delivery": "container", "link_mode": "none"},
}

LINK_MODES = ("none", "static", "dynamic", "separate-process")

VERDICTS = (
    "triggered",
    "not_triggered",
    "pending_confirmation",
)

CONFLICT_RESOLUTIONS = (
    "compatible",
    "incompatible",
    "pending",
)

PENDING = "pending_confirmation"
