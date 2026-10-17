# -*- coding: utf-8 -*-
"""四级可信度链（K1 / K2 / K3 / K4）。

``license_expression`` > ``trove_classifier`` > ``license_first_line`` > ``truncated_fallback``
严格按序，命中即停，**不跨级合并**。

第 3 级只取首行且首行 >200 字符不匹配（K2）——这是 pandas 61K 字符字段不会误命中的原因。
"""

from .. import contract
from .spdx_expr import (
    ExprError,
    anchored_first_line,
    parse_expression,
)

CONFIDENCE_LEVELS = contract.CONFIDENCE_LEVELS

FALLBACK_TEXT_LIMIT = 200
FLAG_VERSION_AMBIGUOUS = "version-ambiguous"


class Normalized(object):
    """归一化结果。"""

    __slots__ = (
        "spdx_id",
        "confidence",
        "raw_license",
        "flags",
        "details_urls",
        "matched_token",
    )

    def __init__(self, spdx_id, confidence, raw_license, flags,
                 details_urls, matched_token):
        self.spdx_id = spdx_id
        self.confidence = confidence
        self.raw_license = raw_license
        self.flags = flags
        self.details_urls = details_urls
        self.matched_token = matched_token

    @property
    def needs_confirmation(self):
        if self.spdx_id is None:
            return True
        if self.confidence == contract.CONFIDENCE_LEVELS[-1]:
            return True
        return bool(self.flags)

    def to_dict(self):
        return {
            "spdx_id": self.spdx_id,
            "confidence": self.confidence,
            "raw_license": self.raw_license,
            "flags": list(self.flags),
            "needs_confirmation": self.needs_confirmation,
        }


def _truncate(text):
    if text is None:
        return None
    text = text.strip()
    if len(text) <= FALLBACK_TEXT_LIMIT:
        return text
    return text[:FALLBACK_TEXT_LIMIT]


def _first_line(text):
    if not isinstance(text, str):
        return ""
    for separator in ("\r\n", "\r", "\n"):
        if separator in text:
            text = text.split(separator, 1)[0]
            break
    return text.strip()


def normalize_license(raw_license, spdx_index, trove_classifiers=None,
                      trove_map=None, structured=True):
    """把一条清单记录归一化。

    ``structured=False`` 表示调用方已判定该值不是结构化字段（如 pom 的自由文本），
    第 1 级直接跳过，从 trove 开始。
    """
    trove_classifiers = list(trove_classifiers or [])

    # ---- 第 1 级：结构化表达式 ----
    if structured and isinstance(raw_license, str) and raw_license.strip():
        try:
            parsed = parse_expression(raw_license.strip(), spdx_index)
        except ExprError:
            parsed = None
        if parsed is not None and parsed.atoms:
            flags = list(parsed.flags)
            deprecated = parsed.deprecated_atoms(spdx_index)
            if deprecated:
                flags.append("deprecated-id")
            return Normalized(
                spdx_id=parsed.text,
                confidence="license_expression",
                raw_license=_truncate(raw_license),
                flags=flags,
                details_urls=parsed.details_urls(spdx_index),
                matched_token=raw_license.strip(),
            )

    # ---- 第 2 级：trove classifier ----
    if trove_classifiers:
        mapping = {entry.get("classifier"): entry for entry in (trove_map or [])}
        for classifier in trove_classifiers:
            entry = mapping.get(classifier)
            if not entry:
                continue
            spdx_id = entry.get("spdx_id")
            if not spdx_id:
                continue
            url = spdx_index.details_url(spdx_id)
            return Normalized(
                spdx_id=spdx_id,
                confidence="trove_classifier",
                raw_license=_truncate(raw_license if isinstance(raw_license, str) else None),
                flags=[],
                details_urls=[url] if url else [],
                matched_token=classifier,
            )

    # ---- 第 3 级：首行锚定 ----
    if isinstance(raw_license, str) and raw_license.strip():
        first_line = _first_line(raw_license)
        matched, flags = anchored_first_line(first_line, spdx_index)
        if matched:
            urls = []
            for atom in _atoms_for(matched, spdx_index):
                url = spdx_index.details_url(atom)
                if url and url not in urls:
                    urls.append(url)
            return Normalized(
                spdx_id=matched,
                confidence="license_first_line",
                raw_license=_truncate(raw_license),
                flags=list(flags),
                details_urls=urls,
                matched_token=first_line,
            )

    # ---- 第 4 级：截断兜底 ----
    return Normalized(
        spdx_id=None,
        confidence="truncated_fallback",
        raw_license=_truncate(raw_license if isinstance(raw_license, str) else None),
        flags=["unresolved"],
        details_urls=[],
        matched_token=None,
    )


def _atoms_for(spdx_id, spdx_index):
    try:
        parsed = parse_expression(spdx_id, spdx_index)
        return parsed.atoms
    except ExprError:
        return [spdx_id]


__all__ = [
    "CONFIDENCE_LEVELS",
    "FALLBACK_TEXT_LIMIT",
    "FLAG_VERSION_AMBIGUOUS",
    "Normalized",
    "normalize_license",
]
